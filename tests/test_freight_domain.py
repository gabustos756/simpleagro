"""
Suite de Pruebas Unitarias para el Dominio de Flete y Economía de Entregas Comercial (EduAgro).
Verifica los 13 casos de prueba obligatorios del dominio freight.
"""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest

from app.services.decision_engine import (
    DecisionEngine,
    DecisionContext,
    PolicyLayer,
    DecisionPolicyResolver,
)
from app.services.decision_engine.models import (
    DeliveryDestinationContext,
    RoadStatus,
    AvailabilityStatus,
    HarvestData,
)
from app.services.decision_engine.calculators.freight import (
    calculate_delivery_economics,
    DeliveryEconomicsResult,
)
from app.services.decision_engine.calculators.delivery_economics import (
    evaluate_destination_eligibility,
    rank_delivery_options,
)


def test_1_exact_net_price_calculation_with_decimal():
    """Caso 1: Cálculo exacto de precio neto en origen usando Decimal (precio - flete - reacondicionamiento - otros)."""
    dest = DeliveryDestinationContext(
        destination_name="Puerto Rosario",
        price_usd_tn=Decimal("200.00"),
        freight_usd_tn=Decimal("15.50"),
        conditioning_cost_usd_tn=Decimal("3.00"),
        other_costs_usd_tn=Decimal("1.50"),
    )
    econ = calculate_delivery_economics(dest)

    assert econ.is_net_price_fully_calculated is True
    assert econ.total_deductions_usd_tn == Decimal("20.00")
    assert econ.net_origin_price_usd_tn == Decimal("180.00")


def test_2_missing_costs_do_not_become_zero():
    """Caso 2: Costos faltantes no se convierten a cero y marcan is_net_price_fully_calculated = False."""
    dest = DeliveryDestinationContext(
        destination_name="Acopio Local",
        price_usd_tn=Decimal("190.00"),
        freight_usd_tn=None,  # Falta flete
    )
    econ = calculate_delivery_economics(dest)

    assert econ.is_net_price_fully_calculated is False
    assert econ.net_origin_price_usd_tn is None
    assert "freight_usd_tn" in econ.missing_cost_fields


def test_3_impassable_road_makes_destination_not_eligible():
    """Caso 3: Camino 'impassable' marca el destino como not_eligible."""
    dest = DeliveryDestinationContext(
        destination_name="Planta San Francisco",
        road_status=RoadStatus.IMPASSABLE,
    )
    elig = evaluate_destination_eligibility(dest)

    assert elig.eligibility_status == "not_eligible"
    assert "DESTINO_NO_APTO_POR_CAMINO" in elig.reasons


def test_4_unknown_receiving_makes_destination_conditionally_eligible():
    """Caso 4: Recepción o cupo 'unknown' marca el destino como conditionally_eligible."""
    dest = DeliveryDestinationContext(
        destination_name="Acopio Norte",
        receiving_confirmed=AvailabilityStatus.UNKNOWN,
    )
    elig = evaluate_destination_eligibility(dest)

    assert elig.eligibility_status == "conditionally_eligible"
    assert "DESTINO_SIN_CUPO_CONFIRMADO" in elig.reasons


def test_5_moisture_exceeding_max_receiving_moisture():
    """Caso 5: Humedad de grano superior a la máxima de recepción marca conditionally_eligible."""
    dest = DeliveryDestinationContext(
        destination_name="Fábrica Bunge",
        max_receiving_moisture_pct=Decimal("15.0"),
    )
    elig = evaluate_destination_eligibility(dest, grain_moisture_pct=17.5)

    assert elig.eligibility_status == "conditionally_eligible"
    assert "HUMEDAD_SUPERA_RECEPCION" in elig.reasons


def test_6_stale_quote_evaluation():
    """Caso 6: Cotización vencida se marca is_quote_stale = True y dispara COTIZACION_FLETE_DESACTUALIZADA."""
    past_date = datetime.now() - timedelta(hours=50)
    dest = DeliveryDestinationContext(
        destination_name="Puerto San Lorenzo",
        price_usd_tn=Decimal("210.00"),
        freight_usd_tn=Decimal("18.00"),
        quote_observed_at=past_date,
    )
    ctx = DecisionContext(delivery_options=[dest])
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    codes = [ins.codigo for ins in result.insights]
    assert "COTIZACION_FLETE_DESACTUALIZADA" in codes


def test_6b_timezone_aware_datetime_comparison():
    """Caso 6b: Comparación segura entre datetimes timezone-aware (DB/UTC) y timezone-naive."""
    from datetime import timezone
    tz_aware_past = datetime.now(timezone.utc) - timedelta(hours=60)
    dest = DeliveryDestinationContext(
        destination_name="Puerto Quequén",
        price_usd_tn=Decimal("200.00"),
        freight_usd_tn=Decimal("15.00"),
        quote_observed_at=tz_aware_past,
    )
    econ = calculate_delivery_economics(dest)
    assert econ.is_quote_stale is True


def test_7_ranking_sorts_by_net_origin_price_descending():
    """Caso 7: Ranking ordena por precio neto descendente sólo entre alternativas aptas y completas."""
    d1 = DeliveryDestinationContext(destination_name="Destino A", price_usd_tn=Decimal("200.00"), freight_usd_tn=Decimal("20.00"), receiving_confirmed=AvailabilityStatus.AVAILABLE)  # Neto: 180
    d2 = DeliveryDestinationContext(destination_name="Destino B", price_usd_tn=Decimal("205.00"), freight_usd_tn=Decimal("15.00"), receiving_confirmed=AvailabilityStatus.AVAILABLE)  # Neto: 190

    ranked = rank_delivery_options([d1, d2])

    assert ranked.best_option is not None
    assert ranked.best_option.destination_name == "Destino B"
    assert ranked.best_option.net_origin_price_usd_tn == Decimal("190.00")
    assert ranked.is_best_option_material is True
    assert ranked.net_difference_usd_tn == Decimal("10.00")


def test_8_incomplete_destination_does_not_win_over_complete_destination():
    """Caso 8: Destino con datos incompletos no gana sobre uno completo sólo por mayor precio bruto."""
    d_incompleto = DeliveryDestinationContext(destination_name="Destino Incompleto", price_usd_tn=Decimal("250.00"), freight_usd_tn=None)
    d_completo = DeliveryDestinationContext(destination_name="Destino Completo", price_usd_tn=Decimal("190.00"), freight_usd_tn=Decimal("10.00"))  # Neto 180

    ranked = rank_delivery_options([d_incompleto, d_completo])

    assert ranked.best_option is not None
    assert ranked.best_option.destination_name == "Destino Completo"


def test_9_net_difference_below_threshold_triggers_immaterial_difference():
    """Caso 9: Diferencia menor o igual al umbral genera SIN_DIFERENCIA_NETA_MATERIAL_ENTRE_DESTINOS."""
    d1 = DeliveryDestinationContext(destination_name="Acopio X", price_usd_tn=Decimal("200.00"), freight_usd_tn=Decimal("10.00"), receiving_confirmed=AvailabilityStatus.AVAILABLE)  # Neto 190.00
    d2 = DeliveryDestinationContext(destination_name="Acopio Y", price_usd_tn=Decimal("200.50"), freight_usd_tn=Decimal("10.00"), receiving_confirmed=AvailabilityStatus.AVAILABLE)  # Neto 190.50

    ctx = DecisionContext(delivery_options=[d1, d2])
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    codes = [ins.codigo for ins in result.insights]
    assert "SIN_DIFERENCIA_NETA_MATERIAL_ENTRE_DESTINOS" in codes
    assert "DESTINO_NETO_MAS_CONVENIENTE" not in codes


def test_10_insufficient_data_for_destination_comparison():
    """Caso 10: Menos de dos opciones elegibles con neto completo produce DATOS_INSUFICIENTES_PARA_COMPARAR_DESTINOS."""
    d1 = DeliveryDestinationContext(destination_name="Acopio Único", price_usd_tn=Decimal("200.00"), freight_usd_tn=Decimal("10.00"))

    ctx = DecisionContext(delivery_options=[d1])
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    codes = [ins.codigo for ins in result.insights]
    assert "DATOS_INSUFICIENTES_PARA_COMPARAR_DESTINOS" in codes


def test_11_empty_delivery_options_produces_no_freight_insights():
    """Caso 11: Con delivery_options = [], no se genera ningún insight del dominio freight."""
    ctx = DecisionContext(delivery_options=[])
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    freight_insights = [i for i in result.insights if i.domain == "freight"]
    assert len(freight_insights) == 0


def test_12_hierarchical_policy_override_for_freight():
    """Caso 12: Prueba de política jerárquica para max_quote_age_hours."""
    l_base = PolicyLayer(scope="system_base", policy_data={"freight": {"max_quote_age_hours": 48}})
    l_override = PolicyLayer(scope="run_override", policy_data={"freight": {"max_quote_age_hours": 24}})

    resolver = DecisionPolicyResolver(layers=[l_base, l_override])
    eff = resolver.resolve()

    val = eff["freight.max_quote_age_hours"]
    assert val.value == 24
    assert val.source_scope == "run_override"


def test_13_best_destination_recommendation_rule():
    """Caso 13: DESTINO_NETO_MAS_CONVENIENTE se dispara cuando existe una opción significativamente mejor."""
    d1 = DeliveryDestinationContext(destination_name="Puerto A", price_usd_tn=Decimal("220.00"), freight_usd_tn=Decimal("15.00"), receiving_confirmed=AvailabilityStatus.AVAILABLE)  # Neto: 205
    d2 = DeliveryDestinationContext(destination_name="Acopio B", price_usd_tn=Decimal("200.00"), freight_usd_tn=Decimal("10.00"), receiving_confirmed=AvailabilityStatus.AVAILABLE)  # Neto: 190

    ctx = DecisionContext(delivery_options=[d1, d2])
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    codes = [ins.codigo for ins in result.insights]
    assert "DESTINO_NETO_MAS_CONVENIENTE" in codes
    ins = next(i for i in result.insights if i.codigo == "DESTINO_NETO_MAS_CONVENIENTE")
    assert "Puerto A" in ins.titulo
    assert "La alternativa con mayor valor neto estimado" in ins.mensaje
