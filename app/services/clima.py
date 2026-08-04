"""
Servicio Agrometeorológico de EduAgro (Productividad V2).
Procesa la información climática geolocalizada por campo/lote y evalúa alertas operativas.
"""

import logging
from typing import Dict, Any, Optional, List
from app.services.fetchers.clima_fetcher import obtener_pronostico_openmeteo, LAT_DEFAULT, LON_DEFAULT, LOCALIDAD_DEFAULT

logger = logging.getLogger("eduagro.servicios.clima")


def obtener_clima_para_campo(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: Optional[str] = None,
    campo_nombre: Optional[str] = None,
    lote_nombre: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Obtiene la estructura climática agrometeorológica normalizada y backward-compatible para un campo o lote.
    """
    # Resolución de coordenadas efectivas con fallback a Laguna Larga, Córdoba
    lat_val = float(lat) if lat is not None and lat != 0.0 else LAT_DEFAULT
    lon_val = float(lon) if lon is not None and lon != 0.0 else LON_DEFAULT
    loc_val = localidad.strip() if localidad else LOCALIDAD_DEFAULT

    raw_weather = obtener_pronostico_openmeteo(lat=lat_val, lon=lon_val, localidad=loc_val)

    actual = raw_weather.get("actual", {})
    proximo_72h = raw_weather.get("proximo_72h", {})
    pronostico_extendido = raw_weather.get("pronostico_extendido", [])

    # Umbrales Operativos Derivados
    viento_actual = actual.get("viento_kmh", 14.0)
    lluvia_72h = proximo_72h.get("lluvia_acumulada_mm", 0.0)
    tmin_72h = [d.get("temp_min_c", 10.0) for d in pronostico_extendido[:3]]

    alerta_viento = viento_actual > 15.0
    alerta_lluvia = lluvia_72h >= 10.0
    alerta_helada = any(t < 4.0 for t in tmin_72h)

    alertas_list = []
    if alerta_viento:
        alertas_list.append({
            "tipo": "viento",
            "titulo": "💨 Viento Alto para Pulverización (>15 km/h)",
            "mensaje": f"Viento actual de {viento_actual} km/h ({actual.get('viento_direccion_cardinal', 'N')}). Riesgo de deriva de agroquímicos.",
            "nivel": "alto",
        })
    if alerta_lluvia:
        alertas_list.append({
            "tipo": "lluvia",
            "titulo": "🌧️ Alerta Lluvia Relevante (48-72h)",
            "mensaje": f"Se estiman {lluvia_72h} mm acumulados en 72h. Precaución con el tránsito de maquinaria.",
            "nivel": "moderado",
        })
    if alerta_helada:
        tmin_val = min(tmin_72h) if tmin_72h else 0.0
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

    # Adaptación para la compatibilidad con templates existentes (pronostico_semanal)
    pronostico_semanal = []
    for d in pronostico_extendido[:7]:
        precip = d.get("lluvia_mm", 0.0)
        v_max = d.get("viento_max_kmh", 15.0)
        t_min = d.get("temp_min_c", 10.0)

        if precip > 5.0:
            estado_dia = "🌧️ Lluvia"
        elif v_max > 20.0:
            estado_dia = "💨 Ventoso"
        elif t_min < 4.0:
            estado_dia = "❄️ Helada"
        else:
            estado_dia = d.get("descripcion", "☀️ Despejado")

        pronostico_semanal.append({
            "dia": d.get("dia"),
            "fecha": d.get("fecha"),
            "temp_max": d.get("temp_max_c"),
            "temp_min": d.get("temp_min_c"),
            "precipitacion_mm": precip,
            "probabilidad_precipitacion_pct": 70 if precip > 2.0 else 10,
            "viento_max_kmh": v_max,
            "estado": estado_dia,
        })

    return {
        # Estructura Normalizada V2
        "fuente": raw_weather.get("fuente", "open-meteo"),
        "lat": lat_val,
        "lon": lon_val,
        "ubicacion_referencia": loc_val,
        "actual": actual,
        "proximo_72h": proximo_72h,
        "pronostico_extendido": pronostico_extendido,
        "alerta_viento": alerta_viento,
        "alerta_lluvia": alerta_lluvia,
        "alerta_helada": alerta_helada,

        # Aliases y compatibilidad backward-compatible
        "campo_nombre": campo_nombre,
        "lote_nombre": lote_nombre,
        "localidad": loc_val,
        "latitud": lat_val,
        "longitud": lon_val,
        "temperatura_c": actual.get("temperatura_c", 22.5),
        "humedad_porcentaje": actual.get("humedad_relativa_pct", 65),
        "humedad_relativa_pct": actual.get("humedad_relativa_pct", 65),
        "sensacion_termica_c": actual.get("sensacion_termica_c", 23.0),
        "viento_kmh": viento_actual,
        "viento_direccion_deg": actual.get("viento_direccion_grados", 180),
        "viento_direccion_cardinal": actual.get("viento_direccion_cardinal", "S"),
        "alerta_viento_msg": "Alerta Pulverización: Viento Alto (>15 km/h)" if alerta_viento else None,
        "alerta_lluvia_msg": "Alerta Lluvia: Precipitación relevante estimada (>10 mm en 48h)" if alerta_lluvia else None,
        "alerta_helada_msg": "Alerta Helada: Temperatura mínima riesgosa (<4°C en 72h)" if alerta_helada else None,
        "alertas_list": alertas_list,
        "riesgo_operativo": riesgo_operativo,
        "riesgo_color": riesgo_color,
        "pronostico_semanal": pronostico_semanal,
        "fuente_oficial": raw_weather.get("fuente_oficial", "Open-Meteo / SMN Argentina"),
        "actualizado_en": raw_weather.get("actualizado_en"),
    }
