"""
Capa de Adaptación y Compatibilidad Retrocompatible (EduAgro).
Mapea snapshots normalizados V2 a la estructura de diccionario heredada consumida por
templates Jinja2, endpoints existentes y el motor de decisiones.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.weather.models import NormalizedWeatherSnapshot, WeatherConsensus
from app.services.weather.weather_service import WeatherService
from app.services.weather.open_meteo_provider import deg_to_cardinal

LAT_DEFAULT = -31.7766
LON_DEFAULT = -63.8011
LOCALIDAD_DEFAULT = "Laguna Larga, Córdoba"


def snapshot_to_legacy_dict(
    snapshot: NormalizedWeatherSnapshot,
    localidad: Optional[str] = None,
    campo_nombre: Optional[str] = None,
    lote_nombre: Optional[str] = None,
    consensus: Optional[WeatherConsensus] = None,
) -> Dict[str, Any]:
    """
    Transforma un NormalizedWeatherSnapshot al diccionario heredado para Jinja2 y endpoints.
    Preserva todos los aliases históricos y maneja adecuadamente los datos en None si el estado es 'unavailable'.
    """
    loc_name = localidad or snapshot.location.location_name or LOCALIDAD_DEFAULT
    is_unavailable = snapshot.provider_status == "unavailable"

    curr = snapshot.current
    agg = snapshot.aggregates

    if is_unavailable or not curr:
        temp_c = None
        hum_pct = None
        st_c = None
        viento_kmh = None
        v_deg = 180
        v_card = "N/A"
        desc_act = "⚠️ Clima No Disponible"
        lluvia_72h = 0.0
        viento_max_72h = 0.0
        tmin_72h = None
    else:
        temp_c = curr.temperature_c
        hum_pct = curr.relative_humidity_pct
        st_c = curr.apparent_temperature_c
        viento_kmh = curr.wind_speed_kmh
        v_deg = curr.wind_direction_deg or 180
        v_card = deg_to_cardinal(v_deg)
        desc_act = curr.weather_description or "🌤️ Algo nublado"
        lluvia_72h = agg.precipitation_next_72h_mm if agg and agg.precipitation_next_72h_mm is not None else 0.0
        viento_max_72h = agg.wind_max_next_72h_kmh if agg and agg.wind_max_next_72h_kmh is not None else (viento_kmh or 0.0)
        tmin_72h = agg.temp_min_next_72h_c if agg else None

    # Evaluación de Alertas (Sólo se evalúan si hay datos disponibles)
    if is_unavailable or viento_kmh is None:
        alerta_viento = False
        alerta_lluvia = False
        alerta_helada = False
        alertas_no_evaluables = True
    else:
        alerta_viento = viento_kmh > 15.0
        alerta_lluvia = lluvia_72h >= 10.0
        alerta_helada = tmin_72h is not None and tmin_72h < 4.0
        alertas_no_evaluables = False

    alertas_list = []
    if is_unavailable:
        alertas_list.append({
            "tipo": "sistema",
            "titulo": "⚠️ Servicio Meteorológico No Disponible",
            "mensaje": "No se pudo conectar con los proveedores meteorológicos en vivo. Verifique la conexión.",
            "nivel": "alto",
        })
    else:
        if alerta_viento:
            alertas_list.append({
                "tipo": "viento",
                "titulo": "💨 Viento Alto para Pulverización (>15 km/h)",
                "mensaje": f"Viento actual de {viento_kmh} km/h ({v_card}). Riesgo de deriva de agroquímicos.",
                "nivel": "alto",
            })
        if alerta_lluvia:
            alertas_list.append({
                "tipo": "lluvia",
                "titulo": "🌧️ Alerta Lluvia Relevante (72h)",
                "mensaje": f"Se estiman {lluvia_72h} mm acumulados en 72h. Precaución con el tránsito de maquinaria.",
                "nivel": "moderado",
            })
        if alerta_helada:
            alertas_list.append({
                "tipo": "helada",
                "titulo": "❄️ Riesgo de Helada (<4°C en 72h)",
                "mensaje": f"Temperatura mínima de {tmin_72h}°C estimada. Monitorear sensibilidad de cultivos.",
                "nivel": "alto",
            })

    if is_unavailable:
        riesgo_operativo = "Indeterminado"
        riesgo_color = "gray"
    elif alerta_viento or alerta_helada:
        riesgo_operativo = "Alto"
        riesgo_color = "red"
    elif alerta_lluvia:
        riesgo_operativo = "Moderado"
        riesgo_color = "amber"
    else:
        riesgo_operativo = "Óptimo"
        riesgo_color = "agro"

    # Adaptación del pronóstico extendido a formato semanal legacy
    pronostico_semanal = []
    pronostico_extendido = []

    for dp in snapshot.daily[:14]:
        precip = dp.precipitation_mm or 0.0
        v_max = dp.wind_speed_max_kmh or 15.0
        t_min = dp.temp_min_c if dp.temp_min_c is not None else 10.0

        if precip > 5.0:
            estado_dia = "🌧️ Lluvia"
        elif v_max > 20.0:
            estado_dia = "💨 Ventoso"
        elif t_min < 4.0:
            estado_dia = "❄️ Helada"
        else:
            estado_dia = dp.weather_description or "☀️ Despejado"

        d_dict = {
            "fecha": dp.date,
            "dia": dp.day_name,
            "temp_min_c": dp.temp_min_c,
            "temp_max_c": dp.temp_max_c,
            "sensacion_min_c": dp.apparent_temp_min_c,
            "sensacion_max_c": dp.apparent_temp_max_c,
            "lluvia_mm": dp.precipitation_mm,
            "horas_precipitacion": dp.precipitation_hours,
            "viento_max_kmh": dp.wind_speed_max_kmh,
            "weather_code": dp.weather_code,
            "descripcion": dp.weather_description or estado_dia,
        }
        pronostico_extendido.append(d_dict)

        if len(pronostico_semanal) < 7:
            pronostico_semanal.append({
                "dia": dp.day_name,
                "fecha": dp.date,
                "temp_max": dp.temp_max_c,
                "temp_min": dp.temp_min_c,
                "precipitacion_mm": dp.precipitation_mm or 0.0,
                "probabilidad_precipitacion_pct": 70 if (dp.precipitation_mm or 0) > 2.0 else 10,
                "viento_max_kmh": dp.wind_speed_max_kmh or 15.0,
                "estado": estado_dia,
            })

    horas_72 = [
        {
            "hora": hp.time,
            "temp_c": hp.temperature_c,
            "precip_mm": hp.precipitation_mm,
            "viento_kmh": hp.wind_speed_kmh,
        }
        for hp in snapshot.hourly[:72]
    ]

    fuente_label = f"Google Weather API (V2)" if snapshot.provider == "google_weather" else "Open-Meteo API (V2)"

    return {
        # Bloque V2 Normalizado
        "fuente": snapshot.provider,
        "provider_status": snapshot.provider_status,
        "lat": snapshot.location.latitude,
        "lon": snapshot.location.longitude,
        "ubicacion_referencia": loc_name,
        "actual": {
            "temperatura_c": temp_c,
            "humedad_relativa_pct": hum_pct,
            "sensacion_termica_c": st_c,
            "viento_kmh": viento_kmh,
            "viento_direccion_grados": v_deg,
            "viento_direccion_cardinal": v_card,
            "weather_code": curr.weather_code if curr else None,
            "descripcion": desc_act,
        },
        "proximo_72h": {
            "lluvia_acumulada_mm": lluvia_72h,
            "viento_max_kmh": viento_max_72h,
            "horas": horas_72,
        },
        "pronostico_extendido": pronostico_extendido,
        "alerta_viento": alerta_viento,
        "alerta_lluvia": alerta_lluvia,
        "alerta_helada": alerta_helada,
        "alertas_no_evaluables": alertas_no_evaluables,
        "alertas_version": "legacy-weather-v1",
        "alertas_son_recomendaciones": False,

        # Aliases y compatibilidad retrocompatible
        "campo_nombre": campo_nombre,
        "lote_nombre": lote_nombre,
        "localidad": loc_name,
        "latitud": snapshot.location.latitude,
        "longitud": snapshot.location.longitude,
        "temperatura_c": temp_c,
        "humedad_porcentaje": hum_pct,
        "humedad_relativa_pct": hum_pct,
        "sensacion_termica_c": st_c,
        "viento_kmh": viento_kmh,
        "viento_direccion_deg": v_deg,
        "viento_direccion_cardinal": v_card,
        "alerta_viento_msg": "Alerta Pulverización: Viento Alto (>15 km/h)" if alerta_viento else None,
        "alerta_lluvia_msg": "Alerta Lluvia: Precipitación relevante estimada (>10 mm en 72h)" if alerta_lluvia else None,
        "alerta_helada_msg": "Alerta Helada: Temperatura mínima riesgosa (<4°C en 72h)" if alerta_helada else None,
        "alertas_list": alertas_list,
        "riesgo_operativo": riesgo_operativo,
        "riesgo_color": riesgo_color,
        "pronostico_semanal": pronostico_semanal,
        "fuente_oficial": fuente_label,
        "actualizado_en": snapshot.retrieved_at.strftime("%Y-%m-%d %H:%M:%S") if snapshot.retrieved_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "consensus": consensus.model_dump(mode="json") if consensus else None,
    }


async def obtener_clima_para_campo_async(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: Optional[str] = None,
    campo_nombre: Optional[str] = None,
    lote_nombre: Optional[str] = None,
    campo_id: Optional[uuid.UUID] = None,
    lote_id: Optional[uuid.UUID] = None,
    db: Optional[AsyncSession] = None,
    service: Optional[WeatherService] = None,
) -> Dict[str, Any]:
    """
    Función asíncrona principal para obtener el payload climático normalizado de un campo.
    """
    lat_val = float(lat) if lat is not None and lat != 0.0 else LAT_DEFAULT
    lon_val = float(lon) if lon is not None and lon != 0.0 else LON_DEFAULT
    loc_val = localidad.strip() if localidad else LOCALIDAD_DEFAULT

    srv = service or WeatherService()
    snapshot, consensus = await srv.get_weather(
        latitude=lat_val,
        longitude=lon_val,
        timezone="America/Argentina/Cordoba",
        campo_id=campo_id,
        lote_id=lote_id,
        db=db,
    )

    return snapshot_to_legacy_dict(
        snapshot,
        localidad=loc_val,
        campo_nombre=campo_nombre,
        lote_nombre=lote_nombre,
        consensus=consensus,
    )
