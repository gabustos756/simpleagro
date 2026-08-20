"""
Suite de Pruebas Unitarias para el Dominio Determinístico de Entregas (EduAgro).
Verifica calculadoras puras, políticas jerárquicas, transiciones de estado y reglas registrables.
"""

from decimal import Decimal
from datetime import datetime, date
from uuid import uuid4
import pytest

from app.services.decision_engine.calculators.delivery import (
    calculate_origin_net_weight,
    calculate_delivery_weight_difference,
    calculate_estimated_delivery_freight,
)
from app.services.decision_engine.models import (
    DecisionContext,
    GrainDeliveryContext,
    GrainWaybillContext,
    DeliveryDestinationContext,
)
from app.services.decision_engine.rules.delivery import (
    EntregaSinCartaDePorteRule,
    CartaPorteSinPesoOrigenRule,
    CartaPorteSinPesoDestinoRule,
    DiferenciaDePesajeARevisarRule,
    CargaSuperaCapacidadReferenciaRule,
    FleteEstimadoPorEntregaRule,
    EntregaAsociadaACompromisoRule,
    EntregaConDocumentacionPendienteRule,
)
from app.services.decision_motor import evaluar_motor_decisiones_detallado
from app.main import VALID_DELIVERY_TRANSITIONS


def test_1_calculate_origin_net_weight_valid():
    """Caso 1: Peso bruto menos tara resulta en peso neto exacto."""
    res = calculate_origin_net_weight(Decimal("48500"), Decimal("14200"))
    assert res.is_valid_origin_weight is True
    assert res.origin_net_weight_kg == Decimal("34300")
    assert res.warning is None


def test_2_calculate_origin_net_weight_invalid_gross_less_than_tare():
    """Caso 2: Peso bruto menor a la tara es rechazado con warning."""
    res = calculate_origin_net_weight(Decimal("12000"), Decimal("14200"))
    assert res.is_valid_origin_weight is False
    assert res.origin_net_weight_kg is None
    assert "menor a la tara" in res.warning


def test_3_calculate_delivery_weight_difference_evaluable():
    """Caso 3: Diferencia de pesaje en kg y en % cuando existen ambos pesos."""
    res = calculate_delivery_weight_difference(Decimal("35000"), Decimal("34650"))
    assert res.is_evaluable is True
    assert res.difference_kg == Decimal("-350")
    assert res.difference_pct == Decimal("-1.0")


def test_4_calculate_delivery_weight_difference_missing_weights():
    """Caso 4: Si falta origen o destino, la diferencia no es evaluable."""
    res1 = calculate_delivery_weight_difference(Decimal("35000"), None)
    assert res1.is_evaluable is False
    assert res1.difference_kg is None

    res2 = calculate_delivery_weight_difference(None, Decimal("34650"))
    assert res2.is_evaluable is False
    assert res2.difference_kg is None


def test_5_calculate_estimated_delivery_freight_prioritizes_destination():
    """Caso 5: El cálculo de flete prioriza el peso recibido de destino sobre origen."""
    res = calculate_estimated_delivery_freight(
        freight_usd_tn=Decimal("15.00"),
        origin_net_weight_kg=Decimal("35000"),
        destination_received_weight_kg=Decimal("34000"),
    )
    assert res.weight_source == "destination_received"
    assert res.is_estimated is False
    assert res.estimated_freight_cost_usd == Decimal("510.00")  # (34000/1000) * 15


def test_6_calculate_estimated_delivery_freight_fallback_to_origin():
    """Caso 6: Si falta peso en destino, usa neto origen y marca como estimado."""
    res = calculate_estimated_delivery_freight(
        freight_usd_tn=Decimal("15.00"),
        origin_net_weight_kg=Decimal("35000"),
        destination_received_weight_kg=None,
    )
    assert res.weight_source == "origin_net"
    assert res.is_estimated is True
    assert res.estimated_freight_cost_usd == Decimal("525.00")  # (35000/1000) * 15


def test_7_calculate_estimated_delivery_freight_missing_rate():
    """Caso 7: Si falta tarifa de flete, no devuelve un costo inventado."""
    res = calculate_estimated_delivery_freight(
        freight_usd_tn=None,
        origin_net_weight_kg=Decimal("35000"),
        destination_received_weight_kg=Decimal("34000"),
    )
    assert res.estimated_freight_cost_usd is None
    assert res.weight_source == "none"


def test_8_valid_and_invalid_delivery_state_transitions():
    """Caso 8: Validación de transiciones de estado permitidas e inválidas."""
    # Transiciones válidas
    assert "en_transito" in VALID_DELIVERY_TRANSITIONS["planificada"]
    assert "recibida" in VALID_DELIVERY_TRANSITIONS["en_transito"]
    assert "liquidada" in VALID_DELIVERY_TRANSITIONS["recibida"]
    assert "observada" in VALID_DELIVERY_TRANSITIONS["liquidada"]

    # Transiciones inválidas (saltos directos)
    assert "liquidada" not in VALID_DELIVERY_TRANSITIONS["planificada"]
    assert "recibida" not in VALID_DELIVERY_TRANSITIONS["planificada"]


def test_9_rule_entrega_sin_carta_de_porte():
    """Caso 9: La regla ENTREGA_SIN_CARTA_DE_PORTE genera alertas con el tracking_number."""
    deliv = GrainDeliveryContext(
        tracking_number="ENT-20260820-A1B2",
        estado="en_transito",
        waybills=[],
    )
    ctx = DecisionContext(deliveries=[deliv])
    res = evaluar_motor_decisiones_detallado(ctx)

    codes = [ins.codigo for ins in res.insights]
    assert "ENTREGA_SIN_CARTA_DE_PORTE" in codes
    ins = next(i for i in res.insights if i.codigo == "ENTREGA_SIN_CARTA_DE_PORTE")
    assert "ENT-20260820-A1B2" in ins.mensaje
    assert ins.nivel == "warning"
    assert ins.accion_recomendada == "REGISTRAR_CARTA_DE_PORTE"


def test_10_rule_carta_porte_sin_peso_origen():
    """Caso 10: La regla CARTA_PORTE_SIN_PESO_ORIGEN se activa si falta pesaje bruto o tara."""
    w = GrainWaybillContext(
        numero_carta_porte="0001-12345678",
        peso_bruto_origen_kg=Decimal("48000"),
        tara_kg=None,  # Falta tara
        estado="cargada",
    )
    deliv = GrainDeliveryContext(
        tracking_number="ENT-20260820-A1B2",
        estado="en_transito",
        waybills=[w],
    )
    ctx = DecisionContext(deliveries=[deliv])
    res = evaluar_motor_decisiones_detallado(ctx)

    codes = [ins.codigo for ins in res.insights]
    assert "CARTA_PORTE_SIN_PESO_ORIGEN" in codes
    ins = next(i for i in res.insights if i.codigo == "CARTA_PORTE_SIN_PESO_ORIGEN")
    assert ins.accion_recomendada == "COMPLETAR_PESAJE_ORIGEN"


def test_11_rule_carta_porte_sin_peso_destino():
    """Caso 11: La regla CARTA_PORTE_SIN_PESO_DESTINO avisa cuando hay neto origen sin balanza destino."""
    w = GrainWaybillContext(
        numero_carta_porte="0001-88888888",
        tara_kg=Decimal("14000"),
        peso_bruto_origen_kg=Decimal("49000"),
        peso_neto_origen_kg=Decimal("35000"),
        peso_recibido_destino_kg=None,
        estado="en_transito",
    )
    deliv = GrainDeliveryContext(
        tracking_number="ENT-20260820-C3D4",
        estado="en_transito",
        waybills=[w],
    )
    ctx = DecisionContext(deliveries=[deliv])
    res = evaluar_motor_decisiones_detallado(ctx)

    codes = [ins.codigo for ins in res.insights]
    assert "CARTA_PORTE_SIN_PESO_DESTINO" in codes
    ins = next(i for i in res.insights if i.codigo == "CARTA_PORTE_SIN_PESO_DESTINO")
    assert ins.accion_recomendada == "COMPLETAR_PESAJE_DESTINO"


def test_12_rule_diferencia_de_pesaje_a_revisar():
    """Caso 12: DIFERENCIA_DE_PESAJE_A_REVISAR activa aviso cuando supera el umbral configurado."""
    w = GrainWaybillContext(
        numero_carta_porte="0001-99999999",
        peso_neto_origen_kg=Decimal("35000"),
        peso_recibido_destino_kg=Decimal("34500"),  # Diferencia de -500 kg (-1.43%)
        estado="recibida",
    )
    deliv = GrainDeliveryContext(
        tracking_number="ENT-20260820-E5F6",
        estado="recibida",
        waybills=[w],
    )
    ctx = DecisionContext(deliveries=[deliv])
    res = evaluar_motor_decisiones_detallado(ctx)

    codes = [ins.codigo for ins in res.insights]
    assert "DIFERENCIA_DE_PESAJE_A_REVISAR" in codes
    ins = next(i for i in res.insights if i.codigo == "DIFERENCIA_DE_PESAJE_A_REVISAR")
    assert "-500 kg" in ins.titulo
    assert ins.accion_recomendada == "REVISAR_DIFERENCIA_PESAJE"


def test_13_rule_carga_supera_capacidad_referencia():
    """Caso 13: CARGA_SUPERA_CAPACIDAD_REFERENCIA emite aviso preventivo cuando neto origen supera capacidad de camión."""
    w = GrainWaybillContext(
        numero_carta_porte="0001-77777777",
        tipo_camion="normal",
        capacidad_referencia_kg=Decimal("35000"),
        peso_neto_origen_kg=Decimal("38500"),  # +3500 kg sobre 35.000 kg
        estado="cargada",
    )
    deliv = GrainDeliveryContext(
        tracking_number="ENT-20260820-G7H8",
        estado="en_transito",
        waybills=[w],
    )
    ctx = DecisionContext(deliveries=[deliv])
    res = evaluar_motor_decisiones_detallado(ctx)

    codes = [ins.codigo for ins in res.insights]
    assert "CARGA_SUPERA_CAPACIDAD_REFERENCIA" in codes
    ins = next(i for i in res.insights if i.codigo == "CARGA_SUPERA_CAPACIDAD_REFERENCIA")
    assert "+3500 kg" in ins.titulo


def test_14_rule_flete_estimado_por_entrega():
    """Caso 14: FLETE_ESTIMADO_POR_ENTREGA calcula el costo de flete con la cotización vinculada."""
    quote_id = uuid4()
    deliv = GrainDeliveryContext(
        tracking_number="ENT-20260820-I9J0",
        freight_quote_id=quote_id,
        kg_neto_origen_total=Decimal("35000"),
        waybills=[],
    )
    dest_opt = DeliveryDestinationContext(
        destination_id=quote_id,
        destination_name="Puerto San Lorenzo",
        freight_usd_tn=Decimal("18.00"),
    )
    ctx = DecisionContext(deliveries=[deliv], delivery_options=[dest_opt])
    res = evaluar_motor_decisiones_detallado(ctx)

    codes = [ins.codigo for ins in res.insights]
    assert "FLETE_ESTIMADO_POR_ENTREGA" in codes
    ins = next(i for i in res.insights if i.codigo == "FLETE_ESTIMADO_POR_ENTREGA")
    assert "US$ 630.00" in ins.titulo


def test_15_empty_deliveries_context_does_not_fire_delivery_insights():
    """Caso 15: Si no hay entregas en el contexto, no se emiten reglas del dominio deliveries."""
    ctx = DecisionContext(deliveries=[])
    res = evaluar_motor_decisiones_detallado(ctx)
    deliv_insights = [ins for ins in res.insights if ins.domain == "deliveries"]
    assert len(deliv_insights) == 0
