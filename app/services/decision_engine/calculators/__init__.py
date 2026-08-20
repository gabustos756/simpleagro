"""
Calculadoras Puras y Determinísticas para el Motor de Decisiones de EduAgro.
Sin acceso a DB, sin I/O, sin llamadas globales a time/now.
"""

from app.services.decision_engine.calculators.drying import calculate_drying_cost, DryingCostResult
from app.services.decision_engine.calculators.harvest_risk import evaluate_harvest_risk, HarvestRiskResult
from app.services.decision_engine.calculators.trafficability import evaluate_trafficability, TrafficabilityResult
from app.services.decision_engine.calculators.commercial import evaluate_commercial_carry, CommercialCarryResult
from app.services.decision_engine.calculators.spraying import evaluate_spraying_conditions, SprayingConditionsResult
from app.services.decision_engine.calculators.freight import calculate_delivery_economics, DeliveryEconomicsResult
from app.services.decision_engine.calculators.delivery_economics import (
    evaluate_destination_eligibility,
    DestinationEligibilityResult,
    rank_delivery_options,
    RankedDeliveryOptionsResult,
)

from app.services.decision_engine.calculators.delivery import (
    calculate_origin_net_weight,
    DeliveryWeightCalculationResult,
    calculate_delivery_weight_difference,
    DeliveryDifferenceCalculationResult,
    calculate_estimated_delivery_freight,
    DeliveryFreightCalculationResult,
)

__all__ = [
    "calculate_drying_cost",
    "DryingCostResult",
    "evaluate_harvest_risk",
    "HarvestRiskResult",
    "evaluate_trafficability",
    "TrafficabilityResult",
    "evaluate_commercial_carry",
    "CommercialCarryResult",
    "evaluate_spraying_conditions",
    "SprayingConditionsResult",
    "calculate_delivery_economics",
    "DeliveryEconomicsResult",
    "evaluate_destination_eligibility",
    "DestinationEligibilityResult",
    "rank_delivery_options",
    "RankedDeliveryOptionsResult",
    "calculate_origin_net_weight",
    "DeliveryWeightCalculationResult",
    "calculate_delivery_weight_difference",
    "DeliveryDifferenceCalculationResult",
    "calculate_estimated_delivery_freight",
    "DeliveryFreightCalculationResult",
]
