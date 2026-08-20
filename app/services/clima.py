"""
Servicio Agrometeorológico de EduAgro (Productividad V2 / V3 Multiproveedor).
Procesa la información climática geolocalizada por campo/lote y evalúa alertas operativas.
Fachada retrocompatible conectada al motor multiproveedor app.services.weather.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.weather import obtener_clima_para_campo_async

logger = logging.getLogger("eduagro.servicios.clima")

LAT_DEFAULT = -31.7766
LON_DEFAULT = -63.8011
LOCALIDAD_DEFAULT = "Laguna Larga, Córdoba"


def obtener_clima_para_campo(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    localidad: Optional[str] = None,
    campo_nombre: Optional[str] = None,
    lote_nombre: Optional[str] = None,
    campo_id: Optional[uuid.UUID] = None,
    lote_id: Optional[uuid.UUID] = None,
    db: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """
    Versión sincrónica de compatibilidad para código heredado.
    Ejecuta de forma segura la función asíncrona principal.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    coro = obtener_clima_para_campo_async(
        lat=lat,
        lon=lon,
        localidad=localidad,
        campo_nombre=campo_nombre,
        lote_nombre=lote_nombre,
        campo_id=campo_id,
        lote_id=lote_id,
        db=db,
    )

    if loop and loop.is_running():
        # Si ya hay un event loop en ejecución (ej: llamado desde una función sync en contexto async)
        # Usar un runner secundario o resolver la corrutina
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
