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
