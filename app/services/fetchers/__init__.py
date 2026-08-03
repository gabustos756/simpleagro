"""
Módulo de Fetchers HTTP de Fuentes Externas de Mercado Granario (EduAgro).
Conecta con APIs públicas y oficiales de precios de granos y cotizaciones cambiarias.
"""

from app.services.fetchers.bna_fetcher import obtener_cotizacion_dolar
from app.services.fetchers.sagyp_fetcher import obtener_precios_sagyp
from app.services.fetchers.cac_fetcher import obtener_precios_pizarra_cac

__all__ = [
    "obtener_cotizacion_dolar",
    "obtener_precios_sagyp",
    "obtener_precios_pizarra_cac",
]
