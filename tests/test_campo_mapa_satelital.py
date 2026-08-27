"""
Suite de Pruebas de Calidad (QA) para la vista Satelital "Ver desde arriba" (EduAgro MVP).

Verifica:
1. HTTP 200 OK y renderizado completo para un campo y cliente válidos.
2. Aislamiento multi-tenant por cliente_id (HTTP 403 / 404 para campo de otro cliente).
3. Acceso de lectura para roles autorizados (admin, productor, operario_campo, administrador_finanzas).
4. Degradación amigable sin error 500 cuando falta GOOGLE_MAPS_API_KEY (HTTP 200).
5. Degradación amigable sin error 500 cuando el Campo no posee latitud/longitud (HTTP 200).
6. Manejo seguro de UUID inválido o campo inexistente (HTTP 404 sin 500).
7. Ausencia de modificaciones automáticas o inserción de datos ficticios en la BD.
"""

import os
import uuid
from unittest.mock import patch
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func

from app.main import app
from app.database import AsyncSessionLocal
from app.models import Cliente, Usuario, Campo, Lote
from app.enums import RolUsuario
from app.seed import DEMO_CLIENTE, get_uuid


async def get_or_create_test_cliente(db):
    """Obtiene o crea un cliente válido en la base de datos."""
    res_c = await db.execute(select(Cliente).limit(1))
    cliente = res_c.scalars().first()
    if not cliente:
        cliente = Cliente(
            id=get_uuid(DEMO_CLIENTE["id"]),
            nombre=DEMO_CLIENTE["nombre"],
            cuit=DEMO_CLIENTE["cuit"],
            ubicacion=DEMO_CLIENTE["ubicacion"],
            activo=True,
        )
        db.add(cliente)
        await db.commit()
    return cliente


async def get_or_create_test_campo(db, cliente_id, latitud=-31.7766, longitud=-63.8011):
    """Obtiene o crea un campo para el cliente especificado."""
    campo = Campo(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        nombre="Campo Test QA",
        ubicacion="Laguna Larga, Córdoba",
        localidad_referencia="Laguna Larga, Córdoba",
        latitud=latitud,
        longitud=longitud,
        hectareas_totales=300.0,
    )
    db.add(campo)
    await db.commit()
    return campo


@pytest.mark.asyncio
async def test_1_get_campo_mapa_valid_renders_ok():
    """Verifica que /campos/{campo_id}/mapa responda HTTP 200 OK con plantilla satelital para un campo válido."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo = await get_or_create_test_campo(db, cliente.id, latitud=-31.7766, longitud=-63.8011)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user, \
             patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "AIzaSyTestApiKey123"}):
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "productor@eduagro.com",
                "cliente_id": str(cliente.id),
                "rol": "productor",
            }

            response = await ac.get(f"/campos/{campo.id}/mapa")
            assert response.status_code == 200
            assert "Vista Satelital desde Arriba" in response.text
            assert campo.nombre in response.text
            assert "maps.googleapis.com/maps/api/js" in response.text
            assert "initMap" in response.text


@pytest.mark.asyncio
async def test_2_get_campo_mapa_tenant_isolation_returns_403_or_404():
    """Verifica que acceder al mapa de un campo perteneciente a otro cliente_id retorne 403 Forbidden o 404 Not Found."""
    async with AsyncSessionLocal() as db:
        cliente_a = Cliente(id=uuid.uuid4(), nombre="Cliente A QA", cuit="30-11111111-1")
        cliente_b = Cliente(id=uuid.uuid4(), nombre="Cliente B QA", cuit="30-22222222-2")
        db.add_all([cliente_a, cliente_b])
        await db.commit()

        campo_b = await get_or_create_test_campo(db, cliente_b.id, latitud=-31.4201, longitud=-64.1888)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user:
            # Usuario pertenece al cliente A
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "user_a@eduagro.com",
                "cliente_id": str(cliente_a.id),
                "rol": "admin",
            }

            response = await ac.get(f"/campos/{campo_b.id}/mapa")
            assert response.status_code in (403, 404), f"Esperado 403 o 404 pero se obtuvo {response.status_code}"


@pytest.mark.asyncio
async def test_3_get_campo_mapa_authorized_roles_access():
    """Verifica que todos los roles autorizados (admin, productor, operario_campo, administrador_finanzas) tengan acceso de lectura."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo = await get_or_create_test_campo(db, cliente.id)

    roles_to_test = [
        RolUsuario.ADMIN,
        RolUsuario.PRODUCTOR,
        RolUsuario.OPERARIO_CAMPO,
        RolUsuario.ADMINISTRADOR_FINANZAS,
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for rol in roles_to_test:
            with patch("app.main.get_current_user_from_session") as mock_user:
                mock_user.return_value = {
                    "id": str(uuid.uuid4()),
                    "email": f"test_{rol.value}@eduagro.com",
                    "cliente_id": str(cliente.id),
                    "rol": rol,
                }

                response = await ac.get(f"/campos/{campo.id}/mapa")
                assert response.status_code == 200, f"Rol {rol} falló con status {response.status_code}"


@pytest.mark.asyncio
async def test_4_get_campo_mapa_missing_api_key_renders_friendly_notice():
    """Verifica que sin GOOGLE_MAPS_API_KEY se devuelva HTTP 200 con un aviso amigable y sin error 500."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo = await get_or_create_test_campo(db, cliente.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user, \
             patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "", "GOOGLE_API_KEY": ""}):
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "admin@eduagro.com",
                "cliente_id": str(cliente.id),
                "rol": "admin",
            }

            response = await ac.get(f"/campos/{campo.id}/mapa")
            assert response.status_code == 200
            assert "La vista satelital no está configurada" in response.text
            assert "GOOGLE_MAPS_API_KEY" in response.text


@pytest.mark.asyncio
async def test_5_get_campo_mapa_missing_coordinates_renders_friendly_notice():
    """Verifica que un campo sin coordenadas (latitud/longitud en None) devuelva HTTP 200 con aviso amigable."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo_sin_coords = await get_or_create_test_campo(db, cliente.id, latitud=None, longitud=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user:
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "admin@eduagro.com",
                "cliente_id": str(cliente.id),
                "rol": "admin",
            }

            response = await ac.get(f"/campos/{campo_sin_coords.id}/mapa")
            assert response.status_code == 200
            assert "Este campo todavía no tiene ubicación de referencia" in response.text


@pytest.mark.asyncio
async def test_6_get_campo_mapa_invalid_uuid_returns_404_no_500():
    """Verifica que una cadena de UUID inválida retorne HTTP 404 y no cause un error interno 500."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user:
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "admin@eduagro.com",
                "cliente_id": str(uuid.uuid4()),
                "rol": "admin",
            }

            response = await ac.get("/campos/codigo-uuid-invalido-123/mapa")
            assert response.status_code == 404
            assert "Campo no encontrado" in response.text or "inválido" in response.text


@pytest.mark.asyncio
async def test_7_no_mock_data_or_unintended_database_modifications():
    """Verifica que el consumo de los endpoints de mapa no altere ni inserte registros involuntarios en la BD."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo = await get_or_create_test_campo(db, cliente.id)

        count_campos_before = (await db.execute(select(func.count(Campo.id)))).scalar()
        count_lotes_before = (await db.execute(select(func.count(Lote.id)))).scalar()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user:
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "admin@eduagro.com",
                "cliente_id": str(cliente.id),
                "rol": "admin",
            }

            await ac.get(f"/campos/{campo.id}/mapa")

    async with AsyncSessionLocal() as db:
        count_campos_after = (await db.execute(select(func.count(Campo.id)))).scalar()
        count_lotes_after = (await db.execute(select(func.count(Lote.id)))).scalar()

    assert count_campos_before == count_campos_after
    assert count_lotes_before == count_lotes_after
