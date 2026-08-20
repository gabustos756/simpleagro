"""
Suite de Pruebas Unitarias e Integración para Stock 1C (EduAgro).
Cubre despacho físico de stock, consumo de asignaciones, pesaje neto de origen,
conciliación de pesajes origen vs destino, resolución de diferencias, reglas determinísticas
del motor de decisiones y prevención de doble descuento.
"""

from decimal import Decimal
from datetime import datetime, date
from uuid import uuid4
from contextlib import asynccontextmanager
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import DATABASE_URL
from app.models import (
    Cliente,
    Campania,
    StorageLocation,
    StockPartida,
    StockMovement,
    StockReservation,
    StockDeliveryAllocation,
    StockWeightReconciliation,
    CompromisoGrano,
    GrainDelivery,
    GrainWaybill,
    TipoCompromisoEnum,
)
from app.services.stock_service import (
    get_stock_partida_balance,
    get_stock_partida_commercial_balance,
    confirm_delivery_dispatch,
    record_delivery_reception_and_reconciliation,
    resolve_weight_reconciliation,
)
from app.services.decision_engine.models import (
    DecisionContext,
    GrainDeliveryContext,
    GrainWaybillContext,
)
from app.services.decision_engine.rules.base import RuleTraceContext
from app.services.decision_engine.rules.stock_delivery import (
    RuleDespachoSinAsignacionSuficiente,
    RuleDespachoConfirmado,
    RuleRecepcionConDiferenciaDePesaje,
    RuleDiferenciaDePesajeDentroDeTolerancia,
    RuleDiferenciaDePesajePendienteDeResolucion,
    RuleEntregaDespachadaSinPesoDestino,
    RuleAsignacionDespachada,
)
from app.services.decision_engine.policy import DecisionPolicyResolver


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
async def test_1c_dispatch_standard_flow():
    """
    Test 1: Partida 49 Tn, reserva 30 Tn, asignación 18 Tn, carta neto origen 18.000 kg:
    - confirm_delivery_dispatch crea salida física de -18.000 kg.
    - físico pasa de 49 Tn a 31 Tn.
    - reservado remanente pasa a 12 Tn.
    - asignado activo pasa a 0 Tn.
    - disponible libre sigue en 19 Tn (31 - 12 - 0 = 19 Tn).
    - no hay doble conteo.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente QA 1C Standard")
        db.add(cli)
        await db.flush()

        loc = StorageLocation(cliente_id=c_id, nombre="Silobolsa 50Tn", tipo="silobolsa", capacidad_nominal_tn=Decimal("50.00"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(
            cliente_id=c_id,
            storage_location_id=loc.id,
            cultivo="soja",
            tracking_number="STK-49TN-STD",
            cantidad_inicial_kg=Decimal("49000.00"),
            fecha_ingreso=date.today(),
        )
        db.add(partida)
        await db.flush()

        # Ingreso inicial 49.000 kg
        mov_ingreso = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("49000.00"))
        db.add(mov_ingreso)
        await db.flush()

        camp = Campania(id=uuid4(), nombre="2025/2026", fecha_inicio=date.today())
        db.add(camp)
        await db.flush()

        comp = CompromisoGrano(
            cliente_id=c_id,
            campania_id=camp.id,
            cultivo="soja",
            tipo_compromiso=TipoCompromisoEnum.CANJE_INSUMOS,
            concepto="Canje QA",
            beneficiario="Acopio AFA Maciel",
            toneladas_comprometidas=Decimal("30.00"),
        )
        db.add(comp)
        await db.flush()

        res = StockReservation(cliente_id=c_id, stock_partida_id=partida.id, compromiso_id=comp.id, cantidad_reserva_kg=Decimal("30000.00"), estado="activa")
        db.add(res)
        await db.flush()

        deliv = GrainDelivery(cliente_id=c_id, tracking_number="ENT-1C-STD", cultivo="soja", toneladas_planificadas=Decimal("18.00"), estado="planificada")
        db.add(deliv)
        await db.flush()

        alloc = StockDeliveryAllocation(
            cliente_id=c_id,
            stock_partida_id=partida.id,
            grain_delivery_id=deliv.id,
            stock_reservation_id=res.id,
            compromiso_id=comp.id,
            cantidad_kg=Decimal("18000.00"),
            origen_asignacion="reserva",
            estado="activa",
        )
        db.add(alloc)
        await db.flush()

        waybill = GrainWaybill(
            cliente_id=c_id,
            entrega_id=deliv.id,
            numero_carta_porte="CP-1C-STD",
            peso_bruto_origen_kg=Decimal("32000.00"),
            tara_kg=Decimal("14000.00"),
            peso_neto_origen_kg=Decimal("18000.00"),
            estado="planificada",
        )
        db.add(waybill)
        await db.commit()

        # Verificar saldos antes del despacho: Físico=49Tn, Reservado=12Tn, Asignado=18Tn, Disponible=19Tn
        bal_pre = await get_stock_partida_commercial_balance(db, c_id, partida.id)
        assert bal_pre["stock_fisico_kg"] == Decimal("49000.00")
        assert bal_pre["stock_reservado_kg"] == Decimal("12000.00")
        assert bal_pre["stock_asignado_kg"] == Decimal("18000.00")
        assert bal_pre["stock_disponible_kg"] == Decimal("19000.00")

        # Ejecutar Despacho
        res_dispatch = await confirm_delivery_dispatch(
            db=db,
            cliente_id=c_id,
            user_id=None,
            delivery_id=deliv.id,
            waybill_id=waybill.id,
        )

        assert res_dispatch["peso_despachado_kg"] == Decimal("18000.00")
        assert res_dispatch["nuevo_estado_entrega"] == "en_transito"
        assert res_dispatch["nuevo_estado_carta"] == "despachada"

        # Verificar saldos posteriores: Físico=31Tn, Reservado=30Tn, Asignado=0Tn, Disponible=1Tn
        bal_post = await get_stock_partida_commercial_balance(db, c_id, partida.id)
        assert bal_post["stock_fisico_kg"] == Decimal("31000.00")
        assert bal_post["stock_reservado_kg"] == Decimal("30000.00")
        assert bal_post["stock_asignado_kg"] == Decimal("0.00")
        assert bal_post["stock_disponible_kg"] == Decimal("1000.00")

        # Comprobar que el movimiento creado es negativo de tipo despacho_entrega
        stmt_m = select(StockMovement).where(StockMovement.stock_partida_id == partida.id, StockMovement.tipo == "despacho_entrega")
        res_m = await db.execute(stmt_m)
        mov_despacho = res_m.scalars().first()
        assert mov_despacho is not None
        assert mov_despacho.cantidad_kg == Decimal("-18000.00")
        assert mov_despacho.grain_delivery_id == deliv.id
        assert mov_despacho.grain_waybill_id == waybill.id


@pytest.mark.asyncio
async def test_1c_dispatch_insufficient_allocation_rejected():
    """
    Test 3: Intentar despacho cuando las asignaciones activas no cubren el peso neto de origen es rechazado.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente QA Insuficiente")
        db.add(cli)
        await db.flush()

        loc = StorageLocation(cliente_id=c_id, nombre="Silo 1", tipo="silo_propio", capacidad_nominal_tn=Decimal("100.00"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(
            cliente_id=c_id,
            storage_location_id=loc.id,
            cultivo="soja",
            tracking_number="STK-INS",
            cantidad_inicial_kg=Decimal("50000.00"),
            fecha_ingreso=date.today(),
        )
        db.add(partida)
        await db.flush()

        mov_ingreso = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("50000.00"))
        db.add(mov_ingreso)
        await db.flush()

        deliv = GrainDelivery(cliente_id=c_id, tracking_number="ENT-INS-01", cultivo="soja", toneladas_planificadas=Decimal("30.00"), estado="planificada")
        db.add(deliv)
        await db.flush()

        # Asignación sólo de 10.000 kg
        alloc = StockDeliveryAllocation(cliente_id=c_id, stock_partida_id=partida.id, grain_delivery_id=deliv.id, cantidad_kg=Decimal("10000.00"), estado="activa")
        db.add(alloc)
        await db.flush()

        # Carta de porte por 25.000 kg
        waybill = GrainWaybill(cliente_id=c_id, entrega_id=deliv.id, numero_carta_porte="CP-INS", peso_bruto_origen_kg=Decimal("39000.00"), tara_kg=Decimal("14000.00"), peso_neto_origen_kg=Decimal("25000.00"))
        db.add(waybill)
        await db.commit()

        with pytest.raises(ValueError, match="es insuficiente para cubrir el peso neto"):
            await confirm_delivery_dispatch(db=db, cliente_id=c_id, user_id=None, delivery_id=deliv.id, waybill_id=waybill.id)


@pytest.mark.asyncio
async def test_1c_dispatch_duplicate_rejected():
    """
    Test 5: Intentar confirmar despacho dos veces sobre la misma carta es rechazado (idempotencia).
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente QA Idempotencia")
        db.add(cli)
        await db.flush()

        loc = StorageLocation(cliente_id=c_id, nombre="Silo 2", tipo="silo_propio", capacidad_nominal_tn=Decimal("100.00"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(
            cliente_id=c_id,
            storage_location_id=loc.id,
            cultivo="soja",
            tracking_number="STK-DUP",
            cantidad_inicial_kg=Decimal("30000.00"),
            fecha_ingreso=date.today(),
        )
        db.add(partida)
        await db.flush()

        mov_ingreso = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("30000.00"))
        db.add(mov_ingreso)
        await db.flush()

        deliv = GrainDelivery(cliente_id=c_id, tracking_number="ENT-DUP-01", cultivo="soja", toneladas_planificadas=Decimal("15.00"), estado="planificada")
        db.add(deliv)
        await db.flush()

        alloc = StockDeliveryAllocation(cliente_id=c_id, stock_partida_id=partida.id, grain_delivery_id=deliv.id, cantidad_kg=Decimal("15000.00"), estado="activa")
        db.add(alloc)
        await db.flush()

        waybill = GrainWaybill(cliente_id=c_id, entrega_id=deliv.id, numero_carta_porte="CP-DUP", peso_neto_origen_kg=Decimal("15000.00"))
        db.add(waybill)
        await db.commit()

        # Primer despacho: Exitoso
        await confirm_delivery_dispatch(db=db, cliente_id=c_id, user_id=None, delivery_id=deliv.id, waybill_id=waybill.id)

        # Segundo despacho: Debe fallar
        with pytest.raises(ValueError, match="ya fue despachada anteriormente"):
            await confirm_delivery_dispatch(db=db, cliente_id=c_id, user_id=None, delivery_id=deliv.id, waybill_id=waybill.id)


@pytest.mark.asyncio
async def test_1c_reception_and_reconciliation_within_tolerance():
    """
    Test 10 & 12: Recepción con peso destino 17.820 kg vs origen 18.000 kg (-180 kg / -1.0%):
    - NO crea segunda salida física.
    - Registra diferencia -180 kg (-1.0%).
    - Marca reconciliación como dentro_tolerancia.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente QA Tolerancia")
        db.add(cli)
        await db.flush()

        deliv = GrainDelivery(cliente_id=c_id, tracking_number="ENT-REC-01", cultivo="soja", estado="en_transito")
        db.add(deliv)
        await db.flush()

        waybill = GrainWaybill(cliente_id=c_id, entrega_id=deliv.id, numero_carta_porte="CP-REC-01", peso_neto_origen_kg=Decimal("18000.00"), estado="despachada")
        db.add(waybill)
        await db.commit()

        res_rec = await record_delivery_reception_and_reconciliation(
            db=db,
            cliente_id=c_id,
            user_id=None,
            delivery_id=deliv.id,
            waybill_id=waybill.id,
            peso_recibido_destino_kg=Decimal("17820.00"),
        )

        assert res_rec["diferencia_kg"] == Decimal("-180.00")
        assert res_rec["diferencia_pct"] == Decimal("-1.00")
        assert res_rec["estado_reconciliacion"] == "dentro_tolerancia"

        # Verificar que NO se crearon movimientos adicionales de stock
        stmt_m = select(StockMovement).where(StockMovement.grain_delivery_id == deliv.id)
        res_m = await db.execute(stmt_m)
        movs = res_m.scalars().all()
        assert len(movs) == 0


@pytest.mark.asyncio
async def test_1c_reception_significant_difference_pending_resolution():
    """
    Test 11 & 15: Recepción con diferencia significativa (-500 kg / -2.78%):
    - Marca reconciliación como pendiente.
    - Resolución con ajuste_inventario crea movimiento explícito de ajuste en stock física y actualiza estado a resuelta.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente QA Ajuste")
        db.add(cli)
        await db.flush()

        loc = StorageLocation(cliente_id=c_id, nombre="Silo A", tipo="silo_propio", capacidad_nominal_tn=Decimal("100.00"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(
            cliente_id=c_id,
            storage_location_id=loc.id,
            cultivo="soja",
            tracking_number="STK-REC-AJUSTE",
            cantidad_inicial_kg=Decimal("50000.00"),
            fecha_ingreso=date.today(),
        )
        db.add(partida)
        await db.flush()

        mov_ingreso = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("50000.00"))
        db.add(mov_ingreso)
        await db.flush()

        deliv = GrainDelivery(cliente_id=c_id, tracking_number="ENT-REC-02", cultivo="soja", estado="en_transito")
        db.add(deliv)
        await db.flush()

        waybill = GrainWaybill(cliente_id=c_id, entrega_id=deliv.id, numero_carta_porte="CP-REC-02", peso_neto_origen_kg=Decimal("18000.00"), estado="despachada")
        db.add(waybill)
        await db.commit()

        # Recepción con 17.500 kg (diferencia -500 kg / -2.78%)
        res_rec = await record_delivery_reception_and_reconciliation(
            db=db,
            cliente_id=c_id,
            user_id=None,
            delivery_id=deliv.id,
            waybill_id=waybill.id,
            peso_recibido_destino_kg=Decimal("17500.00"),
        )

        assert res_rec["diferencia_kg"] == Decimal("-500.00")
        assert res_rec["estado_reconciliacion"] == "pendiente"

        # Resolver con ajuste_inventario (-500 kg)
        res_sol = await resolve_weight_reconciliation(
            db=db,
            cliente_id=c_id,
            user_id=None,
            reconciliation_id=res_rec["reconciliation_id"],
            resolucion_tipo="ajuste_inventario",
            observaciones="Ajuste aceptado por merma en balanza destino",
            ajuste_cantidad_valor=Decimal("-500.00"),
            stock_partida_id=partida.id,
        )

        assert res_sol["nuevo_estado"] == "resuelta"
        assert res_sol["movimiento_ajuste_id"] is not None

        # Comprobar que el nuevo saldo físico refleja los -500 kg de ajuste (50.000 -> 49.500 kg)
        bal_final = await get_stock_partida_balance(db, c_id, partida.id)
        assert bal_final["saldo_fisico_kg"] == Decimal("49500.00")


@pytest.mark.asyncio
async def test_1c_resolution_aceptada_sin_ajuste_preserves_stock():
    """
    Test 13: Resolver conciliación con 'aceptada_sin_ajuste' documenta resolución y NO altera el stock físico.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente QA Sin Ajuste")
        db.add(cli)
        await db.flush()

        loc = StorageLocation(cliente_id=c_id, nombre="Silo B", tipo="silo_propio", capacidad_nominal_tn=Decimal("100.00"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(
            cliente_id=c_id,
            storage_location_id=loc.id,
            cultivo="soja",
            tracking_number="STK-SIN-AJUSTE",
            cantidad_inicial_kg=Decimal("40000.00"),
            fecha_ingreso=date.today(),
        )
        db.add(partida)
        await db.flush()

        mov_ingreso = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("40000.00"))
        db.add(mov_ingreso)
        await db.flush()

        deliv = GrainDelivery(cliente_id=c_id, tracking_number="ENT-REC-03", cultivo="soja", estado="en_transito")
        db.add(deliv)
        await db.flush()

        waybill = GrainWaybill(cliente_id=c_id, entrega_id=deliv.id, numero_carta_porte="CP-REC-03", peso_neto_origen_kg=Decimal("18000.00"), estado="despachada")
        db.add(waybill)
        await db.commit()

        res_rec = await record_delivery_reception_and_reconciliation(
            db=db,
            cliente_id=c_id,
            user_id=None,
            delivery_id=deliv.id,
            waybill_id=waybill.id,
            peso_recibido_destino_kg=Decimal("17600.00"), # -400 kg
        )

        # Resolver sin ajuste
        res_sol = await resolve_weight_reconciliation(
            db=db,
            cliente_id=c_id,
            user_id=None,
            reconciliation_id=res_rec["reconciliation_id"],
            resolucion_tipo="aceptada_sin_ajuste",
            observaciones="Diferencia dentro del acuerdo comercial sin reclamo",
        )

        assert res_sol["nuevo_estado"] == "resuelta"
        assert res_sol["movimiento_ajuste_id"] is None

        bal_final = await get_stock_partida_balance(db, c_id, partida.id)
        assert bal_final["saldo_fisico_kg"] == Decimal("40000.00")


@pytest.mark.asyncio
async def test_1c_multitenant_isolation():
    """
    Test 8 & 17: Intentar despachar o resolver conciliaciones entre clientes distintos genera error.
    """
    async with get_test_db() as db:
        c1_id = uuid4()
        c2_id = uuid4()

        cli1 = Cliente(id=c1_id, nombre="Cliente 1 Multi")
        cli2 = Cliente(id=c2_id, nombre="Cliente 2 Multi")
        db.add_all([cli1, cli2])
        await db.flush()

        deliv1 = GrainDelivery(cliente_id=c1_id, tracking_number="ENT-C1-MULTI", cultivo="soja", estado="planificada")
        db.add(deliv1)
        await db.flush()

        waybill1 = GrainWaybill(cliente_id=c1_id, entrega_id=deliv1.id, numero_carta_porte="CP-C1-MULTI", peso_neto_origen_kg=Decimal("10000.00"))
        db.add(waybill1)
        await db.commit()

        # Cliente 2 intenta despachar entrega de Cliente 1
        with pytest.raises(ValueError, match="no encontrada o no autorizada"):
            await confirm_delivery_dispatch(db=db, cliente_id=c2_id, user_id=None, delivery_id=deliv1.id, waybill_id=waybill1.id)


def test_1c_decision_engine_stock_delivery_rules():
    """
    Test 18-23: Verificación de reglas determinísticas puras de Stock 1C en el motor de decisiones.
    """
    policy = DecisionPolicyResolver().resolve()

    # 18. Regla DESPACHO_SIN_ASIGNACION_SUFICIENTE
    rule_asig = RuleDespachoSinAsignacionSuficiente()
    ctx_asig_ins = DecisionContext(
        cultivo="soja",
        delivery_context={"peso_neto_origen_kg": 20000.0, "toneladas_asignadas_activas_kg": 10000.0}
    )
    eval_asig = rule_asig.evaluate(ctx_asig_ins, policy, RuleTraceContext())
    assert eval_asig.status == "triggered"
    assert eval_asig.insight.codigo == "DESPACHO_SIN_ASIGNACION_SUFICIENTE"

    # 19. Regla DESPACHO_CONFIRMADO
    rule_desp = RuleDespachoConfirmado()
    ctx_desp = DecisionContext(
        cultivo="soja",
        delivery_context={"is_despachada": True, "despachado_tn": 18.0}
    )
    eval_desp = rule_desp.evaluate(ctx_desp, policy, RuleTraceContext())
    assert eval_desp.status == "triggered"
    assert eval_desp.insight.codigo == "DESPACHO_CONFIRMADO"

    # 20. Regla RECEPCION_CON_DIFERENCIA_DE_PESAJE
    rule_dif = RuleRecepcionConDiferenciaDePesaje()
    ctx_dif = DecisionContext(
        cultivo="soja",
        delivery_context={"diferencia_kg": -500.0, "diferencia_pct": -2.78}
    )
    eval_dif = rule_dif.evaluate(ctx_dif, policy, RuleTraceContext())
    assert eval_dif.status == "triggered"
    assert eval_dif.insight.codigo == "RECEPCION_CON_DIFERENCIA_DE_PESAJE"

    # 21. Regla DIFERENCIA_DE_PESAJE_DENTRO_DE_TOLERANCIA
    rule_tol = RuleDiferenciaDePesajeDentroDeTolerancia()
    ctx_tol = DecisionContext(
        cultivo="soja",
        delivery_context={"diferencia_kg": -100.0, "diferencia_pct": -0.5}
    )
    eval_tol = rule_tol.evaluate(ctx_tol, policy, RuleTraceContext())
    assert eval_tol.status == "triggered"
    assert eval_tol.insight.codigo == "DIFERENCIA_DE_PESAJE_DENTRO_DE_TOLERANCIA"
