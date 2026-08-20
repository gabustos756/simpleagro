"""
Fetcher HTTP Agrometeorológico para Argentina (Open-Meteo).
Conecta con la API geolocalizada oficial de Open-Meteo.
Mantiene funciones helper y compatibilidad asíncrona/sincrónica.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.services.weather.open_meteo_provider import (
    OpenMeteoProvider,
    deg_to_cardinal,
    decode_wmo_code,
)
from app.services.weather.compatibility import snapshot_to_legacy_dict

logger = logging.getLogger("eduagro.fetchers.clima")

LAT_DEFAULT = -31.7766
LON_DEFAULT = -63.8011
LOCALIDAD_DEFAULT = "Laguna Larga, Córdoba"


async def obtener_pronostico_openmeteo_async(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: Optional[str] = None,
    timeout_sec: float = 5.0,
) -> Dict[str, Any]:
    """
    Obtiene el reporte climático asíncrono desde OpenMeteoProvider y retorna el diccionario de compatibilidad.
    """
    lat_val = float(lat) if lat is not None and lat != 0.0 else LAT_DEFAULT
    lon_val = float(lon) if lon is not None and lon != 0.0 else LON_DEFAULT
    loc_val = localidad.strip() if localidad else LOCALIDAD_DEFAULT

    provider = OpenMeteoProvider(timeout=timeout_sec)
    snapshot = await provider.fetch(
        latitude=lat_val,
        longitude=lon_val,
        timezone="America/Argentina/Cordoba",
    )
    return snapshot_to_legacy_dict(snapshot, localidad=loc_val)


def obtener_pronostico_openmeteo(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: Optional[str] = None,
    timeout_sec: float = 5.0,
) -> Dict[str, Any]:
    """
    Wrapper sincrónico de compatibilidad para llamadas heredadas.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    coro = obtener_pronostico_openmeteo_async(lat=lat, lon=lon, localidad=localidad, timeout_sec=timeout_sec)

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
