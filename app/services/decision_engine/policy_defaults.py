"""
Valores Base y Políticas del Sistema por Defecto (EduAgro - Decision Engine v2.0).
Documentados como parámetros iniciales pendientes de calibración agronómica local.
"""

from typing import Dict, Any

SYSTEM_BASE_DECISION_POLICY: Dict[str, Any] = {
    "policy_id": "system-base",
    "policy_version": "2.0.0",
    "cosecha": {
        "humedad_comercial_base_por_cultivo": {
            "maiz": 14.5,
            "soja": 13.5,
            "sorgo": 15.0,
            "trigo": 14.0,
        },
        "costo_secada_punto_usd": 2.50,
        "costo_secada_alerta_pct_spot": 3.0,
        "lluvia_critica_24h_mm": 10.0,
        "lluvia_critica_72h_mm": 10.0,
        "lluvia_acumulada_7d_critica_mm": None,
    },
    "comercializacion": {
        "spread_futuro_min_usd_legacy": 4.0,
        "margen_neto_diferimiento_min_usd_tn": 0.0,
    },
    "pulverizacion": {
        "viento_ideal_min_kmh": 5.0,
        "viento_ideal_max_kmh": 10.0,
        "viento_maximo_kmh": 15.0,
    },
    "helada": {
        "umbral_temperatura_minima_c": 4.0,
    },
    "freight": {
        "diferencia_neta_minima_relevante_usd_tn": 1.0,
        "max_quote_age_hours": 48,
        "require_receiving_confirmation_for_recommendation": True,
        "allow_conditionally_eligible_ranking": True,
    },
    "safety": {
        "allow_override_safety_controls": False,
        "require_data_quality_for_positive_recommendation": True,
    },
    "deliveries": {
        "normal_truck_reference_capacity_kg": 35000,
        "vulcano_truck_reference_capacity_kg": 45000,
        "weight_difference_review_pct": 1.0,
        "weight_difference_review_kg": 300,
        "require_waybill_for_completed_delivery": False,
        "default_final_destination_reference": "Rosario",
    },
    "stock_delivery": {
        "weight_difference_review_pct": 1.0,
        "weight_difference_review_kg": 300,
        "require_explicit_weight_difference_resolution": True,
        "allow_dispatch_without_destination_weight": True,
        "allow_stock_adjustment_for_weight_difference": True,
    },
}
