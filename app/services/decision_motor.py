"""
Fachada de Compatibilidad para el Motor de Decisiones (EduAgro - Façade v2.0).
Delega la evaluación determinística en app.services.decision_engine preservando los contratos públicos legacy.
"""

import logging
from typing import Dict, List, Any, Optional, Union

from app.services.decision_engine import (
    DecisionEngine,
    DecisionContext,
    DecisionResult,
    PolicyLayer,
    SYSTEM_BASE_DECISION_POLICY,
    result_to_legacy_insights,
)

logger = logging.getLogger("eduagro.motor_decision")

# Vista de compatibilidad legacy de la política por defecto
DEFAULT_DECISION_POLICY: Dict[str, Any] = {
    "humedad_base_maiz": SYSTEM_BASE_DECISION_POLICY["cosecha"]["humedad_comercial_base_por_cultivo"]["maiz"],
    "humedad_base_soja": SYSTEM_BASE_DECISION_POLICY["cosecha"]["humedad_comercial_base_por_cultivo"]["soja"],
    "humedad_base_sorgo": SYSTEM_BASE_DECISION_POLICY["cosecha"]["humedad_comercial_base_por_cultivo"]["sorgo"],
    "costo_secada_punto_usd": SYSTEM_BASE_DECISION_POLICY["cosecha"]["costo_secada_punto_usd"],
    "spread_futuro_min_usd": SYSTEM_BASE_DECISION_POLICY["comercializacion"]["spread_futuro_min_usd_legacy"],
    "lluvia_critica_mm": SYSTEM_BASE_DECISION_POLICY["cosecha"]["lluvia_critica_72h_mm"],
    "viento_limite_pulverizacion": SYSTEM_BASE_DECISION_POLICY["pulverizacion"]["viento_maximo_kmh"],
}

# Instancia global reutilizable del motor sincrónico
_ENGINE_INSTANCE = DecisionEngine()


def evaluar_motor_decisiones_detallado(
    contexto: Union[DecisionContext, Dict[str, Any]],
    policy_layers: Optional[List[PolicyLayer]] = None,
) -> DecisionResult:
    """
    API V2 del Motor de Decisiones: Retorna el resultado rico con traza de auditoría,
    contexto normalizado y procedencia de política efectiva.
    """
    return _ENGINE_INSTANCE.evaluate(contexto, policy_layers=policy_layers)


def evaluar_motor_decisiones(
    contexto: Dict[str, Any],
    policy: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    API V1 Legacy del Motor de Decisiones.
    Mantiene 100% de compatibilidad retornando una lista de diccionarios de insights.
    """
    layers: List[PolicyLayer] = []
    if policy:
        layers.append(
            PolicyLayer(
                scope="run_override",
                policy_data={"cosecha": policy, "comercializacion": policy, "pulverizacion": policy},
                policy_id="legacy-override",
            )
        )

    result = _ENGINE_INSTANCE.evaluate(contexto, policy_layers=layers if layers else None)
    return result_to_legacy_insights(result)
