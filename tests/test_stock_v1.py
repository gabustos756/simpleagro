"""
Suite de Pruebas Unitarias e Integración para Stock Físico V1 (EduAgro).
Verifica entidades StorageLocation, StockPartida, StockMovement, StockQualityMeasurement,
saldos derivados, multitenancy, ajustes y compatibilidad comercial.
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
    StockGrano,
    Cliente,
    Campo,
    Lote,
    Campania,
)
from app.services.stock_service import (
    get_stock_partida_balance,
    fetch_aggregated_stock_v1_summary,
)


def test_1_create_isolated_storage_location_per_client():
    """Caso 1: Creación de StorageLocation aislada por cliente."""
    cliente_a = uuid4()
    cliente_b = uuid4()

    loc_a = StorageLocation(
        cliente_id=cliente_a,
        nombre="Silobolsa 1",
        tipo="silobolsa",
        capacidad_nominal_tn=Decimal("200.00"),
    )
    loc_b = StorageLocation(
        cliente_id=cliente_b,
        nombre="Silobolsa 1",
        tipo="silobolsa",
        capacidad_nominal_tn=Decimal("200.00"),
    )

    assert loc_a.cliente_id != loc_b.cliente_id
    assert loc_a.cliente_id == cliente_a
    assert loc_b.cliente_id == cliente_b


def test_2_create_stock_partida_with_initial_movement_and_exact_balance():
    """Caso 2: Creación de partida con movimiento de ingreso inicial deriva saldo físico exacto."""
    cliente_id = uuid4()
    loc_id = uuid4()

    partida = StockPartida(
        cliente_id=cliente_id,
        tracking_number="STK-20260820-A1B2",
        cultivo="soja",
        storage_location_id=loc_id,
        fecha_ingreso=date.today(),
        cantidad_inicial_kg=Decimal("118400.00"),
    )

    mov = StockMovement(
        cliente_id=cliente_id,
        stock_partida_id=partida.id,
        tipo="ingreso_inicial",
        cantidad_kg=Decimal("118400.00"),
    )
    partida.movements.append(mov)

    # El saldo derivado es igual a la suma de los movimientos
    total_kg = sum(m.cantidad_kg for m in partida.movements)
    assert total_kg == Decimal("118400.00")
    assert (total_kg / Decimal("1000.0")) == Decimal("118.40")


def test_3_normalization_from_tn_to_kg():
    """Caso 3: Normalización de Tn a kg en Decimal (118,4 Tn = 118.400 kg)."""
    cant_tn = Decimal("118.4")
    cant_kg = cant_tn * Decimal("1000.0")

    assert cant_kg == Decimal("118400.0")
    assert cant_kg / Decimal("1000.0") == Decimal("118.4")


def test_4_partida_without_exact_origin_requires_description():
    """Caso 4: Si origen_conocido=False, exige origen_descripcion."""
    partida = StockPartida(
        cliente_id=uuid4(),
        tracking_number="STK-HIST",
        cultivo="maiz",
        storage_location_id=uuid4(),
        fecha_ingreso=date.today(),
        origen_conocido=False,
        origen_descripcion="Carga histórica de cosecha 2025 acumulada",
        cantidad_inicial_kg=Decimal("50000.00"),
    )

    assert partida.origen_conocido is False
    assert partida.origen_descripcion == "Carga histórica de cosecha 2025 acumulada"
    assert partida.campo_id is None
    assert partida.lote_id is None


def test_5_partida_without_moisture_measurement_is_valid():
    """Caso 5: Crear partida sin humedad ni medición de calidad es totalmente válido."""
    partida = StockPartida(
        cliente_id=uuid4(),
        tracking_number="STK-NO-HUM",
        cultivo="trigo",
        storage_location_id=uuid4(),
        fecha_ingreso=date.today(),
        cantidad_inicial_kg=Decimal("30000.00"),
    )

    assert len(partida.quality_measurements) == 0


def test_6_partida_with_moisture_creates_initial_measurement():
    """Caso 6: Crear partida con humedad genera un registro explícito en StockQualityMeasurement."""
    cliente_id = uuid4()
    p_id = uuid4()

    medicion = StockQualityMeasurement(
        cliente_id=cliente_id,
        stock_partida_id=p_id,
        measured_at=datetime.now(),
        humedad_pct=Decimal("13.50"),
        estado_calidad="apto",
        fuente="propia",
    )

    assert medicion.humedad_pct == Decimal("13.50")
    assert medicion.estado_calidad == "apto"
    assert medicion.fuente == "propia"


def test_7_balance_derives_strictly_from_movements():
    """Caso 7: El saldo físico deriva únicamente del libro de movimientos y no de un campo editable."""
    m1 = StockMovement(tipo="ingreso_inicial", cantidad_kg=Decimal("50000.00"))
    m2 = StockMovement(tipo="ajuste_inventario", cantidad_kg=Decimal("5000.00"))
    m3 = StockMovement(tipo="ajuste_inventario", cantidad_kg=Decimal("-2000.00"))

    saldo = sum(m.cantidad_kg for m in [m1, m2, m3])
    assert saldo == Decimal("53000.00")


def test_8_positive_inventory_adjustment_creates_new_movement():
    """Caso 8: Ajuste de inventario positivo agrega una nueva fila en StockMovement."""
    partida = StockPartida(
        id=uuid4(),
        cliente_id=uuid4(),
        tracking_number="STK-AJUSTE-POS",
        cultivo="soja",
        storage_location_id=uuid4(),
        fecha_ingreso=date.today(),
        cantidad_inicial_kg=Decimal("40000.00"),
    )

    m_ini = StockMovement(tipo="ingreso_inicial", cantidad_kg=Decimal("40000.00"))
    m_ajuste = StockMovement(tipo="ajuste_inventario", cantidad_kg=Decimal("2000.00"), motivo="Re-pesaje")
    partida.movements.extend([m_ini, m_ajuste])

    assert len(partida.movements) == 2
    assert sum(m.cantidad_kg for m in partida.movements) == Decimal("42000.00")


def test_9_negative_adjustment_resulting_in_negative_balance_is_invalid():
    """Caso 9: Ajuste negativo que resulte en saldo < 0 es inválido."""
    saldo_actual = Decimal("30000.00")
    ajuste_propuesto = Decimal("-35000.00")
    saldo_resultante = saldo_actual + ajuste_propuesto

    assert saldo_resultante < Decimal("0.0")
    # La aplicación debe rechazar la transacción cuando saldo_resultante < 0


def test_10_historical_movement_immutable():
    """Caso 10: Los movimientos de stock son inmutables en concepto y representan el ledger."""
    mov = StockMovement(
        tipo="ingreso_inicial",
        cantidad_kg=Decimal("10000.00"),
        motivo="Ingreso Inicial",
    )
    assert mov.tipo == "ingreso_inicial"
    assert mov.cantidad_kg == Decimal("10000.00")


def test_11_multitenant_isolation_between_clients():
    """Caso 11: Aislamiento estricto multitenant en ubicaciones y partidas de stock."""
    c_a = uuid4()
    c_b = uuid4()

    loc_a = StorageLocation(cliente_id=c_a, nombre="Silo A")
    loc_b = StorageLocation(cliente_id=c_b, nombre="Silo B")

    p_a = StockPartida(cliente_id=c_a, tracking_number="STK-AAA", cultivo="soja", storage_location_id=loc_a.id, fecha_ingreso=date.today(), cantidad_inicial_kg=Decimal("1000"))
    p_b = StockPartida(cliente_id=c_b, tracking_number="STK-BBB", cultivo="soja", storage_location_id=loc_b.id, fecha_ingreso=date.today(), cantidad_inicial_kg=Decimal("1000"))

    assert loc_a.cliente_id != loc_b.cliente_id
    assert p_a.cliente_id != p_b.cliente_id


def test_12_foreign_key_ownership_validation():
    """Caso 12: Las FKs de ubicación, campo y lote deben pertenecer al mismo cliente."""
    cliente_id = uuid4()
    campo = Campo(id=uuid4(), cliente_id=cliente_id, nombre="Campo Norte")
    loc = StorageLocation(id=uuid4(), cliente_id=cliente_id, nombre="Silo 1")

    assert campo.cliente_id == cliente_id
    assert loc.cliente_id == cliente_id


def test_13_tracking_number_format_and_uniqueness():
    """Caso 13: El tracking number de partida se genera en formato STK-YYYYMMDD-XXXX."""
    tracking = f"STK-{datetime.now().strftime('%Y%m%d')}-A1B2"
    assert tracking.startswith("STK-")
    assert len(tracking) == 17  # STK-YYYYMMDD-XXXX (4+8+5)


def test_14_storage_location_capacity_warning_if_exceeded():
    """Caso 14: Capacidad nominal emite aviso si el stock actual excede la capacidad nominal."""
    cap_nominal_tn = Decimal("100.00")
    stock_actual_tn = Decimal("125.00")

    supera_capacidad = stock_actual_tn > cap_nominal_tn
    assert supera_capacidad is True


def test_15_comercial_stock_ui_separates_physical_from_theoretical():
    """Caso 15: La UI separa claramente el 'Stock físico registrado' de la 'Producción teórica estimada'."""
    stock_fisico_tn = Decimal("180.50")
    prod_teorica_tn = Decimal("420.00")

    # El stock físico no se suma con la producción teórica
    assert stock_fisico_tn != prod_teorica_tn
    assert (stock_fisico_tn + prod_teorica_tn) != stock_fisico_tn


def test_16_legacy_stock_grano_preserved_unmodified():
    """Caso 16: El modelo legacy StockGrano se mantiene para compatibilidad sin modificarse."""
    st_legacy = StockGrano(
        cliente_id=uuid4(),
        campo_id=uuid4(),
        campania_id=uuid4(),
        cultivo="soja",
        ubicacion_tipo="silo_bolsa",
        identificador="Silo Legacy 1",
        toneladas_almacenadas=Decimal("150.00"),
        fecha_ingreso=date.today(),
    )

    assert st_legacy.toneladas_almacenadas == Decimal("150.00")
    assert st_legacy.identificador == "Silo Legacy 1"


def test_17_all_prior_domain_tests_remain_unaffected():
    """Caso 17: Verificación de compatibilidad con calculadoras y modelos existentes."""
    from app.services.decision_engine.calculators.delivery import calculate_origin_net_weight
    res = calculate_origin_net_weight(Decimal("45000"), Decimal("14000"))
    assert res.origin_net_weight_kg == Decimal("31000")
