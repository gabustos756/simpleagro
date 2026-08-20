"""
Reglas del Dominio de Heladas y Riesgo Térmico (EduAgro).
"""

from typing import Dict, Set
from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import RuleTraceContext, fmt_ar


class RiesgoTermicoAVerificarRule:
    code: str = "RIESGO_TERMICO_A_VERIFICAR"
    domain: str = "frost"
    priority: int = 60
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        temp_min = context.weather.temp_min_next_72h_c
        w_status = context.weather.provider_status or "unavailable"

        if temp_min is None and w_status == "unavailable":
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["temp_min_next_72h_c"],
            )

        if temp_min is None:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["temp_min_next_72h_c"],
            )

        umbral = float(policy.get(
            "helada.umbral_temperatura_minima_c",
            EffectivePolicyValue(value=4.0, source_scope="system_base"),
        ).value)

        if temp_min > umbral:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["temp_min_next_72h_c"],
            )

        cultivo = context.cultivo or "cultivo"

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning" if temp_min > 0.0 else "danger",
            titulo=f"Riesgo Térmico Nocturno: {fmt_ar(temp_min, 1)} °C Previstos",
            mensaje=(
                f"Se proyecta un descenso de temperatura mínima a {fmt_ar(temp_min, 1)} °C en las próximas 72h. "
                f"La susceptibilidad del {cultivo} depende del cultivo, estado fenológico, duración de la exposición, topografía y condición local."
            ),
            datos={
                "temp_min_c": temp_min,
                "umbral_alerta_c": umbral,
                "provider": context.weather.provider,
                "provider_status": w_status,
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Inspeccionar bajíos y estaciones agrometeorológicas locales para determinar impacto real.",
            confidence="high" if w_status == "live" else "medium",
            reason_codes=["LOW_TEMPERATURE_RISK"],
            inputs_used=["temp_min_next_72h_c"],
            disclaimer="Diagnóstico agrometeorológico preventivo; validar estado de desarrollo del cultivo en lote.",
        )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            inputs_used=["temp_min_next_72h_c"],
        )
