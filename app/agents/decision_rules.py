"""
Módulo Agente de Reglas de Decisión Agronómica y Comercial (EduAgro).
Exporta el motor de decisión formal y trazable.
"""

from typing import Dict, List, Any, Optional
from app.services.decision_motor import evaluar_motor_decisiones, DEFAULT_DECISION_POLICY


def evaluar_decision_campo(
    cultivo: str = "maiz",
    precio_fisico_usd: float = 188.0,
    precio_futuro_usd: float = 195.0,
    humedad_grano_pct: float = 17.5,
    lluvia_esperada_mm: float = 0.0,
    viento_max_kmh: float = 14.0,
    temp_min_c: float = 10.0,
    campo_nombre: str = "Estancia La Esperanza",
    policy: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Helper de alto nivel para ejecutar el motor de decisiones ingresando parámetros de prueba u operativos.
    """
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
        "alerta_viento": viento_max_kmh > 15.0,
        "alerta_lluvia": lluvia_esperada_mm >= 10.0,
        "alerta_helada": temp_min_c < 4.0,
        "campo_nombre": campo_nombre,
    }
    return evaluar_motor_decisiones(contexto, policy=policy)
