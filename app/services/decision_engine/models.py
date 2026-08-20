"""
Modelos de Datos Tipados y Esquemas Pydantic v2 para el Motor de Decisiones (EduAgro).
Garantiza inmutabilidad, trazabilidad y explicabilidad en cada recomendación.
"""

from datetime import datetime, date
from enum import Enum
from typing import Optional, Dict, Any, List, Literal, Union
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator


from decimal import Decimal


class DataAvailability(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    INVALID = "invalid"
    ESTIMATED = "estimated"
    CACHED = "cached"
    STALE_CACHED = "stale_cached"


class RoadStatus(str, Enum):
    GOOD = "good"
    CONDITIONED = "conditioned"
    POOR = "poor"
    IMPASSABLE = "impassable"
    UNKNOWN = "unknown"


class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class FreightQuoteSource(str, Enum):
    MANUAL = "manual"
    TRANSPORTER_QUOTE = "transporter_quote"
    ESTIMATED = "estimated"
    EXTERNAL = "external"


class DeliveryDestinationContext(BaseModel):
    destination_id: Optional[Union[UUID, str]] = None
    destination_name: str
    destination_type: Optional[str] = None  # acopio, cooperativa, fábrica, puerto, comprador
    cultivo: Optional[str] = None
    condicion_precio: Optional[str] = None
    distancia_estimada_km: Optional[Decimal] = None
    detalle_cupo_turno: Optional[str] = None
    price_usd_tn: Optional[Decimal] = None
    freight_usd_tn: Optional[Decimal] = None
    conditioning_cost_usd_tn: Optional[Decimal] = None
    other_costs_usd_tn: Optional[Decimal] = None
    max_receiving_moisture_pct: Optional[Decimal] = None
    humedad_max_recepcion_pct: Optional[Decimal] = None
    receiving_confirmed: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    road_status: RoadStatus = RoadStatus.UNKNOWN
    quote_observed_at: Optional[datetime] = None
    quote_valid_until: Optional[datetime] = None
    quote_source: Optional[FreightQuoteSource] = None
    quote_confidence: Optional[Literal["high", "medium", "low"]] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def sync_moisture_fields(self) -> "DeliveryDestinationContext":
        if self.humedad_max_recepcion_pct is not None and self.max_receiving_moisture_pct is None:
            object.__setattr__(self, "max_receiving_moisture_pct", self.humedad_max_recepcion_pct)
        elif self.max_receiving_moisture_pct is not None and self.humedad_max_recepcion_pct is None:
            object.__setattr__(self, "humedad_max_recepcion_pct", self.max_receiving_moisture_pct)
        return self


class DataQualityItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    availability: DataAvailability
    source: Optional[str] = None
    observed_at: Optional[datetime] = None
    warning: Optional[str] = None


class MarketData(BaseModel):
    precio_spot_usd: Optional[float] = None
    precio_futuro_usd: Optional[float] = None
    spread_usd: Optional[float] = None
    costo_flete_usd_tn: Optional[float] = None
    costo_almacenaje_mes_usd_tn: Optional[float] = None
    tasa_interes_mensual_pct: Optional[float] = None
    costo_seguro_pct: Optional[float] = None
    merma_almacenaje_pct: Optional[float] = None


class HarvestData(BaseModel):
    humedad_grano_pct: Optional[float] = None
    costo_secada_punto_usd: Optional[float] = None
    rendimiento_estimado_tn_ha: Optional[float] = None
    dias_para_madurez: Optional[int] = None
    riesgo_vuelco_observado: Optional[bool] = None
    riesgo_desgrane_observado: Optional[bool] = None


class LogisticsData(BaseModel):
    capacidad_transporte_disponible: Optional[bool] = None
    distancia_acopio_km: Optional[float] = None
    estado_caminos: Optional[Literal["bueno", "regular", "intransitable", "desconocido"]] = "desconocido"


class SprayingData(BaseModel):
    viento_actual_kmh: Optional[float] = None
    viento_rafagas_kmh: Optional[float] = None
    viento_direccion_deg: Optional[int] = None
    temperatura_c: Optional[float] = None
    humedad_relativa_pct: Optional[float] = None
    inversion_termica_presente: Optional[bool] = None
    botalon_altura_m: Optional[float] = None


class WeatherData(BaseModel):
    provider: Optional[str] = None
    provider_status: Optional[Literal["live", "cached", "stale_cached", "unavailable"]] = "unavailable"
    retrieved_at: Optional[datetime] = None
    forecast_generated_at: Optional[datetime] = None

    precipitation_next_24h_mm: Optional[float] = None
    precipitation_next_48h_mm: Optional[float] = None
    precipitation_next_72h_mm: Optional[float] = None
    precipitation_next_7d_mm: Optional[float] = None

    wind_max_next_24h_kmh: Optional[float] = None
    wind_max_next_72h_kmh: Optional[float] = None
    wind_gust_max_next_24h_kmh: Optional[float] = None
    wind_gust_max_next_72h_kmh: Optional[float] = None

    temp_min_next_72h_c: Optional[float] = None
    temp_max_next_72h_c: Optional[float] = None
    relative_humidity_min_next_72h_pct: Optional[float] = None
    relative_humidity_max_next_72h_pct: Optional[float] = None

    disagreement_level: Optional[Literal["none", "low", "medium", "high"]] = "none"
    recommended_decision_mode: Optional[Literal["primary", "conservative", "verify_in_field"]] = "primary"
    data_quality_warnings: List[str] = Field(default_factory=list)


class GrainWaybillContext(BaseModel):
    id: Optional[Union[UUID, str]] = None
    numero_carta_porte: Optional[str] = None
    tipo_camion: Optional[str] = None
    capacidad_referencia_kg: Optional[Decimal] = None
    tara_kg: Optional[Decimal] = None
    peso_bruto_origen_kg: Optional[Decimal] = None
    peso_neto_origen_kg: Optional[Decimal] = None
    peso_recibido_destino_kg: Optional[Decimal] = None
    diferencia_kg: Optional[Decimal] = None
    diferencia_pct: Optional[Decimal] = None
    fecha_carga: Optional[datetime] = None
    fecha_recepcion: Optional[datetime] = None
    referencia_ticket_origen: Optional[str] = None
    referencia_ticket_destino: Optional[str] = None
    estado: str = "planificada"
    observaciones: Optional[str] = None


class GrainDeliveryContext(BaseModel):
    id: Optional[Union[UUID, str]] = None
    tracking_number: str
    campo_id: Optional[Union[UUID, str]] = None
    lote_id: Optional[Union[UUID, str]] = None
    compromiso_id: Optional[Union[UUID, str]] = None
    freight_quote_id: Optional[Union[UUID, str]] = None
    acopio_receptor: Optional[str] = None
    destination_final_reference: Optional[str] = None
    cultivo: Optional[str] = None
    transportista_nombre: Optional[str] = None
    fecha_planificada: Optional[date] = None
    fecha_salida: Optional[datetime] = None
    fecha_recepcion: Optional[datetime] = None
    toneladas_planificadas: Optional[Decimal] = None
    kg_neto_origen_total: Optional[Decimal] = None
    kg_recibido_total: Optional[Decimal] = None
    diferencia_total_kg: Optional[Decimal] = None
    diferencia_total_pct: Optional[Decimal] = None
    estado: str = "planificada"
    documentacion_status: str = "sin_documentacion"
    observaciones: Optional[str] = None
    waybills: List[GrainWaybillContext] = Field(default_factory=list)


class DecisionContext(BaseModel):
    request_id: Optional[Union[UUID, str]] = None
    organization_id: Optional[Union[UUID, str]] = None
    family_client_id: Optional[Union[UUID, str]] = None
    campo_id: Optional[Union[UUID, str]] = None
    lote_id: Optional[Union[UUID, str]] = None

    cultivo: Optional[Literal["maiz", "soja", "sorgo", "trigo"]] = None
    campo_nombre: Optional[str] = None
    lote_nombre: Optional[str] = None

    market: MarketData = Field(default_factory=MarketData)
    harvest: HarvestData = Field(default_factory=HarvestData)
    logistics: LogisticsData = Field(default_factory=LogisticsData)
    spraying: SprayingData = Field(default_factory=SprayingData)
    weather: WeatherData = Field(default_factory=WeatherData)

    delivery_options: List[DeliveryDestinationContext] = Field(default_factory=list)
    deliveries: List[GrainDeliveryContext] = Field(default_factory=list)

    metadata: Dict[str, Any] = Field(default_factory=dict)


class EffectivePolicyValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: Any
    source_scope: Literal[
        "system_base",
        "agronomic_template",
        "organization",
        "family_client",
        "field",
        "lot",
        "run_override",
    ]
    source_id: Optional[Union[UUID, str]] = None
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None


class DecisionPolicy(BaseModel):
    policy_id: str = "system-base"
    policy_version: str = "2.0.0"
    effective_from: Optional[datetime] = None

    cosecha: Dict[str, Any] = Field(default_factory=dict)
    comercializacion: Dict[str, Any] = Field(default_factory=dict)
    pulverizacion: Dict[str, Any] = Field(default_factory=dict)
    helada: Dict[str, Any] = Field(default_factory=dict)
    safety: Dict[str, Any] = Field(default_factory=dict)


class DecisionInsight(BaseModel):
    codigo: str
    nivel: Literal["danger", "warning", "info", "success"]
    titulo: str
    mensaje: str
    datos: Dict[str, Any] = Field(default_factory=dict)

    domain: str
    priority: int = 100
    accion_recomendada: Optional[str] = None
    confidence: Literal["high", "medium", "low"] = "high"
    reason_codes: List[str] = Field(default_factory=list)
    drivers: List[str] = Field(default_factory=list)
    tradeoffs: Dict[str, Any] = Field(default_factory=dict)
    inputs_used: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    next_review_at_hours: Optional[int] = None
    disclaimer: Optional[str] = None


class RuleEvaluation(BaseModel):
    rule_code: str
    status: Literal["triggered", "not_triggered", "not_evaluated"]
    insight: Optional[DecisionInsight] = None
    reason_codes: List[str] = Field(default_factory=list)
    inputs_used: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    duration_ms: Optional[float] = None


class DecisionTrace(BaseModel):
    trace_id: Union[UUID, str]
    engine_version: str = "2.0.0"
    evaluated_at: datetime
    context_schema_version: str = "v2.0"
    policy_schema_version: str = "v2.0"
    policy_versions: List[str] = Field(default_factory=list)
    rules_evaluated: List[RuleEvaluation] = Field(default_factory=list)
    data_quality: List[DataQualityItem] = Field(default_factory=list)
    weather_provenance: Optional[Dict[str, Any]] = None
    effective_policy_provenance: Dict[str, EffectivePolicyValue] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)

    def to_audit_dict(self) -> Dict[str, Any]:
        """Genera un diccionario sanitizado libre de credenciales y datos sensibles."""
        dumped = self.model_dump(mode="json")
        return dumped


class DecisionResult(BaseModel):
    insights: List[DecisionInsight]
    trace: DecisionTrace
    normalized_context: DecisionContext
    effective_policy: Dict[str, EffectivePolicyValue]
    engine_version: str = "2.0.0"
