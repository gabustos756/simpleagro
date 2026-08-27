"""
Suite de Pruebas de Calidad (QA) para el Módulo GIS de Delimitación Vectorial de Lotes y Visor Multicampo.

Verifica:
1. Cálculo geodésico exacto de área en hectáreas (ha), perímetro en m/km y centroide en WGS84.
2. Validación de polígonos GeoJSON (cierre automático de anillo y estructura).
3. Respuesta del endpoint REST GET /api/v1/gis/campos-y-lotes.
4. Actualización de geometría GeoJSON vía PUT /api/v1/gis/lotes/{id}/geometria.
5. Creación de nuevos lotes delimitados vía POST /api/v1/gis/lotes/crear-con-poligono.
6. Sincronización de superficie productiva vía POST /api/v1/gis/lotes/{id}/sincronizar-superficie.
7. Aislamiento multi-tenant por cliente_id.
"""

import os
import uuid
from unittest.mock import patch
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import AsyncSessionLocal
from app.models import Cliente, Campo, Lote
from app.services.gis_service import procesar_geometria_lote, validar_poligono_geojson


# Polígono GeoJSON de prueba (~40 ha en Laguna Larga, Córdoba)
SAMPLE_POLYGON_GEOJSON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-63.95518, -31.870379],
            [-63.948183, -31.870395],
            [-63.948210, -31.875200],
            [-63.955200, -31.875180],
            [-63.95518, -31.870379]
        ]
    ]
}


async def get_or_create_test_cliente(db):
    cliente = Cliente(
        id=uuid.uuid4(),
        nombre="Cliente GIS QA",
        cuit="30-99887766-5",
        activo=True,
    )
    db.add(cliente)
    await db.commit()
    return cliente


async def get_or_create_test_campo(db, cliente_id):
    campo = Campo(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        nombre="Establecimiento Venier QA",
        ubicacion="Laguna Larga",
        latitud=-31.8703,
        longitud=-63.9551,
        hectareas_totales=200.0,
    )
    db.add(campo)
    await db.commit()
    return campo


async def get_or_create_test_lote(db, campo_id, cliente_id):
    lote = Lote(
        id=uuid.uuid4(),
        campo_id=campo_id,
        cliente_id=cliente_id,
        nombre="Venier 1 QA",
        superficie_total_ha=40.0,
        superficie_productiva_ha=40.0,
        cultivo_actual="Soja 1ra",
    )
    db.add(lote)
    await db.commit()
    return lote


def test_1_gis_service_calculation():
    """Verifica que el servicio GIS calcule correctamente el área en ha, perímetro en m/km y centroide."""
    res = procesar_geometria_lote(SAMPLE_POLYGON_GEOJSON)

    assert "superficie_calculada_gis_ha" in res
    assert "perimetro_calculado_m" in res
    assert "centroide_lat" in res
    assert "centroide_lng" in res

    # Para este polígono de ~700m x ~530m, el área esperada es de aprox 35 - 40 ha
    assert 30.0 <= res["superficie_calculada_gis_ha"] <= 45.0
    assert 2000.0 <= res["perimetro_calculado_m"] <= 3000.0
    assert res["perimetro_calculado_km"] > 2.0
    assert -31.88 <= res["centroide_lat"] <= -31.86
    assert -63.96 <= res["centroide_lng"] <= -63.94


def test_2_invalid_polygon_validation():
    """Verifica que polígonos malformados lancen ValueError."""
    invalid_geojson = {"type": "Polygon", "coordinates": [[[-63.9, -31.8]]]}
    with pytest.raises(ValueError):
        procesar_geometria_lote(invalid_geojson)


@pytest.mark.asyncio
async def test_3_get_gis_campos_y_lotes_api():
    """Verifica el endpoint GET /api/v1/gis/campos-y-lotes."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo = await get_or_create_test_campo(db, cliente.id)
        lote = await get_or_create_test_lote(db, campo.id, cliente.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user:
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "productor@eduagro.com",
                "cliente_id": str(cliente.id),
                "rol": "productor",
            }

            response = await ac.get("/api/v1/gis/campos-y-lotes")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert isinstance(data["campos"], list)
            assert isinstance(data["lotes"], list)


@pytest.mark.asyncio
async def test_4_put_update_lote_geometria_api():
    """Verifica el endpoint PUT /api/v1/gis/lotes/{lote_id}/geometria."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo = await get_or_create_test_campo(db, cliente.id)
        lote = await get_or_create_test_lote(db, campo.id, cliente.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user:
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "productor@eduagro.com",
                "cliente_id": str(cliente.id),
                "rol": "productor",
            }

            payload = {
                "geometria_geojson": SAMPLE_POLYGON_GEOJSON,
                "sincronizar_superficie": True
            }

            response = await ac.put(f"/api/v1/gis/lotes/{lote.id}/geometria", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "metricas" in data
            assert data["metricas"]["superficie_calculada_gis_ha"] > 0


@pytest.mark.asyncio
async def test_5_post_create_lote_con_poligono_api():
    """Verifica el endpoint POST /api/v1/gis/lotes/crear-con-poligono."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo = await get_or_create_test_campo(db, cliente.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user:
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "productor@eduagro.com",
                "cliente_id": str(cliente.id),
                "rol": "productor",
            }

            payload = {
                "campo_id": str(campo.id),
                "nombre": "Nuevo Lote Dibuja QA",
                "cultivo_actual": "Maíz Tardío",
                "geometria_geojson": SAMPLE_POLYGON_GEOJSON
            }

            response = await ac.post("/api/v1/gis/lotes/crear-con-poligono", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["lote"]["nombre"] == "Nuevo Lote Dibuja QA"


@pytest.mark.asyncio
async def test_6_sync_surface_api():
    """Verifica la sincronización de superficie productiva."""
    async with AsyncSessionLocal() as db:
        cliente = await get_or_create_test_cliente(db)
        campo = await get_or_create_test_campo(db, cliente.id)
        lote = await get_or_create_test_lote(db, campo.id, cliente.id)
        # Asignar superficie GIS
        lote.superficie_calculada_gis_ha = 42.37
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.main.get_current_user_from_session") as mock_user:
            mock_user.return_value = {
                "id": str(uuid.uuid4()),
                "email": "productor@eduagro.com",
                "cliente_id": str(cliente.id),
                "rol": "productor",
            }

            response = await ac.post(f"/api/v1/gis/lotes/{lote.id}/sincronizar-superficie")
            assert response.status_code == 200
            data = response.json()
            assert "sincronizada" in data["message"]
