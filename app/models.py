from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import (
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
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente", back_populates="servicios_instalados")
    campo: Mapped["Campo"] = relationship("Campo", back_populates="servicios_instalados")
    instalacion: Mapped[Optional["Instalacion"]] = relationship("Instalacion", back_populates="servicios")


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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True
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



