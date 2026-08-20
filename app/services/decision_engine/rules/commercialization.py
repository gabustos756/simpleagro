"""
Reglas del Dominio de Comercialización y Futuros (EduAgro).
"""

from typing import Dict, Set, List
from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import RuleTraceContext, fmt_ar
from app.services.decision_engine.calculators.commercial import evaluate_commercial_carry


class FuturoFavorableFijacionRule:
    code: str = "FUTURO_FAVORABLE_PARA_FIJACION"
    domain: str = "commercialization"
    priority: int = 50
    required_inputs: Set[str] = {"precio_spot_usd", "precio_futuro_usd"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        cultivo = context.cultivo or "grano"
        p_spot = context.market.precio_spot_usd
        p_futuro = context.market.precio_futuro_usd

        if p_spot is None or p_futuro is None:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["precio_spot_usd", "precio_futuro_usd"],
            )

        min_spread = float(policy.get(
            "comercializacion.spread_futuro_min_usd_legacy",
            EffectivePolicyValue(value=4.0, source_scope="system_base"),
        ).value)

        carry_res = evaluate_commercial_carry(
            spot_price_usd_tn=p_spot,
            future_price_usd_tn=p_futuro,
            storage_cost_per_month_usd_tn=context.market.costo_almacenaje_mes_usd_tn,
            monthly_interest_rate_pct=context.market.tasa_interes_mensual_pct,
        )

        spread = carry_res.spread_bruto_usd_tn or round(p_futuro - p_spot, 2)

        if spread < min_spread:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["precio_spot_usd", "precio_futuro_usd"],
            )

        mensaje_base = (
            f"El mercado de futuros (Matba Rofex) cotiza en US$ {fmt_ar(p_futuro)} USD/Tn, "
            f"ofreciendo una prima bruta de +US$ {fmt_ar(spread)} USD/Tn respecto al spot (US$ {fmt_ar(p_spot)} USD/Tn). "
            f"El pase bruto es favorable, pero la conveniencia neta depende de costos financieros, almacenaje, seguro, merma, flete, calidad y estrategia comercial."
        )

        insight = DecisionInsight(
            codigo=self.code,
            nivel="success",
            titulo=f"Pase de Futuros Favorable en {cultivo.capitalize()} (+US$ {fmt_ar(spread)} USD/Tn)",
            mensaje=mensaje_base,
            datos={
                "precio_spot_usd": p_spot,
                "precio_futuro_usd": p_futuro,
                "spread_usd": spread,
                "carry_neto_estimado_usd_tn": carry_res.carry_neto_estimado_usd_tn,
                "evaluacion_financiera_completa": carry_res.is_fully_evaluated,
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Analizar costo financiero de inmovilización de granos y consultar asesor comercial antes de operar.",
            confidence="high" if carry_res.is_fully_evaluated else "medium",
            reason_codes=["POSITIVE_FUTURE_SPREAD"],
            inputs_used=["precio_spot_usd", "precio_futuro_usd"],
            tradeoffs={
                "ventaja": "Fijación de valor superior al disponible actual.",
                "riesgo": "Costo de oportunidad financiero y gasto de acopio/merma si se difiere la entrega.",
            },
            disclaimer="Análisis determinístico de precios de referencia. No constituye una recomendación financiera o comercial vinculante.",
        )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            inputs_used=["precio_spot_usd", "precio_futuro_usd"],
        )
