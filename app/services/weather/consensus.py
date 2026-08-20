"""
Módulo de Consenso y Evaluación de Discrepancias Meteorológicas (EduAgro).
Compara predicciones de proveedores sin promediar automáticamente. Proporciona recomendaciones
de modo de decisión ("primary", "conservative", "verify_in_field").
"""

from typing import Optional, Dict, Any, List
from app.services.weather.models import (
    NormalizedWeatherSnapshot,
    ForecastDisagreement,
    WeatherConsensus,
)


def evaluate_forecast_consensus(
    primary_snapshot: Optional[NormalizedWeatherSnapshot],
    secondary_snapshot: Optional[NormalizedWeatherSnapshot],
    consensus_enabled: bool = True,
) -> WeatherConsensus:
    """
    Evalúa las diferencias de variables críticas entre el proveedor primario y el secundario.
    No promedia automáticamente los valores.
    """
    if not consensus_enabled or not primary_snapshot or not secondary_snapshot:
        return WeatherConsensus(
            enabled=consensus_enabled,
            primary_provider=primary_snapshot.provider if primary_snapshot else "unknown",
            secondary_provider=secondary_snapshot.provider if secondary_snapshot else None,
            disagreement=ForecastDisagreement(
                level="not_evaluated",
                differences={},
                recommended_decision_mode="primary",
                reason_codes=["SINGLE_PROVIDER_OR_DISABLED"],
            ),
        )

    p_agg = primary_snapshot.aggregates
    s_agg = secondary_snapshot.aggregates

    differences: Dict[str, float] = {}
    reason_codes: List[str] = []

    if p_agg and s_agg:
        # Precipitaciones a 72h
        if p_agg.precipitation_next_72h_mm is not None and s_agg.precipitation_next_72h_mm is not None:
            diff_p72 = round(abs(p_agg.precipitation_next_72h_mm - s_agg.precipitation_next_72h_mm), 1)
            differences["precipitation_next_72h_mm"] = diff_p72
            if diff_p72 >= 15.0:
                reason_codes.append("HIGH_PRECIPITATION_72H_DISCREPANCY")

        # Viento máximo 72h
        if p_agg.wind_max_next_72h_kmh is not None and s_agg.wind_max_next_72h_kmh is not None:
            diff_v72 = round(abs(p_agg.wind_max_next_72h_kmh - s_agg.wind_max_next_72h_kmh), 1)
            differences["wind_max_next_72h_kmh"] = diff_v72
            if diff_v72 >= 10.0:
                reason_codes.append("HIGH_WIND_MAX_72H_DISCREPANCY")

        # Ráfagas máximas 72h
        if p_agg.wind_gust_max_next_72h_kmh is not None and s_agg.wind_gust_max_next_72h_kmh is not None:
            diff_g72 = round(abs(p_agg.wind_gust_max_next_72h_kmh - s_agg.wind_gust_max_next_72h_kmh), 1)
            differences["wind_gust_max_next_72h_kmh"] = diff_g72

        # Temperatura mínima 72h
        if p_agg.temp_min_next_72h_c is not None and s_agg.temp_min_next_72h_c is not None:
            diff_tmin = round(abs(p_agg.temp_min_next_72h_c - s_agg.temp_min_next_72h_c), 1)
            differences["temp_min_next_72h_c"] = diff_tmin
            if diff_tmin >= 3.0:
                reason_codes.append("HIGH_TEMP_MIN_DISCREPANCY")

    # Evaluación del nivel de discrepancia
    p_diff = differences.get("precipitation_next_72h_mm", 0.0)
    w_diff = differences.get("wind_max_next_72h_kmh", 0.0)
    t_diff = differences.get("temp_min_next_72h_c", 0.0)

    if p_diff >= 15.0 or w_diff >= 15.0 or t_diff >= 4.0:
        level = "high"
        mode = "verify_in_field"
    elif p_diff >= 8.0 or w_diff >= 8.0 or t_diff >= 2.0:
        level = "medium"
        mode = "conservative"
    else:
        level = "low"
        mode = "primary"

    disagreement = ForecastDisagreement(
        level=level,
        differences=differences,
        recommended_decision_mode=mode,
        reason_codes=reason_codes,
    )

    return WeatherConsensus(
        enabled=True,
        primary_provider=primary_snapshot.provider,
        secondary_provider=secondary_snapshot.provider,
        disagreement=disagreement,
    )
