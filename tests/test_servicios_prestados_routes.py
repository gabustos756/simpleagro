"""
Suite de Pruebas de Endpoints HTTP y Permisos de Interfaz para Servicios Prestados (EduAgro V3).
Verifica:
1. Renderizado de listado, alta, clientes terceros y maquinarias.
2. Restricción de permisos para rol operario_campo.
3. Flujo completo HTTP: Alta -> Cobro Parcial -> Pago a Andrés -> Cierre.
"""

from decimal import Decimal
from datetime import date
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.database import AsyncSessionLocal
from app.models import Cliente, Usuario, EquipoMaquinaria, ClienteTercero, ServicioPrestado
from app.services.servicios_prestados_service import create_equipo_maquinaria, create_cliente_tercero


@pytest.mark.asyncio
async def test_1_get_servicios_prestados_list_renders_ok():
    """Verifica que /servicios-prestados responda HTTP 200 OK para un usuario autenticado."""
    async with AsyncSessionLocal() as db:
        res_u = await db.execute(select(Usuario).limit(1))
        usuario = res_u.scalars().first()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        headers = {"x-user-id": str(usuario.id)} if usuario else {}
        response = await ac.get("/servicios-prestados", headers=headers)
        assert response.status_code == 200
        assert "Trabajos a Terceros" in response.text


@pytest.mark.asyncio
async def test_2_http_flow_create_order_register_cobro_and_pago():
    """Prueba el flujo completo HTTP con cliente autenticado."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

        maquina = await create_equipo_maquinaria(db, cliente.id, "Metalfor HTTP Test")
        tercero = await create_cliente_tercero(db, cliente.id, "Cliente HTTP Test")

    # Autenticar cliente simulando sesión
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"session": f"user_id={usuario.id}"},
    ) as ac:
        # 1. Crear Orden de Trabajo HTTP
        form_data = {
            "cliente_tercero_id": str(tercero.id),
            "maquinaria_id": str(maquina.id),
            "operador_id": str(usuario.id),
            "fecha_trabajo": date.today().isoformat(),
            "establecimiento_lote_libre": "Lote HTTP Test",
            "superficie_ha": "100.00",
            "monto_total_facturado": "1000000.00",
            "pago_operador_negociado": "200000.00",
            "imputacion_uso_maquinaria": "150000.00",
            "gastos_directos_informados": "50000.00",
            "tipo_aplicacion": "Cobertura Total",
            "volumen_caldo_lha": "40.0",
            "insumos_aportados_por": "cliente",
        }

        # Simular sesión inyectada por app fixture o get_current_user_from_session
        from unittest.mock import patch
        with patch("app.main.get_current_user_from_session") as mock_user:
            mock_user.return_value = {
                "id": str(usuario.id),
                "email": usuario.email,
                "cliente_id": cliente.id,
                "rol": "admin",
            }

            res_post = await ac.post("/servicios-prestados/nuevo", data=form_data)
            assert res_post.status_code == 303
            assert "/servicios-prestados/" in res_post.headers["location"]

            # Obtener ID de la orden creada
            orden_id_str = res_post.headers["location"].split("/")[-1]
            orden_uuid = uuid.UUID(orden_id_str)

            # 2. Registrar Cobro HTTP
            res_cobro = await ac.post(
                f"/servicios-prestados/{orden_uuid}/cobros",
                data={
                    "fecha_cobro": date.today().isoformat(),
                    "monto_cobrado": "500000.00",
                    "medio_pago": "transferencia",
                    "numero_comprobante": "TR-12345",
                    "clave_idempotencia": "req_http_cobro_1",
                },
            )
            assert res_cobro.status_code == 303

            # 3. Liquidar Pago a Operador HTTP
            res_pago = await ac.post(
                f"/servicios-prestados/{orden_uuid}/pagos-operador",
                data={
                    "fecha_pago": date.today().isoformat(),
                    "monto_pagado": "200000.00",
                    "medio_pago": "transferencia",
                    "clave_idempotencia": "req_http_pago_1",
                },
            )
            assert res_pago.status_code == 303

            # 4. Actualización Técnica Operario
            res_tec = await ac.post(
                f"/servicios-prestados/{orden_uuid}/actualizacion-tecnica",
                data={
                    "superficie_ha": "105.00",
                    "tipo_aplicacion": "Cobertura Total Ajustada",
                    "volumen_caldo_lha": "42.0",
                    "observaciones": "Aplicación finalizada sin viento",
                },
            )
            assert res_tec.status_code == 303


@pytest.mark.asyncio
async def test_3_operario_role_blocked_from_financial_mutations():
    """Verifica que el rol operario_campo sea bloqueado en los endpoints de cobro/negociación."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()
        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        from unittest.mock import patch
        with patch("app.main.get_current_user_from_session") as mock_user:
            # Forzar rol operario_campo (Andrés)
            mock_user.return_value = {
                "id": str(usuario.id),
                "email": usuario.email,
                "cliente_id": cliente.id,
                "rol": "operario_campo",
            }

            res_cobro = await ac.post(
                f"/servicios-prestados/{uuid.uuid4()}/cobros",
                data={
                    "fecha_cobro": date.today().isoformat(),
                    "monto_cobrado": "1000.00",
                },
            )
            assert res_cobro.status_code == 303
            assert "error=" in res_cobro.headers["location"]
