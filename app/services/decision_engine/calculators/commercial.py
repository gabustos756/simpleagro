"""
Calculadora Pura de Comercialización y Carry Neto de Futuros (EduAgro).
"""

from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class CommercialCarryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_fully_evaluated: bool
    spread_bruto_usd_tn: Optional[float] = None
    carry_neto_estimado_usd_tn: Optional[float] = None
    missing_inputs: List[str] = []
    warning: Optional[str] = None


def evaluate_commercial_carry(
    spot_price_usd_tn: Optional[float],
    future_price_usd_tn: Optional[float],
    storage_cost_per_month_usd_tn: Optional[float] = None,
    monthly_interest_rate_pct: Optional[float] = None,
    months_to_future: int = 1,
) -> CommercialCarryResult:
    """
    Evalúa el pase de futuros (bruto y neto estimado).
    """
    missing: List[str] = []
    if spot_price_usd_tn is None:
        missing.append("spot_price_usd_tn")
    if future_price_usd_tn is None:
        missing.append("future_price_usd_tn")

    if missing:
        return CommercialCarryResult(is_fully_evaluated=False, missing_inputs=missing)

    spread_bruto = round(float(future_price_usd_tn) - float(spot_price_usd_tn), 2)

    # Costos financieros/almacenaje adicionales
    financial_missing: List[str] = []
    if storage_cost_per_month_usd_tn is None:
        financial_missing.append("storage_cost_per_month_usd_tn")
    if monthly_interest_rate_pct is None:
        financial_missing.append("monthly_interest_rate_pct")

    carry_neto = None
    warning_msg = None

    if not financial_missing:
        costo_almacenaje = float(storage_cost_per_month_usd_tn) * months_to_future
        costo_financiero = (float(spot_price_usd_tn) * (float(monthly_interest_rate_pct) / 100.0)) * months_to_future
        carry_neto = round(spread_bruto - (costo_almacenaje + costo_financiero), 2)
    else:
        warning_msg = (
            "El pase bruto es favorable, pero la conveniencia neta depende de costos financieros, "
            "almacenaje, seguro, merma, flete, calidad y estrategia comercial."
        )

    return CommercialCarryResult(
        is_fully_evaluated=len(financial_missing) == 0,
        spread_bruto_usd_tn=spread_bruto,
        carry_neto_estimado_usd_tn=carry_neto,
        missing_inputs=financial_missing,
        warning=warning_msg,
    )
