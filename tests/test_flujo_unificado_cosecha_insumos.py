"""
tests/test_flujo_unificado_cosecha_insumos.py

Pruebas de integración para verificar el flujo unificado:
1. Cosecha en lote -> Creación de Silo Bolsa y Partida de Grano automática.
2. Actualización de métricas de lote y estado productivo a COSECHADO.
3. Descuento automático de stock de insumos en depósitos con costo PPP.
"""

from decimal import Decimal
import uuid
from datetime import date, datetime, timezone
import pytest
from sqlalchemy import select
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import AsyncSessionLocal
from app.models import (
    Cliente,
    Campo,
    Lote,
    Campania,
    Usuario,
    StorageLocation,
    StockPartida,
    LaborCampo,
    Insumo,
    InsumoSaldoUbicacion,
    InsumoMovimiento,
)
from app.enums import (
    TipoLabor,
    EstadoProductivoLoteEnum,
    CategoriaInsumoEnum,
    UnidadMedidaInsumoEnum,
    TipoMovimientoInsumoEnum,
)
from app.services.stock_service import crear_partida_grano_desde_cosecha, get_stock_partida_commercial_balance
from app.services.insumos_service import registrar_consumo_labor


@pytest.mark.asyncio
async def test_crear_partida_grano_desde_cosecha_unitario():
    """Verifica la función crear_partida_grano_desde_cosecha con validación de movimientos y balance."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()
        assert cliente is not None

        res_campo = await db.execute(select(Campo).where(Campo.cliente_id == cliente.id).limit(1))
        campo = res_campo.scalars().first()

        res_lote = await db.execute(select(Lote).where(Lote.cliente_id == cliente.id).limit(1))
        lote = res_lote.scalars().first()

        res_camp = await db.execute(select(Campania).limit(1))
        campania = res_camp.scalars().first()

        # 1. Crear StorageLocation (Silo Bolsa de prueba)
        loc = StorageLocation(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            campo_id=campo.id if campo else None,
            nombre=f"Silobolsa Test {uuid.uuid4().hex[:4]}",
            tipo="silobolsa",
            capacidad_nominal_tn=Decimal("300.00"),
            estado="activo",
        )
        db.add(loc)
        await db.commit()

        # 2. Invocar creación automática desde cosecha
        partida = await crear_partida_grano_desde_cosecha(
            db=db,
            cliente_id=cliente.id,
            storage_location_id=loc.id,
            cultivo="soja",
            cantidad_tn=Decimal("150.00"),
            lote_id=lote.id if lote else None,
            campo_id=campo.id if campo else None,
            campania_id=campania.id if campania else None,
            fecha_cosecha=date.today(),
            humedad_pct=Decimal("13.5"),
            observaciones="Cosecha de prueba unitaria",
        )
        await db.commit()

        assert partida.id is not None
        assert partida.cultivo == "soja"
        assert partida.cantidad_inicial_kg == Decimal("150000.00")
        assert partida.storage_location_id == loc.id

        # 3. Verificar balance comercial
        bal = await get_stock_partida_commercial_balance(db, cliente.id, partida.id)
        assert bal["stock_fisico_tn"] == Decimal("150.00")
        assert bal["stock_disponible_tn"] == Decimal("150.00")


@pytest.mark.asyncio
async def test_descuento_insumo_en_labor_campo():
    """Verifica que registrar_consumo_labor descuenta stock físico del galpón y calcula costos PPP."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()
        assert cliente is not None

        res_lote = await db.execute(select(Lote).where(Lote.cliente_id == cliente.id).limit(1))
        lote = res_lote.scalars().first()

        res_camp = await db.execute(select(Campania).limit(1))
        campania = res_camp.scalars().first()

        # Ubicación / Galpón de Insumos
        galpon = StorageLocation(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Galpón Test {uuid.uuid4().hex[:4]}",
            tipo="galpon",
            estado="activo",
        )
        db.add(galpon)
        await db.flush()

        # Insumo
        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Insumo Test {uuid.uuid4().hex[:4]}",
            categoria=CategoriaInsumoEnum.FITOSANITARIO,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
            activo=True,
        )
        db.add(insumo)
        await db.flush()

        # Saldo inicial en galpón: 500 Litros a USD 8.00 / Litro
        saldo = InsumoSaldoUbicacion(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=galpon.id,
            cantidad_disponible=Decimal("500.0000"),
            costo_ppp_usd=Decimal("8.0000"),
            costo_ppp_ars=Decimal("8000.0000"),
        )
        db.add(saldo)

        # Labor de Pulverización
        labor = LaborCampo(
            id=uuid.uuid4(),
            lote_id=lote.id,
            campania_id=campania.id if campania else uuid.uuid4(),
            tipo_labor=TipoLabor.PULVERIZACION,
            fecha=datetime.now(timezone.utc),
            superficie_afectada_ha=50.0,
            insumos_utilizados=[{"nombre": insumo.nombre, "dosis": 3.0, "unidad": "lt/ha"}],
        )
        db.add(labor)
        await db.commit()

        # Consumir 150 Litros (3 L/ha * 50 ha)
        mov = await registrar_consumo_labor(
            db=db,
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=galpon.id,
            labor_campo_id=labor.id,
            fecha_consumo=datetime.now(timezone.utc),
            cantidad_real=Decimal("150.0000"),
            clave_idempotencia=f"TEST-CONS-{labor.id}",
        )
        await db.commit()

        assert mov is not None
        assert mov.tipo_movimiento == TipoMovimientoInsumoEnum.CONSUMO_LABOR
        assert mov.costo_unitario_usd == Decimal("8.0000")
        assert mov.costo_total_usd == Decimal("1200.0000")

        # Verificar saldo remanente (500 - 150 = 350 Litros)
        await db.refresh(saldo)
        assert saldo.cantidad_disponible == Decimal("350.0000")


@pytest.mark.asyncio
async def test_endpoint_labor_rapida_cosecha_con_nuevo_silobolsa():
    """Verifica que el endpoint HTTP registre la cosecha, cree el silobolsa y la partida de grano."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

        res_l = await db.execute(select(Lote).where(Lote.cliente_id == cliente.id).limit(1))
        lote = res_l.scalars().first()
        assert lote is not None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        cookies = {"session_user_id": str(usuario.id)} if usuario else {}
        form_data = {
            "tipo_labor": "cosecha",
            "fecha": "2026-09-07",
            "superficie_afectada_ha": "57.0",
            "rendimiento_qq_ha": "38.5",
            "total_cosechado_qq": "2194.5",
            "humedad_porcentaje": "13.0",
            "destino_grano_tipo": "nuevo_silobolsa",
            "nuevo_silobolsa_nombre": "Silo Bolsa Cosecha Test Endpoint",
            "notas": "Prueba de integración cosecha a silo",
        }

        resp = await ac.post(
            f"/productivo/lotes/{lote.id}/labores/rapida",
            data=form_data,
            cookies=cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "historial" in resp.headers["location"]

    # Verificar en base de datos que se creó la partida y se actualizó el lote
    async with AsyncSessionLocal() as db:
        lote_db = await db.get(Lote, lote.id)
        assert lote_db is not None
        assert lote_db.qq_ha_real == 38.5
        assert lote_db.produccion_total_qq == 2194.5
        assert (lote_db.metadatos_agronomicos or {}).get("estado_productivo") == EstadoProductivoLoteEnum.RECIEN_COSECHADO.value

        # Verificar partida de grano creada
        res_p = await db.execute(
            select(StockPartida).where(StockPartida.lote_id == lote.id).order_by(StockPartida.fecha_creacion.desc()).limit(1)
        )
        partida_creada = res_p.scalars().first()
        assert partida_creada is not None
        assert partida_creada.cantidad_inicial_kg == Decimal("219450.00")
