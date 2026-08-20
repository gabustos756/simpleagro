"""
Reglas Determinísticas Puras de Dominio de Stock V1 & Stock Comercial 1B.
Maneja reglas para disponibilidad de partidas, reservas por compromisos y asignaciones a entregas.
"""

from typing import Dict, Set, Optional, List

from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import DecisionRule, RuleTraceContext, fmt_ar


class RuleStockPartidaSinDisponibilidad:
    """Regla: Advierte cuando una partida física tiene disponibilidad cero o agotada pero aún conserva stock físico u operaciones."""
    code = "STOCK_PARTIDA_SIN_DISPONIBILIDAD"
    domain = "stock"
    priority = 20
    required_inputs: Set[str] = {"stock_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        st_ctx = getattr(context, "stock_context", None) or {}
        fired = False
        insight_res = None

        for p in st_ctx.get("partidas", []):
            dispon_tn = p.get("stock_disponible_tn", 0.0)
            fisico_tn = p.get("stock_fisico_tn", 0.0)
            tracking = p.get("tracking_number", "N/D")

            if dispon_tn <= 0 and fisico_tn > 0:
                fired = True
                insight_res = DecisionInsight(
                    codigo=self.code,
                    domain=self.domain,
                    nivel="warning",
                    titulo=f"Partida {tracking} sin disponibilidad libre",
                    mensaje=(
                        f"La partida {tracking} cuenta con {fmt_ar(fisico_tn)} Tn físicas pero 0 Tn disponibles libres "
                        f"(sus existencias están reservadas o asignadas a entregas)."
                    ),
                    accion_recomendada="Verificar si se pueden liberar reservas no utilizadas o reasignar existencias.",
                    datos={"tracking_number": tracking, "fisico_tn": fisico_tn, "disponible_tn": dispon_tn},
                )
                break

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleCompromisoSinCoberturaSuficiente:
    """Regla: Informa cuando las reservas activas para un compromiso comercial resultan inferiores a sus toneladas requeridas."""
    code = "COMPROMISO_SIN_COBERTURA_SUFICIENTE"
    domain = "stock"
    priority = 30
    required_inputs: Set[str] = {"stock_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        st_ctx = getattr(context, "stock_context", None) or {}
        fired = False
        insight_res = None

        for c in st_ctx.get("compromisos", []):
            req_tn = c.get("toneladas_requeridas", 0.0)
            res_tn = c.get("toneladas_reservadas", 0.0)
            pend_tn = c.get("toneladas_pendientes", 0.0)
            concepto = c.get("concepto", "Compromiso")

            if req_tn > 0 and res_tn < req_tn:
                fired = True
                insight_res = DecisionInsight(
                    codigo=self.code,
                    domain=self.domain,
                    nivel="info",
                    titulo=f"Compromiso '{concepto}' con cobertura parcial",
                    mensaje=(
                        f"El compromiso requiere {fmt_ar(req_tn)} Tn pero sólo cuenta con {fmt_ar(res_tn)} Tn reservadas. "
                        f"Falta reservar {fmt_ar(pend_tn)} Tn."
                    ),
                    accion_recomendada="Vincular partidas físicas libres usando 'Reservar para compromiso'.",
                    datos={"concepto": concepto, "requeridas_tn": req_tn, "reservadas_tn": res_tn, "pendientes_tn": pend_tn},
                )
                break

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleEntregaSinStockAsignado:
    """Regla: Advierte cuando una entrega planificada no cuenta con partidas físicas asignadas."""
    code = "ENTREGA_SIN_STOCK_ASIGNADO"
    domain = "stock"
    priority = 25
    required_inputs: Set[str] = {"stock_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        st_ctx = getattr(context, "stock_context", None) or {}
        fired = False
        insight_res = None

        for d in st_ctx.get("deliveries", []):
            plan_tn = d.get("toneladas_planificadas", 0.0)
            asig_tn = d.get("toneladas_asignadas", 0.0)
            tracking = d.get("tracking_number", "N/D")

            if plan_tn > 0 and asig_tn < plan_tn:
                fired = True
                diff_tn = plan_tn - asig_tn
                insight_res = DecisionInsight(
                    codigo=self.code,
                    domain=self.domain,
                    nivel="warning",
                    titulo=f"Entrega {tracking} sin asignación completa",
                    mensaje=(
                        f"La entrega {tracking} posee {fmt_ar(plan_tn)} Tn planificadas pero sólo {fmt_ar(asig_tn)} Tn asignadas. "
                        f"Pendiente de asignar: {fmt_ar(diff_tn)} Tn."
                    ),
                    accion_recomendada="Asignar una o más partidas físicas antes del despacho.",
                    datos={"tracking_number": tracking, "planificadas_tn": plan_tn, "asignadas_tn": asig_tn},
                )
                break

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


class RuleEntregaAsignadaPorEncimaDePlan:
    """Regla: Advierte cuando el total asignado de partidas supera las toneladas planificadas de una entrega."""
    code = "ENTREGA_ASIGNADA_POR_ENCIMA_DE_PLAN"
    domain = "stock"
    priority = 20
    required_inputs: Set[str] = {"stock_context"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        st_ctx = getattr(context, "stock_context", None) or {}
        fired = False
        insight_res = None

        for d in st_ctx.get("deliveries", []):
            plan_tn = d.get("toneladas_planificadas", 0.0)
            asig_tn = d.get("toneladas_asignadas", 0.0)
            tracking = d.get("tracking_number", "N/D")

            if plan_tn > 0 and asig_tn > plan_tn:
                fired = True
                exceso_tn = asig_tn - plan_tn
                insight_res = DecisionInsight(
                    codigo=self.code,
                    domain=self.domain,
                    nivel="info",
                    titulo=f"Entrega {tracking} supera plan de carga",
                    mensaje=(
                        f"La entrega {tracking} tiene {fmt_ar(asig_tn)} Tn asignadas, superando en {fmt_ar(exceso_tn)} Tn "
                        f"las toneladas planificadas ({fmt_ar(plan_tn)} Tn)."
                    ),
                    accion_recomendada="Revisar la capacidad de transporte o ajustar el plan de entrega.",
                    datos={"tracking_number": tracking, "planificadas_tn": plan_tn, "asignadas_tn": asig_tn},
                )
                break

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered" if fired else "not_triggered",
            insight=insight_res,
        )


def get_stock_rules() -> List[DecisionRule]:
    """Retorna todas las reglas determinísticas del dominio de stock."""
    return [
        RuleStockPartidaSinDisponibilidad(),
        RuleCompromisoSinCoberturaSuficiente(),
        RuleEntregaSinStockAsignado(),
        RuleEntregaAsignadaPorEncimaDePlan(),
    ]
