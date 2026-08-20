"""
Módulo de compatibilidad agrometeorológica (EduAgro).
Enruta las consultas hacia el servicio modular app.services.clima y app.services.weather.
"""

from typing import Dict, Any, Optional
from app.services.clima import obtener_clima_para_campo, obtener_clima_para_campo_async


async def get_weather_for_location_async(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: str = "Laguna Larga, Córdoba",
) -> Dict[str, Any]:
    """
    Función asíncrona de compatibilidad para consultas agrometeorológicas geolocalizadas.
    """
    return await obtener_clima_para_campo_async(lat=lat, lon=lon, localidad=localidad)


def get_weather_for_location(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: str = "Laguna Larga, Córdoba",
) -> Dict[str, Any]:
    """
    Función sincrónica de compatibilidad para consultas agrometeorológicas geolocalizadas.
    """
    return obtener_clima_para_campo(lat=lat, lon=lon, localidad=localidad)
