import enum


class RolUsuario(str, enum.Enum):
    ADMIN = "admin"
    PRODUCTOR = "productor"
    OPERARIO_CAMPO = "operario_campo"
    ADMINISTRADOR_FINANZAS = "administrador_finanzas"


class TenenciaTipoEnum(str, enum.Enum):
    PROPIO = "propio"
    ALQUILADO = "alquilado"


class EstadoProductivoLoteEnum(str, enum.Enum):
    BARBECHO = "barbecho"
    RECIEN_SEMBRADO = "recien_sembrado"
    EN_CRECIMIENTO = "en_crecimiento"
    DESARROLLO_AVANZADO = "desarrollo_avanzado"
    LISTO_COSECHA = "listo_cosecha"
    RECIEN_COSECHADO = "recien_cosechado"
    CON_ALERTA = "con_alerta"


class TipoServicioEnum(str, enum.Enum):
    LUZ_RURAL = "luz_rural"
    AGUA = "agua"
    INTERNET = "internet"
    COMBUSTIBLE = "combustible"
    MANTENIMIENTO = "mantenimiento"
    IMPUESTO_TASA = "impuesto_tasa"


class EstadoServicioInstaladoEnum(str, enum.Enum):
    AL_DIA = "al_dia"
    PENDIENTE = "pendiente"
    VENCIDO = "vencido"
    EN_REVISION = "en_revision"


class FrecuenciaPagoEnum(str, enum.Enum):
    MENSUAL = "mensual"
    BIMENSUAL = "bimensual"
    ANUAL = "anual"
    EVENTUAL = "eventual"


class TipoLabor(str, enum.Enum):
    SIEMBRA = "siembra"
    PULVERIZACION = "pulverizacion"
    COSECHA = "cosecha"
    FERTILIZACION = "fertilizacion"


class EstadoServicio(str, enum.Enum):
    PENDIENTE = "pendiente"
    PAGADO = "pagado"
    VENCIDO = "vencido"


class EstadoCartaDePorte(str, enum.Enum):
    EN_TRANSITO = "en_transito"
    DESCARGADO = "descargado"
    LIQUIDADO = "liquidado"


class TipoTransaccion(str, enum.Enum):
    INGRESO = "ingreso"
    EGRESO = "egreso"


class TipoPrecioEnum(str, enum.Enum):
    FIJO = "fijo"
    A_FIJAR = "a_fijar"


class UbicacionStockEnum(str, enum.Enum):
    SILO_BOLSA = "silo_bolsa"
    ACOPIO_TERCERO = "acopio_tercero"
    PUERTO = "puerto"


class TipoCompromisoEnum(str, enum.Enum):
    ALQUILER_ARRENDAMIENTO = "alquiler_arrendamiento"
    CANJE_INSUMOS = "canje_insumos"
    OTRO = "otro"


class EstadoCaminoEnum(str, enum.Enum):
    GOOD = "good"
    CONDITIONED = "conditioned"
    POOR = "poor"
    IMPASSABLE = "impassable"
    UNKNOWN = "unknown"


class EstadoRecepcionEnum(str, enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class FuenteCotizacionFleteEnum(str, enum.Enum):
    MANUAL = "manual"
    TRANSPORTER_QUOTE = "transporter_quote"
    ESTIMATED = "estimated"
    EXTERNAL = "external"


class ConfianzaCotizacionEnum(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CultivoCotizacionEnum(str, enum.Enum):
    MAIZ = "maiz"
    SOJA = "soja"
    TRIGO = "trigo"
    SORGO = "sorgo"
    NO_ESPECIFICADO = "no_especificado"


class CondicionPrecioEnum(str, enum.Enum):
    DISPONIBLE_SPOT = "disponible_spot"
    A_FIJAR = "a_fijar"
    CONTRATO = "contrato"
    FUTURO = "futuro"
    A_CONFIRMAR = "a_confirmar"


class EstadoEntregaEnum(str, enum.Enum):
    PLANIFICADA = "planificada"
    EN_TRANSITO = "en_transito"
    RECIBIDA = "recibida"
    LIQUIDADA = "liquidada"
    OBSERVADA = "observada"
    CANCELADA = "cancelada"


class EstadoDocumentacionEnum(str, enum.Enum):
    SIN_DOCUMENTACION = "sin_documentacion"
    CARTA_PENDIENTE = "carta_pendiente"
    PARCIAL = "parcial"
    COMPLETA = "completa"
    OBSERVADA = "observada"


class EstadoWaybillEnum(str, enum.Enum):
    PLANIFICADA = "planificada"
    CARGADA = "cargada"
    EN_TRANSITO = "en_transito"
    RECIBIDA = "recibida"
    OBSERVADA = "observada"
    ANULADA = "anulada"


class TipoCamionEnum(str, enum.Enum):
    NORMAL = "normal"
    VULCANO = "vulcano"
    OTRO = "otro"



