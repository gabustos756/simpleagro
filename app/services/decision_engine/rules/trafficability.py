"""
Reglas del Dominio de Transitabilidad y Riesgo de Piso (EduAgro).
"""

from typing import Dict, Set
from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import RuleTraceContext, fmt_ar
from app.services.decision_engine.calculators.trafficability import evaluate_trafficability


class RiesgoPisoPrecipitacionRule:
    code: str = "RIESGO_DE_PISO_POR_PRECIPITACION"
    domain: str = "trafficability"
    priority: int = 35
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        w_status = context.weather.provider_status or "unavailable"

        if w_status == "unavailable":
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["weather_forecast"],
            )

        p24 = context.weather.precipitation_next_24h_mm
        p72 = context.weather.precipitation_next_72h_mm
        thresh = float(policy.get(
            "cosecha.lluvia_critica_72h_mm",
            EffectivePolicyValue(value=10.0, source_scope="system_base"),
        ).value)

        traff_res = evaluate_trafficability(
            precip_24h_mm=p24,
            precip_72h_mm=p72,
            critical_threshold_mm=thresh,
            road_condition=context.logistics.estado_caminos,
        )

        if not traff_res.is_evaluated or traff_res.risk_level in ("low", None):
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["precipitation_next_72h_mm"],
            )

        lluvia_eval = p72 if p72 is not None else (p24 or 0.0)

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning" if traff_res.risk_level == "medium" else "danger",
            titulo=f"Precaución Logística: {fmt_ar(lluvia_eval, 1)} mm Estimados en las Próximas 72h",
            mensaje=(
                f"Se pronostican precipitaciones acumuladas de {fmt_ar(lluvia_eval, 1)} mm en 72h (Fuente: {context.weather.provider or 'Meteo V2'}). "
                f"Puede comprometerse la transitabilidad de caminos rurales y el ingreso de cosechadoras y camiones al lote."
            ),
            datos={
                "lluvia_mm": lluvia_eval,
                "precip_24h_mm": p24,
                "precip_72h_mm": p72,
                "riesgo_piso": traff_res.risk_level,
                "provider": context.weather.provider,
                "provider_status": context.weather.provider_status,
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Verificar estado de caminos rurales y coordinar logística de retiro previa a la lluvia.",
            confidence="high" if w_status == "live" else "medium",
            reason_codes=["PRECIPITATION_SOIL_RISK"],
            inputs_used=["precipitation_next_72h_mm"],
        )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            inputs_used=["precipitation_next_72h_mm"],
        )
