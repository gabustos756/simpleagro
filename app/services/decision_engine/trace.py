"""
Gestor de Trazabilidad y Auditoría para el Motor de Decisiones (EduAgro).
"""

from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from uuid import uuid4, UUID

from app.services.decision_engine.models import (
    DecisionTrace,
    RuleEvaluation,
    DataQualityItem,
    EffectivePolicyValue,
    DecisionContext,
)


def build_decision_trace(
    evaluations: List[RuleEvaluation],
    context: DecisionContext,
    effective_policy: Dict[str, EffectivePolicyValue],
    warnings: Optional[List[str]] = None,
) -> DecisionTrace:
    """
    Construye la traza de auditoría inmutable del motor de decisiones.
    """
    data_quality_items: List[DataQualityItem] = []

    # Extraer procedencia climática
    weather_prov = {
        "provider": context.weather.provider,
        "provider_status": context.weather.provider_status,
        "retrieved_at": context.weather.retrieved_at.isoformat() if context.weather.retrieved_at else None,
        "disagreement_level": context.weather.disagreement_level,
        "recommended_decision_mode": context.weather.recommended_decision_mode,
    }

    policy_versions = list({ep.policy_version for ep in effective_policy.values() if ep.policy_version})

    return DecisionTrace(
        trace_id=str(uuid4()),
        engine_version="2.0.0",
        evaluated_at=datetime.now(),
        context_schema_version="v2.0",
        policy_schema_version="v2.0",
        policy_versions=policy_versions,
        rules_evaluated=evaluations,
        data_quality=data_quality_items,
        weather_provenance=weather_prov,
        effective_policy_provenance=effective_policy,
        warnings=warnings or [],
    )
