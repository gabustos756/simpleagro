"""
Pruebas de Integración y Seguridad para el Rol SuperAdmin, Centro de Métricas de Clientes y Generador de Placas de Marketing (Canva Rural).
"""

import pytest
from sqlalchemy import select
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import AsyncSessionLocal
from app.models import Cliente, Usuario
from app.enums import RolUsuario
from app.auth import hash_password


@pytest.mark.asyncio
async def test_1_superadmin_user_seed_and_role_integrity():
    """Verifica que el usuario SuperAdmin exista con rol SUPERADMIN."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Usuario).where(Usuario.email == "superadmin@eduagro.com.ar"))
        sa_user = res.scalars().first()
        if not sa_user:
            sa_user = Usuario(
                nombre="SuperAdmin EduAgro",
                email="superadmin@eduagro.com.ar",
                password_hash=hash_password("admin123"),
                rol=RolUsuario.SUPERADMIN,
                cliente_id=None,
            )
            db.add(sa_user)
            await db.commit()
            await db.refresh(sa_user)

        assert sa_user is not None
        assert sa_user.rol == RolUsuario.SUPERADMIN


@pytest.mark.asyncio
async def test_2_superadmin_login_redirects_to_superadmin():
    """Verifica que el inicio de sesión del SuperAdmin redirija a /superadmin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post(
            "/login",
            data={"email": "superadmin@eduagro.com.ar", "password": "admin123"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert res.headers["location"] == "/superadmin"


@pytest.mark.asyncio
async def test_3_matteuda_user_login_redirects_to_portal_not_superadmin():
    """Verifica que los usuarios regulares (Familia Matteuda) no sean redirigidos a /superadmin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post(
            "/login",
            data={"email": "andres@eduagro.com.ar", "password": "andres123"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert res.headers["location"] == "/portal"


@pytest.mark.asyncio
async def test_4_regular_user_cannot_access_superadmin():
    """Verifica que un usuario regular sea bloqueado/redirigido al intentar ingresar a /superadmin."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Usuario).where(Usuario.email == "andres@eduagro.com.ar"))
        andres = res.scalars().first()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        cookies = {"session_user_id": str(andres.id)} if andres else {}
        res = await ac.get("/superadmin", cookies=cookies, follow_redirects=False)
        assert res.status_code == 303
        assert "/login" in res.headers["location"]


@pytest.mark.asyncio
async def test_5_superadmin_can_access_dashboard_and_canva_rural():
    """Verifica que el SuperAdmin acceda a /superadmin y /superadmin/marketing con métricas y herramientas."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Usuario).where(Usuario.email == "superadmin@eduagro.com.ar"))
        sa = res.scalars().first()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        cookies = {"session_user_id": str(sa.id)}
        res = await ac.get("/superadmin", cookies=cookies)
        assert res.status_code == 200
        assert "Consola SuperAdmin" in res.text
        assert "Familia Matteuda" in res.text
        assert "Canva Rural" in res.text
        assert "Descargar Placa HD" in res.text

        # Acceso a pestaña de marketing directamente
        res_mkt = await ac.get("/superadmin/marketing", cookies=cookies)
        assert res_mkt.status_code == 200
        assert "Canva Rural" in res_mkt.text


@pytest.mark.asyncio
async def test_6_superadmin_impersonate_and_exit_support_mode():
    """Verifica el flujo de Modo Soporte (impersonar cliente y retornar a superadmin)."""
    async with AsyncSessionLocal() as db:
        res_sa = await db.execute(select(Usuario).where(Usuario.email == "superadmin@eduagro.com.ar"))
        sa = res_sa.scalars().first()
        res_cli = await db.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        cookies = {"session_user_id": str(sa.id)}

        # 1. Impersonar cliente
        res_imp = await ac.post(f"/superadmin/impersonar/{cliente.id}", cookies=cookies, follow_redirects=False)
        assert res_imp.status_code == 303
        assert res_imp.headers["location"] == "/portal"

        # 2. Salir de impersonación
        res_exit = await ac.get("/superadmin/salir-impersonacion", cookies=cookies, follow_redirects=False)
        assert res_exit.status_code == 303
        assert res_exit.headers["location"] == "/superadmin"
