"""
Calculadora Pura de Transitabilidad y Riesgo de Piso (EduAgro).
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict


class TrafficabilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_evaluated: bool
    risk_level: Optional[Literal["low", "medium", "high"]] = None
    reason_summary: Optional[str] = None
    missing_inputs: List[str] = []


def evaluate_trafficability(
    precip_24h_mm: Optional[float],
    precip_72h_mm: Optional[float],
    critical_threshold_mm: float = 10.0,
    road_condition: Optional[str] = None,
) -> TrafficabilityResult:
    """
    Evalúa conservadoramente la transitabilidad de caminos y riesgo de piso en lote.
    """
    missing: List[str] = []
    if precip_24h_mm is None and precip_72h_mm is None:
        missing.append("precipitation_forecast")

    if missing:
        return TrafficabilityResult(is_evaluated=False, missing_inputs=missing)

    p24 = precip_24h_mm or 0.0
    p72 = precip_72h_mm or p24

    if p24 >= critical_threshold_mm or p72 >= (critical_threshold_mm * 1.5):
        risk = "high"
        reason = f"Precipitación prevista significativa ({p72:.1f} mm en 72h) que puede comprometer el piso."
    elif p72 >= critical_threshold_mm:
        risk = "medium"
        reason = f"Precipitación moderada prevista ({p72:.1f} mm en 72h)."
    else:
        risk = "low"
        reason = f"Precipitación estimada baja ({p72:.1f} mm en 72h)."

    if road_condition == "intransitable":
        risk = "high"
        reason += " Estado de caminos rurales reportado como intransitable."

    return TrafficabilityResult(
        is_evaluated=True,
        risk_level=risk,
        reason_summary=reason,
        missing_inputs=missing,
    )
