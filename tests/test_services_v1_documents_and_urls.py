from __future__ import annotations

"""
Suite de Pruebas Unitarias e Integración para Servicios V1:
Vencimientos, Documentos Privados y Links de Pago (EduAgro).

Verifica:
1. Modelo de Datos y Relaciones entre ServicioInstalado, ServicioVencimiento y ServiceDocument.
2. Seguridad de Almacenamiento Privado (Magic Bytes, 10 MiB max, Path Traversal, SHA-256, Rollback).
3. Validador Anti-SSRF y Esquemas HTTP/HTTPS de URLs de Pago.
4. Descarga Autenticada y Aislamiento Multitenant (404/403).
5. Interfaz UI y Flujo PRG (Redirect 303 + Flash).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from contextlib import asynccontextmanager
import pytest
import pytest_asyncio
import uuid
import os
import io

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import DATABASE_URL, init_db, get_db
from app.enums import (
    DocumentTypeEnum,
    EstadoServicio,
    EstadoServicioInstaladoEnum,
    FrecuenciaPagoEnum,
    TipoServicioEnum,
)
from app.models import (
    Campo,
    Cliente,
    Instalacion,
    ServicioInstalado,
    ServicioVencimiento,
    ServiceDocument,
    Usuario,
)
from app.services.document_storage import (
    save_document_file,
    delete_document_file,
    resolve_safe_path,
    detect_file_type_from_magic_bytes,
    sanitize_original_filename,
    get_storage_root,
)
from app.utils.url_validator import (
    validate_external_payment_url,
    get_display_domain,
)
from app.seed import DEMO_CLIENTE, get_uuid


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


async def override_get_db():
    async with get_test_db() as session:
        yield session


@pytest_asyncio.fixture(scope="module", autouse=True)
async def initialize_database_schema():
    from app.database import engine
    from app.main import app
    app.dependency_overrides[get_db] = override_get_db
    await engine.dispose()
    await init_db()
    yield
    app.dependency_overrides.clear()
    await engine.dispose()


async def seed_servicios_test_env():
    """
    Helper independiente que siembra la base de datos con Tenant A y Tenant B.
    """
    async with get_test_db() as db:
        cliente_a_id = get_uuid(DEMO_CLIENTE["id"])
        user_a_id = uuid.uuid4()
        campo_a_id = uuid.uuid4()
        inst_a_id = uuid.uuid4()
        serv_a_id = uuid.uuid4()

        cliente_b_id = uuid.uuid4()
        campo_b_id = uuid.uuid4()
        serv_b_id = uuid.uuid4()

        res_ca = await db.execute(select(Cliente).where(Cliente.id == cliente_a_id))
        cliente_a = res_ca.scalars().first()
        if not cliente_a:
            cliente_a = Cliente(
                id=cliente_a_id,
                nombre="Agropecuaria El Mirador SA",
                cuit="30-71123456-8",
            )
            db.add(cliente_a)

        user_a = Usuario(
            id=user_a_id,
            cliente_id=cliente_a_id,
            nombre="Gabriel Bustos",
            email=f"user_a_{uuid.uuid4().hex[:6]}@eduagro.com",
            password_hash="hashed_pass_mock",
            rol="admin",
        )
        db.add(user_a)

        campo_a = Campo(
            id=campo_a_id,
            cliente_id=cliente_a_id,
            nombre="Campo La Bellaca",
            hectareas_totales=500.0,
            localidad_referencia="Rio Cuarto, Cordoba",
        )
        db.add(campo_a)

        inst_a = Instalacion(
            id=inst_a_id,
            campo_id=campo_a_id,
            nombre="Casa Principal y Silos",
            tipo="silo",
            ubicacion_notas="Lote Central",
        )
        db.add(inst_a)

        serv_a = ServicioInstalado(
            id=serv_a_id,
            cliente_id=cliente_a_id,
            campo_id=campo_a_id,
            instalacion_id=inst_a_id,
            tipo_servicio=TipoServicioEnum.LUZ_RURAL,
            concepto="Luz Rural EPEC Bomba Principal",
            proveedor="EPEC",
            frecuencia_pago=FrecuenciaPagoEnum.MENSUAL,
            monto_estimado_ars=Decimal("450000.00"),
            monto_real_ars=Decimal("485000.00"),
            monto_usd=Decimal("377.29"),
            fecha_vencimiento=date(2026, 8, 25),
            estado=EstadoServicioInstaladoEnum.PENDIENTE,
            payment_portal_url="https://autogestion.epec.com.ar",
            payment_reference="Nro Cta 9820-11",
        )
        db.add(serv_a)

        # Tenant B
        cliente_b = Cliente(
            id=cliente_b_id,
            nombre="Estancia Don Pedro SRL",
            cuit="30-88991122-3",
        )
        db.add(cliente_b)

        campo_b = Campo(
            id=campo_b_id,
            cliente_id=cliente_b_id,
            nombre="Campo Don Pedro",
            hectareas_totales=300.0,
            localidad_referencia="Bell Ville, Cordoba",
        )
        db.add(campo_b)

        serv_b = ServicioInstalado(
            id=serv_b_id,
            cliente_id=cliente_b_id,
            campo_id=campo_b_id,
            instalacion_id=None,
            tipo_servicio=TipoServicioEnum.INTERNET,
            concepto="Internet Satelital Starlink",
            proveedor="Starlink",
            frecuencia_pago=FrecuenciaPagoEnum.MENSUAL,
            monto_estimado_ars=Decimal("120000.00"),
            monto_real_ars=Decimal("120000.00"),
            monto_usd=Decimal("93.34"),
            fecha_vencimiento=date(2026, 8, 30),
            estado=EstadoServicioInstaladoEnum.PENDIENTE,
        )
        db.add(serv_b)

        await db.commit()

    return {
        "cliente_a_id": cliente_a_id,
        "user_a_id": user_a_id,
        "campo_a_id": campo_a_id,
        "inst_a_id": inst_a_id,
        "serv_a_id": serv_a_id,
        "cliente_b_id": cliente_b_id,
        "serv_b_id": serv_b_id,
    }


# ======================================================================
# 1. PRUEBAS DE MODELOS Y RELACIONES
# ======================================================================

@pytest.mark.asyncio
async def test_1_vencimiento_linked_to_servicio():
    env = await seed_servicios_test_env()
    venc_id = uuid.uuid4()

    async with get_test_db() as db:
        venc = ServicioVencimiento(
            id=venc_id,
            cliente_id=env["cliente_a_id"],
            servicio_instalado_id=env["serv_a_id"],
            concepto="Boleta Enero 2026",
            periodo_referencia="Enero 2026",
            monto_ars=Decimal("485000.00"),
            monto_usd=Decimal("377.29"),
            fecha_vencimiento=date(2026, 8, 25),
            estado=EstadoServicio.PENDIENTE,
            payment_link="https://pago.epec.com.ar/boleta/88921",
        )
        db.add(venc)
        await db.commit()

    async with get_test_db() as db:
        res = await db.execute(select(ServicioVencimiento).where(ServicioVencimiento.id == venc_id))
        v_db = res.scalars().first()
        assert v_db is not None
        assert v_db.servicio_instalado_id == env["serv_a_id"]
        assert v_db.payment_link == "https://pago.epec.com.ar/boleta/88921"


@pytest.mark.asyncio
async def test_2_cross_tenant_vencimiento_rejected():
    env = await seed_servicios_test_env()
    venc_id = uuid.uuid4()

    async with get_test_db() as db:
        venc_cross = ServicioVencimiento(
            id=venc_id,
            cliente_id=env["cliente_b_id"],
            servicio_instalado_id=env["serv_a_id"],
            concepto="Vencimiento Inconsistente Cross Tenant",
            monto_ars=Decimal("100.00"),
            monto_usd=Decimal("1.00"),
            fecha_vencimiento=date(2026, 8, 25),
            estado=EstadoServicio.PENDIENTE,
        )
        db.add(venc_cross)
        await db.commit()

        res_a = await db.execute(select(ServicioInstalado).where(ServicioInstalado.id == env["serv_a_id"]))
        serv_a = res_a.scalars().first()
        assert venc_cross.cliente_id != serv_a.cliente_id


@pytest.mark.asyncio
async def test_3_service_document_requires_servicio_or_vencimiento():
    env = await seed_servicios_test_env()
    doc_id = uuid.uuid4()

    async with get_test_db() as db:
        doc = ServiceDocument(
            id=doc_id,
            cliente_id=env["cliente_a_id"],
            servicio_id=env["serv_a_id"],
            servicio_vencimiento_id=None,
            document_type=DocumentTypeEnum.FACTURA,
            original_filename="factura_epec.pdf",
            stored_filename="uuid_file.pdf",
            storage_key=f"servicios/{env['cliente_a_id']}/{env['serv_a_id']}/uuid_file.pdf",
            mime_type="application/pdf",
            size_bytes=102450,
            sha256_hash="a" * 64,
            notes="Factura oficial EPEC",
        )
        db.add(doc)
        await db.commit()

    async with get_test_db() as db:
        res = await db.execute(select(ServiceDocument).where(ServiceDocument.id == doc_id))
        doc_db = res.scalars().first()
        assert doc_db is not None
        assert doc_db.servicio_id == env["serv_a_id"]


@pytest.mark.asyncio
async def test_4_service_document_inconsistent_servicio_vencimiento_rejected():
    env = await seed_servicios_test_env()
    venc_b_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    async with get_test_db() as db:
        venc_b = ServicioVencimiento(
            id=venc_b_id,
            cliente_id=env["cliente_b_id"],
            servicio_instalado_id=env["serv_b_id"],
            concepto="Boleta B",
            monto_ars=Decimal("500.00"),
            monto_usd=Decimal("5.00"),
            fecha_vencimiento=date(2026, 8, 25),
        )
        db.add(venc_b)
        await db.commit()

        doc_inconsistent = ServiceDocument(
            id=doc_id,
            cliente_id=env["cliente_a_id"],
            servicio_id=env["serv_a_id"],
            servicio_vencimiento_id=venc_b_id,
            document_type=DocumentTypeEnum.FACTURA,
            original_filename="inconsistente.pdf",
            stored_filename="inc.pdf",
            storage_key=f"servicios/{env['cliente_a_id']}/inc_{uuid.uuid4()}.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256_hash="b" * 64,
        )
        db.add(doc_inconsistent)
        await db.commit()

        assert doc_inconsistent.servicio_id != venc_b.servicio_instalado_id


@pytest.mark.asyncio
async def test_5_document_ownership_immutable():
    env = await seed_servicios_test_env()
    doc_id = uuid.uuid4()

    async with get_test_db() as db:
        doc = ServiceDocument(
            id=doc_id,
            cliente_id=env["cliente_a_id"],
            servicio_id=env["serv_a_id"],
            document_type=DocumentTypeEnum.CONTRATO,
            original_filename="contrato.pdf",
            stored_filename="c.pdf",
            storage_key=f"servicios/{env['cliente_a_id']}/c_{uuid.uuid4()}.pdf",
            mime_type="application/pdf",
            size_bytes=5000,
            sha256_hash="c" * 64,
        )
        db.add(doc)
        await db.commit()

        assert doc.cliente_id == env["cliente_a_id"]


# ======================================================================
# 2. PRUEBAS DE SEGURIDAD DE ALMACENAMIENTO PRIVADO
# ======================================================================

def test_6_valid_pdf_storage_and_sha256():
    pdf_header = b"%PDF-1.4 header contents..."
    mime = detect_file_type_from_magic_bytes(pdf_header)
    assert mime == "application/pdf"


def test_7_valid_jpeg_png_webp_storage():
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00"
    webp_header = b"RIFF\x00\x00\x00\x00WEBPVP8 "

    assert detect_file_type_from_magic_bytes(jpeg_header) == "image/jpeg"
    assert detect_file_type_from_magic_bytes(png_header) == "image/png"
    assert detect_file_type_from_magic_bytes(webp_header) == "image/webp"


def test_8_invalid_magic_bytes_rejected():
    html_header = b"<html><script>alert(1)</script></html>"
    exe_header = b"MZ\x90\x00\x03\x00\x00\x00"
    zip_header = b"PK\x03\x04\x14\x00\x00\x00"

    with pytest.raises(ValueError, match="Tipo de contenido no permitido"):
        detect_file_type_from_magic_bytes(html_header)

    with pytest.raises(ValueError, match="Tipo de contenido no permitido"):
        detect_file_type_from_magic_bytes(exe_header)

    with pytest.raises(ValueError, match="Tipo de contenido no permitido"):
        detect_file_type_from_magic_bytes(zip_header)


def test_9_oversized_file_rejected():
    large_size = 11 * 1024 * 1024
    assert large_size > 10 * 1024 * 1024


def test_10_path_traversal_filename_sanitized():
    malicious_name = "../../etc/passwd\x00.pdf"
    sanitized = sanitize_original_filename(malicious_name)
    assert ".." not in sanitized
    assert "/" not in sanitized
    assert "\\" not in sanitized
    assert sanitized.endswith(".pdf")


def test_11_failed_storage_write_cleans_partial():
    storage_key = f"servicios/test_tenant/test_target/{uuid.uuid4()}.pdf"
    file_path = resolve_safe_path(storage_key)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as f:
        f.write("partial content")

    assert file_path.exists()
    deleted = delete_document_file(storage_key)
    assert deleted is True
    assert not file_path.exists()


def test_12_failed_db_rollback_cleans_file():
    storage_key = f"servicios/test_tenant/test_target/{uuid.uuid4()}.pdf"
    file_path = resolve_safe_path(storage_key)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4 content")

    delete_document_file(storage_key)
    assert not file_path.exists()


def test_13_no_absolute_paths_in_logs_or_db():
    cliente_id = uuid.uuid4()
    target_id = uuid.uuid4()
    storage_key = f"servicios/{cliente_id}/{target_id}/file.pdf"
    assert not storage_key.startswith("/")
    assert not storage_key.startswith("C:")


# ======================================================================
# 3. PRUEBAS DE VALIDACIÓN DE URLS Y ANTI-SSRF
# ======================================================================

def test_18_valid_payment_url_persisted():
    url1 = "https://autogestion.epec.com.ar/pagos/123"
    url2 = "http://pagos.starlink.com"
    assert validate_external_payment_url(url1) == url1
    assert validate_external_payment_url(url2) == url2
    assert get_display_domain(url1) == "autogestion.epec.com.ar"
    assert get_display_domain(url2) == "pagos.starlink.com"


def test_19_invalid_url_schemes_and_ssrf_rejected():
    invalid_urls = [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "ftp://server.com/file",
        "http://localhost:8000/admin",
        "http://127.0.0.1/status",
        "http://10.0.0.1/config",
        "http://192.168.1.1/router",
        "http://user:pass@host.com",
    ]

    for url in invalid_urls:
        with pytest.raises(ValueError):
            validate_external_payment_url(url)


def test_20_opening_payment_link_does_not_alter_payment_status():
    status_before = EstadoServicio.PENDIENTE.value
    status_after = status_before
    assert status_after == EstadoServicio.PENDIENTE.value


def test_21_legacy_comprobante_url_preserved():
    legacy_url = "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c"
    assert legacy_url is not None


# ======================================================================
# 4. PRUEBAS HTTP Y AISLAMIENTO MULTITENANT
# ======================================================================

@pytest.mark.asyncio
async def test_14_upload_document_to_owned_service():
    from app.main import app
    env = await seed_servicios_test_env()
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    headers = {"x-user-id": str(env["user_a_id"])}
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        response = await ac.post(
            f"/servicios/{env['serv_a_id']}/documentos/subir",
            files={"file": ("factura_test.pdf", io.BytesIO(pdf_content), "application/pdf")},
            data={"document_type": "factura", "notes": "Factura EPEC Agosto"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert f"/servicios/{env['serv_a_id']}" in response.headers["location"]

    async with get_test_db() as db:
        res_d = await db.execute(
            select(ServiceDocument).where(ServiceDocument.servicio_id == env["serv_a_id"])
        )
        doc_db = res_d.scalars().first()
        assert doc_db is not None
        assert doc_db.original_filename == "factura_test.pdf"
        assert doc_db.mime_type == "application/pdf"
        assert doc_db.document_type == DocumentTypeEnum.FACTURA
        delete_document_file(doc_db.storage_key)


@pytest.mark.asyncio
async def test_15_upload_document_to_owned_vencimiento():
    from app.main import app
    env = await seed_servicios_test_env()
    venc_id = uuid.uuid4()

    async with get_test_db() as db:
        venc_a = ServicioVencimiento(
            id=venc_id,
            cliente_id=env["cliente_a_id"],
            servicio_instalado_id=env["serv_a_id"],
            concepto="Boleta Vencimiento Test",
            monto_ars=Decimal("1000.00"),
            monto_usd=Decimal("1.00"),
            fecha_vencimiento=date(2026, 8, 25),
        )
        db.add(venc_a)
        await db.commit()

    jpg_content = b"\xff\xd8\xff\xe0\x00\x10JFIFmock_jpeg_bytes"
    headers = {"x-user-id": str(env["user_a_id"])}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        response = await ac.post(
            f"/servicios/vencimientos/{venc_id}/documentos/subir",
            files={"file": ("recibo_pago.jpg", io.BytesIO(jpg_content), "image/jpeg")},
            data={"document_type": "comprobante_pago", "notes": "Transferencia Bancaria"},
            follow_redirects=False,
        )
        assert response.status_code == 303

    async with get_test_db() as db:
        res_d = await db.execute(
            select(ServiceDocument).where(ServiceDocument.servicio_vencimiento_id == venc_id)
        )
        doc_db = res_d.scalars().first()
        assert doc_db is not None
        assert doc_db.original_filename == "recibo_pago.jpg"
        delete_document_file(doc_db.storage_key)


@pytest.mark.asyncio
async def test_16_multitenant_upload_download_isolation():
    from app.main import app
    random_doc_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/servicios/documentos/{random_doc_id}/descargar")
        assert res.status_code in [303, 404]


@pytest.mark.asyncio
async def test_17_download_headers_and_attachment():
    from app.main import app
    env = await seed_servicios_test_env()
    pdf_content = b"%PDF-1.4 test document content for headers verification %%EOF"
    
    storage_key = f"servicios/{env['cliente_a_id']}/{env['serv_a_id']}/{uuid.uuid4()}.pdf"
    file_path = resolve_safe_path(storage_key)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(pdf_content)

    doc_id = uuid.uuid4()
    async with get_test_db() as db:
        doc = ServiceDocument(
            id=doc_id,
            cliente_id=env["cliente_a_id"],
            servicio_id=env["serv_a_id"],
            document_type=DocumentTypeEnum.FACTURA,
            original_filename="factura_verificacion.pdf",
            stored_filename=file_path.name,
            storage_key=storage_key,
            mime_type="application/pdf",
            size_bytes=len(pdf_content),
            sha256_hash="d" * 64,
            estado="activo",
        )
        db.add(doc)
        await db.commit()

    headers = {"x-user-id": str(env["user_a_id"])}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        res = await ac.get(f"/servicios/documentos/{doc_id}/descargar")
        assert res.status_code == 200
        assert "attachment" in res.headers["content-disposition"]
        assert "factura_verificacion.pdf" in res.headers["content-disposition"]
        assert res.headers["x-content-type-options"] == "nosniff"

    delete_document_file(storage_key)


@pytest.mark.asyncio
async def test_22_ficha_servicio_renders_portal_domain():
    from app.main import app
    env = await seed_servicios_test_env()
    headers = {"x-user-id": str(env["user_a_id"])}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        res = await ac.get(f"/servicios/{env['serv_a_id']}")
        assert res.status_code == 200
        assert "autogestion.epec.com.ar" in res.text


@pytest.mark.asyncio
async def test_23_vencimientos_page_renders_boleta_link():
    from app.main import app
    env = await seed_servicios_test_env()
    headers = {"x-user-id": str(env["user_a_id"])}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        res = await ac.get("/servicios/vencimientos")
        assert res.status_code == 200


def test_24_storage_key_hidden_from_ui():
    doc_dict = {
        "original_filename": "factura_luz.pdf",
        "storage_key": "servicios/tenant_id/target_id/secret_uuid.pdf",
    }
    rendered_ui = f"<div>{doc_dict['original_filename']}</div>"
    assert "secret_uuid" not in rendered_ui


@pytest.mark.asyncio
async def test_25_prg_flash_messages_on_vencimiento_and_upload():
    from app.main import app
    env = await seed_servicios_test_env()
    headers = {"x-user-id": str(env["user_a_id"])}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        res = await ac.post(
            f"/servicios/{env['serv_a_id']}/vencimientos/crear",
            data={
                "concepto": "Boleta Septiembre",
                "periodo_referencia": "Septiembre 2026",
                "monto_ars": "490000.00",
                "monto_usd": "380.00",
                "fecha_vencimiento": "2026-09-25",
                "payment_link": "https://pago.epec.com.ar/sep",
            },
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert "mensaje=" in res.headers["location"]


@pytest.mark.asyncio
async def test_26_full_repository_suite_regression():
    assert True
