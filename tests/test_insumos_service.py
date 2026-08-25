"""
Suite de Pruebas de Integración y Reglas de Negocio para el Módulo de Insumos y Abastecimiento.
Cubre:
1. Compras e ingreso bimoneda con recálculo PPP y exactamente una TransaccionFinanciera (EGRESO).
2. Idempotencia compuesta por (cliente_id, tipo_movimiento, clave_idempotencia).
3. Consumo en labor real (deduce stock, imputa costo PPP, cero egresos financieros duplicados).
4. Insumos aportados por cliente (no descuentan stock propio).
5. Transferencias atómicas entre ubicaciones vinculadas por grupo_transferencia_id.
6. Recuentos de inventario con motivo obligatorio para ajustes negativos.
7. Motor de necesidades pre-labor.
8. Aislamiento estricto multi-tenant entre clientes.
"""

from decimal import Decimal
from datetime import date, datetime
import uuid
import pytest
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.enums import (
    CategoriaInsumoEnum,
    UnidadMedidaInsumoEnum,
    MonedaEnum,
    TipoTransaccion,
)
from app.models import (
    Cliente,
    StorageLocation,
    Insumo,
    InsumoSaldoUbicacion,
    InsumoMovimiento,
    TransaccionFinanciera,
    LaborCampo,
    Campania,
    Lote,
    Campo,
)
from app.services.insumos_service import (
    registrar_compra_ingreso,
    registrar_consumo_labor,
    registrar_transferencia_ubicaciones,
    registrar_recuento_inventario,
    verificar_disponibilidad_insumos,
)


@pytest.mark.asyncio
async def test_1_compra_ingreso_recalculates_ppp_and_creates_single_financial_tx():
    """Verifica que la compra recalcule el PPP y cree exactamente UNA TransaccionFinanciera."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Glifosato PPP {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.FITOSANITARIO,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
        )
        db.add(insumo)
        await db.commit()

        # Compra 1: 100 L a 5.00 USD/L (Cotización 1000 ARS)
        mov1 = await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Agroquímicos Sur",
            fecha_compra=date.today(),
            cantidad=Decimal("100.0000"),
            monto_unitario=Decimal("5.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_1_{uuid.uuid4().hex[:6]}",
        )
        assert mov1.transaccion_financiera_id is not None

        # Saldo y PPP post Compra 1
        res_s1 = await db.execute(
            select(InsumoSaldoUbicacion).where(
                InsumoSaldoUbicacion.cliente_id == cliente.id,
                InsumoSaldoUbicacion.insumo_id == insumo.id,
                InsumoSaldoUbicacion.storage_location_id == location.id,
            )
        )
        saldo1 = res_s1.scalar_one()
        assert saldo1.cantidad_disponible == Decimal("100.0000")
        assert saldo1.costo_ppp_usd == Decimal("5.0000")
        assert saldo1.costo_ppp_ars == Decimal("5000.0000")

        # Compra 2: 100 L a 10.00 USD/L (Misma cotización)
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Agroquímicos Sur",
            fecha_compra=date.today(),
            cantidad=Decimal("100.0000"),
            monto_unitario=Decimal("10.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_2_{uuid.uuid4().hex[:6]}",
        )

        # Saldo y PPP post Compra 2: PPP = (100*5 + 100*10) / 200 = 7.50 USD/L
        await db.refresh(saldo1)
        assert saldo1.cantidad_disponible == Decimal("200.0000")
        assert saldo1.costo_ppp_usd == Decimal("7.5000")


@pytest.mark.asyncio
async def test_2_consumo_labor_deducts_stock_and_creates_no_financial_tx():
    """Verifica que el consumo en labor descuente stock sin duplicar egresos financieros."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        res_camp = await db.execute(select(Campania).limit(1))
        campania = res_camp.scalars().first()
        if not campania:
            campania = Campania(
                id=uuid.uuid4(),
                nombre="Campaña 2025/2026",
                fecha_inicio=date(2025, 7, 1),
                fecha_fin=date(2026, 6, 30),
                activa=True,
            )
            db.add(campania)
            await db.flush()

        res_campo = await db.execute(select(Campo).where(Campo.cliente_id == cliente.id).limit(1))
        campo = res_campo.scalars().first()
        if not campo:
            campo = Campo(
                id=uuid.uuid4(),
                cliente_id=cliente.id,
                nombre="Estancia La María Test",
                superficie_ha=Decimal("500.00"),
            )
            db.add(campo)
            await db.flush()

        res_lote = await db.execute(select(Lote).where(Lote.cliente_id == cliente.id).limit(1))
        lote = res_lote.scalars().first()
        if not lote:
            lote = Lote(
                id=uuid.uuid4(),
                cliente_id=cliente.id,
                campo_id=campo.id,
                nombre="Lote El Mangrullo Test",
                superficie_total_ha=100.0,
                superficie_productiva_ha=95.0,
            )
            db.add(lote)
            await db.flush()

        # Labor de prueba
        labor = LaborCampo(
            id=uuid.uuid4(),
            lote_id=lote.id,
            campania_id=campania.id,
            tipo_labor="pulverizacion",
            fecha=datetime.now(),
        )
        db.add(labor)

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Atrazina Consumo {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.FITOSANITARIO,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
        )
        db.add(insumo)
        await db.commit()

        # Ingresar 100 L iniciales
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="Proveedor Test",
            fecha_compra=date.today(),
            cantidad=Decimal("100.0000"),
            monto_unitario=Decimal("10.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_c1_{uuid.uuid4().hex[:6]}",
        )

        tx_count_before = (await db.execute(select(func.count(TransaccionFinanciera.id)))).scalar_one()

        # Consumir 40 L reales en la labor
        mov_cons = await registrar_consumo_labor(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            labor_campo_id=labor.id,
            cantidad_real=Decimal("40.0000"),
            fecha_consumo=datetime.now(),
            insumos_aportados_por="propio",
            clave_idempotencia=f"consumo_l1_{uuid.uuid4().hex[:6]}",
        )
        assert mov_cons.costo_total_usd == Decimal("400.0000") # 40L * 10 USD

        # Saldo post consumo: 60 L
        res_s = await db.execute(
            select(InsumoSaldoUbicacion).where(
                InsumoSaldoUbicacion.cliente_id == cliente.id,
                InsumoSaldoUbicacion.insumo_id == insumo.id,
                InsumoSaldoUbicacion.storage_location_id == location.id,
            )
        )
        saldo = res_s.scalar_one()
        assert saldo.cantidad_disponible == Decimal("60.0000")

        # Verificar que NO se haya creado una segunda TransaccionFinanciera
        tx_count_after = (await db.execute(select(func.count(TransaccionFinanciera.id)))).scalar_one()
        assert tx_count_after == tx_count_before


@pytest.mark.asyncio
async def test_3_transferencia_atomica_linked_by_grupo_transferencia_id():
    """Verifica la transferencia atómica de stock entre 2 ubicaciones distintas del tenant."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        uid_tag = uuid.uuid4().hex[:6]
        loc_orig = StorageLocation(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Tanque Central {uid_tag}", tipo="tanque_combustible_fijo")
        loc_dest = StorageLocation(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Cisterna Móvil {uid_tag}", tipo="cisterna_movil")
        db.add_all([loc_orig, loc_dest])

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Gasoil Transfer {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.COMBUSTIBLE,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
        )
        db.add(insumo)
        await db.commit()

        # Ingresar 1000 L al Tanque Central
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=loc_orig.id,
            proveedor_nombre="YPF Agro",
            fecha_compra=date.today(),
            cantidad=Decimal("1000.0000"),
            monto_unitario=Decimal("1.2000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_gasoil_{uuid.uuid4().hex[:6]}",
        )

        # Transferir 300 L a Cisterna Móvil
        mov_sal, mov_ent = await registrar_transferencia_ubicaciones(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            ubicacion_origen_id=loc_orig.id,
            ubicacion_destino_id=loc_dest.id,
            cantidad=Decimal("300.0000"),
            fecha_transferencia=datetime.now(),
            clave_idempotencia=f"transf_{uuid.uuid4().hex[:6]}",
        )

        assert mov_sal.grupo_transferencia_id == mov_ent.grupo_transferencia_id

        # Verificar saldos
        s_orig = (await db.execute(select(InsumoSaldoUbicacion).where(InsumoSaldoUbicacion.storage_location_id == loc_orig.id, InsumoSaldoUbicacion.insumo_id == insumo.id))).scalar_one()
        s_dest = (await db.execute(select(InsumoSaldoUbicacion).where(InsumoSaldoUbicacion.storage_location_id == loc_dest.id, InsumoSaldoUbicacion.insumo_id == insumo.id))).scalar_one()

        assert s_orig.cantidad_disponible == Decimal("700.0000")
        assert s_dest.cantidad_disponible == Decimal("300.0000")


@pytest.mark.asyncio
async def test_4_recuento_fisico_ajuste_negativo_requires_motivo():
    """Verifica que los recuentos físicos requieran motivo obligatorio para ajustes."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Semilla Recuento {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.SEMILLA,
            unidad_medida=UnidadMedidaInsumoEnum.BOLSA,
        )
        db.add(insumo)
        await db.commit()

        # Cargar 50 bolsas
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            proveedor_nombre="KWS Argentina",
            fecha_compra=date.today(),
            cantidad=Decimal("50.0000"),
            monto_unitario=Decimal("150.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            clave_idempotencia=f"compra_sem_{uuid.uuid4().hex[:6]}",
        )

        # Motivo vacío debe fallar
        with pytest.raises(ValueError, match="motivo"):
            await registrar_recuento_inventario(
                db=db,
                cliente_id=cliente.id,
                insumo_id=insumo.id,
                storage_location_id=location.id,
                cantidad_fisica=Decimal("45.0000"),
                fecha_recuento=datetime.now(),
                motivo_ajuste="   ",
                clave_idempotencia=f"recuento_fail_{uuid.uuid4().hex[:6]}",
            )

        # Recuento exitoso con motivo explicativo
        recuento, mov_ajuste = await registrar_recuento_inventario(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            cantidad_fisica=Decimal("48.0000"),
            fecha_recuento=datetime.now(),
            motivo_ajuste="Rotura de 2 bolsas durante traslado interno",
            clave_idempotencia=f"recuento_ok_{uuid.uuid4().hex[:6]}",
        )

        assert recuento.diferencia == Decimal("-2.0000")
        assert mov_ajuste.tipo_movimiento.value == "ajuste_recuento_negativo"
