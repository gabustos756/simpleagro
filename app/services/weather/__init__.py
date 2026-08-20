"""
Paquete del Servicio Meteorológico Multiproveedor (EduAgro).
Exporta el orquestador asíncrono, modelos normalizados y funciones compatibles.
"""

from app.services.weather.config import WeatherSettings, get_weather_settings
from app.services.weather.models import (
    NormalizedWeatherSnapshot,
    WeatherLocation,
    WeatherCurrent,
    WeatherHourlyPoint,
    WeatherDailyPoint,
    WeatherAggregates,
    WeatherDataQuality,
    ForecastDisagreement,
    WeatherConsensus,
)
from app.services.weather.weather_service import WeatherService
from app.services.weather.compatibility import (
    snapshot_to_legacy_dict,
    obtener_clima_para_campo_async,
)

__all__ = [
    "WeatherService",
    "WeatherSettings",
    "get_weather_settings",
    "NormalizedWeatherSnapshot",
    "WeatherLocation",
    "WeatherCurrent",
    "WeatherHourlyPoint",
    "WeatherDailyPoint",
    "WeatherAggregates",
    "WeatherDataQuality",
    "ForecastDisagreement",
    "WeatherConsensus",
    "snapshot_to_legacy_dict",
    "obtener_clima_para_campo_async",
]
