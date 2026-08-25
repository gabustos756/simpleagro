"""
Suite de Pruebas para la Fase 3 del Módulo de Insumos y Abastecimiento (EduAgro V3).
Cubre:
1. Verificación de referencias cruzadas multitenant entre entidades del sistema.
2. Protección contra doble aprobación/aplicación de recuentos físicos.
3. Rechazo de cotizaciones USD/ARS <= 0.
4. Operación atómica de imputación a ServicioPrestado sin doble contabilización ante reintentos.
5. Cálculo de demanda, reservas de insumos sin descuento físico de stock y diagnóstico neto de disponibilidad.
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
    registrar_consumo_servicio_prestado,
    registrar_recuento_inventario,
    aprobar_recuento_fisico,
    crear_reserva_insumo,
    liberar_reserva_insumo,
    verificar_disponibilidad_insumos,
)


@pytest.mark.asyncio
async def test_1_cross_tenant_foreign_keys_rejected():
    """Verifica que mezclar entidades de distintos clientes en compras/consumos sea rechazado."""
    async with AsyncSessionLocal() as db:
        # Obtener 2 clientes distintos o crear uno secundario si sólo hay 1
        res_c = await db.execute(select(Cliente))
        clientes = res_c.scalars().all()
        cliente1 = clientes[0]
        if len(clientes) > 1:
            cliente2 = clientes[1]
        else:
            cliente2 = Cliente(id=uuid.uuid4(), nombre_razon_social="Cliente Secundario Test", cuit="30999999999")
            db.add(cliente2)
            await db.flush()

        # Insumo de Cliente 1 y Ubicación de Cliente 2
        insumo_c1 = Insumo(id=uuid.uuid4(), cliente_id=cliente1.id, nombre=f"CrossTenant {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.SEMILLA, unidad_medida=UnidadMedidaInsumoEnum.BOLSA)
        loc_c2 = StorageLocation(id=uuid.uuid4(), cliente_id=cliente2.id, nombre=f"Galpón C2 {uuid.uuid4().hex[:4]}", tipo="galpon")
        db.add_all([insumo_c1, loc_c2])
        await db.commit()

        # Compra cruzada debe fallar
        with pytest.raises(ValueError, match="no pertenece"):
            await registrar_compra_ingreso(
                db=db,
                cliente_id=cliente1.id,
                insumo_id=insumo_c1.id,
                storage_location_id=loc_c2.id, # Ubicación de C2!
                proveedor_nombre="Proveedor Cross",
                fecha_compra=date.today(),
                cantidad=Decimal("10.0000"),
                monto_unitario=Decimal("100.0000"),
                moneda_origen=MonedaEnum.USD,
                cotizacion_usd_ars=Decimal("1000.0000"),
                clave_idempotencia=f"idem_cross_{uuid.uuid4().hex[:4]}",
            )


@pytest.mark.asyncio
async def test_2_recuento_fisico_double_approval_protection():
    """Verifica que un recuento físico no pueda ser re-aprobado ni aplicado dos veces."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Semilla DoubleApprove {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.SEMILLA, unidad_medida=UnidadMedidaInsumoEnum.BOLSA)
        db.add(insumo)
        await db.commit()

        # Registrar recuento en 1 sola paso (estado 'aprobado')
        recuento, mov = await registrar_recuento_inventario(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            cantidad_fisica=Decimal("10.0000"),
            fecha_recuento=datetime.now(),
            motivo_ajuste="Inventario inicial auditado",
            usuario_contador_id=usuario.id if usuario else None,
            clave_idempotencia=f"rec_init_{uuid.uuid4().hex[:4]}",
        )

        assert recuento.estado_recuento == "aprobado"
        assert recuento.movimiento_ajuste_id == mov.id

        # Intentar re-aprobar el mismo recuento debe lanzar ValueError
        with pytest.raises(ValueError, match="aprobado previamente"):
            await aprobar_recuento_fisico(
                db=db,
                cliente_id=cliente.id,
                recuento_id=recuento.id,
                usuario_aprobador_id=usuario.id if usuario else uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_3_invalid_cotizacion_usd_ars_rejected():
    """Verifica que cotización USD/ARS <= 0 sea rechazada en bimoneda."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Gasoil ZeroCot {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.COMBUSTIBLE, unidad_medida=UnidadMedidaInsumoEnum.LITRO)
        db.add(insumo)
        await db.commit()

        with pytest.raises(ValueError, match="mayor a 0"):
            await registrar_compra_ingreso(
                db=db,
                cliente_id=cliente.id,
                insumo_id=insumo.id,
                storage_location_id=location.id,
                proveedor_nombre="YPF",
                fecha_compra=date.today(),
                cantidad=Decimal("100.0000"),
                monto_unitario=Decimal("1.0000"),
                moneda_origen=MonedaEnum.USD,
                cotizacion_usd_ars=Decimal("0.0000"), # Inválida!
                clave_idempotencia=f"compra_zerocot_{uuid.uuid4().hex[:4]}",
            )


@pytest.mark.asyncio
async def test_4_servicio_prestado_idempotent_retry_no_double_margin_impact():
    """Verifica que reintentar consumo en ServicioPrestado no duplique la imputación a gastos_directos_informados."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_u.scalars().first()

        maquina = EquipoMaquinaria(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Pulverizadora F3 {uuid.uuid4().hex[:4]}", tipo_equipo="pulverizadora")
        tercero = ClienteTercero(id=uuid.uuid4(), cliente_id=cliente.id, razon_social_nombre=f"Tercero F3 {uuid.uuid4().hex[:4]}")
        db.add_all([maquina, tercero])
        await db.flush()

        orden = ServicioPrestado(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=operador.id,
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Lote F3 Test",
            superficie_ha=Decimal("100.00"),
            monto_total_facturado=Decimal("1000000.00"),
            pago_operador_negociado=Decimal("200000.00"),
            imputacion_uso_maquinaria=Decimal("150000.00"),
            gastos_directos_informados=Decimal("0.00"),
            estado_operativo=EstadoOperativoTrabajoEnum.PROGRAMADO.value,
        )
        db.add(orden)

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Herbicida Idem {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.FITOSANITARIO, unidad_medida=UnidadMedidaInsumoEnum.LITRO)
        db.add(insumo)
        await db.commit()

        # Ingresar 100 L a 10 USD/L (Cotización 1000 ARS -> 10,000 ARS/L)
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Agro Insumos",
            fecha_compra=date.today(),
            cantidad=Decimal("100.0000"),
            monto_unitario=Decimal("10.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_idem_s_{uuid.uuid4().hex[:4]}",
        )

        clave_idem = f"cons_service_retry_{uuid.uuid4().hex[:6]}"

        # Consumo 1: 20 L = 200,000 ARS
        mov1 = await registrar_consumo_servicio_prestado(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            servicio_prestado_id=orden.id,
            insumos_aportados_por="propio",
            fecha_consumo=datetime.now(),
            cantidad_real_total=Decimal("20.0000"),
            clave_idempotencia=clave_idem,
        )
        await db.refresh(orden)
        assert orden.gastos_directos_informados == Decimal("200000.00")

        # Reintento con la MISMA clave de idempotencia
        mov2 = await registrar_consumo_servicio_prestado(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            servicio_prestado_id=orden.id,
            insumos_aportados_por="propio",
            fecha_consumo=datetime.now(),
            cantidad_real_total=Decimal("20.0000"),
            clave_idempotencia=clave_idem,
        )

        assert mov1.id == mov2.id
        await db.refresh(orden)
        # NO se duplicó la imputación a gastos! Sigue en 200,000 ARS
        assert orden.gastos_directos_informados == Decimal("200000.00")


@pytest.mark.asyncio
async def test_5_insumo_reservas_and_net_availability_diagnosis():
    """Verifica creación de reservas opcionales y diagnóstico de disponibilidad neta."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Fertilizante Reserva {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.FERTILIZANTE, unidad_medida=UnidadMedidaInsumoEnum.KG)
        db.add(insumo)
        await db.commit()

        # Cargar 1000 kg físicos
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Profertil",
            fecha_compra=date.today(),
            cantidad=Decimal("1000.0000"),
            monto_unitario=Decimal("0.8000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_fert_res_{uuid.uuid4().hex[:4]}",
        )

        # Labor de prueba para la reserva
        res_camp = await db.execute(select(Campania).limit(1))
        campania = res_camp.scalars().first()
        res_campo = await db.execute(select(Campo).where(Campo.cliente_id == cliente.id).limit(1))
        campo = res_campo.scalars().first()
        res_lote = await db.execute(select(Lote).where(Lote.cliente_id == cliente.id).limit(1))
        lote = res_lote.scalars().first()

        labor = LaborCampo(id=uuid.uuid4(), lote_id=lote.id, campania_id=campania.id, tipo_labor="fertilizacion", fecha=datetime.now())
        db.add(labor)
        await db.flush()

        # Crear Reserva de 600 kg (sin descontar físico)
        reserva = await crear_reserva_insumo(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            cantidad_reservada=Decimal("600.0000"),
            fecha_reserva=datetime.now(),
            storage_location_id=location.id,
            labor_campo_id=labor.id,
            observaciones="Reserva pre-siembra Maíz Lote 4",
        )

        assert reserva.estado_reserva == "activa"

        # Evaluar disponibilidad para demanda de 500 kg (Neto disponible = 1000 - 600 = 400 kg) -> Faltan 100 kg!
        diag = await verificar_disponibilidad_insumos(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            superficie_ha=Decimal("50.00"),
            dosis_por_ha=Decimal("10.0000"), # Demanda = 500 kg
            storage_location_id=location.id,
        )

        # Físico en ubicación = 1000, pero neto total disponible = 400 kg < 500 kg -> STOCK_INSUFICIENTE
        assert diag["cantidad_reservada_total"] == 600.0
        assert diag["cantidad_neto_disponible"] == 400.0
        assert diag["cantidad_faltante"] == 100.0

        # Liberar reserva
        await liberar_reserva_insumo(db=db, cliente_id=cliente.id, reserva_id=reserva.id, motivo="liberada")

        # Diagnóstico post liberación -> DISPONIBLE
        diag_post = await verificar_disponibilidad_insumos(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            superficie_ha=Decimal("50.00"),
            dosis_por_ha=Decimal("10.0000"),
            storage_location_id=location.id,
        )
        assert diag_post["estado"] == "DISPONIBLE"
        assert diag_post["cantidad_neto_disponible"] == 1000.0
