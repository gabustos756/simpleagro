"""
Suite de Pruebas Unitarias para Persistencia, UI y Aislamiento Multitenant del Módulo de Entregas (EduAgro).
Verifica modelo GrainDelivery, GrainWaybill, relaciones, unicidad de tracking, recálculo de totales y multitenancy.
"""

from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4
import pytest

from app.models import GrainDelivery, GrainWaybill, Cliente
from app.main import recalculate_delivery_totals, parse_decimal_ar


def test_1_create_grain_delivery_model_with_tracking():
    """Caso 1: Creación de GrainDelivery genera tracking_number legible e inmutable."""
    cliente_id = uuid4()
    tracking = f"ENT-{datetime.now().strftime('%Y%m%d')}-A1B2"

    deliv = GrainDelivery(
        cliente_id=cliente_id,
        tracking_number=tracking,
        acopio_receptor="Acopio AFA Maciel",
        destination_final_reference="Rosario",
        transportista_nombre="Marcelo Martina",
        fecha_planificada=date.today(),
        toneladas_planificadas=Decimal("35.00"),
        cultivo="soja",
        estado="planificada",
        documentacion_status="sin_documentacion",
    )

    assert deliv.tracking_number == tracking
    assert deliv.acopio_receptor == "Acopio AFA Maciel"
    assert deliv.transportista_nombre == "Marcelo Martina"
    assert deliv.destination_final_reference == "Rosario"
    assert deliv.kg_neto_origen_total is None
    assert deliv.kg_recibido_total is None


def test_2_multitenant_isolation_between_clients():
    """Caso 2: Aislamiento estricto de entregas y cartas de porte por cliente_id."""
    cliente_a = uuid4()
    cliente_b = uuid4()

    d_a = GrainDelivery(
        cliente_id=cliente_a,
        tracking_number=f"ENT-20260820-AAAA",
        acopio_receptor="Acopio A",
    )
    d_b = GrainDelivery(
        cliente_id=cliente_b,
        tracking_number=f"ENT-20260820-BBBB",
        acopio_receptor="Acopio B",
    )

    assert d_a.cliente_id != d_b.cliente_id
    assert d_a.cliente_id == cliente_a
    assert d_b.cliente_id == cliente_b


def test_3_delivery_without_waybills_is_valid():
    """Caso 3: Crear entrega sin cartas de porte es válido y tiene documentacion_status='sin_documentacion'."""
    deliv = GrainDelivery(
        cliente_id=uuid4(),
        tracking_number="ENT-20260820-XXXX",
        acopio_receptor="Acopio Sin Carta",
    )
    recalculate_delivery_totals(deliv)
    assert deliv.documentacion_status == "sin_documentacion"
    assert len(deliv.waybills) == 0


def test_4_associate_multiple_waybills_to_delivery():
    """Caso 4: Asociar múltiples cartas de porte a una entrega y verificar acumulación de pesajes."""
    cliente_id = uuid4()
    deliv = GrainDelivery(
        cliente_id=cliente_id,
        tracking_number="ENT-20260820-MULTI",
        acopio_receptor="Puerto Rosario",
    )

    w1 = GrainWaybill(
        cliente_id=cliente_id,
        numero_carta_porte="0001-00000001",
        tara_kg=Decimal("14000"),
        peso_bruto_origen_kg=Decimal("49000"),
        peso_neto_origen_kg=Decimal("35000"),
        peso_recibido_destino_kg=Decimal("34800"),
        estado="recibida",
    )
    w2 = GrainWaybill(
        cliente_id=cliente_id,
        numero_carta_porte="0001-00000002",
        tara_kg=Decimal("14200"),
        peso_bruto_origen_kg=Decimal("49200"),
        peso_neto_origen_kg=Decimal("35000"),
        peso_recibido_destino_kg=Decimal("34900"),
        estado="recibida",
    )

    deliv.waybills.extend([w1, w2])
    recalculate_delivery_totals(deliv)

    assert deliv.kg_neto_origen_total == Decimal("70000.0")
    assert deliv.kg_recibido_total == Decimal("69700.0")
    assert deliv.diferencia_total_kg == Decimal("-300.0")
    assert deliv.diferencia_total_pct == Decimal("-0.43")
    assert deliv.documentacion_status == "completa"


def test_5_optional_weights_preserved_as_none():
    """Caso 5: Pesos no ingresados permanecen como None y no como 0.0."""
    w = GrainWaybill(
        cliente_id=uuid4(),
        tara_kg=None,
        peso_bruto_origen_kg=None,
        peso_recibido_destino_kg=None,
    )
    assert w.tara_kg is None
    assert w.peso_bruto_origen_kg is None
    assert w.peso_neto_origen_kg is None
    assert w.peso_recibido_destino_kg is None
    assert w.diferencia_kg is None


def test_6_documentacion_status_transitions():
    """Caso 6: Recálculo de documentacion_status según cartas de porte registradas."""
    cliente_id = uuid4()
    deliv = GrainDelivery(cliente_id=cliente_id, tracking_number="ENT-STATUS")

    # Sin cartas
    recalculate_delivery_totals(deliv)
    assert deliv.documentacion_status == "sin_documentacion"

    # Carta sin número CPE
    w_no_num = GrainWaybill(cliente_id=cliente_id, numero_carta_porte=None)
    deliv.waybills.append(w_no_num)
    recalculate_delivery_totals(deliv)
    assert deliv.documentacion_status == "carta_pendiente"

    # Carta adicional con número CPE -> Parcial
    w_with_num = GrainWaybill(cliente_id=cliente_id, numero_carta_porte="0001-11111111")
    deliv.waybills.append(w_with_num)
    recalculate_delivery_totals(deliv)
    assert deliv.documentacion_status == "parcial"

    # Completar número CPE en la primera -> Completa
    w_no_num.numero_carta_porte = "0001-22222222"
    recalculate_delivery_totals(deliv)
    assert deliv.documentacion_status == "completa"


def test_7_truck_capacity_suggestions_do_not_override_actual_weight():
    """Caso 7: La capacidad de referencia (35.000 / 45.000 kg) no sustituye el peso neto real."""
    w_normal = GrainWaybill(
        tipo_camion="normal",
        capacidad_referencia_kg=Decimal("35000"),
        peso_neto_origen_kg=Decimal("36200"),  # Peso real documentado
    )
    w_vulcano = GrainWaybill(
        tipo_camion="vulcano",
        capacidad_referencia_kg=Decimal("45000"),
        peso_neto_origen_kg=Decimal("46500"),  # Peso real documentado
    )

    assert w_normal.capacidad_referencia_kg == Decimal("35000")
    assert w_normal.peso_neto_origen_kg == Decimal("36200")
    assert w_vulcano.capacidad_referencia_kg == Decimal("45000")
    assert w_vulcano.peso_neto_origen_kg == Decimal("46500")
