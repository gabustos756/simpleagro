"""
Calculadora Pura de Economía de Flete y Precio Neto en Origen por Destino (EduAgro).
Calcula determinísticamente deducciones y precio neto en origen usando Decimal sin I/O ni efectores externos.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Union
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.services.decision_engine.models import DeliveryDestinationContext


class DeliveryEconomicsResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    destination_id: Optional[Union[UUID, str]] = None
    destination_name: str
    offered_price_usd_tn: Optional[Decimal] = None
    freight_usd_tn: Optional[Decimal] = None
    conditioning_cost_usd_tn: Optional[Decimal] = None
    other_costs_usd_tn: Optional[Decimal] = None
    total_deductions_usd_tn: Optional[Decimal] = None
    net_origin_price_usd_tn: Optional[Decimal] = None
    is_net_price_fully_calculated: bool = False
    missing_cost_fields: List[str] = []
    is_quote_stale: bool = False


def _to_naive(dt: datetime) -> datetime:
    """Elimina tzinfo para permitir comparación segura entre datetimes tz-aware y tz-naive."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def calculate_delivery_economics(
    destination: DeliveryDestinationContext,
    max_quote_age_hours: int = 48,
    current_time: Optional[datetime] = None,
) -> DeliveryEconomicsResult:
    """
    Calcula determinísticamente el precio neto en origen (USD/Tn) descontando flete, acondicionamiento y otros costos.
    """
    now = current_time or datetime.now()
    now_naive = _to_naive(now)
    missing: List[str] = []

    p_offered = destination.price_usd_tn
    flete = destination.freight_usd_tn
    cond_cost = destination.conditioning_cost_usd_tn if destination.conditioning_cost_usd_tn is not None else Decimal("0.0")
    other_cost = destination.other_costs_usd_tn if destination.other_costs_usd_tn is not None else Decimal("0.0")

    if p_offered is None:
        missing.append("price_usd_tn")
    if flete is None:
        missing.append("freight_usd_tn")

    is_fully_calc = len(missing) == 0

    net_origin_price: Optional[Decimal] = None
    total_deductions: Optional[Decimal] = None

    if is_fully_calc and p_offered is not None and flete is not None:
        total_deductions = flete + cond_cost + other_cost
        net_origin_price = p_offered - total_deductions

    # Evaluación de vigencia de cotización (con comparación timezone-safe)
    is_stale = False
    if destination.quote_valid_until and _to_naive(destination.quote_valid_until) < now_naive:
        is_stale = True
    elif destination.quote_observed_at:
        age_hours = (now_naive - _to_naive(destination.quote_observed_at)).total_seconds() / 3600.0
        if age_hours > max_quote_age_hours:
            is_stale = True

    return DeliveryEconomicsResult(
        destination_id=destination.destination_id,
        destination_name=destination.destination_name,
        offered_price_usd_tn=p_offered,
        freight_usd_tn=flete,
        conditioning_cost_usd_tn=destination.conditioning_cost_usd_tn,
        other_costs_usd_tn=destination.other_costs_usd_tn,
        total_deductions_usd_tn=total_deductions,
        net_origin_price_usd_tn=net_origin_price,
        is_net_price_fully_calculated=is_fully_calc,
        missing_cost_fields=missing,
        is_quote_stale=is_stale,
    )
