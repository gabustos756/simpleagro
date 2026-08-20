"""
Proveedor Meteorológico Asíncrono de Open-Meteo (EduAgro).
Obtiene reportes horarios (con ráfagas) y diarios de 14 días desde la API de Open-Meteo.
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
import httpx

from app.services.weather.models import (
    NormalizedWeatherSnapshot,
    WeatherLocation,
    WeatherCurrent,
    WeatherHourlyPoint,
    WeatherDailyPoint,
    WeatherDataQuality,
)
from app.services.weather.provider_base import (
    WeatherProvider,
    WeatherProviderError,
    calculate_aggregates_from_hourly,
)


def deg_to_cardinal(deg: float) -> str:
    """Convierte grados de dirección del viento a puntos cardinales."""
    val = int((deg / 22.5) + 0.5)
    arr = ["N", "NE", "NE", "E", "E", "SE", "SE", "S", "S", "SO", "SO", "O", "O", "NO", "NO", "N"]
    return arr[val % 16]


def decode_wmo_code(code: int) -> str:
    """Decodifica el código de clima WMO de Open-Meteo a descripción en español con emoji."""
    wmo_map = {
        0: "☀️ Despejado",
        1: "🌤️ Principalmente despejado",
        2: "🌤️ Parcialmente nublado",
        3: "☁️ Nublado",
        45: "🌫️ Niebla",
        48: "🌫️ Niebla con escarcha",
        51: "🌦️ Llovizna ligera",
        53: "🌦️ Llovizna moderada",
        55: "🌦️ Llovizna densa",
        61: "🌧️ Lluvia ligera",
        63: "🌧️ Lluvia moderada",
        65: "🌧️ Lluvia fuerte",
        71: "❄️ Nieve ligera",
        73: "❄️ Nieve moderada",
        75: "❄️ Nieve fuerte",
        80: "🌧️ Chubascos ligeros",
        81: "🌧️ Chubascos moderados",
        82: "🌧️ Chubascos violentos",
        95: "⛈️ Tormenta eléctrica",
        96: "⛈️ Tormenta con granizo ligero",
        99: "⛈️ Tormenta con granizo fuerte",
    }
    return wmo_map.get(code, "🌤️ Algo nublado")


class OpenMeteoProvider(WeatherProvider):
    provider_name: str = "open_meteo"

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None, timeout: float = 5.0, max_retries: int = 2):
        self._custom_client = http_client
        self.timeout = timeout
        self.max_retries = max_retries

    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        timezone: str = "America/Argentina/Cordoba",
        requested_at: Optional[datetime] = None,
    ) -> NormalizedWeatherSnapshot:
        req_time = requested_at or datetime.now()
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
            "hourly": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_sum,precipitation_hours,wind_speed_10m_max,wind_gusts_10m_max",
            "forecast_days": 14,
            "timezone": timezone,
        }

        should_close = False
        client = self._custom_client
        if client is None:
            client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
            should_close = True

        try:
            raw_data = await self._http_get_with_retry(
                client,
                url,
                params=params,
                max_retries=self.max_retries,
                timeout=self.timeout,
            )
            return self.normalize(raw_data, latitude, longitude, timezone, req_time)
        finally:
            if should_close and client:
                await client.aclose()

    def normalize(
        self,
        raw_data: Dict[str, Any],
        latitude: float,
        longitude: float,
        timezone: str,
        requested_at: datetime,
    ) -> NormalizedWeatherSnapshot:
        current_raw = raw_data.get("current", {})
        hourly_raw = raw_data.get("hourly", {})
        daily_raw = raw_data.get("daily", {})

        missing_fields: List[str] = []

        # Current
        temp_c = current_raw.get("temperature_2m")
        rh_pct = current_raw.get("relative_humidity_2m")
        app_temp = current_raw.get("apparent_temperature")
        precip_curr = current_raw.get("precipitation", 0.0)
        w_code = current_raw.get("weather_code")
        v_speed = current_raw.get("wind_speed_10m")
        v_gust = current_raw.get("wind_gusts_10m")
        v_deg = current_raw.get("wind_direction_10m")

        if temp_c is None:
            missing_fields.append("current.temperature_2m")
        if rh_pct is None:
            missing_fields.append("current.relative_humidity_2m")

        w_desc = decode_wmo_code(int(w_code)) if w_code is not None else "🌤️ Desconocido"

        current_obj = WeatherCurrent(
            temperature_c=float(temp_c) if temp_c is not None else None,
            relative_humidity_pct=int(rh_pct) if rh_pct is not None else None,
            apparent_temperature_c=float(app_temp) if app_temp is not None else None,
            precipitation_mm=float(precip_curr) if precip_curr is not None else 0.0,
            weather_code=int(w_code) if w_code is not None else None,
            weather_description=w_desc,
            wind_speed_kmh=float(v_speed) if v_speed is not None else None,
            wind_gust_kmh=float(v_gust) if v_gust is not None else None,
            wind_direction_deg=int(v_deg) if v_deg is not None else None,
        )

        # Hourly
        h_times = hourly_raw.get("time", [])
        h_temps = hourly_raw.get("temperature_2m", [])
        h_rhs = hourly_raw.get("relative_humidity_2m", [])
        h_stemps = hourly_raw.get("apparent_temperature", [])
        h_precip = hourly_raw.get("precipitation", [])
        h_viento = hourly_raw.get("wind_speed_10m", [])
        h_gust = hourly_raw.get("wind_gusts_10m", [])
        h_vdeg = hourly_raw.get("wind_direction_10m", [])
        h_wcode = hourly_raw.get("weather_code", [])

        hourly_list: List[WeatherHourlyPoint] = []
        for i in range(len(h_times)):
            wc = int(h_wcode[i]) if i < len(h_wcode) and h_wcode[i] is not None else None
            wd = decode_wmo_code(wc) if wc is not None else None

            pt = WeatherHourlyPoint(
                time=str(h_times[i]),
                temperature_c=float(h_temps[i]) if i < len(h_temps) and h_temps[i] is not None else None,
                relative_humidity_pct=int(h_rhs[i]) if i < len(h_rhs) and h_rhs[i] is not None else None,
                apparent_temperature_c=float(h_stemps[i]) if i < len(h_stemps) and h_stemps[i] is not None else None,
                precipitation_mm=float(h_precip[i]) if i < len(h_precip) and h_precip[i] is not None else None,
                wind_speed_kmh=float(h_viento[i]) if i < len(h_viento) and h_viento[i] is not None else None,
                wind_gust_kmh=float(h_gust[i]) if i < len(h_gust) and h_gust[i] is not None else None,
                wind_direction_deg=int(h_vdeg[i]) if i < len(h_vdeg) and h_vdeg[i] is not None else None,
                weather_code=wc,
                weather_description=wd,
            )
            hourly_list.append(pt)

        # Daily
        d_times = daily_raw.get("time", [])
        d_tmax = daily_raw.get("temperature_2m_max", [])
        d_tmin = daily_raw.get("temperature_2m_min", [])
        d_stmax = daily_raw.get("apparent_temperature_max", [])
        d_stmin = daily_raw.get("apparent_temperature_min", [])
        d_precip = daily_raw.get("precipitation_sum", [])
        d_phours = daily_raw.get("precipitation_hours", [])
        d_vmax = daily_raw.get("wind_speed_10m_max", [])
        d_gmax = daily_raw.get("wind_gusts_10m_max", [])
        d_wcode = daily_raw.get("weather_code", [])

        dias_semana_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        daily_list: List[WeatherDailyPoint] = []

        for i in range(len(d_times)):
            dt_str = str(d_times[i])
            try:
                dt_obj = date.fromisoformat(dt_str)
                dia_nombre = "Hoy" if i == 0 else ("Mañana" if i == 1 else dias_semana_es[dt_obj.weekday()])
            except Exception:
                dia_nombre = dt_str

            wc = int(d_wcode[i]) if i < len(d_wcode) and d_wcode[i] is not None else None
            wd = decode_wmo_code(wc) if wc is not None else None

            dp = WeatherDailyPoint(
                date=dt_str,
                day_name=dia_nombre,
                temp_min_c=float(d_tmin[i]) if i < len(d_tmin) and d_tmin[i] is not None else None,
                temp_max_c=float(d_tmax[i]) if i < len(d_tmax) and d_tmax[i] is not None else None,
                apparent_temp_min_c=float(d_stmin[i]) if i < len(d_stmin) and d_stmin[i] is not None else None,
                apparent_temp_max_c=float(d_stmax[i]) if i < len(d_stmax) and d_stmax[i] is not None else None,
                precipitation_mm=float(d_precip[i]) if i < len(d_precip) and d_precip[i] is not None else None,
                precipitation_hours=float(d_phours[i]) if i < len(d_phours) and d_phours[i] is not None else None,
                wind_speed_max_kmh=float(d_vmax[i]) if i < len(d_vmax) and d_vmax[i] is not None else None,
                wind_gust_max_kmh=float(d_gmax[i]) if i < len(d_gmax) and d_gmax[i] is not None else None,
                weather_code=wc,
                weather_description=wd,
            )
            daily_list.append(dp)

        aggregates_obj = calculate_aggregates_from_hourly(hourly_list, daily_list)

        quality = WeatherDataQuality(
            missing_fields=missing_fields,
            warnings=[],
            is_complete=len(missing_fields) == 0,
        )

        return NormalizedWeatherSnapshot(
            provider=self.provider_name,
            provider_status="live",
            retrieved_at=requested_at,
            observed_at=requested_at,
            forecast_generated_at=requested_at,
            location=WeatherLocation(
                latitude=latitude,
                longitude=longitude,
                timezone=timezone,
            ),
            current=current_obj,
            hourly=hourly_list,
            daily=daily_list,
            aggregates=aggregates_obj,
            data_quality=quality,
            raw_payload_reference="open_meteo_response",
            schema_version="v2.0",
        )
