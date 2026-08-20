"""
Base y Protocolo Abstracto para Reglas del Motor de Decisiones (EduAgro).
"""

from typing import Protocol, Set, Dict, Any, List, Optional
from pydantic import BaseModel, ConfigDict

from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)


class RuleTraceContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    warnings: List[str] = []


def fmt_ar(val: Optional[float], decimales: int = 2) -> str:
    """Formatea números al estándar argentino (1.234,56)."""
    if val is None:
        return "N/D"
    val_str = f"{val:,.{decimales}f}"
    return val_str.replace(",", "X").replace(".", ",").replace("X", ".")


class DecisionRule(Protocol):
    code: str
    domain: str
    priority: int
    required_inputs: Set[str]

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        ...
