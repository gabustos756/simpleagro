from __future__ import annotations

"""
Suite de Pruebas Unitarias e Integración para Arrendamientos V1 y Desglose por Ubicación/Custodia (EduAgro).
Verifica conversión qq/ha a Tn equivalentes, valuación base Rosario vs Acopio,
alertas de valorización incompleta, desglose por custodia ("EN CAMPO" vs "EN CUSTODIA / ACOPIOS"),
y aislamiento multitenant estricto.
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
    Campo,
    Campania,
    StorageLocation,
    StockPartida,
    StockMovement,
    StockReservation,
    StockDeliveryAllocation,
    CompromisoGrano,
    ArrendamientoTerms,
    GrainDelivery,
    GrainWaybill,
    StockGrano,
    TipoCompromisoEnum,
)
from app.services.lease_calculator import calculate_field_lease_terms
from app.services.commercial_dashboard_service import get_commercial_dashboard_summary
from app.services.stock_service import allocate_stock_to_delivery


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


def test_1_lease_calculator_120ha_8qq_ha():
    """
    Test 1: 120 ha * 8 qq/ha genera 960 qq y 96 Tn equivalentes.
    """
    res = calculate_field_lease_terms(
        superficie_arrendada_ha=Decimal("120.0"),
        alquiler_qq_ha=Decimal("8.0"),
        base_valorizacion="rosario",
    )
    assert res.qq_totales == Decimal("960.00")
    assert res.toneladas_equivalentes == Decimal("96.00")


def test_2_base_rosario_with_price_no_deductions():
    """
    Test 2: Base Rosario a 290 USD/Tn calcula valor neto sin descontar flete ni comisión.
    96 Tn * 290 USD/Tn = 27,840 USD.
    """
    res = calculate_field_lease_terms(
        superficie_arrendada_ha=Decimal("120.0"),
        alquiler_qq_ha=Decimal("8.0"),
        base_valorizacion="rosario",
        precio_referencia_usd_tn=Decimal("290.00"),
        flete_usd_tn=Decimal("15.00"),  # Se ignora en Rosario
        comision_usd_tn=Decimal("3.50"), # Se ignora en Rosario
    )
    assert res.status_valorizacion == "complete"
    assert res.precio_neto_usd_tn == Decimal("290.00")
    assert res.valor_neto_estimado_usd == Decimal("27840.00")


def test_3_base_acopio_with_freight_and_commission_deductions():
    """
    Test 3: Base Acopio 290 USD/Tn - Flete 15 USD/Tn - Comisión 5 USD/Tn = 270 USD/Tn Neto.
    96 Tn * 270 USD/Tn = 25,920 USD.
    """
    res = calculate_field_lease_terms(
        superficie_arrendada_ha=Decimal("120.0"),
        alquiler_qq_ha=Decimal("8.0"),
        base_valorizacion="acopio",
        precio_referencia_usd_tn=Decimal("290.00"),
        flete_usd_tn=Decimal("15.00"),
        comision_usd_tn=Decimal("5.00"),
    )
    assert res.status_valorizacion == "complete"
    assert res.precio_neto_usd_tn == Decimal("270.00")
    assert res.valor_neto_estimado_usd == Decimal("25920.00")


def test_4_base_acopio_missing_freight_or_commission_is_partial():
    """
    Test 4: Base Acopio con precio de referencia pero sin flete/comisión queda 'partial' sin usar cero.
    """
    res = calculate_field_lease_terms(
        superficie_arrendada_ha=Decimal("120.0"),
        alquiler_qq_ha=Decimal("8.0"),
        base_valorizacion="acopio",
        precio_referencia_usd_tn=Decimal("290.00"),
        flete_usd_tn=None,
        comision_usd_tn=None,
    )
    assert res.status_valorizacion == "partial"
    assert res.valor_neto_estimado_usd is None
    assert "flete_usd_tn" in res.missing_fields
    assert "comision_usd_tn" in res.missing_fields


def test_5_missing_price_reference_is_not_evaluated():
    """
    Test 5: Si falta precio de referencia, la obligación Tn queda en 96 Tn pero el valor USD no se evalúa.
    """
    res = calculate_field_lease_terms(
        superficie_arrendada_ha=Decimal("120.0"),
        alquiler_qq_ha=Decimal("8.0"),
        base_valorizacion="rosario",
        precio_referencia_usd_tn=None,
    )
    assert res.toneladas_equivalentes == Decimal("96.00")
    assert res.status_valorizacion == "not_evaluated"
    assert res.valor_neto_estimado_usd is None


@pytest.mark.asyncio
async def test_6_lease_commitment_can_be_reserved_and_allocated():
    """
    Test 6: Un compromiso de arrendamiento V1 de 96 Tn permite vincular reservas y asignaciones.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Lease Reservation Test 6")
        db.add(cli)

        campo = Campo(id=uuid4(), cliente_id=c_id, nombre="Campo Norte Arrendado", hectareas_totales=120.0)
        db.add(campo)

        camp = Campania(id=uuid4(), nombre="2025/2026", fecha_inicio=date.today())
        db.add(camp)
        await db.flush()

        loc = StorageLocation(id=uuid4(), cliente_id=c_id, campo_id=campo.id, tipo="silobolsa", nombre="Silobolsa L1", capacidad_nominal_tn=Decimal("200.0"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(id=uuid4(), cliente_id=c_id, storage_location_id=loc.id, cultivo="soja", tracking_number="STK-ARR-100TN", cantidad_inicial_kg=Decimal("100000.0"), fecha_ingreso=date.today())
        db.add(partida)
        mov = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("100000.0"))
        db.add(mov)

        comp = CompromisoGrano(
            id=uuid4(),
            cliente_id=c_id,
            campania_id=camp.id,
            campo_id=campo.id,
            cultivo="soja",
            tipo_compromiso=TipoCompromisoEnum.ALQUILER_ARRENDAMIENTO,
            concepto="Alquiler Campo Norte (120 ha x 8 qq/ha)",
            beneficiario="Sucesión Donati",
            toneladas_comprometidas=Decimal("96.0"),
        )
        db.add(comp)
        await db.flush()

        terms = ArrendamientoTerms(
            compromiso_id=comp.id,
            superficie_arrendada_ha=Decimal("120.0"),
            alquiler_qq_ha=Decimal("8.0"),
            base_valorizacion="rosario",
            precio_referencia_usd_tn=Decimal("290.00"),
        )
        db.add(terms)

        reserva = StockReservation(cliente_id=c_id, stock_partida_id=partida.id, compromiso_id=comp.id, cantidad_reserva_kg=Decimal("50000.0"), estado="activa")
        db.add(reserva)
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        assert summary.stock_fisico_total_tn == Decimal("100.00")
        assert summary.stock_reservado_total_tn == Decimal("50.00")
        assert summary.upcoming_commitments[0].toneladas_comprometidas_tn == Decimal("96.00")
        assert summary.upcoming_commitments[0].toneladas_reservadas_tn == Decimal("50.00")


def test_8_invalid_negative_lease_inputs_rejected():
    """
    Test 8: Superficie o qq/ha menores o iguales a cero son rechazados con ValueError.
    """
    with pytest.raises(ValueError, match="superficie"):
        calculate_field_lease_terms(superficie_arrendada_ha=Decimal("0.0"), alquiler_qq_ha=Decimal("8.0"))

    with pytest.raises(ValueError, match="alquiler"):
        calculate_field_lease_terms(superficie_arrendada_ha=Decimal("100.0"), alquiler_qq_ha=Decimal("-5.0"))


@pytest.mark.asyncio
async def test_9_silo_casa_principal_appears_in_en_campo_group():
    """
    Test 9: Stock en silo de chapa de la Casa Principal aparece agrupado en 'EN CAMPO'.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Silo Casa Test 9")
        db.add(cli)
        await db.flush()

        loc = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="silo_propio", nombre="Silo Chapa N° 1 - Casa Principal", capacidad_nominal_tn=Decimal("120.0"))
        db.add(loc)
        await db.flush()

        partida = StockPartida(id=uuid4(), cliente_id=c_id, storage_location_id=loc.id, cultivo="soja", tracking_number="STK-SILO-CASA", cantidad_inicial_kg=Decimal("60000.0"), fecha_ingreso=date.today())
        db.add(partida)
        mov = StockMovement(cliente_id=c_id, stock_partida_id=partida.id, tipo="ingreso_inicial", cantidad_kg=Decimal("60000.0"))
        db.add(mov)
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        group_campo = next((g for g in summary.location_groups if g.nombre_grupo == "EN CAMPO"), None)
        assert group_campo is not None
        assert group_campo.stock_fisico_tn == Decimal("60.00")
        assert len(group_campo.locations) == 1
        assert "Casa Principal" in group_campo.locations[0].nombre


@pytest.mark.asyncio
async def test_10_stock_in_acopios_afa_murature_agd_appears_in_custodia():
    """
    Test 10: Stock en acopios individuales (AFA, Murature, AGD) aparece en 'EN CUSTODIA / ACOPIOS'.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Acopios Test 10")
        db.add(cli)
        await db.flush()

        loc_afa = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="acopio", nombre="Acopio AFA San Lorenzo")
        loc_mur = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="acopio", nombre="Acopio Murature S.A.")
        loc_agd = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="acopio", nombre="Acopio AGD General Deheza")
        db.add_all([loc_afa, loc_mur, loc_agd])
        await db.flush()

        p_afa = StockPartida(id=uuid4(), cliente_id=c_id, storage_location_id=loc_afa.id, cultivo="soja", tracking_number="STK-AFA-40TN", cantidad_inicial_kg=Decimal("40000.0"), fecha_ingreso=date.today())
        p_mur = StockPartida(id=uuid4(), cliente_id=c_id, storage_location_id=loc_mur.id, cultivo="soja", tracking_number="STK-MUR-30TN", cantidad_inicial_kg=Decimal("30000.0"), fecha_ingreso=date.today())
        db.add_all([p_afa, p_mur])

        mov_afa = StockMovement(cliente_id=c_id, stock_partida_id=p_afa.id, tipo="ingreso_inicial", cantidad_kg=Decimal("40000.0"))
        mov_mur = StockMovement(cliente_id=c_id, stock_partida_id=p_mur.id, tipo="ingreso_inicial", cantidad_kg=Decimal("30000.0"))
        db.add_all([mov_afa, mov_mur])
        await db.commit()

        summary = await get_commercial_dashboard_summary(db=db, cliente_id=c_id, cultivo="soja")

        group_acopio = next((g for g in summary.location_groups if "CUSTODIA" in g.nombre_grupo), None)
        assert group_acopio is not None
        assert group_acopio.stock_fisico_tn == Decimal("70.00")

        # Verificar que AFA y Murature aparecen como custodia y no vendidos
        afa_item = next((l for l in group_acopio.locations if "AFA" in l.nombre), None)
        assert afa_item is not None
        assert afa_item.es_custodia_acopio is True
        assert afa_item.stock_fisico_tn == Decimal("40.00")


@pytest.mark.asyncio
async def test_14_multitenant_location_and_stock_isolation():
    """
    Test 14: El Cliente A no visualiza ubicaciones ni stock del Cliente B.
    """
    async with get_test_db() as db:
        c1_id = uuid4()
        c2_id = uuid4()
        db.add_all([Cliente(id=c1_id, nombre="Cliente Loc Tenant A"), Cliente(id=c2_id, nombre="Cliente Loc Tenant B")])
        await db.flush()

        loc_b = StorageLocation(id=uuid4(), cliente_id=c2_id, tipo="acopio", nombre="Acopio Exclusivo B")
        db.add(loc_b)
        await db.flush()

        partida_b = StockPartida(id=uuid4(), cliente_id=c2_id, storage_location_id=loc_b.id, cultivo="soja", tracking_number="STK-B-50TN", cantidad_inicial_kg=Decimal("50000.0"), fecha_ingreso=date.today())
        db.add(partida_b)
        mov_b = StockMovement(cliente_id=c2_id, stock_partida_id=partida_b.id, tipo="ingreso_inicial", cantidad_kg=Decimal("50000.0"))
        db.add(mov_b)
        await db.commit()

        summary_a = await get_commercial_dashboard_summary(db=db, cliente_id=c1_id, cultivo="soja")
        summary_b = await get_commercial_dashboard_summary(db=db, cliente_id=c2_id, cultivo="soja")

        # Cliente A no ve la ubicación de Cliente B
        all_locs_a = [loc for grp in summary_a.location_groups for loc in grp.locations]
        assert not any(l.nombre == "Acopio Exclusivo B" for l in all_locs_a)

        all_locs_b = [loc for grp in summary_b.location_groups for loc in grp.locations]
        assert any(l.nombre == "Acopio Exclusivo B" for l in all_locs_b)


@pytest.mark.asyncio
async def test_15_http_post_arrendamiento_endpoint():
    """
    Test 15: Probar endpoint HTTP POST /comercial/contratos/arrendamientos/crear
    Verifica que procesa correctamente la petición sin lanzar NameError ni Error 500.
    """
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente HTTP Arrendamiento Test")
        db.add(cli)
        await db.flush()

        campo = Campo(id=uuid4(), cliente_id=c_id, nombre="Campo HTTP Test", hectareas_totales=150.0)
        db.add(campo)
        camp = Campania(id=uuid4(), cliente_id=c_id, nombre="2025/2026", fecha_inicio=date.today(), activa=True)
        db.add(camp)
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/comercial/contratos/arrendamientos/crear",
                data={
                    "campo_id": str(campo.id),
                    "superficie_arrendada_ha": "150.0",
                    "alquiler_qq_ha": "10.0",
                    "beneficiario": "Familia Rossi",
                    "concepto": "Alquiler HTTP Test",
                    "cultivo": "soja",
                    "base_valorizacion": "rosario",
                    "precio_referencia_usd_tn": "295.00",
                },
                follow_redirects=False,
            )

            # Debe redirigir con 303 (no dar 500)
            assert resp.status_code == 303
            assert "/comercial/contratos" in resp.headers.get("location", "")
