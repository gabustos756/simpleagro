"""
Orquestador Principal del Servicio Meteorológico Asíncrono (EduAgro).
Coordina caché, proveedores primarios y secundarios, consenso, fallbacks resilientes y persistencia en DB.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import uuid
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.weather.config import WeatherSettings, get_weather_settings
from app.services.weather.models import (
    NormalizedWeatherSnapshot,
    WeatherLocation,
    WeatherDataQuality,
    WeatherConsensus,
    ForecastDisagreement,
)
from app.services.weather.provider_base import WeatherProvider, WeatherProviderError
from app.services.weather.open_meteo_provider import OpenMeteoProvider
from app.services.weather.google_weather_provider import GoogleWeatherProvider
from app.services.weather.cache import WeatherCache, MemoryWeatherCache
from app.services.weather.consensus import evaluate_forecast_consensus

logger = logging.getLogger("eduagro.weather.service")

# Instancias singleton globales de caché y cliente HTTP con connection pool
_GLOBAL_WEATHER_CACHE = MemoryWeatherCache(default_ttl_seconds=900)
_GLOBAL_HTTP_CLIENT = httpx.AsyncClient(
    timeout=httpx.Timeout(5.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
)


class WeatherService:
    def __init__(
        self,
        settings: Optional[WeatherSettings] = None,
        cache: Optional[WeatherCache] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.settings = settings or get_weather_settings()
        self.cache = cache or _GLOBAL_WEATHER_CACHE
        self._shared_client = http_client or _GLOBAL_HTTP_CLIENT

        # Inicialización de proveedores
        self.providers: Dict[str, WeatherProvider] = {
            "google_weather": GoogleWeatherProvider(
                api_key=self.settings.google_maps_weather_api_key,
                http_client=self._shared_client,
                timeout=self.settings.http_timeout_seconds,
                max_retries=self.settings.http_max_retries,
            ),
            "open_meteo": OpenMeteoProvider(
                http_client=self._shared_client,
                timeout=self.settings.http_timeout_seconds,
                max_retries=self.settings.http_max_retries,
            ),
        }

    async def get_weather(
        self,
        latitude: float,
        longitude: float,
        timezone: str = "America/Argentina/Cordoba",
        campo_id: Optional[uuid.UUID] = None,
        lote_id: Optional[uuid.UUID] = None,
        db: Optional[AsyncSession] = None,
    ) -> Tuple[NormalizedWeatherSnapshot, WeatherConsensus]:
        """
        Obtiene el reporte climático normalizado con soporte para failover, caché y consenso.
        """
        now = datetime.now()

        # 1. Validar Coordenadas
        if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            logger.warning(f"[WEATHER SERVICE] Coordenadas inválidas: lat={latitude}, lon={longitude}")
            unavail_snap = self._create_unavailable_snapshot(
                latitude, longitude, timezone, now,
                warnings=[f"Coordenadas fuera de rango: lat={latitude}, lon={longitude}"]
            )
            return unavail_snap, WeatherConsensus(enabled=False)

        primary_name = self.settings.primary_provider
        secondary_name = self.settings.secondary_provider

        # 2. Verificar Caché en Memoria
        cached_snap, cache_status = await self.cache.get(
            provider=primary_name,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            max_stale_minutes=self.settings.stale_cache_max_age_minutes,
        )

        if cached_snap and cache_status == "cached":
            logger.info(f"[WEATHER SERVICE] HIT Caché fresco ({primary_name}) lat={latitude}, lon={longitude}")
            consensus = WeatherConsensus(enabled=False, primary_provider=primary_name)
            return cached_snap, consensus

        # 3. Intentar Proveedor Primario
        primary_snap: Optional[NormalizedWeatherSnapshot] = None
        secondary_snap: Optional[NormalizedWeatherSnapshot] = None
        service_warnings: list[str] = []

        primary_provider = self.providers.get(primary_name)
        if primary_provider:
            try:
                logger.info(f"[WEATHER SERVICE] Consultando proveedor primario: {primary_name}")
                primary_snap = await primary_provider.fetch(
                    latitude=latitude,
                    longitude=longitude,
                    timezone=timezone,
                    requested_at=now,
                )
            except Exception as e:
                warn_msg = f"Proveedor primario '{primary_name}' no disponible: {str(e)}"
                logger.warning(f"[WEATHER SERVICE] {warn_msg}")
                service_warnings.append(warn_msg)

        # 4. Fallback al Proveedor Secundario si el primario falló o para Consenso
        secondary_provider = self.providers.get(secondary_name)
        if not primary_snap and secondary_provider:
            try:
                logger.info(f"[WEATHER SERVICE] FAILOVER -> Consultando secundario: {secondary_name}")
                secondary_snap = await secondary_provider.fetch(
                    latitude=latitude,
                    longitude=longitude,
                    timezone=timezone,
                    requested_at=now,
                )
                if secondary_snap:
                    secondary_snap.data_quality.warnings.extend(service_warnings)
            except Exception as e:
                warn_msg = f"Proveedor secundario '{secondary_name}' no disponible: {str(e)}"
                logger.warning(f"[WEATHER SERVICE] {warn_msg}")
                service_warnings.append(warn_msg)

        # 5. Si está activado el consenso y ambos proveedores están disponibles, consultar el secundario también
        if primary_snap and self.settings.consensus_enabled and secondary_provider and secondary_name != primary_name:
            try:
                secondary_snap = await secondary_provider.fetch(
                    latitude=latitude,
                    longitude=longitude,
                    timezone=timezone,
                    requested_at=now,
                )
            except Exception as e:
                logger.debug(f"[WEATHER SERVICE] Consenso secundario omitido ({secondary_name}): {e}")

        # 6. Seleccionar Snapshot Principal o fallback a Stale Cache
        final_snapshot: Optional[NormalizedWeatherSnapshot] = primary_snap or secondary_snap

        if final_snapshot:
            # Guardar en Caché
            await self.cache.set(final_snapshot, ttl_seconds=self.settings.cache_ttl_seconds)

            # Persistencia en Base de Datos PostgreSQL si está habilitada
            if db and self.settings.enable_persistence:
                await self._persist_snapshot(db, final_snapshot, campo_id=campo_id, lote_id=lote_id)

            consensus = evaluate_forecast_consensus(
                primary_snap or final_snapshot,
                secondary_snap,
                consensus_enabled=self.settings.consensus_enabled,
            )
            return final_snapshot, consensus

        # 7. Si ambos proveedores fallaron, intentar Stale Cache
        if cached_snap and cache_status == "stale_cached":
            logger.warning(f"[WEATHER SERVICE] Proveedores caídos. Retornando STALE CACHE ({primary_name})")
            cached_snap.data_quality.warnings.extend(service_warnings)
            cached_snap.data_quality.warnings.append("Datos obtenidos de caché vencido por falla de proveedores en vivo.")
            consensus = WeatherConsensus(enabled=False, primary_provider=primary_name)
            return cached_snap, consensus

        # 8. Sin proveedores ni caché -> UNAVAILABLE (Sin datos ficticios)
        logger.error(f"[WEATHER SERVICE] Todos los proveedores fallaron y no hay caché disponible para lat={latitude}, lon={longitude}")
        unavail_snap = self._create_unavailable_snapshot(
            latitude, longitude, timezone, now, warnings=service_warnings
        )
        return unavail_snap, WeatherConsensus(enabled=False)

    def _create_unavailable_snapshot(
        self,
        latitude: float,
        longitude: float,
        timezone: str,
        requested_at: datetime,
        warnings: list[str],
    ) -> NormalizedWeatherSnapshot:
        """Crea un snapshot normalizado con estado 'unavailable' (Campos en None, sin datos ficticios)."""
        return NormalizedWeatherSnapshot(
            provider=self.settings.primary_provider,
            provider_status="unavailable",
            retrieved_at=requested_at,
            observed_at=None,
            forecast_generated_at=None,
            location=WeatherLocation(
                latitude=latitude,
                longitude=longitude,
                timezone=timezone,
            ),
            current=None,
            hourly=[],
            daily=[],
            aggregates=None,
            data_quality=WeatherDataQuality(
                missing_fields=["current", "hourly", "daily", "aggregates"],
                warnings=warnings,
                is_complete=False,
            ),
            raw_payload_reference=None,
            schema_version="v2.0",
        )

    async def _persist_snapshot(
        self,
        db: AsyncSession,
        snapshot: NormalizedWeatherSnapshot,
        campo_id: Optional[uuid.UUID] = None,
        lote_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Guarda asíncronamente el snapshot en la tabla weather_snapshots de PostgreSQL."""
        try:
            from app.models import WeatherSnapshot

            db_obj = WeatherSnapshot(
                id=uuid.uuid4(),
                campo_id=campo_id,
                lote_id=lote_id,
                provider=snapshot.provider,
                provider_status=snapshot.provider_status,
                latitude=snapshot.location.latitude,
                longitude=snapshot.location.longitude,
                timezone=snapshot.location.timezone,
                observed_at=snapshot.observed_at,
                forecast_generated_at=snapshot.forecast_generated_at,
                retrieved_at=snapshot.retrieved_at,
                schema_version=snapshot.schema_version,
                normalized_payload=snapshot.model_dump(mode="json"),
                data_quality=snapshot.data_quality.model_dump(mode="json"),
            )
            db.add(db_obj)
            await db.commit()
            logger.debug(f"[WEATHER SERVICE] Snapshot guardado en BD id={db_obj.id}")
        except Exception as e:
            logger.error(f"[WEATHER SERVICE] Error al persistir snapshot en BD: {e}")
            await db.rollback()
