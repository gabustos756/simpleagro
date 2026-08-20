"""
Calculadora Pura de Elegibilidad y Ranking de Opciones de Entrega (EduAgro).
Evalúa aptitud por camino, cupo y humedad de recibo, y ordena alternativas determinísticamente.
"""

from decimal import Decimal
from typing import Optional, List, Literal, Union
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.services.decision_engine.models import (
    DeliveryDestinationContext,
    RoadStatus,
    AvailabilityStatus,
)
from app.services.decision_engine.calculators.freight import (
    DeliveryEconomicsResult,
    calculate_delivery_economics,
)


class DestinationEligibilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    destination_id: Optional[Union[UUID, str]] = None
    destination_name: str
    eligibility_status: Literal["eligible", "conditionally_eligible", "not_eligible", "not_evaluable"]
    reasons: List[str] = []
    missing_inputs: List[str] = []


class RankedDeliveryOptionsResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    best_option: Optional[DeliveryEconomicsResult] = None
    is_best_option_material: bool = False
    net_difference_usd_tn: Optional[Decimal] = None
    all_economics: List[DeliveryEconomicsResult] = []
    all_eligibilities: List[DestinationEligibilityResult] = []
    ranked_options: List[DeliveryEconomicsResult] = []


def evaluate_destination_eligibility(
    destination: DeliveryDestinationContext,
    grain_moisture_pct: Optional[float] = None,
) -> DestinationEligibilityResult:
    """
    Evalúa determinísticamente si un destino es elegible, condicionado o no apto.
    """
    reasons: List[str] = []
    missing: List[str] = []
    is_not_eligible = False
    is_conditioned = False

    # 1. Verificar estado de caminos
    if destination.road_status == RoadStatus.IMPASSABLE:
        is_not_eligible = True
        reasons.append("DESTINO_NO_APTO_POR_CAMINO")
    elif destination.road_status in (RoadStatus.POOR, RoadStatus.CONDITIONED):
        is_conditioned = True
        reasons.append("CAMINO_RURAL_CONDICIONADO")

    # 2. Verificar confirmación de recepción / cupo
    if destination.receiving_confirmed == AvailabilityStatus.UNAVAILABLE:
        is_not_eligible = True
        reasons.append("DESTINO_SIN_RECEPCION")
    elif destination.receiving_confirmed == AvailabilityStatus.UNKNOWN:
        is_conditioned = True
        reasons.append("DESTINO_SIN_CUPO_CONFIRMADO")

    # 3. Verificar límite de humedad de recepción
    max_moisture = destination.max_receiving_moisture_pct
    if max_moisture is not None and grain_moisture_pct is not None:
        if Decimal(str(grain_moisture_pct)) > max_moisture:
            is_conditioned = True
            reasons.append("HUMEDAD_SUPERA_RECEPCION")
    elif max_moisture is None:
        missing.append("max_receiving_moisture_pct")
    elif grain_moisture_pct is None:
        missing.append("grain_moisture_pct")

    # Determinar status final
    if is_not_eligible:
        status = "not_eligible"
    elif is_conditioned:
        status = "conditionally_eligible"
    elif len(missing) > 0:
        status = "conditionally_eligible"
        reasons.append("DATOS_INCOMPLETOS_RECEPCION")
    else:
        status = "eligible"

    return DestinationEligibilityResult(
        destination_id=destination.destination_id,
        destination_name=destination.destination_name,
        eligibility_status=status,
        reasons=reasons,
        missing_inputs=missing,
    )


def rank_delivery_options(
    destinations: List[DeliveryDestinationContext],
    grain_moisture_pct: Optional[float] = None,
    min_material_difference_usd_tn: Decimal = Decimal("1.0"),
    max_quote_age_hours: int = 48,
) -> RankedDeliveryOptionsResult:
    """
    Ordena determinísticamente las opciones de entrega por precio neto en origen descendente.
    Compara sólo alternativas elegibles o condicionadas con cálculo económico completo.
    """
    all_econ: List[DeliveryEconomicsResult] = []
    all_elig: List[DestinationEligibilityResult] = []

    elig_map: dict[str, DestinationEligibilityResult] = {}

    for d in destinations:
        econ = calculate_delivery_economics(d, max_quote_age_hours=max_quote_age_hours)
        elig = evaluate_destination_eligibility(d, grain_moisture_pct=grain_moisture_pct)
        all_econ.append(econ)
        all_elig.append(elig)
        elig_map[d.destination_name] = elig

    # Filtrar opciones candidatas: elegibles o condicionadas, con precio neto completo
    candidates = [
        e for e in all_econ
        if e.is_net_price_fully_calculated
        and e.net_origin_price_usd_tn is not None
        and elig_map.get(e.destination_name, DestinationEligibilityResult(destination_name=e.destination_name, eligibility_status="not_eligible")).eligibility_status in ("eligible", "conditionally_eligible")
    ]

    # Ordenar candidatos por precio neto en origen descendente
    candidates.sort(key=lambda x: x.net_origin_price_usd_tn or Decimal("-999999"), reverse=True)

    best_opt: Optional[DeliveryEconomicsResult] = None
    is_material = False
    diff_usd: Optional[Decimal] = None

    if candidates:
        best_opt = candidates[0]
        if len(candidates) >= 2:
            second_best = candidates[1]
            if best_opt.net_origin_price_usd_tn is not None and second_best.net_origin_price_usd_tn is not None:
                diff_usd = best_opt.net_origin_price_usd_tn - second_best.net_origin_price_usd_tn
                if diff_usd >= min_material_difference_usd_tn:
                    is_material = True

    return RankedDeliveryOptionsResult(
        best_option=best_opt,
        is_best_option_material=is_material,
        net_difference_usd_tn=diff_usd,
        all_economics=all_econ,
        all_eligibilities=all_elig,
        ranked_options=candidates,
    )
