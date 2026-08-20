"""
Reglas del Dominio de Cosecha y Secado de Grano (EduAgro).
"""

from typing import Dict, Set, List
from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import RuleTraceContext, fmt_ar
from app.services.decision_engine.calculators.drying import calculate_drying_cost


class HumedadAltaVentanaSecaRule:
    code: str = "HUMEDAD_ALTA_Y_VENTANA_SECA"
    domain: str = "harvest"
    priority: int = 30
    required_inputs: Set[str] = {"cultivo", "humedad_grano_pct"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        cultivo = context.cultivo or "maiz"
        humedad_grano = context.harvest.humedad_grano_pct

        if humedad_grano is None:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["humedad_grano_pct"],
            )

        # Obtener base comercial desde la política efectiva
        bases_map = policy.get(
            "cosecha.humedad_comercial_base_por_cultivo",
            EffectivePolicyValue(value={"maiz": 14.5, "soja": 13.5, "sorgo": 15.0, "trigo": 14.0}, source_scope="system_base"),
        ).value

        hum_base = float(bases_map.get(cultivo, 14.5)) if isinstance(bases_map, dict) else 14.5
        costo_punto = float(policy.get("cosecha.costo_secada_punto_usd", EffectivePolicyValue(value=2.50, source_scope="system_base")).value)
        p_spot = context.market.precio_spot_usd

        drying_res = calculate_drying_cost(
            grain_moisture_pct=humedad_grano,
            commercial_base_moisture_pct=hum_base,
            drying_cost_per_point_usd_tn=costo_punto,
            spot_price_usd_tn=p_spot,
        )

        if not drying_res.is_evaluated or (drying_res.excess_moisture_points or 0.0) <= 0.0:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["humedad_grano_pct"],
            )

        # Verificar condición de lluvia a 72h
        p72 = context.weather.precipitation_next_72h_mm
        w_status = context.weather.provider_status or "unavailable"

        if p72 is None and w_status == "unavailable":
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["precipitation_next_72h_mm"],
            )

        lluvia_mm = p72 if p72 is not None else 0.0
        crit_threshold = float(policy.get("cosecha.lluvia_critica_72h_mm", EffectivePolicyValue(value=10.0, source_scope="system_base")).value)

        if lluvia_mm >= crit_threshold:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["precipitation_next_72h_mm"],
            )

        exceso = drying_res.excess_moisture_points
        costo_total = drying_res.total_drying_cost_usd_tn

        conf = "high"
        if w_status == "stale_cached" or context.weather.disagreement_level in ("medium", "high"):
            conf = "medium"

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning",
            titulo=f"{cultivo.capitalize()} con {fmt_ar(humedad_grano, 1)}% de Humedad ({fmt_ar(exceso, 1)} pts sobre base comercial)",
            mensaje=(
                f"El grano registra {fmt_ar(humedad_grano, 1)}% de humedad frente a la base comercial de {fmt_ar(hum_base, 1)}%. "
                f"No se prevén lluvias significativas a 72h ({fmt_ar(lluvia_mm, 1)} mm est.). "
                f"Existe potencial de ahorro de secada (aprox. US$ {fmt_ar(costo_total)} USD/Tn) si se confirma bajo riesgo de demora, calidad, vuelco, desgrane, piso y logística."
            ),
            datos={
                "humedad_grano_pct": humedad_grano,
                "humedad_objetivo_pct": hum_base,
                "exceso_puntos": exceso,
                "ahorro_secada_usd_tn": costo_total,
                "lluvia_esperada_mm": lluvia_mm,
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Monitorear humedad del lote y verificar pronóstico local antes de coordinar cosechadora.",
            confidence=conf,
            reason_codes=["HIGH_GRAIN_MOISTURE", "DRY_WEATHER_WINDOW"],
            inputs_used=["humedad_grano_pct", "precipitation_next_72h_mm"],
            disclaimer="Recomendación de apoyo a decisión; validar condición real de lote, maquinaria, destino y asesoramiento profesional.",
        )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            inputs_used=["humedad_grano_pct", "precipitation_next_72h_mm"],
        )


class HumedadAltaLluviaProximaRule:
    code: str = "HUMEDAD_ALTA_Y_LLUVIA_PROXIMA"
    domain: str = "harvest"
    priority: int = 25
    required_inputs: Set[str] = {"cultivo", "humedad_grano_pct"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        cultivo = context.cultivo or "maiz"
        humedad_grano = context.harvest.humedad_grano_pct

        if humedad_grano is None:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["humedad_grano_pct"],
            )

        bases_map = policy.get(
            "cosecha.humedad_comercial_base_por_cultivo",
            EffectivePolicyValue(value={"maiz": 14.5, "soja": 13.5, "sorgo": 15.0, "trigo": 14.0}, source_scope="system_base"),
        ).value
        hum_base = float(bases_map.get(cultivo, 14.5)) if isinstance(bases_map, dict) else 14.5
        costo_punto = float(policy.get("cosecha.costo_secada_punto_usd", EffectivePolicyValue(value=2.50, source_scope="system_base")).value)

        drying_res = calculate_drying_cost(
            grain_moisture_pct=humedad_grano,
            commercial_base_moisture_pct=hum_base,
            drying_cost_per_point_usd_tn=costo_punto,
            spot_price_usd_tn=context.market.precio_spot_usd,
        )

        if not drying_res.is_evaluated or (drying_res.excess_moisture_points or 0.0) <= 0.0:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["humedad_grano_pct"],
            )

        p72 = context.weather.precipitation_next_72h_mm
        crit_threshold = float(policy.get("cosecha.lluvia_critica_72h_mm", EffectivePolicyValue(value=10.0, source_scope="system_base")).value)

        if p72 is None or p72 < crit_threshold:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["precipitation_next_72h_mm"],
            )

        costo_total = drying_res.total_drying_cost_usd_tn

        insight = DecisionInsight(
            codigo=self.code,
            nivel="danger",
            titulo=f"Riesgo Operativo: Lluvia Imminente en {cultivo.capitalize()} Húmedo",
            mensaje=(
                f"El grano está en {fmt_ar(humedad_grano, 1)}% de humedad y se prevén precipitaciones importantes ({fmt_ar(p72, 1)} mm en 72h). "
                f"El riesgo de pérdida de piso, brotado o deterioro de calidad puede superar el costo estimado de secado (US$ {fmt_ar(costo_total)} USD/Tn). "
                f"Se sugiere evaluar la oportunidad de cosecha inmediata asumiendo el acondicionamiento."
            ),
            datos={
                "humedad_grano_pct": humedad_grano,
                "costo_secada_usd_tn": costo_total,
                "lluvia_esperada_mm": p72,
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Evaluar disponibilidad de maquinaria y capacidad de recepción en acopio/secadora.",
            confidence="high" if context.weather.provider_status == "live" else "medium",
            reason_codes=["HIGH_GRAIN_MOISTURE", "IMMINENT_RAINFALL"],
            inputs_used=["humedad_grano_pct", "precipitation_next_72h_mm"],
            disclaimer="Recomendación de apoyo a decisión; validar condición real de lote, maquinaria, destino y asesoramiento profesional.",
        )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            inputs_used=["humedad_grano_pct", "precipitation_next_72h_mm"],
        )


class CostoSecadaElevadoRule:
    code: str = "COSTO_SECADA_ELEVADO"
    domain: str = "harvest"
    priority: int = 40
    required_inputs: Set[str] = {"cultivo", "humedad_grano_pct"}

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        cultivo = context.cultivo or "maiz"
        humedad_grano = context.harvest.humedad_grano_pct
        p_spot = context.market.precio_spot_usd

        if humedad_grano is None or p_spot is None or p_spot <= 0.0:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                missing_inputs=["humedad_grano_pct", "precio_spot_usd"],
            )

        bases_map = policy.get(
            "cosecha.humedad_comercial_base_por_cultivo",
            EffectivePolicyValue(value={"maiz": 14.5, "soja": 13.5, "sorgo": 15.0, "trigo": 14.0}, source_scope="system_base"),
        ).value
        hum_base = float(bases_map.get(cultivo, 14.5)) if isinstance(bases_map, dict) else 14.5
        costo_punto = float(policy.get("cosecha.costo_secada_punto_usd", EffectivePolicyValue(value=2.50, source_scope="system_base")).value)

        drying_res = calculate_drying_cost(
            grain_moisture_pct=humedad_grano,
            commercial_base_moisture_pct=hum_base,
            drying_cost_per_point_usd_tn=costo_punto,
            spot_price_usd_tn=p_spot,
        )

        pct_alerta = float(policy.get("cosecha.costo_secada_alerta_pct_spot", EffectivePolicyValue(value=3.0, source_scope="system_base")).value)
        pct_costo = drying_res.cost_pct_over_spot or 0.0

        if not drying_res.is_evaluated or pct_costo < pct_alerta:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["humedad_grano_pct", "precio_spot_usd"],
            )

        costo_total = drying_res.total_drying_cost_usd_tn

        insight = DecisionInsight(
            codigo=self.code,
            nivel="info",
            titulo=f"Impacto de Secada: {fmt_ar(pct_costo)}% del Valor de la Tonelada",
            mensaje=(
                f"El costo de secada estimado (US$ {fmt_ar(costo_total)} USD/Tn) absorbe el "
                f"{fmt_ar(pct_costo)}% del precio spot (US$ {fmt_ar(p_spot)} USD/Tn). "
                f"Conviene considerar la tarifa de acondicionamiento del acopio antes de entregar."
            ),
            datos={
                "costo_secada_usd_tn": costo_total,
                "porcentaje_sobre_spot": pct_costo,
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Revisar cuadro tarifario de acopio / cooperativa de entrega.",
            confidence="high",
            reason_codes=["HIGH_DRYING_COST_RATIO"],
            inputs_used=["humedad_grano_pct", "precio_spot_usd"],
        )

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            inputs_used=["humedad_grano_pct", "precio_spot_usd"],
        )
