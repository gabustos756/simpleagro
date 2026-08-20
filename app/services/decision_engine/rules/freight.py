"""
Reglas del Dominio de Flete y Economía de Entregas Comercial (EduAgro).
Evalúa alternativas de destino, precios netos en origen, elegibilidad por camino/cupo y vigencia de cotización.
"""

from decimal import Decimal
from typing import Dict, Set, List
from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
    DecisionInsight,
    RoadStatus,
    AvailabilityStatus,
)
from app.services.decision_engine.rules.base import RuleTraceContext, fmt_ar
from app.services.decision_engine.calculators.freight import calculate_delivery_economics
from app.services.decision_engine.calculators.delivery_economics import (
    evaluate_destination_eligibility,
    rank_delivery_options,
)


class FleteSinCotizacionRule:
    code: str = "FLETE_SIN_COTIZACION"
    domain: str = "freight"
    priority: int = 70
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        destinos_sin_flete: List[str] = []
        for d in context.delivery_options:
            if d.freight_usd_tn is None:
                destinos_sin_flete.append(d.destination_name)

        if not destinos_sin_flete:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning",
            titulo=f"Flete no Cotizado en {len(destinos_sin_flete)} Destino(s)",
            mensaje=f"No se ingresó la tarifa de flete para: {', '.join(destinos_sin_flete)}. No es posible calcular el precio neto en origen para estas alternativas.",
            datos={"destinos_sin_flete": destinos_sin_flete},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="ACTUALIZAR_COTIZACION",
            confidence="low",
            reason_codes=["MISSING_FREIGHT_COST"],
            missing_inputs=["freight_usd_tn"],
            disclaimer="Análisis determinístico de flete de referencia. No constituye oferta de transporte ni contrato comercial.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)


class CotizacionFleteDesactualizadaRule:
    code: str = "COTIZACION_FLETE_DESACTUALIZADA"
    domain: str = "freight"
    priority: int = 71
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        max_age = int(policy.get("freight.max_quote_age_hours", EffectivePolicyValue(value=48, source_scope="system_base")).value)

        destinos_stale: List[str] = []
        for d in context.delivery_options:
            econ = calculate_delivery_economics(d, max_quote_age_hours=max_age)
            if econ.is_quote_stale:
                destinos_stale.append(d.destination_name)

        if not destinos_stale:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning",
            titulo=f"Cotización de Flete Desactualizada ({len(destinos_stale)} Destino(s))",
            mensaje=f"La tarifa o precio registrado para {', '.join(destinos_stale)} supera la antigüedad máxima permitida ({max_age}h) o ha vencido. Se requiere actualización.",
            datos={"destinos_desactualizados": destinos_stale, "max_age_hours": max_age},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="ACTUALIZAR_COTIZACION",
            confidence="medium",
            reason_codes=["STALE_FREIGHT_QUOTE"],
            missing_inputs=[],
            disclaimer="Análisis determinístico de flete de referencia. No constituye oferta de transporte ni contrato comercial.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)


class DestinoNoAptoPorCaminoRule:
    code: str = "DESTINO_NO_APTO_POR_CAMINO"
    domain: str = "freight"
    priority: int = 72
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        destinos_bloqueados: List[str] = []
        for d in context.delivery_options:
            if d.road_status == RoadStatus.IMPASSABLE:
                destinos_bloqueados.append(d.destination_name)

        if not destinos_bloqueados:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        insight = DecisionInsight(
            codigo=self.code,
            nivel="danger",
            titulo="Destino No Apto por Estado de Camino Rural",
            mensaje=f"Caminos clasificados como intransitables impiden la entrega en: {', '.join(destinos_bloqueados)}. La alternativa queda desestimada.",
            datos={"destinos_intransitables": destinos_bloqueados},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="REVISAR_CAMINO",
            confidence="high",
            reason_codes=["ROAD_IMPASSABLE"],
            disclaimer="Diagnóstico determinístico de accesibilidad vial.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)


class DestinoSinCupoConfirmadoRule:
    code: str = "DESTINO_SIN_CUPO_CONFIRMADO"
    domain: str = "freight"
    priority: int = 73
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        destinos_sin_cupo: List[str] = []
        for d in context.delivery_options:
            if d.receiving_confirmed == AvailabilityStatus.UNKNOWN:
                destinos_sin_cupo.append(d.destination_name)

        if not destinos_sin_cupo:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        insight = DecisionInsight(
            codigo=self.code,
            nivel="info",
            titulo="Recepcion o Cupo Pendiente de Confirmación",
            mensaje=f"No se registra cupo/recepción confirmado para: {', '.join(destinos_sin_cupo)}. La opción se evalúa en forma condicionada.",
            datos={"destinos_sin_cupo": destinos_sin_cupo},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="CONFIRMAR_CUPO",
            confidence="medium",
            reason_codes=["UNCONFIRMED_RECEIVING"],
            disclaimer="Análisis de factibilidad logística de entrega.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)


class DestinoCondicionadoPorHumedadRule:
    code: str = "DESTINO_CONDICIONADO_POR_HUMEDAD"
    domain: str = "freight"
    priority: int = 74
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        hum_grano = context.harvest.humedad_grano_pct
        if hum_grano is None:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        destinos_excedidos: List[str] = []
        for d in context.delivery_options:
            if d.max_receiving_moisture_pct is not None and Decimal(str(hum_grano)) > d.max_receiving_moisture_pct:
                destinos_excedidos.append(f"{d.destination_name} (Máx: {d.max_receiving_moisture_pct}%)")

        if not destinos_excedidos:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning",
            titulo="Humedad de Grano Supera Límite de Recepción",
            mensaje=f"La humedad medida ({hum_grano:.1f}%) supera el tolerancia máxima de recibo en: {', '.join(destinos_excedidos)}. Requiere confirmar secada o excepción de recibo.",
            datos={"humedad_grano_pct": hum_grano, "destinos_excedidos": destinos_excedidos},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="CONFIRMAR_RECEPCION_HUMEDAD",
            confidence="high",
            reason_codes=["GRAIN_MOISTURE_EXCEEDS_RECEIVING_LIMIT"],
            disclaimer="Evaluación de tolerancia de humedad según contrato comercial.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)


class PrecioNetoOrigenCalculadoRule:
    code: str = "PRECIO_NETO_ORIGEN_CALCULADO"
    domain: str = "freight"
    priority: int = 75
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        max_age = int(policy.get("freight.max_quote_age_hours", EffectivePolicyValue(value=48, source_scope="system_base")).value)

        desglose: List[dict] = []
        for d in context.delivery_options:
            econ = calculate_delivery_economics(d, max_quote_age_hours=max_age)
            if econ.is_net_price_fully_calculated and econ.net_origin_price_usd_tn is not None:
                desglose.append({
                    "destino": d.destination_name,
                    "precio_ofrecido_usd": float(econ.offered_price_usd_tn or 0.0),
                    "flete_usd": float(econ.freight_usd_tn or 0.0),
                    "acondicionamiento_usd": float(econ.conditioning_cost_usd_tn or 0.0),
                    "otros_costos_usd": float(econ.other_costs_usd_tn or 0.0),
                    "neto_origen_usd": float(econ.net_origin_price_usd_tn),
                })

        if not desglose:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        insight = DecisionInsight(
            codigo=self.code,
            nivel="info",
            titulo=f"Precio Neto en Origen Calculado para {len(desglose)} Destino(s)",
            mensaje=f"Se completó la liquidación estimada en origen descontando flete y reacondicionamiento para {len(desglose)} alternativas.",
            datos={"desglose_destinos": desglose},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="EVALUAR_DESTINO_NETO",
            confidence="high",
            reason_codes=["NET_ORIGIN_PRICE_CALCULATED"],
            disclaimer="Cálculo informativo en origen; no constituye liquidación final de granos.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)


class DestinoNetoMasConvenienteRule:
    code: str = "DESTINO_NETO_MAS_CONVENIENTE"
    domain: str = "freight"
    priority: int = 76
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        threshold = Decimal(str(policy.get("freight.diferencia_neta_minima_relevante_usd_tn", EffectivePolicyValue(value=1.0, source_scope="system_base")).value))
        max_age = int(policy.get("freight.max_quote_age_hours", EffectivePolicyValue(value=48, source_scope="system_base")).value)

        ranked = rank_delivery_options(
            destinations=context.delivery_options,
            grain_moisture_pct=context.harvest.humedad_grano_pct,
            min_material_difference_usd_tn=threshold,
            max_quote_age_hours=max_age,
        )

        if not ranked.best_option or not ranked.is_best_option_material or ranked.net_difference_usd_tn is None:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        best = ranked.best_option
        neto_best = float(best.net_origin_price_usd_tn or 0.0)
        diff_val = float(ranked.net_difference_usd_tn)

        insight = DecisionInsight(
            codigo=self.code,
            nivel="success",
            titulo=f"Destino Sugerido: {best.destination_name} (+US$ {fmt_ar(diff_val)} USD/Tn Neto)",
            mensaje=(
                f"La alternativa con mayor valor neto estimado en origen es {best.destination_name} (US$ {fmt_ar(neto_best)} USD/Tn neto), "
                f"ofreciendo una ventaja económica de +US$ {fmt_ar(diff_val)} USD/Tn respecto a la segunda opción elegible."
            ),
            datos={
                "destino_optimo": best.destination_name,
                "neto_origen_usd_tn": neto_best,
                "diferencia_ventaja_usd_tn": diff_val,
                "diferencia_minima_material_usd": float(threshold),
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="EVALUAR_DESTINO_NETO",
            confidence="high" if not best.is_quote_stale else "medium",
            reason_codes=["OPTIMAL_NET_DELIVERY_DESTINATION"],
            disclaimer="Recomendación determinística de apoyo a la decisión de comercialización; validar cupo y tarifa final.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)


class SinDiferenciaNetaMaterialEntreDestinosRule:
    code: str = "SIN_DIFERENCIA_NETA_MATERIAL_ENTRE_DESTINOS"
    domain: str = "freight"
    priority: int = 77
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        threshold = Decimal(str(policy.get("freight.diferencia_neta_minima_relevante_usd_tn", EffectivePolicyValue(value=1.0, source_scope="system_base")).value))
        max_age = int(policy.get("freight.max_quote_age_hours", EffectivePolicyValue(value=48, source_scope="system_base")).value)

        ranked = rank_delivery_options(
            destinations=context.delivery_options,
            grain_moisture_pct=context.harvest.humedad_grano_pct,
            min_material_difference_usd_tn=threshold,
            max_quote_age_hours=max_age,
        )

        if not ranked.best_option or len(ranked.ranked_options) < 2 or ranked.is_best_option_material:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        diff_val = float(ranked.net_difference_usd_tn or Decimal("0.0"))

        insight = DecisionInsight(
            codigo=self.code,
            nivel="info",
            titulo="Sin Diferencia Económica Material Entre Destinos",
            mensaje=(
                f"Las alternativas elegibles presentan valores netos similares (diferencia de US$ {fmt_ar(diff_val)} USD/Tn, inferior al umbral de US$ {fmt_ar(float(threshold))} USD/Tn). "
                f"Se sugiere decidir considerando conveniencia de cupo, estado de caminos, tiempos de descarga y confianza en el comprador."
            ),
            datos={
                "diferencia_detectada_usd": diff_val,
                "umbral_material_usd": float(threshold),
                "opciones_evaluadas": [o.destination_name for o in ranked.ranked_options],
            },
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="CONFIRMAR_CUPO",
            confidence="high",
            reason_codes=["IMMTERIAL_NET_PRICE_DIFFERENCE"],
            disclaimer="Análisis de apoyo a la decisión logística y comercial.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)


class DatosInsuficientesParaCompararDestinosRule:
    code: str = "DATOS_INSUFICIENTES_PARA_COMPARAR_DESTINOS"
    domain: str = "freight"
    priority: int = 78
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.delivery_options:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        max_age = int(policy.get("freight.max_quote_age_hours", EffectivePolicyValue(value=48, source_scope="system_base")).value)
        threshold = Decimal(str(policy.get("freight.diferencia_neta_minima_relevante_usd_tn", EffectivePolicyValue(value=1.0, source_scope="system_base")).value))

        ranked = rank_delivery_options(
            destinations=context.delivery_options,
            grain_moisture_pct=context.harvest.humedad_grano_pct,
            min_material_difference_usd_tn=threshold,
            max_quote_age_hours=max_age,
        )

        if len(ranked.ranked_options) >= 2:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        destinos_incompletos: List[str] = [
            e.destination_name for e in ranked.all_economics if not e.is_net_price_fully_calculated
        ]

        insight = DecisionInsight(
            codigo=self.code,
            nivel="warning",
            titulo="Datos Incompletos para Comparación de Destinos",
            mensaje=f"No se cuenta con al menos dos alternativas elegibles con precio neto completo para realizar la comparativa. Revisar: {', '.join(destinos_incompletos) if destinos_incompletos else 'opciones no elegibles'}.",
            datos={"destinos_incompletos": destinos_incompletos},
            domain=self.domain,
            priority=self.priority,
            accion_recomendada="ACTUALIZAR_COTIZACION",
            confidence="low",
            reason_codes=["INSUFFICIENT_DELIVERY_DATA"],
            missing_inputs=["freight_usd_tn", "price_usd_tn"],
            disclaimer="Análisis informativo de cobertura de datos.",
        )
        return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)
