"""
Pruebas de modelos, constraints de base de datos e integridad relacional del módulo de Insumos y Abastecimiento.
"""

from decimal import Decimal
from datetime import date, datetime
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal
from app.enums import (
    CategoriaInsumoEnum,
    UnidadMedidaInsumoEnum,
    TipoMovimientoInsumoEnum,
    MonedaEnum,
)
from app.models import (
    Cliente,
    StorageLocation,
    Insumo,
    InsumoLote,
    InsumoSaldoUbicacion,
    InsumoLoteSaldoUbicacion,
    InsumoMovimiento,
)


@pytest.mark.asyncio
async def test_1_create_insumo_and_lote_integrity():
    """Verifica la creación básica de un insumo y lote con constraints de unicidad."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Glifosato Test {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.FITOSANITARIO,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
            principio_activo_formula="Glifosato 66.2%",
            punto_pedido_minimo=Decimal("50.0000"),
        )
        db.add(insumo)
        await db.commit()

        lote = InsumoLote(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            numero_lote="LOTE-2026-001",
            fecha_vencimiento=date(2027, 12, 31),
            proveedor_origen="Bayer CropScience",
        )
        db.add(lote)
        await db.commit()

        # Verificar consulta
        res_insumo = await db.get(Insumo, insumo.id)
        assert res_insumo is not None
        assert res_insumo.categoria == CategoriaInsumoEnum.FITOSANITARIO


@pytest.mark.asyncio
async def test_2_insumo_saldo_no_negativo_constraint():
    """Verifica que CheckConstraint('cantidad_disponible >= 0') prevenga saldos negativos en DB."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Semilla Test {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.SEMILLA,
            unidad_medida=UnidadMedidaInsumoEnum.BOLSA,
        )
        db.add(insumo)
        await db.flush()

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()
        if not location:
            location = StorageLocation(
                id=uuid.uuid4(),
                cliente_id=cliente.id,
                nombre="Galpón Central Test",
                tipo="galpon",
            )
            db.add(location)
            await db.flush()

        saldo_negativo = InsumoSaldoUbicacion(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            storage_location_id=location.id,
            cantidad_disponible=Decimal("-10.0000"),
        )
        db.add(saldo_negativo)

        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.asyncio
async def test_3_idempotencia_compuesta_movimiento_constraint():
    """Verifica que (cliente_id, tipo_movimiento, clave_idempotencia) rechace duplicados."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Gasoil Test {uuid.uuid4().hex[:6]}",
            categoria=CategoriaInsumoEnum.COMBUSTIBLE,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
        )
        db.add(insumo)
        await db.flush()

        clave = f"idem_mov_{uuid.uuid4().hex[:8]}"

        mov1 = InsumoMovimiento(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            tipo_movimiento=TipoMovimientoInsumoEnum.COMPRA_INGRESO,
            fecha_movimiento=datetime.now(),
            cantidad=Decimal("100.0000"),
            moneda_origen=MonedaEnum.USD,
            cotizacion_usd_ars=Decimal("1000.0000"),
            costo_unitario_usd=Decimal("1.5000"),
            costo_total_usd=Decimal("150.0000"),
            costo_unitario_ars=Decimal("1500.0000"),
            costo_total_ars=Decimal("150000.0000"),
            clave_idempotencia=clave,
        )
        db.add(mov1)
        await db.commit()

        mov2 = InsumoMovimiento(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            insumo_id=insumo.id,
            tipo_movimiento=TipoMovimientoInsumoEnum.COMPRA_INGRESO,
            fecha_movimiento=datetime.now(),
            cantidad=Decimal("100.0000"),
            clave_idempotencia=clave,
        )
        db.add(mov2)

        with pytest.raises(IntegrityError):
            await db.commit()
