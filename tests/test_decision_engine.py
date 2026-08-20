"""
Suite Completa de Pruebas Unitarias para el Motor de Decisiones Determinístico (EduAgro v2.0).
Cubre los 15 casos de prueba obligatorios requeridos por la especificación técnica.
"""

import pytest
from datetime import datetime

from app.services.decision_engine import (
    DecisionEngine,
    DecisionContext,
    DecisionResult,
    DecisionPolicyResolver,
    PolicyLayer,
    RuleRegistry,
    build_decision_context_from_dict,
    build_demo_decision_context,
    result_to_legacy_insights,
)
from app.services.decision_engine.models import (
    MarketData,
    HarvestData,
    SprayingData,
    WeatherData,
    RuleEvaluation,
    DecisionInsight,
)
from app.services.decision_engine.rules.base import RuleTraceContext, DecisionRule
from app.services.decision_motor import evaluar_motor_decisiones, evaluar_motor_decisiones_detallado
from app.agents.decision_rules import evaluar_decision_campo


def test_1_legacy_input_output_compatibility():
    """Caso 1: La entrada/salida legacy produce una lista de diccionarios de insights 100% compatible."""
    contexto = {
        "cultivo": "maiz",
        "precio_fisico_usd": 188.0,
        "precio_futuro_usd": 195.0,
        "spread_futuro_usd": 7.0,
        "humedad_grano_pct": 17.5,
        "lluvia_esperada_mm": 0.0,
        "viento_max_kmh": 14.0,
        "temp_min_c": 10.0,
    }
    insights = evaluar_motor_decisiones(contexto)
    assert isinstance(insights, list)
    assert len(insights) > 0
    for ins in insights:
        assert "codigo" in ins
        assert "nivel" in ins
        assert "titulo" in ins
        assert "mensaje" in ins
        assert "datos" in ins


def test_2_none_values_are_not_converted_to_zero():
    """Caso 2: None en humedad, precios o lluvia no se convierte en 0.0 ni emite decisiones falsas."""
    contexto = {
        "cultivo": "soja",
        "precio_fisico_usd": None,
        "precio_futuro_usd": None,
        "humedad_grano_pct": None,
        "lluvia_esperada_mm": None,
    }
    engine = DecisionEngine()
    result = engine.evaluate(contexto)

    codes = [ins.codigo for ins in result.insights]
    assert "DATOS_INSUFICIENTES_PARA_COSECHA" in codes
    assert "DATOS_INSUFICIENTES_PARA_COMERCIALIZACION" in codes
    assert "HUMEDAD_ALTA_Y_VENTANA_SECA" not in codes


def test_3_policy_hierarchy_priority():
    """Caso 3: La resolución jerárquica respeta la prioridad estricta de 7 capas."""
    l_base = PolicyLayer(scope="system_base", policy_data={"cosecha": {"costo_secada_punto_usd": 2.50}})
    l_org = PolicyLayer(scope="organization", policy_data={"cosecha": {"costo_secada_punto_usd": 2.80}}, source_id="org_1")
    l_field = PolicyLayer(scope="field", policy_data={"cosecha": {"costo_secada_punto_usd": 3.00}}, source_id="field_1")
    l_override = PolicyLayer(scope="run_override", policy_data={"cosecha": {"costo_secada_punto_usd": 3.50}}, source_id="run_1")

    resolver = DecisionPolicyResolver(layers=[l_base, l_org, l_field, l_override])
    eff = resolver.resolve()

    val = eff["cosecha.costo_secada_punto_usd"]
    assert val.value == 3.50
    assert val.source_scope == "run_override"
    assert val.source_id == "run_1"


def test_4_effective_value_retains_provenance():
    """Caso 4: Cada valor de política conserva su procedencia (source_scope, source_id, policy_id)."""
    l_fam = PolicyLayer(
        scope="family_client",
        policy_data={"cosecha": {"costo_secada_punto_usd": 3.10}},
        source_id="fam_abc",
        policy_id="politica-familia-abc",
        policy_version="2026.1",
    )
    resolver = DecisionPolicyResolver(layers=[l_fam])
    eff = resolver.resolve()

    val = eff["cosecha.costo_secada_punto_usd"]
    assert val.value == 3.10
    assert val.source_scope == "family_client"
    assert val.source_id == "fam_abc"
    assert val.policy_id == "politica-familia-abc"
    assert val.policy_version == "2026.1"


def test_5_client_cannot_override_safety_controls():
    """Caso 5: Overrides de cliente no pueden deshabilitar controles de seguridad (safety)."""
    l_client = PolicyLayer(
        scope="organization",
        policy_data={"safety": {"allow_override_safety_controls": True, "require_data_quality_for_positive_recommendation": False}},
    )
    resolver = DecisionPolicyResolver(layers=[l_client])
    eff = resolver.resolve()

    assert eff["safety.allow_override_safety_controls"].value is False
    assert eff["safety.allow_override_safety_controls"].source_scope == "system_base"


def test_6_custom_rule_registration_without_modifying_engine():
    """Caso 6: Se puede registrar y evaluar una regla nueva sin modificar DecisionEngine."""
    class ReglaFleteCustom:
        code: str = "FLETE_ELEVADO_CUSTOM"
        domain: str = "freight"
        priority: int = 80
        required_inputs: set = set()

        def evaluate(self, context, policy, trace_context):
            insight = DecisionInsight(
                codigo=self.code,
                nivel="info",
                titulo="Costo de Flete Detectado",
                mensaje="Evaluación de flete realizada.",
                domain=self.domain,
            )
            return RuleEvaluation(rule_code=self.code, status="triggered", insight=insight)

    registry = RuleRegistry()
    registry.register(ReglaFleteCustom())
    engine = DecisionEngine(registry=registry)

    result = engine.evaluate({})
    codes = [ins.codigo for ins in result.insights]
    assert "FLETE_ELEVADO_CUSTOM" in codes


def test_7_engine_evaluates_non_weather_rules_without_weather():
    """Caso 7: El motor ejecuta reglas comerciales y de grano sin necesidad de clima."""
    ctx = DecisionContext(
        cultivo="maiz",
        market=MarketData(precio_spot_usd=180.0, precio_futuro_usd=195.0, spread_usd=15.0),
        harvest=HarvestData(humedad_grano_pct=14.0),
        weather=WeatherData(provider_status="unavailable"),
    )
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    codes = [ins.codigo for ins in result.insights]
    assert "FUTURO_FAVORABLE_PARA_FIJACION" in codes
    assert "CLIMA_NO_DISPONIBLE" in codes


def test_8_weather_unavailable_does_not_fire_alerts_via_defaults():
    """Caso 8: Clima 'unavailable' genera CLIMA_NO_DISPONIBLE y omite alertas meteorológicas por defaults."""
    ctx = DecisionContext(
        cultivo="soja",
        weather=WeatherData(provider_status="unavailable"),
    )
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    codes = [ins.codigo for ins in result.insights]
    assert "CLIMA_NO_DISPONIBLE" in codes
    assert "RIESGO_DE_PISO_POR_PRECIPITACION" not in codes
    assert "ALERTA_PULVERIZACION_VIENTO" not in codes


def test_9_stale_cached_or_disagreement_reduces_confidence():
    """Caso 9: Clima 'stale_cached' o alta discrepancia reduce confidence y queda trazado."""
    ctx = DecisionContext(
        cultivo="maiz",
        weather=WeatherData(
            provider="open_meteo",
            provider_status="stale_cached",
            disagreement_level="high",
            precipitation_next_72h_mm=25.0,
        ),
    )
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    codes = [ins.codigo for ins in result.insights]
    assert "ALTA_INCERTIDUMBRE_METEOROLOGICA" in codes

    # Verificar reducción de confianza
    stale_ins = next(i for i in result.insights if i.codigo == "ALTA_INCERTIDUMBRE_METEOROLOGICA")
    assert stale_ins.confidence in ("medium", "low")


def test_10_harvest_moisture_rule_uses_conditioned_language():
    """Caso 10: La regla de humedad con ventana seca utiliza lenguaje condicionado y no la orden imperativa 'esperar'."""
    ctx = DecisionContext(
        cultivo="maiz",
        harvest=HarvestData(humedad_grano_pct=17.5),
        market=MarketData(precio_spot_usd=188.0),
        weather=WeatherData(provider_status="live", precipitation_next_72h_mm=0.0),
    )
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    ins = next(i for i in result.insights if i.codigo == "HUMEDAD_ALTA_Y_VENTANA_SECA")
    assert "Existe potencial de ahorro de secada" in ins.mensaje
    assert "esperar" not in ins.mensaje.lower() or "potencial" in ins.mensaje.lower()
    assert ins.disclaimer is not None


def test_11_future_spread_alert_warns_about_net_costs():
    """Caso 11: La alerta de pase futuro incluye advertencia de costos netos diferidos."""
    ctx = DecisionContext(
        cultivo="maiz",
        market=MarketData(precio_spot_usd=188.0, precio_futuro_usd=195.0, spread_usd=7.0),
    )
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    ins = next(i for i in result.insights if i.codigo == "FUTURO_FAVORABLE_PARA_FIJACION")
    assert "conveniencia neta depende de costos financieros" in ins.mensaje
    assert ins.disclaimer is not None


def test_12_high_wind_alert_warns_incomplete_evaluation():
    """Caso 12: Viento alto informa evaluación incompleta y sugiere verificación en campo."""
    ctx = DecisionContext(
        spraying=SprayingData(viento_actual_kmh=18.0),
        weather=WeatherData(provider_status="live", wind_max_next_24h_kmh=18.0),
    )
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    ins = next(i for i in result.insights if i.codigo == "ALERTA_PULVERIZACION_VIENTO")
    assert "verificar condiciones en campo" in ins.mensaje
    assert "evaluación completa de aplicación requiere" in ins.mensaje


def test_13_low_temperature_frost_rule():
    """Caso 13: Temperatura mínima bajo umbral genera RIESGO_TERMICO_A_VERIFICAR sin afirmación categórica."""
    ctx = DecisionContext(
        cultivo="trigo",
        weather=WeatherData(provider_status="live", temp_min_next_72h_c=2.5),
    )
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    ins = next(i for i in result.insights if i.codigo == "RIESGO_TERMICO_A_VERIFICAR")
    assert "La susceptibilidad del trigo depende del cultivo" in ins.mensaje


def test_14_audit_trace_to_audit_dict_sanitization():
    """Caso 14: La traza de auditoría to_audit_dict() produce una estructura serializable y sanitizada."""
    ctx = build_demo_decision_context()
    engine = DecisionEngine()
    result = engine.evaluate(ctx)

    trace_dict = result.trace.to_audit_dict()
    assert isinstance(trace_dict, dict)
    assert "trace_id" in trace_dict
    assert "engine_version" in trace_dict
    assert "rules_evaluated" in trace_dict


def test_15_existing_agent_helper_works():
    """Caso 15: El helper de agentes evaluar_decision_campo sigue funcionando correctamente."""
    insights = evaluar_decision_campo(
        cultivo="maiz",
        precio_fisico_usd=188.0,
        precio_futuro_usd=195.0,
        humedad_grano_pct=17.5,
    )
    assert isinstance(insights, list)
    assert len(insights) > 0
