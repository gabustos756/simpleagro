from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums import (
    EstadoCartaDePorte,
    EstadoServicio,
    EstadoServicioInstaladoEnum,
    FrecuenciaPagoEnum,
    RolUsuario,
    TenenciaTipoEnum,
    TipoLabor,
    TipoServicioEnum,
    TipoTransaccion,
)

# ----------------------------------------------------------------------
# 0. Cliente, Campo & Instalacion Schemas
# ----------------------------------------------------------------------


class ClienteBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=150, example="Establecimiento Agropecuario")
    cuit: Optional[str] = Field(None, example="30-71234567-8")
    ubicacion: Optional[str] = Field(None, example="Río Cuarto, Córdoba")
    activo: bool = True


class ClienteCreate(ClienteBase):
    pass


class ClienteResponse(ClienteBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fecha_creacion: datetime


class CampoBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=150, example="Campo Don Alfredo")
    ubicacion: Optional[str] = Field(None, example="Río Cuarto, Córdoba")
    localidad_referencia: Optional[str] = Field(None, example="Río Cuarto, Córdoba")
    latitud: Optional[float] = Field(None, example=-31.4201)
    longitud: Optional[float] = Field(None, example=-64.1888)
    hectareas_totales: float = Field(..., ge=0, example=500.0)
    cliente_id: Optional[uuid.UUID] = None


class CampoCreate(CampoBase):
    pass


class CampoResponse(CampoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fecha_creacion: datetime


class InstalacionBase(BaseModel):
    campo_id: uuid.UUID
    nombre: str = Field(..., min_length=2, max_length=150, example="Casa Principal")
    tipo: str = Field(default="casa", example="casa")  # casa, galpon, deposito, pozo_bomba
    ubicacion_notas: Optional[str] = None
    cliente_id: Optional[uuid.UUID] = None


class InstalacionCreate(InstalacionBase):
    pass


class InstalacionResponse(InstalacionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


# ----------------------------------------------------------------------
# ServicioInstalado Schemas
# ----------------------------------------------------------------------


class ServicioInstaladoBase(BaseModel):
    campo_id: uuid.UUID
    instalacion_id: Optional[uuid.UUID] = None
    tipo_servicio: TipoServicioEnum
    concepto: str = Field(..., min_length=2, max_length=200, example="Luz Rural - EPEC Bomba Lote 2")
    proveedor: str = Field(..., min_length=2, max_length=150, example="EPEC")
    frecuencia_pago: FrecuenciaPagoEnum = FrecuenciaPagoEnum.MENSUAL
    monto_estimado_ars: Decimal = Field(..., ge=0)
    monto_real_ars: Decimal = Field(..., ge=0)
    monto_usd: Decimal = Field(..., ge=0)
    fecha_vencimiento: date
    estado: EstadoServicioInstaladoEnum = EstadoServicioInstaladoEnum.PENDIENTE
    comprobante_url: Optional[str] = None
    observaciones: Optional[str] = None
    cliente_id: Optional[uuid.UUID] = None


class ServicioInstaladoCreate(ServicioInstaladoBase):
    pass


class ServicioInstaladoResponse(ServicioInstaladoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


# ----------------------------------------------------------------------
# Sub-Schemas de Apoyo
# ----------------------------------------------------------------------


class GeoLocationSchema(BaseModel):
    lat: float = Field(..., description="Latitud geográfica", example=-31.4201)
    lng: float = Field(..., description="Longitud geográfica", example=-64.1888)


class InsumoUtilizadoItem(BaseModel):
    insumo_id: uuid.UUID = Field(..., description="ID del insumo en inventario")
    cantidad: float = Field(..., gt=0, description="Cantidad del insumo utilizada")
    unidad: str = Field(..., example="l/ha", description="Unidad de medida")


# ----------------------------------------------------------------------
# 1. Usuario Schemas
# ----------------------------------------------------------------------


class UsuarioBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100, example="Juan Pérez")
    email: EmailStr = Field(..., example="juan.perez@eduagro.com.ar")
    rol: RolUsuario
    cliente_id: Optional[uuid.UUID] = None


class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=6, description="Contraseña en texto plano")


class UsuarioResponse(UsuarioBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fecha_creacion: datetime
    cliente: Optional[ClienteResponse] = None


# ----------------------------------------------------------------------
# 2. Lote Schemas
# ----------------------------------------------------------------------


class LoteBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100, example="Lote 1 - El Norte")
    campo_id: Optional[uuid.UUID] = None
    campania_id: Optional[uuid.UUID] = None
    cliente_id: Optional[uuid.UUID] = None
    superficie_total_ha: float = Field(..., gt=0, example=150.0)
    superficie_productiva_ha: float = Field(..., gt=0, example=145.0)
    tenencia_tipo: TenenciaTipoEnum = TenenciaTipoEnum.PROPIO
    costo_alquiler_usd_ha: Optional[Decimal] = Field(None, ge=0)
    vencimiento_alquiler: Optional[date] = None
    notas_alquiler: Optional[str] = None
    cultivo_anterior: Optional[str] = Field(None, example="Trigo 24/25")
    cultivo_actual: Optional[str] = Field(None, example="Soja 1ra")
    cultivo_planificado: Optional[str] = Field(None, example="Maíz Tardío 26/27")
    tipo_suelo: Optional[str] = Field(None, example="Argiudol Típico")
    geolocalizacion_lat_lng: Optional[GeoLocationSchema] = None
    qq_ha_estimado: Optional[float] = Field(None, ge=0, example=38.5)
    qq_ha_real: Optional[float] = Field(None, ge=0, example=41.2)
    produccion_total_qq: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None


class LoteCreate(LoteBase):
    pass


class LoteResponse(LoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
