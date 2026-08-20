"""
Módulo Agente de Reglas de Decisión Agronómica y Comercial (EduAgro).
Exporta helpers para invocar el motor de decisión formal y trazable.
"""

from typing import Dict, List, Any, Optional
from app.services.decision_motor import evaluar_motor_decisiones
from app.services.decision_engine import build_demo_decision_context, result_to_legacy_insights, DecisionEngine


def evaluar_decision_campo(
    cultivo: Optional[str] = None,
    precio_fisico_usd: Optional[float] = None,
    precio_futuro_usd: Optional[float] = None,
    humedad_grano_pct: Optional[float] = None,
    lluvia_esperada_mm: Optional[float] = None,
    viento_max_kmh: Optional[float] = None,
    temp_min_c: Optional[float] = None,
    campo_nombre: Optional[str] = None,
    policy: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Helper de nivel superior para ejecutar el motor de decisiones ingresando parámetros de prueba u operativos.
    Los parámetros no suministrados se procesan como None (sin falsos valores numéricos).
    """
    spread = None
    if precio_futuro_usd is not None and precio_fisico_usd is not None:
        spread = round(precio_futuro_usd - precio_fisico_usd, 2)

    contexto = {
        "cultivo": cultivo,
        "precio_fisico_usd": precio_fisico_usd,
        "precio_futuro_usd": precio_futuro_usd,
        "spread_futuro_usd": spread,
        "humedad_grano_pct": humedad_grano_pct,
        "lluvia_esperada_mm": lluvia_esperada_mm,
        "viento_max_kmh": viento_max_kmh,
        "temp_min_c": temp_min_c,
        "campo_nombre": campo_nombre,
    }
    return evaluar_motor_decisiones(contexto, policy=policy)


def evaluar_demo_campo() -> List[Dict[str, Any]]:
    """
    Helper explicito para ejecutar la demostración con contexto de prueba tipado.
    """
    engine = DecisionEngine()
    demo_ctx = build_demo_decision_context()
    result = engine.evaluate(demo_ctx)
    return result_to_legacy_insights(result)
