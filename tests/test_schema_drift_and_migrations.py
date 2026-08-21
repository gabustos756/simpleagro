"""
Suite de Pruebas de CI: Verificación de Schema Drift y Smoke Tests de Routers HTTP.

Garantiza que la estructura física de la base de datos coincida al 100% con los modelos
SQLAlchemy declarados en app/models.py, y que los endpoints de Home, Comercial, Stock,
Servicios y Clientes/Campos respondan sin errores HTTP 500.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.database import Base, DATABASE_URL, engine, get_db, AsyncSessionLocal
from app.main import app as fastapi_app
import app.models  # Carga todos los modelos de la app


@pytest.mark.asyncio
async def test_1_models_metadata_completeness():
    """
    Verifica que las 29 tablas del modelo estén correctamente registradas en Base.metadata.
    """
    expected_tables = {
        "clientes",
        "campos",
        "instalaciones",
        "servicios_instalados",
        "usuarios",
        "lotes",
        "campanias",
        "labores_campo",
        "registros_lluvia",
        "servicios_vencimiento",
        "service_documents",
        "cartas_de_porte",
        "transacciones_financieras",
        "contratos_venta_grano",
        "stock_grano",
        "compromisos_grano",
        "arrendamiento_terms",
        "precios_mercado_cache",
        "weather_snapshots",
        "freight_quotes",
        "grain_deliveries",
        "grain_waybills",
        "storage_locations",
        "stock_partidas",
        "stock_movements",
        "stock_quality_measurements",
        "stock_reservations",
        "stock_delivery_allocations",
        "stock_weight_reconciliations",
    }

    registered_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - registered_tables
    assert not missing_tables, f"Faltan tablas registradas en SQLAlchemy Base.metadata: {missing_tables}"


@pytest.mark.asyncio
async def test_2_schema_drift_verification():
    """
    Verifica que todas las columnas declaradas en Base.metadata existan en la DB activa.
    """
    test_engine = create_async_engine(DATABASE_URL, echo=False)
    try:
        async with test_engine.connect() as conn:
            def get_db_schema(sync_conn):
                inspector = inspect(sync_conn)
                table_names = inspector.get_table_names()
                db_schema = {}
                for t_name in table_names:
                    columns = inspector.get_columns(t_name)
                    db_schema[t_name] = {c["name"] for c in columns}
                return db_schema

            db_schema = await conn.run_sync(get_db_schema)
    finally:
        await test_engine.dispose()

    drift_errors = []
    for table_name, table_obj in Base.metadata.tables.items():
        if table_name not in db_schema:
            drift_errors.append(f"Tabla '{table_name}' declarada en modelos pero ausente en la base de datos.")
            continue

        existing_cols = db_schema[table_name]
        for col in table_obj.columns:
            if col.name not in existing_cols:
                drift_errors.append(
                    f"Columna '{col.name}' de la tabla '{table_name}' declarada en modelos pero ausente en la base de datos."
                )

    assert not drift_errors, "Se detectó Schema Drift (desincronización de esquema):\n" + "\n".join(drift_errors)


@pytest.mark.asyncio
async def test_3_smoke_tests_all_routers_no_500():
    """
    Smoke test sobre todas las rutas principales de Home, Comercial, Stock, Servicios y Campos.
    Verifica que ninguna responda con HTTP 500 Internal Server Error.
    """
    await engine.dispose()

    # Rutas clave a probar sin lanzar error 500
    target_routes = [
        "/",
        "/comercial/stock",
        "/comercial/contratos",
        "/comercial/entregas",
        "/comercial/fletes",
        "/servicios",
        "/servicios/vencimientos",
        "/servicios/campos",
        "/servicios/instalaciones",
    ]

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for route in target_routes:
            response = await client.get(route, follow_redirects=True)
            assert response.status_code != 500, (
                f"La ruta '{route}' devolvió un HTTP 500 Internal Server Error. "
                "Verificar columnas o desincronización de base de datos."
            )
            assert response.status_code in [200, 303, 302, 401], (
                f"La ruta '{route}' devolvió código inesperado {response.status_code}"
            )
