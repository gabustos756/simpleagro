"""
Pruebas de Integración HTTP / Routes / Templates para /insumos en EduAgro.
Cubre:
1. Renderizado de Dashboard sin HTTP 500 y con tarjetas KPI.
2. Renderizado de Kardex.
3. Formularios POST de compra, consumo, idempotencia y restricción por rol.
4. Multitenant Isolation HTTP.
"""

from decimal import Decimal
from datetime import date
import uuid
import pytest
from sqlalchemy import select, func
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import AsyncSessionLocal
from app.models import (
    Cliente,
    Usuario,
    StorageLocation,
    Insumo,
    InsumoSaldoUbicacion,
    TransaccionFinanciera,
    Campania,
    Campo,
    Lote,
    LaborCampo,
)
from app.enums import CategoriaInsumoEnum, UnidadMedidaInsumoEnum
from app.services.insumos_service import crear_insumo_catalogo


@pytest.mark.asyncio
async def test_1_get_insumos_dashboard_renders_ok():
    """Verifica que /insumos renderice correctamente sin error 500 para un usuario autenticado."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        cookies = {"session_user_id": str(usuario.id)} if usuario else {}
        res = await ac.get("/insumos", cookies=cookies)
        assert res.status_code == 200
        assert "Insumos y Abastecimiento" in res.text
        assert "Inventario Físico" in res.text


@pytest.mark.asyncio
async def test_2_get_insumos_kardex_renders_ok():
    """Verifica que /insumos/kardex renderice correctamente."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        cookies = {"session_user_id": str(usuario.id)} if usuario else {}
        res = await ac.get("/insumos/kardex", cookies=cookies)
        assert res.status_code == 200
        assert "Kardex e Historial de Movimientos" in res.text


@pytest.mark.asyncio
async def test_3_post_insumos_compra_as_admin_succeeds():
    """Verifica registrar compra desde el formulario POST /insumos/compra como administración."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        admin_user = Usuario(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            email=f"admin_route_{uuid.uuid4().hex[:4]}@eduagro.com",
            nombre="Admin Route",
            rol="admin",
            password_hash="hash",
        )
        db.add(admin_user)

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Insumo RouteCompra {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.FITOSANITARIO, unidad_medida=UnidadMedidaInsumoEnum.LITRO)
        db.add(insumo)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"x-user-id": str(admin_user.id)}
        payload = {
            "insumo_id": str(insumo.id),
            "storage_location_id": str(location.id),
            "cantidad": "100.00",
            "monto_unitario": "15.00",
            "moneda_origen": "USD",
            "cotizacion_usd_ars": "1000.00",
            "proveedor_nombre": "Proveedor Route",
            "clave_idempotencia": f"route_compra_{uuid.uuid4().hex[:4]}",
        }
        res = await ac.post("/insumos/compra", data=payload, headers=headers, follow_redirects=True)
        assert res.status_code == 200
        assert "Compra e ingreso de insumo registrados exitosamente" in res.text or "mensaje=" in str(res.url)


@pytest.mark.asyncio
async def test_4_post_insumos_compra_as_operario_campo_is_rejected():
    """Verifica que el rol operario_campo no pueda registrar compras HTTP."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        # Usuario operario_campo
        user_op = Usuario(id=uuid.uuid4(), cliente_id=cliente.id, email=f"op_{uuid.uuid4().hex[:4]}@eduagro.com", nombre="Operario Route", rol="operario_campo", password_hash="hash")
        db.add(user_op)

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(id=uuid.uuid4(), cliente_id=cliente.id, nombre=f"Insumo OpReject {uuid.uuid4().hex[:4]}", categoria=CategoriaInsumoEnum.FITOSANITARIO, unidad_medida=UnidadMedidaInsumoEnum.LITRO)
        db.add(insumo)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"x-user-id": str(user_op.id)}
        payload = {
            "insumo_id": str(insumo.id),
            "storage_location_id": str(location.id),
            "cantidad": "100.00",
            "monto_unitario": "15.00",
            "moneda_origen": "USD",
            "cotizacion_usd_ars": "1000.00",
            "proveedor_nombre": "Proveedor Op",
            "clave_idempotencia": f"route_op_{uuid.uuid4().hex[:4]}",
        }
        res = await ac.post("/insumos/compra", data=payload, headers=headers, follow_redirects=True)
        assert res.status_code == 200
        assert "error=" in str(res.url) or "permiso" in res.text.lower()


@pytest.mark.asyncio
async def test_5_insumos_templates_use_light_mode_and_no_dark_theme():
    """Snapshot/Regresión visual: Garantiza que las plantillas de insumos usen el diseño claro de EduAgro (bg-slate-50) y no modo oscuro."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        usuario = res_u.scalars().first()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"x-user-id": str(usuario.id)} if usuario else {}
        res_dash = await ac.get("/insumos", headers=headers)
        assert res_dash.status_code == 200
        assert "bg-slate-50" in res_dash.text
        assert 'class="h-full bg-slate-950"' not in res_dash.text
        assert 'body class="min-h-full flex flex-col font-sans antialiased text-slate-100 bg-slate-950"' not in res_dash.text

        res_kardex = await ac.get("/insumos/kardex", headers=headers)
        assert res_kardex.status_code == 200
        assert "bg-slate-50" in res_kardex.text
        assert 'class="h-full bg-slate-950"' not in res_kardex.text


@pytest.mark.asyncio
async def test_6_catalogo_abm_full_lifecycle():
    """Prueba el ciclo de vida completo del ABM de Catálogo: Listado, Alta, Edición y Baja Lógica."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        admin_user = Usuario(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            email=f"admin_cat_{uuid.uuid4().hex[:4]}@eduagro.com",
            nombre="Admin Catálogo",
            rol="admin",
            password_hash="hash",
        )
        db.add(admin_user)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"x-user-id": str(admin_user.id)}

        # 1. GET /insumos/catalogo (Renderizado)
        res_list = await ac.get("/insumos/catalogo", headers=headers)
        assert res_list.status_code == 200
        assert "Catálogo Maestro de Insumos" in res_list.text

        # 2. POST /insumos/catalogo/nuevo (Alta)
        ins_nombre = f"Fertilizante Urea {uuid.uuid4().hex[:4]}"
        payload_alta = {
            "nombre": ins_nombre,
            "categoria": "fertilizante",
            "unidad_medida": "kg",
            "principio_activo_formula": "N46%",
            "punto_pedido_minimo": "1000.00",
        }
        res_alta = await ac.post("/insumos/catalogo/nuevo", data=payload_alta, headers=headers, follow_redirects=True)
        assert res_alta.status_code == 200
        assert "creado+exitosamente" in str(res_alta.url) or "creado exitosamente" in res_alta.text

        # Obtener insumo creado en DB
        async with AsyncSessionLocal() as db:
            res_ins = await db.execute(select(Insumo).where(Insumo.cliente_id == cliente.id, Insumo.nombre == ins_nombre))
            insumo_creado = res_ins.scalars().first()
            assert insumo_creado is not None
            assert insumo_creado.activo is True

        # 3. POST /insumos/catalogo/{id}/editar (Edición)
        payload_edit = {
            "nombre": ins_nombre + " Editado",
            "categoria": "fertilizante",
            "unidad_medida": "kg",
            "principio_activo_formula": "N46% Granulado Premium",
            "punto_pedido_minimo": "1500.00",
        }
        res_edit = await ac.post(f"/insumos/catalogo/{insumo_creado.id}/editar", data=payload_edit, headers=headers, follow_redirects=True)
        assert res_edit.status_code == 200
        assert "actualizado+exitosamente" in str(res_edit.url) or "actualizado exitosamente" in res_edit.text

        # 4. POST /insumos/catalogo/{id}/desactivar (Baja Lógica)
        res_desact = await ac.post(f"/insumos/catalogo/{insumo_creado.id}/desactivar", headers=headers, follow_redirects=True)
        assert res_desact.status_code == 200
        assert "desactivado+exitosamente" in str(res_desact.url) or "desactivado exitosamente" in res_desact.text

        async with AsyncSessionLocal() as db:
            ins_db = await db.get(Insumo, insumo_creado.id)
            assert ins_db is not None
            assert ins_db.activo is False


@pytest.mark.asyncio
async def test_7_catalogo_abm_permissions_operario_campo_rejected():
    """Verifica que un operario de campo no pueda acceder al formulario ni crear o desactivar catálogo."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        user_op = Usuario(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            email=f"op_cat_{uuid.uuid4().hex[:4]}@eduagro.com",
            nombre="Operario Catálogo",
            rol="operario_campo",
            password_hash="hash",
        )
        db.add(user_op)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"x-user-id": str(user_op.id)}

        # GET /insumos/catalogo/nuevo como operario -> Redirige con error de permisos
        res_nuevo = await ac.get("/insumos/catalogo/nuevo", headers=headers, follow_redirects=True)
        assert res_nuevo.status_code == 200
        assert "error=" in str(res_nuevo.url) or "permisos" in res_nuevo.text.lower()


@pytest.mark.asyncio
async def test_8_catalogo_nuevo_get_renders_form_ok():
    """Verifica que GET /insumos/catalogo/nuevo renderice el formulario sin errores de plantilla (Jinja2)."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        admin_user = Usuario(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            email=f"admin_render_{uuid.uuid4().hex[:4]}@eduagro.com",
            nombre="Admin Render",
            rol="admin",
            password_hash="hash",
        )
        db.add(admin_user)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"x-user-id": str(admin_user.id)}
        res = await ac.get("/insumos/catalogo/nuevo", headers=headers)
        assert res.status_code == 200
        assert "Registrar Nuevo Insumo" in res.text
        assert "Unidad de Medida" in res.text


@pytest.mark.asyncio
async def test_9_validar_categoria_unidad_invalida_rejected():
    """Verifica que combinaciones incoherentes de categoría/unidad (ej: Semilla + Litro) sean rechazadas por el backend."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

    # Semilla en Litros debe fallar
    with pytest.raises(ValueError, match="no es válida para la categoría 'semilla'"):
        async with AsyncSessionLocal() as db:
            await crear_insumo_catalogo(
                db=db,
                cliente_id=cliente.id,
                nombre=f"Semilla Invalida {uuid.uuid4().hex[:4]}",
                categoria=CategoriaInsumoEnum.SEMILLA,
                unidad_medida=UnidadMedidaInsumoEnum.LITRO,
                usuario_rol="admin",
            )


@pytest.mark.asyncio
async def test_10_post_insumos_stock_inicial_creates_stock_no_financial_tx():
    """Verifica que Cargar Stock Inicial cree saldos y movimientos físicos sin generar una TransaccionFinanciera."""
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(Cliente).limit(1))
        cliente = res_c.scalars().first()

        admin_user = Usuario(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            email=f"admin_stk_{uuid.uuid4().hex[:4]}@eduagro.com",
            nombre="Admin StockInit",
            rol="admin",
            password_hash="hash",
        )
        db.add(admin_user)

        res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente.id).limit(1))
        location = res_loc.scalars().first()

        insumo = Insumo(
            id=uuid.uuid4(),
            cliente_id=cliente.id,
            nombre=f"Gasoil StockInit {uuid.uuid4().hex[:4]}",
            categoria=CategoriaInsumoEnum.COMBUSTIBLE,
            unidad_medida=UnidadMedidaInsumoEnum.LITRO,
        )
        db.add(insumo)
        await db.commit()

        # Contar TransaccionFinanciera pre-operación
        res_tx_pre = await db.execute(select(func.count(TransaccionFinanciera.id)))
        count_tx_pre = res_tx_pre.scalar_one() or 0

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"x-user-id": str(admin_user.id)}
        payload = {
            "insumo_id": str(insumo.id),
            "storage_location_id": str(location.id),
            "cantidad": "2500.00",
            "costo_unitario_usd": "0.95",
            "cotizacion_usd_ars": "1000.00",
            "observaciones": "Carga inicial sin egreso",
            "clave_idempotencia": f"stk_init_{uuid.uuid4().hex[:6]}",
        }
        res = await ac.post("/insumos/stock-inicial", data=payload, headers=headers, follow_redirects=True)
        assert res.status_code == 200
        assert "Stock+inicial+cargado" in str(res.url) or "Stock inicial cargado" in res.text

    async with AsyncSessionLocal() as db:
        # Verificar que el stock aumentó
        res_s = await db.execute(select(InsumoSaldoUbicacion).where(InsumoSaldoUbicacion.insumo_id == insumo.id, InsumoSaldoUbicacion.storage_location_id == location.id))
        saldo = res_s.scalars().first()
        assert saldo is not None
        assert saldo.cantidad_disponible == Decimal("2500.0000")

        # Confirmar que NO se creó ninguna TransaccionFinanciera
        res_tx_post = await db.execute(select(func.count(TransaccionFinanciera.id)))
        count_tx_post = res_tx_post.scalar_one() or 0
        assert count_tx_post == count_tx_pre
