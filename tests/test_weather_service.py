"""
Suite de Pruebas Unitarias para el Servicio Meteorológico Multiproveedor (EduAgro).
Verifica los 10 casos de prueba obligatorios requeridos por la especificación.
"""

import pytest
from datetime import datetime
import respx
import httpx

from app.services.weather.models import (
    NormalizedWeatherSnapshot,
    WeatherLocation,
    WeatherCurrent,
    WeatherHourlyPoint,
    WeatherDailyPoint,
    WeatherAggregates,
)
from app.services.weather.config import WeatherSettings
from app.services.weather.open_meteo_provider import OpenMeteoProvider
from app.services.weather.google_weather_provider import GoogleWeatherProvider, adapt_google_condition_code
from app.services.weather.cache import MemoryWeatherCache
from app.services.weather.consensus import evaluate_forecast_consensus
from app.services.weather.weather_service import WeatherService
from app.services.weather.compatibility import snapshot_to_legacy_dict, obtener_clima_para_campo_async
from app.services.weather.provider_base import sanitize_url, WeatherProviderError


@pytest.mark.asyncio
async def test_1_open_meteo_normalization():
    """Caso 1: Open-Meteo normaliza correctamente actual, hourly, daily y agregados 24/48/72h."""
    provider = OpenMeteoProvider()
    raw_fixture = {
        "current": {
            "temperature_2m": 24.5,
            "relative_humidity_2m": 60,
            "apparent_temperature": 25.0,
            "precipitation": 0.0,
            "weather_code": 0,
            "wind_speed_10m": 12.0,
            "wind_gusts_10m": 18.0,
            "wind_direction_10m": 180,
        },
        "hourly": {
            "time": [f"2026-08-20T{h:02d}:00" for h in range(72)],
            "temperature_2m": [20.0 + (h % 5) for h in range(72)],
            "relative_humidity_2m": [60 for h in range(72)],
            "apparent_temperature": [20.0 + (h % 5) for h in range(72)],
            "precipitation": [0.5 if h < 24 else (1.0 if h < 48 else 0.0) for h in range(72)],
            "wind_speed_10m": [10.0 + (h % 3) for h in range(72)],
            "wind_gusts_10m": [15.0 + (h % 4) for h in range(72)],
            "wind_direction_10m": [180 for h in range(72)],
            "weather_code": [0 for h in range(72)],
        },
        "daily": {
            "time": ["2026-08-20", "2026-08-21", "2026-08-22"],
            "temperature_2m_max": [25.0, 26.0, 24.0],
            "temperature_2m_min": [12.0, 11.0, 10.0],
            "apparent_temperature_max": [25.0, 26.0, 24.0],
            "apparent_temperature_min": [12.0, 11.0, 10.0],
            "precipitation_sum": [12.0, 24.0, 0.0],
            "precipitation_hours": [4.0, 6.0, 0.0],
            "wind_speed_10m_max": [15.0, 18.0, 12.0],
            "wind_gusts_10m_max": [22.0, 25.0, 18.0],
            "weather_code": [0, 61, 0],
        },
    }

    snapshot = provider.normalize(raw_fixture, -31.7766, -63.8011, "America/Argentina/Cordoba", datetime.now())

    assert snapshot.provider == "open_meteo"
    assert snapshot.current.temperature_c == 24.5
    assert len(snapshot.hourly) == 72
    assert snapshot.aggregates.precipitation_next_24h_mm == 12.0
    assert snapshot.aggregates.precipitation_next_48h_mm == 36.0
    assert snapshot.aggregates.precipitation_next_72h_mm == 36.0
    assert snapshot.aggregates.wind_max_next_72h_kmh is not None


@pytest.mark.asyncio
async def test_2_google_weather_normalization():
    """Caso 2: Google Weather normaliza correctamente una respuesta fixture realista y sanitizada."""
    provider = GoogleWeatherProvider(api_key="AIzaSyTESTKEY")
    raw_fixture = {
        "currentConditions": {
            "temperature": {"degrees": 23.0},
            "humidity": 55,
            "feelsLike": {"degrees": 23.5},
            "weatherCondition": "CLEAR",
            "wind": {
                "speed": {"value": 14.0},
                "gust": {"value": 20.0},
                "direction": {"degrees": 180},
            },
        }
    }

    snapshot = provider.normalize(raw_fixture, -31.7766, -63.8011, "America/Argentina/Cordoba", datetime.now())

    assert snapshot.provider == "google_weather"
    assert snapshot.current.temperature_c == 23.0
    assert snapshot.current.relative_humidity_pct == 55
    assert snapshot.current.weather_description == "☀️ Despejado"


@pytest.mark.asyncio
@respx.mock
async def test_3_google_fail_fallback_to_open_meteo():
    """Caso 3: Google falla por timeout o HTTP error y Open-Meteo responde: se usa Open-Meteo."""
    respx.get(url__startswith="https://weather.googleapis.com").mock(return_value=httpx.Response(500))
    respx.get(url__startswith="https://api.open-meteo.com").mock(
        return_value=httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 22.0, "relative_humidity_2m": 50, "apparent_temperature": 22.0, "precipitation": 0.0, "weather_code": 0, "wind_speed_10m": 10.0, "wind_direction_10m": 180},
                "hourly": {"time": [], "temperature_2m": []},
                "daily": {"time": []},
            },
        )
    )

    settings = WeatherSettings(
        primary_provider="google_weather",
        secondary_provider="open_meteo",
        google_maps_weather_api_key="AIzaSyTESTKEY",
        http_max_retries=0,
    )
    cache = MemoryWeatherCache()
    service = WeatherService(settings=settings, cache=cache)

    snapshot, consensus = await service.get_weather(-31.7766, -63.8011)

    assert snapshot.provider == "open_meteo"
    assert snapshot.provider_status == "live"
    assert any("google_weather" in w for w in snapshot.data_quality.warnings)


@pytest.mark.asyncio
@respx.mock
async def test_4_cache_hit_and_stale_cache_fallback():
    """Caso 4: Revisa caché fresco y stale_cache cuando los proveedores caen."""
    cache = MemoryWeatherCache(default_ttl_seconds=1)

    # Crear snapshot simulado
    snap = NormalizedWeatherSnapshot(
        provider="google_weather",
        provider_status="live",
        retrieved_at=datetime.now(),
        location=WeatherLocation(latitude=-31.7766, longitude=-63.8011),
        current=WeatherCurrent(temperature_c=25.0, relative_humidity_pct=50, wind_speed_kmh=10.0),
    )
    await cache.set(snap)

    # 1. Hit fresco
    cached, status = await cache.get("google_weather", -31.7766, -63.8011, max_stale_minutes=60)
    assert status == "cached"
    assert cached.current.temperature_c == 25.0

    # 2. Esperar expiración del TTL (1s) para probar stale_cached
    import asyncio
    await asyncio.sleep(1.1)

    stale, status_stale = await cache.get("google_weather", -31.7766, -63.8011, max_stale_minutes=60)
    assert status_stale == "stale_cached"
    assert stale.current.temperature_c == 25.0


@pytest.mark.asyncio
@respx.mock
async def test_5_both_providers_fail_without_cache():
    """Caso 5: Ambos proveedores fallan sin caché: 'unavailable', valores None, sin datos ficticios."""
    respx.get(url__startswith="https://weather.googleapis.com").mock(return_value=httpx.Response(500))
    respx.get(url__startswith="https://api.open-meteo.com").mock(return_value=httpx.Response(500))

    settings = WeatherSettings(
        primary_provider="google_weather",
        secondary_provider="open_meteo",
        google_maps_weather_api_key="AIzaSyTESTKEY",
        http_max_retries=0,
    )
    cache = MemoryWeatherCache()
    service = WeatherService(settings=settings, cache=cache)

    snapshot, consensus = await service.get_weather(-31.7766, -63.8011)

    assert snapshot.provider_status == "unavailable"
    assert snapshot.current is None
    assert len(snapshot.hourly) == 0
    assert snapshot.data_quality.is_complete is False


@pytest.mark.asyncio
async def test_6_high_precipitation_disagreement_consensus():
    """Caso 6: Alta discrepancia de precipitación 72h: no promedia, propone modo conservative / verify_in_field."""
    snap1 = NormalizedWeatherSnapshot(
        provider="google_weather",
        provider_status="live",
        retrieved_at=datetime.now(),
        location=WeatherLocation(latitude=-31.7766, longitude=-63.8011),
        current=WeatherCurrent(temperature_c=25.0),
        aggregates=WeatherAggregates(precipitation_next_72h_mm=35.0, wind_max_next_72h_kmh=12.0),
    )
    snap2 = NormalizedWeatherSnapshot(
        provider="open_meteo",
        provider_status="live",
        retrieved_at=datetime.now(),
        location=WeatherLocation(latitude=-31.7766, longitude=-63.8011),
        current=WeatherCurrent(temperature_c=24.0),
        aggregates=WeatherAggregates(precipitation_next_72h_mm=10.0, wind_max_next_72h_kmh=12.0),
    )

    consensus = evaluate_forecast_consensus(snap1, snap2, consensus_enabled=True)

    assert consensus.disagreement.level in ("medium", "high")
    assert consensus.disagreement.recommended_decision_mode in ("conservative", "verify_in_field")
    assert consensus.disagreement.differences["precipitation_next_72h_mm"] == 25.0


@pytest.mark.asyncio
@respx.mock
async def test_7_missing_api_key_google_fails_safely():
    """Caso 7: API Key no configurada: Google queda no disponible de forma segura y se intenta Open-Meteo."""
    respx.get(url__startswith="https://api.open-meteo.com").mock(
        return_value=httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 20.0, "relative_humidity_2m": 50, "apparent_temperature": 20.0, "precipitation": 0.0, "weather_code": 0, "wind_speed_10m": 10.0, "wind_direction_10m": 180},
                "hourly": {"time": [], "temperature_2m": []},
                "daily": {"time": []},
            },
        )
    )

    settings = WeatherSettings(
        primary_provider="google_weather",
        secondary_provider="open_meteo",
        google_maps_weather_api_key=None,  # Sin API key
    )
    cache = MemoryWeatherCache()
    service = WeatherService(settings=settings, cache=cache)

    snapshot, consensus = await service.get_weather(-31.7766, -63.8011)

    assert snapshot.provider == "open_meteo"
    assert snapshot.provider_status == "live"


@pytest.mark.asyncio
async def test_8_invalid_coordinates():
    """Caso 8: Coordenadas inválidas: no se hace request HTTP y retorna status unavailable."""
    settings = WeatherSettings()
    cache = MemoryWeatherCache()
    service = WeatherService(settings=settings, cache=cache)

    snapshot, consensus = await service.get_weather(999.0, 999.0)  # Coordenadas fuera de rango

    assert snapshot.provider_status == "unavailable"
    assert any("fuera de rango" in w for w in snapshot.data_quality.warnings)


@pytest.mark.asyncio
async def test_9_legacy_payload_compatibility():
    """Caso 9: El payload legacy conserva todas las claves y campos requeridos."""
    snap = NormalizedWeatherSnapshot(
        provider="google_weather",
        provider_status="live",
        retrieved_at=datetime.now(),
        location=WeatherLocation(latitude=-31.7766, longitude=-63.8011),
        current=WeatherCurrent(
            temperature_c=22.5,
            relative_humidity_pct=65,
            apparent_temperature_c=23.0,
            precipitation_mm=0.0,
            weather_code=0,
            weather_description="☀️ Despejado",
            wind_speed_kmh=12.0,
            wind_direction_deg=180,
        ),
        aggregates=WeatherAggregates(precipitation_next_72h_mm=5.0, wind_max_next_72h_kmh=12.0),
    )

    legacy_dict = snapshot_to_legacy_dict(snap, localidad="Laguna Larga, Córdoba", campo_nombre="Estancia La Esperanza")

    required_keys = [
        "fuente", "lat", "lon", "ubicacion_referencia", "actual", "proximo_72h",
        "pronostico_extendido", "alerta_viento", "alerta_lluvia", "alerta_helada",
        "alertas_list", "riesgo_operativo", "riesgo_color", "pronostico_semanal",
        "campo_nombre", "lote_nombre", "temperatura_c", "humedad_relativa_pct", "viento_kmh"
    ]
    for key in required_keys:
        assert key in legacy_dict


@pytest.mark.asyncio
async def test_10_no_api_key_leakage():
    """Caso 10: Ningún log, payload o error serializado contiene la API key."""
    secret_key = "AIzaSySECRET_KEY_12345"
    url_with_key = f"https://weather.googleapis.com/v1/lookup?key={secret_key}&lat=-31.77"

    sanitized = sanitize_url(url_with_key)
    assert secret_key not in sanitized
    assert "[REDACTED]" in sanitized

    provider = GoogleWeatherProvider(api_key=secret_key)
    snap = provider.normalize({}, -31.7766, -63.8011, "America/Argentina/Cordoba", datetime.now())

    dumped_json = str(snap.model_dump())
    assert secret_key not in dumped_json


@pytest.mark.asyncio
async def test_11_google_weather_dict_condition():
    """Caso 11: Verifica que adapt_google_condition_code procese estructuras dict sin arrojar AttributeError."""
    code, desc = adapt_google_condition_code({"type": "PARTLY_CLOUDY", "text": "Partly Cloudy"})
    assert code == 2
    assert "Parcialmente nublado" in desc

    code_custom, desc_custom = adapt_google_condition_code({"type": "CUSTOM_STORMY_WEATHER"})
    assert code_custom == 2
    assert "Custom stormy weather" in desc_custom

