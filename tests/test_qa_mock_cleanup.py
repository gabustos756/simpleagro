from __future__ import annotations

"""
Suite de Pruebas Unitarias e Integración para el Script de Limpieza Segura de Datos QA-MOCK (Parte B).
Verifica ejecuciones dry-run vs real delete, rechazos de entornos/prefijos no permitidos,
validación de frase de confirmación, protección de datos reales, aislamiento por vinculación y generación de reportes.
"""

from decimal import Decimal
from datetime import date
from uuid import uuid4
from contextlib import asynccontextmanager
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import DATABASE_URL
from app.models import (
    Cliente,
    StorageLocation,
    StockPartida,
    StockMovement,
    CompromisoGrano,
    GrainDelivery,
    GrainWaybill,
    StockDeliveryAllocation,
)
from scripts.cleanup_qa_mock_data import run_qa_mock_cleanup, mask_db_url, is_local_db_host


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


def test_1_mask_db_url_and_local_host_validation():
    """
    Test 1: Mascarado de passwords y validación de host local.
    """
    url_pass = "postgresql+asyncpg://postgres:secretpassword123@localhost:5432/eduagro"
    masked = mask_db_url(url_pass)
    assert "secretpassword123" not in masked
    assert "******" in masked
    assert is_local_db_host(url_pass) is True


@pytest.mark.asyncio
async def test_2_rejection_of_non_local_environment():
    """
    Test 2: Rechazar ejecuciones donde --environment no sea 'local'.
    """
    with pytest.raises(PermissionError, match="Entorno denegado"):
        await run_qa_mock_cleanup(
            environment="production",
            prefix="QA-MOCK-",
            dry_run=True,
            confirm_delete=False,
            confirm_phrase="",
        )


@pytest.mark.asyncio
async def test_3_rejection_of_invalid_prefix():
    """
    Test 3: Rechazar ejecuciones donde --prefix no sea exactamente 'QA-MOCK-'.
    """
    with pytest.raises(PermissionError, match="Prefijo denegado"):
        await run_qa_mock_cleanup(
            environment="local",
            prefix="INVALID-",
            dry_run=True,
            confirm_delete=False,
            confirm_phrase="",
        )


@pytest.mark.asyncio
async def test_4_rejection_of_missing_confirm_phrase():
    """
    Test 4: Rechazar borrado real sin la frase exacta DELETE_QA_MOCK_LOCAL.
    """
    with pytest.raises(ValueError, match="Confirmación denegada"):
        await run_qa_mock_cleanup(
            environment="local",
            prefix="QA-MOCK-",
            dry_run=False,
            confirm_delete=True,
            confirm_phrase="WRONG_PHRASE",
        )


@pytest.mark.asyncio
async def test_5_dry_run_preserves_qa_records_without_deletion():
    """
    Test 5: El modo dry-run identifica registros QA-MOCK- pero no modifica la base de datos.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Cleanup Test")
        db.add(cli)
        await db.flush()

        loc_qa = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="silobolsa", nombre="QA-MOCK-Silobolsa-DryRun", capacidad_nominal_tn=Decimal("50.0"))
        db.add(loc_qa)
        await db.commit()

        # Ejecutar en modo dry-run
        summary = await run_qa_mock_cleanup(
            environment="local",
            prefix="QA-MOCK-",
            dry_run=True,
            confirm_delete=False,
            confirm_phrase="",
        )

        assert summary["counts"]["StorageLocation"] >= 1
        assert str(loc_qa.id) in summary["affected_ids"]["StorageLocation"]

        # Verificar que la ubicación sigue existiendo en BD
        stmt = select(StorageLocation).where(StorageLocation.id == loc_qa.id)
        res = (await db.execute(stmt)).scalar_one_or_none()
        assert res is not None


@pytest.mark.asyncio
async def test_6_real_delete_removes_qa_records_and_spares_real_data():
    """
    Test 6: Borrado real elimina únicamente registros QA-MOCK- y respeta registros reales.
    """
    async with get_test_db() as db:
        c_id = uuid4()
        cli = Cliente(id=c_id, nombre="Cliente Real Delete Test")
        db.add(cli)

        loc_qa = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="silobolsa", nombre="QA-MOCK-Silobolsa-RealDelete", capacidad_nominal_tn=Decimal("50.0"))
        loc_real = StorageLocation(id=uuid4(), cliente_id=c_id, tipo="silo", nombre="Silo Real Produccion", capacidad_nominal_tn=Decimal("100.0"))
        db.add_all([loc_qa, loc_real])
        await db.commit()

        # Ejecutar borrado real
        summary = await run_qa_mock_cleanup(
            environment="local",
            prefix="QA-MOCK-",
            dry_run=False,
            confirm_delete=True,
            confirm_phrase="DELETE_QA_MOCK_LOCAL",
        )

        # Verificar que la ubicación QA fue eliminada y la real preservada
        stmt_qa = select(StorageLocation).where(StorageLocation.id == loc_qa.id)
        res_qa = (await db.execute(stmt_qa)).scalar_one_or_none()
        assert res_qa is None

        stmt_real = select(StorageLocation).where(StorageLocation.id == loc_real.id)
        res_real = (await db.execute(stmt_real)).scalar_one_or_none()
        assert res_real is not None
