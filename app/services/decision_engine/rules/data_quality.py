"""
Reglas del Dominio de Calidad de Datos e Incertidumbre Meteorológica (EduAgro).
"""

from typing import Dict, Set, List
from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import RuleTraceContext, fmt_ar


class DatosInsuficientesCosechaRule:
    code: str = "DATOS_INSUFICIENTES_PARA_COSECHA"
    domain: str = "data_quality"
    priority: int = 10
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        missing: List[str] = []
        if context.harvest.humedad_grano_pct is None:
            missing.append("humedad_grano_pct")
        if context.cultivo is None:
            missing.append("cultivo")

        if not missing:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["humedad_grano_pct", "cultivo"],
                missing_inputs=[],
            )

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning",
            titulo="Datos Insuficientes para Evaluación de Cosecha",
            mensaje=f"Faltan parámetros clave de cosecha ({', '.join(missing)}). No es posible cuantificar costo de secado ni ventana óptima.",
            datos={"missing_inputs": missing},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Ingresar la humedad del grano en laboratorio o humedad estimada del lote.",
            confidence="low",
            reason_codes=["MISSING_HARVEST_INPUTS"],
            missing_inputs=missing,
        )
        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            missing_inputs=missing,
        )


class DatosInsuficientesComercializacionRule:
    code: str = "DATOS_INSUFICIENTES_PARA_COMERCIALIZACION"
    domain: str = "data_quality"
    priority: int = 15
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        missing: List[str] = []
        if context.market.precio_spot_usd is None:
            missing.append("precio_spot_usd")
        if context.market.precio_futuro_usd is None:
            missing.append("precio_futuro_usd")

        if not missing:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["precio_spot_usd", "precio_futuro_usd"],
                missing_inputs=[],
            )

        insight = DecisionInsight(
            codigo=self.code,
            nivel="info",
            titulo="Datos de Mercado Incompletos",
            mensaje=f"Faltan cotizaciones de mercado ({', '.join(missing)}). La recomendación neta de diferimiento requiere precios spot y futuro de Matba Rofex.",
            datos={"missing_inputs": missing},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Actualizar cotización CAC Rosario o seleccionar contrato de futuro de referencia.",
            confidence="low",
            reason_codes=["MISSING_MARKET_INPUTS"],
            missing_inputs=missing,
        )
        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            missing_inputs=missing,
        )


class ClimaNoDisponibleRule:
    code: str = "CLIMA_NO_DISPONIBLE"
    domain: str = "data_quality"
    priority: int = 5
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        w_status = context.weather.provider_status or "unavailable"

        if w_status != "unavailable":
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["weather.provider_status"],
                missing_inputs=[],
            )

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning",
            titulo="Información Meteorológica en Vivo No Disponible",
            mensaje="Los proveedores climáticos no respondieron y no existe serie histórica en caché. Las alertas operativas basadas en clima se encuentran desactivadas para evitar decisiones erróneas.",
            datos={"provider_status": w_status},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Verificar conectividad o consultar la estación meteorológica física del establecimiento.",
            confidence="low",
            reason_codes=["WEATHER_UNAVAILABLE"],
            missing_inputs=["weather_forecast"],
        )
        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
            missing_inputs=["weather_forecast"],
        )


class AltaIncertidumbreMeteorologicaRule:
    code: str = "ALTA_INCERTIDUMBRE_METEOROLOGICA"
    domain: str = "data_quality"
    priority: int = 8
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        disagreement = context.weather.disagreement_level or "none"
        w_status = context.weather.provider_status or "live"

        is_stale = w_status == "stale_cached"
        is_high_disagreement = disagreement in ("medium", "high")

        if not is_stale and not is_high_disagreement:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_triggered",
                inputs_used=["weather.disagreement_level", "weather.provider_status"],
                missing_inputs=[],
            )

        razon = "Datos obtenidos de caché vencido por falla de proveedores en vivo." if is_stale else f"Alta discrepancia en la predicción entre proveedores meteorológicos (nivel: {disagreement})."

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning",
            titulo="Incertidumbre Meteorológica Detectada",
            mensaje=f"{razon} Se recomienda verificar condiciones locales antes de iniciar labores críticas.",
            datos={
                "disagreement_level": disagreement,
                "provider_status": w_status,
                "recommended_decision_mode": context.weather.recommended_decision_mode,
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="Aplicar criterio conservador o verificar pluviómetro e instrumental de campo.",
            confidence="medium" if not is_stale else "low",
            reason_codes=["WEATHER_DISAGREEMENT" if is_high_disagreement else "WEATHER_STALE_CACHE"],
        )
        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insight,
        )
