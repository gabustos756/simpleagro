from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from decimal import Decimal
from typing import Optional, List, Dict, Any
import uuid
from uuid import uuid4, UUID
import os
import time
import logging
import asyncio
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

from fastapi import FastAPI, Request, Form, status, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_password
from app.database import init_db, AsyncSessionLocal, get_db
from app.models import (
    Cliente,
    Usuario,
    Campo,
    Lote,
    Instalacion,
    ServicioInstalado,
    ServicioVencimiento,
    ServiceDocument,
    StockGrano,
    ContratoVentaGrano,
    CompromisoGrano,
    ArrendamientoTerms,
    PrecioMercadoCache,
)
from app.services.comercial import calcular_posicion_comercial, obtener_campania_activa_para_cliente
from app.enums import (
    DocumentTypeEnum,
    EstadoProductivoLoteEnum,
    EstadoServicio,
    EstadoServicioInstaladoEnum,
    FrecuenciaPagoEnum,
    RolUsuario,
    TenenciaTipoEnum,
    TipoCompromisoEnum,
    TipoPrecioEnum,
    TipoServicioEnum,
    UbicacionStockEnum,
)
from app.seed import (
    seed_initial_data,
    get_uuid,
    DEMO_CLIENTE,
    DEMO_USUARIOS,
    DEMO_CAMPOS,
    DEMO_LOTES,
    DEMO_INSTALACIONES,
    DEMO_SERVICIOS_INSTALADOS,
    DEMO_TAREAS,
)
from app.weather import get_weather_for_location
from app.utils.url_validator import validate_external_payment_url, get_display_domain
from app.services.document_storage import (
    save_document_file,
    delete_document_file,
    resolve_safe_path,
)

# Configuración de Logging para Performance
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("eduagro.performance")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestor del ciclo de vida: inicializa tablas, datos iniciales y tarea en segundo plano de cotizaciones CAC."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
        # Refresco de inicio de cotizaciones CAC en vivo
        try:
            from app.services.mercado import actualizar_precios_mercado
            await actualizar_precios_mercado(session, usar_fetcher_real=True)
            logger.info("[STARTUP REFRESH] Cotizaciones oficiales CAC Rosario inicializadas.")
        except Exception as e:
            logger.warning(f"[STARTUP REFRESH] No se pudo refrescar cotizaciones en arranque ({e}). Servir datos almacenados.")

    # Tarea en segundo plano periódica para refresco automático cada 4 horas
    import asyncio
    async def periodic_refresh_task():
        while True:
            await asyncio.sleep(4 * 3600)  # Cada 4 horas
            try:
                async with AsyncSessionLocal() as bg_session:
                    from app.services.mercado import actualizar_precios_mercado
                    await actualizar_precios_mercado(bg_session, usar_fetcher_real=True)
                    logger.info("[BACKGROUND REFRESH] Cotizaciones CAC Rosario actualizadas automáticamente.")
            except Exception as e:
                logger.warning(f"[BACKGROUND REFRESH] Error en refresco periódico: {e}")

    refresh_task = asyncio.create_task(periodic_refresh_task())

    yield

    refresh_task.cancel()


app = FastAPI(
    title="EduAgro ERP Agropecuario",
    description="Plataforma ERP Agropecuaria (Laguna Larga, Córdoba) - Cliente: Familia Matteuda",
    version="1.0.0",
    lifespan=lifespan,
)

# Compresión GZip para reducir tamaño de descarga de respuestas HTML en Railway
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Configuración Middleware de Sesión por Cookie Firmada
SECRET_KEY = os.environ.get("SESSION_SECRET", "eduagro-secret-key-2026-cordoba")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="eduagro_session")


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Middleware de timing: mide el tiempo de respuesta en ms, lo loguea e inyecta header X-Process-Time."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"
    logger.info(f"[PERFORMANCE] {request.method} {request.url.path} - Status {response.status_code} - {process_time_ms:.2f}ms")
    return response


# Configuración de Plantillas Jinja2 y Archivos Estáticos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates_dir = os.path.join(BASE_DIR, "templates")
static_dir = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=templates_dir)

def formato_numero_ar(value, decimales=2):
    """Formatea números con notación argentina (punto para miles, coma para decimales)."""
    if value is None:
        return "0,00"
    try:
        val = float(value)
        val_str = f"{val:,.{decimales}f}"
        return val_str.replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(value)

templates.env.filters["formato_ar"] = formato_numero_ar

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/sw.js")
def get_service_worker_root():
    """Servir Service Worker en la raíz con alcance total '/'."""
    sw_path = os.path.join(static_dir, "sw.js")
    return FileResponse(
        sw_path,
        media_type="text/javascript; charset=utf-8",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"}
    )


# Store de Tareas Operativas en Memoria (Modo Campo)
TAREAS_STORE = []


# ----------------------------------------------------------------------
# Mapeadores de Modelos a Diccionarios para Plantillas Jinja2
# ----------------------------------------------------------------------

def campo_to_dict(c: Campo, lotes_count: int = 0) -> dict:
    return {
        "id": str(c.id),
        "nombre": c.nombre,
        "ubicacion": c.ubicacion or "Laguna Larga, Córdoba",
        "localidad_referencia": c.localidad_referencia or "Laguna Larga, Córdoba",
        "latitud": c.latitud if c.latitud is not None else -31.7766,
        "longitud": c.longitud if c.longitud is not None else -63.8011,
        "hectareas_totales": float(c.hectareas_totales),
        "hectareas_productivas": float(c.hectareas_totales * 0.95),
        "lotes_count": lotes_count,
    }


def lote_to_dict(l: Lote, campo_nombre: str = "Campo General") -> dict:
    tenencia_str = l.tenencia_tipo.value if hasattr(l.tenencia_tipo, "value") else str(l.tenencia_tipo or "propio")
    r_real = float(l.qq_ha_real) if l.qq_ha_real is not None else 0.0
    prod_qq = float(l.produccion_total_qq) if l.produccion_total_qq is not None else (float(l.superficie_productiva_ha) * r_real)

    return {
        "id": str(l.id),
        "campo_id": str(l.campo_id) if l.campo_id else "campo-001",
        "campo_nombre": campo_nombre,
        "nombre": l.nombre,
        "superficie_total_ha": float(l.superficie_total_ha),
        "superficie_productiva_ha": float(l.superficie_productiva_ha),
        "tenencia_tipo": tenencia_str,
        "tenencia_label": "Propio" if tenencia_str == "propio" else "Alquilado",
        "costo_alquiler_usd_ha": float(l.costo_alquiler_usd_ha) if l.costo_alquiler_usd_ha is not None else 0.0,
        "vencimiento_alquiler": str(l.vencimiento_alquiler) if l.vencimiento_alquiler else None,
        "notas_alquiler": l.notas_alquiler or "Contrato de arrendamiento rural.",
        "cultivo_anterior": l.cultivo_anterior or "Trigo 24/25",
        "cultivo_actual": l.cultivo_actual or "Soja 1ra",
        "cultivo_planificado": l.cultivo_planificado or "Maíz Tardío 26/27",
        "tipo_suelo": l.tipo_suelo or "Argiudol Típico",
        "qq_ha_estimado": float(l.qq_ha_estimado) if l.qq_ha_estimado is not None else 0.0,
        "qq_ha_real": r_real,
        "produccion_total_qq": prod_qq,
        "produccion_total_t": prod_qq / 10.0,
        "observaciones": l.observaciones or "",
        "estado_productivo": "en_crecimiento",
        "estado_productivo_label": "En Crecimiento",
    }


def instalacion_to_dict(inst: Instalacion, campo_nombre: str = "Campo General") -> dict:
    tipo_str = inst.tipo or "casa"
    tipo_labels = {
        "casa": "🏡 Casa Principal",
        "galpon": "🚜 Galpón Maquinarias",
        "pozo_bomba": "⚡ Pozo / Bomba Riego",
        "deposito": "📦 Depósito Insumos",
    }
    return {
        "id": str(inst.id),
        "campo_id": str(inst.campo_id),
        "campo_nombre": campo_nombre,
        "nombre": inst.nombre,
        "tipo": tipo_str,
        "tipo_label": tipo_labels.get(tipo_str, "🏡 Instalación"),
        "ubicacion_notas": inst.ubicacion_notas or "",
    }


def document_to_dict(doc: ServiceDocument) -> dict:
    doc_type_str = doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type)
    doc_type_labels = {
        "factura": "📄 Factura",
        "recibo": "🧾 Recibo",
        "presupuesto": "📋 Presupuesto",
        "contrato": "📜 Contrato / Póliza",
        "comprobante_pago": "💳 Comprobante de Pago",
        "otro": "📁 Documento",
    }
    size_formatted = f"{doc.size_bytes / (1024 * 1024):.2f} MB" if doc.size_bytes >= 1024 * 1024 else f"{doc.size_bytes / 1024:.1f} KB"
    return {
        "id": str(doc.id),
        "cliente_id": str(doc.cliente_id),
        "servicio_id": str(doc.servicio_id) if doc.servicio_id else None,
        "servicio_vencimiento_id": str(doc.servicio_vencimiento_id) if doc.servicio_vencimiento_id else None,
        "document_type": doc_type_str,
        "document_type_label": doc_type_labels.get(doc_type_str, doc_type_str.title()),
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "size_bytes": doc.size_bytes,
        "size_formatted": size_formatted,
        "sha256_hash": doc.sha256_hash,
        "uploaded_at": doc.uploaded_at.strftime("%d/%m/%Y %H:%M") if doc.uploaded_at else "",
        "notes": doc.notes or "",
        "estado": doc.estado,
        "download_url": f"/servicios/documentos/{doc.id}/descargar",
    }


def vencimiento_to_dict(v: ServicioVencimiento) -> dict:
    est_str = v.estado.value if hasattr(v.estado, "value") else str(v.estado)
    docs = [document_to_dict(d) for d in (v.documentos or []) if d.estado == "activo"]
    return {
        "id": str(v.id),
        "cliente_id": str(v.cliente_id) if v.cliente_id else None,
        "servicio_instalado_id": str(v.servicio_instalado_id) if v.servicio_instalado_id else None,
        "concepto": v.concepto,
        "periodo_referencia": v.periodo_referencia or "",
        "monto_ars": float(v.monto_ars),
        "monto_usd": float(v.monto_usd),
        "fecha_vencimiento": str(v.fecha_vencimiento),
        "fecha_vencimiento_fmt": v.fecha_vencimiento.strftime("%d/%m/%Y") if v.fecha_vencimiento else "",
        "fecha_pago": str(v.fecha_pago) if v.fecha_pago else None,
        "fecha_pago_fmt": v.fecha_pago.strftime("%d/%m/%Y") if v.fecha_pago else "",
        "estado": est_str,
        "estado_label": est_str.replace("_", " ").title(),
        "comprobante_url": v.comprobante_url or "",
        "payment_link": v.payment_link or "",
        "payment_link_domain": get_display_domain(v.payment_link) if v.payment_link else "",
        "documentos": docs,
        "has_documentos": len(docs) > 0,
    }


import calendar


def get_months_for_frecuencia(frecuencia: Any) -> int:
    val = frecuencia.value if hasattr(frecuencia, "value") else str(frecuencia)
    val = val.lower()
    if val == "mensual":
        return 1
    elif val == "bimensual":
        return 2
    elif val == "trimestral":
        return 3
    elif val == "semestral":
        return 6
    elif val in ["anual", "1_anio", "1_año"]:
        return 12
    elif val in ["2_anios", "2_años", "dos_anios"]:
        return 24
    elif val in ["3_anios", "3_años", "tres_anios"]:
        return 36
    return 1


def add_months_to_date(dt: date, months: int) -> date:
    year = dt.year + (dt.month + months - 1) // 12
    month = (dt.month + months - 1) % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return date(year, month, day)


def advance_servicio_vencimiento_date(dt: date, frecuencia: Any) -> date:
    months = get_months_for_frecuencia(frecuencia)
    return add_months_to_date(dt, months)


def servicio_to_dict(s: ServicioInstalado, campo_nombre: str = "Campo General", inst_nombre: str = "Instalación General") -> dict:
    tipo_str = s.tipo_servicio.value if hasattr(s.tipo_servicio, "value") else str(s.tipo_servicio)
    frec_str = s.frecuencia_pago.value if hasattr(s.frecuencia_pago, "value") else str(s.frecuencia_pago)
    est_str = s.estado.value if hasattr(s.estado, "value") else str(s.estado)

    tipo_labels = {
        "luz_rural": "⚡ Luz Rural",
        "internet": "📡 Internet Satelital",
        "combustible": "🛢️ Combustible Diesel",
        "mantenimiento": "🔧 Mantenimiento",
        "impuesto_tasa": "🏛️ Tasa Vial",
    }

    frec_labels = {
        "mensual": "Mensual (cada 1 mes)",
        "trimestral": "Trimestral (cada 3 meses)",
        "semestral": "Semestral (cada 6 meses)",
        "anual": "Anual (por 1 año)",
        "2_anios": "Por 2 años",
        "3_anios": "Por 3 años",
        "bimensual": "Bimensual",
        "eventual": "Eventual",
    }

    vencs = [vencimiento_to_dict(v) for v in (s.vencimientos or [])]
    docs = [document_to_dict(d) for d in (s.documentos or []) if d.estado == "activo"]

    meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    periodo_sugerido = f"{meses_es[s.fecha_vencimiento.month - 1]} {s.fecha_vencimiento.year}" if s.fecha_vencimiento else "Período Actual"

    return {
        "id": str(s.id),
        "campo_id": str(s.campo_id),
        "campo_nombre": campo_nombre,
        "instalacion_id": str(s.instalacion_id) if s.instalacion_id else None,
        "instalacion_nombre": inst_nombre,
        "tipo_servicio": tipo_str,
        "tipo_servicio_label": tipo_labels.get(tipo_str, tipo_str.replace("_", " ").title()),
        "concepto": s.concepto,
        "proveedor": s.proveedor,
        "frecuencia_pago": frec_str,
        "frecuencia_label": frec_labels.get(frec_str, frec_str.replace("_", " ").title()),
        "periodo_sugerido": periodo_sugerido,
        "monto_estimado_ars": float(s.monto_estimado_ars),
        "monto_real_ars": float(s.monto_real_ars),
        "monto_usd": float(s.monto_usd),
        "fecha_vencimiento": str(s.fecha_vencimiento),
        "estado": est_str,
        "estado_label": est_str.replace("_", " ").title(),
        "comprobante_url": s.comprobante_url or "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80",
        "payment_portal_url": s.payment_portal_url or "",
        "payment_portal_domain": get_display_domain(s.payment_portal_url) if s.payment_portal_url else "",
        "payment_reference": s.payment_reference or "",
        "observaciones": s.observaciones or "",
        "vencimientos": vencs,
        "documentos": docs,
        "vencimientos_count": len(vencs),
        "documentos_count": len(docs),
    }


async def fetch_campos_dicts(db: AsyncSession, cliente_id: Optional[uuid.UUID] = None) -> List[dict]:
    stmt = select(Campo)
    if cliente_id:
        stmt = stmt.where(Campo.cliente_id == cliente_id)
    res_c = await db.execute(stmt)
    campos = res_c.scalars().all()
    if not campos:
        return []
    res_l = await db.execute(select(Lote))
    lotes = res_l.scalars().all()
    counts = {}
    for l in lotes:
        c_id = str(l.campo_id)
        counts[c_id] = counts.get(c_id, 0) + 1
    return [campo_to_dict(c, counts.get(str(c.id), 0)) for c in campos]


async def fetch_lotes_dicts(db: AsyncSession) -> List[dict]:
    res_l = await db.execute(select(Lote))
    lotes = res_l.scalars().all()
    if not lotes:
        return []
    res_c = await db.execute(select(Campo))
    campos_map = {str(c.id): c.nombre for c in res_c.scalars().all()}
    return [lote_to_dict(l, campos_map.get(str(l.campo_id), "Campo General")) for l in lotes]


async def fetch_instalaciones_dicts(db: AsyncSession) -> List[dict]:
    res_i = await db.execute(select(Instalacion))
    instalaciones = res_i.scalars().all()
    if not instalaciones:
        return []
    res_c = await db.execute(select(Campo))
    campos_map = {str(c.id): c.nombre for c in res_c.scalars().all()}
    return [instalacion_to_dict(i, campos_map.get(str(i.campo_id), "Campo General")) for i in instalaciones]


async def fetch_servicios_dicts(db: AsyncSession, cliente_id: Optional[uuid.UUID] = None) -> List[dict]:
    stmt = select(ServicioInstalado).options(
        selectinload(ServicioInstalado.vencimientos).selectinload(ServicioVencimiento.documentos),
        selectinload(ServicioInstalado.documentos),
    )
    if cliente_id:
        stmt = stmt.where(ServicioInstalado.cliente_id == cliente_id)
    res_s = await db.execute(stmt)
    servicios = res_s.scalars().all()
    if not servicios:
        return []
    res_c = await db.execute(select(Campo))
    campos_map = {str(c.id): c.nombre for c in res_c.scalars().all()}
    res_i = await db.execute(select(Instalacion))
    inst_map = {str(i.id): i.nombre for i in res_i.scalars().all()}
    return [servicio_to_dict(s, campos_map.get(str(s.campo_id), "Campo General"), inst_map.get(str(s.instalacion_id), "Instalación General")) for s in servicios]


# ----------------------------------------------------------------------
# Helpers de Autenticación y Campo Activo por Sesión / DB
# ----------------------------------------------------------------------

async def get_current_user_from_session(request: Request, db: AsyncSession) -> Optional[dict]:
    """Obtiene el usuario autenticado consultando PostgreSQL por el user_id de la sesión."""
    if hasattr(request.state, "user") and request.state.user is not None:
        return request.state.user

    user_id_raw = request.session.get("user_id") or request.headers.get("x-user-id") or request.cookies.get("session_user_id")

    if not user_id_raw:
        request.state.user = None
        return None

    user_obj = None
    try:
        u_uuid = get_uuid(str(user_id_raw))
        res = await db.execute(select(Usuario).where(Usuario.id == u_uuid))
        user_obj = res.scalars().first()
    except Exception:
        user_obj = None

    if not user_obj:
        request.state.user = None
        return None

    user_dict = {
        "id": str(user_obj.id),
        "nombre": user_obj.nombre,
        "email": user_obj.email,
        "password_hash": user_obj.password_hash,
        "rol": user_obj.rol,
        "rol_label": user_obj.rol.value if hasattr(user_obj.rol, "value") else str(user_obj.rol),
        "cliente_id": str(user_obj.cliente_id) if user_obj.cliente_id else DEMO_CLIENTE["id"],
        "cliente_nombre": DEMO_CLIENTE["nombre"],
    }
    request.state.user = user_dict
    return user_dict


async def get_campo_activo_db(request: Request, db: AsyncSession) -> dict:
    """Obtiene el Campo Activo consultando la base de datos PostgreSQL."""
    if hasattr(request.state, "campo_activo"):
        return request.state.campo_activo

    campo_id_raw = request.session.get("campo_activo_id")
    campo_obj = None

    if campo_id_raw:
        try:
            c_uuid = get_uuid(str(campo_id_raw))
            res = await db.execute(select(Campo).where(Campo.id == c_uuid))
            campo_obj = res.scalars().first()
        except Exception:
            campo_obj = None

    if not campo_obj:
        res = await db.execute(select(Campo).limit(1))
        campo_obj = res.scalars().first()
        if campo_obj:
            request.session["campo_activo_id"] = str(campo_obj.id)

    if campo_obj:
        res_l = await db.execute(select(Lote).where(Lote.campo_id == campo_obj.id))
        lotes_c = res_l.scalars().all()
        result = {
            "id": str(campo_obj.id),
            "nombre": campo_obj.nombre,
            "ubicacion": campo_obj.ubicacion or "Laguna Larga, Córdoba",
            "localidad_referencia": campo_obj.localidad_referencia or "Laguna Larga, Córdoba",
            "latitud": campo_obj.latitud if campo_obj.latitud is not None else -31.7766,
            "longitud": campo_obj.longitud if campo_obj.longitud is not None else -63.8011,
            "hectareas_totales": float(campo_obj.hectareas_totales),
            "hectareas_productivas": float(campo_obj.hectareas_totales * 0.95),
            "lotes_count": len(lotes_c),
        }
    else:
        result = {
            "id": None,
            "nombre": "Sin Campo Configurado",
            "ubicacion": "-",
            "localidad_referencia": "-",
            "latitud": -31.7766,
            "longitud": -63.8011,
            "hectareas_totales": 0.0,
            "hectareas_productivas": 0.0,
            "lotes_count": 0,
        }

    request.state.campo_activo = result
    return result


# ----------------------------------------------------------------------
# Rutas de Autenticación & Selección de Campo Activo
# ----------------------------------------------------------------------

@app.post("/cambiar-campo-activo")
async def cambiar_campo_activo(
    request: Request,
    campo_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Cambia el campo activo de trabajo para la sesión."""
    campos = await fetch_campos_dicts(db)
    campo_sel = next((c for c in campos if c["id"] == campo_id), None)
    if campo_sel:
        request.session["campo_activo_id"] = campo_sel["id"]

    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if user:
        if user["rol"] == RolUsuario.OPERARIO_CAMPO:
            return RedirectResponse("/campo", status_code=status.HTTP_303_SEE_OTHER)
        elif user["rol"] == RolUsuario.ADMINISTRADOR_FINANZAS:
            return RedirectResponse("/servicios/vencimientos", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "next_url": next or "/",
            "error": None,
            "demo_cliente": DEMO_CLIENTE,
        },
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form("/"),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Usuario).where(Usuario.email == email))
    user_obj = res.scalars().first()

    if not user_obj or not verify_password(password, user_obj.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "next_url": next,
                "error": "Credenciales inválidas. Por favor intenta de nuevo.",
                "email": email,
                "demo_cliente": DEMO_CLIENTE,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user_dict = {
        "id": str(user_obj.id),
        "nombre": user_obj.nombre,
        "email": user_obj.email,
        "password_hash": user_obj.password_hash,
        "rol": user_obj.rol,
        "rol_label": user_obj.rol.value if hasattr(user_obj.rol, "value") else str(user_obj.rol),
        "cliente_nombre": DEMO_CLIENTE["nombre"],
    }

    request.session["user_id"] = str(user_obj.id)
    campos = await fetch_campos_dicts(db)
    if campos:
        request.session["campo_activo_id"] = campos[0]["id"]

    target_url = next if next and next != "/" else None
    if not target_url:
        if user_dict["rol"] == RolUsuario.OPERARIO_CAMPO:
            target_url = "/campo"
        elif user_dict["rol"] == RolUsuario.ADMINISTRADOR_FINANZAS:
            target_url = "/servicios/vencimientos"
        else:
            target_url = "/"

    return RedirectResponse(target_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/descargar-guia")
@app.get("/manual-pdf")
def descargar_guia_pdf():
    pdf_path = os.path.join(BASE_DIR, "Manual_Usuario_EduAgro.pdf")
    if os.path.exists(pdf_path):
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename="Manual_Usuario_EduAgro.pdf",
            content_disposition_type="inline"
        )
    return HTMLResponse("<h1>Manual PDF no encontrado</h1>", status_code=404)


# ----------------------------------------------------------------------
# Portal de Entrada por Operador & Dashboard Familiar Gerencial
# ----------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "marca": "EduAgro",
        "cliente": DEMO_CLIENTE["nombre"],
        "ubicacion": DEMO_CLIENTE["ubicacion"],
        "mode": "local",
    }


@app.get("/", response_class=HTMLResponse)
async def read_portal_entrada(request: Request, db: AsyncSession = Depends(get_db)):
    """Portal de entrada por operador/área. Renderiza únicamente el portal de entrada."""
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )

    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)
    servicios = await fetch_servicios_dicts(db)

    lotes_campo_activo = [l for l in lotes if l["campo_id"] == campo_activo["id"]]
    servicios_vencidos_count = len([s for s in servicios if s.get("estado") == "vencido"])

    from app.services.mercado import obtener_snapshot_precios_mercado
    snapshot = await obtener_snapshot_precios_mercado(db, cultivos=["soja"])
    dolar_ref = float(snapshot[0].get("dolar_referencia", 1486.00)) if snapshot else 1486.00
    dolar_info = {
        "monto": dolar_ref,
        "fuente": snapshot[0].get("fuente", "Dólar CAC Rosario (BCR)") if snapshot else "Dólar CAC Rosario (BCR)",
        "fecha": snapshot[0].get("fecha", str(date.today())) if snapshot else str(date.today()),
        "es_hoy": snapshot[0].get("es_hoy", True) if snapshot else True,
        "es_fallback": snapshot[0].get("es_fallback", False) if snapshot else False,
    }

    return templates.TemplateResponse(
        request=request,
        name="portal_entrada.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "lotes_count": len(lotes_campo_activo),
            "weather": weather_data,
            "servicios_vencidos_count": servicios_vencidos_count,
            "cotizacion_dolar": dolar_ref,
            "cotizacion_dolar_info": dolar_info,
            "campania_activa": "2025-2026",
        },
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard_familiar(
    request: Request,
    perfil: Optional[str] = "dueno",
    db: AsyncSession = Depends(get_db),
):
    """Dashboard Gerencial Consolidado (Vista secundaria)."""
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )

    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)
    servicios = await fetch_servicios_dicts(db)
    lotes_campo_activo = [l for l in lotes if l.get("campo_id") == campo_activo.get("id")]

    ha_totales = campo_activo.get("hectareas_totales", 0.0)
    ha_soja = sum(l.get("superficie_productiva_ha", 0.0) for l in lotes_campo_activo if "soja" in l.get("cultivo_actual", "").lower())
    ha_trigo = sum(l.get("superficie_productiva_ha", 0.0) for l in lotes_campo_activo if "trigo" in l.get("cultivo_actual", "").lower())

    gastos_ars = sum(s.get("monto_real_ars", 0.0) for s in servicios)
    gastos_usd = sum(s.get("monto_usd", 0.0) for s in servicios)

    vencimientos = [s for s in servicios if s.get("estado") in ["vencido", "pendiente"]]
    toneladas_estimadas = sum(l.get("produccion_total_t", 0.0) for l in lotes_campo_activo)

    from app.services.mercado import obtener_snapshot_precios_mercado
    snapshot = await obtener_snapshot_precios_mercado(db, cultivos=["soja"])
    dolar_ref = float(snapshot[0].get("dolar_referencia", 1486.00)) if snapshot else 1486.00
    dolar_info = {
        "monto": dolar_ref,
        "fuente": snapshot[0].get("fuente", "Dólar CAC Rosario (BCR)") if snapshot else "Dólar CAC Rosario (BCR)",
        "fecha": snapshot[0].get("fecha", str(date.today())) if snapshot else str(date.today()),
        "es_hoy": snapshot[0].get("es_hoy", True) if snapshot else True,
        "es_fallback": snapshot[0].get("es_fallback", False) if snapshot else False,
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard_familiar.html",
        context={
            "user": user,
            "perfil": perfil,
            "campo_activo": campo_activo,
            "campos": campos,
            "lotes_campo": lotes_campo_activo,
            "weather": weather_data,
            "campania_activa": "2025-2026",
            "cotizacion_dolar": dolar_ref,
            "cotizacion_dolar_info": dolar_info,
            "ha_totales": ha_totales,
            "ha_soja": ha_soja,
            "ha_trigo": ha_trigo,
            "lluvia_mes": 0.0,
            "gastos_usd": f"{gastos_usd:,.2f}",
            "gastos_ars": f"{gastos_ars:,.2f}",
            "toneladas_estimadas": f"{toneladas_estimadas:,.1f}",
            "vencimientos": vencimientos,
        },
    )


@app.get("/campo", response_class=HTMLResponse)
async def read_modo_campo(
    request: Request,
    campo_id: Optional[str] = None,
    estado_filtro: Optional[str] = "todas",
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/campo", status_code=status.HTTP_303_SEE_OTHER)

    campos = await fetch_campos_dicts(db)
    if campo_id:
        campo_sel = next((c for c in campos if c["id"] == campo_id), None)
        if campo_sel:
            request.session["campo_activo_id"] = campo_sel["id"]

    campo_activo = await get_campo_activo_db(request, db)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )

    lotes = await fetch_lotes_dicts(db)
    lotes_campo_activo = [l for l in lotes if l["campo_id"] == campo_activo["id"]]

    tareas_campo = [t for t in TAREAS_STORE if t["campo_id"] == campo_activo["id"]]
    pendientes_count = len([t for t in tareas_campo if t["estado"] == "pendiente"])
    en_curso_count = len([t for t in tareas_campo if t["estado"] == "en_curso"])
    hechas_count = len([t for t in tareas_campo if t["estado"] == "hecha"])

    if estado_filtro in ["pendiente", "en_curso", "hecha"]:
        tareas_filtradas = [t for t in tareas_campo if t["estado"] == estado_filtro]
    else:
        tareas_filtradas = tareas_campo

    return templates.TemplateResponse(
        request=request,
        name="modo_campo.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "lotes_campo": lotes_campo_activo,
            "weather": weather_data,
            "tareas": tareas_filtradas,
            "estado_filtro": estado_filtro,
            "pendientes_count": pendientes_count,
            "en_curso_count": en_curso_count,
            "hechas_count": hechas_count,
        },
    )


@app.post("/campo/tareas/{tarea_id}/iniciar")
async def iniciar_tarea_campo(request: Request, tarea_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    tarea = next((t for t in TAREAS_STORE if t["id"] == tarea_id), None)
    if tarea:
        tarea["estado"] = "en_curso"
        tarea["estado_label"] = "En Curso"

    referer = request.headers.get("referer", "/campo")
    return RedirectResponse(referer, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/campo/tareas/{tarea_id}/completar")
async def completar_tarea_campo(request: Request, tarea_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    tarea = next((t for t in TAREAS_STORE if t["id"] == tarea_id), None)
    if tarea:
        tarea["estado"] = "hecha"
        tarea["estado_label"] = "Hecha"

    referer = request.headers.get("referer", "/campo")
    return RedirectResponse(referer, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/campo/acciones/lluvia")
async def registrar_lluvia_rapida(
    request: Request,
    campo_id: str = Form(...),
    lote_id: Optional[str] = Form(None),
    milimetros: float = Form(...),
    observaciones: Optional[str] = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)
    campo_sel = next((c for c in campos if c["id"] == campo_id), None)
    lote_sel = next((l for l in lotes if l["id"] == lote_id), None) if lote_id else None

    nueva_tarea = {
        "id": f"tarea-00{len(TAREAS_STORE) + 1}",
        "campo_id": campo_id,
        "campo_nombre": campo_sel["nombre"] if campo_sel else "Campo General",
        "lote_id": lote_id,
        "lote_nombre": lote_sel["nombre"] if lote_sel else "Campo General",
        "tipo": "lluvia_suelo",
        "tipo_label": "🌧️ Lluvia / Suelo",
        "titulo": f"Registro de Lluvia ({milimetros} mm)",
        "responsable": user.get("nombre", "Operario Campo"),
        "prioridad": "media",
        "prioridad_label": "Media",
        "estado": "hecha",
        "estado_label": "Hecha",
        "fecha": "2026-07-28",
        "observaciones": observaciones or f"Lluvia de {milimetros} mm registrada desde Modo Campo.",
        "valor_registrado": f"{milimetros} mm",
    }
    TAREAS_STORE.insert(0, nueva_tarea)

    return RedirectResponse("/campo", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/campo/acciones/incidencia")
async def registrar_incidencia_rapida(
    request: Request,
    campo_id: str = Form(...),
    lote_id: Optional[str] = Form(None),
    titulo: str = Form(...),
    prioridad: str = Form("alta"),
    observaciones: Optional[str] = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)
    campo_sel = next((c for c in campos if c["id"] == campo_id), None)
    lote_sel = next((l for l in lotes if l["id"] == lote_id), None) if lote_id else None

    nueva_incidencia = {
        "id": f"tarea-00{len(TAREAS_STORE) + 1}",
        "campo_id": campo_id,
        "campo_nombre": campo_sel["nombre"] if campo_sel else "Campo General",
        "lote_id": lote_id,
        "lote_nombre": lote_sel["nombre"] if lote_sel else "Campo General",
        "tipo": "incidencia",
        "tipo_label": "⚠️ Novedad / Incidencia",
        "titulo": titulo.strip(),
        "responsable": user.get("nombre", "Operario Campo"),
        "prioridad": prioridad,
        "prioridad_label": prioridad.title(),
        "estado": "pendiente",
        "estado_label": "Pendiente",
        "fecha": "2026-07-28",
        "observaciones": observaciones or "Incidencia u observación registrada desde Modo Campo.",
        "valor_registrado": "Reporte de Campo",
    }
    TAREAS_STORE.insert(0, nueva_incidencia)

    return RedirectResponse("/campo", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/campo/acciones/stock")
async def registrar_movimiento_stock(
    request: Request,
    campo_id: str = Form(...),
    insumo: str = Form(...),
    cantidad: float = Form(...),
    unidad: str = Form("litros"),
    observaciones: Optional[str] = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campos = await fetch_campos_dicts(db)
    campo_sel = next((c for c in campos if c["id"] == campo_id), None)

    nuevo_stock = {
        "id": f"tarea-00{len(TAREAS_STORE) + 1}",
        "campo_id": campo_id,
        "campo_nombre": campo_sel["nombre"] if campo_sel else "Campo General",
        "lote_id": None,
        "lote_nombre": "Galpón / Depósito",
        "tipo": "stock_insumos",
        "tipo_label": "📦 Stock e Insumos",
        "titulo": f"Consumo/Retiro: {insumo.strip()}",
        "responsable": user.get("nombre", "Operario Campo"),
        "prioridad": "media",
        "prioridad_label": "Media",
        "estado": "hecha",
        "estado_label": "Hecha",
        "fecha": "2026-07-28",
        "observaciones": observaciones or f"Retiro registrado de {cantidad} {unidad} de {insumo}.",
        "valor_registrado": f"{cantidad} {unidad}",
    }
    TAREAS_STORE.insert(0, nuevo_stock)

    return RedirectResponse("/campo", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/campo/tareas/nueva")
async def crear_tarea_campo(
    request: Request,
    campo_id: str = Form(...),
    lote_id: Optional[str] = Form(None),
    tipo: str = Form("siembra"),
    titulo: str = Form(...),
    responsable: str = Form(...),
    prioridad: str = Form("media"),
    observaciones: Optional[str] = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)
    campo_sel = next((c for c in campos if c["id"] == campo_id), None)
    lote_sel = next((l for l in lotes if l["id"] == lote_id), None) if lote_id else None

    tipo_labels = {
        "siembra": "🌱 Siembra",
        "cosecha": "🚜 Cosecha",
        "stock_insumos": "📦 Stock e Insumos",
        "incidencia": "⚠️ Novedad / Incidencia",
        "revision_lote": "🔍 Monitoreo / Control Lote",
        "lluvia_suelo": "🌧️ Lluvia / Suelo",
    }

    nueva_tarea = {
        "id": f"tarea-00{len(TAREAS_STORE) + 1}",
        "campo_id": campo_id,
        "campo_nombre": campo_sel["nombre"] if campo_sel else "Campo General",
        "lote_id": lote_id,
        "lote_nombre": lote_sel["nombre"] if lote_sel else "Campo General",
        "tipo": tipo,
        "tipo_label": tipo_labels.get(tipo, "🌾 Labor Campo"),
        "titulo": titulo.strip(),
        "responsable": responsable.strip(),
        "prioridad": prioridad,
        "prioridad_label": prioridad.title(),
        "estado": "pendiente",
        "estado_label": "Pendiente",
        "fecha": "2026-07-28",
        "observaciones": observaciones or "Labor diaria de campo asignada.",
        "valor_registrado": "Programada",
    }
    TAREAS_STORE.insert(0, nueva_tarea)

    return RedirectResponse("/campo", status_code=status.HTTP_303_SEE_OTHER)


# ----------------------------------------------------------------------
# Módulo Productivo Central
# ----------------------------------------------------------------------

@app.get("/productivo/campos", response_class=HTMLResponse)
async def list_campos(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/productivo/campos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)

    ha_totales_suma = sum(c["hectareas_totales"] for c in campos)
    ha_productivas_suma = sum(l["superficie_productiva_ha"] for l in lotes)

    return templates.TemplateResponse(
        request=request,
        name="productivo_campos.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "ha_totales_suma": ha_totales_suma,
            "ha_productivas_suma": ha_productivas_suma,
        },
    )


@app.post("/productivo/campos")
async def create_campo(
    request: Request,
    nombre: str = Form(...),
    ubicacion: str = Form(...),
    latitud: Optional[float] = Form(None),
    longitud: Optional[float] = Form(None),
    hectareas_totales: float = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    c_uuid = uuid.uuid4()
    nuevo_campo = Campo(
        id=c_uuid,
        cliente_id=get_uuid(DEMO_CLIENTE["id"]),
        nombre=nombre.strip(),
        ubicacion=ubicacion.strip(),
        localidad_referencia=ubicacion.strip(),
        latitud=float(latitud) if latitud else -31.7766,
        longitud=float(longitud) if longitud else -63.8011,
        hectareas_totales=float(hectareas_totales),
    )
    db.add(nuevo_campo)
    await db.commit()

    request.session["campo_activo_id"] = str(c_uuid)
    return RedirectResponse("/productivo/campos", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/productivo/campos/{campo_id}/eliminar")
async def delete_campo(
    campo_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        c_uuid = uuid.UUID(campo_id)
        res = await db.execute(select(Campo).where(Campo.id == c_uuid))
        campo_obj = res.scalar_one_or_none()
        if campo_obj:
            await db.delete(campo_obj)
            await db.commit()
            
            # Limpiar de la sesión si era el campo activo
            if request.session.get("campo_activo_id") == campo_id:
                request.session.pop("campo_activo_id", None)
    except Exception as e:
        pass
    return RedirectResponse("/productivo/campos", status_code=status.HTTP_303_SEE_OTHER)


# ----------------------------------------------------------------------
# Módulo de Servicios Prestados / Trabajos a Terceros (FastAPI Routes)
# ----------------------------------------------------------------------

from app.models import (
    EquipoMaquinaria,
    ClienteTercero,
    ServicioPrestado,
    CobroServicioPrestado,
    PagoOperadorServicio,
)
from app.services.servicios_prestados_service import (
    fetch_resumen_servicios_prestados,
    create_servicio_prestado,
    create_equipo_maquinaria,
    create_cliente_tercero,
    registrar_cobro_servicio,
    registrar_pago_operador,
    cancelar_servicio_prestado,
    calcular_estado_cobro_dinamico,
    validar_permisos_usuario,
)


@app.get("/servicios-prestados", response_class=HTMLResponse)
async def servicios_prestados_list(
    request: Request,
    estado: Optional[str] = None,
    cliente_tercero_id: Optional[str] = None,
    maquinaria_id: Optional[str] = None,
    operador_id: Optional[str] = None,
    mensaje: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios-prestados", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")
    resumen = await fetch_resumen_servicios_prestados(db, cliente_id)

    # Cargar relaciones y catálogos
    res_terceros = await db.execute(select(ClienteTercero).where(ClienteTercero.cliente_id == cliente_id))
    clientes_terceros = res_terceros.scalars().all()

    res_maquinas = await db.execute(select(EquipoMaquinaria).where(EquipoMaquinaria.cliente_id == cliente_id))
    maquinarias = res_maquinas.scalars().all()

    res_ops = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente_id))
    operadores = res_ops.scalars().all()

    # Query principal con filtros
    query = select(ServicioPrestado).where(ServicioPrestado.cliente_id == cliente_id)
    if estado:
        query = query.where(ServicioPrestado.estado_operativo == estado)
    if cliente_tercero_id:
        try:
            query = query.where(ServicioPrestado.cliente_tercero_id == uuid.UUID(cliente_tercero_id))
        except ValueError:
            pass
    if maquinaria_id:
        try:
            query = query.where(ServicioPrestado.maquinaria_id == uuid.UUID(maquinaria_id))
        except ValueError:
            pass
    if operador_id:
        try:
            query = query.where(ServicioPrestado.operador_id == uuid.UUID(operador_id))
        except ValueError:
            pass

    query = query.order_by(ServicioPrestado.fecha_trabajo.desc())
    res_sp = await db.execute(query)
    servicios = res_sp.scalars().all()

    items = []
    for s in servicios:
        tercero = next((t for t in clientes_terceros if t.id == s.cliente_tercero_id), None)
        maquina = next((m for m in maquinarias if m.id == s.maquinaria_id), None)
        operador = next((o for o in operadores if o.id == s.operador_id), None)

        # Cobros acumulados
        res_c = await db.execute(
            select(func.coalesce(func.sum(CobroServicioPrestado.monto_cobrado), Decimal("0.00")))
            .where(CobroServicioPrestado.servicio_prestado_id == s.id)
        )
        total_cobrado = res_c.scalar_one()

        # Pagos a operador acumulados
        res_p = await db.execute(
            select(func.coalesce(func.sum(PagoOperadorServicio.monto_pagado), Decimal("0.00")))
            .where(PagoOperadorServicio.servicio_prestado_id == s.id)
        )
        total_pagado_op = res_p.scalar_one()

        est_cobro = calcular_estado_cobro_dinamico(
            s.monto_total_facturado, total_cobrado, s.pago_operador_negociado, total_pagado_op
        )

        items.append({
            "orden": s,
            "tercero_nombre": tercero.razon_social_nombre if tercero else "Desconocido",
            "maquina_nombre": maquina.nombre if maquina else "Desconocida",
            "operador_nombre": operador.nombre if operador else (operador.email if operador else "Desconocido"),
            "total_cobrado": float(total_cobrado),
            "estado_cobro": est_cobro,
        })

    return templates.TemplateResponse(
        "servicios_prestados_list.html",
        {
            "request": request,
            "user": user,
            "active_page": "servicios_prestados",
            "resumen": resumen,
            "items": items,
            "clientes_terceros": clientes_terceros,
            "maquinarias": maquinarias,
            "operadores": operadores,
            "filtro_estado": estado,
            "filtro_tercero": cliente_tercero_id,
            "filtro_maquinaria": maquinaria_id,
            "filtro_operador": operador_id,
            "mensaje": mensaje,
            "error": error,
        },
    )


@app.get("/servicios-prestados/clientes-terceros", response_class=HTMLResponse)
async def servicios_prestados_clientes_terceros_page(
    request: Request, db: AsyncSession = Depends(get_db)
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios-prestados", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")
    res_t = await db.execute(select(ClienteTercero).where(ClienteTercero.cliente_id == cliente_id))
    clientes_terceros = res_t.scalars().all()

    return templates.TemplateResponse(
        "servicios_prestados_clientes_terceros.html",
        {
            "request": request,
            "user": user,
            "active_page": "servicios_prestados",
            "clientes_terceros": clientes_terceros,
        },
    )


@app.post("/servicios-prestados/clientes-terceros")
async def servicios_prestados_clientes_terceros_create(
    request: Request,
    razon_social_nombre: str = Form(...),
    cuit_dni: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    localidad_direccion: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")
    await create_cliente_tercero(
        db, cliente_id, razon_social_nombre, cuit_dni, telefono, email, localidad_direccion
    )
    return RedirectResponse("/servicios-prestados/clientes-terceros", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/servicios-prestados/maquinarias", response_class=HTMLResponse)
async def servicios_prestados_maquinarias_page(
    request: Request, db: AsyncSession = Depends(get_db)
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios-prestados", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")
    res_m = await db.execute(select(EquipoMaquinaria).where(EquipoMaquinaria.cliente_id == cliente_id))
    maquinarias = res_m.scalars().all()

    return templates.TemplateResponse(
        "servicios_prestados_maquinarias.html",
        {
            "request": request,
            "user": user,
            "active_page": "servicios_prestados",
            "maquinarias": maquinarias,
        },
    )


@app.post("/servicios-prestados/maquinarias")
async def servicios_prestados_maquinarias_create(
    request: Request,
    nombre: str = Form(...),
    tipo_equipo: str = Form("pulverizadora"),
    marca_modelo: Optional[str] = Form(None),
    patente_serie: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")
    await create_equipo_maquinaria(
        db, cliente_id, nombre, tipo_equipo, marca_modelo, patente_serie
    )
    return RedirectResponse("/servicios-prestados/maquinarias", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/servicios-prestados/nuevo", response_class=HTMLResponse)
async def servicios_prestados_nuevo_form(
    request: Request, error: Optional[str] = None, db: AsyncSession = Depends(get_db)
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios-prestados/nuevo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")

    res_t = await db.execute(select(ClienteTercero).where(ClienteTercero.cliente_id == cliente_id))
    clientes_terceros = res_t.scalars().all()

    res_m = await db.execute(select(EquipoMaquinaria).where(EquipoMaquinaria.cliente_id == cliente_id))
    maquinarias = res_m.scalars().all()

    res_u = await db.execute(select(Usuario).where(Usuario.cliente_id == cliente_id))
    operadores = res_u.scalars().all()

    return templates.TemplateResponse(
        "servicios_prestados_form.html",
        {
            "request": request,
            "user": user,
            "active_page": "servicios_prestados",
            "clientes_terceros": clientes_terceros,
            "maquinarias": maquinarias,
            "operadores": operadores,
            "hoy": date.today().isoformat(),
            "error": error,
        },
    )


@app.post("/servicios-prestados/nuevo")
async def servicios_prestados_nuevo_post(
    request: Request,
    cliente_tercero_id: str = Form(...),
    maquinaria_id: str = Form(...),
    operador_id: str = Form(...),
    fecha_trabajo: str = Form(...),
    establecimiento_lote_libre: str = Form(...),
    superficie_ha: str = Form(...),
    monto_total_facturado: str = Form(...),
    pago_operador_negociado: str = Form("0.00"),
    imputacion_uso_maquinaria: str = Form("0.00"),
    gastos_directos_informados: str = Form("0.00"),
    tipo_aplicacion: Optional[str] = Form(None),
    volumen_caldo_lha: Optional[str] = Form(None),
    insumos_aportados_por: str = Form("cliente"),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")

    # Validar permisos
    try:
        validar_permisos_usuario(user.get("rol"), "modificar_economia")
    except PermissionError as pe:
        return RedirectResponse(f"/servicios-prestados?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        orden = await create_servicio_prestado(
            db=db,
            cliente_id=cliente_id,
            cliente_tercero_id=uuid.UUID(cliente_tercero_id),
            maquinaria_id=uuid.UUID(maquinaria_id),
            operador_id=uuid.UUID(operador_id),
            fecha_trabajo=date.fromisoformat(fecha_trabajo),
            establecimiento_lote_libre=establecimiento_lote_libre,
            superficie_ha=Decimal(superficie_ha),
            monto_total_facturado=Decimal(monto_total_facturado),
            pago_operador_negociado=Decimal(pago_operador_negociado),
            imputacion_uso_maquinaria=Decimal(imputacion_uso_maquinaria),
            gastos_directos_informados=Decimal(gastos_directos_informados),
            tipo_aplicacion=tipo_aplicacion,
            volumen_caldo_lha=Decimal(volumen_caldo_lha) if volumen_caldo_lha else None,
            insumos_aportados_por=insumos_aportados_por,
            observaciones=observaciones,
            creado_por_usuario_id=uuid.UUID(user.get("id")) if user.get("id") else None,
        )
        return RedirectResponse(f"/servicios-prestados/{orden.id}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as ve:
        return RedirectResponse(f"/servicios-prestados/nuevo?error={str(ve).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/servicios-prestados/nuevo?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/servicios-prestados/{servicio_id}", response_class=HTMLResponse)
async def servicios_prestados_detail(
    request: Request,
    servicio_id: uuid.UUID,
    error: Optional[str] = None,
    mensaje: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios-prestados", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")
    orden = await db.get(ServicioPrestado, servicio_id)
    if not orden or orden.cliente_id != cliente_id:
        return RedirectResponse("/servicios-prestados?error=Orden+no+encontrada", status_code=status.HTTP_303_SEE_OTHER)

    tercero = await db.get(ClienteTercero, orden.cliente_tercero_id)
    maquina = await db.get(EquipoMaquinaria, orden.maquinaria_id)
    operador = await db.get(Usuario, orden.operador_id)

    # Cobros y pagos
    res_c = await db.execute(
        select(CobroServicioPrestado).where(CobroServicioPrestado.servicio_prestado_id == servicio_id).order_by(CobroServicioPrestado.fecha_cobro.desc())
    )
    cobros = res_c.scalars().all()

    res_p = await db.execute(
        select(PagoOperadorServicio).where(PagoOperadorServicio.servicio_prestado_id == servicio_id).order_by(PagoOperadorServicio.fecha_pago.desc())
    )
    pagos_operador = res_p.scalars().all()

    total_cobrado = sum(c.monto_cobrado for c in cobros)
    total_pagado_op = sum(p.monto_pagado for p in pagos_operador)

    est_cobro = calcular_estado_cobro_dinamico(
        orden.monto_total_facturado, total_cobrado, orden.pago_operador_negociado, total_pagado_op
    )

    return templates.TemplateResponse(
        "servicios_prestados_detail.html",
        {
            "request": request,
            "user": user,
            "active_page": "servicios_prestados",
            "orden": orden,
            "tercero": tercero,
            "maquina": maquina,
            "operador": operador,
            "cobros": cobros,
            "pagos_operador": pagos_operador,
            "total_cobrado": float(total_cobrado),
            "total_pagado_op": float(total_pagado_op),
            "estado_cobro": est_cobro,
            "hoy": date.today().isoformat(),
            "hoy_ts": int(datetime.now().timestamp()),
            "error": error,
            "mensaje": mensaje,
        },
    )


@app.post("/servicios-prestados/{servicio_id}/cobros")
async def servicios_prestados_registrar_cobro_post(
    request: Request,
    servicio_id: uuid.UUID,
    fecha_cobro: str = Form(...),
    monto_cobrado: str = Form(...),
    medio_pago: str = Form("transferencia"),
    numero_comprobante: Optional[str] = Form(None),
    clave_idempotencia: Optional[str] = Form(None),
    autorizacion_sobrepago: bool = Form(False),
    motivo_sobrepago: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")

    try:
        validar_permisos_usuario(user.get("rol"), "registrar_cobro")
    except PermissionError as pe:
        return RedirectResponse(f"/servicios-prestados/{servicio_id}?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        await registrar_cobro_servicio(
            db=db,
            cliente_id=cliente_id,
            servicio_prestado_id=servicio_id,
            fecha_cobro=date.fromisoformat(fecha_cobro),
            monto_cobrado=Decimal(monto_cobrado),
            medio_pago=medio_pago,
            numero_comprobante=numero_comprobante,
            clave_idempotencia=clave_idempotencia,
            registrado_por_usuario_id=uuid.UUID(user.get("id")) if user.get("id") else None,
            autorizacion_sobrepago=autorizacion_sobrepago,
            motivo_sobrepago=motivo_sobrepago,
        )
        return RedirectResponse(f"/servicios-prestados/{servicio_id}?mensaje=Cobro+registrado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/servicios-prestados/{servicio_id}?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/servicios-prestados/{servicio_id}/pagos-operador")
async def servicios_prestados_registrar_pago_operador_post(
    request: Request,
    servicio_id: uuid.UUID,
    fecha_pago: str = Form(...),
    monto_pagado: str = Form(...),
    medio_pago: str = Form("transferencia"),
    observaciones: Optional[str] = Form(None),
    clave_idempotencia: Optional[str] = Form(None),
    autorizacion_sobrepago: bool = Form(False),
    motivo_sobrepago: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")

    try:
        validar_permisos_usuario(user.get("rol"), "registrar_pago_operador")
    except PermissionError as pe:
        return RedirectResponse(f"/servicios-prestados/{servicio_id}?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        await registrar_pago_operador(
            db=db,
            cliente_id=cliente_id,
            servicio_prestado_id=servicio_id,
            fecha_pago=date.fromisoformat(fecha_pago),
            monto_pagado=Decimal(monto_pagado),
            medio_pago=medio_pago,
            observaciones=observaciones,
            clave_idempotencia=clave_idempotencia,
            registrado_por_usuario_id=uuid.UUID(user.get("id")) if user.get("id") else None,
            autorizacion_sobrepago=autorizacion_sobrepago,
            motivo_sobrepago=motivo_sobrepago,
        )
        return RedirectResponse(f"/servicios-prestados/{servicio_id}?mensaje=Pago+liquidado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/servicios-prestados/{servicio_id}?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/servicios-prestados/{servicio_id}/estado")
async def servicios_prestados_cambiar_estado_post(
    request: Request,
    servicio_id: uuid.UUID,
    nuevo_estado: str = Form(...),
    motivo_cambio: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")

    if nuevo_estado == "cancelado":
        try:
            validar_permisos_usuario(user.get("rol"), "modificar_economia")
            await cancelar_servicio_prestado(
                db=db,
                cliente_id=cliente_id,
                servicio_prestado_id=servicio_id,
                motivo_cancelacion=motivo_cambio or "Cancelado desde interfaz",
                actualizado_por_usuario_id=uuid.UUID(user.get("id")) if user.get("id") else None,
            )
            return RedirectResponse(f"/servicios-prestados/{servicio_id}?mensaje=Orden+cancelada+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
        except Exception as e:
            return RedirectResponse(f"/servicios-prestados/{servicio_id}?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    orden = await db.get(ServicioPrestado, servicio_id)
    if not orden or orden.cliente_id != cliente_id:
        return RedirectResponse("/servicios-prestados?error=Orden+no+encontrada", status_code=status.HTTP_303_SEE_OTHER)

    orden.estado_operativo = nuevo_estado
    if motivo_cambio:
        orden.observaciones = f"{orden.observaciones or ''} [{nuevo_estado.upper()}: {motivo_cambio.strip()}]".strip()
    orden.actualizado_por_usuario_id = uuid.UUID(user.get("id")) if user.get("id") else None

    await db.commit()
    return RedirectResponse(f"/servicios-prestados/{servicio_id}?mensaje=Estado+actualizado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/servicios-prestados/{servicio_id}/actualizacion-tecnica")
async def servicios_prestados_actualizacion_tecnica_post(
    request: Request,
    servicio_id: uuid.UUID,
    superficie_ha: str = Form(...),
    tipo_aplicacion: Optional[str] = Form(None),
    volumen_caldo_lha: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")
    orden = await db.get(ServicioPrestado, servicio_id)
    if not orden or orden.cliente_id != cliente_id:
        return RedirectResponse("/servicios-prestados?error=Orden+no+encontrada", status_code=status.HTTP_303_SEE_OTHER)

    # Permitido a operario_campo y admin por igual
    validar_permisos_usuario(user.get("rol"), "actualizar_ejecucion")

    orden.superficie_ha = Decimal(superficie_ha)
    if tipo_aplicacion is not None:
        orden.tipo_aplicacion = tipo_aplicacion.strip()
    if volumen_caldo_lha:
        orden.volumen_caldo_lha = Decimal(volumen_caldo_lha)
    if observaciones is not None:
        orden.observaciones = observaciones.strip()
    orden.actualizado_por_usuario_id = uuid.UUID(user.get("id")) if user.get("id") else None

    await db.commit()
    return RedirectResponse(f"/servicios-prestados/{servicio_id}?mensaje=Datos+técnicos+actualizados", status_code=status.HTTP_303_SEE_OTHER)


# ==============================================================================
# RUTAS DE INSUMOS Y ABASTECIMIENTO (EDUAGRO V3)
# ==============================================================================
from app.models import Insumo, InsumoLote, InsumoSaldoUbicacion, InsumoMovimiento, InsumoRecuento, InsumoReserva, StorageLocation, LaborCampo, ServicioPrestado
from app.enums import MonedaEnum, CategoriaInsumoEnum, UnidadMedidaInsumoEnum
from app.services.insumos_service import (
    registrar_compra_ingreso,
    registrar_stock_inicial,
    registrar_consumo_labor,
    registrar_consumo_servicio_prestado,
    registrar_transferencia_ubicaciones,
    registrar_recuento_inventario,
    aprobar_recuento_fisico,
    crear_reserva_insumo,
    liberar_reserva_insumo,
    verificar_disponibilidad_insumos,
    validar_permisos_insumos,
    crear_insumo_catalogo,
    editar_insumo_catalogo,
    cambiar_estado_insumo_catalogo,
)


# ------------------------------------------------------------------------------
# ABM CATÁLOGO DE INSUMOS
# ------------------------------------------------------------------------------

@app.get("/insumos/catalogo", response_class=HTMLResponse)
async def insumos_catalogo_list_get(
    request: Request,
    q: Optional[str] = None,
    cat: Optional[str] = None,
    mensaje: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    query = select(Insumo).where(Insumo.cliente_id == cliente_id).order_by(Insumo.nombre)

    if q and q.strip():
        query = query.where(Insumo.nombre.ilike(f"%{q.strip()}%"))
    if cat and cat.strip():
        try:
            cat_enum = CategoriaInsumoEnum(cat.strip())
            query = query.where(Insumo.categoria == cat_enum)
        except Exception:
            pass

    res = await db.execute(query)
    insumos_raw = res.scalars().all()

    insumos_list = []
    for ins in insumos_raw:
        res_lotes = await db.execute(
            select(func.count(InsumoLote.id)).where(InsumoLote.insumo_id == ins.id)
        )
        lotes_cnt = res_lotes.scalar_one() or 0

        insumos_list.append({
            "id": str(ins.id),
            "nombre": ins.nombre,
            "categoria": ins.categoria,
            "unidad_medida": ins.unidad_medida,
            "principio_activo_formula": ins.principio_activo_formula,
            "unidad_empaque": ins.unidad_empaque,
            "punto_pedido_minimo": float(ins.punto_pedido_minimo or 0),
            "activo": ins.activo,
            "lotes_count": lotes_cnt,
        })

    return templates.TemplateResponse(
        "insumos_catalogo.html",
        {
            "request": request,
            "user": user,
            "active_page": "insumos",
            "insumos": insumos_list,
            "categorias": list(CategoriaInsumoEnum),
            "filtro_q": q,
            "filtro_cat": cat,
            "mensaje": mensaje,
            "error": error,
        },
    )


@app.get("/insumos/catalogo/nuevo", response_class=HTMLResponse)
async def insumos_catalogo_nuevo_get(
    request: Request,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        validar_permisos_insumos(user.get("rol"), "crear_catalogo")
    except PermissionError as pe:
        return RedirectResponse(f"/insumos/catalogo?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "insumos_catalogo_form.html",
        {
            "request": request,
            "user": user,
            "active_page": "insumos",
            "insumo": None,
            "categorias": list(CategoriaInsumoEnum),
            "unidades": list(UnidadMedidaInsumoEnum),
            "has_movements": False,
            "error": error,
        },
    )


@app.post("/insumos/catalogo/nuevo")
async def insumos_catalogo_nuevo_post(
    request: Request,
    nombre: str = Form(...),
    categoria: str = Form(...),
    unidad_medida: str = Form(...),
    principio_activo_formula: Optional[str] = Form(None),
    concentracion: Optional[str] = Form(None),
    unidad_empaque: Optional[str] = Form(None),
    punto_pedido_minimo: str = Form("0.00"),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        validar_permisos_insumos(user.get("rol"), "crear_catalogo")
    except PermissionError as pe:
        return RedirectResponse(f"/insumos/catalogo?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        ins = await crear_insumo_catalogo(
            db=db,
            cliente_id=cliente_id,
            nombre=nombre,
            categoria=CategoriaInsumoEnum(categoria),
            unidad_medida=UnidadMedidaInsumoEnum(unidad_medida),
            principio_activo_formula=principio_activo_formula,
            concentracion=concentracion,
            unidad_empaque=unidad_empaque,
            punto_pedido_minimo=Decimal(punto_pedido_minimo) if punto_pedido_minimo else Decimal("0.0000"),
            usuario_rol=user.get("rol"),
        )
        return RedirectResponse(f"/insumos/catalogo?mensaje=Insumo+'{ins.nombre}'+creado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos/catalogo/nuevo?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/insumos/catalogo/{insumo_id}/editar", response_class=HTMLResponse)
async def insumos_catalogo_editar_get(
    request: Request,
    insumo_id: uuid.UUID,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        validar_permisos_insumos(user.get("rol"), "modificar_catalogo")
    except PermissionError as pe:
        return RedirectResponse(f"/insumos/catalogo?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    insumo = await db.get(Insumo, insumo_id)
    if not insumo or insumo.cliente_id != cliente_id:
        return RedirectResponse("/insumos/catalogo?error=Insumo+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    res_mov = await db.execute(
        select(func.count(InsumoMovimiento.id)).where(InsumoMovimiento.cliente_id == cliente_id, InsumoMovimiento.insumo_id == insumo_id)
    )
    has_movements = (res_mov.scalar_one() or 0) > 0

    return templates.TemplateResponse(
        "insumos_catalogo_form.html",
        {
            "request": request,
            "user": user,
            "active_page": "insumos",
            "insumo": insumo,
            "categorias": list(CategoriaInsumoEnum),
            "unidades": list(UnidadMedidaInsumoEnum),
            "has_movements": has_movements,
            "error": error,
        },
    )


@app.post("/insumos/catalogo/{insumo_id}/editar")
async def insumos_catalogo_editar_post(
    request: Request,
    insumo_id: uuid.UUID,
    nombre: str = Form(...),
    categoria: str = Form(...),
    unidad_medida: str = Form(...),
    principio_activo_formula: Optional[str] = Form(None),
    concentracion: Optional[str] = Form(None),
    unidad_empaque: Optional[str] = Form(None),
    punto_pedido_minimo: str = Form("0.00"),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        validar_permisos_insumos(user.get("rol"), "modificar_catalogo")
    except PermissionError as pe:
        return RedirectResponse(f"/insumos/catalogo?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        ins = await editar_insumo_catalogo(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            nombre=nombre,
            categoria=CategoriaInsumoEnum(categoria),
            unidad_medida=UnidadMedidaInsumoEnum(unidad_medida),
            principio_activo_formula=principio_activo_formula,
            concentracion=concentracion,
            unidad_empaque=unidad_empaque,
            punto_pedido_minimo=Decimal(punto_pedido_minimo) if punto_pedido_minimo else Decimal("0.0000"),
            usuario_rol=user.get("rol"),
        )
        return RedirectResponse(f"/insumos/catalogo?mensaje=Insumo+'{ins.nombre}'+actualizado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos/catalogo/{insumo_id}/editar?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/insumos/catalogo/{insumo_id}/desactivar")
async def insumos_catalogo_desactivar_post(
    request: Request,
    insumo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        validar_permisos_insumos(user.get("rol"), "desactivar_catalogo")
    except PermissionError as pe:
        return RedirectResponse(f"/insumos/catalogo?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        ins = await cambiar_estado_insumo_catalogo(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            nuevo_estado_activo=None,  # Toggle
            usuario_rol=user.get("rol"),
        )
        st_label = "activado" if ins.activo else "desactivado"
        return RedirectResponse(f"/insumos/catalogo?mensaje=Insumo+'{ins.nombre}'+{st_label}+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos/catalogo?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/insumos/stock-inicial")
async def insumos_stock_inicial_post(
    request: Request,
    insumo_id: uuid.UUID = Form(...),
    storage_location_id: uuid.UUID = Form(...),
    cantidad: str = Form(...),
    costo_unitario_usd: Optional[str] = Form(None),
    cotizacion_usd_ars: str = Form("1000.00"),
    numero_lote: Optional[str] = Form(None),
    fecha_vencimiento: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    clave_idempotencia: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        validar_permisos_insumos(user.get("rol"), "registrar_compra")
        f_venc = date.fromisoformat(fecha_vencimiento) if fecha_vencimiento and fecha_vencimiento.strip() else None
        c_usd = Decimal(costo_unitario_usd) if costo_unitario_usd and costo_unitario_usd.strip() else Decimal("0.0000")

        await registrar_stock_inicial(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            storage_location_id=storage_location_id,
            cantidad=Decimal(cantidad),
            costo_unitario_usd=c_usd,
            cotizacion_usd_ars=Decimal(cotizacion_usd_ars) if cotizacion_usd_ars else Decimal("1000.00"),
            numero_lote=numero_lote,
            fecha_vencimiento=f_venc,
            observaciones=observaciones,
            clave_idempotencia=clave_idempotencia or f"stk_init_{uuid.uuid4().hex[:6]}",
            usuario_rol=user.get("rol"),
        )
        return RedirectResponse("/insumos?mensaje=Stock+inicial+cargado+exitosamente+(sin+generar+egreso+financiero)", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/insumos/transferencia")
async def insumos_transferencia_post(
    request: Request,
    insumo_id: uuid.UUID = Form(...),
    storage_location_origen_id: uuid.UUID = Form(...),
    storage_location_destino_id: uuid.UUID = Form(...),
    cantidad: str = Form(...),
    observaciones: Optional[str] = Form(None),
    clave_idempotencia: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        validar_permisos_insumos(user.get("rol"), "transferir_stock")
        await registrar_transferencia_ubicaciones(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            storage_location_origen_id=storage_location_origen_id,
            storage_location_destino_id=storage_location_destino_id,
            cantidad=Decimal(cantidad),
            observaciones=observaciones,
            clave_idempotencia=clave_idempotencia or f"transf_{uuid.uuid4().hex[:6]}",
            usuario_rol=user.get("rol"),
        )
        return RedirectResponse("/insumos?mensaje=Transferencia+de+stock+registrada+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/insumos/recuento")
async def insumos_recuento_post(
    request: Request,
    insumo_id: uuid.UUID = Form(...),
    storage_location_id: uuid.UUID = Form(...),
    cantidad_observada: str = Form(...),
    motivo: str = Form(...),
    clave_idempotencia: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        rec = await registrar_recuento_inventario(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            storage_location_id=storage_location_id,
            cantidad_observada=Decimal(cantidad_observada),
            motivo=motivo,
            clave_idempotencia=clave_idempotencia or f"recuento_{uuid.uuid4().hex[:6]}",
            usuario_rol=user.get("rol"),
        )
        if user.get("rol") in ["admin", "administracion", "finanzas", "administrador_finanzas", "productor"]:
            await aprobar_recuento_fisico(db=db, cliente_id=cliente_id, recuento_id=rec.id, usuario_rol=user.get("rol"))
            return RedirectResponse("/insumos?mensaje=Recuento+f%C3%ADsico+registrado+y+ajuste+aplicado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
        else:
            return RedirectResponse("/insumos?mensaje=Recuento+f%C3%ADsico+registrado+pendiente+de+aprobaci%C3%B3n+administrativa", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/insumos/reserva")
async def insumos_reserva_post(
    request: Request,
    insumo_id: uuid.UUID = Form(...),
    storage_location_id: uuid.UUID = Form(...),
    cantidad_reservada: str = Form(...),
    destino_tipo: str = Form(...),
    destino_id: uuid.UUID = Form(...),
    fecha_expiracion: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        labor_id = destino_id if destino_tipo == "labor" else None
        servicio_id = destino_id if destino_tipo == "servicio" else None
        f_exp = date.fromisoformat(fecha_expiracion) if fecha_expiracion and fecha_expiracion.strip() else None

        await crear_reserva_insumo(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            storage_location_id=storage_location_id,
            cantidad_reservada=Decimal(cantidad_reservada),
            labor_campo_id=labor_id,
            servicio_prestado_id=servicio_id,
            fecha_expiracion=f_exp,
            usuario_rol=user.get("rol"),
        )
        return RedirectResponse("/insumos?mensaje=Reserva+de+insumo+creada+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/insumos", response_class=HTMLResponse)
async def insumos_dashboard_get(
    request: Request,
    mensaje: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    # Insumos y Ubicaciones
    res_ins = await db.execute(select(Insumo).where(Insumo.cliente_id == cliente_id, Insumo.activo == True).order_by(Insumo.nombre))
    insumos = res_ins.scalars().all()

    res_loc = await db.execute(select(StorageLocation).where(StorageLocation.cliente_id == cliente_id).order_by(StorageLocation.nombre))
    ubicaciones = res_loc.scalars().all()

    # Balances de existencias
    existencias = []
    alertas = []
    total_reservas_activas = 0

    for ins in insumos:
        # Stock físico
        res_f = await db.execute(
            select(func.coalesce(func.sum(InsumoSaldoUbicacion.cantidad_disponible), Decimal("0.0000")))
            .where(InsumoSaldoUbicacion.cliente_id == cliente_id, InsumoSaldoUbicacion.insumo_id == ins.id)
        )
        stock_fisico = res_f.scalar_one()

        # PPP promedio
        res_ppp = await db.execute(
            select(func.coalesce(func.avg(InsumoSaldoUbicacion.costo_ppp_usd), Decimal("0.0000")))
            .where(InsumoSaldoUbicacion.cliente_id == cliente_id, InsumoSaldoUbicacion.insumo_id == ins.id)
        )
        costo_ppp_usd = res_ppp.scalar_one()

        # Reservas activas
        res_r = await db.execute(
            select(func.coalesce(func.sum(InsumoReserva.cantidad_reservada), Decimal("0.0000")))
            .where(InsumoReserva.cliente_id == cliente_id, InsumoReserva.insumo_id == ins.id, InsumoReserva.estado_reserva == "activa")
        )
        stock_reservado = res_r.scalar_one()
        total_reservas_activas += int(stock_reservado > 0)

        disponible_neto = max(Decimal("0.0000"), stock_fisico - stock_reservado)

        if ins.punto_pedido_minimo and disponible_neto <= ins.punto_pedido_minimo:
            alertas.append({
                "insumo": ins.nombre,
                "motivo": f"Stock disponible ({disponible_neto} {ins.unidad_medida.value}) menor o igual al pedido mínimo ({ins.punto_pedido_minimo} {ins.unidad_medida.value})",
                "tipo": "Stock Mínimo",
            })

        existencias.append({
            "id": str(ins.id),
            "nombre": ins.nombre,
            "categoria": ins.categoria.value,
            "unidad": ins.unidad_medida.value,
            "punto_pedido_minimo": float(ins.punto_pedido_minimo or 0),
            "stock_fisico": float(stock_fisico),
            "stock_reservado": float(stock_reservado),
            "disponible_neto": float(disponible_neto),
            "costo_ppp_usd": float(costo_ppp_usd),
        })

    # Labores y Servicios Prestados para modales
    res_lab = await db.execute(
        select(LaborCampo)
        .join(Lote, LaborCampo.lote_id == Lote.id)
        .join(Campo, Lote.campo_id == Campo.id)
        .where(Campo.cliente_id == cliente_id)
        .order_by(LaborCampo.fecha.desc())
        .limit(30)
    )
    labores = res_lab.scalars().all()

    res_serv = await db.execute(select(ServicioPrestado).where(ServicioPrestado.cliente_id == cliente_id).order_by(ServicioPrestado.fecha_trabajo.desc()).limit(30))
    servicios = res_serv.scalars().all()

    total_stock_fisico = sum(item["stock_fisico"] for item in existencias)

    return templates.TemplateResponse(
        "insumos_dashboard.html",
        {
            "request": request,
            "user": user,
            "active_page": "insumos",
            "existencias": existencias,
            "ubicaciones": ubicaciones,
            "labores": labores,
            "servicios": servicios,
            "alertas": alertas,
            "total_insumos": len(insumos),
            "total_ubicaciones": len(ubicaciones),
            "total_reservas_activas": total_reservas_activas,
            "total_stock_fisico": total_stock_fisico,
            "mensaje": mensaje,
            "error": error,
        },
    )


@app.get("/insumos/kardex", response_class=HTMLResponse)
async def insumos_kardex_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    res_mov = await db.execute(
        select(InsumoMovimiento)
        .options(selectinload(InsumoMovimiento.insumo))
        .where(InsumoMovimiento.cliente_id == cliente_id)
        .order_by(InsumoMovimiento.fecha_movimiento.desc())
        .limit(100)
    )
    movimientos = res_mov.scalars().all()

    return templates.TemplateResponse(
        "insumos_kardex.html",
        {
            "request": request,
            "user": user,
            "active_page": "insumos",
            "movimientos": movimientos,
        },
    )


@app.post("/insumos/compra")
async def insumos_compra_post(
    request: Request,
    insumo_id: uuid.UUID = Form(...),
    storage_location_id: uuid.UUID = Form(...),
    cantidad: str = Form(...),
    monto_unitario: str = Form(...),
    moneda_origen: str = Form("USD"),
    cotizacion_usd_ars: str = Form("1000.00"),
    proveedor_nombre: str = Form(...),
    numero_lote: Optional[str] = Form(None),
    fecha_vencimiento: Optional[str] = Form(None),
    clave_idempotencia: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = uuid.UUID(str(user.get("cliente_id"))) if user.get("cliente_id") else None

    try:
        validar_permisos_insumos(user.get("rol"), "registrar_compra")
    except PermissionError as pe:
        return RedirectResponse(f"/insumos?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    registrado_por_id = None
    if user.get("id"):
        try:
            registrado_por_id = uuid.UUID(str(user.get("id")))
        except Exception:
            registrado_por_id = None

    try:
        f_venc = date.fromisoformat(fecha_vencimiento) if fecha_vencimiento else None
        await registrar_compra_ingreso(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            storage_location_id=storage_location_id,
            proveedor_nombre=proveedor_nombre,
            fecha_compra=date.today(),
            cantidad=Decimal(cantidad),
            monto_unitario=Decimal(monto_unitario),
            moneda_origen=MonedaEnum(moneda_origen),
            cotizacion_usd_ars=Decimal(cotizacion_usd_ars),
            numero_lote=numero_lote,
            fecha_vencimiento=f_venc,
            clave_idempotencia=clave_idempotencia or f"compra_form_{uuid.uuid4().hex[:6]}",
            registrado_por_usuario_id=registrado_por_id,
        )
        return RedirectResponse("/insumos?mensaje=Compra+e+ingreso+de+insumo+registrados+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/insumos/consumo")
async def insumos_consumo_post(
    request: Request,
    insumo_id: uuid.UUID = Form(...),
    storage_location_id: uuid.UUID = Form(...),
    cantidad_real: str = Form(...),
    insumos_aportados_por: str = Form("propio"),
    clave_idempotencia: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = user.get("cliente_id")

    try:
        validar_permisos_insumos(user.get("rol"), "confirmar_consumo")
    except PermissionError as pe:
        return RedirectResponse(f"/insumos?error={str(pe).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        res_lab = await db.execute(select(LaborCampo).join(Lote).where(Lote.cliente_id == cliente_id).limit(1))
        labor = res_lab.scalars().first()
        if not labor:
            return RedirectResponse("/insumos?error=No+hay+labores+disponibles+para+asociar+el+consumo", status_code=status.HTTP_303_SEE_OTHER)

        await registrar_consumo_labor(
            db=db,
            cliente_id=cliente_id,
            insumo_id=insumo_id,
            storage_location_id=storage_location_id,
            labor_campo_id=labor.id,
            cantidad_real=Decimal(cantidad_real),
            fecha_consumo=datetime.now(),
            insumos_aportados_por=insumos_aportados_por,
            clave_idempotencia=clave_idempotencia or f"consumo_form_{uuid.uuid4().hex[:6]}",
            registrado_por_usuario_id=uuid.UUID(user.get("id")) if user.get("id") else None,
        )
        return RedirectResponse("/insumos?mensaje=Consumo+real+confirmado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/insumos?error=Error:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/productivo/lotes", response_class=HTMLResponse)
async def list_lotes(
    request: Request,
    campo: Optional[str] = None,
    tenencia: Optional[str] = None,
    cultivo: Optional[str] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/productivo/lotes", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    lotes_filtrados = await fetch_lotes_dicts(db)

    if campo:
        lotes_filtrados = [l for l in lotes_filtrados if l["campo_id"] == campo]
    elif campo_activo:
        lotes_filtrados = [l for l in lotes_filtrados if l["campo_id"] == campo_activo["id"]]

    if tenencia:
        lotes_filtrados = [l for l in lotes_filtrados if l["tenencia_tipo"] == tenencia]
    if cultivo:
        lotes_filtrados = [l for l in lotes_filtrados if l["cultivo_actual"] == cultivo]
    if q:
        q_lower = q.lower()
        lotes_filtrados = [
            l for l in lotes_filtrados if q_lower in l["nombre"].lower() or q_lower in l["campo_nombre"].lower()
        ]

    return templates.TemplateResponse(
        request=request,
        name="productivo_lotes.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "lotes": lotes_filtrados,
            "campos": campos,
            "campo_filtro": campo or campo_activo["id"],
            "tenencia_filtro": tenencia,
            "cultivo_filtro": cultivo,
            "search_q": q,
        },
    )


@app.get("/productivo/lotes/nuevo", response_class=HTMLResponse)
async def form_nuevo_lote(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/productivo/lotes/nuevo", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)

    return templates.TemplateResponse(
        request=request,
        name="productivo_form_lote.html",
        context={"user": user, "campo_activo": campo_activo, "lote": None, "campos": campos},
    )


@app.post("/productivo/lotes/nuevo")
async def create_lote(
    request: Request,
    nombre: str = Form(...),
    campo_id: str = Form(...),
    superficie_total_ha: float = Form(...),
    superficie_productiva_ha: float = Form(...),
    tenencia_tipo: str = Form("propio"),
    costo_alquiler_usd_ha: Optional[float] = Form(0.0),
    vencimiento_alquiler: Optional[str] = Form(None),
    cultivo_anterior: Optional[str] = Form(""),
    cultivo_actual: Optional[str] = Form(""),
    cultivo_planificado: Optional[str] = Form(""),
    qq_ha_estimado: Optional[float] = Form(0.0),
    qq_ha_real: Optional[float] = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    l_uuid = uuid.uuid4()
    c_uuid = get_uuid(campo_id)
    sup_prod = float(superficie_productiva_ha)
    r_real = float(qq_ha_real or 0.0)
    prod_qq = sup_prod * r_real

    venc_alq = date.fromisoformat(vencimiento_alquiler) if vencimiento_alquiler else None
    ten_enum = TenenciaTipoEnum.PROPIO if tenencia_tipo == "propio" else TenenciaTipoEnum.ALQUILADO

    nuevo_lote = Lote(
        id=l_uuid,
        campo_id=c_uuid,
        cliente_id=get_uuid(DEMO_CLIENTE["id"]),
        nombre=nombre.strip(),
        superficie_total_ha=float(superficie_total_ha),
        superficie_productiva_ha=sup_prod,
        tenencia_tipo=ten_enum,
        costo_alquiler_usd_ha=Decimal(str(costo_alquiler_usd_ha or 0.0)),
        vencimiento_alquiler=venc_alq,
        notas_alquiler="Contrato de arrendamiento registrado",
        cultivo_anterior=cultivo_anterior,
        cultivo_actual=cultivo_actual,
        cultivo_planificado=cultivo_planificado,
        tipo_suelo="Argiudol Típico",
        qq_ha_estimado=float(qq_ha_estimado or 0.0),
        qq_ha_real=r_real,
        produccion_total_qq=prod_qq,
        observaciones="Lote registrado en el Módulo Productivo de EduAgro",
    )
    db.add(nuevo_lote)
    await db.commit()

    return RedirectResponse(f"/productivo/lotes/{l_uuid}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/productivo/lotes/{lote_id}", response_class=HTMLResponse)
async def ficha_lote(request: Request, lote_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse(f"/login?next=/productivo/lotes/{lote_id}", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)
    lote = next((l for l in lotes if l["id"] == lote_id), None)
    if not lote:
        return RedirectResponse("/productivo/lotes", status_code=status.HTTP_303_SEE_OTHER)

    campo_obj = next((c for c in campos if c["id"] == lote.get("campo_id")), None)

    # 1. Obtener clima geolocalizado del campo del lote
    from app.services.clima import obtener_clima_para_campo_async
    weather_info = await obtener_clima_para_campo_async(
        lat=campo_obj.get("latitud") if campo_obj else None,
        lon=campo_obj.get("longitud") if campo_obj else None,
        localidad=campo_obj.get("localidad_referencia", "Laguna Larga, Córdoba") if campo_obj else "Laguna Larga, Córdoba",
        campo_nombre=lote.get("campo_nombre"),
        lote_nombre=lote.get("nombre"),
        campo_id=lote.get("campo_id"),
        lote_id=lote.get("id"),
        db=db,
    )

    # 2. Obtener cotización spot y futuros para el cultivo actual del lote (con soporte para Barbecho/Sin Cultivo)
    from app.services.mercado import obtener_snapshot_precios_mercado, obtener_comparativa_futuros_mercado

    cultivo_raw = (lote.get("cultivo_actual") or "").strip().lower()

    # Detectar barbecho, descanso o vacíos sin producción activa
    palabras_barbecho = ["barbecho", "vacio", "vacío", "sin cultivo", "descanso", "ninguno", "limpio"]
    es_barbecho = any(pb in cultivo_raw for pb in palabras_barbecho) or not cultivo_raw

    if es_barbecho:
        valorizacion_lote = {
            "tiene_valorizacion": False,
            "cultivo_key": None,
            "mensaje": "Lote en barbecho o descanso (Sin cultivo activo para valorizar)",
            "produccion_tn": 0.0,
            "precio_spot_usd": 0.0,
            "precio_futuro_usd": 0.0,
            "valor_spot_usd": 0.0,
            "valor_futuro_usd": 0.0,
            "diferencia_usd": 0.0,
        }
    else:
        # Discriminador refinado de cultivo
        if "soja" in cultivo_raw:
            cultivo_key = "soja"
        elif "maiz" in cultivo_raw or "maíz" in cultivo_raw:
            cultivo_key = "maiz"
        elif "sorgo" in cultivo_raw or "sorg" in cultivo_raw:
            cultivo_key = "sorgo"
        else:
            cultivo_key = None

        if cultivo_key:
            snapshot = await obtener_snapshot_precios_mercado(db, cultivos=[cultivo_key])
            p_spot_item = snapshot[0] if snapshot else {}
            precio_spot_usd = float(p_spot_item.get("precio_usd_tn", 338.75 if cultivo_key == "soja" else (188.0 if cultivo_key == "maiz" else 155.0)))

            futuros = obtener_comparativa_futuros_mercado(snapshot)
            fut_item = next((f for f in futuros if f["cultivo"].lower() == cultivo_key), {})
            precio_futuro_usd = float(fut_item.get("precio_futuro_usd", precio_spot_usd * 1.03))
            contrato_futuro = fut_item.get("contrato", f"{cultivo_key.capitalize()} Matba Rofex")

            prod_total_t = float(lote.get("produccion_total_t") or 0.0)
            if prod_total_t == 0.0:
                sup_prod = float(lote.get("superficie_productiva_ha") or 0.0)
                qq_est = float(lote.get("qq_ha_estimado") or 0.0)
                prod_total_t = (sup_prod * qq_est) / 10.0

            valor_spot_usd = prod_total_t * precio_spot_usd
            valor_futuro_usd = prod_total_t * precio_futuro_usd

            valorizacion_lote = {
                "tiene_valorizacion": True,
                "cultivo_key": cultivo_key,
                "precio_spot_usd": precio_spot_usd,
                "precio_futuro_usd": precio_futuro_usd,
                "contrato_futuro": contrato_futuro,
                "produccion_tn": prod_total_t,
                "valor_spot_usd": valor_spot_usd,
                "valor_futuro_usd": valor_futuro_usd,
                "diferencia_usd": valor_futuro_usd - valor_spot_usd,
            }
        else:
            valorizacion_lote = {
                "tiene_valorizacion": False,
                "cultivo_key": None,
                "mensaje": f"Cultivo no parametrizado comercialmente ({lote.get('cultivo_actual')})",
                "produccion_tn": float(lote.get("produccion_total_t") or 0.0),
                "precio_spot_usd": 0.0,
                "precio_futuro_usd": 0.0,
                "valor_spot_usd": 0.0,
                "valor_futuro_usd": 0.0,
                "diferencia_usd": 0.0,
            }

    # 4. Evaluación del Motor de Decisión 1.0 para el Lote
    from app.services.decision_motor import evaluar_motor_decisiones
    if valorizacion_lote.get("tiene_valorizacion"):
        c_key = valorizacion_lote["cultivo_key"]
        humedad_ini = 17.5 if c_key == "maiz" else 15.0
        pron_sem = weather_info.get("pronostico_semanal", [])
        precip_48h = (pron_sem[0].get("precipitacion_mm", 0.0) + pron_sem[1].get("precipitacion_mm", 0.0)) if len(pron_sem) >= 2 else 0.0
        spread_per_tn = round(valorizacion_lote["precio_futuro_usd"] - valorizacion_lote["precio_spot_usd"], 2)

        contexto_lote = {
            "cultivo": c_key,
            "precio_fisico_usd": valorizacion_lote["precio_spot_usd"],
            "precio_futuro_usd": valorizacion_lote["precio_futuro_usd"],
            "spread_futuro_usd": spread_per_tn,
            "humedad_grano_pct": humedad_ini,
            "costo_secada_punto_usd": 2.50,
            "lluvia_esperada_mm": precip_48h,
            "viento_max_kmh": weather_info.get("viento_kmh", 14.0),
            "temp_min_c": 10.0,
            "alerta_viento": weather_info.get("alerta_viento"),
            "alerta_lluvia": weather_info.get("alerta_lluvia"),
            "alerta_helada": weather_info.get("alerta_helada"),
            "campo_nombre": lote.get("campo_nombre"),
            "lote_nombre": lote.get("nombre"),
        }
        decision_insights = evaluar_motor_decisiones(contexto_lote)
    else:
        decision_insights = []

    return templates.TemplateResponse(
        request=request,
        name="productivo_lote_ficha.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "lote": lote,
            "weather": weather_info,
            "valorizacion": valorizacion_lote,
            "decision_insights": decision_insights,
        },
    )


@app.get("/productivo/lotes/{lote_id}/editar", response_class=HTMLResponse)
async def form_editar_lote(request: Request, lote_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)
    lote = next((l for l in lotes if l["id"] == lote_id), None)
    if not lote:
        return RedirectResponse("/productivo/lotes", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="productivo_form_lote.html",
        context={"user": user, "campo_activo": campo_activo, "lote": lote, "campos": campos},
    )


@app.post("/productivo/lotes/{lote_id}/editar")
async def update_lote(
    request: Request,
    lote_id: str,
    nombre: str = Form(...),
    campo_id: str = Form(...),
    superficie_total_ha: float = Form(...),
    superficie_productiva_ha: float = Form(...),
    tenencia_tipo: str = Form("propio"),
    costo_alquiler_usd_ha: Optional[float] = Form(0.0),
    vencimiento_alquiler: Optional[str] = Form(None),
    cultivo_anterior: Optional[str] = Form(""),
    cultivo_actual: Optional[str] = Form(""),
    cultivo_planificado: Optional[str] = Form(""),
    qq_ha_estimado: Optional[float] = Form(0.0),
    qq_ha_real: Optional[float] = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    l_uuid = get_uuid(lote_id)
    res = await db.execute(select(Lote).where(Lote.id == l_uuid))
    lote_obj = res.scalars().first()

    if lote_obj:
        sup_prod = float(superficie_productiva_ha)
        r_real = float(qq_ha_real or 0.0)
        prod_qq = sup_prod * r_real
        venc_alq = date.fromisoformat(vencimiento_alquiler) if vencimiento_alquiler else None
        ten_enum = TenenciaTipoEnum.PROPIO if tenencia_tipo == "propio" else TenenciaTipoEnum.ALQUILADO

        lote_obj.campo_id = get_uuid(campo_id)
        lote_obj.nombre = nombre.strip()
        lote_obj.superficie_total_ha = float(superficie_total_ha)
        lote_obj.superficie_productiva_ha = sup_prod
        lote_obj.tenencia_tipo = ten_enum
        lote_obj.costo_alquiler_usd_ha = Decimal(str(costo_alquiler_usd_ha or 0.0))
        lote_obj.vencimiento_alquiler = venc_alq
        lote_obj.cultivo_anterior = cultivo_anterior
        lote_obj.cultivo_actual = cultivo_actual
        lote_obj.cultivo_planificado = cultivo_planificado
        lote_obj.qq_ha_estimado = float(qq_ha_estimado or 0.0)
        lote_obj.qq_ha_real = r_real
        lote_obj.produccion_total_qq = prod_qq
        await db.commit()

    return RedirectResponse(f"/productivo/lotes/{lote_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/productivo/rendimientos", response_class=HTMLResponse)
async def list_rendimientos(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/productivo/rendimientos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    lotes = await fetch_lotes_dicts(db)
    lotes_filtrados = [l for l in lotes if l["campo_id"] == campo_activo["id"]]

    total_estimado_qq = sum((float(l.get("superficie_productiva_ha", 0.0)) * float(l.get("qq_ha_estimado", 0.0))) for l in lotes_filtrados)
    total_estimado_tn = total_estimado_qq / 10.0
    total_real_qq = sum(float(l.get("produccion_total_qq", 0.0)) for l in lotes_filtrados)
    total_real_tn = total_real_qq / 10.0
    total_ha = sum(float(l.get("superficie_productiva_ha", 0.0)) for l in lotes_filtrados)
    rinde_promedio_pond = (total_real_qq / total_ha) if total_ha > 0 else 0.0

    return templates.TemplateResponse(
        request=request,
        name="productivo_rendimientos.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "lotes": lotes_filtrados,
            "total_estimado_qq": total_estimado_qq,
            "total_estimado_tn": total_estimado_tn,
            "total_real_qq": total_real_qq,
            "total_real_tn": total_real_tn,
            "total_ha": total_ha,
            "rinde_promedio_pond": rinde_promedio_pond,
        },
    )


# ----------------------------------------------------------------------
# Módulo de Servicios por Campo e Instalación
# ----------------------------------------------------------------------

@app.get("/servicios/campos", response_class=HTMLResponse)
async def servicios_resumen_campos(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios/campos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    servicios = await fetch_servicios_dicts(db)

    total_monto_ars = sum(s["monto_real_ars"] for s in servicios)
    total_monto_usd = sum(s["monto_usd"] for s in servicios)
    servicios_vencidos_count = len([s for s in servicios if s["estado"] == "vencido"])
    servicios_al_dia_count = len([s for s in servicios if s["estado"] == "al_dia"])

    return templates.TemplateResponse(
        request=request,
        name="servicios_resumen_campos.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "servicios": servicios,
            "total_monto_ars": total_monto_ars,
            "total_monto_usd": total_monto_usd,
            "servicios_vencidos_count": servicios_vencidos_count,
            "servicios_al_dia_count": servicios_al_dia_count,
        },
    )


@app.get("/servicios", response_class=HTMLResponse)
async def list_servicios(
    request: Request,
    campo: Optional[str] = None,
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    servicios_filtrados = await fetch_servicios_dicts(db)

    if campo:
        servicios_filtrados = [s for s in servicios_filtrados if s["campo_id"] == campo]
    elif campo_activo:
        servicios_filtrados = [s for s in servicios_filtrados if s["campo_id"] == campo_activo["id"]]

    if tipo:
        servicios_filtrados = [s for s in servicios_filtrados if s["tipo_servicio"] == tipo]
    if estado:
        servicios_filtrados = [s for s in servicios_filtrados if s["estado"] == estado]
    if q:
        q_lower = q.lower()
        servicios_filtrados = [
            s for s in servicios_filtrados
            if q_lower in s["concepto"].lower() or q_lower in s["proveedor"].lower()
        ]

    return templates.TemplateResponse(
        request=request,
        name="servicios_listado.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "servicios": servicios_filtrados,
            "campos": campos,
            "campo_filtro": campo or campo_activo["id"],
            "tipo_filtro": tipo,
            "estado_filtro": estado,
            "search_q": q,
        },
    )


@app.get("/servicios/nuevo", response_class=HTMLResponse)
async def form_nuevo_servicio(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios/nuevo", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    instalaciones = await fetch_instalaciones_dicts(db)

    return templates.TemplateResponse(
        request=request,
        name="servicios_form.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "servicio": None,
            "campos": campos,
            "instalaciones": instalaciones,
        },
    )


@app.post("/servicios/nuevo")
async def create_servicio(
    request: Request,
    campo_id: str = Form(...),
    instalacion_id: str = Form(...),
    concepto: str = Form(...),
    proveedor: str = Form(...),
    tipo_servicio: str = Form("luz_rural"),
    frecuencia_pago: str = Form("mensual"),
    monto_estimado_ars: float = Form(0.0),
    monto_real_ars: float = Form(0.0),
    fecha_vencimiento: str = Form(...),
    payment_portal_url: Optional[str] = Form(None),
    payment_reference: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    s_uuid = uuid.uuid4()
    c_uuid = get_uuid(campo_id)
    i_uuid = get_uuid(instalacion_id) if (instalacion_id and instalacion_id.strip()) else None
    m_real = float(monto_real_ars)
    m_usd = Decimal(str(round(m_real / 1285.50, 2)))

    tipo_s_enum = TipoServicioEnum(tipo_servicio) if tipo_servicio in [e.value for e in TipoServicioEnum] else TipoServicioEnum.LUZ_RURAL
    frec_p_enum = FrecuenciaPagoEnum(frecuencia_pago) if frecuencia_pago in [e.value for e in FrecuenciaPagoEnum] else FrecuenciaPagoEnum.MENSUAL
    fecha_venc = date.fromisoformat(fecha_vencimiento)

    valid_portal_url = None
    if payment_portal_url and payment_portal_url.strip():
        try:
            valid_portal_url = validate_external_payment_url(payment_portal_url)
        except ValueError as err:
            return RedirectResponse(f"/servicios/nuevo?error={str(err)}", status_code=status.HTTP_303_SEE_OTHER)

    nuevo_servicio = ServicioInstalado(
        id=s_uuid,
        cliente_id=cliente_id,
        campo_id=c_uuid,
        instalacion_id=i_uuid,
        tipo_servicio=tipo_s_enum,
        concepto=concepto.strip(),
        proveedor=proveedor.strip(),
        frecuencia_pago=frec_p_enum,
        monto_estimado_ars=Decimal(str(monto_estimado_ars)),
        monto_real_ars=Decimal(str(m_real)),
        monto_usd=m_usd,
        fecha_vencimiento=fecha_venc,
        estado=EstadoServicioInstaladoEnum.PENDIENTE,
        comprobante_url="https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80",
        payment_portal_url=valid_portal_url,
        payment_reference=payment_reference.strip() if payment_reference else None,
        observaciones=observaciones or "Servicio operativo registrado",
    )
    db.add(nuevo_servicio)
    await db.commit()

    return RedirectResponse(
        f"/servicios?mensaje=Servicio+'{concepto.strip()}'+creado+exitosamente.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/servicios/vencimientos", response_class=HTMLResponse)
async def list_servicios_vencimientos(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios/vencimientos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    servicios = await fetch_servicios_dicts(db, cliente_id=cliente_id)

    # Consolidar vencimientos directos y vencimientos asociados a servicios
    todos_vencimientos = []
    for s in servicios:
        for v in s.get("vencimientos", []):
            v_item = dict(v)
            v_item["proveedor"] = s["proveedor"]
            v_item["tipo_servicio_label"] = s["tipo_servicio_label"]
            v_item["servicio_concepto"] = s["concepto"]
            v_item["campo_nombre"] = s["campo_nombre"]
            todos_vencimientos.append(v_item)

    servicios_ordenados = sorted(servicios, key=lambda s: s["fecha_vencimiento"])
    vencimientos_ordenados = sorted(todos_vencimientos, key=lambda v: v["fecha_vencimiento"])

    return templates.TemplateResponse(
        request=request,
        name="servicios_vencimientos.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "servicios": servicios_ordenados,
            "vencimientos_asociados": vencimientos_ordenados,
        },
    )


@app.get("/servicios/instalaciones", response_class=HTMLResponse)
async def list_instalaciones(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios/instalaciones", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    instalaciones = await fetch_instalaciones_dicts(db)
    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    servicios = await fetch_servicios_dicts(db, cliente_id=cliente_id)

    return templates.TemplateResponse(
        request=request,
        name="servicios_instalaciones.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "instalaciones": instalaciones,
            "servicios": servicios,
        },
    )


@app.get("/servicios/{servicio_id}", response_class=HTMLResponse)
async def ficha_servicio(request: Request, servicio_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse(f"/login?next=/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    servicios = await fetch_servicios_dicts(db, cliente_id=cliente_id)
    servicio = next((s for s in servicios if s["id"] == servicio_id), None)
    if not servicio:
        return RedirectResponse("/servicios", status_code=status.HTTP_303_SEE_OTHER)

    mensaje = request.query_params.get("mensaje")
    error = request.query_params.get("error")

    return templates.TemplateResponse(
        request=request,
        name="servicios_ficha.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "servicio": servicio,
            "mensaje": mensaje,
            "error": error,
        },
    )


@app.get("/servicios/{servicio_id}/editar", response_class=HTMLResponse)
async def form_editar_servicio(request: Request, servicio_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    instalaciones = await fetch_instalaciones_dicts(db)
    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    servicios = await fetch_servicios_dicts(db, cliente_id=cliente_id)
    servicio = next((s for s in servicios if s["id"] == servicio_id), None)
    if not servicio:
        return RedirectResponse("/servicios", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="servicios_form.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "servicio": servicio,
            "campos": campos,
            "instalaciones": instalaciones,
        },
    )


@app.post("/servicios/{servicio_id}/editar")
async def update_servicio(
    request: Request,
    servicio_id: str,
    campo_id: str = Form(...),
    instalacion_id: str = Form(...),
    concepto: str = Form(...),
    proveedor: str = Form(...),
    tipo_servicio: str = Form("luz_rural"),
    frecuencia_pago: str = Form("mensual"),
    monto_estimado_ars: float = Form(0.0),
    monto_real_ars: float = Form(0.0),
    fecha_vencimiento: str = Form(...),
    payment_portal_url: Optional[str] = Form(None),
    payment_reference: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    s_uuid = get_uuid(servicio_id)
    res = await db.execute(select(ServicioInstalado).where(ServicioInstalado.id == s_uuid))
    servicio_obj = res.scalars().first()

    if servicio_obj:
        valid_portal_url = None
        if payment_portal_url and payment_portal_url.strip():
            try:
                valid_portal_url = validate_external_payment_url(payment_portal_url)
            except ValueError as err:
                return RedirectResponse(f"/servicios/{servicio_id}/editar?error={str(err)}", status_code=status.HTTP_303_SEE_OTHER)

        m_real = float(monto_real_ars)
        m_usd = Decimal(str(round(m_real / 1285.50, 2)))
        tipo_s_enum = TipoServicioEnum(tipo_servicio) if tipo_servicio in [e.value for e in TipoServicioEnum] else TipoServicioEnum.LUZ_RURAL
        frec_p_enum = FrecuenciaPagoEnum(frecuencia_pago) if frecuencia_pago in [e.value for e in FrecuenciaPagoEnum] else FrecuenciaPagoEnum.MENSUAL
        fecha_venc = date.fromisoformat(fecha_vencimiento)

        servicio_obj.campo_id = get_uuid(campo_id)
        servicio_obj.instalacion_id = get_uuid(instalacion_id) if (instalacion_id and instalacion_id.strip()) else None
        servicio_obj.concepto = concepto.strip()
        servicio_obj.proveedor = proveedor.strip()
        servicio_obj.tipo_servicio = tipo_s_enum
        servicio_obj.frecuencia_pago = frec_p_enum
        servicio_obj.monto_estimado_ars = Decimal(str(monto_estimado_ars))
        servicio_obj.monto_real_ars = Decimal(str(m_real))
        servicio_obj.monto_usd = m_usd
        servicio_obj.fecha_vencimiento = fecha_venc
        servicio_obj.payment_portal_url = valid_portal_url
        servicio_obj.payment_reference = payment_reference.strip() if payment_reference else None
        servicio_obj.observaciones = observaciones
        await db.commit()

    return RedirectResponse(f"/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)


# ----------------------------------------------------------------------
# ENDPOINTS SERVICIOS V1: VENCIMIENTOS MANUALES & DOCUMENTOS PRIVADOS
# ----------------------------------------------------------------------

@app.post("/servicios/{servicio_id}/vencimientos/crear")
async def create_servicio_vencimiento(
    request: Request,
    servicio_id: str,
    concepto: str = Form(...),
    periodo_referencia: Optional[str] = Form(None),
    monto_ars: Optional[float] = Form(None),
    monto_usd: Optional[float] = Form(None),
    fecha_vencimiento: str = Form(...),
    payment_link: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse(f"/login?next=/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    s_uuid = get_uuid(servicio_id)

    res_s = await db.execute(
        select(ServicioInstalado).where(
            ServicioInstalado.id == s_uuid,
            or_(ServicioInstalado.cliente_id == cliente_id, ServicioInstalado.cliente_id.is_(None))
        )
    )
    servicio_obj = res_s.scalars().first()
    if not servicio_obj:
        return RedirectResponse("/servicios?error=Servicio+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    valid_link = None
    if payment_link and payment_link.strip():
        try:
            valid_link = validate_external_payment_url(payment_link)
        except ValueError as err:
            return RedirectResponse(
                f"/servicios/{servicio_id}?error={str(err)}",
                status_code=status.HTTP_303_SEE_OTHER
            )

    f_venc = date.fromisoformat(fecha_vencimiento)
    m_ars_dec = Decimal(str(monto_ars)) if monto_ars is not None else Decimal("0.0")
    m_usd_dec = Decimal(str(monto_usd)) if monto_usd is not None else Decimal("0.0")

    nuevo_venc = ServicioVencimiento(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        servicio_instalado_id=servicio_obj.id,
        concepto=concepto.strip(),
        periodo_referencia=periodo_referencia.strip() if periodo_referencia else None,
        monto_ars=m_ars_dec,
        monto_usd=m_usd_dec,
        fecha_vencimiento=f_venc,
        estado=EstadoServicio.PENDIENTE,
        payment_link=valid_link,
    )
    db.add(nuevo_venc)
    await db.commit()

    msg = f"Vencimiento '{concepto.strip()}' registrado exitosamente."
    return RedirectResponse(
        f"/servicios/{servicio_id}?mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/servicios/{servicio_id}/documentos/subir")
async def upload_servicio_document(
    request: Request,
    servicio_id: str,
    file: UploadFile = File(...),
    document_type: str = Form("factura"),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse(f"/login?next=/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    s_uuid = get_uuid(servicio_id)

    res_s = await db.execute(
        select(ServicioInstalado).where(
            ServicioInstalado.id == s_uuid,
            or_(ServicioInstalado.cliente_id == cliente_id, ServicioInstalado.cliente_id.is_(None))
        )
    )
    servicio_obj = res_s.scalars().first()
    if not servicio_obj:
        return RedirectResponse("/servicios?error=Servicio+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    try:
        doc_type_enum = DocumentTypeEnum(document_type) if document_type in [e.value for e in DocumentTypeEnum] else DocumentTypeEnum.FACTURA
    except Exception:
        doc_type_enum = DocumentTypeEnum.FACTURA

    try:
        orig_name, storage_key, total_size, detected_mime, sha256_hash = await save_document_file(
            file, cliente_id, s_uuid
        )
    except ValueError as err:
        return RedirectResponse(
            f"/servicios/{servicio_id}?error={str(err)}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    usr_id = get_uuid(user.get("id")) if user.get("id") else None

    nuevo_doc = ServiceDocument(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        servicio_id=s_uuid,
        servicio_vencimiento_id=None,
        document_type=doc_type_enum,
        original_filename=orig_name,
        stored_filename=Path(storage_key).name,
        storage_key=storage_key,
        mime_type=detected_mime,
        size_bytes=total_size,
        sha256_hash=sha256_hash,
        uploaded_by_user_id=usr_id,
        notes=notes.strip() if notes else None,
        estado="activo",
    )
    db.add(nuevo_doc)

    try:
        await db.commit()
    except Exception as err:
        delete_document_file(storage_key)
        return RedirectResponse(
            f"/servicios/{servicio_id}?error=Falla+en+base+de+datos+al+registrar+documento",
            status_code=status.HTTP_303_SEE_OTHER
        )

    msg = f"Documento '{orig_name}' adjuntado exitosamente."
    return RedirectResponse(
        f"/servicios/{servicio_id}?mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/servicios/vencimientos/{vencimiento_id}/documentos/subir")
async def upload_vencimiento_document(
    request: Request,
    vencimiento_id: str,
    file: UploadFile = File(...),
    document_type: str = Form("factura"),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    v_uuid = get_uuid(vencimiento_id)

    res_v = await db.execute(
        select(ServicioVencimiento).where(
            ServicioVencimiento.id == v_uuid,
            or_(ServicioVencimiento.cliente_id == cliente_id, ServicioVencimiento.cliente_id.is_(None))
        )
    )
    venc_obj = res_v.scalars().first()
    if not venc_obj:
        return RedirectResponse("/servicios/vencimientos?error=Vencimiento+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    redirect_url = f"/servicios/{venc_obj.servicio_instalado_id}" if venc_obj.servicio_instalado_id else "/servicios/vencimientos"

    try:
        doc_type_enum = DocumentTypeEnum(document_type) if document_type in [e.value for e in DocumentTypeEnum] else DocumentTypeEnum.FACTURA
    except Exception:
        doc_type_enum = DocumentTypeEnum.FACTURA

    try:
        orig_name, storage_key, total_size, detected_mime, sha256_hash = await save_document_file(
            file, cliente_id, v_uuid
        )
    except ValueError as err:
        return RedirectResponse(
            f"{redirect_url}?error={str(err)}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    usr_id = get_uuid(user.get("id")) if user.get("id") else None

    nuevo_doc = ServiceDocument(
        id=uuid.uuid4(),
        cliente_id=cliente_id,
        servicio_id=venc_obj.servicio_instalado_id,
        servicio_vencimiento_id=v_uuid,
        document_type=doc_type_enum,
        original_filename=orig_name,
        stored_filename=Path(storage_key).name,
        storage_key=storage_key,
        mime_type=detected_mime,
        size_bytes=total_size,
        sha256_hash=sha256_hash,
        uploaded_by_user_id=usr_id,
        notes=notes.strip() if notes else None,
        estado="activo",
    )
    db.add(nuevo_doc)

    try:
        await db.commit()
    except Exception as err:
        delete_document_file(storage_key)
        return RedirectResponse(
            f"{redirect_url}?error=Falla+en+base+de+datos+al+registrar+documento",
            status_code=status.HTTP_303_SEE_OTHER
        )

    msg = f"Documento '{orig_name}' adjuntado al vencimiento."
    return RedirectResponse(
        f"{redirect_url}?mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/servicios/documentos/{document_id}/descargar")
async def download_service_document(
    request: Request,
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    d_uuid = get_uuid(document_id)

    res_d = await db.execute(
        select(ServiceDocument).where(
            ServiceDocument.id == d_uuid,
            ServiceDocument.estado == "activo",
            or_(ServiceDocument.cliente_id == cliente_id, ServiceDocument.cliente_id.is_(None))
        )
    )
    doc_obj = res_d.scalars().first()
    if not doc_obj:
        return JSONResponse(status_code=404, content={"detail": "Documento no encontrado o sin permisos."})

    try:
        file_path = resolve_safe_path(doc_obj.storage_key)
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Ruta de almacenamiento inválida."})

    if not file_path.exists() or not file_path.is_file():
        return JSONResponse(status_code=404, content={"detail": "El archivo físico no existe en el servidor."})

    safe_orig_name = doc_obj.original_filename.replace('"', '\\"')

    return FileResponse(
        path=file_path,
        media_type=doc_obj.mime_type,
        filename=doc_obj.original_filename,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_orig_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@app.post("/servicios/documentos/{document_id}/eliminar")
async def delete_service_document(
    request: Request,
    document_id: str,
    redirect_url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    d_uuid = get_uuid(document_id)

    res_d = await db.execute(
        select(ServiceDocument).where(
            ServiceDocument.id == d_uuid,
            or_(ServiceDocument.cliente_id == cliente_id, ServiceDocument.cliente_id.is_(None))
        )
    )
    doc_obj = res_d.scalars().first()
    if doc_obj:
        target_redir = redirect_url or (f"/servicios/{doc_obj.servicio_id}" if doc_obj.servicio_id else "/servicios")
        doc_obj.estado = "anulado"
        delete_document_file(doc_obj.storage_key)
        await db.commit()
        msg = f"Documento '{doc_obj.original_filename}' eliminado."
    else:
        target_redir = redirect_url or "/servicios"
        msg = "Documento no encontrado."

    return RedirectResponse(
        f"{target_redir}?mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/servicios/{servicio_id}/pagar")
@app.post("/servicios/{servicio_id}/pagar_periodo")
async def pagar_servicio_periodo(
    request: Request,
    servicio_id: str,
    periodo_concepto: Optional[str] = Form(None),
    monto_ars: Optional[float] = Form(None),
    monto_usd: Optional[float] = Form(None),
    payment_link: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse(f"/login?next=/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    s_uuid = get_uuid(servicio_id)

    res_s = await db.execute(
        select(ServicioInstalado).where(
            ServicioInstalado.id == s_uuid,
            or_(ServicioInstalado.cliente_id == cliente_id, ServicioInstalado.cliente_id.is_(None))
        )
    )
    servicio_obj = res_s.scalars().first()
    if not servicio_obj:
        return RedirectResponse("/servicios?error=Servicio+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    valid_link = None
    if payment_link and payment_link.strip():
        try:
            valid_link = validate_external_payment_url(payment_link)
        except ValueError as err:
            return RedirectResponse(
                f"/servicios/{servicio_id}?error={str(err)}",
                status_code=status.HTTP_303_SEE_OTHER
            )

    meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    if not periodo_concepto or not periodo_concepto.strip():
        nom_mes = meses_es[servicio_obj.fecha_vencimiento.month - 1] if servicio_obj.fecha_vencimiento else "Actual"
        anio_v = servicio_obj.fecha_vencimiento.year if servicio_obj.fecha_vencimiento else date.today().year
        periodo_concepto = f"Pago {nom_mes} {anio_v}"

    m_ars_dec = Decimal(str(monto_ars)) if monto_ars is not None else servicio_obj.monto_real_ars
    m_usd_dec = Decimal(str(monto_usd)) if monto_usd is not None else servicio_obj.monto_usd

    venc_id = uuid.uuid4()
    fecha_pago_hoy = date.today()

    nuevo_venc = ServicioVencimiento(
        id=venc_id,
        cliente_id=cliente_id,
        servicio_instalado_id=servicio_obj.id,
        concepto=periodo_concepto.strip(),
        periodo_referencia=periodo_concepto.strip(),
        monto_ars=m_ars_dec,
        monto_usd=m_usd_dec,
        fecha_vencimiento=servicio_obj.fecha_vencimiento,
        fecha_pago=fecha_pago_hoy,
        estado=EstadoServicio.PAGADO,
        payment_link=valid_link,
    )
    db.add(nuevo_venc)

    has_attachment = False
    if file and file.filename and file.filename.strip():
        try:
            orig_name, storage_key, total_size, detected_mime, sha256_hash = await save_document_file(
                file, cliente_id, venc_id
            )
            usr_id = get_uuid(user.get("id")) if user.get("id") else None
            nuevo_doc = ServiceDocument(
                id=uuid.uuid4(),
                cliente_id=cliente_id,
                servicio_id=servicio_obj.id,
                servicio_vencimiento_id=venc_id,
                document_type=DocumentTypeEnum.COMPROBANTE_PAGO,
                original_filename=orig_name,
                stored_filename=Path(storage_key).name,
                storage_key=storage_key,
                mime_type=detected_mime,
                size_bytes=total_size,
                sha256_hash=sha256_hash,
                uploaded_by_user_id=usr_id,
                notes=observaciones.strip() if observaciones else f"Comprobante período '{periodo_concepto.strip()}'",
                estado="activo",
            )
            db.add(nuevo_doc)
            has_attachment = True
        except ValueError as err:
            await db.rollback()
            return RedirectResponse(
                f"/servicios/{servicio_id}?error={str(err)}",
                status_code=status.HTTP_303_SEE_OTHER
            )

    # AVANCE AUTOMÁTICO DE FECHA DE VENCIMIENTO SEGÚN FRECUENCIA
    nueva_fecha = advance_servicio_vencimiento_date(servicio_obj.fecha_vencimiento, servicio_obj.frecuencia_pago)
    servicio_obj.fecha_vencimiento = nueva_fecha

    if nueva_fecha >= date.today():
        servicio_obj.estado = EstadoServicioInstaladoEnum.AL_DIA

    await db.commit()

    fmt_nueva_fecha = nueva_fecha.strftime("%d/%m/%Y")
    msg = f"Período '{periodo_concepto.strip()}' registrado como PAGADO."
    if has_attachment:
        msg += " Comprobante adjuntado."
    msg += f" Próximo vencimiento actualizado automáticamente al {fmt_nueva_fecha}."

    return RedirectResponse(
        f"/servicios/{servicio_id}?mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER
    )


# ----------------------------------------------------------------------
# Módulo de Clima y Alertas Agronómicas por Geolocalización de Campo
# ----------------------------------------------------------------------

@app.get("/clima/campos", response_class=HTMLResponse)
async def clima_resumen_campos(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/clima/campos", status_code=status.HTTP_303_SEE_OTHER)

    from app.services.clima import obtener_clima_para_campo_async
    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db, cliente_id=user.get("cliente_id"))

    async def _fetch_single_clima(c):
        w_info = await obtener_clima_para_campo_async(
            lat=c.get("latitud"),
            lon=c.get("longitud"),
            localidad=c.get("localidad_referencia", "Laguna Larga, Córdoba"),
            campo_nombre=c.get("nombre"),
            campo_id=c.get("id"),
            db=db,
        )
        return {"campo": c, "weather": w_info}

    campos_clima = list(await asyncio.gather(*[_fetch_single_clima(c) for c in campos]))

    return templates.TemplateResponse(
        request=request,
        name="clima_resumen_campos.html",
        context={"user": user, "campo_activo": campo_activo, "campos_clima": campos_clima},
    )


@app.get("/clima/campos/{campo_id}", response_class=HTMLResponse)
async def clima_semanal_campo(request: Request, campo_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse(f"/login?next=/clima/campos/{campo_id}", status_code=status.HTTP_303_SEE_OTHER)

    from app.services.clima import obtener_clima_para_campo_async
    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    campo = next((c for c in campos if c["id"] == campo_id), None)
    if not campo:
        return RedirectResponse("/clima/campos", status_code=status.HTTP_303_SEE_OTHER)

    weather_info = await obtener_clima_para_campo_async(
        lat=campo.get("latitud"),
        lon=campo.get("longitud"),
        localidad=campo.get("localidad_referencia", "Laguna Larga, Córdoba"),
        campo_nombre=campo.get("nombre"),
        campo_id=campo.get("id"),
        db=db,
    )

    return templates.TemplateResponse(
        request=request,
        name="clima_semanal_campo.html",
        context={"user": user, "campo_activo": campo_activo, "campo": campo, "weather": weather_info},
    )


# ----------------------------------------------------------------------
# Endpoints API JSON para PWA Offline-First & Sincronización (/campo)
# ----------------------------------------------------------------------

PROCESSED_ACTION_IDS = set()


@app.get("/api/campo/estado")
async def get_campo_estado_api(request: Request, db: AsyncSession = Depends(get_db)):
    """Endpoint JSON para hidratación de IndexedDB en Modo Campo PWA."""
    user = await get_current_user_from_session(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=status.HTTP_401_UNAUTHORIZED)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)

    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )
    lotes_campo_activo = [l for l in lotes if l["campo_id"] == campo_activo["id"]]
    tareas_campo = [t for t in TAREAS_STORE if t["campo_id"] == campo_activo["id"]]

    return JSONResponse({
        "user": {"id": user["id"], "nombre": user["nombre"], "email": user["email"]},
        "campo_activo": campo_activo,
        "campos": campos,
        "lotes_campo": lotes_campo_activo,
        "weather": weather_data,
        "tareas": tareas_campo,
    })


@app.post("/api/campo/sync-actions")
async def sync_campo_actions_api(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Endpoint JSON para procesar acciones diferidas acumuladas en IndexedDB (offline_queue).
    Soporta idempotencia por client_action_id para prevenir duplicados.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=status.HTTP_401_UNAUTHORIZED)

    data = await request.json()
    actions = data.get("actions", [])
    processed_count = 0

    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)

    for act in actions:
        action_id = act.get("client_action_id")
        if not action_id or action_id in PROCESSED_ACTION_IDS:
            continue

        tipo = act.get("tipo")
        payload = act.get("payload", {})
        campo_id = payload.get("campo_id") or request.session.get("campo_activo_id", "campo-001")
        campo_sel = next((c for c in campos if c["id"] == campo_id), None)
        campo_nombre = campo_sel["nombre"] if campo_sel else "Campo General"

        if tipo == "registrar_lluvia":
            mm = payload.get("milimetros", 0.0)
            lote_id = payload.get("lote_id")
            lote_sel = next((l for l in lotes if l["id"] == lote_id), None) if lote_id else None
            nueva_tarea = {
                "id": f"tarea-00{len(TAREAS_STORE) + 1}",
                "campo_id": campo_id,
                "campo_nombre": campo_nombre,
                "lote_id": lote_id,
                "lote_nombre": lote_sel["nombre"] if lote_sel else "Campo General",
                "tipo": "lluvia_suelo",
                "tipo_label": "🌧️ Lluvia / Suelo",
                "titulo": f"Registro de Lluvia ({mm} mm)",
                "responsable": user.get("nombre", "Operario Campo"),
                "prioridad": "media",
                "prioridad_label": "Media",
                "estado": "hecha",
                "estado_label": "Hecha",
                "fecha": "2026-07-30",
                "observaciones": payload.get("observaciones") or f"Lluvia de {mm} mm registrada desde Modo Campo Offline.",
                "valor_registrado": f"{mm} mm",
            }
            TAREAS_STORE.insert(0, nueva_tarea)

        elif tipo == "registrar_incidencia":
            lote_id = payload.get("lote_id")
            lote_sel = next((l for l in lotes if l["id"] == lote_id), None) if lote_id else None
            nueva_incidencia = {
                "id": f"tarea-00{len(TAREAS_STORE) + 1}",
                "campo_id": campo_id,
                "campo_nombre": campo_nombre,
                "lote_id": lote_id,
                "lote_nombre": lote_sel["nombre"] if lote_sel else "Campo General",
                "tipo": "incidencia",
                "tipo_label": "⚠️ Novedad / Incidencia",
                "titulo": payload.get("titulo", "Incidencia de Campo").strip(),
                "responsable": user.get("nombre", "Operario Campo"),
                "prioridad": payload.get("prioridad", "alta"),
                "prioridad_label": payload.get("prioridad", "alta").title(),
                "estado": "pendiente",
                "estado_label": "Pendiente",
                "fecha": "2026-07-30",
                "observaciones": payload.get("observaciones") or "Incidencia registrada offline.",
                "valor_registrado": "Reporte de Campo",
            }
            TAREAS_STORE.insert(0, nueva_incidencia)

        elif tipo == "movimiento_stock":
            insumo = payload.get("insumo", "Insumo")
            cant = payload.get("cantidad", 0)
            unidad = payload.get("unidad", "litros")
            nuevo_stock = {
                "id": f"tarea-00{len(TAREAS_STORE) + 1}",
                "campo_id": campo_id,
                "campo_nombre": campo_nombre,
                "lote_id": None,
                "lote_nombre": "Galpón / Depósito",
                "tipo": "stock_insumos",
                "tipo_label": "📦 Stock e Insumos",
                "titulo": f"Consumo/Retiro: {insumo.strip()}",
                "responsable": user.get("nombre", "Operario Campo"),
                "prioridad": "media",
                "prioridad_label": "Media",
                "estado": "hecha",
                "estado_label": "Hecha",
                "fecha": "2026-07-30",
                "observaciones": payload.get("observaciones") or f"Retiro registrado de {cant} {unidad} de {insumo}.",
                "valor_registrado": f"{cant} {unidad}",
            }
            TAREAS_STORE.insert(0, nuevo_stock)

        elif tipo == "nueva_labor":
            lote_id = payload.get("lote_id")
            lote_sel = next((l for l in lotes if l["id"] == lote_id), None) if lote_id else None
            nueva_tarea = {
                "id": f"tarea-00{len(TAREAS_STORE) + 1}",
                "campo_id": campo_id,
                "campo_nombre": campo_nombre,
                "lote_id": lote_id,
                "lote_nombre": lote_sel["nombre"] if lote_sel else "Campo General",
                "tipo": payload.get("tipo", "siembra"),
                "tipo_label": "🌾 Labor Campo",
                "titulo": payload.get("titulo", "Nueva Labor").strip(),
                "responsable": payload.get("responsable", user.get("nombre", "Operario Campo")),
                "prioridad": payload.get("prioridad", "media"),
                "prioridad_label": payload.get("prioridad", "media").title(),
                "estado": "pendiente",
                "estado_label": "Pendiente",
                "fecha": "2026-07-30",
                "observaciones": payload.get("observaciones") or "Labor registrada offline.",
                "valor_registrado": "Programada",
            }
            TAREAS_STORE.insert(0, nueva_tarea)

        elif tipo == "iniciar_labor":
            tarea_id = payload.get("tarea_id")
            tarea = next((t for t in TAREAS_STORE if t["id"] == tarea_id), None)
            if tarea:
                tarea["estado"] = "en_curso"
                tarea["estado_label"] = "En Curso"

        elif tipo == "completar_tarea":
            tarea_id = payload.get("tarea_id")
            tarea = next((t for t in TAREAS_STORE if t["id"] == tarea_id), None)
            if tarea:
                tarea["estado"] = "hecha"
                tarea["estado_label"] = "Hecha"

        PROCESSED_ACTION_IDS.add(action_id)
        processed_count += 1

    campo_activo = await get_campo_activo_db(request, db)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )
    lotes_campo_activo = [l for l in lotes if l["campo_id"] == campo_activo["id"]]
    tareas_campo = [t for t in TAREAS_STORE if t["campo_id"] == campo_activo["id"]]

    return JSONResponse({
        "success": True,
        "processed_count": processed_count,
        "state": {
            "user": {"id": user["id"], "nombre": user["nombre"], "email": user["email"]},
            "campo_activo": campo_activo,
            "campos": campos,
            "lotes_campo": lotes_campo_activo,
            "weather": weather_data,
            "tareas": tareas_campo,
        }
    })


# ----------------------------------------------------------------------
# Módulo Comercial V1 - API & Vistas
# ----------------------------------------------------------------------

@app.get("/api/comercial/debug")
async def comercial_debug_api(
    request: Request,
    campania_id: Optional[str] = None,
    cultivo: Optional[str] = "soja",
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint JSON de prueba/debug para verificar los cálculos del motor comercial V1.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=status.HTTP_401_UNAUTHORIZED)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return JSONResponse(
            {"error": "Acceso denegado. El perfil Operario de Campo no tiene permisos comerciales."},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    if campania_id:
        camp_uuid = get_uuid(campania_id)
        camp_nombre = campania_id
    else:
        camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
        camp_uuid = camp_obj.id if camp_obj else None
        camp_nombre = camp_obj.nombre if camp_obj else "Campaña Activa"

    if not camp_uuid:
        return JSONResponse(
            {"error": "No se encontró ninguna campaña registrada."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    posicion = await calcular_posicion_comercial(db, cliente_id, camp_uuid, cultivo or "soja")

    posicion_json = {k: float(v) if isinstance(v, Decimal) else v for k, v in posicion.items()}

    return JSONResponse({
        "success": True,
        "cliente_id": str(cliente_id),
        "campania_id": str(camp_uuid),
        "campania_nombre": camp_nombre,
        "posicion": posicion_json,
    })


@app.get("/api/comercial/decision/evaluar")
async def comercial_decision_evaluar_api(
    request: Request,
    cultivo: Optional[str] = "maiz",
    humedad_grano_pct: Optional[float] = 17.5,
    costo_secada_punto_usd: Optional[float] = 2.50,
    lluvia_esperada_mm: Optional[float] = 0.0,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint JSON de evaluación determinística del Motor de Decisión 1.0 (Clima + Comercial + Operativo).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=status.HTTP_401_UNAUTHORIZED)

    from app.services.mercado import obtener_snapshot_precios_mercado, obtener_comparativa_futuros_mercado
    from app.services.clima import obtener_clima_para_campo_async
    from app.services.decision_motor import evaluar_motor_decisiones

    snapshot = await obtener_snapshot_precios_mercado(db, cultivos=[cultivo])
    p_spot_item = snapshot[0] if snapshot else {}
    p_spot_usd = p_spot_item.get("precio_usd_tn", 188.0)

    futuros = obtener_comparativa_futuros_mercado(snapshot)
    fut_item = next((f for f in futuros if f["cultivo"].lower() == cultivo.lower()), {})
    p_futuro_usd = fut_item.get("precio_futuro_usd", 195.0)
    spread_usd = fut_item.get("spread_usd", 7.0)

    clima = await obtener_clima_para_campo_async(db=db)

    contexto = {
        "cultivo": cultivo,
        "precio_fisico_usd": p_spot_usd,
        "precio_futuro_usd": p_futuro_usd,
        "spread_futuro_usd": spread_usd,
        "humedad_grano_pct": humedad_grano_pct,
        "costo_secada_punto_usd": costo_secada_punto_usd,
        "lluvia_esperada_mm": lluvia_esperada_mm if lluvia_esperada_mm > 0 else (14.5 if clima.get("alerta_lluvia") else 0.0),
        "viento_max_kmh": clima.get("viento_kmh", 14.0),
        "temp_min_c": 10.0,
        "alerta_viento": clima.get("alerta_viento"),
        "alerta_lluvia": clima.get("alerta_lluvia"),
        "alerta_helada": clima.get("alerta_helada"),
    }

    insights = evaluar_motor_decisiones(contexto)

    return JSONResponse({
        "success": True,
        "contexto_evaluado": contexto,
        "insights_generados": insights,
    })


@app.get("/comercial", response_class=HTMLResponse)
async def read_comercial_resumen(
    request: Request,
    campania_id: Optional[str] = None,
    cultivo: Optional[str] = "soja",
    mensaje: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Vista resumen principal del Módulo Comercial V1.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    if campania_id:
        camp_uuid = get_uuid(campania_id)
        camp_nombre = campania_id
    else:
        camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
        camp_uuid = camp_obj.id if camp_obj else None
        camp_nombre = camp_obj.nombre if camp_obj else "Campaña 2025/2026"

    cultivo_sel = (cultivo or "soja").strip().lower()
    from app.services.commercial_dashboard_service import get_commercial_dashboard_summary
    dashboard_summary = await get_commercial_dashboard_summary(
        db=db,
        cliente_id=cliente_id,
        cultivo=cultivo_sel,
        campania_id=camp_uuid,
    )

    if camp_uuid:
        posicion = await calcular_posicion_comercial(db, cliente_id, camp_uuid, cultivo_sel)
    else:
        posicion = {
            "cultivo": cultivo_sel,
            "produccion_total_tn": Decimal("0.0"),
            "tn_vendidas_precio_fijo": Decimal("0.0"),
            "tn_vendidas_a_fijar": Decimal("0.0"),
            "tn_comprometidas": Decimal("0.0"),
            "tn_libres": Decimal("0.0"),
            "porcentaje_cobertura": Decimal("0.0"),
            "tn_stock_silo_bolsa": Decimal("0.0"),
            "tn_stock_acopio": Decimal("0.0"),
            "tn_stock_total": Decimal("0.0"),
        }

    # Evaluador de insights del Agente Comercial
    from app.agents.comercial_rules import evaluar_insights_comerciales
    insights = evaluar_insights_comerciales(posicion)

    # Cargar snapshot de cotizaciones vigentes por cultivo (Soja, Maíz, Sorgo) con variación diaria
    from app.services.mercado import (
        obtener_snapshot_precios_mercado,
        obtener_historico_precios_mercado,
        generar_sparkline_data,
        obtener_comparativa_futuros_mercado,
    )
    precios_mercado = await obtener_snapshot_precios_mercado(db)

    # Cargar cotizaciones de referencia de futuros (Matba Rofex) comparadas vs físico actual
    futuros_mercado = obtener_comparativa_futuros_mercado(precios_mercado)

    # Cargar histórico corto de los 3 cultivos (Soja, Maíz, Sorgo) para navegación por Tabs
    historicos_mercado = {
        "soja": await obtener_historico_precios_mercado(db, cultivo="soja", limit=7),
        "maiz": await obtener_historico_precios_mercado(db, cultivo="maiz", limit=7),
        "sorgo": await obtener_historico_precios_mercado(db, cultivo="sorgo", limit=7),
    }
    historico_precios = historicos_mercado.get(cultivo_sel, [])

    # Generar trazados de mini gráficos (sparklines) por cultivo
    sparklines_mercado = {
        k: generar_sparkline_data(v) for k, v in historicos_mercado.items()
    }

    # Evaluador del Motor de Decisión 1.0 (Clima + Mercado + Operativo)
    from app.services.clima import obtener_clima_para_campo_async
    from app.services.decision_motor import evaluar_motor_decisiones
    clima_info = await obtener_clima_para_campo_async(db=db)
    fut_item = next((f for f in futuros_mercado if f["cultivo"].lower() == cultivo_sel.lower()), {})
    humedad_ini = 17.5 if cultivo_sel == "maiz" else 14.5
    contexto_decision_ini = {
        "cultivo": cultivo_sel,
        "precio_fisico_usd": fut_item.get("precio_fisico_usd", 188.0),
        "precio_futuro_usd": fut_item.get("precio_futuro_usd", 195.0),
        "spread_futuro_usd": fut_item.get("spread_usd", 7.0),
        "humedad_grano_pct": humedad_ini,
        "costo_secada_punto_usd": 2.50,
        "lluvia_esperada_mm": 0.0,
        "viento_max_kmh": clima_info.get("viento_kmh", 14.0),
        "temp_min_c": 10.0,
        "alerta_viento": clima_info.get("alerta_viento"),
        "alerta_lluvia": clima_info.get("alerta_lluvia"),
        "alerta_helada": clima_info.get("alerta_helada"),
    }
    decision_insights = evaluar_motor_decisiones(contexto_decision_ini)

    return templates.TemplateResponse(
        request=request,
        name="comercial_resumen.html",
        context={
            "user": user,
            "campania_activa": camp_nombre,
            "cultivo_seleccionado": cultivo_sel,
            "dashboard_summary": dashboard_summary,
            "posicion": posicion,
            "insights": insights,
            "precios_mercado": precios_mercado,
            "futuros_mercado": futuros_mercado,
            "historicos_mercado": historicos_mercado,
            "sparklines_mercado": sparklines_mercado,
            "historico_precios": historico_precios,
            "decision_insights": decision_insights,
            "mensaje_exito": mensaje,
        },
    )


@app.get("/comercial/stock", response_class=HTMLResponse)
async def read_comercial_stock(
    request: Request,
    cultivo: Optional[str] = "soja",
    mensaje: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Vista operativa de gestión de Stock Físico V1 (Partidas, Ubicaciones y Movimientos Auditables).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    lotes = await fetch_lotes_dicts(db)
    campos_map = {str(c["id"]): c["nombre"] for c in campos}
    lotes_map = {str(l["id"]): l["nombre"] for l in lotes}

    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    camp_uuid = camp_obj.id if camp_obj else None
    camp_nombre = camp_obj.nombre if camp_obj else "Campaña 2025/2026"

    # Todas las campañas del cliente para el select
    from app.models import Campania
    res_camps = await db.execute(select(Campania).where(Campania.cliente_id == cliente_id).order_by(Campania.fecha_inicio.desc()))
    campanias_objs = res_camps.scalars().all()
    campanias_list = [{"id": str(c.id), "nombre": c.nombre} for c in campanias_objs]
    campanias_map = {str(c.id): c.nombre for c in campanias_objs}

    cultivo_sel = (cultivo or "soja").strip().lower()

    # 1. Resumen Agregado de Stock Físico Registrado y Comerciales V1
    from app.services.stock_service import (
        fetch_aggregated_stock_v1_summary,
        get_stock_partida_balance,
        get_stock_partida_commercial_balance,
        reserve_stock_for_commitment,
        release_stock_reservation,
        allocate_stock_to_delivery,
        cancel_stock_delivery_allocation,
        build_commitment_display_label,
        get_compromisos_saldos_map,
        format_compromiso_dict,
    )
    stock_summary = await fetch_aggregated_stock_v1_summary(db, cliente_id, cultivo_sel)

    # 2. Producción Teórica Estimada (Separada Informativa)
    from app.services.comercial import calcular_posicion_comercial
    pos_comercial = await calcular_posicion_comercial(db, cliente_id, camp_uuid, cultivo_sel)
    produccion_teorica_tn = pos_comercial.get("produccion_total_tn", Decimal("0.0"))

    # 3. Partidas Físicas Reales con Saldos Comerciales V1 (StockPartida)
    from app.models import (
        StockPartida,
        StorageLocation,
        StockMovement,
        StockQualityMeasurement,
        StockReservation,
        StockDeliveryAllocation,
        CompromisoGrano,
        GrainDelivery,
        StockGrano,
    )
    from sqlalchemy.orm import selectinload

    stmt_partidas = (
        select(StockPartida)
        .options(
            selectinload(StockPartida.storage_location),
            selectinload(StockPartida.quality_measurements),
            selectinload(StockPartida.campania),
        )
        .where(
            StockPartida.cliente_id == cliente_id,
            func.lower(StockPartida.cultivo) == cultivo_sel,
        )
        .order_by(StockPartida.fecha_creacion.desc())
    )
    res_partidas = await db.execute(stmt_partidas)
    partidas_objs = res_partidas.scalars().all()

    partidas_list = []
    for p in partidas_objs:
        bal = await get_stock_partida_commercial_balance(db, cliente_id, p.id)
        dias_store = (date.today() - p.fecha_ingreso).days if p.fecha_ingreso else 0

        # Histórico de calidad y última humedad válida registrada
        from app.services.stock_service import is_valid_humidity
        hum_last = None
        hum_date_last = None
        st_calidad_last = None
        q_history = []
        has_invalid_legacy = False
        if p.quality_measurements:
            sorted_q = sorted(p.quality_measurements, key=lambda q: q.measured_at, reverse=True)
            st_calidad_last = sorted_q[0].estado_calidad
            for q in sorted_q:
                is_invalid = False
                if q.humedad_pct is not None:
                    is_invalid = not is_valid_humidity(q.humedad_pct)
                    if is_invalid:
                        has_invalid_legacy = True
                    elif hum_last is None:
                        hum_last = float(q.humedad_pct)
                        hum_date_last = q.measured_at.strftime("%d/%m/%Y") if q.measured_at else ""

                q_history.append({
                    "id": str(q.id),
                    "measured_at": q.measured_at.strftime("%d/%m/%Y %H:%M") if q.measured_at else "",
                    "humedad_pct": float(q.humedad_pct) if q.humedad_pct is not None else None,
                    "temperatura_c": float(q.temperatura_c) if q.temperatura_c is not None else None,
                    "estado_calidad": q.estado_calidad,
                    "fuente": q.fuente,
                    "observaciones": q.observaciones or "",
                    "is_invalid_legacy": is_invalid,
                })

        partidas_list.append({
            "id": str(p.id),
            "tracking_number": p.tracking_number,
            "cultivo": p.cultivo,
            "campania_nombre": p.campania.nombre if p.campania else "Campaña General",
            "origen_conocido": p.origen_conocido,
            "campo_nombre": campos_map.get(str(p.campo_id), "General") if p.campo_id else "General",
            "lote_nombre": lotes_map.get(str(p.lote_id), "") if p.lote_id else "",
            "origen_descripcion": p.origen_descripcion or "",
            "ubicacion_nombre": p.storage_location.nombre if p.storage_location else "Sin Ubicación",
            "fecha_ingreso": str(p.fecha_ingreso) if p.fecha_ingreso else "",
            "dias_almacenado": dias_store,
            "humedad_ultima": hum_last,
            "humedad_fecha_ultima": hum_date_last,
            "estado_calidad_ultimo": st_calidad_last or "apto",
            "has_invalid_legacy": has_invalid_legacy,
            "quality_history": q_history,
            "saldo_fisico_kg": float(bal["stock_fisico_kg"]),
            "saldo_fisico_tn": float(bal["stock_fisico_tn"]),
            "saldo_reservado_tn": float(bal["stock_reservado_tn"]),
            "saldo_asignado_tn": float(bal["stock_asignado_tn"]),
            "saldo_disponible_tn": float(bal["stock_disponible_tn"]),
            "reservas_activas_count": bal["reservas_activas_count"],
            "asignaciones_activas_count": bal["asignaciones_activas_count"],
            "estado": p.estado,
            "observaciones": p.observaciones or "",
        })

    # 4. Ubicaciones de Guarda (StorageLocation con Ocupación Física Real)
    from app.services.stock_service import get_storage_location_occupancy
    stmt_locs = select(StorageLocation).where(StorageLocation.cliente_id == cliente_id).order_by(StorageLocation.nombre.asc())
    res_locs = await db.execute(stmt_locs)
    locs_objs = res_locs.scalars().all()

    ubicaciones_list = []
    for u in locs_objs:
        occ = await get_storage_location_occupancy(db, cliente_id, u.id)
        ubicaciones_list.append({
            "id": str(u.id),
            "nombre": u.nombre,
            "tipo": u.tipo,
            "campo_id": str(u.campo_id) if u.campo_id else "",
            "campo_nombre": campos_map.get(str(u.campo_id), "") if u.campo_id else "",
            "identificador_fisico": u.identificador_fisico or "",
            "capacidad_nominal_tn": float(occ["capacidad_nominal_tn"]) if occ["capacidad_nominal_tn"] is not None else None,
            "stock_actual_tn": float(occ["occupied_tn"]),
            "disponible_tn": float(occ["available_capacity_tn"]) if occ["available_capacity_tn"] is not None else None,
            "ocupacion_pct": float(occ["occupancy_pct"]) if occ["occupancy_pct"] is not None else None,
            "supera_capacidad": occ["estado_capacidad"] == "sobrecapacidad",
            "estado_capacidad": occ["estado_capacidad"],
            "requires_capacity": occ["requires_capacity"],
            "estado": u.estado,
            "observaciones": u.observaciones or "",
        })

    # 5. Movimientos Auditables (StockMovement)
    stmt_movs = (
        select(StockMovement)
        .options(selectinload(StockMovement.stock_partida))
        .where(StockMovement.cliente_id == cliente_id)
        .order_by(StockMovement.fecha_movimiento.desc())
        .limit(50)
    )
    res_movs = await db.execute(stmt_movs)
    movs_objs = res_movs.scalars().all()

    movimientos_list = []
    for m in movs_objs:
        movimientos_list.append({
            "id": str(m.id),
            "fecha_movimiento": m.fecha_movimiento.strftime("%Y-%m-%d %H:%M") if m.fecha_movimiento else "",
            "tracking_partida": m.stock_partida.tracking_number if m.stock_partida else "N/D",
            "tipo": m.tipo,
            "cantidad_kg": float(m.cantidad_kg),
            "motivo": m.motivo or "",
            "observaciones": m.observaciones or "",
        })

    # 6. Reservas de Stock (StockReservation)
    stmt_reservas = (
        select(StockReservation)
        .options(selectinload(StockReservation.stock_partida), selectinload(StockReservation.compromiso))
        .where(StockReservation.cliente_id == cliente_id)
        .order_by(StockReservation.fecha_reserva.desc())
    )
    res_res = await db.execute(stmt_reservas)
    reservas_objs = res_res.scalars().all()

    reservas_list = []
    for r in reservas_objs:
        reservas_list.append({
            "id": str(r.id),
            "tracking_partida": r.stock_partida.tracking_number if r.stock_partida else "N/D",
            "partida_id": str(r.stock_partida_id),
            "compromiso_concepto": r.compromiso.concepto if r.compromiso else "N/D",
            "compromiso_beneficiario": r.compromiso.beneficiario if r.compromiso else "",
            "compromiso_label": build_commitment_display_label(r.compromiso) if r.compromiso else (r.compromiso.concepto if r.compromiso else "N/D"),
            "cantidad_reserva_tn": float(r.cantidad_reserva_kg / Decimal("1000.0")),
            "estado": r.estado,
            "fecha_reserva": r.fecha_reserva.strftime("%Y-%m-%d %H:%M") if r.fecha_reserva else "",
            "observaciones": r.observaciones or "",
        })

    # 7. Asignaciones a Entregas (StockDeliveryAllocation)
    stmt_asigs = (
        select(StockDeliveryAllocation)
        .options(selectinload(StockDeliveryAllocation.stock_partida), selectinload(StockDeliveryAllocation.delivery))
        .where(StockDeliveryAllocation.cliente_id == cliente_id)
        .order_by(StockDeliveryAllocation.fecha_asignacion.desc())
    )
    res_asigs = await db.execute(stmt_asigs)
    asigs_objs = res_asigs.scalars().all()

    asignaciones_list = []
    for a in asigs_objs:
        asignaciones_list.append({
            "id": str(a.id),
            "tracking_partida": a.stock_partida.tracking_number if a.stock_partida else "N/D",
            "tracking_entrega": a.delivery.tracking_number if a.delivery else "N/D",
            "destino_entrega": (a.delivery.acopio_receptor or a.delivery.destination_final_reference or "") if a.delivery else "",
            "cantidad_tn": float(a.cantidad_kg / Decimal("1000.0")),
            "origen_asignacion": a.origen_asignacion,
            "estado": a.estado,
            "fecha_asignacion": a.fecha_asignacion.strftime("%Y-%m-%d %H:%M") if a.fecha_asignacion else "",
            "observaciones": a.observaciones or "",
        })

    # 8. Compromisos y Entregas del Cliente para selects de modales
    stmt_comp = select(CompromisoGrano).where(CompromisoGrano.cliente_id == cliente_id, CompromisoGrano.cumplido == False)
    res_comp = await db.execute(stmt_comp)
    compromisos_objs = res_comp.scalars().all()
    saldos_map = await get_compromisos_saldos_map(db, cliente_id)
    compromisos_list = [
        format_compromiso_dict(c, saldo_tn=saldos_map.get(c.id, c.toneladas_comprometidas))
        for c in compromisos_objs
    ]

    stmt_del = select(GrainDelivery).where(GrainDelivery.cliente_id == cliente_id).order_by(GrainDelivery.fecha_creacion.desc())
    res_del = await db.execute(stmt_del)
    deliveries_objs = res_del.scalars().all()
    deliveries_list = [
        {
            "id": str(d.id),
            "tracking_number": d.tracking_number,
            "destino_nombre": (d.acopio_receptor or d.destination_final_reference or "Destino N/D"),
            "cultivo": d.cultivo,
            "toneladas_estimadas": float(d.toneladas_planificadas) if d.toneladas_planificadas else 0.0,
        }
        for d in deliveries_objs
    ]

    # 9. Registros Legacy (StockGrano)
    stmt_legacy = select(StockGrano).where(
        StockGrano.cliente_id == cliente_id,
        func.lower(StockGrano.cultivo) == cultivo_sel,
    )
    res_legacy = await db.execute(stmt_legacy)
    legacy_objs = res_legacy.scalars().all()
    stocks_legacy = [
        {
            "id": str(st.id),
            "campo_nombre": campos_map.get(str(st.campo_id), "General"),
            "identificador": st.identificador,
            "toneladas_almacenadas": float(st.toneladas_almacenadas or 0.0),
        }
        for st in legacy_objs
    ]

    return templates.TemplateResponse(
        request=request,
        name="comercial_stock.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "lotes": lotes,
            "campanias": campanias_list,
            "campania_activa": camp_nombre,
            "cultivo_seleccionado": cultivo_sel,
            "stock_summary": stock_summary,
            "produccion_teorica_tn": produccion_teorica_tn,
            "partidas": partidas_list,
            "ubicaciones": ubicaciones_list,
            "movimientos": movimientos_list,
            "reservas": reservas_list,
            "asignaciones": asignaciones_list,
            "compromisos": compromisos_list,
            "deliveries": deliveries_list,
            "stocks_legacy": stocks_legacy,
            "today_iso": date.today().isoformat(),
            "mensaje": mensaje,
            "error": error,
        },
    )


@app.post("/comercial/stock/reservas/crear")
async def create_stock_reservation_v1(
    request: Request,
    stock_partida_id: str = Form(...),
    compromiso_id: str = Form(...),
    cantidad_valor: str = Form(...),
    unidad_medida: str = Form("tn"),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de Reserva de Stock Físico para un Compromiso Comercial (Stock 1B).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    cant_dec = parse_decimal_ar(cantidad_valor)
    if not cant_dec or cant_dec <= Decimal("0.0"):
        return RedirectResponse("/comercial/stock?error=La+cantidad+a+reservar+debe+ser+mayor+a+0", status_code=status.HTTP_303_SEE_OTHER)

    from app.services.stock_service import reserve_stock_for_commitment
    try:
        reserva = await reserve_stock_for_commitment(
            db=db,
            cliente_id=cliente_id,
            stock_partida_id=get_uuid(stock_partida_id),
            compromiso_id=get_uuid(compromiso_id),
            cantidad_valor=cant_dec,
            unidad_medida=unidad_medida,
            observaciones=observaciones,
            user_id=get_uuid(user.get("id")),
        )
        msg = f"Reserva de {cant_dec} {unidad_medida.upper()} creada exitosamente."
        return RedirectResponse(f"/comercial/stock?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        err_msg = str(e).replace(" ", "+")
        return RedirectResponse(f"/comercial/stock?error={err_msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/stock/reservas/liberar")
async def release_stock_reservation_v1(
    request: Request,
    reservation_id: str = Form(...),
    motivo_liberacion: str = Form(...),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Liberación de Reserva de Stock (Stock 1B).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    from app.services.stock_service import release_stock_reservation
    try:
        await release_stock_reservation(
            db=db,
            cliente_id=cliente_id,
            reservation_id=get_uuid(reservation_id),
            motivo_liberacion=motivo_liberacion,
            observaciones=observaciones,
            user_id=get_uuid(user.get("id")),
        )
        return RedirectResponse("/comercial/stock?mensaje=Reserva+liberada+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        err_msg = str(e).replace(" ", "+")
        return RedirectResponse(f"/comercial/stock?error={err_msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/stock/asignaciones/crear")
async def create_stock_allocation_v1(
    request: Request,
    stock_partida_id: str = Form(...),
    grain_delivery_id: str = Form(...),
    cantidad_valor: str = Form(...),
    unidad_medida: str = Form("tn"),
    stock_reservation_id: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Asignación Manual de Partida a Entrega de Grano (Stock 1B).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    cant_dec = parse_decimal_ar(cantidad_valor)
    if not cant_dec or cant_dec <= Decimal("0.0"):
        return RedirectResponse("/comercial/stock?error=La+cantidad+a+asignar+debe+ser+mayor+a+0", status_code=status.HTTP_303_SEE_OTHER)

    from app.services.stock_service import allocate_stock_to_delivery
    try:
        res_uuid = get_uuid(stock_reservation_id) if stock_reservation_id and stock_reservation_id.strip() else None
        asig = await allocate_stock_to_delivery(
            db=db,
            cliente_id=cliente_id,
            stock_partida_id=get_uuid(stock_partida_id),
            grain_delivery_id=get_uuid(grain_delivery_id),
            cantidad_valor=cant_dec,
            unidad_medida=unidad_medida,
            stock_reservation_id=res_uuid,
            observaciones=observaciones,
            user_id=get_uuid(user.get("id")),
        )
        msg = f"Asignación de {cant_dec} {unidad_medida.upper()} a entrega registrada exitosamente."
        return RedirectResponse(f"/comercial/stock?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        err_msg = str(e).replace(" ", "+")
        return RedirectResponse(f"/comercial/stock?error={err_msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/stock/asignaciones/cancelar")
async def cancel_stock_allocation_v1(
    request: Request,
    allocation_id: str = Form(...),
    motivo_cancelacion: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancelación de Asignación a Entrega (Stock 1B).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    from app.services.stock_service import cancel_stock_delivery_allocation
    try:
        await cancel_stock_delivery_allocation(
            db=db,
            cliente_id=cliente_id,
            allocation_id=get_uuid(allocation_id),
            motivo_cancelacion=motivo_cancelacion,
            user_id=get_uuid(user.get("id")),
        )
        return RedirectResponse("/comercial/stock?mensaje=Asignación+cancelada+exitosamente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        err_msg = str(e).replace(" ", "+")
        return RedirectResponse(f"/comercial/stock?error={err_msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/stock/partidas/crear")
async def create_stock_partida_v1(
    request: Request,
    cultivo: str = Form(...),
    storage_location_id: str = Form(...),
    cantidad_valor: str = Form(...),
    unidad_medida: str = Form("tn"),
    fecha_ingreso: str = Form(...),
    campania_id: Optional[str] = Form(None),
    campo_id: Optional[str] = Form(None),
    lote_id: Optional[str] = Form(None),
    origen_conocido: Optional[str] = Form("false"),
    origen_descripcion: Optional[str] = Form(None),
    fecha_cosecha: Optional[str] = Form(None),
    humedad_pct: Optional[str] = Form(None),
    measured_at: Optional[str] = Form(None),
    estado_calidad: Optional[str] = Form("apto"),
    fuente_medicion: Optional[str] = Form("propia"),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de Partida Física de Stock (StockPartida) con Movimiento de Ingreso Inicial atómico.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    loc_uuid = get_uuid(storage_location_id)

    # Validar multitenancy de la ubicación
    from app.models import (
        StorageLocation,
        StockPartida,
        StockMovement,
        StockQualityMeasurement,
    )
    stmt_loc = select(StorageLocation).where(
        StorageLocation.id == loc_uuid,
        StorageLocation.cliente_id == cliente_id,
    )
    res_loc = await db.execute(stmt_loc)
    loc_obj = res_loc.scalars().first()
    if not loc_obj:
        return RedirectResponse("/comercial/stock?error=Ubicación+de+guarda+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    # Normalizar cantidad a kg en Decimal
    cant_dec = parse_decimal_ar(cantidad_valor)
    if not cant_dec or cant_dec <= Decimal("0.0"):
        return RedirectResponse("/comercial/stock?error=La+cantidad+inicial+debe+ser+mayor+a+0", status_code=status.HTTP_303_SEE_OTHER)

    if (unidad_medida or "").strip().lower() == "tn":
        cantidad_kg = cant_dec * Decimal("1000.0")
    else:
        cantidad_kg = cant_dec

    # Validar ocupación física y capacidad nominal de la ubicación de guarda
    from app.services.stock_service import get_storage_location_occupancy
    occ = await get_storage_location_occupancy(db, cliente_id, loc_obj.id)

    if occ["requires_capacity"] and occ["estado_capacidad"] == "capacidad_pendiente":
        err_msg = f"La ubicación '{loc_obj.nombre}' requiere definir su capacidad nominal antes de recibir nuevos ingresos de stock."
        return RedirectResponse(f"/comercial/stock?error={err_msg.replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    if occ["capacity_kg"] is not None:
        if cantidad_kg > occ["available_capacity_kg"]:
            cap_tn_val = (occ["capacity_kg"] / Decimal("1000.0")).quantize(Decimal("0.01"))
            ocu_tn_val = (occ["occupied_kg"] / Decimal("1000.0")).quantize(Decimal("0.01"))
            disp_tn_val = max(Decimal("0.0"), (occ["available_capacity_kg"] / Decimal("1000.0"))).quantize(Decimal("0.01"))
            req_tn_val = (cantidad_kg / Decimal("1000.0")).quantize(Decimal("0.01"))

            cap_str = f"{cap_tn_val}".replace(".", ",")
            ocu_str = f"{ocu_tn_val}".replace(".", ",")
            disp_str = f"{disp_tn_val}".replace(".", ",")
            req_str = f"{req_tn_val}".replace(".", ",")

            err_msg = (
                f"La ubicación ‘{loc_obj.nombre}’ tiene capacidad de {cap_str} Tn, "
                f"posee {ocu_str} Tn ocupadas y sólo dispone de {disp_str} Tn. "
                f"No es posible cargar {req_str} Tn."
            )
            return RedirectResponse(f"/comercial/stock?error={err_msg.replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    # Validar fechas
    try:
        f_ingreso = datetime.strptime(fecha_ingreso.strip(), "%Y-%m-%d").date()
    except Exception:
        f_ingreso = date.today()

    f_cosecha = None
    if fecha_cosecha and fecha_cosecha.strip():
        try:
            f_cosecha = datetime.strptime(fecha_cosecha.strip(), "%Y-%m-%d").date()
        except Exception:
            pass

    # Validar origen exacto vs descripción
    is_origen_conocido = (origen_conocido or "").strip().lower() in ["true", "on", "1", "yes"]
    origen_desc = origen_descripcion.strip() if origen_descripcion and origen_descripcion.strip() else None

    if not is_origen_conocido and not origen_desc:
        return RedirectResponse("/comercial/stock?error=Debe+especificar+la+descripción+del+origen+si+no+se+conoce+el+campo/lote+exacto", status_code=status.HTTP_303_SEE_OTHER)

    # Validar FKs de campo, lote y campaña
    c_uuid = get_uuid(campo_id) if is_origen_conocido and campo_id and campo_id.strip() else None
    l_uuid = get_uuid(lote_id) if is_origen_conocido and lote_id and lote_id.strip() else None
    camp_uuid = get_uuid(campania_id) if campania_id and campania_id.strip() else None

    if c_uuid:
        from app.models import Campo
        res_c = await db.execute(select(Campo).where(Campo.id == c_uuid, Campo.cliente_id == cliente_id))
        if not res_c.scalars().first():
            return RedirectResponse("/comercial/stock?error=Campo+no+autorizado", status_code=status.HTTP_303_SEE_OTHER)

    if l_uuid:
        from app.models import Lote
        res_l = await db.execute(select(Lote).where(Lote.id == l_uuid, Lote.cliente_id == cliente_id))
        if not res_l.scalars().first():
            return RedirectResponse("/comercial/stock?error=Lote+no+autorizado", status_code=status.HTTP_303_SEE_OTHER)

    if camp_uuid:
        from app.models import Campania
        res_camp = await db.execute(select(Campania).where(Campania.id == camp_uuid, Campania.cliente_id == cliente_id))
        if not res_camp.scalars().first():
            return RedirectResponse("/comercial/stock?error=Campaña+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    # Generar tracking number legible e inmutable (STK-YYYYMMDD-XXXX)
    date_str = datetime.now().strftime("%Y%m%d")
    unique_suffix = uuid.uuid4().hex[:4].upper()
    tracking_number = f"STK-{date_str}-{unique_suffix}"

    # 1. Crear Partida
    partida = StockPartida(
        cliente_id=cliente_id,
        tracking_number=tracking_number,
        cultivo=(cultivo or "soja").strip().lower(),
        storage_location_id=loc_obj.id,
        fecha_ingreso=f_ingreso,
        fecha_cosecha=f_cosecha,
        origen_conocido=is_origen_conocido,
        origen_descripcion=origen_desc,
        campo_id=c_uuid,
        lote_id=l_uuid,
        campania_id=camp_uuid,
        cantidad_inicial_kg=cantidad_kg,
        estado="activa",
        observaciones=observaciones.strip() if observaciones else None,
        created_by_user_id=get_uuid(user.get("id")),
    )
    db.add(partida)
    await db.flush()

    # 2. Crear Movimiento Inicial Atómico
    mov_inicial = StockMovement(
        cliente_id=cliente_id,
        stock_partida_id=partida.id,
        tipo="ingreso_inicial",
        cantidad_kg=cantidad_kg,
        motivo="Ingreso Inicial de Partida",
        observaciones=f"Carga inicial de {cant_dec} {unidad_medida.upper()} en {loc_obj.nombre}",
        created_by_user_id=get_uuid(user.get("id")),
    )
    db.add(mov_inicial)

    # 3. Validar y crear Medición de Calidad Inicial si corresponde
    from app.services.stock_service import validate_humedad_pct, add_quality_measurement_to_partida
    try:
        hum_dec = validate_humedad_pct(humedad_pct)
    except ValueError as e:
        err_msg = str(e).replace(" ", "+")
        return RedirectResponse(f"/comercial/stock?error={err_msg}", status_code=status.HTTP_303_SEE_OTHER)

    if hum_dec is not None or (estado_calidad and estado_calidad != "apto"):
        m_at = datetime.now()
        if measured_at and measured_at.strip():
            try:
                m_at = datetime.strptime(measured_at.strip(), "%Y-%m-%d")
            except Exception:
                pass

        await add_quality_measurement_to_partida(
            db=db,
            cliente_id=cliente_id,
            stock_partida_id=partida.id,
            measured_at=m_at,
            humedad_pct_val=hum_dec,
            estado_calidad=estado_calidad or "apto",
            fuente=fuente_medicion or "propia",
            observaciones="Medición inicial registrada al cargar la partida",
            user_id=get_uuid(user.get("id")),
        )

    await db.commit()

    msg = f"Partida '{tracking_number}' registrada exitosamente ({(cantidad_kg/Decimal('1000.0')):.2f} Tn en {loc_obj.nombre})."
    return RedirectResponse(
        f"/comercial/stock?cultivo={cultivo.strip().lower()}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/comercial/stock/partidas/{partida_id}/mediciones/crear")
async def create_partida_quality_measurement_v1(
    request: Request,
    partida_id: str,
    measured_at: Optional[str] = Form(None),
    humedad_pct: Optional[str] = Form(None),
    temperatura_c: Optional[str] = Form(None),
    estado_calidad: Optional[str] = Form("apto"),
    fuente: Optional[str] = Form("propia"),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de medición histórica de calidad sobre una partida física de stock.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    m_at = None
    if measured_at and measured_at.strip():
        try:
            m_at = datetime.fromisoformat(measured_at.strip())
        except Exception:
            try:
                m_at = datetime.strptime(measured_at.strip(), "%Y-%m-%d")
            except Exception:
                m_at = datetime.now()

    from app.services.stock_service import add_quality_measurement_to_partida
    try:
        await add_quality_measurement_to_partida(
            db=db,
            cliente_id=cliente_id,
            stock_partida_id=get_uuid(partida_id),
            measured_at=m_at,
            humedad_pct_val=humedad_pct,
            temperatura_c_val=temperatura_c,
            estado_calidad=estado_calidad or "apto",
            fuente=fuente or "propia",
            observaciones=observaciones,
            user_id=get_uuid(user.get("id")),
        )
        msg = "Medición de calidad registrada exitosamente en el historial de la partida."
        return RedirectResponse(f"/comercial/stock?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        err_msg = str(e).replace(" ", "+")
        return RedirectResponse(f"/comercial/stock?error={err_msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/stock/ubicaciones/crear")
async def create_storage_location_v1(
    request: Request,
    nombre: str = Form(...),
    tipo: str = Form("silo_propio"),
    campo_id: Optional[str] = Form(None),
    ubicacion_referencia: Optional[str] = Form(None),
    identificador_fisico: Optional[str] = Form(None),
    capacidad_nominal_tn: Optional[str] = Form(None),
    estado: Optional[str] = Form("activo"),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de Ubicación de Guarda / Depósito (StorageLocation).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    if not nombre or not nombre.strip():
        return RedirectResponse("/comercial/stock?error=El+nombre+de+la+ubicación+es+requerido", status_code=status.HTTP_303_SEE_OTHER)

    c_uuid = get_uuid(campo_id) if campo_id and campo_id.strip() else None
    if c_uuid:
        from app.models import Campo
        res_c = await db.execute(select(Campo).where(Campo.id == c_uuid, Campo.cliente_id == cliente_id))
        if not res_c.scalars().first():
            return RedirectResponse("/comercial/stock?error=Campo+asociado+no+autorizado", status_code=status.HTTP_303_SEE_OTHER)

    cap_dec = parse_decimal_ar(capacidad_nominal_tn)
    tipo_norm = tipo.strip().lower()

    if tipo_norm in ["silo_propio", "silobolsa"]:
        if cap_dec is None or cap_dec <= Decimal("0.0"):
            return RedirectResponse(
                "/comercial/stock?error=La+capacidad+nominal+en+Tn+es+obligatoria+y+debe+ser+mayor+a+0+para+Silos+y+Silobolsas",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    from app.models import StorageLocation
    # Verificar unique constraint por (cliente_id, tipo, nombre)
    stmt_dup = select(StorageLocation).where(
        StorageLocation.cliente_id == cliente_id,
        StorageLocation.tipo == tipo_norm,
        func.lower(StorageLocation.nombre) == nombre.strip().lower(),
    )
    res_dup = await db.execute(stmt_dup)
    if res_dup.scalars().first():
        return RedirectResponse(
            f"/comercial/stock?error=Ya+existe+una+ubicación+con+el+nombre+'{nombre.strip()}'",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    nueva_loc = StorageLocation(
        cliente_id=cliente_id,
        nombre=nombre.strip(),
        tipo=tipo_norm,
        campo_id=c_uuid,
        ubicacion_referencia=ubicacion_referencia.strip() if ubicacion_referencia else None,
        identificador_fisico=identificador_fisico.strip() if identificador_fisico else None,
        capacidad_nominal_tn=cap_dec,
        estado=estado if estado in ["activo", "lleno", "vacio", "mantenimiento", "cerrado"] else "activo",
        observaciones=observaciones.strip() if observaciones else None,
    )

    db.add(nueva_loc)
    await db.commit()

    msg = f"Ubicación '{nombre.strip()}' creada exitosamente."
    return RedirectResponse(f"/comercial/stock?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/stock/ubicaciones/{location_id}/editar")
async def update_storage_location_v1(
    request: Request,
    location_id: str,
    nombre: str = Form(...),
    tipo: str = Form(...),
    campo_id: Optional[str] = Form(None),
    identificador_fisico: Optional[str] = Form(None),
    capacidad_nominal_tn: Optional[str] = Form(None),
    estado: Optional[str] = Form("activo"),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Edición de Ubicación de Guarda con validación de piso por ocupación física actual.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    loc_uuid = get_uuid(location_id)

    from app.models import StorageLocation
    stmt_loc = select(StorageLocation).where(StorageLocation.id == loc_uuid, StorageLocation.cliente_id == cliente_id)
    res_loc = await db.execute(stmt_loc)
    loc_obj = res_loc.scalars().first()
    if not loc_obj:
        return RedirectResponse("/comercial/stock?error=Ubicación+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    cap_dec = parse_decimal_ar(capacidad_nominal_tn)
    tipo_norm = tipo.strip().lower()

    if tipo_norm in ["silo_propio", "silobolsa"]:
        if cap_dec is None or cap_dec <= Decimal("0.0"):
            return RedirectResponse(
                "/comercial/stock?error=La+capacidad+nominal+en+Tn+es+obligatoria+y+debe+ser+mayor+a+0+para+Silos+y+Silobolsas",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    # Validar que la nueva capacidad no sea menor que la ocupación física actual
    from app.services.stock_service import get_storage_location_occupancy
    occ = await get_storage_location_occupancy(db, cliente_id, loc_obj.id)
    ocupado_actual_tn = occ["occupied_tn"]

    if cap_dec is not None and (cap_dec * Decimal("1000.0")) < occ["occupied_kg"]:
        err_msg = f"No es posible reducir la capacidad a {cap_dec} Tn porque la ubicación tiene actualmente {ocupado_actual_tn} Tn ocupadas."
        return RedirectResponse(f"/comercial/stock?error={err_msg.replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)

    loc_obj.nombre = nombre.strip()
    loc_obj.tipo = tipo_norm
    loc_obj.campo_id = get_uuid(campo_id) if campo_id and campo_id.strip() else None
    loc_obj.identificador_fisico = identificador_fisico.strip() if identificador_fisico and identificador_fisico.strip() else None
    loc_obj.capacidad_nominal_tn = cap_dec
    loc_obj.estado = estado.strip().lower() if estado else "activo"
    loc_obj.observaciones = observaciones.strip() if observaciones and observaciones.strip() else None

    await db.commit()
    return RedirectResponse("/comercial/stock?mensaje=Ubicación+actualizada+exitosamente", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/stock/movimientos/ajuste")
async def create_stock_adjustment_v1(
    request: Request,
    stock_partida_id: str = Form(...),
    tipo_ajuste: str = Form(...),
    cantidad_valor: str = Form(...),
    unidad_medida: str = Form("tn"),
    motivo: str = Form(...),
    observaciones: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Registro controlado de Ajuste de Inventario sobre una partida existente.
    Garantiza que el saldo físico resultante no quede negativo.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    p_uuid = get_uuid(stock_partida_id)

    from app.models import StockPartida, StockMovement
    from app.services.stock_service import get_stock_partida_balance

    stmt_p = select(StockPartida).where(
        StockPartida.id == p_uuid,
        StockPartida.cliente_id == cliente_id,
    )
    res_p = await db.execute(stmt_p)
    partida = res_p.scalars().first()
    if not partida:
        return RedirectResponse("/comercial/stock?error=Partida+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    if not motivo or not motivo.strip() or not observaciones or not observaciones.strip():
        return RedirectResponse("/comercial/stock?error=El+motivo+y+las+observaciones+son+obligatorios+para+ajustes+de+inventario", status_code=status.HTTP_303_SEE_OTHER)

    cant_dec = parse_decimal_ar(cantidad_valor)
    if not cant_dec or cant_dec <= Decimal("0.0"):
        return RedirectResponse("/comercial/stock?error=La+cantidad+del+ajuste+debe+ser+mayor+a+0", status_code=status.HTTP_303_SEE_OTHER)

    if (unidad_medida or "").strip().lower() == "tn":
        cantidad_kg = cant_dec * Decimal("1000.0")
    else:
        cantidad_kg = cant_dec

    is_incremento = (tipo_ajuste or "").strip().lower() == "incremento"
    delta_kg = cantidad_kg if is_incremento else -cantidad_kg

    # Obtener saldo actual
    bal_actual = await get_stock_partida_balance(db, cliente_id, partida.id)
    saldo_actual_kg = bal_actual["saldo_fisico_kg"]
    saldo_propuesto_kg = saldo_actual_kg + delta_kg

    if saldo_propuesto_kg < Decimal("0.0"):
        return RedirectResponse(
            f"/comercial/stock?error=El+ajuste+dejaría+el+saldo+físico+en+negativo+(Saldo+actual:+{bal_actual['saldo_fisico_tn']:.2f}+Tn)",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Crear nuevo movimiento inmutable
    mov_ajuste = StockMovement(
        cliente_id=cliente_id,
        stock_partida_id=partida.id,
        tipo="ajuste_inventario",
        cantidad_kg=delta_kg,
        motivo=motivo.strip(),
        observaciones=observaciones.strip(),
        created_by_user_id=get_uuid(user.get("id")),
    )
    db.add(mov_ajuste)

    # Si el nuevo saldo pasa a 0, actualizar estado a agotada
    if saldo_propuesto_kg == Decimal("0.0"):
        partida.estado = "agotada"
    elif partida.estado == "agotada" and saldo_propuesto_kg > Decimal("0.0"):
        partida.estado = "activa"

    await db.commit()

    tipo_lbl = "Incremento" if is_incremento else "Disminución"
    msg = f"Ajuste de inventario registrado ({tipo_lbl} de {cant_dec} {unidad_medida.upper()} en partida {partida.tracking_number}). Saldo actual: {(saldo_propuesto_kg/Decimal('1000.0')):.2f} Tn."
    return RedirectResponse(
        f"/comercial/stock?cultivo={partida.cultivo}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/comercial/stock/crear")
async def create_comercial_stock_legacy(
    request: Request,
    campo_id: str = Form(...),
    cultivo: str = Form(...),
    ubicacion_tipo: str = Form(...),
    identificador: str = Form(...),
    toneladas_almacenadas: float = Form(...),
    fecha_ingreso: str = Form(...),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de Stock Legacy (StockGrano) para compatibilidad hacia atrás.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    if not camp_obj:
        return JSONResponse({"error": "No hay campaña registrada para el cliente"}, status_code=400)

    try:
        f_ingreso = date.fromisoformat(fecha_ingreso)
    except Exception:
        f_ingreso = date.today()

    from app.models import StockGrano, UbicacionStockEnum
    try:
        ub_enum = UbicacionStockEnum(ubicacion_tipo)
    except Exception:
        ub_enum = UbicacionStockEnum.SILO_BOLSA

    nuevo_stock = StockGrano(
        cliente_id=cliente_id,
        campo_id=get_uuid(campo_id),
        campania_id=camp_obj.id,
        cultivo=cultivo.strip().lower(),
        ubicacion_tipo=ub_enum,
        identificador=identificador.strip(),
        toneladas_almacenadas=Decimal(str(toneladas_almacenadas)),
        fecha_ingreso=f_ingreso,
        observaciones=observaciones.strip() if observaciones else None,
    )

    db.add(nuevo_stock)
    await db.commit()

    msg = f"Registro legacy '{identificador.strip()}' guardado ({toneladas_almacenadas} Tn)."
    return RedirectResponse(
        f"/comercial/stock?cultivo={cultivo.strip().lower()}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/comercial/contratos", response_class=HTMLResponse)
async def read_comercial_contratos(
    request: Request,
    cultivo: Optional[str] = "soja",
    mensaje: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Vista operativa de gestión de Contratos de Venta y Compromisos.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/contratos", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    campos = await fetch_campos_dicts(db)
    campos_map = {str(c["id"]): c["nombre"] for c in campos}

    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    camp_uuid = camp_obj.id if camp_obj else None
    camp_nombre = camp_obj.nombre if camp_obj else "Campaña 2025/2026"

    cultivo_sel = (cultivo or "soja").strip().lower()

    stmt_contratos = select(ContratoVentaGrano).where(
        ContratoVentaGrano.cliente_id == cliente_id,
        func.lower(ContratoVentaGrano.cultivo) == cultivo_sel,
    )
    if camp_uuid:
        stmt_contratos = stmt_contratos.where(ContratoVentaGrano.campania_id == camp_uuid)

    res_contratos = await db.execute(stmt_contratos)
    contratos_objs = res_contratos.scalars().all()

    contratos_list = []
    if contratos_objs:
        for c in contratos_objs:
            tp_val = c.tipo_precio.value if hasattr(c.tipo_precio, "value") else str(c.tipo_precio)
            contratos_list.append({
                "id": str(c.id),
                "comprador_acopio": c.comprador_acopio,
                "numero_contrato": c.numero_contrato or "",
                "cultivo": c.cultivo,
                "toneladas": float(c.toneladas or 0.0),
                "tipo_precio": tp_val,
                "precio_usd_tn": float(c.precio_usd_tn) if c.precio_usd_tn is not None else None,
                "fecha_contrato": str(c.fecha_contrato) if c.fecha_contrato else "",
                "fecha_entrega_limite": str(c.fecha_entrega_limite) if c.fecha_entrega_limite else "",
                "observaciones": c.observaciones or "",
            })

    stmt_comp = select(CompromisoGrano).where(
        CompromisoGrano.cliente_id == cliente_id,
        func.lower(CompromisoGrano.cultivo) == cultivo_sel,
    )
    if camp_uuid:
        stmt_comp = stmt_comp.where(CompromisoGrano.campania_id == camp_uuid)

    res_comp = await db.execute(stmt_comp)
    comp_objs = res_comp.scalars().all()

    compromisos_list = []
    if comp_objs:
        for k in comp_objs:
            tk_val = k.tipo_compromiso.value if hasattr(k.tipo_compromiso, "value") else str(k.tipo_compromiso)
            label_tk = "Alquiler / Arrendamiento" if tk_val == "alquiler_arrendamiento" else ("Canje Insumos" if tk_val == "canje_insumos" else "Otro Compromiso")
            compromisos_list.append({
                "id": str(k.id),
                "concepto": k.concepto,
                "beneficiario": k.beneficiario,
                "cultivo": k.cultivo,
                "campo_id": str(k.campo_id) if k.campo_id else None,
                "campo_nombre": campos_map.get(str(k.campo_id), "") if k.campo_id else "",
                "tipo_compromiso": tk_val,
                "tipo_compromiso_label": label_tk,
                "toneladas_comprometidas": float(k.toneladas_comprometidas or 0.0),
                "fecha_vencimiento": str(k.fecha_vencimiento) if k.fecha_vencimiento else "",
                "cumplido": bool(k.cumplido),
            })

    tn_vendidas_fijo = sum(c["toneladas"] for c in contratos_list if c["tipo_precio"] == "fijo")
    tn_vendidas_a_fijar = sum(c["toneladas"] for c in contratos_list if c["tipo_precio"] == "a_fijar")
    tn_comprometidas = sum(k["toneladas_comprometidas"] for k in compromisos_list if not k["cumplido"])

    return templates.TemplateResponse(
        request=request,
        name="comercial_contratos.html",
        context={
            "user": user,
            "campos": campos,
            "campania_activa": camp_nombre,
            "cultivo_seleccionado": cultivo_sel,
            "contratos": contratos_list,
            "compromisos": compromisos_list,
            "tn_vendidas_fijo": round(tn_vendidas_fijo, 2),
            "tn_vendidas_a_fijar": round(tn_vendidas_a_fijar, 2),
            "tn_comprometidas": round(tn_comprometidas, 2),
            "mensaje": mensaje,
            "error": error,
        },
    )


@app.post("/comercial/contratos/crear")
async def create_comercial_contrato(
    request: Request,
    comprador_acopio: str = Form(...),
    numero_contrato: Optional[str] = Form(None),
    tipo_precio: str = Form(...),
    precio_usd_tn: Optional[float] = Form(None),
    toneladas: float = Form(...),
    fecha_contrato: str = Form(...),
    fecha_entrega_limite: Optional[str] = Form(None),
    cultivo: str = Form(...),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de un contrato de venta (Fijo o A Fijar).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/contratos", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    if not camp_obj:
        return RedirectResponse(
            f"/comercial/contratos?cultivo={cultivo.strip().lower()}&error=No+hay+campaña+activa",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        tp_enum = TipoPrecioEnum(tipo_precio)
    except Exception:
        tp_enum = TipoPrecioEnum.FIJO

    if tp_enum == TipoPrecioEnum.FIJO and (precio_usd_tn is None or precio_usd_tn <= 0):
        return RedirectResponse(
            f"/comercial/contratos?cultivo={cultivo.strip().lower()}&error=El+precio+en+USD+es+obligatorio+para+contratos+a+Precio+Fijo",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        f_contrato = date.fromisoformat(fecha_contrato)
    except Exception:
        f_contrato = date.today()

    f_entrega = None
    if fecha_entrega_limite:
        try:
            f_entrega = date.fromisoformat(fecha_entrega_limite)
        except Exception:
            f_entrega = None

    p_usd = Decimal(str(precio_usd_tn)) if (tp_enum == TipoPrecioEnum.FIJO and precio_usd_tn) else None

    nuevo_contrato = ContratoVentaGrano(
        cliente_id=cliente_id,
        campania_id=camp_obj.id,
        cultivo=cultivo.strip().lower(),
        comprador_acopio=comprador_acopio.strip(),
        numero_contrato=numero_contrato.strip() if numero_contrato else None,
        toneladas=Decimal(str(toneladas)),
        tipo_precio=tp_enum,
        precio_usd_tn=p_usd,
        fecha_contrato=f_contrato,
        fecha_entrega_limite=f_entrega,
        observaciones=observaciones.strip() if observaciones else None,
    )

    db.add(nuevo_contrato)
    await db.commit()

    msg = f"Contrato con '{comprador_acopio.strip()}' registrado exitosamente ({toneladas} Tn)."
    return RedirectResponse(
        f"/comercial/contratos?cultivo={cultivo.strip().lower()}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/comercial/compromisos/crear")
async def create_comercial_compromiso(
    request: Request,
    tipo_compromiso: str = Form(...),
    concepto: str = Form(...),
    beneficiario: str = Form(...),
    campo_id: Optional[str] = Form(None),
    toneladas_comprometidas: float = Form(...),
    fecha_vencimiento: Optional[str] = Form(None),
    cultivo: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de un compromiso de grano (Alquiler en qq/ha o Canje de insumos).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/contratos", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    if not camp_obj:
        return RedirectResponse(
            f"/comercial/contratos?cultivo={cultivo.strip().lower()}&error=No+hay+campaña+activa",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        tk_enum = TipoCompromisoEnum(tipo_compromiso)
    except Exception:
        tk_enum = TipoCompromisoEnum.ALQUILER_ARRENDAMIENTO

    f_venc = None
    if fecha_vencimiento:
        try:
            f_venc = date.fromisoformat(fecha_vencimiento)
        except Exception:
            f_venc = None

    campo_uuid = get_uuid(campo_id) if (campo_id and campo_id.strip()) else None

    nuevo_compromiso = CompromisoGrano(
        cliente_id=cliente_id,
        campania_id=camp_obj.id,
        campo_id=campo_uuid,
        cultivo=cultivo.strip().lower(),
        tipo_compromiso=tk_enum,
        concepto=concepto.strip(),
        beneficiario=beneficiario.strip(),
        toneladas_comprometidas=Decimal(str(toneladas_comprometidas)),
        fecha_vencimiento=f_venc,
        cumplido=False,
    )

    db.add(nuevo_compromiso)
    await db.commit()

    msg = f"Compromiso '{concepto.strip()}' registrado exitosamente ({toneladas_comprometidas} Tn)."
    return RedirectResponse(
        f"/comercial/contratos?cultivo={cultivo.strip().lower()}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/comercial/contratos/{contrato_id}/eliminar")
async def delete_comercial_contrato(
    request: Request,
    contrato_id: str,
    cultivo: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Eliminación de un contrato de venta de grano por el usuario.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/contratos", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    contrato_uuid = get_uuid(contrato_id)

    stmt = select(ContratoVentaGrano).where(
        ContratoVentaGrano.id == contrato_uuid,
        ContratoVentaGrano.cliente_id == cliente_id,
    )
    res = await db.execute(stmt)
    contrato = res.scalars().first()

    cult_redir = (cultivo or (contrato.cultivo if contrato else "soja")).strip().lower()

    if not contrato:
        return RedirectResponse(
            f"/comercial/contratos?cultivo={cult_redir}&error=Contrato+no+encontrado",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    num_ref = contrato.numero_contrato or contrato.comprador_acopio
    await db.delete(contrato)
    await db.commit()

    msg = f"Contrato '{num_ref}' eliminado exitosamente."
    return RedirectResponse(
        f"/comercial/contratos?cultivo={cult_redir}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/comercial/compromisos/{compromiso_id}/eliminar")
async def delete_comercial_compromiso(
    request: Request,
    compromiso_id: str,
    cultivo: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Eliminación de un compromiso de grano (Alquiler o Canje) por el usuario.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/contratos", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    compromiso_uuid = get_uuid(compromiso_id)

    stmt = select(CompromisoGrano).where(
        CompromisoGrano.id == compromiso_uuid,
        CompromisoGrano.cliente_id == cliente_id,
    )
    res = await db.execute(stmt)
    compromiso = res.scalars().first()

    cult_redir = (cultivo or (compromiso.cultivo if compromiso else "soja")).strip().lower()

    if not compromiso:
        return RedirectResponse(
            f"/comercial/contratos?cultivo={cult_redir}&error=Compromiso+no+encontrado",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    conc_ref = compromiso.concepto
    await db.delete(compromiso)
    await db.commit()

    msg = f"Compromiso '{conc_ref}' eliminado exitosamente."
    return RedirectResponse(
        f"/comercial/contratos?cultivo={cult_redir}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )



@app.post("/comercial/contratos/arrendamientos/crear")
async def create_comercial_arrendamiento(
    request: Request,
    campo_id: str = Form(...),
    superficie_arrendada_ha: float = Form(...),
    alquiler_qq_ha: float = Form(...),
    beneficiario: str = Form(...),
    concepto: Optional[str] = Form(None),
    cultivo: str = Form("soja"),
    base_valorizacion: str = Form("rosario"),
    precio_referencia_usd_tn: Optional[float] = Form(None),
    fecha_precio_referencia: Optional[str] = Form(None),
    fuente_precio: Optional[str] = Form(None),
    flete_usd_tn: Optional[float] = Form(None),
    comision_usd_tn: Optional[float] = Form(None),
    fecha_vencimiento: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de un compromiso de arrendamiento pactado en qq/ha con valorización Rosario o Acopio.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/contratos", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    if not camp_obj:
        return RedirectResponse(
            f"/comercial/contratos?cultivo={cultivo.strip().lower()}&error=No+hay+campaña+activa",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    campo_uuid = get_uuid(campo_id)
    stmt_c = select(Campo).where(Campo.id == campo_uuid, Campo.cliente_id == cliente_id)
    res_c = await db.execute(stmt_c)
    campo_obj = res_c.scalars().first()
    if not campo_obj:
        return RedirectResponse(
            f"/comercial/contratos?cultivo={cultivo.strip().lower()}&error=Campo+inválido+o+no+encontrado",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    from app.services.lease_calculator import calculate_field_lease_terms
    try:
        calc_res = calculate_field_lease_terms(
            superficie_arrendada_ha=superficie_arrendada_ha,
            alquiler_qq_ha=alquiler_qq_ha,
            base_valorizacion=base_valorizacion,
            precio_referencia_usd_tn=precio_referencia_usd_tn,
            fecha_precio_referencia=date.fromisoformat(fecha_precio_referencia) if (fecha_precio_referencia and fecha_precio_referencia.strip()) else None,
            fuente_precio=fuente_precio,
            flete_usd_tn=flete_usd_tn,
            comision_usd_tn=comision_usd_tn,
        )
    except ValueError as err:
        return RedirectResponse(
            f"/comercial/contratos?cultivo={cultivo.strip().lower()}&error={str(err)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    f_venc = None
    if fecha_vencimiento:
        try:
            f_venc = date.fromisoformat(fecha_vencimiento)
        except Exception:
            f_venc = None

    conc_final = concepto.strip() if (concepto and concepto.strip()) else f"Alquiler {campo_obj.nombre} ({superficie_arrendada_ha} ha × {alquiler_qq_ha} qq/ha)"

    nuevo_compromiso = CompromisoGrano(
        cliente_id=cliente_id,
        campania_id=camp_obj.id,
        campo_id=campo_uuid,
        cultivo=cultivo.strip().lower(),
        tipo_compromiso=TipoCompromisoEnum.ALQUILER_ARRENDAMIENTO,
        concepto=conc_final,
        beneficiario=beneficiario.strip(),
        toneladas_comprometidas=calc_res.toneladas_equivalentes,
        fecha_vencimiento=f_venc,
        cumplido=False,
    )
    db.add(nuevo_compromiso)
    await db.flush()

    terms = ArrendamientoTerms(
        compromiso_id=nuevo_compromiso.id,
        superficie_arrendada_ha=calc_res.superficie_arrendada_ha,
        alquiler_qq_ha=calc_res.alquiler_qq_ha,
        base_valorizacion=calc_res.base_valorizacion,
        precio_referencia_usd_tn=calc_res.precio_referencia_usd_tn,
        fecha_precio_referencia=calc_res.fecha_precio_referencia,
        fuente_precio=calc_res.fuente_precio,
        flete_usd_tn=calc_res.flete_usd_tn,
        comision_usd_tn=calc_res.comision_usd_tn,
        observaciones=observaciones.strip() if observaciones else None,
    )
    db.add(terms)
    await db.commit()

    msg = f"Arrendamiento registrado exitosamente: {calc_res.qq_totales} qq ({calc_res.toneladas_equivalentes} Tn) para {campo_obj.nombre}."
    return RedirectResponse(
        f"/comercial/contratos?cultivo={cultivo.strip().lower()}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/comercial/compromisos/{compromiso_id}/cumplir")
async def marcar_compromiso_cumplido(
    request: Request,
    compromiso_id: str,
    cultivo: str = Form("soja"),
    db: AsyncSession = Depends(get_db),
):
    """
    Actualiza el estado de un compromiso a cumplido=True.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/contratos", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    try:
        k_uuid = get_uuid(compromiso_id)
        stmt = select(CompromisoGrano).where(CompromisoGrano.id == k_uuid)
        res = await db.execute(stmt)
        comp_obj = res.scalars().first()

        if comp_obj:
            comp_obj.cumplido = True
            await db.commit()
            msg = "Compromiso marcado como cumplido exitosamente."
        else:
            msg = "Compromiso actualizado."
    except Exception as e:
        msg = "Estado de compromiso actualizado."

    return RedirectResponse(
        f"/comercial/contratos?cultivo={cultivo.strip().lower()}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/comercial/mercado/refrescar")
async def refrescar_precios_mercado_action(
    request: Request,
    cultivo: Optional[str] = "soja",
    fuente: Optional[str] = "pizarra",
    db: AsyncSession = Depends(get_db),
):
    """
    Refresca las cotizaciones de mercado desde las APIs externas y redirige a /comercial en la misma pestaña.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    from app.services.mercado import actualizar_precios_mercado
    cult_sel = (cultivo or "soja").strip().lower()
    registros = await actualizar_precios_mercado(db, usar_fetcher_real=True, fuente_preferida=fuente or "pizarra")

    msg = f"Cotizaciones de mercado actualizadas exitosamente ({len(registros)} registros)."
    return RedirectResponse(
        f"/comercial?cultivo={cult_sel}&mensaje={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/api/comercial/mercado/refrescar")
async def refrescar_precios_mercado_api(
    request: Request,
    fuente: Optional[str] = "pizarra",
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint de actualización/fetch manual de precios de mercado desde fuentes externas.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=status.HTTP_401_UNAUTHORIZED)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return JSONResponse({"error": "Acceso denegado"}, status_code=status.HTTP_403_FORBIDDEN)

    from app.services.mercado import actualizar_precios_mercado
    registros = await actualizar_precios_mercado(db, usar_fetcher_real=True, fuente_preferida=fuente or "pizarra")

    return JSONResponse({
        "success": True,
        "mensaje": f"Se actualizaron {len(registros)} cotizaciones de mercado en la base de datos.",
        "precios": registros,
    })


# ----------------------------------------------------------------------
# Módulo Comercial V1 - Fletes y Destinos Comerciales (Freight)
# ----------------------------------------------------------------------

CULTIVO_LABELS = {
    "maiz": "Maíz",
    "soja": "Soja",
    "trigo": "Trigo",
    "sorgo": "Sorgo",
    "no_especificado": "No especificado",
}

CONDICION_PRECIO_LABELS = {
    "disponible_spot": "Disponible / Spot",
    "a_fijar": "A Fijar",
    "contrato": "Contrato",
    "futuro": "Futuro",
    "a_confirmar": "A Confirmar",
}


def parse_decimal_ar(val: Optional[str]) -> Optional[Decimal]:
    """
    Parseador seguro de montos con formato numérico argentino (ej. '334,80' o '334.80').
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
        return d
    except Exception:
        return None


@app.get("/comercial/fletes", response_class=HTMLResponse)
async def read_comercial_fletes(
    request: Request,
    cultivo: Optional[str] = "soja",
    mensaje: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Vista principal de Cotizaciones de Flete y Alternativas de Entrega Commercial.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/fletes", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    campos = await fetch_campos_dicts(db)
    campos_map = {str(c["id"]): c["nombre"] for c in campos}

    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    camp_nombre = camp_obj.nombre if camp_obj else "Campaña 2025/2026"

    cultivo_sel = (cultivo or "soja").strip().lower()

    from app.models import FreightQuote
    from app.services.decision_engine.models import (
        DeliveryDestinationContext,
        RoadStatus,
        AvailabilityStatus,
        FreightQuoteSource,
    )
    from app.services.decision_engine.calculators.freight import calculate_delivery_economics

    stmt = (
        select(FreightQuote)
        .where(FreightQuote.cliente_id == cliente_id)
        .order_by(FreightQuote.fecha_creacion.desc())
    )
    res = await db.execute(stmt)
    quotes_objs = res.scalars().all()

    now = datetime.now()

    quotes_list = []
    for q in quotes_objs:
        dest_ctx = DeliveryDestinationContext(
            destination_id=q.id,
            destination_name=q.destination_name,
            destination_type=q.destination_type,
            cultivo=q.cultivo,
            condicion_precio=q.condicion_precio,
            distancia_estimada_km=q.distancia_estimada_km,
            detalle_cupo_turno=q.detalle_cupo_turno,
            price_usd_tn=q.price_usd_tn,
            freight_usd_tn=q.freight_usd_tn,
            conditioning_cost_usd_tn=q.conditioning_cost_usd_tn,
            other_costs_usd_tn=q.other_costs_usd_tn,
            max_receiving_moisture_pct=q.max_receiving_moisture_pct,
            receiving_confirmed=AvailabilityStatus(q.receiving_confirmed) if q.receiving_confirmed in AvailabilityStatus._value2member_map_ else AvailabilityStatus.UNKNOWN,
            road_status=RoadStatus(q.road_status) if q.road_status in RoadStatus._value2member_map_ else RoadStatus.UNKNOWN,
            quote_observed_at=q.quote_observed_at,
            quote_valid_until=q.quote_valid_until,
            quote_source=FreightQuoteSource(q.quote_source) if q.quote_source in FreightQuoteSource._value2member_map_ else FreightQuoteSource.MANUAL,
            notes=q.notes,
        )

        econ = calculate_delivery_economics(dest_ctx, current_time=now)

        quotes_list.append({
            "id": str(q.id),
            "destination_name": q.destination_name,
            "destination_type": q.destination_type or "",
            "cultivo": q.cultivo or "",
            "cultivo_label": CULTIVO_LABELS.get(q.cultivo or "", q.cultivo or ""),
            "condicion_precio": q.condicion_precio or "",
            "condicion_precio_label": CONDICION_PRECIO_LABELS.get(q.condicion_precio or "", q.condicion_precio or ""),
            "distancia_estimada_km": float(q.distancia_estimada_km) if q.distancia_estimada_km is not None else None,
            "distancia_estimada_formatted": f"{q.distancia_estimada_km:.1f}".replace(".", ",") if q.distancia_estimada_km is not None else "",
            "distancia_estimada_raw": str(q.distancia_estimada_km) if q.distancia_estimada_km is not None else "",
            "detalle_cupo_turno": q.detalle_cupo_turno or "",
            "campo_id": str(q.campo_id) if q.campo_id else "",
            "campo_nombre": campos_map.get(str(q.campo_id), "") if q.campo_id else "",
            "price_usd_tn": float(q.price_usd_tn) if q.price_usd_tn is not None else None,
            "price_usd_formatted": f"{q.price_usd_tn:.2f}".replace(".", ",") if q.price_usd_tn is not None else "",
            "price_usd_raw": str(q.price_usd_tn) if q.price_usd_tn is not None else "",
            "freight_usd_tn": float(q.freight_usd_tn) if q.freight_usd_tn is not None else None,
            "freight_usd_formatted": f"{q.freight_usd_tn:.2f}".replace(".", ",") if q.freight_usd_tn is not None else "",
            "freight_usd_raw": str(q.freight_usd_tn) if q.freight_usd_tn is not None else "",
            "conditioning_cost_formatted": f"{q.conditioning_cost_usd_tn:.2f}".replace(".", ",") if q.conditioning_cost_usd_tn is not None else "0,00",
            "conditioning_cost_raw": str(q.conditioning_cost_usd_tn) if q.conditioning_cost_usd_tn is not None else "",
            "other_costs_formatted": f"{q.other_costs_usd_tn:.2f}".replace(".", ",") if q.other_costs_usd_tn is not None else "0,00",
            "other_costs_raw": str(q.other_costs_usd_tn) if q.other_costs_usd_tn is not None else "",
            "max_receiving_moisture_raw": str(q.max_receiving_moisture_pct) if q.max_receiving_moisture_pct is not None else "",
            "humedad_max_recepcion_formatted": f"{q.max_receiving_moisture_pct:.1f}".replace(".", ",") if q.max_receiving_moisture_pct is not None else "",
            "net_origin_price_formatted": f"{econ.net_origin_price_usd_tn:.2f}".replace(".", ",") if econ.net_origin_price_usd_tn is not None else "",
            "is_net_fully_calculated": econ.is_net_price_fully_calculated,
            "is_stale": econ.is_quote_stale,
            "receiving_confirmed": q.receiving_confirmed,
            "road_status": q.road_status,
            "quote_source": q.quote_source,
            "quote_confidence": q.quote_confidence or "",
            "quote_observed_at_str": q.quote_observed_at.strftime("%Y-%m-%d") if q.quote_observed_at else "",
            "quote_valid_until_str": q.quote_valid_until.strftime("%Y-%m-%d") if q.quote_valid_until else "",
            "notes": q.notes or "",
        })

    return templates.TemplateResponse(
        request=request,
        name="comercial_fletes.html",
        context={
            "user": user,
            "campania_activa": camp_nombre,
            "cultivo_seleccionado": cultivo_sel,
            "campos": campos,
            "quotes": quotes_list,
            "mensaje_exito": mensaje,
            "mensaje_error": error,
        },
    )


@app.post("/comercial/fletes/crear")
async def create_comercial_flete(
    request: Request,
    destination_name: str = Form(...),
    destination_type: Optional[str] = Form(None),
    cultivo: Optional[str] = Form(None),
    condicion_precio: Optional[str] = Form(None),
    price_usd_tn: Optional[str] = Form(None),
    freight_usd_tn: Optional[str] = Form(None),
    conditioning_cost_usd_tn: Optional[str] = Form(None),
    other_costs_usd_tn: Optional[str] = Form(None),
    distancia_estimada_km: Optional[str] = Form(None),
    humedad_max_recepcion_pct: Optional[str] = Form(None),
    max_receiving_moisture_pct: Optional[str] = Form(None),
    receiving_confirmed: str = Form("unknown"),
    detalle_cupo_turno: Optional[str] = Form(None),
    road_status: str = Form("good"),
    quote_observed_at: str = Form(...),
    quote_valid_until: Optional[str] = Form(None),
    quote_source: str = Form("manual"),
    quote_confidence: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    campo_id: Optional[str] = Form(None),
    lote_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Alta de una cotización manual de flete/destino comercial.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/fletes", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    dest_name = destination_name.strip() if destination_name else ""
    if not dest_name:
        return RedirectResponse("/comercial/fletes?error=El+nombre+del+destino+es+obligatorio", status_code=status.HTTP_303_SEE_OTHER)

    # Validar Enums permitidos
    cult_val = cultivo.strip().lower() if (cultivo and cultivo.strip()) else None
    if cult_val and cult_val not in ["maiz", "soja", "trigo", "sorgo", "no_especificado"]:
        return RedirectResponse("/comercial/fletes?error=El+cultivo+especificable+no+es+válido", status_code=status.HTTP_303_SEE_OTHER)

    cond_val = condicion_precio.strip().lower() if (condicion_precio and condicion_precio.strip()) else None
    if cond_val and cond_val not in ["disponible_spot", "a_fijar", "contrato", "futuro", "a_confirmar"]:
        return RedirectResponse("/comercial/fletes?error=La+condición+de+precio+no+es+válida", status_code=status.HTTP_303_SEE_OTHER)

    p_usd = parse_decimal_ar(price_usd_tn)
    f_usd = parse_decimal_ar(freight_usd_tn)
    c_usd = parse_decimal_ar(conditioning_cost_usd_tn)
    o_usd = parse_decimal_ar(other_costs_usd_tn)
    dist_km = parse_decimal_ar(distancia_estimada_km)

    # Soporte para ambas denominaciones de humedad
    moist_input = humedad_max_recepcion_pct if humedad_max_recepcion_pct is not None else max_receiving_moisture_pct
    moist_pct = parse_decimal_ar(moist_input)

    # Validar importes no negativos
    for val, name in [(p_usd, "precio"), (f_usd, "flete"), (c_usd, "acondicionamiento"), (o_usd, "otros costos")]:
        if val is not None and val < Decimal("0.0"):
            return RedirectResponse(f"/comercial/fletes?error=El+monto+de+{name}+no+puede+ser+negativo", status_code=status.HTTP_303_SEE_OTHER)

    if dist_km is not None and (dist_km < Decimal("0.0") or dist_km > Decimal("5000.0")):
        return RedirectResponse("/comercial/fletes?error=La+distancia+estimada+debe+ser+un+número+positivo", status_code=status.HTTP_303_SEE_OTHER)

    if moist_pct is not None and (moist_pct < Decimal("5.0") or moist_pct > Decimal("35.0")):
        return RedirectResponse("/comercial/fletes?error=La+humedad+máxima+aceptada+debe+estar+entre+5%+y+35%", status_code=status.HTTP_303_SEE_OTHER)

    try:
        obs_dt = datetime.fromisoformat(quote_observed_at)
    except Exception:
        obs_dt = datetime.now()

    valid_dt = None
    if quote_valid_until and quote_valid_until.strip():
        try:
            valid_dt = datetime.fromisoformat(quote_valid_until)
            if valid_dt < obs_dt:
                return RedirectResponse("/comercial/fletes?error=La+fecha+de+validez+no+puede+ser+anterior+a+la+fecha+de+observación", status_code=status.HTTP_303_SEE_OTHER)
        except Exception:
            valid_dt = None

    cupo_detail = detalle_cupo_turno.strip()[:300] if (detalle_cupo_turno and detalle_cupo_turno.strip()) else None

    from app.models import FreightQuote

    nuevo_flete = FreightQuote(
        cliente_id=cliente_id,
        campo_id=get_uuid(campo_id) if campo_id else None,
        lote_id=get_uuid(lote_id) if lote_id else None,
        destination_name=dest_name,
        destination_type=destination_type.strip() if destination_type else None,
        cultivo=cult_val,
        condicion_precio=cond_val,
        distancia_estimada_km=dist_km,
        detalle_cupo_turno=cupo_detail,
        price_usd_tn=p_usd,
        freight_usd_tn=f_usd,
        conditioning_cost_usd_tn=c_usd,
        other_costs_usd_tn=o_usd,
        max_receiving_moisture_pct=moist_pct,
        receiving_confirmed=receiving_confirmed.strip(),
        road_status=road_status.strip(),
        quote_observed_at=obs_dt,
        quote_valid_until=valid_dt,
        quote_source=quote_source.strip(),
        quote_confidence=quote_confidence.strip() if quote_confidence else None,
        notes=notes.strip() if notes else None,
        created_by_user_id=get_uuid(user.get("id")),
    )

    db.add(nuevo_flete)
    await db.commit()

    msg = f"Cotización de '{dest_name}' registrada exitosamente."
    return RedirectResponse(f"/comercial/fletes?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/fletes/{quote_id}/editar")
async def edit_comercial_flete(
    request: Request,
    quote_id: str,
    destination_name: str = Form(...),
    destination_type: Optional[str] = Form(None),
    cultivo: Optional[str] = Form(None),
    condicion_precio: Optional[str] = Form(None),
    price_usd_tn: Optional[str] = Form(None),
    freight_usd_tn: Optional[str] = Form(None),
    conditioning_cost_usd_tn: Optional[str] = Form(None),
    other_costs_usd_tn: Optional[str] = Form(None),
    distancia_estimada_km: Optional[str] = Form(None),
    humedad_max_recepcion_pct: Optional[str] = Form(None),
    max_receiving_moisture_pct: Optional[str] = Form(None),
    receiving_confirmed: str = Form("unknown"),
    detalle_cupo_turno: Optional[str] = Form(None),
    road_status: str = Form("good"),
    quote_observed_at: str = Form(...),
    quote_valid_until: Optional[str] = Form(None),
    quote_source: str = Form("manual"),
    quote_confidence: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Edición protegida por multitenant de una cotización existente.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/fletes", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    q_uuid = get_uuid(quote_id)

    from app.models import FreightQuote
    stmt = select(FreightQuote).where(FreightQuote.id == q_uuid, FreightQuote.cliente_id == cliente_id)
    res = await db.execute(stmt)
    quote = res.scalars().first()

    if not quote:
        return RedirectResponse("/comercial/fletes?error=Cotización+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    dest_name = destination_name.strip() if destination_name else ""
    if not dest_name:
        return RedirectResponse("/comercial/fletes?error=El+nombre+del+destino+es+obligatorio", status_code=status.HTTP_303_SEE_OTHER)

    cult_val = cultivo.strip().lower() if (cultivo and cultivo.strip()) else None
    if cult_val and cult_val not in ["maiz", "soja", "trigo", "sorgo", "no_especificado"]:
        return RedirectResponse("/comercial/fletes?error=El+cultivo+especificable+no+es+válido", status_code=status.HTTP_303_SEE_OTHER)

    cond_val = condicion_precio.strip().lower() if (condicion_precio and condicion_precio.strip()) else None
    if cond_val and cond_val not in ["disponible_spot", "a_fijar", "contrato", "futuro", "a_confirmar"]:
        return RedirectResponse("/comercial/fletes?error=La+condición+de+precio+no+es+válida", status_code=status.HTTP_303_SEE_OTHER)

    p_usd = parse_decimal_ar(price_usd_tn)
    f_usd = parse_decimal_ar(freight_usd_tn)
    c_usd = parse_decimal_ar(conditioning_cost_usd_tn)
    o_usd = parse_decimal_ar(other_costs_usd_tn)
    dist_km = parse_decimal_ar(distancia_estimada_km)

    moist_input = humedad_max_recepcion_pct if humedad_max_recepcion_pct is not None else max_receiving_moisture_pct
    moist_pct = parse_decimal_ar(moist_input)

    for val, name in [(p_usd, "precio"), (f_usd, "flete"), (c_usd, "acondicionamiento"), (o_usd, "otros costos")]:
        if val is not None and val < Decimal("0.0"):
            return RedirectResponse(f"/comercial/fletes?error=El+monto+de+{name}+no+puede+ser+negativo", status_code=status.HTTP_303_SEE_OTHER)

    if dist_km is not None and (dist_km < Decimal("0.0") or dist_km > Decimal("5000.0")):
        return RedirectResponse("/comercial/fletes?error=La+distancia+estimada+debe+ser+un+número+positivo", status_code=status.HTTP_303_SEE_OTHER)

    if moist_pct is not None and (moist_pct < Decimal("5.0") or moist_pct > Decimal("35.0")):
        return RedirectResponse("/comercial/fletes?error=La+humedad+máxima+aceptada+debe+estar+entre+5%+y+35%", status_code=status.HTTP_303_SEE_OTHER)

    obs_dt = quote.quote_observed_at
    if quote_observed_at:
        try:
            obs_dt = datetime.fromisoformat(quote_observed_at)
        except Exception:
            pass

    valid_dt = None
    if quote_valid_until and quote_valid_until.strip():
        try:
            valid_dt = datetime.fromisoformat(quote_valid_until)
            if valid_dt < obs_dt:
                return RedirectResponse("/comercial/fletes?error=La+fecha+de+validez+no+puede+ser+anterior+a+la+fecha+de+observación", status_code=status.HTTP_303_SEE_OTHER)
        except Exception:
            valid_dt = None

    quote.destination_name = dest_name
    quote.destination_type = destination_type.strip() if destination_type else None
    quote.cultivo = cult_val
    quote.condicion_precio = cond_val
    quote.distancia_estimada_km = dist_km
    quote.detalle_cupo_turno = detalle_cupo_turno.strip()[:300] if (detalle_cupo_turno and detalle_cupo_turno.strip()) else None
    quote.price_usd_tn = p_usd
    quote.freight_usd_tn = f_usd
    quote.conditioning_cost_usd_tn = c_usd
    quote.other_costs_usd_tn = o_usd
    quote.max_receiving_moisture_pct = moist_pct
    quote.receiving_confirmed = receiving_confirmed.strip()
    quote.road_status = road_status.strip()
    quote.quote_observed_at = obs_dt
    quote.quote_valid_until = valid_dt
    quote.quote_source = quote_source.strip()
    quote.quote_confidence = quote_confidence.strip() if quote_confidence else None
    quote.notes = notes.strip() if notes else None

    await db.commit()

    msg = f"Cotización de '{quote.destination_name}' actualizada exitosamente."
    return RedirectResponse(f"/comercial/fletes?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/fletes/{quote_id}/eliminar")
async def delete_comercial_flete(
    request: Request,
    quote_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Eliminación protegida por multitenant de una cotización existente.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/fletes", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    q_uuid = get_uuid(quote_id)

    from app.models import FreightQuote
    stmt = select(FreightQuote).where(FreightQuote.id == q_uuid, FreightQuote.cliente_id == cliente_id)
    res = await db.execute(stmt)
    quote = res.scalars().first()

    if not quote:
        return RedirectResponse("/comercial/fletes?error=Cotización+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    name = quote.destination_name
    await db.delete(quote)
    await db.commit()

    msg = f"Cotización de '{name}' eliminada exitosamente."
    return RedirectResponse(f"/comercial/fletes?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/fletes/comparar")
async def compare_comercial_fletes(
    request: Request,
    selected_quotes: List[str] = Form(...),
    cultivo: str = Form("soja"),
    humedad_grano_pct: float = Form(14.5),
    db: AsyncSession = Depends(get_db),
):
    """
    Ejecuta la comparación determinística de alternativas con el motor de decisiones V2.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/fletes", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    if not selected_quotes or len(selected_quotes) < 2:
        return RedirectResponse("/comercial/fletes?error=Seleccioná+al+menos+2+cotizaciones+para+comparar", status_code=status.HTTP_303_SEE_OTHER)

    uuids = [get_uuid(q) for q in selected_quotes if q]

    from app.models import FreightQuote
    from app.services.decision_engine.models import (
        DeliveryDestinationContext,
        DecisionContext,
        HarvestData,
        RoadStatus,
        AvailabilityStatus,
        FreightQuoteSource,
    )
    from app.services.decision_motor import evaluar_motor_decisiones_detallado
    from app.services.decision_engine.calculators.delivery_economics import rank_delivery_options

    stmt = select(FreightQuote).where(
        FreightQuote.id.in_(uuids),
        FreightQuote.cliente_id == cliente_id,
    )
    res = await db.execute(stmt)
    quotes_objs = res.scalars().all()

    if len(quotes_objs) < 2:
        return RedirectResponse("/comercial/fletes?error=Cotizaciones+insuficientes+o+no+autorizadas", status_code=status.HTTP_303_SEE_OTHER)

    dest_options: List[DeliveryDestinationContext] = []
    condiciones_set = set()
    for q in quotes_objs:
        if q.condicion_precio and q.condicion_precio.strip():
            condiciones_set.add(q.condicion_precio.strip())

        dest_options.append(
            DeliveryDestinationContext(
                destination_id=q.id,
                destination_name=q.destination_name,
                destination_type=q.destination_type,
                cultivo=q.cultivo,
                condicion_precio=q.condicion_precio,
                distancia_estimada_km=q.distancia_estimada_km,
                detalle_cupo_turno=q.detalle_cupo_turno,
                price_usd_tn=q.price_usd_tn,
                freight_usd_tn=q.freight_usd_tn,
                conditioning_cost_usd_tn=q.conditioning_cost_usd_tn,
                other_costs_usd_tn=q.other_costs_usd_tn,
                max_receiving_moisture_pct=q.max_receiving_moisture_pct,
                receiving_confirmed=AvailabilityStatus(q.receiving_confirmed) if q.receiving_confirmed in AvailabilityStatus._value2member_map_ else AvailabilityStatus.UNKNOWN,
                road_status=RoadStatus(q.road_status) if q.road_status in RoadStatus._value2member_map_ else RoadStatus.UNKNOWN,
                quote_observed_at=q.quote_observed_at,
                quote_valid_until=q.quote_valid_until,
                quote_source=FreightQuoteSource(q.quote_source) if q.quote_source in FreightQuoteSource._value2member_map_ else FreightQuoteSource.MANUAL,
                notes=q.notes,
            )
        )

    warning_diferente_condicion = len(condiciones_set) > 1

    context = DecisionContext(
        cultivo=cultivo.strip().lower(), # type: ignore
        harvest=HarvestData(humedad_grano_pct=humedad_grano_pct),
        delivery_options=dest_options,
    )

    decision_result = evaluar_motor_decisiones_detallado(context)

    ranked_res = rank_delivery_options(dest_options, grain_moisture_pct=humedad_grano_pct)

    winning_opt = ranked_res.best_option if ranked_res.is_best_option_material else None
    winning_adv = float(ranked_res.net_difference_usd_tn) if ranked_res.net_difference_usd_tn is not None else None

    # Renderizar la vista con los resultados de comparación
    campos = await fetch_campos_dicts(db)
    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    camp_nombre = camp_obj.nombre if camp_obj else "Campaña 2025/2026"

    stmt_all = select(FreightQuote).where(FreightQuote.cliente_id == cliente_id).order_by(FreightQuote.fecha_creacion.desc())
    res_all = await db.execute(stmt_all)
    all_quotes_objs = res_all.scalars().all()
    campos_map = {str(c["id"]): c["nombre"] for c in campos}

    from app.services.decision_engine.calculators.freight import calculate_delivery_economics
    now = datetime.now()
    quotes_list = []
    for q in all_quotes_objs:
        dest_ctx = DeliveryDestinationContext(
            destination_id=q.id,
            destination_name=q.destination_name,
            destination_type=q.destination_type,
            cultivo=q.cultivo,
            condicion_precio=q.condicion_precio,
            distancia_estimada_km=q.distancia_estimada_km,
            detalle_cupo_turno=q.detalle_cupo_turno,
            price_usd_tn=q.price_usd_tn,
            freight_usd_tn=q.freight_usd_tn,
            conditioning_cost_usd_tn=q.conditioning_cost_usd_tn,
            other_costs_usd_tn=q.other_costs_usd_tn,
            max_receiving_moisture_pct=q.max_receiving_moisture_pct,
            receiving_confirmed=AvailabilityStatus(q.receiving_confirmed) if q.receiving_confirmed in AvailabilityStatus._value2member_map_ else AvailabilityStatus.UNKNOWN,
            road_status=RoadStatus(q.road_status) if q.road_status in RoadStatus._value2member_map_ else RoadStatus.UNKNOWN,
            quote_observed_at=q.quote_observed_at,
            quote_valid_until=q.quote_valid_until,
            quote_source=FreightQuoteSource(q.quote_source) if q.quote_source in FreightQuoteSource._value2member_map_ else FreightQuoteSource.MANUAL,
            notes=q.notes,
        )
        econ = calculate_delivery_economics(dest_ctx, current_time=now)
        quotes_list.append({
            "id": str(q.id),
            "destination_name": q.destination_name,
            "destination_type": q.destination_type or "",
            "cultivo": q.cultivo or "",
            "cultivo_label": CULTIVO_LABELS.get(q.cultivo or "", q.cultivo or ""),
            "condicion_precio": q.condicion_precio or "",
            "condicion_precio_label": CONDICION_PRECIO_LABELS.get(q.condicion_precio or "", q.condicion_precio or ""),
            "distancia_estimada_km": float(q.distancia_estimada_km) if q.distancia_estimada_km is not None else None,
            "distancia_estimada_formatted": f"{q.distancia_estimada_km:.1f}".replace(".", ",") if q.distancia_estimada_km is not None else "",
            "distancia_estimada_raw": str(q.distancia_estimada_km) if q.distancia_estimada_km is not None else "",
            "detalle_cupo_turno": q.detalle_cupo_turno or "",
            "campo_id": str(q.campo_id) if q.campo_id else "",
            "campo_nombre": campos_map.get(str(q.campo_id), "") if q.campo_id else "",
            "price_usd_tn": float(q.price_usd_tn) if q.price_usd_tn is not None else None,
            "price_usd_formatted": f"{q.price_usd_tn:.2f}".replace(".", ",") if q.price_usd_tn is not None else "",
            "price_usd_raw": str(q.price_usd_tn) if q.price_usd_tn is not None else "",
            "freight_usd_tn": float(q.freight_usd_tn) if q.freight_usd_tn is not None else None,
            "freight_usd_formatted": f"{q.freight_usd_tn:.2f}".replace(".", ",") if q.freight_usd_tn is not None else "",
            "freight_usd_raw": str(q.freight_usd_tn) if q.freight_usd_tn is not None else "",
            "conditioning_cost_formatted": f"{q.conditioning_cost_usd_tn:.2f}".replace(".", ",") if q.conditioning_cost_usd_tn is not None else "0,00",
            "conditioning_cost_raw": str(q.conditioning_cost_usd_tn) if q.conditioning_cost_usd_tn is not None else "",
            "other_costs_formatted": f"{q.other_costs_usd_tn:.2f}".replace(".", ",") if q.other_costs_usd_tn is not None else "0,00",
            "other_costs_raw": str(q.other_costs_usd_tn) if q.other_costs_usd_tn is not None else "",
            "max_receiving_moisture_raw": str(q.max_receiving_moisture_pct) if q.max_receiving_moisture_pct is not None else "",
            "humedad_max_recepcion_formatted": f"{q.max_receiving_moisture_pct:.1f}".replace(".", ",") if q.max_receiving_moisture_pct is not None else "",
            "net_origin_price_formatted": f"{econ.net_origin_price_usd_tn:.2f}".replace(".", ",") if econ.net_origin_price_usd_tn is not None else "",
            "is_net_fully_calculated": econ.is_net_price_fully_calculated,
            "is_stale": econ.is_quote_stale,
            "receiving_confirmed": q.receiving_confirmed,
            "road_status": q.road_status,
            "quote_source": q.quote_source,
            "quote_confidence": q.quote_confidence or "",
            "quote_observed_at_str": q.quote_observed_at.strftime("%Y-%m-%d") if q.quote_observed_at else "",
            "quote_valid_until_str": q.quote_valid_until.strftime("%Y-%m-%d") if q.quote_valid_until else "",
            "notes": q.notes or "",
        })

    return templates.TemplateResponse(
        request=request,
        name="comercial_fletes.html",
        context={
            "user": user,
            "campania_activa": camp_nombre,
            "cultivo_seleccionado": cultivo,
            "humedad_grano_pct": humedad_grano_pct,
            "campos": campos,
            "quotes": quotes_list,
            "comparison_result": decision_result,
            "winning_option": winning_opt,
            "winning_advantage_usd": winning_adv,
            "comparison_insights": decision_result.insights,
            "warning_diferente_condicion": warning_diferente_condicion,
        },
    )


# ==============================================================================
# RUTAS DEL MÓDULO COMERCIAL - ENTREGAS Y CARTAS DE PORTE
# ==============================================================================

VALID_DELIVERY_TRANSITIONS = {
    "planificada": {"en_transito", "cancelada", "observada", "planificada"},
    "en_transito": {"recibida", "observada", "cancelada", "en_transito"},
    "recibida": {"liquidada", "observada", "recibida"},
    "liquidada": {"observada", "liquidada"},
    "observada": {"planificada", "en_transito", "recibida", "liquidada", "cancelada", "observada"},
    "cancelada": {"cancelada", "planificada"},
}


def recalculate_delivery_totals(delivery) -> None:
    """
    Recalcula los totales de pesaje derivados a partir de sus cartas de porte asociadas.
    """
    active_waybills = [w for w in delivery.waybills if w.estado != "anulada"]

    net_origen = Decimal("0.0")
    has_origen = False
    for w in active_waybills:
        if w.peso_neto_origen_kg is not None:
            net_origen += Decimal(str(w.peso_neto_origen_kg))
            has_origen = True

    rec_destino = Decimal("0.0")
    has_destino = False
    for w in active_waybills:
        if w.peso_recibido_destino_kg is not None:
            rec_destino += Decimal(str(w.peso_recibido_destino_kg))
            has_destino = True

    delivery.kg_neto_origen_total = net_origen if has_origen else None
    delivery.kg_recibido_total = rec_destino if has_destino else None

    if has_origen and has_destino and net_origen > Decimal("0.0"):
        diff_kg = rec_destino - net_origen
        diff_pct = (diff_kg / net_origen) * Decimal("100.0")
        delivery.diferencia_total_kg = diff_kg
        delivery.diferencia_total_pct = diff_pct.quantize(Decimal("0.01"))
    elif has_origen and has_destino:
        delivery.diferencia_total_kg = rec_destino - net_origen
        delivery.diferencia_total_pct = None
    else:
        delivery.diferencia_total_kg = None
        delivery.diferencia_total_pct = None

    if not active_waybills:
        delivery.documentacion_status = "sin_documentacion"
    else:
        has_obs = any(w.estado == "observada" for w in active_waybills)
        if has_obs:
            delivery.documentacion_status = "observada"
        else:
            num_with_cpe = sum(1 for w in active_waybills if w.numero_carta_porte and w.numero_carta_porte.strip())
            num_total = len(active_waybills)
            if num_with_cpe == 0:
                delivery.documentacion_status = "carta_pendiente"
            elif num_with_cpe < num_total:
                delivery.documentacion_status = "parcial"
            else:
                delivery.documentacion_status = "completa"


@app.get("/comercial/entregas", response_class=HTMLResponse)
async def read_comercial_entregas(
    request: Request,
    cultivo: Optional[str] = "soja",
    mensaje: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Vista principal de Entregas y Cartas de Porte en el módulo Comercial.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    camp_nombre = camp_obj.nombre if camp_obj else "Campaña 2025/2026"

    from app.models import GrainDelivery, GrainWaybill, CompromisoGrano, FreightQuote, StockDeliveryAllocation, StockWeightReconciliation, StockPartida
    from sqlalchemy.orm import selectinload

    stmt_del = (
        select(GrainDelivery)
        .options(
            selectinload(GrainDelivery.waybills),
            selectinload(GrainDelivery.compromiso),
            selectinload(GrainDelivery.freight_quote),
            selectinload(GrainDelivery.allocations).selectinload(StockDeliveryAllocation.stock_partida),
            selectinload(GrainDelivery.reconciliations),
        )
        .where(GrainDelivery.cliente_id == cliente_id)
        .order_by(GrainDelivery.fecha_creacion.desc())
    )
    res_del = await db.execute(stmt_del)
    deliveries_objs = res_del.scalars().all()

    from app.services.stock_service import get_compromisos_saldos_map, format_compromiso_dict
    stmt_comp = select(CompromisoGrano).where(CompromisoGrano.cliente_id == cliente_id, CompromisoGrano.cumplido == False)
    res_comp = await db.execute(stmt_comp)
    compromisos_objs = res_comp.scalars().all()
    saldos_map = await get_compromisos_saldos_map(db, cliente_id)
    compromisos_list = [
        format_compromiso_dict(c, saldo_tn=saldos_map.get(c.id, c.toneladas_comprometidas))
        for c in compromisos_objs
    ]

    stmt_quotes = select(FreightQuote).where(FreightQuote.cliente_id == cliente_id)
    res_quotes = await db.execute(stmt_quotes)
    quotes_objs = res_quotes.scalars().all()

    deliveries_list = []
    deliveries_dict_json = []

    from app.services.decision_engine.models import (
        DecisionContext,
        GrainDeliveryContext,
        GrainWaybillContext,
    )
    from app.services.decision_motor import evaluar_motor_decisiones_detallado

    engine_deliveries: List[GrainDeliveryContext] = []

    for d in deliveries_objs:
        recalculate_delivery_totals(d)

        waybills_list = []
        engine_waybills: List[GrainWaybillContext] = []

        for w in d.waybills:
            w_dict = {
                "id": str(w.id),
                "numero_carta_porte": w.numero_carta_porte or "",
                "tipo_camion": w.tipo_camion or "normal",
                "capacidad_referencia_kg": float(w.capacidad_referencia_kg) if w.capacidad_referencia_kg is not None else None,
                "tara_kg": float(w.tara_kg) if w.tara_kg is not None else None,
                "peso_bruto_origen_kg": float(w.peso_bruto_origen_kg) if w.peso_bruto_origen_kg is not None else None,
                "peso_neto_origen_kg": float(w.peso_neto_origen_kg) if w.peso_neto_origen_kg is not None else None,
                "peso_recibido_destino_kg": float(w.peso_recibido_destino_kg) if w.peso_recibido_destino_kg is not None else None,
                "diferencia_kg": float(w.diferencia_kg) if w.diferencia_kg is not None else None,
                "diferencia_pct": float(w.diferencia_pct) if w.diferencia_pct is not None else None,
                "referencia_ticket_origen": w.referencia_ticket_origen or "",
                "referencia_ticket_destino": w.referencia_ticket_destino or "",
                "estado": w.estado,
                "observaciones": w.observaciones or "",
            }
            waybills_list.append(w_dict)
            engine_waybills.append(
                GrainWaybillContext(
                    id=w.id,
                    numero_carta_porte=w.numero_carta_porte,
                    tipo_camion=w.tipo_camion,
                    capacidad_referencia_kg=w.capacidad_referencia_kg,
                    tara_kg=w.tara_kg,
                    peso_bruto_origen_kg=w.peso_bruto_origen_kg,
                    peso_neto_origen_kg=w.peso_neto_origen_kg,
                    peso_recibido_destino_kg=w.peso_recibido_destino_kg,
                    diferencia_kg=w.diferencia_kg,
                    diferencia_pct=w.diferencia_pct,
                    estado=w.estado,
                    observaciones=w.observaciones,
                )
            )

        allocations_activas = [a for a in d.allocations if a.estado == "activa"]
        allocations_despachadas = [a for a in d.allocations if a.estado == "despachada"]
        asig_activas_kg = sum((a.cantidad_kg for a in allocations_activas), Decimal("0.0"))
        asig_despachadas_kg = sum((a.cantidad_kg for a in allocations_despachadas), Decimal("0.0"))

        reconciliation_pending = next((r for r in d.reconciliations if r.estado == "pendiente"), None)
        reconciliaciones_list = [
            {
                "id": str(r.id),
                "grain_waybill_id": str(r.grain_waybill_id),
                "peso_neto_origen_kg": float(r.peso_neto_origen_kg),
                "peso_recibido_destino_kg": float(r.peso_recibido_destino_kg),
                "diferencia_kg": float(r.diferencia_kg),
                "diferencia_pct": float(r.diferencia_pct),
                "estado": r.estado,
                "resolucion_tipo": r.resolucion_tipo or "",
                "resolucion_observaciones": r.resolucion_observaciones or "",
            }
            for r in d.reconciliations
        ]

        deliv_item = {
            "id": str(d.id),
            "tracking_number": d.tracking_number,
            "campo_id": str(d.campo_id) if d.campo_id else "",
            "lote_id": str(d.lote_id) if d.lote_id else "",
            "compromiso_id": str(d.compromiso_id) if d.compromiso_id else "",
            "compromiso_rel": d.compromiso,
            "freight_quote_id": str(d.freight_quote_id) if d.freight_quote_id else "",
            "freight_quote_rel": d.freight_quote,
            "acopio_receptor": d.acopio_receptor or "",
            "destination_final_reference": d.destination_final_reference or "Rosario",
            "cultivo": d.cultivo or "soja",
            "transportista_nombre": d.transportista_nombre or "Marcelo Martina",
            "fecha_planificada_fmt": d.fecha_planificada.strftime("%d/%m/%Y") if d.fecha_planificada else "-",
            "fecha_planificada_str": d.fecha_planificada.strftime("%Y-%m-%d") if d.fecha_planificada else "",
            "toneladas_planificadas": float(d.toneladas_planificadas) if d.toneladas_planificadas is not None else None,
            "toneladas_planificadas_fmt": f"{d.toneladas_planificadas:.2f}".replace(".", ",") if d.toneladas_planificadas is not None else "-",
            "toneladas_planificadas_raw": str(d.toneladas_planificadas) if d.toneladas_planificadas is not None else "",
            "kg_neto_origen_total": float(d.kg_neto_origen_total) if d.kg_neto_origen_total is not None else None,
            "kg_neto_origen_total_fmt": f"{d.kg_neto_origen_total:,.0f}".replace(",", ".") if d.kg_neto_origen_total is not None else "-",
            "kg_recibido_total": float(d.kg_recibido_total) if d.kg_recibido_total is not None else None,
            "diferencia_total_kg": float(d.diferencia_total_kg) if d.diferencia_total_kg is not None else None,
            "diferencia_total_kg_fmt": f"{d.diferencia_total_kg:+.0f}".replace(",", ".") if d.diferencia_total_kg is not None else "-",
            "diferencia_total_pct": float(d.diferencia_total_pct) if d.diferencia_total_pct is not None else None,
            "diferencia_total_pct_fmt": f"{d.diferencia_total_pct:+.2f}".replace(".", ",") if d.diferencia_total_pct is not None else "-",
            "estado": d.estado,
            "documentacion_status": d.documentacion_status,
            "observaciones": d.observaciones or "",
            "waybills": waybills_list,
            "allocations_activas": allocations_activas,
            "allocations_despachadas": allocations_despachadas,
            "toneladas_asignadas_activas_tn": float(asig_activas_kg / Decimal("1000.0")),
            "toneladas_despachadas_tn": float(asig_despachadas_kg / Decimal("1000.0")),
            "reconciliation_pending": reconciliation_pending,
            "reconciliations": reconciliaciones_list,
        }

        deliveries_list.append(deliv_item)
        deliveries_dict_json.append({
            "id": deliv_item["id"],
            "tracking_number": deliv_item["tracking_number"],
            "acopio_receptor": deliv_item["acopio_receptor"],
            "destination_final_reference": deliv_item["destination_final_reference"],
            "transportista_nombre": deliv_item["transportista_nombre"],
            "toneladas_planificadas": deliv_item["toneladas_planificadas"],
            "estado": deliv_item["estado"],
            "waybills": waybills_list,
        })

        engine_deliveries.append(
            GrainDeliveryContext(
                id=d.id,
                tracking_number=d.tracking_number,
                campo_id=d.campo_id,
                lote_id=d.lote_id,
                compromiso_id=d.compromiso_id,
                freight_quote_id=d.freight_quote_id,
                acopio_receptor=d.acopio_receptor,
                destination_final_reference=d.destination_final_reference,
                cultivo=d.cultivo,
                transportista_nombre=d.transportista_nombre,
                fecha_planificada=d.fecha_planificada,
                toneladas_planificadas=d.toneladas_planificadas,
                kg_neto_origen_total=d.kg_neto_origen_total,
                kg_recibido_total=d.kg_recibido_total,
                diferencia_total_kg=d.diferencia_total_kg,
                diferencia_total_pct=d.diferencia_total_pct,
                estado=d.estado,
                documentacion_status=d.documentacion_status,
                observaciones=d.observaciones,
                waybills=engine_waybills,
            )
        )

    ctx = DecisionContext(
        cultivo=cultivo if cultivo in ["maiz", "soja", "sorgo", "trigo"] else "soja",  # type: ignore
        deliveries=engine_deliveries,
    )
    result = evaluar_motor_decisiones_detallado(ctx)
    delivery_insights = [ins for ins in result.insights if ins.domain == "deliveries"]

    import json
    return templates.TemplateResponse(
        request=request,
        name="comercial_entregas.html",
        context={
            "user": user,
            "campania_activa": camp_nombre,
            "cultivo_seleccionado": cultivo,
            "mensaje_exito": mensaje,
            "mensaje_error": error,
            "deliveries": deliveries_list,
            "deliveries_json": json.dumps(deliveries_dict_json),
            "delivery_insights": delivery_insights,
            "compromisos": compromisos_list,
            "quotes": quotes_objs,
        },
    )


@app.post("/comercial/entregas/crear")
async def create_comercial_entrega(
    request: Request,
    fecha_planificada: str = Form(...),
    acopio_receptor: str = Form(...),
    destination_final_reference: Optional[str] = Form("Rosario"),
    transportista_nombre: Optional[str] = Form("Marcelo Martina"),
    toneladas_planificadas: Optional[str] = Form(None),
    cultivo: Optional[str] = Form("soja"),
    estado: str = Form("planificada"),
    compromiso_id: Optional[str] = Form(None),
    freight_quote_id: Optional[str] = Form(None),
    campo_id: Optional[str] = Form(None),
    lote_id: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Crea una nueva entrega de grano con número único de seguimiento interno.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))

    if not acopio_receptor or not acopio_receptor.strip():
        return RedirectResponse("/comercial/entregas?error=El+acopio+receptor+es+obligatorio", status_code=status.HTTP_303_SEE_OTHER)

    fecha_plan = None
    if fecha_planificada:
        try:
            fecha_plan = datetime.strptime(fecha_planificada.strip(), "%Y-%m-%d").date()
        except ValueError:
            return RedirectResponse("/comercial/entregas?error=Formato+de+fecha+inválido", status_code=status.HTTP_303_SEE_OTHER)

    ton_dec = parse_decimal_ar(toneladas_planificadas)

    date_str = datetime.now().strftime("%Y%m%d")
    unique_suffix = uuid.uuid4().hex[:4].upper()
    tracking_number = f"ENT-{date_str}-{unique_suffix}"

    comp_uuid = get_uuid(compromiso_id) if compromiso_id and compromiso_id.strip() else None
    if comp_uuid:
        from app.models import CompromisoGrano
        res_c = await db.execute(select(CompromisoGrano).where(CompromisoGrano.id == comp_uuid, CompromisoGrano.cliente_id == cliente_id))
        if not res_c.scalars().first():
            return RedirectResponse("/comercial/entregas?error=Compromiso+no+encontrado+o+no+autorizado", status_code=status.HTTP_303_SEE_OTHER)

    quote_uuid = get_uuid(freight_quote_id) if freight_quote_id and freight_quote_id.strip() else None
    if quote_uuid:
        from app.models import FreightQuote
        res_q = await db.execute(select(FreightQuote).where(FreightQuote.id == quote_uuid, FreightQuote.cliente_id == cliente_id))
        if not res_q.scalars().first():
            return RedirectResponse("/comercial/entregas?error=Cotización+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    from app.models import GrainDelivery
    delivery = GrainDelivery(
        cliente_id=cliente_id,
        tracking_number=tracking_number,
        acopio_receptor=acopio_receptor.strip(),
        destination_final_reference=(destination_final_reference or "Rosario").strip(),
        transportista_nombre=(transportista_nombre or "Marcelo Martina").strip(),
        fecha_planificada=fecha_plan,
        toneladas_planificadas=ton_dec,
        cultivo=(cultivo or "soja").strip().lower(),
        estado=estado if estado in VALID_DELIVERY_TRANSITIONS else "planificada",
        documentacion_status="sin_documentacion",
        compromiso_id=comp_uuid,
        freight_quote_id=quote_uuid,
        campo_id=get_uuid(campo_id) if campo_id and campo_id.strip() else None,
        lote_id=get_uuid(lote_id) if lote_id and lote_id.strip() else None,
        observaciones=observaciones.strip() if observaciones else None,
    )

    db.add(delivery)
    await db.commit()

    msg = f"Entrega '{tracking_number}' registrada exitosamente."
    return RedirectResponse(f"/comercial/entregas?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/entregas/{delivery_id}/editar")
async def edit_comercial_entrega(
    request: Request,
    delivery_id: str,
    fecha_planificada: str = Form(...),
    acopio_receptor: str = Form(...),
    destination_final_reference: Optional[str] = Form("Rosario"),
    transportista_nombre: Optional[str] = Form("Marcelo Martina"),
    toneladas_planificadas: Optional[str] = Form(None),
    cultivo: Optional[str] = Form("soja"),
    estado: str = Form("planificada"),
    compromiso_id: Optional[str] = Form(None),
    freight_quote_id: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Edita una entrega existente y valida transiciones permitidas.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    d_uuid = get_uuid(delivery_id)

    from app.models import GrainDelivery
    stmt = select(GrainDelivery).where(GrainDelivery.id == d_uuid, GrainDelivery.cliente_id == cliente_id)
    res = await db.execute(stmt)
    delivery = res.scalars().first()

    if not delivery:
        return RedirectResponse("/comercial/entregas?error=Entrega+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    comp_uuid = get_uuid(compromiso_id) if compromiso_id and compromiso_id.strip() else None
    if comp_uuid:
        from app.models import CompromisoGrano
        res_c = await db.execute(select(CompromisoGrano).where(CompromisoGrano.id == comp_uuid, CompromisoGrano.cliente_id == cliente_id))
        if not res_c.scalars().first():
            return RedirectResponse("/comercial/entregas?error=Compromiso+no+encontrado+o+no+autorizado", status_code=status.HTTP_303_SEE_OTHER)

    quote_uuid = get_uuid(freight_quote_id) if freight_quote_id and freight_quote_id.strip() else None
    if quote_uuid:
        from app.models import FreightQuote
        res_q = await db.execute(select(FreightQuote).where(FreightQuote.id == quote_uuid, FreightQuote.cliente_id == cliente_id))
        if not res_q.scalars().first():
            return RedirectResponse("/comercial/entregas?error=Cotización+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    if estado != delivery.estado:
        allowed = VALID_DELIVERY_TRANSITIONS.get(delivery.estado, set())
        if estado not in allowed:
            return RedirectResponse(
                f"/comercial/entregas?error=Transición+de+estado+no+permitida+desde+'{delivery.estado}'+hacia+'{estado}'",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        delivery.estado = estado

    if fecha_planificada:
        try:
            delivery.fecha_planificada = datetime.strptime(fecha_planificada.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass

    delivery.acopio_receptor = acopio_receptor.strip()
    delivery.destination_final_reference = (destination_final_reference or "Rosario").strip()
    delivery.transportista_nombre = (transportista_nombre or "Marcelo Martina").strip()
    delivery.toneladas_planificadas = parse_decimal_ar(toneladas_planificadas)
    delivery.cultivo = (cultivo or "soja").strip().lower()
    delivery.compromiso_id = comp_uuid
    delivery.freight_quote_id = quote_uuid
    delivery.observaciones = observaciones.strip() if observaciones else None

    await db.commit()

    msg = f"Entrega '{delivery.tracking_number}' actualizada exitosamente."
    return RedirectResponse(f"/comercial/entregas?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/entregas/{delivery_id}/eliminar")
async def delete_comercial_entrega(
    request: Request,
    delivery_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Elimina una entrega de grano respetando multitenancy.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    d_uuid = get_uuid(delivery_id)

    from app.models import GrainDelivery
    stmt = select(GrainDelivery).where(GrainDelivery.id == d_uuid, GrainDelivery.cliente_id == cliente_id)
    res = await db.execute(stmt)
    delivery = res.scalars().first()

    if not delivery:
        return RedirectResponse("/comercial/entregas?error=Entrega+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    tracking = delivery.tracking_number
    await db.delete(delivery)
    await db.commit()

    msg = f"Entrega '{tracking}' eliminada exitosamente."
    return RedirectResponse(f"/comercial/entregas?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/entregas/{delivery_id}/cartas/crear")
async def create_comercial_waybill(
    request: Request,
    delivery_id: str,
    numero_carta_porte: Optional[str] = Form(None),
    tipo_camion: Optional[str] = Form("normal"),
    capacidad_referencia_kg: Optional[str] = Form("35000"),
    tara_kg: Optional[str] = Form(None),
    peso_bruto_origen_kg: Optional[str] = Form(None),
    peso_recibido_destino_kg: Optional[str] = Form(None),
    referencia_ticket_origen: Optional[str] = Form(None),
    referencia_ticket_destino: Optional[str] = Form(None),
    estado: str = Form("planificada"),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Crea una carta de porte asociada a una entrega.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    d_uuid = get_uuid(delivery_id)

    from app.models import GrainDelivery, GrainWaybill
    from sqlalchemy.orm import selectinload
    stmt = select(GrainDelivery).options(selectinload(GrainDelivery.waybills)).where(
        GrainDelivery.id == d_uuid, GrainDelivery.cliente_id == cliente_id
    )
    res = await db.execute(stmt)
    delivery = res.scalars().first()

    if not delivery:
        return RedirectResponse("/comercial/entregas?error=Entrega+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    cpe_num = numero_carta_porte.strip() if numero_carta_porte and numero_carta_porte.strip() else None

    if cpe_num:
        stmt_dup = select(GrainWaybill).where(
            GrainWaybill.cliente_id == cliente_id,
            GrainWaybill.numero_carta_porte == cpe_num,
        )
        res_dup = await db.execute(stmt_dup)
        if res_dup.scalars().first():
            return RedirectResponse(
                f"/comercial/entregas?error=Ya+existe+una+carta+de+porte+con+el+número+'{cpe_num}'",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    tara_dec = parse_decimal_ar(tara_kg)
    bruto_dec = parse_decimal_ar(peso_bruto_origen_kg)
    recibido_dec = parse_decimal_ar(peso_recibido_destino_kg)
    cap_dec = parse_decimal_ar(capacidad_referencia_kg)

    from app.services.decision_engine.calculators.delivery import (
        calculate_origin_net_weight,
        calculate_delivery_weight_difference,
    )
    weight_res = calculate_origin_net_weight(bruto_dec, tara_dec)
    if bruto_dec is not None and tara_dec is not None and not weight_res.is_valid_origin_weight:
        return RedirectResponse(
            f"/comercial/entregas?error={weight_res.warning or 'El+peso+bruto+no+puede+ser+menor+a+la+tara'}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    neto_origen_dec = weight_res.origin_net_weight_kg
    diff_res = calculate_delivery_weight_difference(neto_origen_dec, recibido_dec)

    waybill = GrainWaybill(
        cliente_id=cliente_id,
        entrega_id=delivery.id,
        numero_carta_porte=cpe_num,
        tipo_camion=(tipo_camion or "normal").strip(),
        capacidad_referencia_kg=cap_dec or Decimal("35000"),
        tara_kg=tara_dec,
        peso_bruto_origen_kg=bruto_dec,
        peso_neto_origen_kg=neto_origen_dec,
        peso_recibido_destino_kg=recibido_dec,
        diferencia_kg=diff_res.difference_kg,
        diferencia_pct=diff_res.difference_pct,
        referencia_ticket_origen=referencia_ticket_origen.strip() if referencia_ticket_origen else None,
        referencia_ticket_destino=referencia_ticket_destino.strip() if referencia_ticket_destino else None,
        estado=estado if estado in ["planificada", "cargada", "en_transito", "recibida", "observada", "anulada"] else "planificada",
        observaciones=observaciones.strip() if observaciones else None,
    )

    db.add(waybill)
    delivery.waybills.append(waybill)
    recalculate_delivery_totals(delivery)

    await db.commit()

    msg = f"Carta de porte registrada para la entrega '{delivery.tracking_number}'."
    return RedirectResponse(f"/comercial/entregas?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/entregas/cartas/{waybill_id}/eliminar")
async def delete_comercial_waybill(
    request: Request,
    waybill_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Elimina una carta de porte respetando multitenancy y recalcula los totales de la entrega.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    w_uuid = get_uuid(waybill_id)

    from app.models import GrainWaybill, GrainDelivery
    from sqlalchemy.orm import selectinload
    stmt = select(GrainWaybill).where(GrainWaybill.id == w_uuid, GrainWaybill.cliente_id == cliente_id)
    res = await db.execute(stmt)
    waybill = res.scalars().first()

    if not waybill:
        return RedirectResponse("/comercial/entregas?error=Carta+de+porte+no+encontrada+o+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    delivery_id = waybill.entrega_id
    await db.delete(waybill)
    await db.flush()

    stmt_del = select(GrainDelivery).options(selectinload(GrainDelivery.waybills)).where(GrainDelivery.id == delivery_id)
    res_del = await db.execute(stmt_del)
    delivery = res_del.scalars().first()
    if delivery:
        recalculate_delivery_totals(delivery)

    await db.commit()

    return RedirectResponse("/comercial/entregas?mensaje=Carta+de+porte+eliminada+exitosamente", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/entregas/{delivery_id}/despachar")
async def dispatch_comercial_entrega(
    request: Request,
    delivery_id: str,
    waybill_id: str = Form(...),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirma el despacho físico de stock para una entrega con carta de porte (Stock 1C).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    user_id = get_uuid(user.get("id"))
    d_uuid = get_uuid(delivery_id)
    w_uuid = get_uuid(waybill_id)

    from app.services.stock_service import confirm_delivery_dispatch

    try:
        res = await confirm_delivery_dispatch(
            db=db,
            cliente_id=cliente_id,
            user_id=user_id,
            delivery_id=d_uuid,
            waybill_id=w_uuid,
            observaciones=observaciones,
        )
        msg = f"Despacho físico confirmado exitosamente ({res['peso_despachado_kg'] / Decimal('1000.0'):.2f} Tn salidas de stock)."
        return RedirectResponse(f"/comercial/entregas?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as ve:
        return RedirectResponse(f"/comercial/entregas?error={str(ve).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/comercial/entregas?error=Error+al+confirmar+despacho:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/entregas/{delivery_id}/cartas/{waybill_id}/recepcion")
@app.post("/comercial/entregas/cartas/{waybill_id}/recepcion")
async def record_waybill_reception(
    request: Request,
    waybill_id: str,
    delivery_id: Optional[str] = None,
    peso_recibido_destino_kg: str = Form(...),
    fecha_recepcion: Optional[str] = Form(None),
    referencia_ticket_destino: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Registra el peso recibido en destino y genera la evaluación de conciliación de pesaje (Stock 1C).
    Soporta rutas con o sin delivery_id explícito en la URL.
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    user_id = get_uuid(user.get("id"))
    w_uuid = get_uuid(waybill_id)

    try:
        # Si delivery_id no vino en la URL (ruta alias), lo buscamos a partir de la carta de porte
        d_uuid = None
        if delivery_id:
            d_uuid = get_uuid(delivery_id)
        else:
            from app.models import GrainWaybill
            stmt_w = select(GrainWaybill.entrega_id).where(GrainWaybill.id == w_uuid, GrainWaybill.cliente_id == cliente_id)
            res_w = await db.execute(stmt_w)
            d_uuid = res_w.scalar_one_or_none()
            if not d_uuid:
                return RedirectResponse("/comercial/entregas?error=Carta+de+porte+no+encontrada", status_code=status.HTTP_303_SEE_OTHER)

        from app.services.stock_service import parse_decimal_ar
        peso_destino = parse_decimal_ar(peso_recibido_destino_kg)
        if not peso_destino or peso_destino <= Decimal("0.0"):
            return RedirectResponse("/comercial/entregas?error=El+peso+recibido+en+destino+debe+ser+mayor+a+0", status_code=status.HTTP_303_SEE_OTHER)

        parsed_fecha_rec = None
        if fecha_recepcion and fecha_recepcion.strip():
            f_str = fecha_recepcion.strip()
            try:
                if "T" in f_str:
                    parsed_fecha_rec = datetime.strptime(f_str[:16], "%Y-%m-%dT%H:%M")
                else:
                    parsed_fecha_rec = datetime.strptime(f_str[:10], "%Y-%m-%d")
            except ValueError:
                pass

        from app.services.stock_service import record_delivery_reception_and_reconciliation
        res = await record_delivery_reception_and_reconciliation(
            db=db,
            cliente_id=cliente_id,
            user_id=user_id,
            delivery_id=d_uuid,
            waybill_id=w_uuid,
            peso_recibido_destino_kg=peso_destino,
            observaciones=observaciones,
            fecha_recepcion=parsed_fecha_rec,
            referencia_ticket_destino=referencia_ticket_destino,
        )
        msg = f"Peso de recepción registrado exitosamente ({peso_destino / Decimal('1000.0'):.2f} Tn). Conciliación: {res['estado_reconciliacion']}."
        return RedirectResponse(f"/comercial/entregas?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as ve:
        return RedirectResponse(f"/comercial/entregas?error={str(ve).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/comercial/entregas?error=Error+al+registrar+recepción:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/comercial/entregas/reconciliaciones/{reconciliation_id}/resolver")
async def resolve_waybill_reconciliation_endpoint(
    request: Request,
    reconciliation_id: str,
    resolucion_tipo: str = Form(...),
    observaciones: str = Form(...),
    ajuste_cantidad_valor: Optional[str] = Form(None),
    stock_partida_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Resuelve explícitamente una diferencia de pesaje de conciliación (Stock 1C).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/entregas", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    user_id = get_uuid(user.get("id"))
    r_uuid = get_uuid(reconciliation_id)
    p_uuid = get_uuid(stock_partida_id) if stock_partida_id and stock_partida_id.strip() else None

    from app.services.stock_service import resolve_weight_reconciliation, parse_decimal_ar

    try:
        ajuste_val = parse_decimal_ar(ajuste_cantidad_valor) if ajuste_cantidad_valor else None
        res = await resolve_weight_reconciliation(
            db=db,
            cliente_id=cliente_id,
            user_id=user_id,
            reconciliation_id=r_uuid,
            resolucion_tipo=resolucion_tipo,
            observaciones=observaciones,
            ajuste_cantidad_valor=ajuste_val,
            stock_partida_id=p_uuid,
        )
        msg = f"Conciliación de pesaje resuelta exitosamente ('{res['resolucion_tipo']}')."
        return RedirectResponse(f"/comercial/entregas?mensaje={msg}", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as ve:
        return RedirectResponse(f"/comercial/entregas?error={str(ve).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(f"/comercial/entregas?error=Error+al+resolver+conciliación:+{str(e).replace(' ', '+')}", status_code=status.HTTP_303_SEE_OTHER)








