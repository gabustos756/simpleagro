"""
Motor de Reglas Formales e Insights Interpretativos del Agente Comercial (EduAgro).

Este módulo evalúa determinísticamente el diccionario de posición comercial
generado por `app.services.comercial.calcular_posicion_comercial` y produce una lista
de insights estructurados, trazables y explicables para el productor.
"""

from decimal import Decimal
from typing import Dict, List, Any, Optional

# Thresholds por defecto parametrizables para productores en Argentina
DEFAULT_POLICY_THRESHOLDS = {
    "cobertura_baja_max": 25.0,        # Cobertura < 25% => COBERTURA_BAJA
    "cobertura_alta_min": 60.0,        # Cobertura > 60% => COBERTURA_ALTA
    "exposicion_a_fijar_pct_min": 15.0, # Tn A Fijar / Producción Total > 15% => EXPOSICION_A_FIJAR_ELEVADA
    "compromisos_pct_min": 30.0,       # Tn Comprometidas / Producción Total > 30% => CARGA_COMPROMISOS_ELEVADA
    "silo_bolsa_pct_min": 70.0,        # Stock Silo Bolsa / Stock Total > 70% => CONCENTRACION_SILO_BOLSA
    "valorizacion_min_usd": 10000.0,   # Valorización Stock Libre >= $10.000 USD => VALORIZACION_STOCK_LIBRE
}


def _to_float(val: Any) -> float:
    """Convierte de forma segura Decimal, int, float o str a float."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _fmt_ar(val: float, decimales: int = 2) -> str:
    """Formatea un flotante a notación argentina (puntos miles, coma decimales)."""
    val_str = f"{val:,.{decimales}f}"
    return val_str.replace(",", "X").replace(".", ",").replace("X", ".")


def evaluar_insights_comerciales(
    posicion: Dict[str, Any],
    policy: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Evalúa una posición comercial de grano y retorna una lista de insights estructurados.
    
    Args:
        posicion: Diccionario devuelto por `calcular_posicion_comercial()`.
        policy: Diccionario opcional para sobrescribir thresholds por defecto.
        
    Returns:
        List[Dict[str, Any]]: Lista de insights estructurados con la forma:
            {
                "codigo": str,
                "nivel": "danger" | "warning" | "info" | "success",
                "titulo": str,
                "mensaje": str,
                "datos": dict
            }
    """
    thresholds = {**DEFAULT_POLICY_THRESHOLDS, **(policy or {})}
    insights: List[Dict[str, Any]] = []

    # Extraer variables con fallback seguro
    cultivo = str(posicion.get("cultivo", "grano")).capitalize()
    prod_total = _to_float(posicion.get("produccion_total_tn"))
    tn_fijo = _to_float(posicion.get("tn_vendidas_precio_fijo"))
    tn_a_fijar = _to_float(posicion.get("tn_vendidas_a_fijar"))
    tn_comp = _to_float(posicion.get("tn_comprometidas"))
    tn_libres = _to_float(posicion.get("tn_libres"))
    pct_cobertura = _to_float(posicion.get("porcentaje_cobertura"))
    
    tn_silo_bolsa = _to_float(posicion.get("tn_stock_silo_bolsa"))
    tn_stock_total = _to_float(posicion.get("tn_stock_total"))
    
    precio_mercado_usd = posicion.get("precio_mercado_usd_tn")
    valoriz_libre_usd = posicion.get("valorizacion_stock_libre_usd")
    fuente_mercado = posicion.get("fuente_precio_mercado")
    fecha_mercado = posicion.get("fecha_precio_mercado")

    precio_usd_val = _to_float(precio_mercado_usd)
    valoriz_usd_val = _to_float(valoriz_libre_usd)

    # ------------------------------------------------------------------
    # 1. REGLA: Cobertura Comercial (Baja / Media / Alta)
    # ------------------------------------------------------------------
    if prod_total > 0:
        if pct_cobertura < thresholds["cobertura_baja_max"]:
            insights.append({
                "codigo": "COBERTURA_BAJA",
                "nivel": "warning",
                "titulo": f"Cobertura Comercial Baja en {cultivo} ({_fmt_ar(pct_cobertura)}%)",
                "mensaje": (
                    f"Solo tenés el {_fmt_ar(pct_cobertura)}% de la producción de {cultivo} "
                    f"resguardado a precio fijo o compromisos ({_fmt_ar(tn_fijo + tn_comp)} Tn de {_fmt_ar(prod_total)} Tn totales). "
                    f"La mayor parte del volumen ({_fmt_ar(tn_libres)} Tn) permanece expuesto a variaciones de mercado."
                ),
                "datos": {
                    "porcentaje_cobertura": pct_cobertura,
                    "tn_cubiertas": tn_fijo + tn_comp,
                    "produccion_total_tn": prod_total,
                },
            })
        elif pct_cobertura >= thresholds["cobertura_alta_min"]:
            insights.append({
                "codigo": "COBERTURA_ALTA",
                "nivel": "success",
                "titulo": f"Cobertura Comercial Defendida en {cultivo} ({_fmt_ar(pct_cobertura)}%)",
                "mensaje": (
                    f"Tenés el {_fmt_ar(pct_cobertura)}% de la producción de {cultivo} respaldado a valor firme "
                    f"y compromisos obligatorios. Mantenés una posición protegida contra caídas severas de precio."
                ),
                "datos": {
                    "porcentaje_cobertura": pct_cobertura,
                    "tn_cubiertas": tn_fijo + tn_comp,
                },
            })
        else:
            insights.append({
                "codigo": "COBERTURA_MEDIA",
                "nivel": "info",
                "titulo": f"Cobertura Comercial Moderada en {cultivo} ({_fmt_ar(pct_cobertura)}%)",
                "mensaje": (
                    f"Tu cobertura comercial actual en {cultivo} es del {_fmt_ar(pct_cobertura)}%. "
                    f"Existe un nivel de protección aceptable, con {_fmt_ar(tn_libres)} Tn aún disponibles para captura de precio."
                ),
                "datos": {
                    "porcentaje_cobertura": pct_cobertura,
                    "tn_libres": tn_libres,
                },
            })

    # ------------------------------------------------------------------
    # 2. REGLA: Exposición por Ventas "A Fijar"
    # ------------------------------------------------------------------
    if prod_total > 0:
        pct_a_fijar = (tn_a_fijar / prod_total) * 100.0
        if pct_a_fijar >= thresholds["exposicion_a_fijar_pct_min"]:
            insights.append({
                "codigo": "EXPOSICION_A_FIJAR_ELEVADA",
                "nivel": "warning",
                "titulo": f"Exposición Significativa a Fijar Pizarra ({_fmt_ar(tn_a_fijar)} Tn)",
                "mensaje": (
                    f"Tenés {_fmt_ar(tn_a_fijar)} Tn de {cultivo} ({_fmt_ar(pct_a_fijar)}% de la cosecha) "
                    f"comprometidas o entregadas bajo contratos 'A Fijar'. Recordá monitorear la Pizarra o fijar valores "
                    f"para reducir la incertidumbre sobre este volumen."
                ),
                "datos": {
                    "tn_vendidas_a_fijar": tn_a_fijar,
                    "porcentaje_a_fijar": pct_a_fijar,
                },
            })

    # ------------------------------------------------------------------
    # 3. REGLA: Carga de Compromisos (Alquileres / Canjes de Insumos)
    # ------------------------------------------------------------------
    if prod_total > 0:
        pct_compromisos = (tn_comp / prod_total) * 100.0
        if pct_compromisos >= thresholds["compromisos_pct_min"]:
            insights.append({
                "codigo": "CARGA_COMPROMISOS_ELEVADA",
                "nivel": "info",
                "titulo": f"Retención Fija por Alquileres/Canjes ({_fmt_ar(tn_comp)} Tn)",
                "mensaje": (
                    f"Un {_fmt_ar(pct_compromisos)}% de la producción total de {cultivo} ({_fmt_ar(tn_comp)} Tn) "
                    f"está reservado para pagos obligatorios (arrendamientos en quintales o canjes de insumos). "
                    f"Este volumen no genera ingresos de caja netos adicionales."
                ),
                "datos": {
                    "tn_comprometidas": tn_comp,
                    "porcentaje_compromisos": pct_compromisos,
                },
            })

    # ------------------------------------------------------------------
    # 4. REGLA: Concentración de Almacenamiento Físico en Silo Bolsa
    # ------------------------------------------------------------------
    if tn_stock_total > 0:
        pct_silo_bolsa = (tn_silo_bolsa / tn_stock_total) * 100.0
        if pct_silo_bolsa >= thresholds["silo_bolsa_pct_min"]:
            insights.append({
                "codigo": "CONCENTRACION_SILO_BOLSA",
                "nivel": "info",
                "titulo": f"Existencias Físicas Principalmente en Silo Bolsa ({_fmt_ar(tn_silo_bolsa)} Tn)",
                "mensaje": (
                    f"El {_fmt_ar(pct_silo_bolsa)}% de tu stock de {cultivo} ({_fmt_ar(tn_silo_bolsa)} Tn) "
                    f"se encuentra embolsado en el campo. Se recomienda mantener el monitoreo periódico de hermeticidad y humedad."
                ),
                "datos": {
                    "tn_stock_silo_bolsa": tn_silo_bolsa,
                    "tn_stock_total": tn_stock_total,
                    "porcentaje_silo_bolsa": pct_silo_bolsa,
                },
            })

    # ------------------------------------------------------------------
    # 5. REGLA: Cotización de Mercado & Valorización del Stock Libre
    # ------------------------------------------------------------------
    if precio_mercado_usd is None:
        insights.append({
            "codigo": "SIN_COTIZACION_MERCADO",
            "nivel": "warning",
            "titulo": f"Sin Cotización de Mercado Vigente para {cultivo}",
            "mensaje": (
                f"No se encontró precio de referencia cargado en el sistema para {cultivo}. "
                f"Para calcular el valor estimado de las {_fmt_ar(tn_libres)} Tn libres, ingresá o actualizá la cotización de mercado."
            ),
            "datos": {
                "cultivo": cultivo,
                "tn_libres": tn_libres,
            },
        })
    else:
        if valoriz_usd_val >= thresholds["valorizacion_min_usd"]:
            insights.append({
                "codigo": "VALORIZACION_STOCK_LIBRE",
                "nivel": "success",
                "titulo": f"Stock Libre Valorizado en USD $ {_fmt_ar(valoriz_usd_val)}",
                "mensaje": (
                    f"A una cotización de referencia de $ {_fmt_ar(precio_usd_val)} USD/Tn ({fuente_mercado or 'Pizarra'}), "
                    f"tus {_fmt_ar(tn_libres)} Tn libres de {cultivo} representan un activo comercial estimado de $ {_fmt_ar(valoriz_usd_val)} USD."
                ),
                "datos": {
                    "precio_mercado_usd_tn": precio_usd_val,
                    "valorizacion_stock_libre_usd": valoriz_usd_val,
                    "tn_libres": tn_libres,
                    "fuente": fuente_mercado,
                    "fecha": fecha_mercado,
                },
            })

    return insights
