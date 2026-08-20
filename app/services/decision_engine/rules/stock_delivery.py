"""
Reglas Determinísticas Puras de Dominio de Despachos y Conciliación de Pesajes (Stock 1C).
Maneja evaluación de asignación suficiente, despacho físico confirmado, diferencia de pesaje y resolución.
"""

from typing import Dict, Set, Optional, List
from decimal import Decimal

from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import DecisionRule, RuleTraceContext, fmt_ar


class RuleDespachoSinAsignacionSuficiente:
    """Regla: Advierte si el peso neto de origen supera el total asignado activo disponible para la entrega."""
    code = "DESPACHO_SIN_ASIGNACION_SUFICIENTE"
    domain = "stock_delivery"
    priority = 10
    required_inputs: Set[str] = {"delivery_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        deliv_ctx = getattr(context, "delivery_context", None) or {}
        peso_origen_kg = deliv_ctx.get("peso_neto_origen_kg", 0.0) or 0.0
        asignado_activo_kg = deliv_ctx.get("toneladas_asignadas_activas_kg", 0.0) or 0.0

        fired = False
        insight_res = None

        if peso_origen_kg > 0 and asignado_activo_kg < peso_origen_kg:
            fired = True
            falta_tn = (peso_origen_kg - asignado_activo_kg) / 1000.0
            insight_res = DecisionInsight(
                codigo=self.code,
                domain=self.domain,
                nivel="danger",
                titulo="Asignación de stock insuficiente para despacho",
                mensaje=(
                    f"El peso neto de origen ({fmt_ar(peso_origen_kg / 1000.0)} Tn) supera la asignación "
                    f"activa disponible ({fmt_ar(asignado_activo_kg / 1000.0)} Tn). "
                    f"Faltan asignación previa de {fmt_ar(falta_tn)} Tn."
                ),
                accion_recomendada="Asignar partida física a la entrega antes de confirmar el despacho.",
                datos={"peso_origen_kg": peso_origen_kg, "asignado_activo_kg": asignado_activo_kg},
            )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleDespachoConfirmado:
    """Regla: Informa la salida física de stock registrada e inmutable por despacho de la entrega."""
    code = "DESPACHO_CONFIRMADO"
    domain = "stock_delivery"
    priority = 20
    required_inputs: Set[str] = {"delivery_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        deliv_ctx = getattr(context, "delivery_context", None) or {}
        is_despachada = deliv_ctx.get("is_despachada", False)
        despachado_tn = deliv_ctx.get("despachado_tn", 0.0) or 0.0

        fired = is_despachada
        insight_res = None

        if fired:
            insight_res = DecisionInsight(
                codigo=self.code,
                domain=self.domain,
                nivel="info",
                titulo="Despacho físico de stock confirmado",
                mensaje=f"Se registró la salida física de {fmt_ar(despachado_tn)} Tn de stock asociada a esta entrega.",
                accion_recomendada="Verificar arribo y pesaje de recepción en destino.",
                datos={"despachado_tn": despachado_tn},
            )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleRecepcionConDiferenciaDePesaje:
    """Regla: Advierte cuando la diferencia de balanza entre origen y destino supera la tolerancia de política."""
    code = "RECEPCION_CON_DIFERENCIA_DE_PESAJE"
    domain = "stock_delivery"
    priority = 30
    required_inputs: Set[str] = {"delivery_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        deliv_ctx = getattr(context, "delivery_context", None) or {}
        dif_pct = deliv_ctx.get("diferencia_pct", None)
        dif_kg = deliv_ctx.get("diferencia_kg", None)

        pol_pct = policy.get("stock_delivery.weight_difference_review_pct")
        pol_kg = policy.get("stock_delivery.weight_difference_review_kg")
        threshold_pct = pol_pct.value if pol_pct else 1.0
        threshold_kg = pol_kg.value if pol_kg else 300

        fired = False
        insight_res = None

        if dif_pct is not None and dif_kg is not None:
            abs_pct = abs(dif_pct)
            abs_kg = abs(dif_kg)
            if abs_pct > threshold_pct and abs_kg > threshold_kg:
                fired = True
                insight_res = DecisionInsight(
                    codigo=self.code,
                    domain=self.domain,
                    nivel="warning",
                    titulo="Diferencia de pesaje a revisar en recepción",
                    mensaje=(
                        f"La diferencia entre origen y destino es de {fmt_ar(dif_kg)} kg ({fmt_ar(dif_pct)}%), "
                        f"superando el umbral de revisión ({threshold_pct}% / {threshold_kg} kg)."
                    ),
                    accion_recomendada="Resolver explícitamente el caso de conciliación (aceptar sin ajuste o registrar ajuste).",
                    datos={"diferencia_kg": dif_kg, "diferencia_pct": dif_pct},
                )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleDiferenciaDePesajeDentroDeTolerancia:
    """Regla: Informa que la diferencia de balanza se encuentra dentro de la tolerancia de política."""
    code = "DIFERENCIA_DE_PESAJE_DENTRO_DE_TOLERANCIA"
    domain = "stock_delivery"
    priority = 40
    required_inputs: Set[str] = {"delivery_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        deliv_ctx = getattr(context, "delivery_context", None) or {}
        dif_pct = deliv_ctx.get("diferencia_pct", None)
        dif_kg = deliv_ctx.get("diferencia_kg", None)

        pol_pct = policy.get("stock_delivery.weight_difference_review_pct")
        pol_kg = policy.get("stock_delivery.weight_difference_review_kg")
        threshold_pct = pol_pct.value if pol_pct else 1.0
        threshold_kg = pol_kg.value if pol_kg else 300

        fired = False
        insight_res = None

        if dif_pct is not None and dif_kg is not None:
            abs_pct = abs(dif_pct)
            abs_kg = abs(dif_kg)
            if abs_pct <= threshold_pct or abs_kg <= threshold_kg:
                fired = True
                insight_res = DecisionInsight(
                    codigo=self.code,
                    domain=self.domain,
                    nivel="info",
                    titulo="Diferencia de pesaje dentro de tolerancia",
                    mensaje=f"La diferencia de pesaje ({fmt_ar(dif_kg)} kg / {fmt_ar(dif_pct)}%) se encuentra dentro del rango aceptable.",
                    accion_recomendada="No requiere acción adicional.",
                    datos={"diferencia_kg": dif_kg, "diferencia_pct": dif_pct},
                )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleDiferenciaDePesajePendienteDeResolucion:
    """Regla: Advierte que existe un caso de conciliación de pesaje pendiente de resolución explícita."""
    code = "DIFERENCIA_DE_PESAJE_PENDIENTE_DE_RESOLUCION"
    domain = "stock_delivery"
    priority = 50
    required_inputs: Set[str] = {"delivery_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        deliv_ctx = getattr(context, "delivery_context", None) or {}
        has_pending = deliv_ctx.get("has_pending_reconciliation", False)

        fired = has_pending
        insight_res = None

        if fired:
            insight_res = DecisionInsight(
                codigo=self.code,
                domain=self.domain,
                nivel="warning",
                titulo="Conciliación de pesaje pendiente de resolución",
                mensaje="La entrega posee un caso de diferencia de pesaje pendiente de resolución por parte del usuario.",
                accion_recomendada="Ingresar a la entrega y ejecutar la resolución explícita correspondiente.",
                datos={},
            )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleEntregaDespachadaSinPesoDestino:
    """Regla: Informa que el despacho fue realizado pero aún se aguarda el pesaje de balanza en destino."""
    code = "ENTREGA_DESPACHADA_SIN_PESO_DESTINO"
    domain = "stock_delivery"
    priority = 60
    required_inputs: Set[str] = {"delivery_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        deliv_ctx = getattr(context, "delivery_context", None) or {}
        is_despachada = deliv_ctx.get("is_despachada", False)
        has_destino_weight = deliv_ctx.get("has_peso_destino", False)

        fired = is_despachada and not has_destino_weight
        insight_res = None

        if fired:
            insight_res = DecisionInsight(
                codigo=self.code,
                domain=self.domain,
                nivel="info",
                titulo="Despacho en tránsito sin peso recibido en destino",
                mensaje="El stock físico ya fue descontado por despacho de origen. Falta cargar el pesaje recibido en destino.",
                accion_recomendada="Cargar el peso de recepción en la carta de porte al recibir la balanza de destino.",
                datos={},
            )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleAsignacionDespachada:
    """Regla: Informa que la asignación de stock fue consumida por despacho."""
    code = "ASIGNACION_DESPACHADA"
    domain = "stock_delivery"
    priority = 70
    required_inputs: Set[str] = {"delivery_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        deliv_ctx = getattr(context, "delivery_context", None) or {}
        asig_despachada_tn = deliv_ctx.get("toneladas_asignadas_despachadas_tn", 0.0) or 0.0

        fired = asig_despachada_tn > 0
        insight_res = None

        if fired:
            insight_res = DecisionInsight(
                codigo=self.code,
                domain=self.domain,
                nivel="info",
                titulo="Asignación convertida en despacho físico",
                mensaje=f"Se consumieron {fmt_ar(asig_despachada_tn)} Tn de asignación operativa convertidas en salida física.",
                accion_recomendada="Verificar saldo físico actualizado de la partida.",
                datos={"toneladas_despachadas_tn": asig_despachada_tn},
            )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


def get_stock_delivery_rules() -> List[DecisionRule]:
    """Retorna todas las reglas determinísticas de despachos y pesajes de stock."""
    return [
        RuleDespachoSinAsignacionSuficiente(),
        RuleDespachoConfirmado(),
        RuleRecepcionConDiferenciaDePesaje(),
        RuleDiferenciaDePesajeDentroDeTolerancia(),
        RuleDiferenciaDePesajePendienteDeResolucion(),
        RuleEntregaDespachadaSinPesoDestino(),
        RuleAsignacionDespachada(),
    ]
