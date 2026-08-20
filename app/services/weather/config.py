"""
Módulo de Configuración del Servicio Meteorológico Multiproveedor (EduAgro).
Lee variables de entorno con fallbacks seguros y detecta claves de Google Maps / Weather.
"""

import os
from dataclasses import dataclass
from typing import Optional, Literal

WeatherProviderType = Literal["google_weather", "open_meteo"]


@dataclass
class WeatherSettings:
    primary_provider: WeatherProviderType = "google_weather"
    secondary_provider: WeatherProviderType = "open_meteo"
    google_maps_weather_api_key: Optional[str] = None
    http_timeout_seconds: float = 5.0
    http_max_retries: int = 2
    cache_ttl_seconds: int = 900  # 15 minutos
    stale_cache_max_age_minutes: int = 60  # 1 hora
    enable_persistence: bool = True
    consensus_enabled: bool = True
    conservative_on_disagreement: bool = True


def get_weather_settings() -> WeatherSettings:
    """
    Construye las configuraciones meteorológicas vigentes a partir del entorno.
    Reutiliza GOOGLE_MAPS_WEATHER_API_KEY o GOOGLE_API_KEY sin exponer claves en código público.
    """
    google_key = os.environ.get("GOOGLE_MAPS_WEATHER_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if google_key:
        google_key = google_key.strip()

    primary_prov = os.environ.get("WEATHER_PRIMARY_PROVIDER", "google_weather").strip().lower()
    if primary_prov not in ("google_weather", "open_meteo"):
        primary_prov = "google_weather"

    secondary_prov = os.environ.get("WEATHER_SECONDARY_PROVIDER", "open_meteo").strip().lower()
    if secondary_prov not in ("google_weather", "open_meteo"):
        secondary_prov = "open_meteo"

    def _to_bool(val: Optional[str], default: bool) -> bool:
        if val is None:
            return default
        return val.strip().lower() in ("true", "1", "yes", "on")

    return WeatherSettings(
        primary_provider=primary_prov,  # type: ignore
        secondary_provider=secondary_prov,  # type: ignore
        google_maps_weather_api_key=google_key,
        http_timeout_seconds=float(os.environ.get("WEATHER_HTTP_TIMEOUT_SECONDS", "5.0")),
        http_max_retries=int(os.environ.get("WEATHER_HTTP_MAX_RETRIES", "2")),
        cache_ttl_seconds=int(os.environ.get("WEATHER_CACHE_TTL_SECONDS", "900")),
        stale_cache_max_age_minutes=int(os.environ.get("WEATHER_STALE_CACHE_MAX_AGE_MINUTES", "60")),
        enable_persistence=_to_bool(os.environ.get("WEATHER_ENABLE_PERSISTENCE"), True),
        consensus_enabled=_to_bool(os.environ.get("WEATHER_CONSENSUS_ENABLED"), False),
        conservative_on_disagreement=_to_bool(os.environ.get("WEATHER_CONSERVATIVE_ON_DISAGREEMENT"), True),
    )
