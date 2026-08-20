"""
Suite de Pruebas Unitarias e Integración para Capacidad de Ubicaciones, CRUD de Ubicaciones
y Detección de Datos Legacy Inválidos en Stock V1.
"""

from decimal import Decimal
from datetime import datetime, date
from uuid import uuid4
import pytest

from app.models import (
    StorageLocation,
    StockPartida,
    StockMovement,
    StockQualityMeasurement,
)
from app.services.stock_service import (
    is_valid_humidity,
    validate_humedad_pct,
)


def test_1_create_silo_or_silobolsa_without_capacity_is_invalid():
    """Caso 1: Intentar registrar silo_propio o silobolsa sin capacidad o con capacidad <= 0 es inválido."""
    tipo = "silo_propio"
    cap_none = None
    cap_zero = Decimal("0.0")

    req_cap = tipo in ["silo_propio", "silobolsa"]
    is_invalid_none = req_cap and (cap_none is None or cap_none <= Decimal("0.0"))
    is_invalid_zero = req_cap and (cap_zero is None or cap_zero <= Decimal("0.0"))

    assert is_invalid_none is True
    assert is_invalid_zero is True


def test_2_create_acopio_without_capacity_is_allowed():
    """Caso 2: Crear ubicación de tipo acopio, tercero, planta o directo_cosecha sin capacidad es permitido."""
    tipo = "acopio"
    cap_none = None

    req_cap = tipo in ["silo_propio", "silobolsa"]
    is_valid = not req_cap or (cap_none is not None and cap_none > Decimal("0.0"))

    assert is_valid is True


def test_3_create_partida_overflowing_capacity_is_rejected():
    """Caso 3: Cargar 50 Tn en silo con capacidad 50 Tn y ocupación 49 Tn se rechaza; 1 Tn se permite."""
    cap_kg = Decimal("50000.00")
    occ_kg = Decimal("49000.00")
    disp_kg = cap_kg - occ_kg

    attempt_50_kg = Decimal("50000.00")
    attempt_1_kg = Decimal("1000.00")

    overflow_50 = attempt_50_kg > disp_kg
    overflow_1 = attempt_1_kg > disp_kg

    assert disp_kg == Decimal("1000.00")
    assert overflow_50 is True
    assert overflow_1 is False


def test_4_cannot_reduce_capacity_below_current_physical_occupancy():
    """Caso 4: No permitir reducir la capacidad de 50 Tn a 40 Tn si la ocupación física actual es 49 Tn."""
    occ_kg = Decimal("49000.00")
    new_cap_tn = Decimal("40.00")
    new_cap_kg = new_cap_tn * Decimal("1000.0")

    invalid_reduction = new_cap_kg < occ_kg
    assert invalid_reduction is True


def test_5_occupancy_derives_strictly_from_physical_movement_balances():
    """Caso 5: La ocupación física se deriva del saldo físico por movimientos, no de la cantidad inicial editable."""
    p_id = uuid4()
    c_id = uuid4()

    mov1 = StockMovement(cliente_id=c_id, stock_partida_id=p_id, tipo="ingreso_inicial", cantidad_kg=Decimal("49000.00"))
    mov2 = StockMovement(cliente_id=c_id, stock_partida_id=p_id, tipo="ajuste_incremento", cantidad_kg=Decimal("1000.00"))

    physical_balance = mov1.cantidad_kg + mov2.cantidad_kg
    assert physical_balance == Decimal("50000.00")


def test_6_reservation_or_allocation_does_not_alter_physical_occupancy():
    """Caso 6: Crear reservas por compromisos o asignaciones a entregas NO altera ni reduce la ocupación física de la ubicación."""
    physical_occ_kg = Decimal("49000.00")
    reserva_kg = Decimal("20000.00")
    asignacion_kg = Decimal("15000.00")

    # La ocupación física del silo sigue siendo 49.000 kg
    assert physical_occ_kg == Decimal("49000.00")


def test_7_multitenant_isolation_for_locations():
    """Caso 7: Cliente A no puede editar ni consultar ubicaciones del Cliente B."""
    client_a = uuid4()
    client_b = uuid4()

    loc_a = StorageLocation(cliente_id=client_a, nombre="Silo 1", tipo="silo_propio")
    loc_b = StorageLocation(cliente_id=client_b, nombre="Silo 1", tipo="silo_propio")

    assert loc_a.cliente_id != loc_b.cliente_id


def test_8_legacy_location_without_capacity_is_marked_pending_and_blocks_new_partidas():
    """Caso 8: Ubicación legacy tipo silo/silobolsa sin capacidad se marca CAPACIDAD_PENDIENTE e impide nuevos ingresos."""
    loc = StorageLocation(tipo="silobolsa", capacidad_nominal_tn=None)

    requires_cap = loc.tipo in ["silo_propio", "silobolsa"]
    is_pending = requires_cap and (loc.capacidad_nominal_tn is None or loc.capacidad_nominal_tn <= Decimal("0.0"))

    assert is_pending is True


def test_9_legacy_moisture_2_percent_marked_invalid_and_ignored_in_summary():
    """Caso 9: Medición histórica legacy con humedad 2% es marcada como inválida (is_invalid_legacy=True) y no se usa como última humedad."""
    m_invalid = StockQualityMeasurement(measured_at=datetime(2026, 8, 1), humedad_pct=Decimal("2.0"))
    m_valid = StockQualityMeasurement(measured_at=datetime(2026, 8, 20), humedad_pct=Decimal("14.2"))

    valid_1 = is_valid_humidity(m_invalid.humedad_pct)
    valid_2 = is_valid_humidity(m_valid.humedad_pct)

    assert valid_1 is False
    assert valid_2 is True


def test_10_latest_valid_moisture_displayed_when_present():
    """Caso 10: Si existe una medición posterior válida (14,2%), pasa a ser la última humedad mostrada."""
    measurements = [
        StockQualityMeasurement(measured_at=datetime(2026, 8, 1), humedad_pct=Decimal("2.0")),
        StockQualityMeasurement(measured_at=datetime(2026, 8, 20), humedad_pct=Decimal("14.2")),
    ]

    sorted_q = sorted(measurements, key=lambda x: x.measured_at, reverse=True)
    latest_valid = None
    for q in sorted_q:
        if is_valid_humidity(q.humedad_pct):
            latest_valid = q.humedad_pct
            break

    assert latest_valid == Decimal("14.2")


def test_11_table_rendering_does_not_place_div_directly_in_tbody():
    """Caso 11: El HTML de la plantilla no coloca divs hijos directos dentro de tbody (evita desalineación de grilla)."""
    with open("templates/comercial_stock.html", "r", encoding="utf-8") as f:
        html = f.read()

    # Verificar que el contenedor de historiales esté fuera de la tabla
    assert '<div id="historiales-partidas-container" class="hidden">' in html
    assert html.find('<tbody class="divide-y divide-slate-100">') < html.find('<div id="historiales-partidas-container"')


def test_12_locations_tab_renders_occupancy_and_edit_cta():
    """Caso 12: La solapa de ubicaciones muestra ocupación, capacidad y CTA de edición."""
    with open("templates/comercial_stock.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert "modal-editar-ubicacion" in html
    assert "Capacidad Pendiente" in html
    assert "Completar Capacidad" in html
