"""
Módulo de Caché Meteorológico (EduAgro).
Soporta caché asíncrono en memoria con TTL y estado vencido reutilizable (stale_cached).
Diseñado para migrar fácilmente a Redis sin cambiar los servicios consumidores.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, Any
import logging

from app.services.weather.models import NormalizedWeatherSnapshot

logger = logging.getLogger("eduagro.weather.cache")


class WeatherCache:
    """Protocolo / Base abstracta para caché meteorológico."""

    async def get(
        self,
        provider: str,
        latitude: float,
        longitude: float,
        timezone: str = "America/Argentina/Cordoba",
        max_stale_minutes: int = 60,
    ) -> Tuple[Optional[NormalizedWeatherSnapshot], Optional[str]]:
        """
        Retorna (snapshot, status) si existe en caché.
        status puede ser 'cached' o 'stale_cached'. Si no existe o venció el máximo stale, retorna (None, None).
        """
        raise NotImplementedError

    async def set(
        self,
        snapshot: NormalizedWeatherSnapshot,
        ttl_seconds: int = 900,
    ) -> None:
        """Guarda un snapshot en caché con un tiempo de vida (TTL)."""
        raise NotImplementedError


class MemoryWeatherCache(WeatherCache):
    """Implementación de caché meteorológico en memoria asíncrono thread-safe."""

    def __init__(self, default_ttl_seconds: int = 900):
        self.default_ttl_seconds = default_ttl_seconds
        self._store: Dict[str, Tuple[NormalizedWeatherSnapshot, datetime]] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, provider: str, latitude: float, longitude: float, timezone: str) -> str:
        return f"weather:{provider}:{round(latitude, 4)}:{round(longitude, 4)}:{timezone.lower()}"

    async def get(
        self,
        provider: str,
        latitude: float,
        longitude: float,
        timezone: str = "America/Argentina/Cordoba",
        max_stale_minutes: int = 60,
    ) -> Tuple[Optional[NormalizedWeatherSnapshot], Optional[str]]:
        key = self._make_key(provider, latitude, longitude, timezone)
        now = datetime.now()

        async with self._lock:
            if key not in self._store:
                return (None, None)

            snapshot, cached_at = self._store[key]
            age_seconds = (now - cached_at).total_seconds()

            if age_seconds <= self.default_ttl_seconds:
                # Caché fresco y vigente
                cloned = snapshot.model_copy(deep=True)
                cloned.provider_status = "cached"
                return (cloned, "cached")
            elif age_seconds <= (max_stale_minutes * 60):
                # Caché vencido pero reutilizable si falla el proveedor
                cloned = snapshot.model_copy(deep=True)
                cloned.provider_status = "stale_cached"
                return (cloned, "stale_cached")
            else:
                # Vencido completamente
                del self._store[key]
                return (None, None)

    async def set(
        self,
        snapshot: NormalizedWeatherSnapshot,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        if not snapshot or snapshot.provider_status == "unavailable":
            return  # No se cachean errores ni datos no disponibles

        key = self._make_key(
            snapshot.provider,
            snapshot.location.latitude,
            snapshot.location.longitude,
            snapshot.location.timezone,
        )
        now = datetime.now()

        async with self._lock:
            self._store[key] = (snapshot, now)
            logger.debug(f"[MEMORY CACHE] Snapshot guardado key={key} TTL={ttl_seconds or self.default_ttl_seconds}s")
