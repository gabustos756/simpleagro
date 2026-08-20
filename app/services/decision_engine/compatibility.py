"""
Adaptador de Compatibilidad Legacy para el Motor de Decisiones (EduAgro).
Transforma DecisionResult en la lista tradicional de diccionarios esperada por Jinja2 y endpoints legacy.
"""

from typing import List, Dict, Any
from app.services.decision_engine.models import DecisionResult, DecisionInsight


def result_to_legacy_insights(result: DecisionResult) -> List[Dict[str, Any]]:
    """
    Convierte la lista de DecisionInsight contenida en DecisionResult en diccionarios legacy.
    """
    legacy_list: List[Dict[str, Any]] = []

    for insight in result.insights:
        legacy_list.append({
            "codigo": insight.codigo,
            "nivel": insight.nivel,
            "titulo": insight.titulo,
            "mensaje": insight.mensaje,
            "datos": insight.datos or {},
        })

    return legacy_list
