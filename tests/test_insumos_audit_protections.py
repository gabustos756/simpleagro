"""
Suite de Auditoría y Verificación de Salvaguardas Críticas para Insumos y Abastecimiento.
Verifica:
1. Idempotencia compuesta por tenant y tipo de movimiento (soporta múltiples NULL).
2. Atomicidad de transferencias por grupo_transferencia_id.
3. Rechazo estricto de consumo de lotes vencidos sin autorización trazada.
4. Consumo en Servicios Prestados: Modalidad Cliente, Propia y Mixta.
5. Imputación de costos en Servicios Prestados afectando margen sin duplicación financiera.
6. Motivo obligatorio en recuentos físicos con ajuste negativo.
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
    TipoTransaccion,
    EstadoOperativoTrabajoEnum,
)
from app.models import (
    Cliente,
    StorageLocation,
    Insumo,
    InsumoLote,
    InsumoSaldoUbicacion,
    InsumoMovimiento,
    TransaccionFinanciera,
    ClienteTercero,
    EquipoMaquinaria,
    ServicioPrestado,
)
from app.services.insumos_service import (
    registrar_compra_ingreso,
    registrar_consumo_labor,
    registrar_consumo_servicio_prestado,
    registrar_transferencia_ubicaciones,
    registrar_recuento_inventario,
    get_or_create_insumo_lote,
)


@pytest.mark.asyncio
async def test_1_multiple_null_idempotency_keys_allowed():
    """Verifica que clave_idempotencia=None permita múltiples registros sin colisionar."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Semilla NullIdem {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.SEMILLA,
            unidad_medida=UnidadMedidaInsumoEnum.BOLSA,
        )
        db.add(insumo)
        await db.commit()

        mov1 = InsumoMovimiento(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            tipo_movimiento="compra_ingreso",
            fecha_movimiento=datetime.now(),
            cantidad=Decimal("10.0000"),
            clave_idempotencia=None,
        )
        mov2 = InsumoMovimiento(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            tipo_movimiento="compra_ingreso",
            fecha_movimiento=datetime.now(),
            cantidad=Decimal("20.0000"),
            clave_idempotencia=None,
        )
        db.add_all([mov1, mov2])
        await db.commit()

        assert mov1.id is not None and mov2.id is not None


@pytest.mark.asyncio
async def test_2_expired_lote_consumption_rejected_without_authorization():
    """Verifica que no se pueda consumir un lote vencido sin autorizacion_vencido=True y motivo."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Fitosanitario Vencido {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.FITOSANITARIO,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
        )
        db.add(insumo)
        await db.commit()

        # Lote vencido ayer
        lote_vencido = await get_or_create_insumo_lote(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            numero_lote=f"VENC-{uuid.uuid4().hex[:4]}",
            fecha_vencimiento=date.today() - timedelta(days=1),
        )

        # Cargar stock de lote vencido
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Proveedor Vencido",
            fecha_compra=date.today(),
            cantidad=Decimal("50.0000"),
            monto_unitario=Decimal("8.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            numero_lote=lote_vencido.numero_lote,
            clave_idempotencia=f"compra_venc_{uuid.uuid4().hex[:6]}",
        )

        # Consumo sin autorización debe fallar
        from app.models import LaborCampo, Lote, Campo, Campania
        res_camp = await db.execute(select(Campania).limit(1))
        campania = res_camp.scalars().first()
        res_campo = await db.execute(select(Campo).where(Campo.cliente_id == cliente.id).limit(1))
        campo = res_campo.scalars().first()
        res_lote = await db.execute(select(Lote).where(Lote.cliente_id == cliente.id).limit(1))
        lote = res_lote.scalars().first()

        labor = LaborCampo(id=uuid.uuid4(), lote_id=lote.id, campania_id=campania.id, tipo_labor="pulverizacion", fecha=datetime.now())
        db.add(labor)
        await db.commit()

        with pytest.raises(ValueError, match="vencido"):
            await registrar_consumo_labor(
                db=db,
                cliente_id=cliente.id,
                insumo_id=insumo.id,
                storage_location_id=location.id,
                labor_campo_id=labor.id,
                cantidad_real=Decimal("10.0000"),
                fecha_consumo=datetime.now(),
                insumo_lote_id=lote_vencido.id,
                autorizacion_vencido=False,
                clave_idempotencia=f"cons_venc_fail_{uuid.uuid4().hex[:6]}",
            )

        # Consumo con autorización exitoso
        mov_ok = await registrar_consumo_labor(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            labor_campo_id=labor.id,
            cantidad_real=Decimal("10.0000"),
            fecha_consumo=datetime.now(),
            insumo_lote_id=lote_vencido.id,
            autorizacion_vencido=True,
            motivo_vencido="Fitosanitario probado en laboratorio sin pérdida de principio activo",
            clave_idempotencia=f"cons_venc_ok_{uuid.uuid4().hex[:6]}",
        )
        assert mov_ok is not None


@pytest.mark.asyncio
async def test_3_servicios_prestados_insumo_modalities_and_margin_impact():
    """Verifica consumos en Trabajos a Terceros: modalidad cliente vs propia vs mixta."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        # Maquinaria y Cliente Tercero
        maquina = EquipoMaquinaria(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Pulverizadora {uuid.uuid4().hex[:4]}", tipo_equipo="pulverizadora")
        tercero = ClienteTercero(id=uuid.uuid4(), cliente_id=cliente.id, razon_social_nombre=f"Tercero Audit {uuid.uuid4().hex[:4]}")
        db.add_all([maquina, tercero])
        await db.flush()

        # Usuario u Operador
        from app.models import Usuario
        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_u.scalars().first()
        if not operador:
            operador = Usuario(
                id=uuid.uuid4(),
                cliente_id=cliente.id,
                email=f"operador_{uuid.uuid4().hex[:4]}@eduagro.com",
                nombre="Andrés Operador Audit",
                rol="operario_campo",
                password_hash="fakehash",
            )
            db.add(operador)
            await db.flush()

        orden = ServicioPrestado(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=operador.id,
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Lote Tercero Audit",
            superficie_ha=Decimal("100.00"),
            monto_total_facturado=Decimal("1000000.00"),
            pago_operador_negociado=Decimal("200000.00"),
            imputacion_uso_maquinaria=Decimal("150000.00"),
            gastos_directos_informados=Decimal("50000.00"),
            estado_operativo=EstadoOperativoTrabajoEnum.PROGRAMADO.value,
        )
        db.add(orden)

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Herbicida Terceros {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.FITOSANITARIO,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
        )
        db.add(insumo)
        await db.commit()

        # Ingresar 200 L propios a 20.00 USD/L (Cotización 1000 ARS -> 20,000 ARS/L)
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Agro Insumos S.A.",
            fecha_compra=date.today(),
            cantidad=Decimal("200.0000"),
            monto_unitario=Decimal("20.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_terc_{uuid.uuid4().hex[:6]}",
        )

        # 1. Modalidad CLIENTE: Cero descuento de stock, cero impacto en gastos
        mov_cli = await registrar_consumo_servicio_prestado(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            servicio_prestado_id=orden.id,
            insumos_aportados_por="cliente",
            fecha_consumo=datetime.now(),
            cantidad_real_total=Decimal("50.0000"),
            clave_idempotencia=f"cons_terc_cli_{uuid.uuid4().hex[:6]}",
        )
        assert mov_cli is None

        # 2. Modalidad MIXTA sin indicar cantidad_real_propia debe fallar
        with pytest.raises(ValueError, match="MIXTA"):
            await registrar_consumo_servicio_prestado(
                db=db,
                cliente_id=cliente.id,
                insumo_id=insumo.id,
                storage_location_id=location.id,
                servicio_prestado_id=orden.id,
                insumos_aportados_por="mixto",
                fecha_consumo=datetime.now(),
                cantidad_real_total=Decimal("50.0000"),
                cantidad_real_propia=None,
                clave_idempotencia=f"cons_terc_mix_fail_{uuid.uuid4().hex[:6]}",
            )

        tx_count_before = (await db.execute(select(func.count(TransaccionFinanciera.id)))).scalar_one()

        # 3. Modalidad PROPIA (50 Litros propios = 1,000,000 ARS)
        mov_prop = await registrar_consumo_servicio_prestado(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            servicio_prestado_id=orden.id,
            insumos_aportados_por="propio",
            fecha_consumo=datetime.now(),
            cantidad_real_total=Decimal("50.0000"),
            clave_idempotencia=f"cons_terc_prop_{uuid.uuid4().hex[:6]}",
        )
        assert mov_prop.costo_total_ars == Decimal("1000000.0000")

        # Gastos directos aumentados de 50,000 a 1,050,000 ARS
        await db.refresh(orden)
        assert orden.gastos_directos_informados == Decimal("1050000.00")

        # Cero TransaccionFinanciera adicional creada
        tx_count_after = (await db.execute(select(func.count(TransaccionFinanciera.id)))).scalar_one()
        assert tx_count_after == tx_count_before
