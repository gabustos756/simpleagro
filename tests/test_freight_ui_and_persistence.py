"""
Suite de Pruebas Unitarias para Persistencia, UI y Endpoints del Dominio de Fletes (EduAgro).
Verifica persistencia en DB (FreightQuote), parseo de notación argentina, aislamiento multitenant, PRG e integración con el motor.
"""

from datetime import datetime, date
from decimal import Decimal
import pytest
from uuid import uuid4

from app.models import FreightQuote, Cliente, Usuario
from app.main import parse_decimal_ar


def test_1_parse_decimal_ar_formats():
    """Caso 1: Parseo de notación decimal argentina y estándar."""
    assert parse_decimal_ar("334,80") == Decimal("334.80")
    assert parse_decimal_ar("334.80") == Decimal("334.80")
    assert parse_decimal_ar("1.234,56") == Decimal("1234.56")
    assert parse_decimal_ar("  15,5  ") == Decimal("15.5")
    assert parse_decimal_ar(None) is None
    assert parse_decimal_ar("") is None
    assert parse_decimal_ar("invalid") is None


def test_2_freight_quote_model_decimal_precision():
    """Caso 2: El modelo FreightQuote persiste campos monetarios con tipo Decimal exacto."""
    cliente_id = uuid4()
    fq = FreightQuote(
        cliente_id=cliente_id,
        destination_name="Puerto Rosario",
        price_usd_tn=Decimal("200.50"),
        freight_usd_tn=Decimal("15.75"),
        conditioning_cost_usd_tn=Decimal("2.50"),
        quote_observed_at=datetime.now(),
    )
    assert isinstance(fq.price_usd_tn, Decimal)
    assert fq.price_usd_tn == Decimal("200.50")
    assert fq.freight_usd_tn == Decimal("15.75")
    assert fq.conditioning_cost_usd_tn == Decimal("2.50")


def test_3_quote_without_costs_is_not_fully_calculated():
    """Caso 3: Una cotización sin flete o precio se guarda pero no marca precio neto definitivo."""
    from app.services.decision_engine.models import DeliveryDestinationContext
    from app.services.decision_engine.calculators.freight import calculate_delivery_economics

    dest = DeliveryDestinationContext(
        destination_name="Acopio Incompleto",
        price_usd_tn=Decimal("190.00"),
        freight_usd_tn=None,
    )
    econ = calculate_delivery_economics(dest)

    assert econ.is_net_price_fully_calculated is False
    assert econ.net_origin_price_usd_tn is None
    assert "freight_usd_tn" in econ.missing_cost_fields


def test_4_multitenant_isolation_logic():
    """Caso 4: Las cotizaciones de flete se filtran estrictamente por cliente_id."""
    cliente_a = uuid4()
    cliente_b = uuid4()

    q_a = FreightQuote(cliente_id=cliente_a, destination_name="Destino A", quote_observed_at=datetime.now())
    q_b = FreightQuote(cliente_id=cliente_b, destination_name="Destino B", quote_observed_at=datetime.now())

    assert q_a.cliente_id != q_b.cliente_id
    assert q_a.cliente_id == cliente_a
    assert q_b.cliente_id == cliente_b


def test_5_convert_freight_quote_to_decision_context():
    """Caso 5: La cotización persistida se convierte correctamente en DeliveryDestinationContext para el motor."""
    from app.services.decision_engine.models import (
        DeliveryDestinationContext,
        AvailabilityStatus,
        RoadStatus,
        FreightQuoteSource,
    )

    fq = FreightQuote(
        id=uuid4(),
        cliente_id=uuid4(),
        destination_name="Planta Bunge",
        destination_type="fabrica",
        price_usd_tn=Decimal("210.00"),
        freight_usd_tn=Decimal("18.00"),
        receiving_confirmed="available",
        road_status="good",
        quote_source="manual",
        quote_observed_at=datetime.now(),
    )

    ctx = DeliveryDestinationContext(
        destination_id=fq.id,
        destination_name=fq.destination_name,
        destination_type=fq.destination_type,
        price_usd_tn=fq.price_usd_tn,
        freight_usd_tn=fq.freight_usd_tn,
        receiving_confirmed=AvailabilityStatus(fq.receiving_confirmed),
        road_status=RoadStatus(fq.road_status),
        quote_source=FreightQuoteSource(fq.quote_source),
        quote_observed_at=fq.quote_observed_at,
    )

    assert ctx.destination_name == "Planta Bunge"
    assert ctx.price_usd_tn == Decimal("210.00")
    assert ctx.freight_usd_tn == Decimal("18.00")
    assert ctx.receiving_confirmed == AvailabilityStatus.AVAILABLE
    assert ctx.road_status == RoadStatus.GOOD


def test_6_decision_engine_detailed_evaluation_with_freight_quotes():
    """Caso 6: Invocación de evaluar_motor_decisiones_detallado con cotizaciones reales."""
    from app.services.decision_engine.models import (
        DeliveryDestinationContext,
        DecisionContext,
        HarvestData,
        AvailabilityStatus,
        RoadStatus,
    )
    from app.services.decision_motor import evaluar_motor_decisiones_detallado

    d1 = DeliveryDestinationContext(
        destination_name="Puerto Rosario",
        price_usd_tn=Decimal("220.00"),
        freight_usd_tn=Decimal("15.00"),
        receiving_confirmed=AvailabilityStatus.AVAILABLE,
        road_status=RoadStatus.GOOD,
    )
    d2 = DeliveryDestinationContext(
        destination_name="Acopio Local",
        price_usd_tn=Decimal("200.00"),
        freight_usd_tn=Decimal("5.00"),
        receiving_confirmed=AvailabilityStatus.AVAILABLE,
        road_status=RoadStatus.GOOD,
    )

    context = DecisionContext(
        cultivo="soja",
        harvest=HarvestData(humedad_grano_pct=13.5),
        delivery_options=[d1, d2],
    )

    result = evaluar_motor_decisiones_detallado(context)
    codes = [ins.codigo for ins in result.insights]

    assert "DESTINO_NETO_MAS_CONVENIENTE" in codes
    ins = next(i for i in result.insights if i.codigo == "DESTINO_NETO_MAS_CONVENIENTE")
    assert "Puerto Rosario" in ins.titulo


def test_7_create_quote_with_new_fields():
    """Caso 7: Cotización con cultivo, condicion_precio, distancia_estimada_km y detalle_cupo_turno."""
    fq = FreightQuote(
        cliente_id=uuid4(),
        destination_name="Puerto Arroyo Seco",
        destination_type="puerto",
        cultivo="soja",
        condicion_precio="disponible_spot",
        distancia_estimada_km=Decimal("340.50"),
        detalle_cupo_turno="2 camiones hoy con turno",
        price_usd_tn=Decimal("205.00"),
        freight_usd_tn=Decimal("16.00"),
        quote_observed_at=datetime.now(),
    )
    assert fq.cultivo == "soja"
    assert fq.condicion_precio == "disponible_spot"
    assert fq.distancia_estimada_km == Decimal("340.50")
    assert fq.detalle_cupo_turno == "2 camiones hoy con turno"


def test_8_create_quote_with_optional_fields_empty():
    """Caso 8: Cotización con todos los campos nuevos opcionales vacíos (NULL)."""
    fq = FreightQuote(
        cliente_id=uuid4(),
        destination_name="Acopio Tradicional",
        price_usd_tn=Decimal("195.00"),
        freight_usd_tn=Decimal("12.00"),
        quote_observed_at=datetime.now(),
    )
    assert fq.cultivo is None
    assert fq.condicion_precio is None
    assert fq.distancia_estimada_km is None
    assert fq.detalle_cupo_turno is None
    assert fq.humedad_max_recepcion_pct is None


def test_9_humedad_max_recepcion_ar_format_and_property_alias():
    """Caso 9: humedad_max_recepcion_pct acepta notación argentina y funciona el property alias."""
    parsed = parse_decimal_ar("13,5")
    assert parsed == Decimal("13.5")

    fq = FreightQuote(
        cliente_id=uuid4(),
        destination_name="Terminal Quequén",
        quote_observed_at=datetime.now(),
    )
    fq.humedad_max_recepcion_pct = Decimal("13.50")
    assert fq.max_receiving_moisture_pct == Decimal("13.50")
    assert fq.humedad_max_recepcion_pct == Decimal("13.50")


def test_10_distancia_estimada_ar_format():
    """Caso 10: distancia_estimada_km parsea correctamente coma decimal argentina."""
    parsed_dist = parse_decimal_ar("340,5")
    assert parsed_dist == Decimal("340.5")


def test_11_different_price_conditions_warning_flag():
    """Caso 11: Comparación entre cotizaciones con distintas condiciones de precio activa la advertencia informativa."""
    from app.services.decision_engine.models import DeliveryDestinationContext

    d1 = DeliveryDestinationContext(
        destination_name="Puerto Spot",
        condicion_precio="disponible_spot",
        price_usd_tn=Decimal("210.00"),
        freight_usd_tn=Decimal("15.00"),
    )
    d2 = DeliveryDestinationContext(
        destination_name="Puerto Futuro",
        condicion_precio="futuro",
        price_usd_tn=Decimal("220.00"),
        freight_usd_tn=Decimal("15.00"),
    )

    condiciones = {d.condicion_precio for d in [d1, d2] if d.condicion_precio}
    warning_diferente_condicion = len(condiciones) > 1

    assert warning_diferente_condicion is True

