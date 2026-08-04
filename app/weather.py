"""
Módulo de compatibilidad agrometeorológica (EduAgro).
Enruta las consultas hacia el servicio modular app.services.clima.
"""

from typing import Dict, Any, Optional
from app.services.clima import obtener_clima_para_campo


def get_weather_for_location(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: str = "Laguna Larga, Córdoba",
) -> Dict[str, Any]:
    """
    Función de compatibilidad para consultas agrometeorológicas geolocalizadas.
    """
    return obtener_clima_para_campo(lat=lat, lon=lon, localidad=localidad)
