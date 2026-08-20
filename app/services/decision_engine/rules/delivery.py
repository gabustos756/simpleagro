"""
Reglas Determinísticas para el Dominio de Entregas y Cartas de Porte (EduAgro).
Evalúa faltante de documentación, pesajes de origen/destino, mermas/diferencias y fletes estimados.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Set
from app.services.decision_engine.models import (
    DecisionContext,
    DecisionInsight,
    EffectivePolicyValue,
    RuleEvaluation,
    GrainDeliveryContext,
)
from app.services.decision_engine.rules.base import RuleTraceContext
from app.services.decision_engine.calculators.delivery import (
    calculate_origin_net_weight,
    calculate_delivery_weight_difference,
    calculate_estimated_delivery_freight,
)


class EntregaSinCartaDePorteRule:
    """
    Regla: ENTREGA_SIN_CARTA_DE_PORTE
    Se activa cuando una entrega no cuenta con al menos una carta de porte con número registrado.
    """
    code: str = "ENTREGA_SIN_CARTA_DE_PORTE"
    domain: str = "deliveries"
    description: str = "Advierte cuando una entrega no posee carta de porte registrada."
    priority: int = 20
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.deliveries:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                reason_codes=["SIN_ENTREGAS_EN_CONTEXTO"],
            )

        require_waybill = policy.get(
            "deliveries.require_waybill_for_completed_delivery",
            EffectivePolicyValue(value=False, source_scope="system_base"),
        ).value

        insights: List[DecisionInsight] = []
        reasons: List[str] = []

        for deliv in context.deliveries:
            has_cpe = any(
                w.numero_carta_porte and w.numero_carta_porte.strip()
                for w in deliv.waybills
            )
            if not has_cpe:
                reasons.append(f"{deliv.tracking_number}_SIN_CPE")

                if deliv.estado == "planificada":
                    nivel = "info"
                elif deliv.estado == "en_transito":
                    nivel = "warning"
                elif deliv.estado in ["recibida", "liquidada"]:
                    nivel = "danger" if require_waybill else "warning"
                else:
                    nivel = "warning"

                insights.append(
                    DecisionInsight(
                        codigo=self.code,
                        nivel=nivel,
                        titulo=f"Documentación Pendiente: Entrega {deliv.tracking_number}",
                        mensaje=f"La entrega '{deliv.tracking_number}' (Estado: {deliv.estado}) no posee número de carta de porte registrado.",
                        datos={
                            "tracking_number": deliv.tracking_number,
                            "delivery_id": str(deliv.id) if deliv.id else None,
                            "estado": deliv.estado,
                        },
                        domain=self.domain,
                        priority=self.priority,
                        accion_recomendada="REGISTRAR_CARTA_DE_PORTE",
                        confidence="high",
                    )
                )

        if not insights:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insights[0],
            reason_codes=reasons,
        )


class CartaPorteSinPesoOrigenRule:
    """
    Regla: CARTA_PORTE_SIN_PESO_ORIGEN
    Se activa cuando una carta de porte no tiene registradas la tara o el peso bruto de origen.
    """
    code: str = "CARTA_PORTE_SIN_PESO_ORIGEN"
    domain: str = "deliveries"
    description: str = "Detecta cartas de porte sin pesaje completo de origen."
    priority: int = 25
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.deliveries:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                reason_codes=["SIN_ENTREGAS_EN_CONTEXTO"],
            )

        insights: List[DecisionInsight] = []
        reasons: List[str] = []

        for deliv in context.deliveries:
            for w in deliv.waybills:
                if w.estado != "anulada":
                    res = calculate_origin_net_weight(w.peso_bruto_origen_kg, w.tara_kg)
                    if not res.is_valid_origin_weight:
                        cpe_lbl = w.numero_carta_porte or "Sin Número"
                        reasons.append(f"CPE_{cpe_lbl}_SIN_PESO_ORIGEN")
                        insights.append(
                            DecisionInsight(
                                codigo=self.code,
                                nivel="warning",
                                titulo=f"Falta Pesaje de Origen: Carta {cpe_lbl}",
                                mensaje=f"La carta de porte {cpe_lbl} de la entrega {deliv.tracking_number} no cuenta con pesaje de origen válido (Tara / Bruto).",
                                datos={
                                    "waybill_id": str(w.id) if w.id else None,
                                    "tracking_number": deliv.tracking_number,
                                    "warning": res.warning,
                                },
                                domain=self.domain,
                                priority=self.priority,
                                accion_recomendada="COMPLETAR_PESAJE_ORIGEN",
                                confidence="high",
                            )
                        )

        if not insights:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insights[0],
            reason_codes=reasons,
        )


class CartaPorteSinPesoDestinoRule:
    """
    Regla: CARTA_PORTE_SIN_PESO_DESTINO
    Se activa cuando existe peso neto de origen y la carta está cargada/en tránsito/recibida, pero falta peso recibido.
    """
    code: str = "CARTA_PORTE_SIN_PESO_DESTINO"
    domain: str = "deliveries"
    description: str = "Detecta viajes en tránsito/recibidos sin balanza de destino."
    priority: int = 30
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.deliveries:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                reason_codes=["SIN_ENTREGAS_EN_CONTEXTO"],
            )

        insights: List[DecisionInsight] = []
        reasons: List[str] = []

        for deliv in context.deliveries:
            for w in deliv.waybills:
                if w.estado in ["cargada", "en_transito", "recibida"]:
                    net_origen = w.peso_neto_origen_kg
                    if net_origen is not None and w.peso_recibido_destino_kg is None:
                        cpe_lbl = w.numero_carta_porte or "Sin Número"
                        reasons.append(f"CPE_{cpe_lbl}_SIN_PESO_DESTINO")
                        insights.append(
                            DecisionInsight(
                                codigo=self.code,
                                nivel="info",
                                titulo=f"Pendiente Balanza Destino: Carta {cpe_lbl}",
                                mensaje=f"La carta {cpe_lbl} ({deliv.tracking_number}) posee neto origen ({net_origen} kg) pero aguarda ticket de pesaje en destino.",
                                datos={
                                    "waybill_id": str(w.id) if w.id else None,
                                    "tracking_number": deliv.tracking_number,
                                    "peso_neto_origen_kg": float(net_origen),
                                },
                                domain=self.domain,
                                priority=self.priority,
                                accion_recomendada="COMPLETAR_PESAJE_DESTINO",
                                confidence="high",
                            )
                        )

        if not insights:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insights[0],
            reason_codes=reasons,
        )


class DiferenciaDePesajeARevisarRule:
    """
    Regla: DIFERENCIA_DE_PESAJE_A_REVISAR
    Se activa únicamente si existen ambos pesajes y la diferencia supera los umbrales configurados.
    """
    code: str = "DIFERENCIA_DE_PESAJE_A_REVISAR"
    domain: str = "deliveries"
    description: str = "Advierte discrepancias de pesaje entre balanza de origen y destino."
    priority: int = 35
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.deliveries:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                reason_codes=["SIN_ENTREGAS_EN_CONTEXTO"],
            )

        review_pct = Decimal(str(policy.get(
            "deliveries.weight_difference_review_pct",
            EffectivePolicyValue(value=1.0, source_scope="system_base"),
        ).value))

        review_kg = Decimal(str(policy.get(
            "deliveries.weight_difference_review_kg",
            EffectivePolicyValue(value=300, source_scope="system_base"),
        ).value))

        insights: List[DecisionInsight] = []
        reasons: List[str] = []

        for deliv in context.deliveries:
            for w in deliv.waybills:
                if w.estado != "anulada":
                    res = calculate_delivery_weight_difference(
                        w.peso_neto_origen_kg,
                        w.peso_recibido_destino_kg,
                    )
                    if res.is_evaluable and res.difference_kg is not None and res.difference_pct is not None:
                        abs_diff_kg = abs(res.difference_kg)
                        abs_diff_pct = abs(res.difference_pct)

                        if abs_diff_pct >= review_pct or abs_diff_kg >= review_kg:
                            cpe_lbl = w.numero_carta_porte or "Sin Número"
                            reasons.append(f"CPE_{cpe_lbl}_DIFERENCIA_EXCEDIDA")

                            insights.append(
                                DecisionInsight(
                                    codigo=self.code,
                                    nivel="warning",
                                    titulo=f"Diferencia de Pesaje a Revisar: {cpe_lbl} ({res.difference_kg:+.0f} kg)",
                                    mensaje=(
                                        f"La carta {cpe_lbl} ({deliv.tracking_number}) registra una diferencia de "
                                        f"{res.difference_kg:+.0f} kg ({res.difference_pct:+.2f}%) entre origen "
                                        f"({w.peso_neto_origen_kg} kg) y destino ({w.peso_recibido_destino_kg} kg)."
                                    ),
                                    datos={
                                        "waybill_id": str(w.id) if w.id else None,
                                        "tracking_number": deliv.tracking_number,
                                        "peso_neto_origen_kg": float(w.peso_neto_origen_kg),
                                        "peso_recibido_destino_kg": float(w.peso_recibido_destino_kg),
                                        "diferencia_kg": float(res.difference_kg),
                                        "diferencia_pct": float(res.difference_pct),
                                    },
                                    domain=self.domain,
                                    priority=self.priority,
                                    accion_recomendada="REVISAR_DIFERENCIA_PESAJE",
                                    confidence="high",
                                )
                            )

        if not insights:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insights[0],
            reason_codes=reasons,
        )


class CargaSuperaCapacidadReferenciaRule:
    """
    Regla: CARGA_SUPERA_CAPACIDAD_REFERENCIA
    Emitida si el neto de origen supera la capacidad de referencia configurada para el camión.
    """
    code: str = "CARGA_SUPERA_CAPACIDAD_REFERENCIA"
    domain: str = "deliveries"
    description: str = "Insight preventivo cuando la carga supera la capacidad referencial."
    priority: int = 40
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.deliveries:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                reason_codes=["SIN_ENTREGAS_EN_CONTEXTO"],
            )

        normal_cap = Decimal(str(policy.get(
            "deliveries.normal_truck_reference_capacity_kg",
            EffectivePolicyValue(value=35000, source_scope="system_base"),
        ).value))

        vulcano_cap = Decimal(str(policy.get(
            "deliveries.vulcano_truck_reference_capacity_kg",
            EffectivePolicyValue(value=45000, source_scope="system_base"),
        ).value))

        insights: List[DecisionInsight] = []
        reasons: List[str] = []

        for deliv in context.deliveries:
            for w in deliv.waybills:
                if w.estado != "anulada" and w.peso_neto_origen_kg is not None:
                    cap = w.capacidad_referencia_kg
                    if cap is None:
                        if w.tipo_camion == "normal":
                            cap = normal_cap
                        elif w.tipo_camion == "vulcano":
                            cap = vulcano_cap

                    if cap is not None and w.peso_neto_origen_kg > cap:
                        cpe_lbl = w.numero_carta_porte or "Sin Número"
                        reasons.append(f"CPE_{cpe_lbl}_SUPERA_CAPACIDAD")
                        excess_kg = w.peso_neto_origen_kg - cap

                        insights.append(
                            DecisionInsight(
                                codigo=self.code,
                                nivel="info",
                                titulo=f"Carga sobre Referencia: Carta {cpe_lbl} (+{excess_kg:.0f} kg)",
                                mensaje=(
                                    f"La carga de la carta {cpe_lbl} ({w.peso_neto_origen_kg:.0f} kg) "
                                    f"supera la capacidad de referencia configurada ({cap:.0f} kg) en {excess_kg:.0f} kg."
                                ),
                                datos={
                                    "waybill_id": str(w.id) if w.id else None,
                                    "tracking_number": deliv.tracking_number,
                                    "peso_neto_origen_kg": float(w.peso_neto_origen_kg),
                                    "capacidad_referencia_kg": float(cap),
                                },
                                domain=self.domain,
                                priority=self.priority,
                                accion_recomendada="VERIFICAR_TOLERANCIA_CARGA",
                                confidence="medium",
                            )
                        )

        if not insights:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insights[0],
            reason_codes=reasons,
        )


class FleteEstimadoPorEntregaRule:
    """
    Regla: FLETE_ESTIMADO_POR_ENTREGA
    Se activa si la entrega o destino posee tarifa de flete y pesaje utilizable.
    """
    code: str = "FLETE_ESTIMADO_POR_ENTREGA"
    domain: str = "deliveries"
    description: str = "Calcula el costo estimado de flete por entrega comercial."
    priority: int = 45
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.deliveries:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                reason_codes=["SIN_ENTREGAS_EN_CONTEXTO"],
            )

        insights: List[DecisionInsight] = []
        reasons: List[str] = []

        quote_rate_map: Dict[str, Decimal] = {}
        for opt in context.delivery_options:
            if opt.destination_id and opt.freight_usd_tn is not None:
                quote_rate_map[str(opt.destination_id)] = opt.freight_usd_tn

        for deliv in context.deliveries:
            freight_rate: Optional[Decimal] = None
            if deliv.freight_quote_id and str(deliv.freight_quote_id) in quote_rate_map:
                freight_rate = quote_rate_map[str(deliv.freight_quote_id)]

            if freight_rate is not None:
                res = calculate_estimated_delivery_freight(
                    freight_rate,
                    deliv.kg_neto_origen_total,
                    deliv.kg_recibido_total,
                )

                if res.estimated_freight_cost_usd is not None:
                    reasons.append(f"FLETE_ESTIMADO_{deliv.tracking_number}")
                    tipo_lbl = "Definitivo" if not res.is_estimated else "Estimado"

                    insights.append(
                        DecisionInsight(
                            codigo=self.code,
                            nivel="info",
                            titulo=f"Flete {tipo_lbl} {deliv.tracking_number}: US$ {res.estimated_freight_cost_usd:.2f}",
                            mensaje=(
                                f"El flete {tipo_lbl.lower()} para la entrega {deliv.tracking_number} es de "
                                f"US$ {res.estimated_freight_cost_usd:.2f} USD "
                                f"({res.base_weight_kg:.0f} kg a US$ {freight_rate:.2f}/Tn)."
                            ),
                            datos={
                                "tracking_number": deliv.tracking_number,
                                "freight_usd_tn": float(freight_rate),
                                "base_weight_kg": float(res.base_weight_kg),
                                "weight_source": res.weight_source,
                                "is_estimated": res.is_estimated,
                                "estimated_freight_cost_usd": float(res.estimated_freight_cost_usd),
                            },
                            domain=self.domain,
                            priority=self.priority,
                            accion_recomendada="AUDITAR_COSTO_FLETE",
                            confidence="high",
                        )
                    )

        if not insights:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insights[0],
            reason_codes=reasons,
        )


class EntregaAsociadaACompromisoRule:
    """
    Regla: ENTREGA_ASOCIADA_A_COMPROMISO
    Se activa si la entrega posee un compromiso de entrega comercial vinculado.
    """
    code: str = "ENTREGA_ASOCIADA_A_COMPROMISO"
    domain: str = "deliveries"
    description: str = "Informa la vinculación comercial con un compromiso de entrega."
    priority: int = 50
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.deliveries:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                reason_codes=["SIN_ENTREGAS_EN_CONTEXTO"],
            )

        insights: List[DecisionInsight] = []
        reasons: List[str] = []

        for deliv in context.deliveries:
            if deliv.compromiso_id:
                reasons.append(f"ENTREGA_{deliv.tracking_number}_CON_COMPROMISO")
                tn_lbl = f"{deliv.toneladas_planificadas:.2f} Tn" if deliv.toneladas_planificadas is not None else "Tn no especificadas"

                insights.append(
                    DecisionInsight(
                        codigo=self.code,
                        nivel="info",
                        titulo=f"Compromiso Vinculado: {deliv.tracking_number}",
                        mensaje=f"La entrega {deliv.tracking_number} ({tn_lbl}) está imputada al compromiso comercial registrado.",
                        datos={
                            "tracking_number": deliv.tracking_number,
                            "compromiso_id": str(deliv.compromiso_id),
                        },
                        domain=self.domain,
                        priority=self.priority,
                        accion_recomendada="VERIFICAR_CUMPLIMIENTO_COMPROMISO",
                        confidence="high",
                    )
                )

        if not insights:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insights[0],
            reason_codes=reasons,
        )


class EntregaConDocumentacionPendienteRule:
    """
    Regla: ENTREGA_CON_DOCUMENTACION_PENDIENTE
    Se activa para entregas recibidas o liquidadas sin documentación completa.
    """
    code: str = "ENTREGA_CON_DOCUMENTACION_PENDIENTE"
    domain: str = "deliveries"
    description: str = "Destaca entregas avanzadas que requieren completar el número de carta de porte."
    priority: int = 55
    required_inputs: Set[str] = set()

    def evaluate(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> RuleEvaluation:
        if not context.deliveries:
            return RuleEvaluation(
                rule_code=self.code,
                status="not_evaluated",
                reason_codes=["SIN_ENTREGAS_EN_CONTEXTO"],
            )

        insights: List[DecisionInsight] = []
        reasons: List[str] = []

        for deliv in context.deliveries:
            if deliv.estado in ["recibida", "liquidada"] and deliv.documentacion_status in ["sin_documentacion", "carta_pendiente"]:
                reasons.append(f"ENTREGA_{deliv.tracking_number}_DOC_PENDIENTE")
                insights.append(
                    DecisionInsight(
                        codigo=self.code,
                        nivel="warning",
                        titulo=f"Documentación Pendiente: Entrega {deliv.tracking_number}",
                        mensaje=(
                            f"La entrega {deliv.tracking_number} se encuentra en estado '{deliv.estado}', "
                            "pero aún no registra el número de carta de porte definitivo."
                        ),
                        datos={
                            "tracking_number": deliv.tracking_number,
                            "estado": deliv.estado,
                            "documentacion_status": deliv.documentacion_status,
                        },
                        domain=self.domain,
                        priority=self.priority,
                        accion_recomendada="REGISTRAR_NUMERO_CARTA_PORTE",
                        confidence="high",
                    )
                )

        if not insights:
            return RuleEvaluation(rule_code=self.code, status="not_triggered")

        return RuleEvaluation(
            rule_code=self.code,
            status="triggered",
            insight=insights[0],
            reason_codes=reasons,
        )
