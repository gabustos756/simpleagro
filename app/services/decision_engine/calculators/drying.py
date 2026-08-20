"""
Calculadora Pura de Costo de Secado de Grano (EduAgro).
"""

from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class DryingCostResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_evaluated: bool
    excess_moisture_points: Optional[float] = None
    total_drying_cost_usd_tn: Optional[float] = None
    cost_pct_over_spot: Optional[float] = None
    missing_inputs: List[str] = []


def calculate_drying_cost(
    grain_moisture_pct: Optional[float],
    commercial_base_moisture_pct: Optional[float],
    drying_cost_per_point_usd_tn: Optional[float],
    spot_price_usd_tn: Optional[float],
) -> DryingCostResult:
    """
    Calcula determinísticamente el exceso de humedad y costo de secada en USD/Tn.
    Si faltan datos requeridos, retorna is_evaluated=False con missing_inputs explícitos.
    """
    missing: List[str] = []
    if grain_moisture_pct is None:
        missing.append("grain_moisture_pct")
    if commercial_base_moisture_pct is None:
        missing.append("commercial_base_moisture_pct")
    if drying_cost_per_point_usd_tn is None:
        missing.append("drying_cost_per_point_usd_tn")

    if missing:
        return DryingCostResult(is_evaluated=False, missing_inputs=missing)

    excess_pts = max(0.0, float(grain_moisture_pct) - float(commercial_base_moisture_pct))
    total_cost = excess_pts * float(drying_cost_per_point_usd_tn)

    cost_pct = None
    if spot_price_usd_tn is not None and float(spot_price_usd_tn) > 0.0:
        cost_pct = (total_cost / float(spot_price_usd_tn)) * 100.0
    elif spot_price_usd_tn is None:
        missing.append("spot_price_usd_tn")

    return DryingCostResult(
        is_evaluated=True,
        excess_moisture_points=round(excess_pts, 2),
        total_drying_cost_usd_tn=round(total_cost, 2),
        cost_pct_over_spot=round(cost_pct, 2) if cost_pct is not None else None,
        missing_inputs=missing,
    )
