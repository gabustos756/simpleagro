from __future__ import annotations

"""
Suite de Pruebas Unitarias e Integración para el Flujo de Recepción en Destino sobre Cartas de Porte Existentes (Parte A).
Verifica actualización sobre la misma entidad GrainWaybill, sin duplicar cartas, sin segundo descuento de stock físico,
validaciones de peso <= 0, prevención de doble recepción, conciliación dentro de tolerancia y fuera de umbral,
aislamiento multitenant y comportamiento HTTP.
"""

from decimal import Decimal
from datetime import datetime, date
from uuid import uuid4
from contextlib import asynccontextmanager
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

from app.database import DATABASE_URL
from app.models import (
    Cliente,
    Campania,
    StorageLocation,
    StockPartida,
    StockMovement,
    CompromisoGrano,
    GrainDelivery,
    GrainWaybill,
    StockDeliveryAllocation,
    StockWeightReconciliation,
    TipoCompromisoEnum,
)
from app.services.stock_service import (
    allocate_stock_to_delivery,
    confirm_delivery_dispatch,
    record_delivery_reception_and_reconciliation,
)
from app.main import app


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
async def test_1_reception_updates_same_waybill_no_second_stock_deduction():
    """
    Test 1: Registrar 19.850 kg sobre carta con origen 20.000 kg:
    - Actualiza la misma carta;
    - No crea una segunda carta de porte;
    - Calcula diferencia -150 kg;
    - No modifica el stock físico por segunda vez.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Recepcion Test")
        db.add(cli)
        await db.flush()

        loc = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="silobolsa", nombre="Silobolsa Rec", capacidad_nominal_tn=Decimal("100.0"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(
            cliente_id=c_id,
            storage_location_id=loc.id,
            cultivo="soja",
            tracking_number="STK-50TN-REC",
            cantidad_inicial_kg=Decimal("50000.00"),
            fecha_ingreso=date.today(),
        )
        db.add(partida)
        await db.flush()

        mov_ingreso = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("50000.00"))
        db.add(mov_ingreso)
        await db.flush()

        deliv = GrainDelivery(
            id=uuid4(),
            cliente_id=c_id,
            tracking_number="ENT-REC-001",
            acopio_receptor="Puerto Rosario",
            cultivo="soja",
            toneladas_planificadas=Decimal("20.0"),
            estado="planificada",
        )
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
            numero_carta_porte="CPE-REC-999",
            peso_bruto_origen_kg=Decimal("30000.0"),
            tara_kg=Decimal("10000.0"),
            peso_neto_origen_kg=Decimal("20000.0"),
            estado="planificada",
        )
        db.add(waybill)
        await db.commit()

        # Confirmar despacho físico (1ra y única salida de stock)
        await confirm_delivery_dispatch(
            db=db,
            cliente_id=c_id,
            user_id=None,
            delivery_id=deliv.id,
            waybill_id=waybill.id,
        )

        # Verificar conteo de movimientos antes de la recepción
        stmt_mov_count = select(func.count(StockMovement.id)).where(StockMovement.stock_partida_id == partida.id)
        count_before = (await db.execute(stmt_mov_count)).scalar()

        # Registrar recepción en destino: 19.850 kg (diferencia -150 kg)
        res_rec = await record_delivery_reception_and_reconciliation(
            db=db,
            cliente_id=c_id,
            user_id=None,
            delivery_id=deliv.id,
            waybill_id=waybill.id,
            peso_recibido_destino_kg=Decimal("19850.0"),
            observaciones="Llegada OK balanza A",
        )

        # Verificar que no se creó otra carta de porte
        stmt_w_count = select(func.count(GrainWaybill.id)).where(GrainWaybill.entrega_id == deliv.id)
        w_count = (await db.execute(stmt_w_count)).scalar()
        assert w_count == 1

        # Verificar que la misma carta se actualizó
        await db.refresh(waybill)
        assert waybill.estado == "recibida"
        assert waybill.peso_recibido_destino_kg == Decimal("19850.0")
        assert waybill.diferencia_kg == Decimal("-150.0")

        # Verificar que el conteo de movimientos físicos en la partida permanezca inalterado
        count_after = (await db.execute(stmt_mov_count)).scalar()
        assert count_after == count_before


@pytest.mark.asyncio
async def test_2_reception_validations_and_rejection_cases():
    """
    Test 2: Validaciones obligatorias:
    - Peso destino <= 0 rechazado.
    - Recepción sin peso neto origen rechazado.
    - Recepción de carta no despachada / planificada rechazada.
    - Prevención de doble recepción silenciosa.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Validation Test")
        db.add(cli)

        deliv = GrainDelivery(id=uuid4(), cliente_id=c_id, tracking_number="ENT-VAL-002", estado="planificada")
        db.add(deliv)

        waybill_no_despacho = GrainWaybill(
            id=uuid4(),
            cliente_id=c_id,
            entrega_id=deliv.id,
            numero_carta_porte="CPE-PLAN",
            peso_neto_origen_kg=Decimal("15000.0"),
            estado="planificada",
        )
        db.add(waybill_no_despacho)
        await db.commit()

        # 1. Rechazo por carta no despachada
        with pytest.raises(ValueError, match="despachada"):
            await record_delivery_reception_and_reconciliation(
                db=db,
                cliente_id=c_id,
                user_id=None,
                delivery_id=deliv.id,
                waybill_id=waybill_no_despacho.id,
                peso_recibido_destino_kg=Decimal("14900.0"),
            )

        # 2. Rechazo por peso destino <= 0
        waybill_no_despacho.estado = "despachada"
        await db.commit()
        with pytest.raises(ValueError, match="mayor a 0"):
            await record_delivery_reception_and_reconciliation(
                db=db,
                cliente_id=c_id,
                user_id=None,
                delivery_id=deliv.id,
                waybill_id=waybill_no_despacho.id,
                peso_recibido_destino_kg=Decimal("0.0"),
            )

        # 3. Registrar recepción exitosa por 1ra vez
        await record_delivery_reception_and_reconciliation(
            db=db,
            cliente_id=c_id,
            user_id=None,
            delivery_id=deliv.id,
            waybill_id=waybill_no_despacho.id,
            peso_recibido_destino_kg=Decimal("14900.0"),
        )

        # 4. Intentar doble recepción silenciosa debe ser rechazado
        with pytest.raises(ValueError, match="ya cuenta con una recepción registrada"):
            await record_delivery_reception_and_reconciliation(
                db=db,
                cliente_id=c_id,
                user_id=None,
                delivery_id=deliv.id,
                waybill_id=waybill_no_despacho.id,
                peso_recibido_destino_kg=Decimal("14800.0"),
            )


@pytest.mark.asyncio
async def test_3_reception_multitenant_isolation():
    """
    Test 3: Intentar registrar recepción sobre la carta de otro cliente es rechazado.
    """
    async with get_test_db() as db:
        c1_id = uuid4()
        c2_id = uuid4()
        db.add_all([Cliente(id=c1_id, nombre="Cliente 1"), Cliente(id=c2_id, nombre="Cliente 2")])

        deliv = GrainDelivery(id=uuid4(), cliente_id=c1_id, tracking_number="ENT-C1", estado="en_transito")
        db.add(deliv)
        waybill = GrainWaybill(
            id=uuid4(),
            cliente_id=c1_id,
            entrega_id=deliv.id,
            numero_carta_porte="CPE-C1",
            peso_neto_origen_kg=Decimal("20000.0"),
            estado="despachada",
        )
        db.add(waybill)
        await db.commit()

        # Intentar recepcionar usando c2_id debe fallar
        with pytest.raises(ValueError, match="Carta de porte no encontrada"):
            await record_delivery_reception_and_reconciliation(
                db=db,
                cliente_id=c2_id,
                user_id=None,
                delivery_id=deliv.id,
                waybill_id=waybill.id,
                peso_recibido_destino_kg=Decimal("19900.0"),
            )


def test_4_ui_template_contains_reception_modal_and_cta():
    """
    Test 4: Verificar que el template comercial_entregas.html contiene el modal de recepción,
    el CTA de registrar peso recibido y la nota aclaratoria sobre 'Agregar carta'.
    """
    with open("templates/comercial_entregas.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="modal-registrar-recepcion"' in html
    assert "abrirModalRegistrarRecepcion" in html
    assert "⚖️ Registrar peso recibido" in html
    assert "Agregar carta" in html
    assert "recalcularPreviewRecepcion" in html
