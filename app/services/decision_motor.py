"""
Motor de Decisión Determinístico y Trazable (EduAgro - FASE MOTOR DE DECISIÓN 1.0).
Combina Mercado Físico + Mercado a Término (Futuros) + Clima Geolocalizado + Variables Operativas de Campo.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Any, Optional

logger = logging.getLogger("eduagro.motor_decision")

# Parámetros por defecto para agricultura en Argentina
DEFAULT_DECISION_POLICY = {
    "humedad_base_maiz": 14.5,          # Humedad recibidor estándar Maíz
    "humedad_base_soja": 13.5,          # Humedad recibidor estándar Soja
    "humedad_base_sorgo": 15.0,         # Humedad recibidor estándar Sorgo
    "costo_secada_punto_usd": 2.50,     # Costo estimado de secada por punto porcentual por Tn en USD
    "spread_futuro_min_usd": 4.0,       # Brecha mínima de futuro para sugerir cobertura/pase
    "lluvia_critica_mm": 10.0,          # Umbral de precipitación para pérdida de piso
    "viento_limite_pulverizacion": 15.0, # Umbral máximo de viento para pulverización
}


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _fmt_ar(val: float, decimales: int = 2) -> str:
    val_str = f"{val:,.{decimales}f}"
    return val_str.replace(",", "X").replace(".", ",").replace("X", ".")


def evaluar_motor_decisiones(
    contexto: Dict[str, Any],
    policy: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Evalúa determinísticamente las variables climáticas, comerciales y operativas
    de un cultivo/campo y produce observaciones explicables y accionables.

    Args:
        contexto: Diccionario con la siguiente estructura de entradas:
            {
                "cultivo": str ("maiz", "soja", "sorgo"),
                "precio_fisico_usd": float,
                "precio_futuro_usd": float,
                "spread_futuro_usd": float,
                "humedad_grano_pct": float,
                "humedad_objetivo_pct": float (opcional),
                "costo_secada_punto_usd": float (opcional),
                "lluvia_esperada_mm": float,
                "viento_max_kmh": float,
                "temp_min_c": float,
                "alerta_viento": bool,
                "alerta_lluvia": bool,
                "alerta_helada": bool,
                "campo_nombre": str,
                "lote_nombre": str,
            }
        policy: Diccionario opcional para ajustar thresholds por defecto.

    Returns:
        List[Dict[str, Any]]: Lista de insights estructurados con formato:
            {
                "codigo": str,
                "nivel": "danger" | "warning" | "info" | "success",
                "titulo": str,
                "mensaje": str,
                "datos": dict
            }
    """
    cfg = {**DEFAULT_DECISION_POLICY, **(policy or {})}
    insights: List[Dict[str, Any]] = []

    cultivo_str = str(contexto.get("cultivo", "maiz")).lower()
    cultivo_nombre = cultivo_str.capitalize()

    # Extraer variables con fallback seguro
    p_spot_usd = _to_float(contexto.get("precio_fisico_usd"))
    p_futuro_usd = _to_float(contexto.get("precio_futuro_usd"))
    spread_usd = _to_float(contexto.get("spread_futuro_usd"))

    humedad_grano = _to_float(contexto.get("humedad_grano_pct"))
    hum_base_default = cfg.get(f"humedad_base_{cultivo_str}", 14.5)
    humedad_objetivo = _to_float(contexto.get("humedad_objetivo_pct")) or hum_base_default

    costo_punto_usd = _to_float(contexto.get("costo_secada_punto_usd")) or cfg["costo_secada_punto_usd"]

    lluvia_mm = _to_float(contexto.get("lluvia_esperada_mm"))
    viento_kmh = _to_float(contexto.get("viento_max_kmh"))
    temp_min_c = _to_float(contexto.get("temp_min_c"))

    alerta_viento = bool(contexto.get("alerta_viento"))
    alerta_lluvia = bool(contexto.get("alerta_lluvia"))
    alerta_helada = bool(contexto.get("alerta_helada"))

    # ------------------------------------------------------------------
    # REGLA 1: Humedad Alta + Ventana Seca Próxima (Caso Maíz/Grano Húmedo)
    # ------------------------------------------------------------------
    if humedad_grano > humedad_objetivo:
        exceso_puntos = round(humedad_grano - humedad_objetivo, 1)
        costo_total_secada_usd = round(exceso_puntos * costo_punto_usd, 2)
        pct_costo_secada = round((costo_total_secada_usd / p_spot_usd * 100.0), 2) if p_spot_usd > 0 else 0.0

        if lluvia_mm < cfg["lluvia_critica_mm"] and not alerta_lluvia:
            insights.append({
                "codigo": "HUMEDAD_ALTA_Y_VENTANA_SECA",
                "nivel": "warning",
                "titulo": f"{cultivo_nombre} con {_fmt_ar(humedad_grano, 1)}% de Humedad ({_fmt_ar(exceso_puntos, 1)} pts sobre base comercial)",
                "mensaje": (
                    f"El grano registra {_fmt_ar(humedad_grano, 1)}% de humedad frente al límite comercial de {_fmt_ar(humedad_objetivo, 1)}%. "
                    f"No se prevén lluvias importantes en las próximas 48-72h ({_fmt_ar(lluvia_mm, 1)} mm est.). "
                    f"Esperar secado natural en lote puede ahorrar aprox. US$ {_fmt_ar(costo_total_secada_usd)} USD/Tn en secada."
                ),
                "datos": {
                    "humedad_grano_pct": humedad_grano,
                    "humedad_objetivo_pct": humedad_objetivo,
                    "exceso_puntos": exceso_puntos,
                    "ahorro_secada_usd_tn": costo_total_secada_usd,
                    "lluvia_esperada_mm": lluvia_mm,
                },
            })

        # ------------------------------------------------------------------
        # REGLA 2: Humedad Alta + Lluvia Próxima Imminente
        # ------------------------------------------------------------------
        else:
            insights.append({
                "codigo": "HUMEDAD_ALTA_Y_LLUVIA_PROXIMA",
                "nivel": "danger",
                "titulo": f"Riesgo Operativo: Lluvia Imminente en {cultivo_nombre} Húmedo",
                "mensaje": (
                    f"El grano está en {_fmt_ar(humedad_grano, 1)}% y se prevén lluvias importantes ({_fmt_ar(lluvia_mm, 1)} mm). "
                    f"El riesgo de pérdida de piso o brotado supera el costo de secado (US$ {_fmt_ar(costo_total_secada_usd)} USD/Tn). "
                    f"Se sugiere evaluar cosecha inmediata y asumir secada."
                ),
                "datos": {
                    "humedad_grano_pct": humedad_grano,
                    "costo_secada_usd_tn": costo_total_secada_usd,
                    "lluvia_esperada_mm": lluvia_mm,
                },
            })

        # ------------------------------------------------------------------
        # REGLA 3: Impacto de Costo de Secada Elevado
        # ------------------------------------------------------------------
        if pct_costo_secada >= 3.0:
            insights.append({
                "codigo": "COSTO_SECADA_ELEVADO",
                "nivel": "info",
                "titulo": f"Impacto de Secada: {_fmt_ar(pct_costo_secada)}% del Valor de la Tonelada",
                "mensaje": (
                    f"El costo de secada estimado (US$ {_fmt_ar(costo_total_secada_usd)} USD/Tn) absorbe el "
                    f"{_fmt_ar(pct_costo_secada)}% del precio spot ($ {_fmt_ar(p_spot_usd)} USD/Tn). "
                    f"Conviene considerar la tarifa de acondicionamiento del acopio antes de entregar."
                ),
                "datos": {
                    "costo_secada_usd_tn": costo_total_secada_usd,
                    "porcentaje_sobre_spot": pct_costo_secada,
                },
            })

    # ------------------------------------------------------------------
    # REGLA 4: Pase Favorable en Mercado a Término (Futuros)
    # ------------------------------------------------------------------
    if spread_usd >= cfg["spread_futuro_min_usd"]:
        insights.append({
            "codigo": "FUTURO_FAVORABLE_PARA_FIJACION",
            "nivel": "success",
            "titulo": f"Pase de Futuros Favorable en {cultivo_nombre} (+US$ {_fmt_ar(spread_usd)} USD/Tn)",
            "mensaje": (
                f"El mercado de futuros (Matba Rofex) cotiza en US$ {_fmt_ar(p_futuro_usd)} USD/Tn, "
                f"ofreciendo una prima de +US$ {_fmt_ar(spread_usd)} USD/Tn respecto al spot ($ {_fmt_ar(p_spot_usd)} USD/Tn). "
                f"Si se difiere la entrega o venta, conviene evaluar una cobertura o contrato a fijar."
            ),
            "datos": {
                "precio_spot_usd": p_spot_usd,
                "precio_futuro_usd": p_futuro_usd,
                "spread_usd": spread_usd,
            },
        })

    # ------------------------------------------------------------------
    # REGLA 5: Alerta de Pérdida de Piso por Precipitaciones
    # ------------------------------------------------------------------
    if lluvia_mm >= cfg["lluvia_critica_mm"] or alerta_lluvia:
        insights.append({
            "codigo": "RIESGO_DE_PISO_POR_PRECIPITACION",
            "nivel": "warning",
            "titulo": f"Precaución Logística: {_fmt_ar(lluvia_mm, 1)} mm Estimados en las Próximas 48h",
            "mensaje": (
                f"Se pronostican precipitaciones significativas. Puede comprometerse la transitabilidad "
                f"de caminos rurales y el ingreso de cosechadoras y camiones al lote."
            ),
            "datos": {
                "lluvia_mm": lluvia_mm,
            },
        })

    # ------------------------------------------------------------------
    # REGLA 6: Alerta de Ventana de Pulverización o Helada 72h
    # ------------------------------------------------------------------
    if alerta_viento or viento_kmh > cfg["viento_limite_pulverizacion"]:
        insights.append({
            "codigo": "ALERTA_PULVERIZACION_VIENTO",
            "nivel": "info",
            "titulo": f"Ventana de Trabajo: Viento de {_fmt_ar(viento_kmh, 1)} km/h",
            "mensaje": (
                f"Viento por encima de los {_fmt_ar(cfg['viento_limite_pulverizacion'], 0)} km/h recomendados. "
                f"Monitorear horarios matutinos o vespertinos para aplicar fitosanitarios."
            ),
            "datos": {
                "viento_kmh": viento_kmh,
            },
        })

    return insights
