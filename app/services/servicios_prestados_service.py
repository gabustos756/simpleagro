"""
Capa de Servicio de Dominio para Servicios Prestados / Trabajos a Terceros (EduAgro).
Implementa reglas de negocio, desgloses contables anti-duplicación, validación multi-tenant
y generación exclusiva de TransaccionFinanciera al cobrar/pagar.
"""

from decimal import Decimal
from datetime import date, datetime
import uuid
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    EquipoMaquinaria,
    ClienteTercero,
    ServicioPrestado,
    CobroServicioPrestado,
    PagoOperadorServicio,
    TransaccionFinanciera,
    Usuario,
)
from app.enums import (
    TipoEquipoEnum,
    EstadoOperativoTrabajoEnum,
    MedioPagoEnum,
    InsumosAportadosEnum,
    TipoTransaccion,
)


def calcular_estado_cobro_dinamico(
    monto_total_facturado: Decimal,
    total_cobrado: Decimal,
    pago_operador_negociado: Decimal,
    total_pagado_operador: Decimal,
) -> str:
    """Calcula dinámicamente el estado financiero/cobro del servicio."""
    if total_cobrado <= Decimal("0.00"):
        return "sin_cobrar"
    elif Decimal("0.00") < total_cobrado < monto_total_facturado:
        return "cobro_parcial"
    elif total_cobrado >= monto_total_facturado:
        if total_pagado_operador >= pago_operador_negociado:
            return "liquidado_cerrado"
        return "cobrado_pendiente_operador"
    return "en_proceso"


async def fetch_resumen_servicios_prestados(
    db: AsyncSession, cliente_id: uuid.UUID
) -> Dict[str, Any]:
    """Obtiene agregados KPI y resúmenes de gestión para el dashboard de trabajos a terceros."""
    res_sp = await db.execute(
        select(ServicioPrestado).where(ServicioPrestado.cliente_id == cliente_id)
    )
    servicios = res_sp.scalars().all()

    total_facturado = Decimal("0.00")
    total_pago_operador_negociado = Decimal("0.00")
    total_imputacion_maquinaria = Decimal("0.00")
    total_gastos_informados = Decimal("0.00")
    total_superficie_ha = Decimal("0.00")

    for s in servicios:
        total_facturado += s.monto_total_facturado or Decimal("0.00")
        total_pago_operador_negociado += s.pago_operador_negociado or Decimal("0.00")
        total_imputacion_maquinaria += s.imputacion_uso_maquinaria or Decimal("0.00")
        total_gastos_informados += s.gastos_directos_informados or Decimal("0.00")
        total_superficie_ha += s.superficie_ha or Decimal("0.00")

    # Suma de cobros recibidos
    res_cobros = await db.execute(
        select(func.coalesce(func.sum(CobroServicioPrestado.monto_cobrado), Decimal("0.00")))
        .where(CobroServicioPrestado.cliente_id == cliente_id)
    )
    total_cobrado = res_cobros.scalar_one()

    # Suma de pagos a operadores efectuados
    res_pagos = await db.execute(
        select(func.coalesce(func.sum(PagoOperadorServicio.monto_pagado), Decimal("0.00")))
        .where(PagoOperadorServicio.cliente_id == cliente_id)
    )
    total_pagado_operador = res_pagos.scalar_one()

    total_pendiente_cobro = max(Decimal("0.00"), total_facturado - total_cobrado)
    pago_operador_pendiente_liquidacion = max(Decimal("0.00"), total_pago_operador_negociado - total_pagado_operador)
    margen_neto_estimado = total_facturado - (total_pago_operador_negociado + total_gastos_informados)

    return {
        "cantidad_trabajos": len(servicios),
        "total_superficie_ha": float(total_superficie_ha),
        "total_facturado": float(total_facturado),
        "total_cobrado": float(total_cobrado),
        "total_pendiente_cobro": float(total_pendiente_cobro),
        "pago_operador_negociado": float(total_pago_operador_negociado),
        "pago_operador_pagado": float(total_pagado_operador),
        "pago_operador_pendiente_liquidacion": float(pago_operador_pendiente_liquidacion),
        "imputacion_uso_maquinaria": float(total_imputacion_maquinaria),
        "gastos_directos_informados": float(total_gastos_informados),
        "margen_neto_estimado": float(margen_neto_estimado),
    }


async def create_equipo_maquinaria(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    nombre: str,
    tipo_equipo: str = TipoEquipoEnum.PULVERIZADORA.value,
    marca_modelo: Optional[str] = None,
    patente_serie: Optional[str] = None,
    propiedad_empresa: bool = True,
) -> EquipoMaquinaria:
    """Crea una nueva maquinaria/equipo para el tenant."""
    equipo = EquipoMaquinaria(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        nombre=nombre.strip(),
        tipo_equipo=tipo_equipo,
        marca_modelo=marca_modelo.strip() if marca_modelo else None,
        patente_serie=patente_serie.strip() if patente_serie else None,
        propiedad_empresa=propiedad_empresa,
        activo=True,
    )
    db.add(equipo)
    await db.commit()
    await db.refresh(equipo)
    return equipo


async def create_cliente_tercero(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    razon_social_nombre: str,
    cuit_dni: Optional[str] = None,
    telefono: Optional[str] = None,
    email: Optional[str] = None,
    localidad_direccion: Optional[str] = None,
) -> ClienteTercero:
    """Crea un cliente tercero comercial para el tenant."""
    tercero = ClienteTercero(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        razon_social_nombre=razon_social_nombre.strip(),
        cuit_dni=cuit_dni.strip() if cuit_dni else None,
        telefono=telefono.strip() if telefono else None,
        email=email.strip() if email else None,
        localidad_direccion=localidad_direccion.strip() if localidad_direccion else None,
        activo=True,
    )
    db.add(tercero)
    await db.commit()
    await db.refresh(tercero)
    return tercero


def validar_permisos_usuario(usuario_rol: str, accion: str) -> None:
    """
    Valida permisos de rol según el contrato de negocio:
    - operario_campo (Andrés): sólo puede actualizar ejecución (estado operativo, superficie real, observaciones).
    - admin / administrador_finanzas: control completo sobre economía, negociación y movimientos.
    """
    rol = (usuario_rol or "").lower()

    if accion in ["modificar_economia", "registrar_cobro", "registrar_pago_operador", "cerrar_liquidacion"]:
        if rol in ["operario_campo"]:
            raise PermissionError("El rol 'operario_campo' no tiene permisos para realizar operaciones financieras o modificar la negociación económica.")
    elif accion in ["actualizar_ejecucion", "marcar_realizado"]:
        # Operario y admin están permitidos
        pass


async def create_servicio_prestado(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    cliente_tercero_id: uuid.UUID,
    maquinaria_id: uuid.UUID,
    operador_id: uuid.UUID,
    fecha_trabajo: date,
    establecimiento_lote_libre: str,
    superficie_ha: Decimal,
    monto_total_facturado: Decimal,
    precio_unitario_ha: Optional[Decimal] = None,
    pago_operador_negociado: Decimal = Decimal("0.00"),
    imputacion_uso_maquinaria: Decimal = Decimal("0.00"),
    gastos_directos_informados: Decimal = Decimal("0.00"),
    tipo_servicio: str = "pulverizacion",
    tipo_aplicacion: Optional[str] = None,
    volumen_caldo_lha: Optional[Decimal] = None,
    insumos_aportados_por: str = InsumosAportadosEnum.CLIENTE.value,
    observaciones: Optional[str] = None,
    datos_adicionales_json: Optional[dict] = None,
    creado_por_usuario_id: Optional[uuid.UUID] = None,
) -> ServicioPrestado:
    """Crea y valida una nueva Orden de Trabajo de Servicio Prestado a Tercero."""

    # 1. Validaciones numéricas de dominio
    if superficie_ha <= Decimal("0.00"):
        raise ValueError("La superficie trabajada (ha) debe ser strictly mayor a 0.")
    if monto_total_facturado < Decimal("0.00"):
        raise ValueError("El monto total facturado al cliente no puede ser negativo.")
    if pago_operador_negociado < Decimal("0.00"):
        raise ValueError("El pago negociado al operador no puede ser negativo.")
    if imputacion_uso_maquinaria < Decimal("0.00"):
        raise ValueError("La imputación de uso de maquinaria no puede ser negativa.")
    if gastos_directos_informados < Decimal("0.00"):
        raise ValueError("Los gastos directos informados no pueden ser negativos.")

    # 2. Validación de pertenencia Multi-tenant estricta
    tercero = await db.get(ClienteTercero, cliente_tercero_id)
    if not tercero or tercero.cliente_id != cliente_id:
        raise PermissionError("El cliente tercero seleccionado no pertenece al inquilino activo.")

    maquina = await db.get(EquipoMaquinaria, maquinaria_id)
    if not maquina or maquina.cliente_id != cliente_id:
        raise PermissionError("La maquinaria seleccionada no pertenece al inquilino activo.")

    operador = await db.get(Usuario, operador_id)
    if not operador or operador.cliente_id != cliente_id:
        raise PermissionError("El operador seleccionado no pertenece al inquilino activo.")

    # 3. Creación de la orden
    orden = ServicioPrestado(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        cliente_tercero_id=cliente_tercero_id,
        maquinaria_id=maquinaria_id,
        operador_id=operador_id,
        tipo_servicio=tipo_servicio,
        fecha_trabajo=fecha_trabajo,
        establecimiento_lote_libre=establecimiento_lote_libre.strip(),
        superficie_ha=superficie_ha,
        precio_unitario_ha=precio_unitario_ha,
        monto_total_facturado=monto_total_facturado,
        pago_operador_negociado=pago_operador_negociado,
        imputacion_uso_maquinaria=imputacion_uso_maquinaria,
        gastos_directos_informados=gastos_directos_informados,
        estado_operativo=EstadoOperativoTrabajoEnum.PRESUPUESTO.value,
        tipo_aplicacion=tipo_aplicacion,
        volumen_caldo_lha=volumen_caldo_lha,
        insumos_aportados_por=insumos_aportados_por,
        datos_adicionales_json=datos_adicionales_json,
        creado_por_usuario_id=creado_por_usuario_id,
        observaciones=observaciones,
    )
    db.add(orden)
    await db.commit()
    await db.refresh(orden)
    return orden


async def registrar_cobro_servicio(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    servicio_prestado_id: uuid.UUID,
    fecha_cobro: date,
    monto_cobrado: Decimal,
    medio_pago: str = MedioPagoEnum.TRANSFERENCIA.value,
    numero_comprobante: Optional[str] = None,
    observaciones: Optional[str] = None,
    clave_idempotencia: Optional[str] = None,
    registrado_por_usuario_id: Optional[uuid.UUID] = None,
    autorizacion_sobrepago: bool = False,
    motivo_sobrepago: Optional[str] = None,
) -> Tuple[CobroServicioPrestado, TransaccionFinanciera]:
    """
    Registra un cobro efectivo de un cliente tercero.
    Genera OBLIGATORIAMENTE una TransaccionFinanciera de tipo INGRESO.
    Garantiza idempotencia si se provee clave_idempotencia.
    """
    if monto_cobrado <= Decimal("0.00"):
        raise ValueError("El monto a cobrar debe ser estrictamente mayor a 0.")

    # Check de Idempotencia por clave única
    if clave_idempotencia:
        res_idemp = await db.execute(
            select(CobroServicioPrestado).where(
                CobroServicioPrestado.cliente_id == cliente_id,
                CobroServicioPrestado.clave_idempotencia == clave_idempotencia.strip(),
            )
        )
        cobro_existente = res_idemp.scalars().first()
        if cobro_existente:
            tx_existente = await db.get(TransaccionFinanciera, cobro_existente.transaccion_financiera_id)
            return cobro_existente, tx_existente

    orden = await db.get(ServicioPrestado, servicio_prestado_id)
    if not orden or orden.cliente_id != cliente_id:
        raise PermissionError("La orden de servicio prestado no pertenece al inquilino activo.")

    # Calcular suma de cobros previos
    res = await db.execute(
        select(func.coalesce(func.sum(CobroServicioPrestado.monto_cobrado), Decimal("0.00")))
        .where(CobroServicioPrestado.servicio_prestado_id == servicio_prestado_id)
    )
    cobrado_previo = res.scalar_one()

    if (cobrado_previo + monto_cobrado) > orden.monto_total_facturado:
        if not autorizacion_sobrepago:
            raise ValueError(
                f"El cobro de ${monto_cobrado} supera el total facturado (${orden.monto_total_facturado}). "
                f"Cobrado previo: ${cobrado_previo}. Requiere autorización explícita de sobrepago con motivo registrado."
            )
        if not motivo_sobrepago or not motivo_sobrepago.strip():
            raise ValueError("La autorización de sobrepago requiere especificar el motivo explícito.")

    # 1. Crear TransaccionFinanciera (INGRESO ÚNICO)
    transaccion = TransaccionFinanciera(
        id=uuid.uuid4(),
        tipo=TipoTransaccion.INGRESO,
        monto_usd=monto_cobrado,
        monto_ars=monto_cobrado,
        cotizacion_dolar=Decimal("1.00"),
        concepto=f"Cobro servicio prestado a tercero #{str(orden.id)[:8]} ({orden.establecimiento_lote_libre})",
        pagado=True,
    )
    db.add(transaccion)
    await db.flush()

    # 2. Crear CobroServicioPrestado
    cobro = CobroServicioPrestado(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        servicio_prestado_id=servicio_prestado_id,
        transaccion_financiera_id=transaccion.id,
        fecha_cobro=fecha_cobro,
        monto_cobrado=monto_cobrado,
        medio_pago=medio_pago,
        numero_comprobante=numero_comprobante,
        clave_idempotencia=clave_idempotencia.strip() if clave_idempotencia else None,
        registrado_por_usuario_id=registrado_por_usuario_id,
        observaciones=f"{observaciones or ''} {f'[Motivo sobrepago: {motivo_sobrepago}]' if motivo_sobrepago else ''}".strip(),
    )
    db.add(cobro)
    await db.commit()
    await db.refresh(cobro)
    return cobro, transaccion


async def registrar_pago_operador(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    servicio_prestado_id: uuid.UUID,
    fecha_pago: date,
    monto_pagado: Decimal,
    medio_pago: str = MedioPagoEnum.TRANSFERENCIA.value,
    observaciones: Optional[str] = None,
    clave_idempotencia: Optional[str] = None,
    registrado_por_usuario_id: Optional[uuid.UUID] = None,
    autorizacion_sobrepago: bool = False,
    motivo_sobrepago: Optional[str] = None,
) -> Tuple[PagoOperadorServicio, TransaccionFinanciera]:
    """
    Registra un pago efectivo liquidado al operador (Andrés).
    Genera OBLIGATORIAMENTE una TransaccionFinanciera de tipo EGRESO.
    Garantiza idempotencia si se provee clave_idempotencia.
    """
    if monto_pagado <= Decimal("0.00"):
        raise ValueError("El monto a pagar al operador debe ser estrictamente mayor a 0.")

    # Check de Idempotencia por clave única
    if clave_idempotencia:
        res_idemp = await db.execute(
            select(PagoOperadorServicio).where(
                PagoOperadorServicio.cliente_id == cliente_id,
                PagoOperadorServicio.clave_idempotencia == clave_idempotencia.strip(),
            )
        )
        pago_existente = res_idemp.scalars().first()
        if pago_existente:
            tx_existente = await db.get(TransaccionFinanciera, pago_existente.transaccion_financiera_id)
            return pago_existente, tx_existente

    orden = await db.get(ServicioPrestado, servicio_prestado_id)
    if not orden or orden.cliente_id != cliente_id:
        raise PermissionError("La orden de servicio prestado no pertenece al inquilino activo.")

    # Límite acumulado de pagos al operador vs pactado
    res_pagos = await db.execute(
        select(func.coalesce(func.sum(PagoOperadorServicio.monto_pagado), Decimal("0.00")))
        .where(PagoOperadorServicio.servicio_prestado_id == servicio_prestado_id)
    )
    pagado_previo = res_pagos.scalar_one()

    if (pagado_previo + monto_pagado) > orden.pago_operador_negociado:
        if not autorizacion_sobrepago:
            raise ValueError(
                f"El pago de ${monto_pagado} al operador supera el negociado (${orden.pago_operador_negociado}). "
                f"Pagado previo: ${pagado_previo}. Requiere autorización explícita con motivo registrado."
            )
        if not motivo_sobrepago or not motivo_sobrepago.strip():
            raise ValueError("La autorización de sobrepago al operador requiere especificar el motivo explícito.")

    # 1. Crear TransaccionFinanciera (EGRESO OPERADOR)
    transaccion = TransaccionFinanciera(
        id=uuid.uuid4(),
        tipo=TipoTransaccion.EGRESO,
        monto_usd=monto_pagado,
        monto_ars=monto_pagado,
        cotizacion_dolar=Decimal("1.00"),
        concepto=f"Pago liquidado a operador por servicio prestado #{str(orden.id)[:8]}",
        pagado=True,
    )
    db.add(transaccion)
    await db.flush()

    # 2. Crear PagoOperadorServicio
    pago = PagoOperadorServicio(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        servicio_prestado_id=servicio_prestado_id,
        transaccion_financiera_id=transaccion.id,
        fecha_pago=fecha_pago,
        monto_pagado=monto_pagado,
        medio_pago=medio_pago,
        clave_idempotencia=clave_idempotencia.strip() if clave_idempotencia else None,
        registrado_por_usuario_id=registrado_por_usuario_id,
        observaciones=f"{observaciones or ''} {f'[Motivo sobrepago: {motivo_sobrepago}]' if motivo_sobrepago else ''}".strip(),
    )
    db.add(pago)
    await db.commit()
    await db.refresh(pago)
    return pago, transaccion


async def cancelar_servicio_prestado(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    servicio_prestado_id: uuid.UUID,
    motivo_cancelacion: str,
    actualizado_por_usuario_id: Optional[uuid.UUID] = None,
    forzar_con_movimientos: bool = False,
) -> ServicioPrestado:
    """
    Cancela una orden de trabajo de servicio prestado.
    Si ya existen cobros o pagos al operador registrados, impide la cancelación salvo bandera explícita.
    """
    if not motivo_cancelacion or not motivo_cancelacion.strip():
        raise ValueError("Para cancelar la orden de trabajo se requiere un motivo explicativo obligatorio.")

    orden = await db.get(ServicioPrestado, servicio_prestado_id)
    if not orden or orden.cliente_id != cliente_id:
        raise PermissionError("La orden de servicio prestado no pertenece al inquilino activo.")

    # Verificar si existen movimientos financieros
    res_cobros = await db.execute(
        select(func.count(CobroServicioPrestado.id)).where(CobroServicioPrestado.servicio_prestado_id == servicio_prestado_id)
    )
    count_cobros = res_cobros.scalar_one()

    res_pagos = await db.execute(
        select(func.count(PagoOperadorServicio.id)).where(PagoOperadorServicio.servicio_prestado_id == servicio_prestado_id)
    )
    count_pagos = res_pagos.scalar_one()

    if (count_cobros > 0 or count_pagos > 0) and not forzar_con_movimientos:
        raise ValueError(
            f"No se puede cancelar la orden #{str(orden.id)[:8]} porque tiene {count_cobros} cobros y {count_pagos} pagos "
            f"financieros registrados. Se requiere confirmación explícita para forzar la anulación."
        )

    orden.estado_operativo = EstadoOperativoTrabajoEnum.CANCELADO.value
    orden.actualizado_por_usuario_id = actualizado_por_usuario_id
    orden.observaciones = f"{orden.observaciones or ''} [CANCELADO: {motivo_cancelacion.strip()}]".strip()

    await db.commit()
    await db.refresh(orden)
    return orden
