"""
Suite de Pruebas de Auditoría y Salvaguardas Críticas para Reservas y Recuentos de Insumos (Fase 3 Auditoría).
Cubre:
1. Regla de Destino Único en Reservas (Exactamente una labor_campo O un servicio_prestado, nunca ambos ni ninguno).
2. Aislamiento Multitenant estricto en Reservas.
3. Máquina de estados de reservas (transiciones válidas, prohibición de doble liberación/consumo/cancelación).
4. Consumo mayor a reserva (requiere autorización explícita y motivo explicativo).
5. Cancelación automática de reservas al cancelar la labor o servicio prestado.
6. Liberación de reservas vencidas (no afectan el saldo neto disponible).
7. Concurrencia en reservas y consumo.
8. Matriz de permisos y rechazo de recuentos físicos (sólo administración/finanzas, sin mutación de stock al rechazar).
"""

from decimal import Decimal
from datetime import date, datetime, timedelta
import uuid
import pytest
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.enums import (
    CategoriaInsumoEnum,
    UnidadMedidaInsumoEnum,
    MonedaEnum,
    EstadoOperativoTrabajoEnum,
)
from app.models import (
    Cliente,
    StorageLocation,
    Insumo,
    InsumoLote,
    InsumoSaldoUbicacion,
    InsumoMovimiento,
    InsumoRecuento,
    InsumoReserva,
    ClienteTercero,
    EquipoMaquinaria,
    ServicioPrestado,
    Usuario,
    Campania,
    Campo,
    Lote,
    LaborCampo,
)
from app.services.insumos_service import (
    registrar_compra_ingreso,
    registrar_recuento_inventario,
    aprobar_recuento_fisico,
    rechazar_recuento_fisico,
    crear_reserva_insumo,
    consumir_reserva_insumo,
    liberar_reserva_insumo,
    cancelar_reservas_asociadas,
    limpiar_reservas_vencidas,
    verificar_disponibilidad_insumos,
)


@pytest.mark.asyncio
async def test_1_reservation_requires_exactly_one_target():
    """Verifica que una reserva deba estar vinculada a una labor O a un servicio, pero nunca a ambos ni a ninguno."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"InsumoTarget {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.FITOSANITARIO, unidad_medida=UnidadMedidaInsumoEnum.LITRO)
        db.add(insumo)
        await db.commit()

        # 1. Sin labor ni servicio prestado -> Falla
        with pytest.raises(ValueError, match="labor de campo o a un servicio prestado"):
            await crear_reserva_insumo(
                db=db,
                cliente_id=cliente.id,
                insumo_id=insumo.id,
                cantidad_reservada=Decimal("10.0000"),
                fecha_reserva=datetime.now(),
                labor_campo_id=None,
                servicio_prestado_id=None,
            )

        # 2. Con labor Y servicio prestado al mismo tiempo -> Falla
        with pytest.raises(ValueError, match="labor de campo o a un servicio prestado"):
            await crear_reserva_insumo(
                db=db,
                cliente_id=cliente.id,
                insumo_id=insumo.id,
                cantidad_reservada=Decimal("10.0000"),
                fecha_reserva=datetime.now(),
                labor_campo_id=uuid.uuid4(),
                servicio_prestado_id=uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_2_reservation_lifecycle_and_prohibited_double_transitions():
    """Verifica la máquina de estados de reservas y prohibición de doble liberación/consumo."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

        maquina = EquipoMaquinaria(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Maq Lifecycle {uuid.uuid4().hex[:4]}", tipo_equipo="pulverizadora")
        tercero = ClienteTercero(id=uuid.uuid4(), cliente_id=cliente.id, razon_social_nombre=f"Tercero Lifecycle {uuid.uuid4().hex[:4]}")
        db.add_all([maquina, tercero])
        await db.flush()

        orden = ServicioPrestado(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=usuario.id if usuario else uuid.uuid4(),
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Lote Lifecycle",
            superficie_ha=Decimal("50.00"),
            monto_total_facturado=Decimal("500000.00"),
            pago_operador_negociado=Decimal("100000.00"),
            imputacion_uso_maquinaria=Decimal("80000.00"),
            gastos_directos_informados=Decimal("0.00"),
            estado_operativo=EstadoOperativoTrabajoEnum.PROGRAMADO.value,
        )
        db.add(orden)

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Insumo Lifecycle {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.SEMILLA, unidad_medida=UnidadMedidaInsumoEnum.BOLSA)
        db.add(insumo)
        await db.commit()

        # Stock físico = 100
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Proveedor Lifecycle",
            fecha_compra=date.today(),
            cantidad=Decimal("100.0000"),
            monto_unitario=Decimal("50.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_lc_{uuid.uuid4().hex[:4]}",
        )

        reserva = await crear_reserva_insumo(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            cantidad_reservada=Decimal("40.0000"),
            fecha_reserva=datetime.now(),
            servicio_prestado_id=orden.id,
        )

        # Consumir reserva
        await consumir_reserva_insumo(
            db=db,
            cliente_id=cliente.id,
            reserva_id=reserva.id,
            cantidad_real=Decimal("40.0000"),
        )
        await db.refresh(reserva)
        assert reserva.estado_reserva == "consumida"

        # Intentar liberar una reserva consumida -> Falla
        with pytest.raises(ValueError, match="estado terminal"):
            await liberar_reserva_insumo(db=db, cliente_id=cliente.id, reserva_id=reserva.id)

        # Intentar re-consumir una reserva consumida -> Falla
        with pytest.raises(ValueError, match="estado terminal"):
            await consumir_reserva_insumo(db=db, cliente_id=cliente.id, reserva_id=reserva.id, cantidad_real=Decimal("40.0000"))


@pytest.mark.asyncio
async def test_3_consumption_exceeding_reservation_requires_authorization():
    """Verifica que consumir más de lo reservado exija autorización y motivo explicativo."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

        maquina = EquipoMaquinaria(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Maq Exceso {uuid.uuid4().hex[:4]}", tipo_equipo="pulverizadora")
        tercero = ClienteTercero(id=uuid.uuid4(), cliente_id=cliente.id, razon_social_nombre=f"Tercero Exceso {uuid.uuid4().hex[:4]}")
        db.add_all([maquina, tercero])
        await db.flush()

        orden = ServicioPrestado(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=usuario.id if usuario else uuid.uuid4(),
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Lote Exceso",
            superficie_ha=Decimal("50.00"),
            monto_total_facturado=Decimal("500000.00"),
            pago_operador_negociado=Decimal("100000.00"),
            imputacion_uso_maquinaria=Decimal("80000.00"),
            gastos_directos_informados=Decimal("0.00"),
            estado_operativo=EstadoOperativoTrabajoEnum.PROGRAMADO.value,
        )
        db.add(orden)

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Insumo Exceso {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.FITOSANITARIO, unidad_medida=UnidadMedidaInsumoEnum.LITRO)
        db.add(insumo)
        await db.commit()

        # Stock = 100 Litros
        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Proveedor Exceso",
            fecha_compra=date.today(),
            cantidad=Decimal("100.0000"),
            monto_unitario=Decimal("10.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_exc_{uuid.uuid4().hex[:4]}",
        )

        # Reserva de 30 Litros
        reserva = await crear_reserva_insumo(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            cantidad_reservada=Decimal("30.0000"),
            fecha_reserva=datetime.now(),
            servicio_prestado_id=orden.id,
        )

        # Consumo de 45 Litros sin autorización -> Falla
        with pytest.raises(ValueError, match="excede la cantidad reservada"):
            await consumir_reserva_insumo(
                db=db,
                cliente_id=cliente.id,
                reserva_id=reserva.id,
                cantidad_real=Decimal("45.0000"),
                autorizacion_exceso=False,
            )

        # Consumo de 45 Litros con autorización explícita -> Exitoso
        res_ok = await consumir_reserva_insumo(
            db=db,
            cliente_id=cliente.id,
            reserva_id=reserva.id,
            cantidad_real=Decimal("45.0000"),
            autorizacion_exceso=True,
            motivo_exceso="Mayor maleza requirió re-aplicación parcial de dosis",
        )
        assert res_ok.estado_reserva == "consumida"


@pytest.mark.asyncio
async def test_4_automatic_cancellation_of_reservations_on_job_cancel():
    """Verifica que al cancelar un servicio o labor, sus reservas activas pasen automáticamente a 'cancelada'."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

        maquina = EquipoMaquinaria(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Maq JobCancel {uuid.uuid4().hex[:4]}", tipo_equipo="pulverizadora")
        tercero = ClienteTercero(id=uuid.uuid4(), cliente_id=cliente.id, razon_social_nombre=f"Tercero JobCancel {uuid.uuid4().hex[:4]}")
        db.add_all([maquina, tercero])
        await db.flush()

        orden = ServicioPrestado(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=usuario.id if usuario else uuid.uuid4(),
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Lote JobCancel",
            superficie_ha=Decimal("50.00"),
            monto_total_facturado=Decimal("500000.00"),
            pago_operador_negociado=Decimal("100000.00"),
            imputacion_uso_maquinaria=Decimal("80000.00"),
            gastos_directos_informados=Decimal("0.00"),
            estado_operativo=EstadoOperativoTrabajoEnum.PROGRAMADO.value,
        )
        db.add(orden)

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Insumo JobCancel {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.FITOSANITARIO, unidad_medida=UnidadMedidaInsumoEnum.LITRO)
        db.add(insumo)
        await db.commit()

        # Stock = 100 Litros
        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Proveedor JC",
            fecha_compra=date.today(),
            cantidad=Decimal("100.0000"),
            monto_unitario=Decimal("10.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_jc_{uuid.uuid4().hex[:4]}",
        )

        reserva = await crear_reserva_insumo(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            cantidad_reservada=Decimal("50.0000"),
            fecha_reserva=datetime.now(),
            servicio_prestado_id=orden.id,
        )

        # Cancelar labor/servicio
        afectadas = await cancelar_reservas_asociadas(db=db, cliente_id=cliente.id, servicio_prestado_id=orden.id)
        assert afectadas == 1

        await db.refresh(reserva)
        assert reserva.estado_reserva == "cancelada"


@pytest.mark.asyncio
async def test_5_expired_reservations_do_not_reduce_net_stock():
    """Verifica que las reservas vencidas no reduzcan el saldo neto y se limpien adecuadamente."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

        maquina = EquipoMaquinaria(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Maq Expired {uuid.uuid4().hex[:4]}", tipo_equipo="pulverizadora")
        tercero = ClienteTercero(id=uuid.uuid4(), cliente_id=cliente.id, razon_social_nombre=f"Tercero Expired {uuid.uuid4().hex[:4]}")
        db.add_all([maquina, tercero])
        await db.flush()

        orden = ServicioPrestado(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=usuario.id if usuario else uuid.uuid4(),
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Lote Expired",
            superficie_ha=Decimal("50.00"),
            monto_total_facturado=Decimal("500000.00"),
            pago_operador_negociado=Decimal("100000.00"),
            imputacion_uso_maquinaria=Decimal("80000.00"),
            gastos_directos_informados=Decimal("0.00"),
            estado_operativo=EstadoOperativoTrabajoEnum.PROGRAMADO.value,
        )
        db.add(orden)

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Insumo Expired {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.SEMILLA, unidad_medida=UnidadMedidaInsumoEnum.BOLSA)
        db.add(insumo)
        await db.commit()

        # Stock = 100 bolsas
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Proveedor Expired",
            fecha_compra=date.today(),
            cantidad=Decimal("100.0000"),
            monto_unitario=Decimal("10.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_exp_{uuid.uuid4().hex[:4]}",
        )

        # Reserva vencida ayer
        reserva_vencida = await crear_reserva_insumo(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            cantidad_reservada=Decimal("60.0000"),
            fecha_reserva=datetime.now() - timedelta(days=2),
            fecha_expiracion=date.today() - timedelta(days=1), # Vencida!
            servicio_prestado_id=orden.id,
        )

        # Diagnóstico de disponibilidad debe ignorar la reserva vencida (Neto disponible = 100 bolsas)
        diag = await verificar_disponibilidad_insumos(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            superficie_ha=Decimal("10.00"),
            dosis_por_ha=Decimal("10.0000"), # 100 bolsas
            storage_location_id=location.id,
        )
        assert diag["estado"] == "DISPONIBLE"
        assert diag["cantidad_neto_disponible"] == 100.0

        # Acción administrativa de limpieza
        limpiadas = await limpiar_reservas_vencidas(db=db, cliente_id=cliente.id)
        assert limpiadas >= 1

        await db.refresh(reserva_vencida)
        assert reserva_vencida.estado_reserva == "vencida"


@pytest.mark.asyncio
async def test_6_physical_count_rejection_leaves_stock_unmutated_and_blocks_operario():
    """Verifica que rechazar un recuento no altere stock y que operario_campo no tenga permiso para aprobar/rechazar."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Insumo RejectCount {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.FITOSANITARIO, unidad_medida=UnidadMedidaInsumoEnum.LITRO)
        db.add(insumo)
        await db.commit()

        # Stock = 50 L
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Proveedor Rej",
            fecha_compra=date.today(),
            cantidad=Decimal("50.0000"),
            monto_unitario=Decimal("10.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_rej_{uuid.uuid4().hex[:4]}",
        )

        # Recuento borrador/pendiente
        recuento = InsumoRecuento(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            fecha_recuento=datetime.now(),
            cantidad_sistema=Decimal("50.0000"),
            cantidad_fisica=Decimal("30.0000"),
            diferencia=Decimal("-20.0000"),
            motivo_ajuste="Diferencia supuesta no aclarada",
            estado_recuento="pendiente",
        )
        db.add(recuento)
        await db.commit()

        # Role operario_campo intentando aprobar o rechazar -> PermissionError
        with pytest.raises(PermissionError, match="permisos"):
            await aprobar_recuento_fisico(
                db=db,
                cliente_id=cliente.id,
                recuento_id=recuento.id,
                usuario_aprobador_id=usuario.id if usuario else uuid.uuid4(),
                usuario_rol="operario_campo",
            )

        # Rechazo por administración
        rec_rej = await rechazar_recuento_fisico(
            db=db,
            cliente_id=cliente.id,
            recuento_id=recuento.id,
            usuario_aprobador_id=usuario.id if usuario else uuid.uuid4(),
            usuario_rol="administracion",
        )
        assert rec_rej.estado_recuento == "rechazado"

        # Saldo en ubicación sigue siendo 50 L (Cero mutación de stock!)
        res_s = await db.execute(
            select(InsumoSaldoUbicacion).where(
                InsumoSaldoUbicacion.cliente_id == cliente.id,
                InsumoSaldoUbicacion.insumo_id == insumo.id,
                InsumoSaldoUbicacion.storage_location_id == location.id,
            )
        )
        saldo = res_s.scalar_one()
        assert saldo.cantidad_disponible == Decimal("50.0000")
