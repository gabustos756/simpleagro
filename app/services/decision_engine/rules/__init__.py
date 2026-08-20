"""
Exportación de Módulos y Reglas Agronómicas del Motor de Decisiones (EduAgro).
"""

from app.services.decision_engine.rules.base import DecisionRule, RuleTraceContext
from app.services.decision_engine.rules.data_quality import (
    DatosInsuficientesCosechaRule,
    DatosInsuficientesComercializacionRule,
    ClimaNoDisponibleRule,
    AltaIncertidumbreMeteorologicaRule,
)
from app.services.decision_engine.rules.harvest import (
    HumedadAltaVentanaSecaRule,
    HumedadAltaLluviaProximaRule,
    CostoSecadaElevadoRule,
)
from app.services.decision_engine.rules.commercialization import (
    FuturoFavorableFijacionRule,
)
from app.services.decision_engine.rules.trafficability import (
    RiesgoPisoPrecipitacionRule,
)
from app.services.decision_engine.rules.spraying import (
    AlertaPulverizacionVientoRule,
)
from app.services.decision_engine.rules.frost import (
    RiesgoTermicoAVerificarRule,
)
from app.services.decision_engine.rules.freight import (
    FleteSinCotizacionRule,
    CotizacionFleteDesactualizadaRule,
    DestinoNoAptoPorCaminoRule,
    DestinoSinCupoConfirmadoRule,
    DestinoCondicionadoPorHumedadRule,
    PrecioNetoOrigenCalculadoRule,
    DestinoNetoMasConvenienteRule,
    SinDiferenciaNetaMaterialEntreDestinosRule,
    DatosInsuficientesParaCompararDestinosRule,
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

__all__ = [
    "DecisionRule",
    "RuleTraceContext",
    "DatosInsuficientesCosechaRule",
    "DatosInsuficientesComercializacionRule",
    "ClimaNoDisponibleRule",
    "AltaIncertidumbreMeteorologicaRule",
    "HumedadAltaVentanaSecaRule",
    "HumedadAltaLluviaProximaRule",
    "CostoSecadaElevadoRule",
    "FuturoFavorableFijacionRule",
    "RiesgoPisoPrecipitacionRule",
    "AlertaPulverizacionVientoRule",
    "RiesgoTermicoAVerificarRule",
    "FleteSinCotizacionRule",
    "CotizacionFleteDesactualizadaRule",
    "DestinoNoAptoPorCaminoRule",
    "DestinoSinCupoConfirmadoRule",
    "DestinoCondicionadoPorHumedadRule",
    "PrecioNetoOrigenCalculadoRule",
    "DestinoNetoMasConvenienteRule",
    "SinDiferenciaNetaMaterialEntreDestinosRule",
    "DatosInsuficientesParaCompararDestinosRule",
    "EntregaSinCartaDePorteRule",
    "CartaPorteSinPesoOrigenRule",
    "CartaPorteSinPesoDestinoRule",
    "DiferenciaDePesajeARevisarRule",
    "CargaSuperaCapacidadReferenciaRule",
    "FleteEstimadoPorEntregaRule",
    "EntregaAsociadaACompromisoRule",
    "EntregaConDocumentacionPendienteRule",
]
