"""
Servicio Agrometeorológico de EduAgro (FASE CLIMA 1.0).
Procesa la información climática geolocalizada por campo/lote y evalúa alertas agrometeorológicas operativas.
"""

import logging
from typing import Dict, Any, Optional, List
from app.services.fetchers.clima_fetcher import obtener_pronostico_openmeteo

logger = logging.getLogger("eduagro.servicios.clima")


def obtener_clima_para_campo(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: str = "Laguna Larga, Córdoba",
    campo_nombre: Optional[str] = None,
    lote_nombre: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Obtiene el reporte agrometeorológico geolocalizado a 7 días por campo o lote,
    evaluando alertas operativas de pulverización (viento), lluvias (48h) y heladas (72h).
    """
    lat_val = lat if lat is not None else -31.4201
    lon_val = lon if lon is not None else -64.1888

    raw_weather = obtener_pronostico_openmeteo(lat=lat_val, lon=lon_val, localidad=localidad)

    viento_actual = raw_weather.get("viento_kmh", 18.4)
    pronostico = raw_weather.get("pronostico_semanal", [])

    precip_3d = [d.get("precipitacion_mm", 0.0) for d in pronostico[:3]]
    tmin_3d = [d.get("temp_min", 10.0) for d in pronostico[:3]]

    alerta_viento = viento_actual > 15.0
    alerta_lluvia = any(p > 10.0 for p in precip_3d)
    alerta_helada = any(t < 4.0 for t in tmin_3d)

    alertas_list = []
    if alerta_viento:
        alertas_list.append({
            "tipo": "viento",
            "titulo": "💨 Viento Alto para Pulverización (>15 km/h)",
            "mensaje": f"Viento actual de {viento_actual} km/h. Riesgo de deriva de agroquímicos.",
            "nivel": "alto",
        })
    if alerta_lluvia:
        lluvia_max = max(precip_3d) if precip_3d else 0.0
        alertas_list.append({
            "tipo": "lluvia",
            "titulo": "🌧️ Alerta Lluvia Relevante (48-72h)",
            "mensaje": f"Se prevén precipitaciones de hasta {lluvia_max} mm. Afectará tránsito de maquinaria.",
            "nivel": "moderado",
        })
    if alerta_helada:
        tmin_val = min(tmin_3d) if tmin_3d else 0.0
        alertas_list.append({
            "tipo": "helada",
            "titulo": "❄️ Riesgo de Helada (<4°C en 72h)",
            "mensaje": f"Temperatura mínima de {tmin_val}°C estimada. Monitorear sensibilidad de cultivos.",
            "nivel": "alto",
        })

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
        "campo_nombre": campo_nombre,
        "lote_nombre": lote_nombre,
        "localidad": raw_weather.get("localidad", localidad),
        "latitud": lat_val,
        "longitud": lon_val,
        "temperatura_c": raw_weather.get("temperatura_c", 22.5),
        "humedad_porcentaje": raw_weather.get("humedad_porcentaje", 65),
        "viento_kmh": viento_actual,
        "viento_direccion_deg": raw_weather.get("viento_direccion_deg", 180),
        "alerta_viento": alerta_viento,
        "alerta_viento_msg": "Alerta Pulverización: Viento Alto (>15 km/h)" if alerta_viento else None,
        "alerta_lluvia": alerta_lluvia,
        "alerta_lluvia_msg": "Alerta Lluvia: Precipitación relevante estimada (>10 mm en 48h)" if alerta_lluvia else None,
        "alerta_helada": alerta_helada,
        "alerta_helada_msg": "Alerta Helada: Temperatura mínima riesgosa (<4°C en 72h)" if alerta_helada else None,
        "alertas_list": alertas_list,
        "riesgo_operativo": riesgo_operativo,
        "riesgo_color": riesgo_color,
        "pronostico_semanal": pronostico,
        "fuente_oficial": raw_weather.get("fuente_oficial", "Open-Meteo / SMN Argentina (Coordenadas Oficiales)"),
        "actualizado_en": raw_weather.get("actualizado_en"),
    }
