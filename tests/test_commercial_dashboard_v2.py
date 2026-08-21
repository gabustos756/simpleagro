from __future__ import annotations

"""
Suite de Pruebas Unitarias e Integración para el Dashboard Comercial V2 (EduAgro).
Verifica agregación real de Stock 1A/1B/1C, desacoplamiento de StockGrano legacy,
aislamiento de producción teórica de lotes, prioridades de hoy, compromisos próximos,
aislamiento multitenant y estados vacíos limpios.
"""

from decimal import Decimal
from datetime import datetime, date, timedelta
from uuid import uuid4
from contextlib import asynccontextmanager
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import DATABASE_URL
from app.models import (
    Cliente,
    Campania,
    Lote,
    StorageLocation,
    StockPartida,
    StockMovement,
    StockReservation,
    StockDeliveryAllocation,
    StockWeightReconciliation,
    CompromisoGrano,
    GrainDelivery,
    GrainWaybill,
    StockGrano,
    TipoCompromisoEnum,
)
from app.services.commercial_dashboard_service import get_commercial_dashboard_summary
from app.services.stock_service import confirm_delivery_dispatch, allocate_stock_to_delivery


@asynccontextmanager
async def get_test_db():
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await engine.dispose()


@pytest.mark.asyncio
async def test_1_dashboard_v2_calculates_real_stock_1c_balances():
    """
    Test 1: Dashboard V2 calcula físico, reservado, asignado y disponible real de Stock 1C.
    Partida 100 Tn, Reserva 30 Tn, Asignación 20 Tn -> Físico: 100, Reservado: 30, Asignado: 20, Disponible: 50.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Dashboard Test 1")
        db.add(cli)
        await db.flush()

        loc = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="silobolsa", nombre="Silobolsa D1", capacidad_nominal_tn=Decimal("150.0"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(
            id=uuid4(),
            cliente_id=c_id,
            storage_location_id=loc.id,
            cultivo="soja",
            tracking_number="STK-D1-100TN",
            cantidad_inicial_kg=Decimal("100000.0"),
            fecha_ingreso=date.today(),
        )
        db.add(partida)
        await db.flush()

        mov_ingreso = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("100000.0"))
        db.add(mov_ingreso)

        camp = Campania(id=uuid4(), nombre="2025/2026", fecha_inicio=date.today())
        db.add(camp)
        await db.flush()

        comp = CompromisoGrano(
            id=uuid4(),
            cliente_id=c_id,
            campania_id=camp.id,
            cultivo="soja",
            tipo_compromiso=TipoCompromisoEnum.CANJE_INSUMOS,
            concepto="Canje Semillas",
            beneficiario="Acopio Don Pedro",
            toneladas_comprometidas=Decimal("30.0"),
        )
        db.add(comp)
        await db.flush()

        reserva = StockReservation(
            cliente_id=c_id,
            stock_partida_id=partida.id,
            compromiso_id=comp.id,
            cantidad_reserva_kg=Decimal("30000.0"),
            estado="activa",
        )
        db.add(reserva)

        deliv = GrainDelivery(id=uuid4(), cliente_id=c_id, tracking_number="ENT-D1", cultivo="soja", toneladas_planificadas=Decimal("20.0"), estado="planificada")
        db.add(deliv)
        await db.flush()

        asig = await allocate_stock_to_delivery(
            db=db,
            cliente_id=c_id,
            stock_partida_id=partida.id,
            grain_delivery_id=deliv.id,
            cantidad_valor=Decimal("20.0"),
            unidad_medida="tn",
        )
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        assert summary.stock_fisico_total_tn == Decimal("100.00")
        assert summary.stock_reservado_total_tn == Decimal("30.00")
        assert summary.stock_asignado_total_tn == Decimal("20.00")
        assert summary.stock_disponible_libre_tn == Decimal("50.00")


@pytest.mark.asyncio
async def test_2_physical_dispatch_reduces_physical_and_dashboard_balances():
    """
    Test 2: Al realizar un despacho de 20 Tn, el físico pasa de 100 Tn a 80 Tn, asignado a 0, disponible a 50 Tn.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Despacho Test 2")
        db.add(cli)

        loc = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="silobolsa", nombre="Silobolsa D2", capacidad_nominal_tn=Decimal("150.0"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(
            id=uuid4(),
            cliente_id=c_id,
            storage_location_id=loc.id,
            cultivo="soja",
            tracking_number="STK-D2-100TN",
            cantidad_inicial_kg=Decimal("100000.0"),
            fecha_ingreso=date.today(),
        )
        db.add(partida)
        mov_ingreso = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("100000.0"))
        db.add(mov_ingreso)

        deliv = GrainDelivery(id=uuid4(), cliente_id=c_id, tracking_number="ENT-D2", cultivo="soja", toneladas_planificadas=Decimal("20.0"), estado="planificada")
        db.add(deliv)
        await db.flush()

        asig = await allocate_stock_to_delivery(
            db=db,
            cliente_id=c_id,
            stock_partida_id=partida.id,
            grain_delivery_id=deliv.id,
            cantidad_valor=Decimal("20.0"),
            unidad_medida="tn",
        )

        waybill = GrainWaybill(
            id=uuid4(),
            cliente_id=c_id,
            entrega_id=deliv.id,
            numero_carta_porte="CPE-D2",
            peso_neto_origen_kg=Decimal("20000.0"),
            estado="planificada",
        )
        db.add(waybill)
        await db.commit()

        await confirm_delivery_dispatch(
            db=db,
            cliente_id=c_id,
            user_id=None,
            delivery_id=deliv.id,
            waybill_id=waybill.id,
        )

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        assert summary.stock_fisico_total_tn == Decimal("80.00")
        assert summary.stock_asignado_total_tn == Decimal("0.00")
        assert summary.stock_disponible_libre_tn == Decimal("80.00")


@pytest.mark.asyncio
async def test_3_theoretical_production_does_not_alter_physical_stock():
    """
    Test 3: Crear lotes con estimación de 500 Tn no incrementa el stock físico ni disponible.
    """
    from app.models import Campo
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Teorico Test 3")
        db.add(cli)
        await db.flush()

        campo = Campo(id=uuid4(), cliente_id=c_id, nombre="Campo Don Juan", hectareas_totales=100.0)
        db.add(campo)
        await db.flush()

        lote = Lote(
            id=uuid4(),
            cliente_id=c_id,
            campo_id=campo.id,
            nombre="Lote Don Juan",
            superficie_total_ha=100.0,
            superficie_productiva_ha=Decimal("100.0"),
            cultivo_actual="soja",
            qq_ha_estimado=Decimal("50.0"),  # 100 ha * 50 qq/ha / 10 = 500 Tn
        )
        db.add(lote)
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        assert summary.produccion_estimada_lotes_tn == Decimal("500.00")
        assert summary.stock_fisico_total_tn == Decimal("0.00")
        assert summary.stock_disponible_libre_tn == Decimal("0.00")


@pytest.mark.asyncio
async def test_4_legacy_stock_grano_is_ignored_by_dashboard_v2():
    """
    Test 4: Insertar un registro en la tabla legacy StockGrano no afecta los KPIs V2.
    """
    from app.models import Campo
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Legacy Test 4")
        db.add(cli)
        await db.flush()

        campo = Campo(id=uuid4(), cliente_id=c_id, nombre="Campo Legacy", hectareas_totales=100.0)
        db.add(campo)
        await db.flush()

        camp = Campania(id=uuid4(), nombre="2025/2026", fecha_inicio=date.today())
        db.add(camp)
        await db.flush()

        stock_legacy = StockGrano(
            id=uuid4(),
            cliente_id=c_id,
            campo_id=campo.id,
            campania_id=camp.id,
            cultivo="soja",
            ubicacion_tipo="silo_bolsa",
            identificador="SB-99",
            toneladas_almacenadas=Decimal("999.0"),
            fecha_ingreso=date.today(),
        )
        db.add(stock_legacy)
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        assert summary.stock_fisico_total_tn == Decimal("0.00")
        assert summary.stock_disponible_libre_tn == Decimal("0.00")


@pytest.mark.asyncio
async def test_5_upcoming_commitments_render_formatted_labels():
    """
    Test 5: Los compromisos próximos aparecen formateados con build_commitment_display_label.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Label Test 5")
        db.add(cli)
        camp = Campania(id=uuid4(), nombre="2025/2026", fecha_inicio=date.today())
        db.add(camp)
        await db.flush()

        comp = CompromisoGrano(
            id=uuid4(),
            cliente_id=c_id,
            campania_id=camp.id,
            cultivo="soja",
            tipo_compromiso=TipoCompromisoEnum.CANJE_INSUMOS,
            concepto="Abono Fertilizantes 2026",
            beneficiario="Murature S.A.",
            toneladas_comprometidas=Decimal("45.0"),
            fecha_vencimiento=date.today() + timedelta(days=10),
        )
        db.add(comp)
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        assert len(summary.upcoming_commitments) == 1
        item = summary.upcoming_commitments[0]
        assert "Canje" in item.display_label
        assert "Murature S.A." in item.display_label
        assert "45" in item.display_label


@pytest.mark.asyncio
async def test_6_pending_reconciliation_appears_in_priorities():
    """
    Test 6: Una conciliación pendiente aparece como prioridad crítica 'CONCILIACION_PENDIENTE'.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Reconciliation Test 6")
        db.add(cli)

        deliv = GrainDelivery(id=uuid4(), cliente_id=c_id, tracking_number="ENT-REC-TEST", cultivo="soja", estado="recibida")
        db.add(deliv)
        await db.flush()

        waybill = GrainWaybill(id=uuid4(), cliente_id=c_id, entrega_id=deliv.id, numero_carta_porte="CPE-REC-TEST", peso_neto_origen_kg=Decimal("30000.0"), estado="recibida")
        db.add(waybill)
        await db.flush()

        rec = StockWeightReconciliation(
            id=uuid4(),
            cliente_id=c_id,
            grain_delivery_id=deliv.id,
            grain_waybill_id=waybill.id,
            peso_neto_origen_kg=Decimal("30000.0"),
            peso_recibido_destino_kg=Decimal("28500.0"),
            diferencia_kg=Decimal("-1500.0"),
            diferencia_pct=Decimal("-5.0"),
            estado="pendiente",
        )
        db.add(rec)
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        codes = [p.codigo for p in summary.priorities]
        assert "CONCILIACION_PENDIENTE" in codes


@pytest.mark.asyncio
async def test_7_multitenant_isolation():
    """
    Test 7: El Cliente A no ve el stock ni compromisos del Cliente B.
    """
    async with get_test_db() as db:
        c1_id = uuid4()
        c2_id = uuid4()
        db.add_all([Cliente(id=c1_id, nombre="Cliente Tenant A"), Cliente(id=c2_id, nombre="Cliente Tenant B")])
        await db.flush()

        loc_b = StorageLocation(id=uuid4(), cliente_id=c2_id, tipo="silobolsa", nombre="Silobolsa Tenant B", capacidad_nominal_tn=Decimal("100.0"))
        db.add(loc_b)
        await db.flush()

        partida_b = StockPartida(id=uuid4(), cliente_id=c2_id, storage_location_id=loc_b.id, cultivo="soja", tracking_number="STK-TENANT-B", cantidad_inicial_kg=Decimal("80000.0"), fecha_ingreso=date.today())
        db.add(partida_b)
        mov_b = StockMovement(cliente_id=c2_id, stock_partida_id=partida_b.id, tipo="ingreso_inicial", cantidad_kg=Decimal("80000.0"))
        db.add(mov_b)
        await db.commit()

        summary_a = await get_commercial_dashboard_summary(db=db, cliente_id=c1_id, cultivo="soja")
        summary_b = await get_commercial_dashboard_summary(db=db, cliente_id=c2_id, cultivo="soja")

        assert summary_a.stock_fisico_total_tn == Decimal("0.00")
        assert summary_b.stock_fisico_total_tn == Decimal("80.00")


@pytest.mark.asyncio
async def test_8_empty_dashboard_returns_clean_zero_balances():
    """
    Test 8: Cliente sin partidas retorna ceros exactos sin números mock ni errores.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Vacio Test 8")
        db.add(cli)
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        assert summary.stock_fisico_total_tn == Decimal("0.00")
        assert summary.stock_reservado_total_tn == Decimal("0.00")
        assert summary.stock_asignado_total_tn == Decimal("0.00")
        assert summary.stock_disponible_libre_tn == Decimal("0.00")
        assert len(summary.priorities) == 0
        assert len(summary.upcoming_commitments) == 0
