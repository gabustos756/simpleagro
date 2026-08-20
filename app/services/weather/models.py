"""
Modelos de Datos Normalizados y Tipados para el Servicio Meteorológico (EduAgro).
Implementado con Pydantic v2.
"""

from datetime import datetime
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field

WeatherProviderName = Literal["google_weather", "open_meteo"]
WeatherDataStatus = Literal[
    "live",
    "cached",
    "stale_cached",
    "partial",
    "unavailable"
]


class WeatherLocation(BaseModel):
    latitude: float
    longitude: float
    timezone: str = "America/Argentina/Cordoba"
    location_name: Optional[str] = None


class WeatherCurrent(BaseModel):
    temperature_c: Optional[float] = None
    relative_humidity_pct: Optional[int] = None
    apparent_temperature_c: Optional[float] = None
    precipitation_mm: Optional[float] = None
    weather_code: Optional[int] = None
    weather_description: Optional[str] = None
    wind_speed_kmh: Optional[float] = None
    wind_gust_kmh: Optional[float] = None
    wind_direction_deg: Optional[int] = None


class WeatherHourlyPoint(BaseModel):
    time: str
    temperature_c: Optional[float] = None
    relative_humidity_pct: Optional[int] = None
    apparent_temperature_c: Optional[float] = None
    precipitation_mm: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_gust_kmh: Optional[float] = None
    wind_direction_deg: Optional[int] = None
    weather_code: Optional[int] = None
    weather_description: Optional[str] = None


class WeatherDailyPoint(BaseModel):
    date: str
    day_name: str
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    apparent_temp_min_c: Optional[float] = None
    apparent_temp_max_c: Optional[float] = None
    precipitation_mm: Optional[float] = None
    precipitation_hours: Optional[float] = None
    wind_speed_max_kmh: Optional[float] = None
    wind_gust_max_kmh: Optional[float] = None
    weather_code: Optional[int] = None
    weather_description: Optional[str] = None


class WeatherAggregates(BaseModel):
    precipitation_next_24h_mm: Optional[float] = None
    precipitation_next_48h_mm: Optional[float] = None
    precipitation_next_72h_mm: Optional[float] = None
    precipitation_next_7d_mm: Optional[float] = None
    wind_max_next_24h_kmh: Optional[float] = None
    wind_max_next_72h_kmh: Optional[float] = None
    wind_gust_max_next_24h_kmh: Optional[float] = None
    wind_gust_max_next_72h_kmh: Optional[float] = None
    temp_min_next_72h_c: Optional[float] = None
    temp_max_next_72h_c: Optional[float] = None
    relative_humidity_min_next_72h_pct: Optional[int] = None
    relative_humidity_max_next_72h_pct: Optional[int] = None


class WeatherDataQuality(BaseModel):
    missing_fields: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    is_complete: bool = True


class NormalizedWeatherSnapshot(BaseModel):
    provider: WeatherProviderName
    provider_status: WeatherDataStatus
    retrieved_at: datetime
    observed_at: Optional[datetime] = None
    forecast_generated_at: Optional[datetime] = None
    location: WeatherLocation
    current: Optional[WeatherCurrent] = None
    hourly: List[WeatherHourlyPoint] = Field(default_factory=list)
    daily: List[WeatherDailyPoint] = Field(default_factory=list)
    aggregates: Optional[WeatherAggregates] = None
    data_quality: WeatherDataQuality = Field(default_factory=WeatherDataQuality)
    raw_payload_reference: Optional[str] = None  # Nunca contiene API keys ni secretos
    schema_version: str = "v2.0"


class ForecastDisagreement(BaseModel):
    level: Literal["low", "medium", "high", "not_evaluated"] = "not_evaluated"
    differences: Dict[str, float] = Field(default_factory=dict)
    recommended_decision_mode: Literal["primary", "conservative", "verify_in_field"] = "primary"
    reason_codes: List[str] = Field(default_factory=list)


class WeatherConsensus(BaseModel):
    enabled: bool = True
    primary_provider: str = "google_weather"
    secondary_provider: Optional[str] = "open_meteo"
    disagreement: ForecastDisagreement = Field(default_factory=ForecastDisagreement)
