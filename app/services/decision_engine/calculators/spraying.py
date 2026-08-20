"""
Calculadora Pura de Condiciones de Pulverización Fitosanitaria (EduAgro).
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict


class SprayingConditionsResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_evaluated: bool
    status: Literal["optimal", "caution", "danger", "incomplete"]
    wind_status: Optional[str] = None
    missing_inputs: List[str] = []
    requires_field_verification: bool = True


def evaluate_spraying_conditions(
    wind_speed_kmh: Optional[float],
    wind_gust_kmh: Optional[float] = None,
    wind_ideal_min_kmh: float = 5.0,
    wind_ideal_max_kmh: float = 10.0,
    wind_max_limit_kmh: float = 15.0,
    relative_humidity_pct: Optional[float] = None,
    temperature_c: Optional[float] = None,
) -> SprayingConditionsResult:
    """
    Evalúa las condiciones meteorológicas para aplicaciones de fitosanitarios.
    """
    missing: List[str] = []
    if wind_speed_kmh is None:
        missing.append("wind_speed_kmh")

    if relative_humidity_pct is None:
        missing.append("relative_humidity_pct")

    if temperature_c is None:
        missing.append("temperature_c")

    if wind_gust_kmh is None:
        missing.append("wind_gust_kmh")

    if wind_speed_kmh is None:
        return SprayingConditionsResult(
            is_evaluated=False,
            status="incomplete",
            missing_inputs=missing,
        )

    ws = float(wind_speed_kmh)
    gust = float(wind_gust_kmh) if wind_gust_kmh is not None else ws

    if ws > wind_max_limit_kmh or gust > (wind_max_limit_kmh * 1.2):
        status = "danger"
        w_msg = f"Viento o ráfagas ({gust:.1f} km/h) superan el límite de seguridad de {wind_max_limit_kmh:.0f} km/h (Riesgo de Deriva)."
    elif ws < wind_ideal_min_kmh:
        status = "caution"
        w_msg = f"Viento muy bajo ({ws:.1f} km/h). Riesgo de Inversión Térmica y suspensión de gotas."
    elif wind_ideal_min_kmh <= ws <= wind_ideal_max_kmh:
        status = "optimal" if len(missing) == 0 else "caution"
        w_msg = f"Viento dentro de la ventana de trabajo ({ws:.1f} km/h)."
    else:
        status = "caution"
        w_msg = f"Viento moderado ({ws:.1f} km/h). Ajustar tamaño de gota y altura de botalón."

    return SprayingConditionsResult(
        is_evaluated=True,
        status=status,
        wind_status=w_msg,
        missing_inputs=missing,
        requires_field_verification=True,
    )
