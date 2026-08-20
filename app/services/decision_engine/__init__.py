"""
Paquete Oficial del Motor de Decisiones Determinístico (EduAgro v2.0).
Exporta el orquestador principal, resolutores de política, modelos y utilidades de compatibilidad.
"""

from app.services.decision_engine.models import (
    DecisionContext,
    DecisionResult,
    DecisionInsight,
    DecisionTrace,
    RuleEvaluation,
    DataAvailability,
    DataQualityItem,
    EffectivePolicyValue,
)
from app.services.decision_engine.policy import DecisionPolicyResolver, PolicyLayer
from app.services.decision_engine.policy_defaults import SYSTEM_BASE_DECISION_POLICY
from app.services.decision_engine.registry import RuleRegistry, create_default_registry
from app.services.decision_engine.engine import DecisionEngine
from app.services.decision_engine.context_builder import (
    build_decision_context_from_dict,
    build_demo_decision_context,
)
from app.services.decision_engine.compatibility import result_to_legacy_insights

__all__ = [
    "DecisionEngine",
    "DecisionContext",
    "DecisionResult",
    "DecisionInsight",
    "DecisionTrace",
    "RuleEvaluation",
    "DataAvailability",
    "DataQualityItem",
    "EffectivePolicyValue",
    "DecisionPolicyResolver",
    "PolicyLayer",
    "SYSTEM_BASE_DECISION_POLICY",
    "RuleRegistry",
    "create_default_registry",
    "build_decision_context_from_dict",
    "build_demo_decision_context",
    "result_to_legacy_insights",
]
