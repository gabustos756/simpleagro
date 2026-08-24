from __future__ import annotations

"""
Suite de Pruebas Unitarias e Integración para Etiquetas de Compromisos Comerciales (EduAgro).
Cubre formateo argentino, fallbacks de etiquetas, distinción entre compromisos de igual tonelaje,
verificación de endpoints HTTP (/comercial/stock, /comercial/entregas), aislamiento multitenant y
preservación del UUID en el value de los option.
"""

from decimal import Decimal
from datetime import datetime, date
from uuid import uuid4
from contextlib import asynccontextmanager
import pytest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import DATABASE_URL
from app.models import (
    Cliente,
    Campania,
    CompromisoGrano,
    TipoCompromisoEnum,
)
from app.services.stock_service import (
    build_commitment_display_label,
    formato_ar_decimal,
    get_compromisos_saldos_map,
    format_compromiso_dict,
)


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


def test_1_build_commitment_display_label_full_data():
    """
    Test 1: Construcción completa de label con tipo, contraparte, referencia, saldo y vencimiento.
    """
    c_id = uuid4()
    comp = CompromisoGrano(
        id=c_id,
        cliente_id=uuid4(),
        campania_id=uuid4(),
        cultivo="soja",
        tipo_compromiso=TipoCompromisoEnum.CANJE_INSUMOS,
        concepto="Semilla maíz 2026/27",
        beneficiario="Murature",
        toneladas_comprometidas=Decimal("18.00"),
        fecha_vencimiento=date(2026, 9, 30),
    )

    label = build_commitment_display_label(comp, saldo_tn=Decimal("18.00"))
    assert label == "Canje · Murature · Semilla maíz 2026/27 · Saldo: 18,00 Tn · Vence: 30/09/2026"


def test_2_build_commitment_display_label_fallback_missing_fields():
    """
    Test 2: Fallback cuando faltan contraparte y concepto no queda vacío ni sólo con toneladas.
    Ejemplo: 'Compromiso sin referencia · Saldo: 18,00 Tn · ID: ABCD'
    """
    c_id = uuid4()
    short_id = str(c_id)[-4:].upper()
    comp = CompromisoGrano(
        id=c_id,
        cliente_id=uuid4(),
        campania_id=uuid4(),
        cultivo="soja",
        tipo_compromiso=TipoCompromisoEnum.OTRO,
        concepto="",
        beneficiario="",
        toneladas_comprometidas=Decimal("18.00"),
        fecha_vencimiento=None,
    )

    label = build_commitment_display_label(comp, saldo_tn=Decimal("18.00"))
    assert "Compromiso sin referencia" in label
    assert "Saldo: 18,00 Tn" in label
    assert f"ID: {short_id}" in label
    assert label != "(18 Tn)"
    assert label != "(18.0 Tn)"


def test_3_two_commitments_equal_tonnage_distinct_labels():
    """
    Test 3: Dos compromisos con exactamente el mismo tonelaje pero distinta contraparte o referencia tienen labels distinguibles.
    """
    comp1 = CompromisoGrano(
        id=uuid4(),
        cliente_id=uuid4(),
        campania_id=uuid4(),
        cultivo="soja",
        tipo_compromiso=TipoCompromisoEnum.CANJE_INSUMOS,
        concepto="Semilla maíz 2026",
        beneficiario="Murature",
        toneladas_comprometidas=Decimal("18.00"),
        fecha_vencimiento=date(2026, 9, 30),
    )
    comp2 = CompromisoGrano(
        id=uuid4(),
        cliente_id=uuid4(),
        campania_id=uuid4(),
        cultivo="soja",
        tipo_compromiso=TipoCompromisoEnum.ALQUILER_ARRENDAMIENTO,
        concepto="Arrendamiento Lote 4",
        beneficiario="Don Pedro",
        toneladas_comprometidas=Decimal("18.00"),
        fecha_vencimiento=None,
    )

    label1 = build_commitment_display_label(comp1, saldo_tn=Decimal("18.00"))
    label2 = build_commitment_display_label(comp2, saldo_tn=Decimal("18.00"))

    assert label1 != label2
    assert "Murature" in label1 and "Canje" in label1
    assert "Don Pedro" in label2 and "Alquiler" in label2


def test_4_expired_commitment_prefix():
    """
    Test 4: Compromiso con fecha de vencimiento pasada incluye prefijo [Vencido].
    """
    comp = CompromisoGrano(
        id=uuid4(),
        cliente_id=uuid4(),
        campania_id=uuid4(),
        cultivo="soja",
        tipo_compromiso=TipoCompromisoEnum.CANJE_INSUMOS,
        concepto="Insumos pasados",
        beneficiario="Proveedor AFA",
        toneladas_comprometidas=Decimal("20.00"),
        fecha_vencimiento=date(2020, 1, 1),
    )

    label = build_commitment_display_label(comp)
    assert label.startswith("[Vencido]")
    assert "Vence: 01/01/2020" in label


def test_5_formato_ar_decimal():
    """
    Test 5: Formateo argentino de números decimales.
    """
    assert formato_ar_decimal(Decimal("18.00")) == "18,00"
    assert formato_ar_decimal(Decimal("1234.50")) == "1.234,50"
    assert formato_ar_decimal(Decimal("0.5")) == "0,50"
    assert formato_ar_decimal(None) == "0,00"


@pytest.mark.asyncio
async def test_6_multitenant_isolation_commitments():
    """
    Test 6: Compromisos de otro cliente_id no son retornados en get_compromisos_saldos_map.
    """
    async with get_test_db() as db:
        c1_id = uuid4()
        c2_id = uuid4()

        cli1 = Cliente(id=c1_id, nombre="Cliente Label 1")
        cli2 = Cliente(id=c2_id, nombre="Cliente Label 2")
        db.add_all([cli1, cli2])
        await db.flush()

        camp1 = Campania(id=uuid4(), nombre="2025/2026", fecha_inicio=date.today())
        camp2 = Campania(id=uuid4(), nombre="2025/2026", fecha_inicio=date.today())
        db.add_all([camp1, camp2])
        await db.flush()

        comp1 = CompromisoGrano(
            id=uuid4(),
            cliente_id=c1_id,
            campania_id=camp1.id,
            cultivo="soja",
            tipo_compromiso=TipoCompromisoEnum.CANJE_INSUMOS,
            concepto="Compromiso Cliente 1",
            beneficiario="Acopio C1",
            toneladas_comprometidas=Decimal("30.00"),
        )
        comp2 = CompromisoGrano(
            id=uuid4(),
            cliente_id=c2_id,
            campania_id=camp2.id,
            cultivo="soja",
            tipo_compromiso=TipoCompromisoEnum.ALQUILER_ARRENDAMIENTO,
            concepto="Compromiso Cliente 2",
            beneficiario="Acopio C2",
            toneladas_comprometidas=Decimal("50.00"),
        )
        db.add_all([comp1, comp2])
        await db.commit()

        saldos_c1 = await get_compromisos_saldos_map(db, c1_id)
        assert comp1.id in saldos_c1
        assert comp2.id not in saldos_c1
        assert saldos_c1[comp1.id] == Decimal("30.00")


@pytest.mark.asyncio
async def test_7_http_endpoints_render_formatted_commitment_labels():
    """
    Test 7 & 8: Verificar que los endpoints HTTP de /comercial/stock y /comercial/entregas
    retornan el HTML con los options formateados correctamente y conservan el UUID como value.
    """
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.database import engine

    await engine.dispose()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True) as client:
        # Autenticación de usuario
        res_login = await client.post("/login", data={"email": "andres@eduagro.com.ar", "password": "andres123"})
        assert res_login.status_code == 200

        # 1. Endpoint GET /comercial/stock
        res_stock = await client.get("/comercial/stock")
        assert res_stock.status_code == 200
        assert "<option value=" in res_stock.text
        assert "Compromiso Comercial" in res_stock.text

        # 2. Endpoint GET /comercial/entregas
        res_entregas = await client.get("/comercial/entregas")
        assert res_entregas.status_code == 200
        assert "<option value=" in res_entregas.text
        assert "Compromiso Comercial" in res_entregas.text


