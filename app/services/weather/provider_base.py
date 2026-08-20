"""
Protocolo Base y Excepciones para Proveedores Meteorológicos (EduAgro).
Maneja llamadas HTTP asíncronas con httpx.AsyncClient, reintentos con backoff y sanitización de logs.
"""

import asyncio
import logging
import random
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, List
import httpx

from app.services.weather.models import (
    NormalizedWeatherSnapshot,
    WeatherHourlyPoint,
    WeatherDailyPoint,
    WeatherAggregates,
)

logger = logging.getLogger("eduagro.weather.provider")


class WeatherProviderError(Exception):
    """Excepción tipada para errores de proveedores meteorológicos."""
    def __init__(self, message: str, status_code: Optional[int] = None, provider: str = "unknown"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.provider = provider


def sanitize_url(url: str) -> str:
    """Remueve parámetros de API Key de URLs para prevenir filtraciones en logs."""
    return re.sub(r'([?&](key|api_key|apikey)=)[^&]+', r'\1[REDACTED]', url, flags=re.IGNORECASE)


def calculate_aggregates_from_hourly(
    hourly: List[WeatherHourlyPoint],
    daily: List[WeatherDailyPoint],
) -> WeatherAggregates:
    """
    Calcula determinísticamente los agregados meteorológicos a partir de la serie horaria y diaria.
    No utiliza defaults inventados; retorna None si no hay puntos en la ventana.
    """
    if not hourly:
        return WeatherAggregates()

    h_24 = hourly[:24]
    h_48 = hourly[:48]
    h_72 = hourly[:72]

    # Precipitaciones acumuladas
    p_24 = round(sum(p.precipitation_mm for p in h_24 if p.precipitation_mm is not None), 1) if h_24 else None
    p_48 = round(sum(p.precipitation_mm for p in h_48 if p.precipitation_mm is not None), 1) if h_48 else None
    p_72 = round(sum(p.precipitation_mm for p in h_72 if p.precipitation_mm is not None), 1) if h_72 else None

    # Precipitación 7d desde diaria o horaria
    if daily:
        d_7 = daily[:7]
        p_7d = round(sum(d.precipitation_mm for d in d_7 if d.precipitation_mm is not None), 1)
    else:
        p_7d = round(sum(p.precipitation_mm for p in hourly if p.precipitation_mm is not None), 1) if hourly else None

    # Viento máximo
    v_24_vals = [p.wind_speed_kmh for p in h_24 if p.wind_speed_kmh is not None]
    v_72_vals = [p.wind_speed_kmh for p in h_72 if p.wind_speed_kmh is not None]
    v_max_24 = round(max(v_24_vals), 1) if v_24_vals else None
    v_max_72 = round(max(v_72_vals), 1) if v_72_vals else None

    # Ráfagas máximas
    g_24_vals = [p.wind_gust_kmh for p in h_24 if p.wind_gust_kmh is not None]
    g_72_vals = [p.wind_gust_kmh for p in h_72 if p.wind_gust_kmh is not None]
    g_max_24 = round(max(g_24_vals), 1) if g_24_vals else None
    g_max_72 = round(max(g_72_vals), 1) if g_72_vals else None

    # Temperaturas mín/máx a 72h
    t_72_vals = [p.temperature_c for p in h_72 if p.temperature_c is not None]
    t_min_72 = round(min(t_72_vals), 1) if t_72_vals else None
    t_max_72 = round(max(t_72_vals), 1) if t_72_vals else None

    # Humedad rel mín/máx a 72h
    rh_72_vals = [p.relative_humidity_pct for p in h_72 if p.relative_humidity_pct is not None]
    rh_min_72 = min(rh_72_vals) if rh_72_vals else None
    rh_max_72 = max(rh_72_vals) if rh_72_vals else None

    return WeatherAggregates(
        precipitation_next_24h_mm=p_24,
        precipitation_next_48h_mm=p_48,
        precipitation_next_72h_mm=p_72,
        precipitation_next_7d_mm=p_7d,
        wind_max_next_24h_kmh=v_max_24,
        wind_max_next_72h_kmh=v_max_72,
        wind_gust_max_next_24h_kmh=g_max_24,
        wind_gust_max_next_72h_kmh=g_max_72,
        temp_min_next_72h_c=t_min_72,
        temp_max_next_72h_c=t_max_72,
        relative_humidity_min_next_72h_pct=rh_min_72,
        relative_humidity_max_next_72h_pct=rh_max_72,
    )


class WeatherProvider(ABC):
    """Clase base abstracta para proveedores de clima asíncronos."""

    provider_name: str

    @abstractmethod
    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        timezone: str = "America/Argentina/Cordoba",
        requested_at: Optional[datetime] = None,
    ) -> NormalizedWeatherSnapshot:
        """Obtiene y normaliza el reporte climático de las coordenadas especificadas."""
        pass

    async def _http_get_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 2,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Ejecuta una petición GET HTTP asíncrona con reintentos acotados y backoff con jitter.
        Redacta cualquier secreto presente en logs.
        """
        safe_url = sanitize_url(url)
        last_exc: Optional[Exception] = None

        for attempt in range(1 + max_retries):
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=httpx.Timeout(timeout),
                )
                if response.status_code == 200:
                    return response.json()

                safe_reason = response.reason_phrase or "Error HTTP"
                if response.status_code in (401, 403):
                    raise WeatherProviderError(
                        f"Error de autenticación/permisos en {self.provider_name} ({response.status_code})",
                        status_code=response.status_code,
                        provider=self.provider_name,
                    )
                elif response.status_code == 429:
                    raise WeatherProviderError(
                        f"Límite de cuota (rate limit) excedido en {self.provider_name} (429)",
                        status_code=429,
                        provider=self.provider_name,
                    )

                logger.warning(
                    f"[{self.provider_name}] Respuesta HTTP no-200 ({response.status_code} {safe_reason}) "
                    f"en intento {attempt + 1}/{1 + max_retries} -> URL={safe_url}"
                )

                if attempt == max_retries:
                    raise WeatherProviderError(
                        f"Proveedor {self.provider_name} retornó HTTP status {response.status_code}",
                        status_code=response.status_code,
                        provider=self.provider_name,
                    )

            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as err:
                last_exc = err
                logger.warning(
                    f"[{self.provider_name}] Fallo de red/timeout ({err.__class__.__name__}) "
                    f"en intento {attempt + 1}/{1 + max_retries} -> URL={safe_url}"
                )
                if attempt == max_retries:
                    raise WeatherProviderError(
                        f"Timeout o error de red al consultar {self.provider_name}: {type(err).__name__}",
                        provider=self.provider_name,
                    ) from err

            # Jittered exponential backoff: 0.2s, 0.4s + random jitter
            backoff = (0.2 * (2 ** attempt)) + (random.uniform(0.05, 0.15))
            await asyncio.sleep(backoff)

        raise WeatherProviderError(f"Fallo al conectar con {self.provider_name}", provider=self.provider_name)
