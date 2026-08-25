"""
Pruebas automatizadas para eliminación de Contratos y Compromisos de Venta
y filtrado de cultivos activos (Soja y Maíz).
"""

import pytest
from decimal import Decimal
from datetime import date
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.database import engine, get_db, AsyncSessionLocal
from app.models import ContratoVentaGrano, CompromisoGrano, Cliente, Campania, Usuario
from app.enums import TipoPrecioEnum, TipoCompromisoEnum, RolUsuario


@pytest.mark.asyncio
async def test_delete_contrato_venta_success():
    """
    Verifica que el usuario pueda eliminar un contrato de venta existente.
    """
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_camp = await session.execute(select(Campania).where(Campania.cliente_id == cliente.id).limit(1))
        campania = res_camp.scalars().first()
        res_u = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        user = res_u.scalars().first()

        contrato = ContratoVentaGrano(
            cliente_id=cliente.id,
            campania_id=campania.id,
            cultivo="soja",
            comprador_acopio="Acopio Test Eliminar",
            numero_contrato="TEST-DEL-001",
            toneladas=Decimal("150.00"),
            tipo_precio=TipoPrecioEnum.FIJO,
            precio_usd_tn=Decimal("290.00"),
            fecha_contrato=date.today(),
        )
        session.add(contrato)
        await session.commit()
        await session.refresh(contrato)
        contrato_id = str(contrato.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/comercial/contratos/{contrato_id}/eliminar",
            data={"cultivo": "soja"},
            headers={"x-user-id": str(user.id)},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/comercial/contratos" in response.headers["location"]

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(ContratoVentaGrano).where(ContratoVentaGrano.id == contrato.id))
        deleted_c = res.scalars().first()
        assert deleted_c is None


@pytest.mark.asyncio
async def test_delete_compromiso_grano_success():
    """
    Verifica que el usuario pueda eliminar un compromiso de grano existente.
    """
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_camp = await session.execute(select(Campania).where(Campania.cliente_id == cliente.id).limit(1))
        campania = res_camp.scalars().first()
        res_u = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        user = res_u.scalars().first()

        compromiso = CompromisoGrano(
            cliente_id=cliente.id,
            campania_id=campania.id,
            cultivo="maiz",
            tipo_compromiso=TipoCompromisoEnum.CANJE_INSUMOS,
            concepto="Canje Semillas Test Eliminar",
            beneficiario="Proveedor Test",
            toneladas_comprometidas=Decimal("80.00"),
            cumplido=False,
        )
        session.add(compromiso)
        await session.commit()
        await session.refresh(compromiso)
        compromiso_id = str(compromiso.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/comercial/compromisos/{compromiso_id}/eliminar",
            data={"cultivo": "maiz"},
            headers={"x-user-id": str(user.id)},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/comercial/contratos" in response.headers["location"]

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(CompromisoGrano).where(CompromisoGrano.id == compromiso.id))
        deleted_k = res.scalars().first()
        assert deleted_k is None
