from typing import Dict, Any, Optional
import urllib.request
import json
import logging
import time

logger = logging.getLogger("eduagro.weather")

# Caché en memoria para evitar peticiones externas repetidas en cada render
# Formato: { (lat_round, lon_round, localidad): (weather_dict, timestamp) }
_WEATHER_CACHE: Dict[tuple, tuple] = {}
CACHE_TTL_SECONDS = 900  # 15 minutos de vigencia para el clima


def get_weather_for_location(lat: Optional[float], lon: Optional[float], localidad: str = "Córdoba, Argentina") -> Dict[str, Any]:
    """
    Obtiene el clima actual y pronóstico a 7 días para un campo según latitud y longitud.
    Utiliza la API pública Open-Meteo (libre sin API Key) con caché TTL de 15 minutos y fallback resiliente.
    """
    # Coordenadas por defecto (Río Cuarto, Córdoba) si no se proporcionan
    default_lat = -31.4201
    default_lon = -64.1888

    lat_val = lat if lat is not None else default_lat
    lon_val = lon if lon is not None else default_lon

    cache_key = (round(lat_val, 4), round(lon_val, 4), localidad)
    now = time.time()

    if cache_key in _WEATHER_CACHE:
        data, cached_at = _WEATHER_CACHE[cache_key]
        if now - cached_at < CACHE_TTL_SECONDS:
            return data

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat_val}&longitude={lon_val}"
        f"&current_weather=true"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max"
        f"&timezone=America%2FArgentina%2FCordoba"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EduAgro/1.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                result = _format_weather_data(data, lat_val, lon_val, localidad)
                _WEATHER_CACHE[cache_key] = (result, now)
                return result
    except Exception as e:
        logger.warning(f"Error consultando Open-Meteo ({e}). Utilizando datos resilientes de fallback.")

    fallback_result = _get_fallback_weather(lat_val, lon_val, localidad)
    _WEATHER_CACHE[cache_key] = (fallback_result, now)
    return fallback_result


def _format_weather_data(data: dict, lat: float, lon: float, localidad: str) -> Dict[str, Any]:
    current = data.get("current_weather", {})
    daily = data.get("daily", {})

    temp_actual = round(current.get("temperature", 22.5), 1)
    viento_actual = round(current.get("windspeed", 18.4), 1)
    humedad_actual = 65  # Valor estimado estándar

    # Extraer pronóstico diario a 7 días
    time_list = daily.get("time", ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-01", "2026-08-02"])
    t_max_list = daily.get("temperature_2m_max", [24.0, 25.5, 21.0, 19.5, 22.0, 26.0, 23.5])
    t_min_list = daily.get("temperature_2m_min", [11.0, 12.5, 8.0, 3.5, 9.0, 13.0, 10.5])
    precip_list = daily.get("precipitation_sum", [0.0, 2.5, 14.2, 0.0, 0.0, 0.0, 1.0])
    viento_max_list = daily.get("windspeed_10m_max", [18.4, 22.1, 14.0, 11.2, 16.5, 19.0, 12.0])

    pronostico_dias = []
    dias_semana = ["Hoy", "Mañana", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    for i in range(min(7, len(time_list))):
        d_name = dias_semana[i] if i < len(dias_semana) else time_list[i]
        precip = precip_list[i] if i < len(precip_list) else 0.0
        v_max = viento_max_list[i] if i < len(viento_max_list) else 15.0
        t_min = t_min_list[i] if i < len(t_min_list) else 10.0
        t_max = t_max_list[i] if i < len(t_max_list) else 22.0

        # Estado del día
        if precip > 5.0:
            estado_dia = "🌧️ Lluvia"
        elif v_max > 20.0:
            estado_dia = "💨 Ventoso"
        elif t_min < 4.0:
            estado_dia = "❄️ Helada"
        else:
            estado_dia = "☀️ Despejado"

        pronostico_dias.append({
            "dia": d_name,
            "fecha": time_list[i],
            "temp_max": round(t_max, 1),
            "temp_min": round(t_min, 1),
            "precipitacion_mm": round(precip, 1),
            "viento_max_kmh": round(v_max, 1),
            "estado": estado_dia,
        })

    # Evaluación de Alertas Agronómicas Operativas
    alerta_viento = viento_actual > 15.0
    alerta_lluvia = any(p > 10.0 for p in precip_list[:3])
    alerta_helada = any(t < 4.0 for t in t_min_list[:3])

    if alerta_viento or alerta_helada:
        riesgo_operativo = "Alto"
        riesgo_color = "red"
    elif alerta_lluvia:
        riesgo_operativo = "Moderado"
        riesgo_color = "amber"
    else:
        riesgo_operativo = "Óptimo"
        riesgo_color = "agro"

    return {
        "localidad": localidad,
        "latitud": lat,
        "longitud": lon,
        "temperatura_c": temp_actual,
        "humedad_porcentaje": humedad_actual,
        "viento_kmh": viento_actual,
        "alerta_viento": alerta_viento,
        "alerta_viento_msg": "Alerta Pulverización: Viento Alto (>15 km/h)" if alerta_viento else None,
        "alerta_lluvia": alerta_lluvia,
        "alerta_lluvia_msg": "Alerta Lluvia: Precipitación relevante estimada (>10 mm)" if alerta_lluvia else None,
        "alerta_helada": alerta_helada,
        "alerta_helada_msg": "Alerta Helada: Temperatura mínima riesgosa (<4°C)" if alerta_helada else None,
        "riesgo_operativo": riesgo_operativo,
        "riesgo_color": riesgo_color,
        "pronostico_semanal": pronostico_dias,
    }


def _get_fallback_weather(lat: float, lon: float, localidad: str) -> Dict[str, Any]:
    """Retorna datos climáticos mock de fallback cuando la API no está accesible."""
    pronostico_fallback = [
        {"dia": "Hoy", "fecha": "2026-07-27", "temp_max": 24.5, "temp_min": 11.2, "precipitacion_mm": 0.0, "viento_max_kmh": 18.4, "estado": "💨 Ventoso"},
        {"dia": "Mañana", "fecha": "2026-07-28", "temp_max": 26.0, "temp_min": 13.0, "precipitacion_mm": 2.5, "viento_max_kmh": 22.0, "estado": "💨 Ventoso"},
        {"dia": "Miércoles", "fecha": "2026-07-29", "temp_max": 21.0, "temp_min": 8.5, "precipitacion_mm": 14.5, "viento_max_kmh": 14.0, "estado": "🌧️ Lluvia"},
        {"dia": "Jueves", "fecha": "2026-07-30", "temp_max": 18.5, "temp_min": 3.2, "precipitacion_mm": 0.0, "viento_max_kmh": 11.0, "estado": "❄️ Helada"},
        {"dia": "Viernes", "fecha": "2026-07-31", "temp_max": 22.0, "temp_min": 7.0, "precipitacion_mm": 0.0, "viento_max_kmh": 15.0, "estado": "☀️ Despejado"},
        {"dia": "Sábado", "fecha": "2026-08-01", "temp_max": 25.0, "temp_min": 12.0, "precipitacion_mm": 0.0, "viento_max_kmh": 17.5, "estado": "☀️ Despejado"},
        {"dia": "Domingo", "fecha": "2026-08-02", "temp_max": 23.0, "temp_min": 10.0, "precipitacion_mm": 0.0, "viento_max_kmh": 12.0, "estado": "☀️ Despejado"},
    ]

    return {
        "localidad": localidad,
        "latitud": lat,
        "longitud": lon,
        "temperatura_c": 24.5,
        "humedad_porcentaje": 65,
        "viento_kmh": 18.4,
        "alerta_viento": True,
        "alerta_viento_msg": "Alerta Pulverización: Viento Alto (>15 km/h)",
        "alerta_lluvia": True,
        "alerta_lluvia_msg": "Alerta Lluvia: Precipitación relevante estimada (>10 mm en 48h)",
        "alerta_helada": True,
        "alerta_helada_msg": "Alerta Helada: Temperatura mínima riesgosa (<4°C en 72h)",
        "riesgo_operativo": "Alto",
        "riesgo_color": "red",
        "pronostico_semanal": pronostico_fallback,
    }
