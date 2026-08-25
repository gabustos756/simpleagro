"""
Servicio de Dominio para el Módulo de Insumos y Abastecimiento (EduAgro V3).
Implementa:
- Recálculo de Promedio Ponderado Móvil (PPP) Bimoneda.
- Compras e ingresos físicos integrados a TransaccionFinanciera (sin duplicar egresos).
- Consumos reales en labores y servicios prestados a terceros.
- Transferencias atómicas entre ubicaciones vinculadas por grupo_transferencia_id.
- Auditorías y recuentos físicos con motivo obligatorio para ajustes negativos.
- Motor de verificación de disponibilidad pre-labor.
- Control de idempotencia compuesta por tenant y permisos de usuario.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    CategoriaInsumoEnum,
    MonedaEnum,
    TipoMovimientoInsumoEnum,
    TipoTransaccion,
    UnidadMedidaInsumoEnum,
)
from app.models import (
    Cliente,
    Insumo,
    InsumoCompra,
    InsumoLote,
    InsumoLoteSaldoUbicacion,
    InsumoMovimiento,
    InsumoNecesidadPlan,
    InsumoRecuento,
    InsumoReserva,
    InsumoSaldoUbicacion,
    LaborCampo,
    Lote,
    ServicioPrestado,
    StorageLocation,
    TransaccionFinanciera,
    Usuario,
)


UNIDADES_VALIDAS_POR_CATEGORIA: Dict[CategoriaInsumoEnum, List[UnidadMedidaInsumoEnum]] = {
    CategoriaInsumoEnum.SEMILLA: [UnidadMedidaInsumoEnum.BOLSA, UnidadMedidaInsumoEnum.KG],
    CategoriaInsumoEnum.COMBUSTIBLE: [UnidadMedidaInsumoEnum.LITRO],
    CategoriaInsumoEnum.FERTILIZANTE: [UnidadMedidaInsumoEnum.KG, UnidadMedidaInsumoEnum.BOLSA],
    CategoriaInsumoEnum.FITOSANITARIO: [UnidadMedidaInsumoEnum.LITRO, UnidadMedidaInsumoEnum.KG, UnidadMedidaInsumoEnum.UNIDAD],
    CategoriaInsumoEnum.REPUESTO: [UnidadMedidaInsumoEnum.UNIDAD],
    CategoriaInsumoEnum.OTRO: [UnidadMedidaInsumoEnum.UNIDAD, UnidadMedidaInsumoEnum.KG, UnidadMedidaInsumoEnum.LITRO],
}


def validar_categoria_unidad(categoria: CategoriaInsumoEnum, unidad_medida: UnidadMedidaInsumoEnum) -> None:
    """Valida que la unidad de medida sea estrictamente coherente con la categoría del insumo."""
    unidades_permitidas = UNIDADES_VALIDAS_POR_CATEGORIA.get(categoria, [])
    if unidad_medida not in unidades_permitidas:
        permitidas_str = ", ".join([u.value for u in unidades_permitidas])
        raise ValueError(
            f"La unidad de medida '{unidad_medida.value}' no es válida para la categoría '{categoria.value}'. "
            f"Unidades permitidas para {categoria.value}: [{permitidas_str}]."
        )


def validar_permisos_insumos(usuario_rol: str, accion: str) -> None:
    """Valida permisos por rol para el módulo de insumos."""
    rol = (usuario_rol or "").lower()

    if accion in ["registrar_compra", "aprobar_recuento", "modificar_catalogo", "crear_catalogo", "desactivar_catalogo"]:
        if rol in ["operario_campo"]:
            raise PermissionError(f"El rol '{rol}' no tiene permisos para ejecutar '{accion}'.")
    elif accion in ["confirmar_consumo", "registrar_recuento_fisico", "transferir_stock", "consultar_catalogo"]:
        # Operario y administración están permitidos
        pass


async def crear_insumo_catalogo(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    nombre: str,
    categoria: CategoriaInsumoEnum,
    unidad_medida: UnidadMedidaInsumoEnum,
    principio_activo_formula: Optional[str] = None,
    concentracion: Optional[str] = None,
    unidad_empaque: Optional[str] = None,
    punto_pedido_minimo: Decimal = Decimal("0.0000"),
    usuario_rol: str = "administracion",
) -> Insumo:
    """
    Crea un nuevo insumo en el catálogo del cliente.
    No genera stock, movimientos ni transacciones financieras.
    """
    validar_permisos_insumos(usuario_rol, "crear_catalogo")
    validar_categoria_unidad(categoria, unidad_medida)

    nombre_clean = (nombre or "").strip()
    if not nombre_clean:
        raise ValueError("El nombre del insumo es obligatorio.")

    # Validar unicidad por cliente
    res_exist = await db.execute(
        select(Insumo).where(Insumo.cliente_id == cliente_id, func.lower(Insumo.nombre) == nombre_clean.lower())
    )
    if res_exist.scalars().first():
        raise ValueError(f"Ya existe un insumo registrado con el nombre '{nombre_clean}'.")

    insumo = Insumo(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        nombre=nombre_clean,
        categoria=categoria,
        unidad_medida=unidad_medida,
        principio_activo_formula=principio_activo_formula.strip() if principio_activo_formula else None,
        concentracion=concentracion.strip() if concentracion else None,
        unidad_empaque=unidad_empaque.strip() if unidad_empaque else None,
        punto_pedido_minimo=max(Decimal("0.0000"), punto_pedido_minimo),
        activo=True,
    )
    db.add(insumo)
    await db.commit()
    await db.refresh(insumo)
    return insumo


async def editar_insumo_catalogo(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    nombre: str,
    categoria: CategoriaInsumoEnum,
    unidad_medida: UnidadMedidaInsumoEnum,
    principio_activo_formula: Optional[str] = None,
    concentracion: Optional[str] = None,
    unidad_empaque: Optional[str] = None,
    punto_pedido_minimo: Decimal = Decimal("0.0000"),
    usuario_rol: str = "administracion",
) -> Insumo:
    """
    Edita la información descriptiva de un insumo.
    Si el insumo ya posee movimientos o saldos, bloquea la modificación arbitraria de categoría y unidad.
    """
    validar_permisos_insumos(usuario_rol, "modificar_catalogo")
    validar_categoria_unidad(categoria, unidad_medida)

    insumo = await db.get(Insumo, insumo_id)
    if not insumo or insumo.cliente_id != cliente_id:
        raise ValueError("El insumo no existe o no pertenece al cliente.")

    nombre_clean = (nombre or "").strip()
    if not nombre_clean:
        raise ValueError("El nombre del insumo es obligatorio.")

    # Verificar si ya posee movimientos de stock registrados
    res_mov = await db.execute(
        select(func.count(InsumoMovimiento.id)).where(
            InsumoMovimiento.cliente_id == cliente_id,
            InsumoMovimiento.insumo_id == insumo_id,
        )
    )
    has_movements = (res_mov.scalar_one() or 0) > 0

    if has_movements:
        if insumo.categoria != categoria:
            raise ValueError("No se puede modificar la categoría de un insumo que ya posee movimientos de stock registrados. Si requiere corregirlo, efectúe un ajuste de inventario y desactive el insumo.")
        if insumo.unidad_medida != unidad_medida:
            raise ValueError("No se puede modificar la unidad de medida de un insumo que ya posee movimientos de stock registrados. Si requiere corregirlo, efectúe un ajuste de inventario y desactive el insumo.")

    insumo.nombre = nombre_clean
    insumo.categoria = categoria
    insumo.unidad_medida = unidad_medida
    insumo.principio_activo_formula = principio_activo_formula.strip() if principio_activo_formula else None
    insumo.concentracion = concentracion.strip() if concentracion else None
    insumo.unidad_empaque = unidad_empaque.strip() if unidad_empaque else None
    insumo.punto_pedido_minimo = max(Decimal("0.0000"), punto_pedido_minimo)

    await db.commit()
    await db.refresh(insumo)
    return insumo


async def cambiar_estado_insumo_catalogo(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    nuevo_estado_activo: Optional[bool] = None,
    usuario_rol: str = "administracion",
) -> Insumo:
    """
    Realiza la baja lógica (activo=False) o activación de un insumo en el catálogo.
    Bloquea la desactivación si existen reservas activas pendientes.
    """
    validar_permisos_insumos(usuario_rol, "desactivar_catalogo")

    insumo = await db.get(Insumo, insumo_id)
    if not insumo or insumo.cliente_id != cliente_id:
        raise ValueError("El insumo no existe o no pertenece al cliente.")

    target_state = nuevo_estado_activo if nuevo_estado_activo is not None else not insumo.activo

    if not target_state:
        # Validar reservas activas pendientes
        res_res = await db.execute(
            select(func.count(InsumoReserva.id)).where(
                InsumoReserva.cliente_id == cliente_id,
                InsumoReserva.insumo_id == insumo_id,
                InsumoReserva.estado_reserva == "activa",
            )
        )
        cant_reservas = res_res.scalar_one() or 0
        if cant_reservas > 0:
            raise ValueError(f"No se puede desactivar el insumo '{insumo.nombre}' porque posee {cant_reservas} reserva(s) activa(s) pendiente(s). Libere o consuma las reservas antes de desactivar.")

    insumo.activo = target_state
    await db.commit()
    await db.refresh(insumo)
    return insumo


def calcular_valores_bimoneda(
    monto_unitario: Decimal,
    cantidad: Decimal,
    moneda_origen: MonedaEnum,
    cotizacion_usd_ars: Decimal,
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    Calcula de forma transparente y coherente los costos bimoneda.
    Garantiza que una sola moneda sea la fuente ingresada y la otra sea derivada.
    Retorna (costo_unitario_usd, costo_total_usd, costo_unitario_ars, costo_total_ars).
    """
    if cotizacion_usd_ars <= Decimal("0.0000"):
        raise ValueError("La cotización USD/ARS debe ser estrictamente mayor a 0.")
    if cantidad <= Decimal("0.0000"):
        raise ValueError("La cantidad debe ser mayor a 0.")

    if moneda_origen == MonedaEnum.USD:
        costo_unitario_usd = monto_unitario
        costo_total_usd = (costo_unitario_usd * cantidad).quantize(Decimal("0.0001"))
        costo_unitario_ars = (costo_unitario_usd * cotizacion_usd_ars).quantize(Decimal("0.0001"))
        costo_total_ars = (costo_total_usd * cotizacion_usd_ars).quantize(Decimal("0.0001"))
    else:  # ARS
        costo_unitario_ars = monto_unitario
        costo_total_ars = (costo_unitario_ars * cantidad).quantize(Decimal("0.0001"))
        costo_unitario_usd = (costo_unitario_ars / cotizacion_usd_ars).quantize(Decimal("0.0001"))
        costo_total_usd = (costo_total_ars / cotizacion_usd_ars).quantize(Decimal("0.0001"))

    return costo_unitario_usd, costo_total_usd, costo_unitario_ars, costo_total_ars


async def get_or_create_insumo_lote(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    numero_lote: str,
    fecha_vencimiento: Optional[date] = None,
    proveedor_origen: Optional[str] = None,
    registro_senasa: Optional[str] = None,
    cultivo: Optional[str] = None,
    hibrido_variedad: Optional[str] = None,
    tratamiento_semilla: Optional[str] = None,
    poder_germinativo_pct: Optional[Decimal] = None,
    peso_mil_granos_gr: Optional[Decimal] = None,
) -> InsumoLote:
    """Obtiene o crea un lote específico validando la propiedad por tenant."""
    numero_lote_clean = numero_lote.strip()
    res = await db.execute(
        select(InsumoLote).where(
            InsumoLote.cliente_id == cliente_id,
            InsumoLote.insumo_id == insumo_id,
            InsumoLote.numero_lote == numero_lote_clean,
        )
    )
    lote = res.scalar_one_or_none()
    if lote:
        return lote

    lote = InsumoLote(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        numero_lote=numero_lote_clean,
        fecha_vencimiento=fecha_vencimiento,
        proveedor_origen=proveedor_origen.strip() if proveedor_origen else None,
        registro_senasa=registro_senasa.strip() if registro_senasa else None,
        cultivo=cultivo.strip() if cultivo else None,
        hibrido_variedad=hibrido_variedad.strip() if hibrido_variedad else None,
        tratamiento_semilla=tratamiento_semilla.strip() if tratamiento_semilla else None,
        poder_germinativo_pct=poder_germinativo_pct,
        peso_mil_granos_gr=peso_mil_granos_gr,
        activo=True,
    )
    db.add(lote)
    await db.flush()
    return lote


async def actualizar_saldo_y_ppp(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    insumo_lote_id: Optional[uuid.UUID],
    delta_cantidad: Decimal,
    costo_total_ingreso_usd: Decimal = Decimal("0.0000"),
    costo_total_ingreso_ars: Decimal = Decimal("0.0000"),
    es_ingreso_compra: bool = False,
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Actualiza el saldo global + PPP en InsumoSaldoUbicacion
    y el saldo por lote en InsumoLoteSaldoUbicacion.
    Retorna (nueva_cantidad_total, nuevo_ppp_usd, nuevo_ppp_ars).
    """
    # 1. Saldo Global e Imputación PPP en la Ubicación (Pessimistic Lock with_for_update)
    res_s = await db.execute(
        select(InsumoSaldoUbicacion)
        .where(
            InsumoSaldoUbicacion.cliente_id == cliente_id,
            InsumoSaldoUbicacion.insumo_id == insumo_id,
            InsumoSaldoUbicacion.storage_location_id == storage_location_id,
        )
        .with_for_update()
    )
    saldo_global = res_s.scalar_one_or_none()

    if not saldo_global:
        if delta_cantidad < Decimal("0.0000"):
            raise ValueError("No se puede realizar un consumo o salida de una ubicación sin stock previo.")
        saldo_global = InsumoSaldoUbicacion(
            id=uuid.uuid4(),
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            storage_location_id=storage_location_id,
            cantidad_disponible=Decimal("0.0000"),
            costo_ppp_usd=Decimal("0.0000"),
            costo_ppp_ars=Decimal("0.0000"),
        )
        db.add(saldo_global)
        await db.flush()

    cant_anterior = saldo_global.cantidad_disponible
    cant_nueva = cant_anterior + delta_cantidad
    if cant_nueva < Decimal("0.0000"):
        raise ValueError(f"Stock insuficiente en ubicación. Disponible: {cant_anterior}, Solicitado: {abs(delta_cantidad)}.")

    # Actualizar PPP si es ingreso de compra
    if es_ingreso_compra and delta_cantidad > Decimal("0.0000"):
        val_anterior_usd = cant_anterior * saldo_global.costo_ppp_usd
        val_anterior_ars = cant_anterior * saldo_global.costo_ppp_ars

        val_total_usd = val_anterior_usd + costo_total_ingreso_usd
        val_total_ars = val_anterior_ars + costo_total_ingreso_ars

        if cant_nueva > Decimal("0.0000"):
            saldo_global.costo_ppp_usd = (val_total_usd / cant_nueva).quantize(Decimal("0.0001"))
            saldo_global.costo_ppp_ars = (val_total_ars / cant_nueva).quantize(Decimal("0.0001"))

    saldo_global.cantidad_disponible = cant_nueva

    # 2. Saldo Físico Específico por Lote (si aplica, with_for_update)
    if insumo_lote_id:
        res_l = await db.execute(
            select(InsumoLoteSaldoUbicacion)
            .where(
                InsumoLoteSaldoUbicacion.cliente_id == cliente_id,
                InsumoLoteSaldoUbicacion.insumo_id == insumo_id,
                InsumoLoteSaldoUbicacion.insumo_lote_id == insumo_lote_id,
                InsumoLoteSaldoUbicacion.storage_location_id == storage_location_id,
            )
            .with_for_update()
        )
        saldo_lote = res_l.scalar_one_or_none()
        if not saldo_lote:
            if delta_cantidad < Decimal("0.0000"):
                raise ValueError("No existe saldo registrado para este lote específico en la ubicación.")
            saldo_lote = InsumoLoteSaldoUbicacion(
                id=uuid.uuid4(),
                cliente_id=cliente_id,
                insumo_id=insumo_id,
                insumo_lote_id=insumo_lote_id,
                storage_location_id=storage_location_id,
                cantidad_disponible=Decimal("0.0000"),
            )
            db.add(saldo_lote)
            await db.flush()

        cant_lote_nueva = saldo_lote.cantidad_disponible + delta_cantidad
        if cant_lote_nueva < Decimal("0.0000"):
            raise ValueError(f"Stock insuficiente en lote específico. Disponible: {saldo_lote.cantidad_disponible}, Solicitado: {abs(delta_cantidad)}.")
        saldo_lote.cantidad_disponible = cant_lote_nueva

    return cant_nueva, saldo_global.costo_ppp_usd, saldo_global.costo_ppp_ars


async def registrar_stock_inicial(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    cantidad: Decimal,
    costo_unitario_usd: Optional[Decimal] = None,
    cotizacion_usd_ars: Decimal = Decimal("1000.00"),
    numero_lote: Optional[str] = None,
    fecha_vencimiento: Optional[date] = None,
    observaciones: Optional[str] = None,
    clave_idempotencia: Optional[str] = None,
    usuario_rol: str = "administracion",
) -> InsumoMovimiento:
    """
    Registra una carga de stock inicial física sin generar egreso financiero ni TransaccionFinanciera.
    Permite establecer existencias de arranque de forma limpia, directa y trazable.
    """
    validar_permisos_insumos(usuario_rol, "registrar_compra")

    if cantidad <= Decimal("0.0000"):
        raise ValueError("La cantidad de stock inicial debe ser estrictamente mayor a 0.")

    insumo = await db.get(Insumo, insumo_id)
    if not insumo or insumo.cliente_id != cliente_id or not insumo.activo:
        raise ValueError("El insumo especificado no existe, está inactivo o no pertenece al cliente.")

    location = await db.get(StorageLocation, storage_location_id)
    if not location or location.cliente_id != cliente_id:
        raise ValueError("La ubicación especificada no existe o no pertenece al cliente.")

    # Idempotencia
    if clave_idempotencia:
        res_idemp = await db.execute(
            select(InsumoMovimiento).where(
                InsumoMovimiento.cliente_id == cliente_id,
                InsumoMovimiento.tipo_movimiento == TipoMovimientoInsumoEnum.AJUSTE_RECUENTO_POSITIVO,
                InsumoMovimiento.clave_idempotencia == clave_idempotencia,
            )
        )
        mov_exist = res_idemp.scalars().first()
        if mov_exist:
            return mov_exist

    # Lote opcional
    lote_obj = None
    if numero_lote and numero_lote.strip():
        lote_obj = await get_or_create_insumo_lote(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            numero_lote=numero_lote.strip(),
            fecha_vencimiento=fecha_vencimiento,
        )

    unit_usd = costo_unitario_usd or Decimal("0.0000")
    _, total_usd, unit_ars, total_ars = calcular_valores_bimoneda(
        monto_unitario=unit_usd if unit_usd > Decimal("0.0000") else Decimal("1.0000"),
        cantidad=cantidad,
        moneda_origen=MonedaEnum.USD,
        cotizacion_usd_ars=cotizacion_usd_ars,
    )
    if unit_usd == Decimal("0.0000"):
        unit_usd = total_usd = unit_ars = total_ars = Decimal("0.0000")

    await actualizar_saldo_y_ppp(
        db=db,
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        storage_location_id=storage_location_id,
        insumo_lote_id=lote_obj.id if lote_obj else None,
        delta_cantidad=cantidad,
        costo_total_ingreso_usd=total_usd,
        costo_total_ingreso_ars=total_ars,
        es_ingreso_compra=True,
    )

    # Registrar movimiento inmutable (SIN TransaccionFinanciera)
    mov = InsumoMovimiento(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        insumo_lote_id=lote_obj.id if lote_obj else None,
        ubicacion_destino_id=storage_location_id,
        tipo_movimiento=TipoMovimientoInsumoEnum.AJUSTE_RECUENTO_POSITIVO,
        fecha_movimiento=datetime.now(),
        cantidad=cantidad,
        costo_unitario_usd=unit_usd,
        costo_total_usd=total_usd,
        costo_unitario_ars=unit_ars,
        costo_total_ars=total_ars,
        cotizacion_usd_ars=cotizacion_usd_ars,
        observaciones=observaciones or "Carga inicial de existencias",
        clave_idempotencia=clave_idempotencia,
    )
    db.add(mov)
    await db.commit()
    await db.refresh(mov)
    return mov


async def registrar_compra_ingreso(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    proveedor_nombre: str,
    fecha_compra: date,
    cantidad: Decimal,
    monto_unitario: Decimal,
    moneda_origen: MonedaEnum,
    cotizacion_usd_ars: Decimal,
    numero_lote: Optional[str] = None,
    fecha_vencimiento: Optional[date] = None,
    proveedor_cuit: Optional[str] = None,
    numero_factura_remito: Optional[str] = None,
    clave_idempotencia: Optional[str] = None,
    registrado_por_usuario_id: Optional[uuid.UUID] = None,
    observaciones: Optional[str] = None,
) -> InsumoMovimiento:
    """
    Registra la compra e ingreso de insumo.
    - Aplica idempotencia compuesta (cliente_id, COMPRA_INGRESO, clave_idempotencia).
    - Actualiza saldo global y recalcula PPP.
    - Genera exactamente UNA TransaccionFinanciera (EGRESO).
    """
    if not clave_idempotencia or not clave_idempotencia.strip():
        raise ValueError("La clave de idempotencia es obligatoria para mutaciones HTTP de compra.")

    clave_clean = clave_idempotencia.strip()

    # Verificar si ya existe el movimiento por idempotencia
    res_idem = await db.execute(
        select(InsumoMovimiento).where(
            InsumoMovimiento.cliente_id == cliente_id,
            InsumoMovimiento.tipo_movimiento == TipoMovimientoInsumoEnum.COMPRA_INGRESO,
            InsumoMovimiento.clave_idempotencia == clave_clean,
        )
    )
    mov_previo = res_idem.scalar_one_or_none()
    if mov_previo:
        return mov_previo

    # Validar tenant de entidades
    insumo = await db.get(Insumo, insumo_id)
    if not insumo or insumo.cliente_id != cliente_id:
        raise ValueError("El insumo especificado no existe o no pertenece al cliente.")

    location = await db.get(StorageLocation, storage_location_id)
    if not location or location.cliente_id != cliente_id:
        raise ValueError("La ubicación de almacenamiento no pertenece al cliente.")

    # Bimoneda
    c_unit_usd, c_tot_usd, c_unit_ars, c_tot_ars = calcular_valores_bimoneda(
        monto_unitario=monto_unitario,
        cantidad=cantidad,
        moneda_origen=moneda_origen,
        cotizacion_usd_ars=cotizacion_usd_ars,
    )

    # Lote opcional
    lote_obj = None
    if numero_lote and numero_lote.strip():
        lote_obj = await get_or_create_insumo_lote(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            numero_lote=numero_lote,
            fecha_vencimiento=fecha_vencimiento,
            proveedor_origen=proveedor_nombre,
        )

    # 1. Crear TransaccionFinanciera EGRESO (Única)
    tx_financiera = TransaccionFinanciera(
        id=uuid.uuid4(),
        tipo=TipoTransaccion.EGRESO,
        monto_usd=c_tot_usd,
        monto_ars=c_tot_ars,
        cotizacion_dolar=cotizacion_usd_ars.quantize(Decimal("0.01")),
        concepto=f"Compra Insumo: {insumo.nombre} ({cantidad} {insumo.unidad_medida.value}) - Factura {numero_factura_remito or 'S/D'}",
        pagado=True,
    )
    db.add(tx_financiera)
    await db.flush()

    # 2. Encabezado InsumoCompra
    compra = InsumoCompra(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        transaccion_financiera_id=tx_financiera.id,
        proveedor_nombre=proveedor_nombre.strip(),
        proveedor_cuit=proveedor_cuit.strip() if proveedor_cuit else None,
        numero_factura_remito=numero_factura_remito.strip() if numero_factura_remito else None,
        fecha_compra=fecha_compra,
        moneda=moneda_origen,
        monto_total=c_tot_usd if moneda_origen == MonedaEnum.USD else c_tot_ars,
        cotizacion_dolar=cotizacion_usd_ars,
        observaciones=observaciones,
        registrado_por_usuario_id=registrado_por_usuario_id,
    )
    db.add(compra)
    await db.flush()

    # 3. Actualizar Saldo y Recalcular PPP
    await actualizar_saldo_y_ppp(
        db=db,
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        storage_location_id=storage_location_id,
        insumo_lote_id=lote_obj.id if lote_obj else None,
        delta_cantidad=cantidad,
        costo_total_ingreso_usd=c_tot_usd,
        costo_total_ingreso_ars=c_tot_ars,
        es_ingreso_compra=True,
    )

    # 4. InsumoMovimiento KARDEX
    movimiento = InsumoMovimiento(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        insumo_lote_id=lote_obj.id if lote_obj else None,
        tipo_movimiento=TipoMovimientoInsumoEnum.COMPRA_INGRESO,
        fecha_movimiento=datetime.combine(fecha_compra, datetime.min.time()),
        ubicacion_destino_id=storage_location_id,
        cantidad=cantidad,
        moneda_origen=moneda_origen,
        cotizacion_usd_ars=cotizacion_usd_ars,
        costo_unitario_usd=c_unit_usd,
        costo_total_usd=c_tot_usd,
        costo_unitario_ars=c_unit_ars,
        costo_total_ars=c_tot_ars,
        transaccion_financiera_id=tx_financiera.id,
        clave_idempotencia=clave_clean,
        observaciones=observaciones,
        registrado_por_usuario_id=registrado_por_usuario_id,
    )
    db.add(movimiento)

    await db.commit()
    await db.refresh(movimiento)
    return movimiento


async def registrar_consumo_labor(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    labor_campo_id: uuid.UUID,
    cantidad_real: Decimal,
    fecha_consumo: datetime,
    insumo_lote_id: Optional[uuid.UUID] = None,
    insumos_aportados_por: str = "propio",
    autorizacion_vencido: bool = False,
    motivo_vencido: Optional[str] = None,
    clave_idempotencia: Optional[str] = None,
    registrado_por_usuario_id: Optional[uuid.UUID] = None,
    observaciones: Optional[str] = None,
) -> Optional[InsumoMovimiento]:
    """
    Registra el consumo real al finalizar una labor de campo.
    - Insumos aportados por cliente ('cliente') NO descuentan stock ni imputan costos.
    - Insumos propios/mixtos descuentan stock e imputan costo PPP.
    - Rechaza lotes vencidos a menos que exista autorizacion_vencido=True y motivo.
    - NO genera TransaccionFinanciera (evita duplicación de egreso).
    """
    if insumos_aportados_por == "cliente":
        return None

    if not clave_idempotencia or not clave_idempotencia.strip():
        raise ValueError("La clave de idempotencia es obligatoria para mutaciones HTTP de consumo.")

    clave_clean = clave_idempotencia.strip()

    # Validar vencimiento del lote si aplica
    if insumo_lote_id:
        lote_obj_check = await db.get(InsumoLote, insumo_lote_id)
        if lote_obj_check and lote_obj_check.fecha_vencimiento and lote_obj_check.fecha_vencimiento < date.today():
            if not autorizacion_vencido or not motivo_vencido or not motivo_vencido.strip():
                raise ValueError("El lote de insumo se encuentra vencido. Se requiere autorización explícita y motivo explicativo para su consumo.")

    # Idempotencia
    res_idem = await db.execute(
        select(InsumoMovimiento).where(
            InsumoMovimiento.cliente_id == cliente_id,
            InsumoMovimiento.tipo_movimiento == TipoMovimientoInsumoEnum.CONSUMO_LABOR,
            InsumoMovimiento.clave_idempotencia == clave_clean,
        )
    )
    mov_previo = res_idem.scalar_one_or_none()
    if mov_previo:
        return mov_previo

    labor = await db.get(LaborCampo, labor_campo_id)
    if not labor:
        raise ValueError("La labor de campo especificada no existe.")
    lote_obj = await db.get(Lote, labor.lote_id)
    if not lote_obj or lote_obj.cliente_id != cliente_id:
        raise ValueError("La labor de campo especificada no pertenece al cliente.")

    # Descontar stock y obtener PPP actual
    cant_nueva, ppp_usd, ppp_ars = await actualizar_saldo_y_ppp(
        db=db,
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        storage_location_id=storage_location_id,
        insumo_lote_id=insumo_lote_id,
        delta_cantidad=-cantidad_real,
        es_ingreso_compra=False,
    )

    c_unit_usd = ppp_usd
    c_tot_usd = (c_unit_usd * cantidad_real).quantize(Decimal("0.0001"))
    c_unit_ars = ppp_ars
    c_tot_ars = (c_unit_ars * cantidad_real).quantize(Decimal("0.0001"))

    movimiento = InsumoMovimiento(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        insumo_lote_id=insumo_lote_id,
        tipo_movimiento=TipoMovimientoInsumoEnum.CONSUMO_LABOR,
        fecha_movimiento=fecha_consumo,
        ubicacion_origen_id=storage_location_id,
        cantidad=cantidad_real,
        moneda_origen=MonedaEnum.USD,
        cotizacion_usd_ars=Decimal("1.0000") if ppp_usd == Decimal("0") else (ppp_ars / ppp_usd).quantize(Decimal("0.0001")),
        costo_unitario_usd=c_unit_usd,
        costo_total_usd=c_tot_usd,
        costo_unitario_ars=c_unit_ars,
        costo_total_ars=c_tot_ars,
        labor_campo_id=labor_campo_id,
        lote_id=labor.lote_id,
        clave_idempotencia=clave_clean,
        observaciones=observaciones,
        registrado_por_usuario_id=registrado_por_usuario_id,
    )
    db.add(movimiento)

    await db.commit()
    await db.refresh(movimiento)
    return movimiento


async def registrar_consumo_servicio_prestado(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    servicio_prestado_id: uuid.UUID,
    insumos_aportados_por: str,
    fecha_consumo: datetime,
    cantidad_real_total: Decimal,
    cantidad_real_propia: Optional[Decimal] = None,
    insumo_lote_id: Optional[uuid.UUID] = None,
    autorizacion_vencido: bool = False,
    motivo_vencido: Optional[str] = None,
    clave_idempotencia: Optional[str] = None,
    registrado_por_usuario_id: Optional[uuid.UUID] = None,
    observaciones: Optional[str] = None,
) -> Optional[InsumoMovimiento]:
    """
    Registra el consumo de insumo en un servicio prestado a tercero (Trabajo a terceros).
    - CLIENTE: 0 movimientos físicos propios y 0 costo imputado.
    - PROPIO: Descuenta la totalidad de cantidad_real_total de stock propio e imputa costo PPP.
    - MIXTO: Exige cantidad_real_propia explícita > 0. Descuenta sólo el componente propio.
    - NO genera TransaccionFinanciera (evita duplicar egresos).
    """
    if insumos_aportados_por == "cliente":
        return None

    if insumos_aportados_por == "mixto":
        if not cantidad_real_propia or cantidad_real_propia <= Decimal("0.0000"):
            raise ValueError("Para insumos aportados en modalidad MIXTA, se exige indicar la cantidad real del componente propio.")
        cant_a_descontar = cantidad_real_propia
    else:
        cant_a_descontar = cantidad_real_total

    if not clave_idempotencia or not clave_idempotencia.strip():
        raise ValueError("La clave de idempotencia es obligatoria para mutaciones HTTP de consumo.")

    clave_clean = clave_idempotencia.strip()

    # Validar vencimiento del lote si aplica
    if insumo_lote_id:
        lote_obj_check = await db.get(InsumoLote, insumo_lote_id)
        if lote_obj_check and lote_obj_check.fecha_vencimiento and lote_obj_check.fecha_vencimiento < date.today():
            if not autorizacion_vencido or not motivo_vencido or not motivo_vencido.strip():
                raise ValueError("El lote de insumo se encuentra vencido. Se requiere autorización explícita y motivo explicativo para su consumo.")

    res_idem = await db.execute(
        select(InsumoMovimiento).where(
            InsumoMovimiento.cliente_id == cliente_id,
            InsumoMovimiento.tipo_movimiento == TipoMovimientoInsumoEnum.CONSUMO_SERVICIO_TERCERO,
            InsumoMovimiento.clave_idempotencia == clave_clean,
        )
    )
    mov_previo = res_idem.scalar_one_or_none()
    if mov_previo:
        return mov_previo

    servicio = await db.get(ServicioPrestado, servicio_prestado_id)
    if not servicio or servicio.cliente_id != cliente_id:
        raise ValueError("El servicio prestado especificado no pertenece al cliente.")

    # Descontar stock propio
    cant_nueva, ppp_usd, ppp_ars = await actualizar_saldo_y_ppp(
        db=db,
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        storage_location_id=storage_location_id,
        insumo_lote_id=insumo_lote_id,
        delta_cantidad=-cant_a_descontar,
        es_ingreso_compra=False,
    )

    c_unit_usd = ppp_usd
    c_tot_usd = (c_unit_usd * cant_a_descontar).quantize(Decimal("0.0001"))
    c_unit_ars = ppp_ars
    c_tot_ars = (c_unit_ars * cant_a_descontar).quantize(Decimal("0.0001"))

    movimiento = InsumoMovimiento(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        insumo_lote_id=insumo_lote_id,
        tipo_movimiento=TipoMovimientoInsumoEnum.CONSUMO_SERVICIO_TERCERO,
        fecha_movimiento=fecha_consumo,
        ubicacion_origen_id=storage_location_id,
        cantidad=cant_a_descontar,
        moneda_origen=MonedaEnum.USD,
        costo_unitario_usd=c_unit_usd,
        costo_total_usd=c_tot_usd,
        costo_unitario_ars=c_unit_ars,
        costo_total_ars=c_tot_ars,
        servicio_prestado_id=servicio_prestado_id,
        clave_idempotencia=clave_clean,
        observaciones=observaciones,
        registrado_por_usuario_id=registrado_por_usuario_id,
    )
    db.add(movimiento)

    # Imputar costo al servicio prestado (deduciendo de su margen) sin crear TransaccionFinanciera
    servicio.gastos_directos_informados = (servicio.gastos_directos_informados + c_tot_ars).quantize(Decimal("0.01"))

    await db.commit()
    await db.refresh(movimiento)
    return movimiento


async def registrar_transferencia_ubicaciones(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    ubicacion_origen_id: uuid.UUID,
    ubicacion_destino_id: uuid.UUID,
    cantidad: Decimal,
    fecha_transferencia: datetime,
    insumo_lote_id: Optional[uuid.UUID] = None,
    clave_idempotencia: Optional[str] = None,
    registrado_por_usuario_id: Optional[uuid.UUID] = None,
    observaciones: Optional[str] = None,
) -> Tuple[InsumoMovimiento, InsumoMovimiento]:
    """
    Ejecuta una transferencia atómica de insumos entre dos ubicaciones.
    - Salida de origen + Entrada a destino vinculadas por grupo_transferencia_id.
    - Origen y destino obligatorios, distintos y del mismo tenant.
    - Cero impacto financiero.
    """
    if ubicacion_origen_id == ubicacion_destino_id:
        raise ValueError("Las ubicaciones de origen y destino deben ser distintas.")

    if not clave_idempotencia or not clave_idempotencia.strip():
        raise ValueError("La clave de idempotencia es obligatoria para mutaciones HTTP de transferencia.")

    clave_clean = clave_idempotencia.strip()

    # Adquirir bloqueos de filas en orden de UUID consistente para evitar deadlocks en concurrencia
    first_loc, second_loc = sorted([ubicacion_origen_id, ubicacion_destino_id], key=lambda u: str(u))
    for loc_id in [first_loc, second_loc]:
        await db.execute(
            select(InsumoSaldoUbicacion)
            .where(
                InsumoSaldoUbicacion.cliente_id == cliente_id,
                InsumoSaldoUbicacion.insumo_id == insumo_id,
                InsumoSaldoUbicacion.storage_location_id == loc_id,
            )
            .with_for_update()
        )

    grupo_transferencia_id = uuid.uuid4()

    # 1. Salida de Origen
    _, ppp_usd, ppp_ars = await actualizar_saldo_y_ppp(
        db=db,
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        storage_location_id=ubicacion_origen_id,
        insumo_lote_id=insumo_lote_id,
        delta_cantidad=-cantidad,
        es_ingreso_compra=False,
    )

    c_unit_usd = ppp_usd
    c_tot_usd = (c_unit_usd * cantidad).quantize(Decimal("0.0001"))
    c_unit_ars = ppp_ars
    c_tot_ars = (c_unit_ars * cantidad).quantize(Decimal("0.0001"))

    mov_salida = InsumoMovimiento(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        insumo_lote_id=insumo_lote_id,
        tipo_movimiento=TipoMovimientoInsumoEnum.TRANSFERENCIA_SALIDA,
        fecha_movimiento=fecha_transferencia,
        ubicacion_origen_id=ubicacion_origen_id,
        ubicacion_destino_id=ubicacion_destino_id,
        cantidad=cantidad,
        moneda_origen=MonedaEnum.USD,
        costo_unitario_usd=c_unit_usd,
        costo_total_usd=c_tot_usd,
        costo_unitario_ars=c_unit_ars,
        costo_total_ars=c_tot_ars,
        grupo_transferencia_id=grupo_transferencia_id,
        clave_idempotencia=f"{clave_clean}_salida",
        observaciones=observaciones,
        registrado_por_usuario_id=registrado_por_usuario_id,
    )
    db.add(mov_salida)

    # 2. Entrada a Destino (mantiene el costo PPP transferido)
    await actualizar_saldo_y_ppp(
        db=db,
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        storage_location_id=ubicacion_destino_id,
        insumo_lote_id=insumo_lote_id,
        delta_cantidad=cantidad,
        costo_total_ingreso_usd=c_tot_usd,
        costo_total_ingreso_ars=c_tot_ars,
        es_ingreso_compra=True,
    )

    mov_entrada = InsumoMovimiento(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        insumo_lote_id=insumo_lote_id,
        tipo_movimiento=TipoMovimientoInsumoEnum.TRANSFERENCIA_ENTRADA,
        fecha_movimiento=fecha_transferencia,
        ubicacion_origen_id=ubicacion_origen_id,
        ubicacion_destino_id=ubicacion_destino_id,
        cantidad=cantidad,
        moneda_origen=MonedaEnum.USD,
        costo_unitario_usd=c_unit_usd,
        costo_total_usd=c_tot_usd,
        costo_unitario_ars=c_unit_ars,
        costo_total_ars=c_tot_ars,
        grupo_transferencia_id=grupo_transferencia_id,
        clave_idempotencia=f"{clave_clean}_entrada",
        observaciones=observaciones,
        registrado_por_usuario_id=registrado_por_usuario_id,
    )
    db.add(mov_entrada)

    await db.commit()
    await db.refresh(mov_salida)
    await db.refresh(mov_entrada)
    return mov_salida, mov_entrada


async def registrar_recuento_inventario(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    storage_location_id: uuid.UUID,
    cantidad_fisica: Decimal,
    fecha_recuento: datetime,
    motivo_ajuste: str,
    insumo_lote_id: Optional[uuid.UUID] = None,
    usuario_contador_id: Optional[uuid.UUID] = None,
    usuario_aprobador_id: Optional[uuid.UUID] = None,
    clave_idempotencia: Optional[str] = None,
) -> Tuple[InsumoRecuento, Optional[InsumoMovimiento]]:
    """
    Registra el recuento físico de inventario.
    - Si hay diferencia, exige motivo explicativo obligatorio (especialmente en ajustes negativos).
    - Crea el ajuste correspondiente en InsumoMovimiento (AJUSTE_RECUENTO_POSITIVO o AJUSTE_RECUENTO_NEGATIVO).
    """
    if not motivo_ajuste or not motivo_ajuste.strip():
        raise ValueError("El motivo del ajuste es obligatorio para registrar un recuento de inventario.")

    if not clave_idempotencia or not clave_idempotencia.strip():
        raise ValueError("La clave de idempotencia es obligatoria para registrar un recuento.")

    clave_clean = clave_idempotencia.strip()

    # Saldo actual en sistema
    res_s = await db.execute(
        select(InsumoSaldoUbicacion).where(
            InsumoSaldoUbicacion.cliente_id == cliente_id,
            InsumoSaldoUbicacion.insumo_id == insumo_id,
            InsumoSaldoUbicacion.storage_location_id == storage_location_id,
        )
    )
    saldo_global = res_s.scalar_one_or_none()
    cant_sistema = saldo_global.cantidad_disponible if saldo_global else Decimal("0.0000")
    diferencia = cantidad_fisica - cant_sistema

    recuento = InsumoRecuento(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        insumo_lote_id=insumo_lote_id,
        storage_location_id=storage_location_id,
        fecha_recuento=fecha_recuento,
        cantidad_sistema=cant_sistema,
        cantidad_fisica=cantidad_fisica,
        diferencia=diferencia,
        motivo_ajuste=motivo_ajuste.strip(),
        usuario_contador_id=usuario_contador_id,
        usuario_aprobador_id=usuario_aprobador_id,
    )
    db.add(recuento)

    mov_ajuste = None
    if diferencia != Decimal("0.0000"):
        tipo_mov = (
            TipoMovimientoInsumoEnum.AJUSTE_RECUENTO_POSITIVO
            if diferencia > Decimal("0.0000")
            else TipoMovimientoInsumoEnum.AJUSTE_RECUENTO_NEGATIVO
        )

        _, ppp_usd, ppp_ars = await actualizar_saldo_y_ppp(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            storage_location_id=storage_location_id,
            insumo_lote_id=insumo_lote_id,
            delta_cantidad=diferencia,
            es_ingreso_compra=False,
        )

        c_unit_usd = ppp_usd
        c_tot_usd = (c_unit_usd * abs(diferencia)).quantize(Decimal("0.0001"))
        c_unit_ars = ppp_ars
        c_tot_ars = (c_unit_ars * abs(diferencia)).quantize(Decimal("0.0001"))

        mov_ajuste = InsumoMovimiento(
            id=uuid.uuid4(),
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            insumo_lote_id=insumo_lote_id,
            tipo_movimiento=tipo_mov,
            fecha_movimiento=fecha_recuento,
            ubicacion_origen_id=storage_location_id if diferencia < 0 else None,
            ubicacion_destino_id=storage_location_id if diferencia > 0 else None,
            cantidad=abs(diferencia),
            moneda_origen=MonedaEnum.USD,
            costo_unitario_usd=c_unit_usd,
            costo_total_usd=c_tot_usd,
            costo_unitario_ars=c_unit_ars,
            costo_total_ars=c_tot_ars,
            clave_idempotencia=clave_clean,
            observaciones=f"Ajuste por recuento físico: {motivo_ajuste.strip()}",
            registrado_por_usuario_id=usuario_contador_id,
        )
        db.add(mov_ajuste)
        await db.flush()
        recuento.movimiento_ajuste_id = mov_ajuste.id

    recuento.estado_recuento = "aprobado"
    await db.commit()
    await db.refresh(recuento)
    if mov_ajuste:
        await db.refresh(mov_ajuste)

    return recuento, mov_ajuste


async def aprobar_recuento_fisico(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    recuento_id: uuid.UUID,
    usuario_aprobador_id: uuid.UUID,
    usuario_rol: str = "administracion",
) -> InsumoRecuento:
    """
    Aprueba un recuento en estado pendiente con bloqueo transaccional.
    Restringido a roles de administración o finanzas.
    """
    validar_permisos_insumos(usuario_rol, "aprobar_recuento")

    res = await db.execute(
        select(InsumoRecuento)
        .where(InsumoRecuento.id == recuento_id, InsumoRecuento.cliente_id == cliente_id)
        .with_for_update()
    )
    recuento = res.scalar_one_or_none()
    if not recuento:
        raise ValueError("El recuento especificado no existe o no pertenece al cliente.")

    if recuento.estado_recuento == "aprobado":
        raise ValueError("El recuento físico ya ha sido aprobado previamente y no puede re-aplicarse.")
    if recuento.estado_recuento == "rechazado":
        raise ValueError("El recuento físico se encuentra rechazado y no puede ser aprobado.")

    recuento.estado_recuento = "aprobado"
    recuento.usuario_aprobador_id = usuario_aprobador_id
    await db.commit()
    await db.refresh(recuento)
    return recuento


async def rechazar_recuento_fisico(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    recuento_id: uuid.UUID,
    usuario_aprobador_id: uuid.UUID,
    usuario_rol: str = "administracion",
) -> InsumoRecuento:
    """
    Rechaza un recuento en estado pendiente sin alterar stock ni generar movimientos de ajuste.
    Restringido a roles de administración o finanzas.
    """
    validar_permisos_insumos(usuario_rol, "aprobar_recuento")

    res = await db.execute(
        select(InsumoRecuento)
        .where(InsumoRecuento.id == recuento_id, InsumoRecuento.cliente_id == cliente_id)
        .with_for_update()
    )
    recuento = res.scalar_one_or_none()
    if not recuento:
        raise ValueError("El recuento especificado no existe o no pertenece al cliente.")

    if recuento.estado_recuento in ["aprobado", "rechazado"]:
        raise ValueError(f"El recuento físico ya se encuentra en estado '{recuento.estado_recuento}'.")

    recuento.estado_recuento = "rechazado"
    recuento.usuario_aprobador_id = usuario_aprobador_id
    await db.commit()
    await db.refresh(recuento)
    return recuento


async def crear_reserva_insumo(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    cantidad_reservada: Decimal,
    fecha_reserva: datetime,
    storage_location_id: Optional[uuid.UUID] = None,
    insumo_lote_id: Optional[uuid.UUID] = None,
    labor_campo_id: Optional[uuid.UUID] = None,
    servicio_prestado_id: Optional[uuid.UUID] = None,
    fecha_expiracion: Optional[date] = None,
    observaciones: Optional[str] = None,
    registrado_por_usuario_id: Optional[uuid.UUID] = None,
) -> InsumoReserva:
    """
    Crea una reserva opcional de insumos sin descontar stock físico.
    Exige vinculo único con labor_campo O servicio_prestado (nunca ambos ni ninguno).
    Verifica que el stock neto (disponible - reservado no vencido) sea suficiente.
    """
    if cantidad_reservada <= Decimal("0.0000"):
        raise ValueError("La cantidad a reservar debe ser estrictamente mayor a 0.")

    # 1. Regla de Destino Único
    has_labor = labor_campo_id is not None
    has_servicio = servicio_prestado_id is not None
    if (has_labor and has_servicio) or (not has_labor and not has_servicio):
        raise ValueError("Una reserva activa debe estar vinculada a una labor de campo o a un servicio prestado, pero nunca a ambos ni a ninguno.")

    # 2. Validar pertenencia por Tenant
    insumo = await db.get(Insumo, insumo_id)
    if not insumo or insumo.cliente_id != cliente_id:
        raise ValueError("El insumo no pertenece al cliente.")

    if storage_location_id:
        loc = await db.get(StorageLocation, storage_location_id)
        if not loc or loc.cliente_id != cliente_id:
            raise ValueError("La ubicación especificada no pertenece al cliente.")

    if insumo_lote_id:
        lote_i = await db.get(InsumoLote, insumo_lote_id)
        if not lote_i or lote_i.cliente_id != cliente_id:
            raise ValueError("El lote de insumo no pertenece al cliente.")

    if labor_campo_id:
        labor = await db.get(LaborCampo, labor_campo_id)
        if not labor:
            raise ValueError("La labor de campo especificada no existe.")
        lote_c = await db.get(Lote, labor.lote_id)
        if not lote_c or lote_c.cliente_id != cliente_id:
            raise ValueError("La labor de campo especificada no pertenece al cliente.")

    if servicio_prestado_id:
        serv = await db.get(ServicioPrestado, servicio_prestado_id)
        if not serv or serv.cliente_id != cliente_id:
            raise ValueError("El servicio prestado especificado no pertenece al cliente.")

    # 3. Bloqueo Psimista de filas individuales y Cálculo de Stock Disponible vs Reservado
    res_stock_rows = await db.execute(
        select(InsumoSaldoUbicacion)
        .where(
            InsumoSaldoUbicacion.cliente_id == cliente_id,
            InsumoSaldoUbicacion.insumo_id == insumo_id,
        )
        .with_for_update()
    )
    saldos_rows = res_stock_rows.scalars().all()
    stock_fisico = sum((s.cantidad_disponible for s in saldos_rows), Decimal("0.0000"))

    # Reservas activas NO vencidas
    from sqlalchemy import or_
    res_res_rows = await db.execute(
        select(InsumoReserva)
        .where(
            InsumoReserva.cliente_id == cliente_id,
            InsumoReserva.insumo_id == insumo_id,
            InsumoReserva.estado_reserva == "activa",
            or_(InsumoReserva.fecha_expiracion.is_(None), InsumoReserva.fecha_expiracion >= date.today()),
        )
        .with_for_update()
    )
    reservas_rows = res_res_rows.scalars().all()
    reservado_activo = sum((r.cantidad_reservada for r in reservas_rows), Decimal("0.0000"))

    stock_neto_disponible = stock_fisico - reservado_activo
    if stock_neto_disponible < cantidad_reservada:
        raise ValueError(f"Stock neto disponible insuficiente para reservar. Físico: {stock_fisico}, Reservado Activo: {reservado_activo}, Solicitado: {cantidad_reservada}.")

    reserva = InsumoReserva(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        insumo_id=insumo_id,
        storage_location_id=storage_location_id,
        insumo_lote_id=insumo_lote_id,
        labor_campo_id=labor_campo_id,
        servicio_prestado_id=servicio_prestado_id,
        cantidad_reservada=cantidad_reservada,
        estado_reserva="activa",
        fecha_reserva=fecha_reserva,
        fecha_expiracion=fecha_expiracion,
        observaciones=observaciones,
        registrado_por_usuario_id=registrado_por_usuario_id,
    )
    db.add(reserva)
    await db.commit()
    await db.refresh(reserva)
    return reserva


async def consumir_reserva_insumo(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    reserva_id: uuid.UUID,
    cantidad_real: Decimal,
    autorizacion_exceso: bool = False,
    motivo_exceso: Optional[str] = None,
) -> InsumoReserva:
    """
    Transiciona una reserva activa al estado 'consumida'.
    Si la cantidad real excede la reservada, requiere autorizacion_exceso=True y motivo explicativo.
    """
    res = await db.execute(
        select(InsumoReserva)
        .where(InsumoReserva.id == reserva_id, InsumoReserva.cliente_id == cliente_id)
        .with_for_update()
    )
    reserva = res.scalar_one_or_none()
    if not reserva:
        raise ValueError("La reserva especificada no existe o no pertenece al cliente.")

    if reserva.estado_reserva != "activa":
        raise ValueError(f"La reserva ya se encuentra en estado terminal '{reserva.estado_reserva}' y no se puede consumir.")

    if cantidad_real > reserva.cantidad_reservada:
        if not autorizacion_exceso or not motivo_exceso or not motivo_exceso.strip():
            raise ValueError(f"El consumo real ({cantidad_real}) excede la cantidad reservada ({reserva.cantidad_reservada}). Se exige autorización explicativa.")

    reserva.estado_reserva = "consumida"
    await db.commit()
    await db.refresh(reserva)
    return reserva


async def liberar_reserva_insumo(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    reserva_id: uuid.UUID,
    motivo: str = "liberada",
) -> InsumoReserva:
    """Libera o cancela una reserva activa de insumos."""
    res = await db.execute(
        select(InsumoReserva).where(InsumoReserva.id == reserva_id, InsumoReserva.cliente_id == cliente_id).with_for_update()
    )
    reserva = res.scalar_one_or_none()
    if not reserva:
        raise ValueError("La reserva especificada no existe o no pertenece al cliente.")

    if reserva.estado_reserva != "activa":
        raise ValueError(f"La reserva ya se encuentra en estado terminal '{reserva.estado_reserva}' y no se puede liberar ni cancelar nuevamente.")

    reserva.estado_reserva = motivo.lower() if motivo.lower() in ["liberada", "cancelada"] else "liberada"
    await db.commit()
    await db.refresh(reserva)
    return reserva


async def cancelar_reservas_asociadas(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    labor_campo_id: Optional[uuid.UUID] = None,
    servicio_prestado_id: Optional[uuid.UUID] = None,
) -> int:
    """
    Cancela automáticamente todas las reservas activas asociadas a una labor o servicio cancelado.
    Evita que queden reservas huérfanas bloqueando el saldo neto.
    """
    query = select(InsumoReserva).where(
        InsumoReserva.cliente_id == cliente_id,
        InsumoReserva.estado_reserva == "activa",
    )
    if labor_campo_id:
        query = query.where(InsumoReserva.labor_campo_id == labor_campo_id)
    elif servicio_prestado_id:
        query = query.where(InsumoReserva.servicio_prestado_id == servicio_prestado_id)
    else:
        return 0

    res = await db.execute(query.with_for_update())
    reservas = res.scalars().all()
    for r in reservas:
        r.estado_reserva = "cancelada"

    await db.commit()
    return len(reservas)


async def limpiar_reservas_vencidas(
    db: AsyncSession,
    cliente_id: uuid.UUID,
) -> int:
    """Acción administrativa para marcar reservas activas con fecha_expiracion < hoy como 'vencidas'."""
    res = await db.execute(
        select(InsumoReserva).where(
            InsumoReserva.cliente_id == cliente_id,
            InsumoReserva.estado_reserva == "activa",
            InsumoReserva.fecha_expiracion < date.today(),
        ).with_for_update()
    )
    reservas = res.scalars().all()
    for r in reservas:
        r.estado_reserva = "vencida"

    await db.commit()
    return len(reservas)


async def verificar_disponibilidad_insumos(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    insumo_id: uuid.UUID,
    superficie_ha: Decimal,
    dosis_por_ha: Decimal,
    storage_location_id: Optional[uuid.UUID] = None,
) -> Dict[str, any]:
    """
    Evalúa si existe disponibilidad física y neta (descontando reservas activas) de insumo.
    Retorna un diccionario de diagnóstico con estados:
    - DISPONIBLE
    - DISPONIBLE_OTRA_UBICACION
    - STOCK_INSUFICIENTE
    """
    demandada = (superficie_ha * dosis_por_ha).quantize(Decimal("0.0001"))

    # 1. Stock físico en la ubicación elegida
    cant_loc = Decimal("0.0000")
    if storage_location_id:
        res_l = await db.execute(
            select(InsumoSaldoUbicacion.cantidad_disponible).where(
                InsumoSaldoUbicacion.cliente_id == cliente_id,
                InsumoSaldoUbicacion.insumo_id == insumo_id,
                InsumoSaldoUbicacion.storage_location_id == storage_location_id,
            )
        )
        val = res_l.scalar_one_or_none()
        if val:
            cant_loc = val

    # 2. Stock físico total acumulado
    res_t = await db.execute(
        select(func.coalesce(func.sum(InsumoSaldoUbicacion.cantidad_disponible), Decimal("0.0000"))).where(
            InsumoSaldoUbicacion.cliente_id == cliente_id,
            InsumoSaldoUbicacion.insumo_id == insumo_id,
        )
    )
    cant_total = res_t.scalar_one()

    # 3. Reservas activas NO vencidas
    from sqlalchemy import or_
    res_r = await db.execute(
        select(func.coalesce(func.sum(InsumoReserva.cantidad_reservada), Decimal("0.0000"))).where(
            InsumoReserva.cliente_id == cliente_id,
            InsumoReserva.insumo_id == insumo_id,
            InsumoReserva.estado_reserva == "activa",
            or_(InsumoReserva.fecha_expiracion.is_(None), InsumoReserva.fecha_expiracion >= date.today()),
        )
    )
    cant_reservada = res_r.scalar_one()
    cant_neto_total = max(Decimal("0.0000"), cant_total - cant_reservada)

    if storage_location_id and cant_loc >= demandada:
        estado = "DISPONIBLE"
    elif cant_neto_total >= demandada:
        estado = "DISPONIBLE_OTRA_UBICACION"
    else:
        estado = "STOCK_INSUFICIENTE"

    faltante = max(Decimal("0.0000"), demandada - cant_neto_total)

    return {
        "estado": estado,
        "cantidad_demandada": float(demandada),
        "cantidad_disponible_ubicacion": float(cant_loc),
        "cantidad_disponible_total": float(cant_total),
        "cantidad_reservada_total": float(cant_reservada),
        "cantidad_neto_disponible": float(cant_neto_total),
        "cantidad_faltante": float(faltante),
    }
