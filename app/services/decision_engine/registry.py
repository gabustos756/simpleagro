"""
Registro Extensible y Seguro de Reglas de Decisión (EduAgro).
Organiza reglas por dominio, valida unicidad y garantiza ejecución determinística sin código dinámico.
"""

import logging
from typing import Dict, List, Set, Optional, Type
from app.services.decision_engine.models import (
    DecisionContext,
    EffectivePolicyValue,
    RuleEvaluation,
)
from app.services.decision_engine.rules.base import DecisionRule, RuleTraceContext

logger = logging.getLogger("eduagro.decision_engine.registry")


class RuleRegistry:
    def __init__(self):
        self._rules_by_code: Dict[str, DecisionRule] = {}
        self._rules_by_domain: Dict[str, List[DecisionRule]] = {}

    def register(self, rule: DecisionRule) -> None:
        """
        Registra una nueva regla verificando unicidad de código.
        """
        if rule.code in self._rules_by_code:
            raise ValueError(f"Ya existe una regla registrada con el código '{rule.code}'")

        self._rules_by_code[rule.code] = rule
        if rule.domain not in self._rules_by_domain:
            self._rules_by_domain[rule.domain] = []

        self._rules_by_domain[rule.domain].append(rule)
        # Ordenar reglas por prioridad ascendente dentro del dominio
        self._rules_by_domain[rule.domain].sort(key=lambda r: r.priority)

    def get_rule(self, code: str) -> Optional[DecisionRule]:
        return self._rules_by_code.get(code)

    def get_all_rules(self) -> List[DecisionRule]:
        all_rules = list(self._rules_by_code.values())
        all_rules.sort(key=lambda r: (r.priority, r.code))
        return all_rules

    def get_domain_rules(self, domain: str) -> List[DecisionRule]:
        return self._rules_by_domain.get(domain, [])

    def evaluate_all(
        self,
        context: DecisionContext,
        policy: Dict[str, EffectivePolicyValue],
        trace_context: RuleTraceContext,
    ) -> List[RuleEvaluation]:
        """
        Evalúa secuencialmente todas las reglas registradas activas.
        """
        evaluations: List[RuleEvaluation] = []
        rules = self.get_all_rules()

        for rule in rules:
            try:
                eval_res = rule.evaluate(context, policy, trace_context)
                evaluations.append(eval_res)
            except Exception as e:
                logger.error(f"[RULE REGISTRY] Error al evaluar regla '{rule.code}': {e}")
                evaluations.append(
                    RuleEvaluation(
                        rule_code=rule.code,
                        status="not_evaluated",
                        reason_codes=[f"EVALUATION_ERROR: {type(e).__name__}"],
                    )
                )

        return evaluations


def create_default_registry() -> RuleRegistry:
    """
    Instancia el registro de reglas por defecto con todos los dominios iniciales.
    """
    from app.services.decision_engine.rules import (
        DatosInsuficientesCosechaRule,
        DatosInsuficientesComercializacionRule,
        ClimaNoDisponibleRule,
        AltaIncertidumbreMeteorologicaRule,
        HumedadAltaVentanaSecaRule,
        HumedadAltaLluviaProximaRule,
        CostoSecadaElevadoRule,
        FuturoFavorableFijacionRule,
        RiesgoPisoPrecipitacionRule,
        AlertaPulverizacionVientoRule,
        RiesgoTermicoAVerificarRule,
        FleteSinCotizacionRule,
        CotizacionFleteDesactualizadaRule,
        DestinoNoAptoPorCaminoRule,
        DestinoSinCupoConfirmadoRule,
        DestinoCondicionadoPorHumedadRule,
        PrecioNetoOrigenCalculadoRule,
        DestinoNetoMasConvenienteRule,
        SinDiferenciaNetaMaterialEntreDestinosRule,
        DatosInsuficientesParaCompararDestinosRule,
        EntregaSinCartaDePorteRule,
        CartaPorteSinPesoOrigenRule,
        CartaPorteSinPesoDestinoRule,
        DiferenciaDePesajeARevisarRule,
        CargaSuperaCapacidadReferenciaRule,
        FleteEstimadoPorEntregaRule,
        EntregaAsociadaACompromisoRule,
        EntregaConDocumentacionPendienteRule,
    )

    registry = RuleRegistry()
    registry.register(ClimaNoDisponibleRule())
    registry.register(AltaIncertidumbreMeteorologicaRule())
    registry.register(DatosInsuficientesCosechaRule())
    registry.register(DatosInsuficientesComercializacionRule())
    registry.register(HumedadAltaVentanaSecaRule())
    registry.register(HumedadAltaLluviaProximaRule())
    registry.register(CostoSecadaElevadoRule())
    registry.register(FuturoFavorableFijacionRule())
    registry.register(RiesgoPisoPrecipitacionRule())
    registry.register(AlertaPulverizacionVientoRule())
    registry.register(RiesgoTermicoAVerificarRule())
    registry.register(FleteSinCotizacionRule())
    registry.register(CotizacionFleteDesactualizadaRule())
    registry.register(DestinoNoAptoPorCaminoRule())
    registry.register(DestinoSinCupoConfirmadoRule())
    registry.register(DestinoCondicionadoPorHumedadRule())
    registry.register(PrecioNetoOrigenCalculadoRule())
    registry.register(DestinoNetoMasConvenienteRule())
    registry.register(SinDiferenciaNetaMaterialEntreDestinosRule())
    registry.register(DatosInsuficientesParaCompararDestinosRule())
    registry.register(EntregaSinCartaDePorteRule())
    registry.register(CartaPorteSinPesoOrigenRule())
    registry.register(CartaPorteSinPesoDestinoRule())
    registry.register(DiferenciaDePesajeARevisarRule())
    registry.register(CargaSuperaCapacidadReferenciaRule())
    registry.register(FleteEstimadoPorEntregaRule())
    registry.register(EntregaAsociadaACompromisoRule())
    registry.register(EntregaConDocumentacionPendienteRule())
    return registry
