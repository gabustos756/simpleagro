"""
Constructor de Contexto Determinístico (EduAgro).
Normaliza entradas desde diccionarios legacy, objetos SQLAlchemy o snapshots meteorológicos en DecisionContext.
"""

from typing import Dict, Any, Optional, Union
from uuid import UUID

from app.services.decision_engine.models import (
    DecisionContext,
    MarketData,
    HarvestData,
    LogisticsData,
    SprayingData,
    WeatherData,
)


def build_decision_context_from_dict(raw: Dict[str, Any]) -> DecisionContext:
    """
    Construye DecisionContext desde un diccionario arbitrario o legacy.
    Preserva None sin convertir a 0.0.
    """
    cultivo_raw = raw.get("cultivo")
    cultivo_norm = str(cultivo_raw).lower() if cultivo_raw else None
    if cultivo_norm not in ("maiz", "soja", "sorgo", "trigo"):
        cultivo_norm = None

    market = MarketData(
        precio_spot_usd=raw.get("precio_fisico_usd") if raw.get("precio_fisico_usd") is not None else raw.get("precio_spot_usd"),
        precio_futuro_usd=raw.get("precio_futuro_usd"),
        spread_usd=raw.get("spread_futuro_usd") if raw.get("spread_futuro_usd") is not None else raw.get("spread_usd"),
        costo_flete_usd_tn=raw.get("costo_flete_usd_tn"),
        costo_almacenaje_mes_usd_tn=raw.get("costo_almacenaje_mes_usd_tn"),
        tasa_interes_mensual_pct=raw.get("tasa_interes_mensual_pct"),
    )

    harvest = HarvestData(
        humedad_grano_pct=raw.get("humedad_grano_pct"),
        costo_secada_punto_usd=raw.get("costo_secada_punto_usd"),
        rendimiento_estimado_tn_ha=raw.get("rendimiento_estimado_tn_ha"),
    )

    logistics = LogisticsData(
        estado_caminos=raw.get("estado_caminos", "desconocido"),
    )

    spraying = SprayingData(
        viento_actual_kmh=raw.get("viento_max_kmh") if raw.get("viento_max_kmh") is not None else raw.get("viento_kmh"),
        temperatura_c=raw.get("temperatura_c"),
        humedad_relativa_pct=raw.get("humedad_relativa_pct"),
    )

    # Procesar Clima
    weather_input = raw.get("weather") or {}
    if isinstance(weather_input, dict):
        pron_sem = weather_input.get("pronostico_semanal", [])
        p72 = None
        if len(pron_sem) >= 3:
            p72 = sum((d.get("precipitacion_mm") or 0.0) for d in pron_sem[:3])
        elif raw.get("lluvia_esperada_mm") is not None:
            p72 = float(raw["lluvia_esperada_mm"])

        weather = WeatherData(
            provider=weather_input.get("fuente") or raw.get("fuente"),
            provider_status="live" if weather_input or raw.get("lluvia_esperada_mm") is not None else "unavailable",
            precipitation_next_72h_mm=p72,
            wind_max_next_24h_kmh=raw.get("viento_max_kmh") or weather_input.get("viento_kmh"),
            temp_min_next_72h_c=raw.get("temp_min_c"),
        )
    else:
        weather = WeatherData(provider_status="unavailable")

    return DecisionContext(
        request_id=raw.get("request_id"),
        organization_id=raw.get("organization_id"),
        family_client_id=raw.get("family_client_id"),
        campo_id=raw.get("campo_id"),
        lote_id=raw.get("lote_id"),
        cultivo=cultivo_norm,  # type: ignore
        campo_nombre=raw.get("campo_nombre"),
        lote_nombre=raw.get("lote_nombre"),
        market=market,
        harvest=harvest,
        logistics=logistics,
        spraying=spraying,
        weather=weather,
        metadata=raw.get("metadata", {}),
    )


def build_demo_decision_context() -> DecisionContext:
    """
    Factory explicito para pruebas unitarias y demostraciones sin valores inventados como mediciones reales.
    """
    return DecisionContext(
        cultivo="maiz",
        campo_nombre="Estancia La Esperanza",
        lote_nombre="Lote 1",
        market=MarketData(
            precio_spot_usd=188.0,
            precio_futuro_usd=195.0,
            spread_usd=7.0,
        ),
        harvest=HarvestData(
            humedad_grano_pct=17.5,
            costo_secada_punto_usd=2.50,
        ),
        weather=WeatherData(
            provider="google_weather",
            provider_status="live",
            precipitation_next_72h_mm=0.0,
            wind_max_next_24h_kmh=14.0,
            temp_min_next_72h_c=10.0,
        ),
    )
