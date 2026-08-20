"""
Calculadora Pura de Riesgo de Cosecha y Secado Natural (EduAgro).
"""

from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class HarvestRiskResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_evaluated: bool
    quality_risk: Optional[str] = None
    physical_loss_risk: Optional[str] = None
    logistics_risk: Optional[str] = None
    delay_risk: Optional[str] = None
    natural_drying_benefit_usd_tn: Optional[float] = None
    missing_inputs: List[str] = []


def evaluate_harvest_risk(
    grain_moisture_pct: Optional[float],
    base_moisture_pct: Optional[float],
    drying_cost_per_point_usd: Optional[float],
    precip_72h_mm: Optional[float],
    vuelco_observado: Optional[bool] = None,
    desgrane_observado: Optional[bool] = None,
) -> HarvestRiskResult:
    """
    Evalúa el balance entre el ahorro potencial de secado natural en pie y los riesgos de espera.
    """
    missing: List[str] = []
    if grain_moisture_pct is None:
        missing.append("grain_moisture_pct")
    if base_moisture_pct is None:
        missing.append("base_moisture_pct")

    if missing:
        return HarvestRiskResult(is_evaluated=False, missing_inputs=missing)

    natural_benefit = None
    if grain_moisture_pct > base_moisture_pct and drying_cost_per_point_usd is not None:
        excess = grain_moisture_pct - base_moisture_pct
        natural_benefit = round(excess * drying_cost_per_point_usd, 2)

    vuelco = "alto" if vuelco_observado else ("bajo" if vuelco_observado is False else "desconocido")
    desgrane = "alto" if desgrane_observado else ("bajo" if desgrane_observado is False else "desconocido")

    p72 = precip_72h_mm if precip_72h_mm is not None else 0.0
    quality = "alto" if p72 >= 15.0 and grain_moisture_pct > base_moisture_pct else "moderado"

    return HarvestRiskResult(
        is_evaluated=True,
        quality_risk=quality,
        physical_loss_risk=f"Vuelco: {vuelco}, Desgrane: {desgrane}",
        logistics_risk="Requiere verificar disponibilidad de transporte y acopio",
        delay_risk="Riesgo de precipitaciones en ventana de 72h" if p72 >= 10.0 else "Bajo riesgo de precipitaciones en 72h",
        natural_drying_benefit_usd_tn=natural_benefit,
        missing_inputs=missing,
    )
