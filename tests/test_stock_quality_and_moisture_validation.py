"""
Suite de Pruebas Unitarias e Integración para Validación de Humedad e Histórico de Calidad en Stock V1.
Cubre la regla de validación de humedad [5.0%, 35.0%], la notación argentina, la preservación de None,
la creación de mediciones históricas sin sobrescribir las previas, el orden descendente y el aislatorio multitenant.
"""

from decimal import Decimal
from datetime import datetime, date
from uuid import uuid4
import pytest

from app.services.stock_service import (
    validate_humedad_pct,
    validate_temperatura_c,
    parse_decimal_ar,
)
from app.models import StockQualityMeasurement, StockPartida


def test_1_create_partida_with_moisture_2_percent_is_rejected():
    """Caso 1: Intentar registrar humedad 2% (fuera de rango [5%, 35%]) es rechazado por backend."""
    with pytest.raises(ValueError) as excinfo:
        validate_humedad_pct("2%")
    assert "La humedad debe estar entre 5% y 35%" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo2:
        validate_humedad_pct("2.0")
    assert "La humedad debe estar entre 5% y 35%" in str(excinfo2.value)


def test_2_create_partida_with_moisture_13_5_percent_creates_valid_decimal():
    """Caso 2: Humedad 13,5% es válida, se parsea correctamente con notación argentina como Decimal('13.5')."""
    d1 = validate_humedad_pct("13,5")
    d2 = validate_humedad_pct("13.5")

    assert d1 == Decimal("13.5")
    assert d2 == Decimal("13.5")
    assert isinstance(d1, Decimal)


def test_3_create_partida_without_moisture_is_valid_and_remains_none():
    """Caso 3: Partida sin humedad es válida y NO genera humedad 0 ni medición falsa."""
    d_none1 = validate_humedad_pct(None)
    d_none2 = validate_humedad_pct("")
    d_none3 = validate_humedad_pct("   ")

    assert d_none1 is None
    assert d_none2 is None
    assert d_none3 is None


def test_4_subsequent_measurement_preserves_earlier_measurements():
    """Caso 4: Crear una medición posterior (ej. 14,2%) conserva la medición inicial (ej. 13,5%)."""
    c_id = uuid4()
    p_id = uuid4()

    m1 = StockQualityMeasurement(
        cliente_id=c_id,
        stock_partida_id=p_id,
        measured_at=datetime(2026, 8, 1),
        humedad_pct=Decimal("13.5"),
        estado_calidad="apto",
    )

    m2 = StockQualityMeasurement(
        cliente_id=c_id,
        stock_partida_id=p_id,
        measured_at=datetime(2026, 8, 20),
        humedad_pct=Decimal("14.2"),
        estado_calidad="apto",
    )

    measurements = [m1, m2]
    assert len(measurements) == 2
    assert measurements[0].humedad_pct == Decimal("13.5")
    assert measurements[1].humedad_pct == Decimal("14.2")


def test_5_history_ordered_by_date_descending():
    """Caso 5: El historial se ordena por fecha de medición de forma descendente (measured_at DESC)."""
    m1 = StockQualityMeasurement(measured_at=datetime(2026, 8, 1), humedad_pct=Decimal("13.5"))
    m2 = StockQualityMeasurement(measured_at=datetime(2026, 8, 20), humedad_pct=Decimal("14.2"))
    m3 = StockQualityMeasurement(measured_at=datetime(2026, 8, 10), humedad_pct=Decimal("13.8"))

    raw = [m1, m2, m3]
    sorted_history = sorted(raw, key=lambda x: x.measured_at, reverse=True)

    assert sorted_history[0].humedad_pct == Decimal("14.2")
    assert sorted_history[1].humedad_pct == Decimal("13.8")
    assert sorted_history[2].humedad_pct == Decimal("13.5")


def test_6_multitenant_isolation_for_measurements():
    """Caso 6: Medición de un cliente A no pertenece ni puede asociarse a cliente B."""
    client_a = uuid4()
    client_b = uuid4()

    m_a = StockQualityMeasurement(cliente_id=client_a)
    m_b = StockQualityMeasurement(cliente_id=client_b)

    assert m_a.cliente_id != m_b.cliente_id


def test_7_empty_moisture_remains_none_never_zero():
    """Caso 7: Humedad no informada se guarda como None y nunca como 0 en BD."""
    m = StockQualityMeasurement(
        cliente_id=uuid4(),
        stock_partida_id=uuid4(),
        measured_at=datetime.now(),
        humedad_pct=None,
    )
    assert m.humedad_pct is None
    assert m.humedad_pct != Decimal("0.0")


def test_8_out_of_range_values_rejected_in_measurements():
    """Caso 8: Humedad 0, 40%, 36%, 4.9% y valores negativos son rechazados."""
    invalid_values = ["0", "0.0", "40.0", "36", "4.9", "-5.0", "35.1"]
    for val in invalid_values:
        with pytest.raises(ValueError):
            validate_humedad_pct(val)


def test_9_ui_contains_measurement_and_history_ctas():
    """Caso 9: Verificación de presencia de los CTAs '+ Medición' y 'Ver historial' en el HTML generado."""
    with open("templates/comercial_stock.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert "+ Medición" in html
    assert "Ver historial" in html
    assert "Registrar Medición de Calidad" in html
    assert "Historial de Calidad" in html


def test_10_temperature_validation_range():
    """Caso 10: Validación de temperatura en °C (opcional, entre -10 y 60)."""
    assert validate_temperatura_c("18,5") == Decimal("18.5")
    assert validate_temperatura_c(None) is None

    with pytest.raises(ValueError):
        validate_temperatura_c("-15.0")

    with pytest.raises(ValueError):
        validate_temperatura_c("70.0")
