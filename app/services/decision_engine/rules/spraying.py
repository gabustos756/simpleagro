"""
Reglas del Dominio de Pulverización y Alertas de Viento (EduAgro).
"""

from typing import Dict, Set
from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import RuleTraceContext, fmt_ar
from app.services.decision_engine.calculators.spraying import evaluate_spraying_conditions


class AlertaPulverizacionVientoRule:
    code: str = "ALERTA_PULVERIZACION_VIENTO"
    domain: str = "spraying"
    priority: int = 45
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        w_status = context.weather.provider_status or "unavailable"

        viento_kmh = context.spraying.viento_actual_kmh or context.weather.wind_max_next_24h_kmh

        if viento_kmh is None and w_status == "unavailable":
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["wind_speed_kmh"],
            )

        if viento_kmh is None:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["wind_speed_kmh"],
            )

        limite_viento = float(policy.get(
            "pulverizacion.viento_maximo_kmh",
            EffectivePolicyValue(value=15.0, source_scope="system_base"),
        ).value)

        v_ideal_min = float(policy.get(
            "pulverizacion.viento_ideal_min_kmh",
            EffectivePolicyValue(value=5.0, source_scope="system_base"),
        ).value)

        v_ideal_max = float(policy.get(
            "pulverizacion.viento_ideal_max_kmh",
            EffectivePolicyValue(value=10.0, source_scope="system_base"),
        ).value)

        spraying_res = evaluate_spraying_conditions(
            wind_speed_kmh=viento_kmh,
            wind_gust_kmh=context.spraying.viento_rafagas_kmh or context.weather.wind_gust_max_next_24h_kmh,
            wind_ideal_min_kmh=v_ideal_min,
            wind_ideal_max_kmh=v_ideal_max,
            wind_max_limit_kmh=limite_viento,
            relative_humidity_pct=context.spraying.humedad_relativa_pct,
            temperature_c=context.spraying.temperatura_c,
        )

        if spraying_res.status == "optimal":
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["wind_speed_kmh"],
            )

        nivel = "danger" if spraying_res.status == "danger" else "info"

        insight = DecisionInsight(
            codigo=self.code,
            nivel=nivel,
            titulo=f"Ventana de Aplicación: Viento de {fmt_ar(viento_kmh, 1)} km/h",
            mensaje=(
                f"La velocidad de viento calculada ({fmt_ar(viento_kmh, 1)} km/h) se encuentra fuera del rango óptimo recomendación ({fmt_ar(v_ideal_min, 0)}-{fmt_ar(v_ideal_max, 0)} km/h). "
                f"La evaluación completa de aplicación requiere verificar ráfagas, humedad relativa, temperatura, dirección del viento, inversión térmica y receptores sensibles. "
                f"Se recomienda verificar condiciones en campo antes de aplicar."
            ),
            datos={
                "viento_kmh": viento_kmh,
                "viento_limite_kmh": limite_viento,
                "status_pulverizacion": spraying_res.status,
                "missing_spraying_inputs": spraying_res.missing_inputs,
                "provider_status": w_status,
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Medir viento e inversión térmica con anemómetro manual en lote previo a cargar la pulverizadora.",
            confidence="medium",
            reason_codes=["SUBOPTIMAL_SPRAYING_WIND"],
            inputs_used=["wind_speed_kmh"],
            missing_inputs=spraying_res.missing_inputs,
        )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            inputs_used=["wind_speed_kmh"],
            missing_inputs=spraying_res.missing_inputs,
        )
