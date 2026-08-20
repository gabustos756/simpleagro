"""
Proveedor Meteorológico Asíncrono para Google Weather API (EduAgro).
Integración oficial utilizando la API de Google Weather / Maps Platform.
Protege las API Keys redactándolas en logs y payloads expuestos.
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
import logging
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

logger = logging.getLogger("eduagro.weather.google_provider")


def adapt_google_condition_code(condition_val: Any) -> tuple[Optional[int], str]:
    """
    Mapea el código/condición en texto, dict o enum de Google Weather a un código y descripción neutral con emoji.
    """
    if not condition_val:
        return (None, "🌤️ Algo nublado")

    if isinstance(condition_val, dict):
        cond_text = condition_val.get("type") or condition_val.get("condition") or condition_val.get("text") or str(condition_val)
    else:
        cond_text = str(condition_val)

    if not isinstance(cond_text, str):
        cond_text = str(cond_text)

    c_norm = cond_text.upper()
    mapping = {
        "CLEAR": (0, "☀️ Despejado"),
        "SUNNY": (0, "☀️ Despejado"),
        "MOSTLY_CLEAR": (1, "🌤️ Principalmente despejado"),
        "PARTLY_CLOUDY": (2, "🌤️ Parcialmente nublado"),
        "MOSTLY_CLOUDY": (3, "☁️ Mayormente nublado"),
        "CLOUDY": (3, "☁️ Nublado"),
        "FOG": (45, "🌫️ Niebla"),
        "LIGHT_RAIN": (61, "🌧️ Lluvia ligera"),
        "RAIN": (63, "🌧️ Lluvia moderada"),
        "HEAVY_RAIN": (65, "🌧️ Lluvia fuerte"),
        "SHOWERS": (80, "🌧️ Chubascos"),
        "THUNDERSTORM": (95, "⛈️ Tormenta eléctrica"),
        "SNOW": (73, "❄️ Nieve"),
    }
    return mapping.get(c_norm, (2, f"🌤️ {cond_text.replace('_', ' ').capitalize()}"))


class GoogleWeatherProvider(WeatherProvider):
    provider_name: str = "google_weather"

    def __init__(
        self,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        timeout: float = 5.0,
        max_retries: int = 2,
    ):
        self.api_key = api_key
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

        # Validación estricta de coordenadas
        if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            raise WeatherProviderError(
                f"Coordenadas fuera de rango válido: lat={latitude}, lon={longitude}",
                provider=self.provider_name,
            )

        if not self.api_key:
            raise WeatherProviderError(
                "API Key de Google Weather no configurada en el servidor",
                status_code=401,
                provider=self.provider_name,
            )

        # Endpoint oficial de la API de Google Weather / Environmental APIs
        url = "https://weather.googleapis.com/v1/currentConditions:lookup"
        params = {
            "location.latitude": round(latitude, 4),
            "location.longitude": round(longitude, 4),
            "key": self.api_key,
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
        except WeatherProviderError:
            raise
        except Exception as e:
            logger.warning(f"[GOOGLE WEATHER] Error al procesar la API de Google: {type(e).__name__}")
            raise WeatherProviderError(
                f"Error al procesar respuesta de Google Weather API: {str(e)}",
                provider=self.provider_name,
            ) from e
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
        missing_fields: List[str] = []
        warnings: List[str] = []

        curr_data = raw_data.get("currentConditions", raw_data)

        # Mapeo de campos actuales
        temp_c = curr_data.get("temperature", {}).get("degrees") if isinstance(curr_data.get("temperature"), dict) else curr_data.get("temperature_c")
        rh_pct = curr_data.get("relativeHumidity") or curr_data.get("humidity")
        app_temp = curr_data.get("feelsLikeTemperature", {}).get("degrees") if isinstance(curr_data.get("feelsLike"), dict) else curr_data.get("apparent_temperature_c")
        precip = curr_data.get("precipitation", {}).get("qpfQuantity", {}).get("amount") if isinstance(curr_data.get("precipitation"), dict) else curr_data.get("precipitation_mm", 0.0)
        
        wind_data = curr_data.get("wind", {}) if isinstance(curr_data.get("wind"), dict) else {}
        wind_speed = wind_data.get("speed", {}).get("value") if isinstance(wind_data.get("speed"), dict) else curr_data.get("wind_speed_kmh")
        wind_gust = wind_data.get("gust", {}).get("value") if isinstance(wind_data.get("gust"), dict) else curr_data.get("wind_gust_kmh")
        wind_deg = wind_data.get("direction", {}).get("degrees") if isinstance(wind_data.get("direction"), dict) else curr_data.get("wind_direction_deg")

        cond_type = curr_data.get("weatherCondition") or curr_data.get("condition")
        w_code, w_desc = adapt_google_condition_code(cond_type)

        if temp_c is None:
            missing_fields.append("current.temperature")
        if rh_pct is None:
            missing_fields.append("current.relativeHumidity")

        current_obj = WeatherCurrent(
            temperature_c=float(temp_c) if temp_c is not None else None,
            relative_humidity_pct=int(rh_pct) if rh_pct is not None else None,
            apparent_temperature_c=float(app_temp) if app_temp is not None else None,
            precipitation_mm=float(precip) if precip is not None else 0.0,
            weather_code=w_code,
            weather_description=w_desc,
            wind_speed_kmh=float(wind_speed) if wind_speed is not None else None,
            wind_gust_kmh=float(wind_gust) if wind_gust is not None else None,
            wind_direction_deg=int(wind_deg) if wind_deg is not None else None,
        )

        # Si el endpoint de condiciones actuales no retornó series horarias/diarias completas de Google:
        # Se registran los campos faltantes explícitamente en data_quality
        hourly_list: List[WeatherHourlyPoint] = []
        hourly_raw = raw_data.get("hourlyForecasts", raw_data.get("hourly", []))
        if not hourly_raw:
            missing_fields.append("hourlyForecasts")
            warnings.append("Google Weather respondió condiciones actuales sin serie horaria completa")
        else:
            for item in hourly_raw[:72]:
                h_code, h_desc = adapt_google_condition_code(item.get("condition"))
                hourly_list.append(
                    WeatherHourlyPoint(
                        time=str(item.get("time")),
                        temperature_c=float(item.get("temp_c")) if item.get("temp_c") is not None else None,
                        relative_humidity_pct=int(item.get("rh")) if item.get("rh") is not None else None,
                        apparent_temperature_c=float(item.get("feels_c")) if item.get("feels_c") is not None else None,
                        precipitation_mm=float(item.get("precip_mm")) if item.get("precip_mm") is not None else None,
                        wind_speed_kmh=float(item.get("wind_kmh")) if item.get("wind_kmh") is not None else None,
                        wind_gust_kmh=float(item.get("gust_kmh")) if item.get("gust_kmh") is not None else None,
                        wind_direction_deg=int(item.get("wind_deg")) if item.get("wind_deg") is not None else None,
                        weather_code=h_code,
                        weather_description=h_desc,
                    )
                )

        daily_list: List[WeatherDailyPoint] = []
        daily_raw = raw_data.get("dailyForecasts", raw_data.get("daily", []))
        if not daily_raw:
            missing_fields.append("dailyForecasts")
        else:
            dias_semana_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            for i, item in enumerate(daily_raw[:14]):
                dt_str = str(item.get("date", item.get("fecha")))
                try:
                    dt_obj = date.fromisoformat(dt_str)
                    dia_nombre = "Hoy" if i == 0 else ("Mañana" if i == 1 else dias_semana_es[dt_obj.weekday()])
                except Exception:
                    dia_nombre = dt_str

                d_code, d_desc = adapt_google_condition_code(item.get("condition"))
                daily_list.append(
                    WeatherDailyPoint(
                        date=dt_str,
                        day_name=dia_nombre,
                        temp_min_c=float(item.get("temp_min")) if item.get("temp_min") is not None else None,
                        temp_max_c=float(item.get("temp_max")) if item.get("temp_max") is not None else None,
                        apparent_temp_min_c=float(item.get("feels_min")) if item.get("feels_min") is not None else None,
                        apparent_temp_max_c=float(item.get("feels_max")) if item.get("feels_max") is not None else None,
                        precipitation_mm=float(item.get("precip_mm")) if item.get("precip_mm") is not None else None,
                        precipitation_hours=float(item.get("precip_hours")) if item.get("precip_hours") is not None else None,
                        wind_speed_max_kmh=float(item.get("wind_max")) if item.get("wind_max") is not None else None,
                        wind_gust_max_kmh=float(item.get("gust_max")) if item.get("gust_max") is not None else None,
                        weather_code=d_code,
                        weather_description=d_desc,
                    )
                )

        aggregates_obj = calculate_aggregates_from_hourly(hourly_list, daily_list)

        quality = WeatherDataQuality(
            missing_fields=missing_fields,
            warnings=warnings,
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
            raw_payload_reference="google_weather_response",
            schema_version="v2.0",
        )
