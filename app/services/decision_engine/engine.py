"""
Orquestador Principal Sincrónico del Motor de Decisiones (EduAgro - Decision Engine v2.0).
Garantiza ejecución pura, determinística, explicable y sin efectos secundarios.
"""

from typing import Dict, Any, List, Optional, Union
import logging

from app.services.decision_engine.models import (
    DecisionContext,
    DecisionResult,
    DecisionInsight,
    RuleEvaluation,
)
from app.services.decision_engine.policy import DecisionPolicyResolver, PolicyLayer
from app.services.decision_engine.registry import RuleRegistry, create_default_registry
from app.services.decision_engine.context_builder import build_decision_context_from_dict
from app.services.decision_engine.trace import build_decision_trace
from app.services.decision_engine.rules.base import RuleTraceContext

logger = logging.getLogger("eduagro.decision_engine")


class DecisionEngine:
    """
    Motor de Decisiones Determinístico y Explicable.
    """

    def __init__(self, registry: Optional[RuleRegistry] = None):
        self.registry = registry or create_default_registry()

    def evaluate(
        self,
        context: Union[DecisionContext, Dict[str, Any]],
        policy_layers: Optional[List[PolicyLayer]] = None,
    ) -> DecisionResult:
        """
        Ejecuta determinísticamente la evaluación de reglas del contexto provisto.
        """
        # 1. Normalizar contexto
        if isinstance(context, dict):
            norm_ctx = build_decision_context_from_dict(context)
        else:
            norm_ctx = context

        # 2. Resolver Política Efectiva Jerárquica
        resolver = DecisionPolicyResolver(layers=policy_layers)
        effective_policy = resolver.resolve()

        # 3. Contexto de Traza
        trace_context = RuleTraceContext()

        # 4. Evaluar Reglas Registradas
        evaluations = self.registry.evaluate_all(norm_ctx, effective_policy, trace_context)

        # 5. Extraer Insights Activados
        triggered_insights: List[DecisionInsight] = []
        for ev in evaluations:
            if ev.status == "triggered" and ev.insight is not None:
                triggered_insights.append(ev.insight)

        # Ordenar insights por prioridad ascendente
        triggered_insights.sort(key=lambda ins: ins.priority)

        # 6. Construir Traza de Auditoría
        trace = build_decision_trace(
            evaluations=evaluations,
            context=norm_ctx,
            effective_policy=effective_policy,
            warnings=trace_context.warnings,
        )

        return DecisionResult(
            insights=triggered_insights,
            trace=trace,
            normalized_context=norm_ctx,
            effective_policy=effective_policy,
            engine_version="2.0.0",
        )
