"""
Calculadora Pura de Pesaje y Economía de Entregas y Cartas de Porte (EduAgro).
Calcula determinísticamente pesajes, diferencias y flete estimado por entrega usando Decimal sin I/O.
"""

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict


class DeliveryWeightCalculationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    gross_weight_kg: Optional[Decimal] = None
    tare_weight_kg: Optional[Decimal] = None
    origin_net_weight_kg: Optional[Decimal] = None
    is_valid_origin_weight: bool = False
    warning: Optional[str] = None


class DeliveryDifferenceCalculationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    origin_net_weight_kg: Optional[Decimal] = None
    destination_received_weight_kg: Optional[Decimal] = None
    difference_kg: Optional[Decimal] = None
    difference_pct: Optional[Decimal] = None
    is_evaluable: bool = False


class DeliveryFreightCalculationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    freight_usd_tn: Optional[Decimal] = None
    base_weight_kg: Optional[Decimal] = None
    weight_source: str  # "destination_received", "origin_net", "none"
    is_estimated: bool = True
    estimated_freight_cost_usd: Optional[Decimal] = None


def calculate_origin_net_weight(
    gross_weight_kg: Optional[Decimal],
    tare_weight_kg: Optional[Decimal],
) -> DeliveryWeightCalculationResult:
    """
    Calcula determinísticamente el peso neto de origen (Bruto - Tara).
    Retorna warning si el peso bruto es menor a la tara.
    """
    if gross_weight_kg is None or tare_weight_kg is None:
        return DeliveryWeightCalculationResult(
            gross_weight_kg=gross_weight_kg,
            tare_weight_kg=tare_weight_kg,
            origin_net_weight_kg=None,
            is_valid_origin_weight=False,
        )

    if gross_weight_kg < tare_weight_kg:
        return DeliveryWeightCalculationResult(
            gross_weight_kg=gross_weight_kg,
            tare_weight_kg=tare_weight_kg,
            origin_net_weight_kg=None,
            is_valid_origin_weight=False,
            warning="El peso bruto no puede ser menor a la tara.",
        )

    net_weight = gross_weight_kg - tare_weight_kg
    return DeliveryWeightCalculationResult(
        gross_weight_kg=gross_weight_kg,
        tare_weight_kg=tare_weight_kg,
        origin_net_weight_kg=net_weight,
        is_valid_origin_weight=True,
    )


def calculate_delivery_weight_difference(
    origin_net_weight_kg: Optional[Decimal],
    destination_received_weight_kg: Optional[Decimal],
) -> DeliveryDifferenceCalculationResult:
    """
    Calcula la diferencia de pesaje (Destino Recibido - Origen Neto) en kg y en %.
    """
    if origin_net_weight_kg is None or destination_received_weight_kg is None:
        return DeliveryDifferenceCalculationResult(
            origin_net_weight_kg=origin_net_weight_kg,
            destination_received_weight_kg=destination_received_weight_kg,
            difference_kg=None,
            difference_pct=None,
            is_evaluable=False,
        )

    diff_kg = destination_received_weight_kg - origin_net_weight_kg
    diff_pct: Optional[Decimal] = None
    if origin_net_weight_kg > Decimal("0.0"):
        diff_pct = (diff_kg / origin_net_weight_kg) * Decimal("100.0")

    return DeliveryDifferenceCalculationResult(
        origin_net_weight_kg=origin_net_weight_kg,
        destination_received_weight_kg=destination_received_weight_kg,
        difference_kg=diff_kg,
        difference_pct=diff_pct,
        is_evaluable=True,
    )


def calculate_estimated_delivery_freight(
    freight_usd_tn: Optional[Decimal],
    origin_net_weight_kg: Optional[Decimal],
    destination_received_weight_kg: Optional[Decimal],
) -> DeliveryFreightCalculationResult:
    """
    Calcula el costo estimado de flete por entrega.
    Prioriza peso recibido de destino si existe; de lo contrario usa neto origen.
    """
    if freight_usd_tn is None:
        return DeliveryFreightCalculationResult(
            freight_usd_tn=None,
            base_weight_kg=None,
            weight_source="none",
            is_estimated=True,
            estimated_freight_cost_usd=None,
        )

    base_weight: Optional[Decimal] = None
    weight_source = "none"
    is_estimated = True

    if destination_received_weight_kg is not None and destination_received_weight_kg > Decimal("0.0"):
        base_weight = destination_received_weight_kg
        weight_source = "destination_received"
        is_estimated = False
    elif origin_net_weight_kg is not None and origin_net_weight_kg > Decimal("0.0"):
        base_weight = origin_net_weight_kg
        weight_source = "origin_net"
        is_estimated = True

    if base_weight is None:
        return DeliveryFreightCalculationResult(
            freight_usd_tn=freight_usd_tn,
            base_weight_kg=None,
            weight_source="none",
            is_estimated=True,
            estimated_freight_cost_usd=None,
        )

    cost_usd = (base_weight / Decimal("1000.0")) * freight_usd_tn

    return DeliveryFreightCalculationResult(
        freight_usd_tn=freight_usd_tn,
        base_weight_kg=base_weight,
        weight_source=weight_source,
        is_estimated=is_estimated,
        estimated_freight_cost_usd=cost_usd,
    )
