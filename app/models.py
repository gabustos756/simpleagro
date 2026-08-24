from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import Optional, List

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import (
    DocumentTypeEnum,
    EstadoCartaDePorte,
    EstadoServicio,
    EstadoServicioInstaladoEnum,
    FrecuenciaPagoEnum,
    RolUsuario,
    TenenciaTipoEnum,
    TipoCompromisoEnum,
    TipoLabor,
    TipoPrecioEnum,
    TipoServicioEnum,
    TipoTransaccion,
    UbicacionStockEnum,
    EstadoCaminoEnum,
    EstadoRecepcionEnum,
    FuenteCotizacionFleteEnum,
    ConfianzaCotizacionEnum,
    TipoEquipoEnum,
    EstadoOperativoTrabajoEnum,
    MedioPagoEnum,
    InsumosAportadosEnum,
)


class Cliente(Base):
    """Entidad Cliente (Organización/Estancia/Empresa Agropecuaria)."""
    __tablename__ = "clientes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    cuit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ubicacion: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    usuarios: Mapped[List["Usuario"]] = relationship(
        "Usuario", back_populates="cliente", cascade="all, delete-orphan"
    )
    campos: Mapped[List["Campo"]] = relationship(
        "Campo", back_populates="cliente", cascade="all, delete-orphan"
    )
    instalaciones: Mapped[List["Instalacion"]] = relationship(
        "Instalacion", back_populates="cliente", cascade="all, delete-orphan"
    )
    servicios_instalados: Mapped[List["ServicioInstalado"]] = relationship(
        "ServicioInstalado", back_populates="cliente", cascade="all, delete-orphan"
    )
    lotes: Mapped[List["Lote"]] = relationship(
        "Lote", back_populates="cliente", cascade="all, delete-orphan"
    )
    contratos_venta: Mapped[List["ContratoVentaGrano"]] = relationship(
        "ContratoVentaGrano", back_populates="cliente", cascade="all, delete-orphan"
    )
    stocks_grano: Mapped[List["StockGrano"]] = relationship(
        "StockGrano", back_populates="cliente", cascade="all, delete-orphan"
    )
    compromisos_grano: Mapped[List["CompromisoGrano"]] = relationship(
        "CompromisoGrano", back_populates="cliente", cascade="all, delete-orphan"
    )
    freight_quotes: Mapped[List["FreightQuote"]] = relationship(
        "FreightQuote", back_populates="cliente", cascade="all, delete-orphan"
    )
    deliveries: Mapped[List["GrainDelivery"]] = relationship(
        "GrainDelivery", back_populates="cliente", cascade="all, delete-orphan"
    )
    storage_locations: Mapped[List["StorageLocation"]] = relationship(
        "StorageLocation", back_populates="cliente", cascade="all, delete-orphan"
    )
    stock_partidas: Mapped[List["StockPartida"]] = relationship(
        "StockPartida", back_populates="cliente", cascade="all, delete-orphan"
    )
    stock_reservations: Mapped[List["StockReservation"]] = relationship(
        "StockReservation", back_populates="cliente", cascade="all, delete-orphan"
    )
    stock_allocations: Mapped[List["StockDeliveryAllocation"]] = relationship(
        "StockDeliveryAllocation", back_populates="cliente", cascade="all, delete-orphan"
    )
    stock_weight_reconciliations: Mapped[List["StockWeightReconciliation"]] = relationship(
        "StockWeightReconciliation", back_populates="cliente", cascade="all, delete-orphan"
    )


class Campo(Base):
    """Entidad Campo con Geolocalización (Latitud/Longitud) y Clima."""
    __tablename__ = "campos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    ubicacion: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    localidad_referencia: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)  # Ej: Río Cuarto, Córdoba
    latitud: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Ej: -31.4201
    longitud: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # Ej: -64.1888
    hectareas_totales: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente", back_populates="campos")
    instalaciones: Mapped[List["Instalacion"]] = relationship(
        "Instalacion", back_populates="campo", cascade="all, delete-orphan"
    )
    servicios_instalados: Mapped[List["ServicioInstalado"]] = relationship(
        "ServicioInstalado", back_populates="campo", cascade="all, delete-orphan"
    )
    lotes: Mapped[List["Lote"]] = relationship(
        "Lote", back_populates="campo", cascade="all, delete-orphan"
    )
    stocks_grano: Mapped[List["StockGrano"]] = relationship(
        "StockGrano", back_populates="campo", cascade="all, delete-orphan"
    )
    compromisos_grano: Mapped[List["CompromisoGrano"]] = relationship(
        "CompromisoGrano", back_populates="campo"
    )


class Instalacion(Base):
    __tablename__ = "instalaciones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True
    )
    campo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), default="casa", nullable=False)
    ubicacion_notas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente", back_populates="instalaciones")
    campo: Mapped["Campo"] = relationship("Campo", back_populates="instalaciones")
    servicios: Mapped[List["ServicioInstalado"]] = relationship(
        "ServicioInstalado", back_populates="instalacion", cascade="all, delete-orphan"
    )


class ServicioInstalado(Base):
    __tablename__ = "servicios_instalados"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True
    )
    campo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="CASCADE"), nullable=False
    )
    instalacion_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instalaciones.id", ondelete="SET NULL"), nullable=True
    )
    tipo_servicio: Mapped[TipoServicioEnum] = mapped_column(
        SQLEnum(TipoServicioEnum, name="tipo_servicio_enum", native_enum=True),
        nullable=False,
    )
    concepto: Mapped[str] = mapped_column(String(200), nullable=False)
    proveedor: Mapped[str] = mapped_column(String(150), nullable=False)
    frecuencia_pago: Mapped[FrecuenciaPagoEnum] = mapped_column(
        SQLEnum(FrecuenciaPagoEnum, name="frecuencia_pago_enum", native_enum=True),
        default=FrecuenciaPagoEnum.MENSUAL,
        nullable=False,
    )
    monto_estimado_ars: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    monto_real_ars: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0.0, nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoServicioInstaladoEnum] = mapped_column(
        SQLEnum(EstadoServicioInstaladoEnum, name="estado_servicio_instalado_enum", native_enum=True),
        default=EstadoServicioInstaladoEnum.PENDIENTE,
        nullable=False,
    )
    comprobante_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_portal_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente", back_populates="servicios_instalados")
    campo: Mapped["Campo"] = relationship("Campo", back_populates="servicios_instalados")
    instalacion: Mapped[Optional["Instalacion"]] = relationship("Instalacion", back_populates="servicios")
    vencimientos: Mapped[List["ServicioVencimiento"]] = relationship(
        "ServicioVencimiento", back_populates="servicio_instalado", cascade="all, delete-orphan"
    )
    documentos: Mapped[List["ServiceDocument"]] = relationship(
        "ServiceDocument", back_populates="servicio", cascade="all, delete-orphan"
    )


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(
        SQLEnum(RolUsuario, name="rol_usuario_enum", native_enum=True),
        nullable=False,
    )
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente", back_populates="usuarios")
    labores: Mapped[List["LaborCampo"]] = relationship("LaborCampo", back_populates="responsable")
    registros_lluvia: Mapped[List["RegistroLluvia"]] = relationship("RegistroLluvia", back_populates="registrado_por")


class Lote(Base):
    __tablename__ = "lotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="CASCADE"), nullable=True
    )
    cliente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True
    )
    campania_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campanias.id", ondelete="SET NULL"), nullable=True
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    superficie_total_ha: Mapped[float] = mapped_column(Float, nullable=False)
    superficie_productiva_ha: Mapped[float] = mapped_column(Float, nullable=False)
    tenencia_tipo: Mapped[TenenciaTipoEnum] = mapped_column(
        SQLEnum(TenenciaTipoEnum, name="tenencia_tipo_enum", native_enum=True),
        default=TenenciaTipoEnum.PROPIO,
        nullable=False,
    )
    costo_alquiler_usd_ha: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    vencimiento_alquiler: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notas_alquiler: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cultivo_anterior: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cultivo_actual: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cultivo_planificado: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tipo_suelo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    geolocalizacion_lat_lng: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    qq_ha_estimado: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    qq_ha_real: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    produccion_total_qq: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadatos_agronomicos: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    campo: Mapped[Optional["Campo"]] = relationship("Campo", back_populates="lotes")
    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente", back_populates="lotes")
    campania: Mapped[Optional["Campania"]] = relationship("Campania", back_populates="lotes")
    labores: Mapped[List["LaborCampo"]] = relationship("LaborCampo", back_populates="lote", cascade="all, delete-orphan")
    registros_lluvia: Mapped[List["RegistroLluvia"]] = relationship("RegistroLluvia", back_populates="lote", cascade="all, delete-orphan")
    cartas_de_porte: Mapped[List["CartaDePorte"]] = relationship("CartaDePorte", back_populates="lote_origen")
    transacciones: Mapped[List["TransaccionFinanciera"]] = relationship("TransaccionFinanciera", back_populates="lote")


class Campania(Base):
    __tablename__ = "campanias"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    lotes: Mapped[List["Lote"]] = relationship("Lote", back_populates="campania")
    labores: Mapped[List["LaborCampo"]] = relationship("LaborCampo", back_populates="campania", cascade="all, delete-orphan")
    contratos_venta: Mapped[List["ContratoVentaGrano"]] = relationship(
        "ContratoVentaGrano", back_populates="campania", cascade="all, delete-orphan"
    )
    stocks_grano: Mapped[List["StockGrano"]] = relationship(
        "StockGrano", back_populates="campania", cascade="all, delete-orphan"
    )
    compromisos_grano: Mapped[List["CompromisoGrano"]] = relationship(
        "CompromisoGrano", back_populates="campania", cascade="all, delete-orphan"
    )


class LaborCampo(Base):
    __tablename__ = "labores_campo"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotes.id", ondelete="CASCADE"), nullable=False
    )
    campania_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campanias.id", ondelete="CASCADE"), nullable=False
    )
    tipo_labor: Mapped[TipoLabor] = mapped_column(
        SQLEnum(TipoLabor, name="tipo_labor_enum", native_enum=True),
        nullable=False,
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    insumos_utilizados: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    responsable_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    costo_estimado_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    notas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lote: Mapped["Lote"] = relationship("Lote", back_populates="labores")
    campania: Mapped["Campania"] = relationship("Campania", back_populates="labores")
    responsable: Mapped[Optional["Usuario"]] = relationship("Usuario", back_populates="labores")


class RegistroLluvia(Base):
    __tablename__ = "registros_lluvia"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotes.id", ondelete="CASCADE"), nullable=False
    )
    milimetros: Mapped[float] = mapped_column(Float, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registrado_por_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    lote: Mapped["Lote"] = relationship("Lote", back_populates="registros_lluvia")
    registrado_por: Mapped[Optional["Usuario"]] = relationship("Usuario", back_populates="registros_lluvia")


class ServicioVencimiento(Base):
    __tablename__ = "servicios_vencimiento"
    __table_args__ = (
        Index("ix_servicios_vencimiento_cliente_fecha", "cliente_id", "fecha_vencimiento"),
        Index("ix_servicios_vencimiento_servicio_id", "servicio_instalado_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    servicio_instalado_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servicios_instalados.id", ondelete="CASCADE"), nullable=True
    )
    concepto: Mapped[str] = mapped_column(String(200), nullable=False)
    monto_ars: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoServicio] = mapped_column(
        SQLEnum(EstadoServicio, name="estado_servicio_enum", native_enum=True),
        default=EstadoServicio.PENDIENTE,
        nullable=False,
    )
    comprobante_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    periodo_referencia: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fecha_pago: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente")
    servicio_instalado: Mapped[Optional["ServicioInstalado"]] = relationship(
        "ServicioInstalado", back_populates="vencimientos"
    )
    documentos: Mapped[List["ServiceDocument"]] = relationship(
        "ServiceDocument", back_populates="servicio_vencimiento", cascade="all, delete-orphan"
    )


class ServiceDocument(Base):
    """Metadatos de documentos digitales adjuntos a servicios o vencimientos."""
    __tablename__ = "service_documents"
    __table_args__ = (
        Index("ix_service_documents_cliente_id", "cliente_id"),
        Index("ix_service_documents_servicio_id", "servicio_id"),
        Index("ix_service_documents_vencimiento_id", "servicio_vencimiento_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    servicio_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servicios_instalados.id", ondelete="CASCADE"), nullable=True
    )
    servicio_vencimiento_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servicios_vencimiento.id", ondelete="CASCADE"), nullable=True
    )
    document_type: Mapped[DocumentTypeEnum] = mapped_column(
        SQLEnum(DocumentTypeEnum, name="document_type_enum", native_enum=True),
        default=DocumentTypeEnum.FACTURA,
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    uploaded_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="activo", nullable=False)

    cliente: Mapped["Cliente"] = relationship("Cliente")
    servicio: Mapped[Optional["ServicioInstalado"]] = relationship("ServicioInstalado", back_populates="documentos")
    servicio_vencimiento: Mapped[Optional["ServicioVencimiento"]] = relationship("ServicioVencimiento", back_populates="documentos")
    uploaded_by: Mapped[Optional["Usuario"]] = relationship("Usuario")


class CartaDePorte(Base):
    __tablename__ = "cartas_de_porte"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    numero_cpe: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    lote_origen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotes.id", ondelete="RESTRICT"), nullable=False
    )
    chofer_camion: Mapped[str] = mapped_column(String(150), nullable=False)
    kilos_brutos: Mapped[float] = mapped_column(Float, nullable=False)
    kilos_netos: Mapped[float] = mapped_column(Float, nullable=False)
    fecha_emision: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estado: Mapped[EstadoCartaDePorte] = mapped_column(
        SQLEnum(EstadoCartaDePorte, name="estado_cpe_enum", native_enum=True),
        default=EstadoCartaDePorte.EN_TRANSITO,
        nullable=False,
    )

    lote_origen: Mapped["Lote"] = relationship("Lote", back_populates="cartas_de_porte")


class TransaccionFinanciera(Base):
    __tablename__ = "transacciones_financieras"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[TipoTransaccion] = mapped_column(
        SQLEnum(TipoTransaccion, name="tipo_transaccion_enum", native_enum=True),
        nullable=False,
    )
    monto_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monto_ars: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cotizacion_dolar: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    lote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotes.id", ondelete="SET NULL"), nullable=True
    )
    pagado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    lote: Mapped[Optional["Lote"]] = relationship("Lote", back_populates="transacciones")


class ContratoVentaGrano(Base):
    __tablename__ = "contratos_venta_grano"
    __table_args__ = (
        Index("ix_contratos_cliente_campania_cultivo", "cliente_id", "campania_id", "cultivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    campania_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campanias.id", ondelete="CASCADE"), nullable=False
    )
    cultivo: Mapped[str] = mapped_column(String(50), nullable=False)
    comprador_acopio: Mapped[str] = mapped_column(String(150), nullable=False)
    numero_contrato: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    toneladas: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tipo_precio: Mapped[TipoPrecioEnum] = mapped_column(
        SQLEnum(TipoPrecioEnum, name="tipo_precio_enum", native_enum=True),
        nullable=False,
    )
    precio_usd_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    fecha_contrato: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_entrega_limite: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="contratos_venta")
    campania: Mapped["Campania"] = relationship("Campania", back_populates="contratos_venta")


class StockGrano(Base):
    __tablename__ = "stock_grano"
    __table_args__ = (
        Index("ix_stock_cliente_campania_cultivo", "cliente_id", "campania_id", "cultivo"),
        Index("ix_stock_campo", "campo_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    campo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="CASCADE"), nullable=False
    )
    campania_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campanias.id", ondelete="CASCADE"), nullable=False
    )
    cultivo: Mapped[str] = mapped_column(String(50), nullable=False)
    ubicacion_tipo: Mapped[UbicacionStockEnum] = mapped_column(
        SQLEnum(UbicacionStockEnum, name="ubicacion_stock_enum", native_enum=True),
        nullable=False,
    )
    identificador: Mapped[str] = mapped_column(String(150), nullable=False)
    toneladas_almacenadas: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_ingreso: Mapped[date] = mapped_column(Date, nullable=False)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="stocks_grano")
    campo: Mapped["Campo"] = relationship("Campo", back_populates="stocks_grano")
    campania: Mapped["Campania"] = relationship("Campania", back_populates="stocks_grano")


class CompromisoGrano(Base):
    __tablename__ = "compromisos_grano"
    __table_args__ = (
        Index("ix_compromisos_cliente_campania_cultivo", "cliente_id", "campania_id", "cultivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    campania_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campanias.id", ondelete="CASCADE"), nullable=False
    )
    campo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="SET NULL"), nullable=True
    )
    cultivo: Mapped[str] = mapped_column(String(50), nullable=False)
    tipo_compromiso: Mapped[TipoCompromisoEnum] = mapped_column(
        SQLEnum(TipoCompromisoEnum, name="tipo_compromiso_enum", native_enum=True),
        nullable=False,
    )
    concepto: Mapped[str] = mapped_column(String(200), nullable=False)
    beneficiario: Mapped[str] = mapped_column(String(150), nullable=False)
    toneladas_comprometidas: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_vencimiento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    cumplido: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="compromisos_grano")
    campania: Mapped["Campania"] = relationship("Campania", back_populates="compromisos_grano")
    campo: Mapped[Optional["Campo"]] = relationship("Campo", back_populates="compromisos_grano")
    reservations: Mapped[List["StockReservation"]] = relationship(
        "StockReservation", back_populates="compromiso", cascade="all, delete-orphan"
    )
    arrendamiento_terms: Mapped[Optional["ArrendamientoTerms"]] = relationship(
        "ArrendamientoTerms", back_populates="compromiso", uselist=False, cascade="all, delete-orphan"
    )


class ArrendamientoTerms(Base):
    """Términos específicos de un compromiso de arrendamiento pactado en qq/ha."""
    __tablename__ = "arrendamiento_terms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    compromiso_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compromisos_grano.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    superficie_arrendada_ha: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    alquiler_qq_ha: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    base_valorizacion: Mapped[str] = mapped_column(String(50), default="rosario", nullable=False) # 'rosario' | 'acopio'
    precio_referencia_usd_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    fecha_precio_referencia: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fuente_precio: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    flete_usd_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    comision_usd_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    compromiso: Mapped["CompromisoGrano"] = relationship("CompromisoGrano", back_populates="arrendamiento_terms")


class PrecioMercadoCache(Base):
    """
    Caché local de cotizaciones de mercado de granos (Soja, Maíz, etc.).
    Almacena precios de referencia de fuentes externas como Pizarra Rosario (CAC) o SAGyP.
    """
    __tablename__ = "precios_mercado_cache"
    __table_args__ = (
        Index("ix_precios_mercado_cultivo_fecha", "cultivo", "fecha"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cultivo: Mapped[str] = mapped_column(String(50), nullable=False)
    fuente: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    precio_usd_tn: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    precio_ars_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    dolar_referencia: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WeatherSnapshot(Base):
    """
    Tabla de persistencia histórica de snapshots meteorológicos normalizados.
    Registra datos observados y pronosticados de proveedores (Google Weather, Open-Meteo).
    """
    __tablename__ = "weather_snapshots"
    __table_args__ = (
        Index("ix_weather_snapshots_campo_retrieved", "campo_id", "retrieved_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="SET NULL"), nullable=True
    )
    lote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotes.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(50), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), default="America/Argentina/Cordoba", nullable=False)
    observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    forecast_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="v2.0", nullable=False)
    normalized_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    data_quality: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FreightQuote(Base):
    """Entidad de cotizaciones y alternativas de entrega comercial/flete."""
    __tablename__ = "freight_quotes"
    __table_args__ = (
        Index("ix_freight_quotes_cliente_destination", "cliente_id", "destination_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    campo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="SET NULL"), nullable=True
    )
    lote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotes.id", ondelete="SET NULL"), nullable=True
    )

    destination_name: Mapped[str] = mapped_column(String(150), nullable=False)
    destination_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    cultivo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    condicion_precio: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    distancia_estimada_km: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)

    price_usd_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    freight_usd_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    conditioning_cost_usd_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    other_costs_usd_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    max_receiving_moisture_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    receiving_confirmed: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)
    detalle_cupo_turno: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    road_status: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)

    quote_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quote_valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    quote_source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    quote_confidence: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="freight_quotes")
    campo: Mapped[Optional["Campo"]] = relationship("Campo")
    lote: Mapped[Optional["Lote"]] = relationship("Lote")

    @property
    def humedad_max_recepcion_pct(self) -> Optional[Decimal]:
        return self.max_receiving_moisture_pct

    @humedad_max_recepcion_pct.setter
    def humedad_max_recepcion_pct(self, val: Optional[Decimal]) -> None:
        self.max_receiving_moisture_pct = val


class GrainDelivery(Base):
    """Entidad de entrega de grano / movimiento operativo comercial."""
    __tablename__ = "grain_deliveries"
    __table_args__ = (
        UniqueConstraint("cliente_id", "tracking_number", name="uq_grain_deliveries_cliente_tracking"),
        Index("ix_grain_deliveries_cliente_estado", "cliente_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tracking_number: Mapped[str] = mapped_column(String(50), nullable=False)

    campo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="SET NULL"), nullable=True
    )
    lote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotes.id", ondelete="SET NULL"), nullable=True
    )
    compromiso_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compromisos_grano.id", ondelete="SET NULL"), nullable=True
    )
    freight_quote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_quotes.id", ondelete="SET NULL"), nullable=True
    )

    acopio_receptor: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    destination_final_reference: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    cultivo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    transportista_nombre: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    fecha_planificada: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fecha_salida: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_recepcion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    toneladas_planificadas: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    kg_neto_origen_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    kg_recibido_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    diferencia_total_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    diferencia_total_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)

    estado: Mapped[str] = mapped_column(String(50), default="planificada", nullable=False)
    documentacion_status: Mapped[str] = mapped_column(String(50), default="sin_documentacion", nullable=False)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="deliveries")
    campo: Mapped[Optional["Campo"]] = relationship("Campo")
    lote: Mapped[Optional["Lote"]] = relationship("Lote")
    compromiso: Mapped[Optional["CompromisoGrano"]] = relationship("CompromisoGrano")
    freight_quote: Mapped[Optional["FreightQuote"]] = relationship("FreightQuote")
    waybills: Mapped[List["GrainWaybill"]] = relationship(
        "GrainWaybill", back_populates="entrega", cascade="all, delete-orphan"
    )
    allocations: Mapped[List["StockDeliveryAllocation"]] = relationship(
        "StockDeliveryAllocation", back_populates="delivery", cascade="all, delete-orphan"
    )
    reconciliations: Mapped[List["StockWeightReconciliation"]] = relationship(
        "StockWeightReconciliation", back_populates="delivery", cascade="all, delete-orphan"
    )
    movements: Mapped[List["StockMovement"]] = relationship(
        "StockMovement", foreign_keys="[StockMovement.grain_delivery_id]", back_populates="delivery"
    )


class GrainWaybill(Base):
    """Entidad de Carta de Porte / Movimiento de Transporte de la Entrega."""
    __tablename__ = "grain_waybills"
    __table_args__ = (
        Index("ix_grain_waybills_cliente_numero", "cliente_id", "numero_carta_porte"),
        Index("ix_grain_waybills_entrega", "entrega_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entrega_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grain_deliveries.id", ondelete="CASCADE"), nullable=False, index=True
    )

    numero_carta_porte: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tipo_camion: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    capacidad_referencia_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    tara_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    peso_bruto_origen_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    peso_neto_origen_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    peso_recibido_destino_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    diferencia_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    diferencia_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)

    fecha_carga: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_recepcion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    despatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    despatched_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    referencia_ticket_origen: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    referencia_ticket_destino: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(50), default="planificada", nullable=False)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    entrega: Mapped["GrainDelivery"] = relationship("GrainDelivery", back_populates="waybills")
    reconciliations: Mapped[List["StockWeightReconciliation"]] = relationship(
        "StockWeightReconciliation", back_populates="waybill", cascade="all, delete-orphan"
    )


class StorageLocation(Base):
    """Entidad de Ubicación Física o Custodia de Grano (Silo Propio, Silobolsa, Acopio, etc.)."""
    __tablename__ = "storage_locations"
    __table_args__ = (
        UniqueConstraint("cliente_id", "tipo", "nombre", name="uq_storage_locations_cliente_tipo_nombre"),
        Index("ix_storage_locations_cliente_campo", "cliente_id", "campo_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), default="silo_propio", nullable=False)
    campo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="SET NULL"), nullable=True
    )
    ubicacion_referencia: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    identificador_fisico: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    capacidad_nominal_tn: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    estado: Mapped[str] = mapped_column(String(50), default="activo", nullable=False)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="storage_locations")
    campo: Mapped[Optional["Campo"]] = relationship("Campo")
    partidas: Mapped[List["StockPartida"]] = relationship(
        "StockPartida", back_populates="storage_location", cascade="all, delete-orphan"
    )


class StockPartida(Base):
    """Entidad de Partida Física Identificable de Grano."""
    __tablename__ = "stock_partidas"
    __table_args__ = (
        UniqueConstraint("cliente_id", "tracking_number", name="uq_stock_partidas_cliente_tracking"),
        Index("ix_stock_partidas_cliente_estado", "cliente_id", "estado"),
        Index("ix_stock_partidas_storage_location", "storage_location_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tracking_number: Mapped[str] = mapped_column(String(50), nullable=False)
    cultivo: Mapped[str] = mapped_column(String(50), nullable=False)

    campania_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campanias.id", ondelete="SET NULL"), nullable=True
    )
    campo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campos.id", ondelete="SET NULL"), nullable=True
    )
    lote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lotes.id", ondelete="SET NULL"), nullable=True
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_locations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    fecha_cosecha: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fecha_ingreso: Mapped[date] = mapped_column(Date, nullable=False)
    origen_conocido: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    origen_descripcion: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    cantidad_inicial_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(50), default="activa", nullable=False)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="stock_partidas")
    campania: Mapped[Optional["Campania"]] = relationship("Campania")
    campo: Mapped[Optional["Campo"]] = relationship("Campo")
    lote: Mapped[Optional["Lote"]] = relationship("Lote")
    storage_location: Mapped["StorageLocation"] = relationship("StorageLocation", back_populates="partidas")
    movements: Mapped[List["StockMovement"]] = relationship(
        "StockMovement", back_populates="stock_partida", cascade="all, delete-orphan"
    )
    quality_measurements: Mapped[List["StockQualityMeasurement"]] = relationship(
        "StockQualityMeasurement", back_populates="stock_partida", cascade="all, delete-orphan"
    )
    reservations: Mapped[List["StockReservation"]] = relationship(
        "StockReservation", back_populates="stock_partida", cascade="all, delete-orphan"
    )
    allocations: Mapped[List["StockDeliveryAllocation"]] = relationship(
        "StockDeliveryAllocation", back_populates="stock_partida", cascade="all, delete-orphan"
    )


class StockMovement(Base):
    """Libro de Movimientos Auditables de Stock Físico (Única Fuente de Variación)."""
    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_stock_movements_cliente_partida", "cliente_id", "stock_partida_id"),
        Index("ix_stock_movements_fecha", "fecha_movimiento"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_partida_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_partidas.id", ondelete="CASCADE"), nullable=False, index=True
    )

    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    cantidad_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_movimiento: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    referencia_tipo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    referencia_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    grain_delivery_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grain_deliveries.id", ondelete="SET NULL"), nullable=True
    )
    grain_waybill_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grain_waybills.id", ondelete="SET NULL"), nullable=True
    )
    stock_delivery_allocation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_delivery_allocations.id", ondelete="SET NULL"), nullable=True
    )
    motivo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    stock_partida: Mapped["StockPartida"] = relationship("StockPartida", back_populates="movements")
    delivery: Mapped[Optional["GrainDelivery"]] = relationship("GrainDelivery", foreign_keys=[grain_delivery_id], back_populates="movements")
    waybill: Mapped[Optional["GrainWaybill"]] = relationship("GrainWaybill", foreign_keys=[grain_waybill_id])
    allocation: Mapped[Optional["StockDeliveryAllocation"]] = relationship("StockDeliveryAllocation", foreign_keys=[stock_delivery_allocation_id])
    allocations: Mapped[List["StockDeliveryAllocation"]] = relationship("StockDeliveryAllocation", foreign_keys="[StockDeliveryAllocation.stock_movement_id]", back_populates="stock_movement")


class StockQualityMeasurement(Base):
    """Registro Histórico de Mediciones de Calidad y Condición de Partida."""
    __tablename__ = "stock_quality_measurements"
    __table_args__ = (
        Index("ix_stock_quality_partida_measured", "stock_partida_id", "measured_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_partida_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_partidas.id", ondelete="CASCADE"), nullable=False, index=True
    )

    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    humedad_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    temperatura_c: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    estado_calidad: Mapped[str] = mapped_column(String(50), default="apto", nullable=False)
    fuente: Mapped[str] = mapped_column(String(50), default="propia", nullable=False)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    stock_partida: Mapped["StockPartida"] = relationship("StockPartida", back_populates="quality_measurements")


class StockReservation(Base):
    """Reserva de Stock Físico para un Compromiso Comercial (Bloqueo Comercial)."""
    __tablename__ = "stock_reservations"
    __table_args__ = (
        Index("ix_stock_reservations_cliente_partida", "cliente_id", "stock_partida_id"),
        Index("ix_stock_reservations_compromiso", "compromiso_id"),
        Index("ix_stock_reservations_estado", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_partida_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_partidas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compromiso_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compromisos_grano.id", ondelete="CASCADE"), nullable=False, index=True
    )

    cantidad_reserva_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(50), default="activa", nullable=False)

    fecha_reserva: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_liberacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_liberacion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    released_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="stock_reservations")
    stock_partida: Mapped["StockPartida"] = relationship("StockPartida", back_populates="reservations")
    compromiso: Mapped["CompromisoGrano"] = relationship("CompromisoGrano", back_populates="reservations")
    allocations: Mapped[List["StockDeliveryAllocation"]] = relationship(
        "StockDeliveryAllocation", back_populates="reservation"
    )


class StockDeliveryAllocation(Base):
    """Asignación Manual de Partida a Entrega de Grano (Bloqueo Operativo)."""
    __tablename__ = "stock_delivery_allocations"
    __table_args__ = (
        Index("ix_stock_allocations_cliente_partida", "cliente_id", "stock_partida_id"),
        Index("ix_stock_allocations_delivery", "grain_delivery_id"),
        Index("ix_stock_allocations_reservation", "stock_reservation_id"),
        Index("ix_stock_allocations_estado", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_partida_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_partidas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grain_delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grain_deliveries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_reservation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_reservations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    compromiso_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compromisos_grano.id", ondelete="SET NULL"), nullable=True, index=True
    )

    cantidad_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    origen_asignacion: Mapped[str] = mapped_column(String(50), default="libre", nullable=False)
    estado: Mapped[str] = mapped_column(String(50), default="activa", nullable=False)

    fecha_asignacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_cancelacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_cancelacion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    despatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancelled_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    despatched_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    stock_movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_movements.id", ondelete="SET NULL"), nullable=True
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="stock_allocations")
    stock_partida: Mapped["StockPartida"] = relationship("StockPartida", back_populates="allocations")
    delivery: Mapped["GrainDelivery"] = relationship("GrainDelivery", back_populates="allocations")
    reservation: Mapped[Optional["StockReservation"]] = relationship("StockReservation", back_populates="allocations")
    compromiso: Mapped[Optional["CompromisoGrano"]] = relationship("CompromisoGrano")
    stock_movement: Mapped[Optional["StockMovement"]] = relationship(
        "StockMovement", foreign_keys=[stock_movement_id], back_populates="allocations"
    )


class StockWeightReconciliation(Base):
    """Caso/Registro Auditado de Conciliación de Pesaje Origen vs Destino para Entrega / Carta de Porte."""
    __tablename__ = "stock_weight_reconciliations"
    __table_args__ = (
        Index("ix_stock_reconciliations_cliente", "cliente_id"),
        Index("ix_stock_reconciliations_delivery", "grain_delivery_id"),
        Index("ix_stock_reconciliations_waybill", "grain_waybill_id"),
        Index("ix_stock_reconciliations_estado", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grain_delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grain_deliveries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grain_waybill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grain_waybills.id", ondelete="CASCADE"), nullable=False, index=True
    )

    peso_neto_origen_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    peso_recibido_destino_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    diferencia_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    diferencia_pct: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)

    estado: Mapped[str] = mapped_column(String(50), default="pendiente", nullable=False)
    resolucion_tipo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resolucion_observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    stock_movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_movements.id", ondelete="SET NULL"), nullable=True
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="stock_weight_reconciliations")
    delivery: Mapped["GrainDelivery"] = relationship("GrainDelivery", back_populates="reconciliations")
    waybill: Mapped["GrainWaybill"] = relationship("GrainWaybill", back_populates="reconciliations")
    stock_movement: Mapped[Optional["StockMovement"]] = relationship("StockMovement", foreign_keys=[stock_movement_id])


class EquipoMaquinaria(Base):
    """Maquinaria y Equipos de la Empresa para Servicios a Terceros y Campo Propio."""
    __tablename__ = "equipos_maquinaria"
    __table_args__ = (
        Index("ix_equipos_maquinaria_cliente", "cliente_id"),
        Index("ix_equipos_maquinaria_tipo", "tipo_equipo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo_equipo: Mapped[str] = mapped_column(
        String(50), default=TipoEquipoEnum.PULVERIZADORA.value, nullable=False
    )
    marca_modelo: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    patente_serie: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    propiedad_empresa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    servicios_prestados: Mapped[List["ServicioPrestado"]] = relationship(
        "ServicioPrestado", back_populates="maquinaria"
    )


class ClienteTercero(Base):
    """Clientes Terceros (Productores / Vecinos) que contratan servicios agrícolas."""
    __tablename__ = "clientes_terceros"
    __table_args__ = (
        Index("ix_clientes_terceros_cliente", "cliente_id"),
        Index("ix_clientes_terceros_nombre", "razon_social_nombre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    razon_social_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    cuit_dni: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    localidad_direccion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    servicios_prestados: Mapped[List["ServicioPrestado"]] = relationship(
        "ServicioPrestado", back_populates="cliente_tercero"
    )


class ServicioPrestado(Base):
    """Orden de Trabajo de Servicios Prestados a Terceros (Pulverización, Siembra, etc.)."""
    __tablename__ = "servicios_prestados"
    __table_args__ = (
        Index("ix_servicios_prestados_cliente", "cliente_id"),
        Index("ix_servicios_prestados_tercero", "cliente_tercero_id"),
        Index("ix_servicios_prestados_maquina", "maquinaria_id"),
        Index("ix_servicios_prestados_operador", "operador_id"),
        Index("ix_servicios_prestados_estado", "estado_operativo"),
        CheckConstraint("superficie_ha > 0", name="chk_superficie_positiva"),
        CheckConstraint("monto_total_facturado >= 0", name="chk_monto_facturado_nn"),
        CheckConstraint("pago_operador_negociado >= 0", name="chk_pago_operador_nn"),
        CheckConstraint("imputacion_uso_maquinaria >= 0", name="chk_imputacion_maquina_nn"),
        CheckConstraint("gastos_directos_informados >= 0", name="chk_gastos_informados_nn"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cliente_tercero_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes_terceros.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    maquinaria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipos_maquinaria.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    operador_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    tipo_servicio: Mapped[str] = mapped_column(String(50), default="pulverizacion", nullable=False, index=True)
    fecha_trabajo: Mapped[date] = mapped_column(Date, nullable=False)
    establecimiento_lote_libre: Mapped[str] = mapped_column(String(255), nullable=False)
    superficie_ha: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    precio_unitario_ha: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    monto_total_facturado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    pago_operador_negociado: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    imputacion_uso_maquinaria: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    gastos_directos_informados: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)

    estado_operativo: Mapped[str] = mapped_column(
        String(50), default=EstadoOperativoTrabajoEnum.PRESUPUESTO.value, nullable=False, index=True
    )

    # Campos específicos de pulverización (MVP integrado)
    tipo_aplicacion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    volumen_caldo_lha: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    insumos_aportados_por: Mapped[Optional[str]] = mapped_column(
        String(50), default=InsumosAportadosEnum.CLIENTE.value, nullable=True
    )
    datos_adicionales_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Trazabilidad y auditoría
    creado_por_usuario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    actualizado_por_usuario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    cliente_tercero: Mapped["ClienteTercero"] = relationship("ClienteTercero", back_populates="servicios_prestados")
    maquinaria: Mapped["EquipoMaquinaria"] = relationship("EquipoMaquinaria", back_populates="servicios_prestados")
    cobros: Mapped[List["CobroServicioPrestado"]] = relationship("CobroServicioPrestado", back_populates="servicio_prestado")
    pagos_operador: Mapped[List["PagoOperadorServicio"]] = relationship("PagoOperadorServicio", back_populates="servicio_prestado")


class CobroServicioPrestado(Base):
    """Registro de Cobros Recibidos de Clientes Terceros (Genera Ingreso Financiero)."""
    __tablename__ = "cobros_servicios_prestados"
    __table_args__ = (
        Index("ix_cobros_servicios_cliente", "cliente_id"),
        Index("ix_cobros_servicios_servicio", "servicio_prestado_id"),
        Index("ix_cobros_servicios_idempotencia", "clave_idempotencia"),
        CheckConstraint("monto_cobrado > 0", name="chk_monto_cobrado_positivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    servicio_prestado_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servicios_prestados.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaccion_financiera_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transacciones_financieras.id", ondelete="SET NULL"), nullable=True, index=True
    )

    fecha_cobro: Mapped[date] = mapped_column(Date, nullable=False)
    monto_cobrado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    medio_pago: Mapped[str] = mapped_column(String(50), default=MedioPagoEnum.TRANSFERENCIA.value, nullable=False)
    numero_comprobante: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    clave_idempotencia: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    registrado_por_usuario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    servicio_prestado: Mapped["ServicioPrestado"] = relationship("ServicioPrestado", back_populates="cobros")


class PagoOperadorServicio(Base):
    """Registro de Pagos Efectuados al Operador (Genera Egreso Financiero al Liquidarse)."""
    __tablename__ = "pagos_operadores_servicios"
    __table_args__ = (
        Index("ix_pagos_operadores_cliente", "cliente_id"),
        Index("ix_pagos_operadores_servicio", "servicio_prestado_id"),
        Index("ix_pagos_operadores_idempotencia", "clave_idempotencia"),
        CheckConstraint("monto_pagado > 0", name="chk_monto_pagado_positivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    servicio_prestado_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servicios_prestados.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaccion_financiera_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transacciones_financieras.id", ondelete="SET NULL"), nullable=True, index=True
    )

    fecha_pago: Mapped[date] = mapped_column(Date, nullable=False)
    monto_pagado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    medio_pago: Mapped[str] = mapped_column(String(50), default=MedioPagoEnum.TRANSFERENCIA.value, nullable=False)
    clave_idempotencia: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    registrado_por_usuario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    servicio_prestado: Mapped["ServicioPrestado"] = relationship("ServicioPrestado", back_populates="pagos_operador")







