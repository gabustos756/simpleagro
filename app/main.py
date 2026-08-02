from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict
import uuid
import os
import time
import logging

from fastapi import FastAPI, Request, Form, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_password
from app.database import init_db, AsyncSessionLocal, get_db
from app.models import Cliente, Usuario, Campo, Lote, Instalacion, ServicioInstalado
from app.enums import (
    EstadoProductivoLoteEnum,
    EstadoServicioInstaladoEnum,
    FrecuenciaPagoEnum,
    RolUsuario,
    TenenciaTipoEnum,
    TipoServicioEnum,
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

# Configuración de Logging para Performance
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("eduagro.performance")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestor del ciclo de vida: inicializa tablas y datos iniciales en PostgreSQL."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
    yield


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
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

templates = Jinja2Templates(directory=templates_dir)
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
TAREAS_STORE = list(DEMO_TAREAS)


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


def lote_to_dict(l: Lote, campo_nombre: str = "Estancia La Esperanza") -> dict:
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
        "notas_alquiler": l.notas_alquiler or "Tierra familiar de la Familia Matteuda.",
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


def instalacion_to_dict(inst: Instalacion, campo_nombre: str = "Estancia La Esperanza") -> dict:
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


def servicio_to_dict(s: ServicioInstalado, campo_nombre: str = "Estancia La Esperanza", inst_nombre: str = "Instalación General") -> dict:
    tipo_str = s.tipo_servicio.value if hasattr(s.tipo_servicio, "value") else str(s.tipo_servicio)
    frec_str = s.frecuencia_pago.value if hasattr(s.frecuencia_pago, "value") else str(s.frecuencia_pago)
    est_str = s.estado.value if hasattr(s.estado, "value") else str(s.estado)

    tipo_labels = {
        "luz_rural": "⚡ Luz Rural",
        "internet": "📡 Internet Satelital",
        "combustible": "🛢️ Combustible Diesel",
        "impuesto_tasa": "🏛️ Tasa Vial",
    }

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
        "frecuencia_label": frec_str.title(),
        "monto_estimado_ars": float(s.monto_estimado_ars),
        "monto_real_ars": float(s.monto_real_ars),
        "monto_usd": float(s.monto_usd),
        "fecha_vencimiento": str(s.fecha_vencimiento),
        "estado": est_str,
        "estado_label": est_str.replace("_", " ").title(),
        "comprobante_url": s.comprobante_url or "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80",
        "observaciones": s.observaciones or "",
    }


async def fetch_campos_dicts(db: AsyncSession) -> List[dict]:
    res_c = await db.execute(select(Campo))
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


async def fetch_servicios_dicts(db: AsyncSession) -> List[dict]:
    res_s = await db.execute(select(ServicioInstalado))
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
    if hasattr(request.state, "user"):
        return request.state.user

    user_id_raw = request.session.get("user_id")
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
            "demo_usuarios": DEMO_USUARIOS,
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
                "demo_usuarios": DEMO_USUARIOS,
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
            "cotizacion_dolar": "1285.50",
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
            "cotizacion_dolar": "1285.50",
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
    lotes = await fetch_lotes_dicts(db)
    lote = next((l for l in lotes if l["id"] == lote_id), None)
    if not lote:
        return RedirectResponse("/productivo/lotes", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="productivo_lote_ficha.html",
        context={"user": user, "campo_activo": campo_activo, "lote": lote},
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

    return templates.TemplateResponse(
        request=request,
        name="productivo_rendimientos.html",
        context={"user": user, "campo_activo": campo_activo, "lotes": lotes_filtrados},
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
    observaciones: Optional[str] = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    s_uuid = uuid.uuid4()
    c_uuid = get_uuid(campo_id)
    i_uuid = get_uuid(instalacion_id) if instalacion_id else None
    m_real = float(monto_real_ars)
    m_usd = Decimal(str(round(m_real / 1285.50, 2)))

    tipo_s_enum = TipoServicioEnum(tipo_servicio) if tipo_servicio in [e.value for e in TipoServicioEnum] else TipoServicioEnum.LUZ_RURAL
    frec_p_enum = FrecuenciaPagoEnum(frecuencia_pago) if frecuencia_pago in [e.value for e in FrecuenciaPagoEnum] else FrecuenciaPagoEnum.MENSUAL
    fecha_venc = date.fromisoformat(fecha_vencimiento)

    nuevo_servicio = ServicioInstalado(
        id=s_uuid,
        cliente_id=get_uuid(DEMO_CLIENTE["id"]),
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
        observaciones=observaciones or "Servicio operativo registrado",
    )
    db.add(nuevo_servicio)
    await db.commit()

    return RedirectResponse(f"/servicios/{s_uuid}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/servicios/vencimientos", response_class=HTMLResponse)
async def list_servicios_vencimientos(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios/vencimientos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    servicios = await fetch_servicios_dicts(db)
    servicios_ordenados = sorted(servicios, key=lambda s: s["fecha_vencimiento"])

    return templates.TemplateResponse(
        request=request,
        name="servicios_vencimientos.html",
        context={"user": user, "campo_activo": campo_activo, "servicios": servicios_ordenados},
    )


@app.get("/servicios/instalaciones", response_class=HTMLResponse)
async def list_instalaciones(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/servicios/instalaciones", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    instalaciones = await fetch_instalaciones_dicts(db)
    servicios = await fetch_servicios_dicts(db)

    return templates.TemplateResponse(
        request=request,
        name="servicios_instalaciones.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
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
    servicios = await fetch_servicios_dicts(db)
    servicio = next((s for s in servicios if s["id"] == servicio_id), None)
    if not servicio:
        return RedirectResponse("/servicios", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="servicios_ficha.html",
        context={"user": user, "campo_activo": campo_activo, "servicio": servicio},
    )


@app.get("/servicios/{servicio_id}/editar", response_class=HTMLResponse)
async def form_editar_servicio(request: Request, servicio_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    instalaciones = await fetch_instalaciones_dicts(db)
    servicios = await fetch_servicios_dicts(db)
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
        m_real = float(monto_real_ars)
        m_usd = Decimal(str(round(m_real / 1285.50, 2)))
        tipo_s_enum = TipoServicioEnum(tipo_servicio) if tipo_servicio in [e.value for e in TipoServicioEnum] else TipoServicioEnum.LUZ_RURAL
        frec_p_enum = FrecuenciaPagoEnum(frecuencia_pago) if frecuencia_pago in [e.value for e in FrecuenciaPagoEnum] else FrecuenciaPagoEnum.MENSUAL
        fecha_venc = date.fromisoformat(fecha_vencimiento)

        servicio_obj.campo_id = get_uuid(campo_id)
        servicio_obj.instalacion_id = get_uuid(instalacion_id) if instalacion_id else None
        servicio_obj.concepto = concepto.strip()
        servicio_obj.proveedor = proveedor.strip()
        servicio_obj.tipo_servicio = tipo_s_enum
        servicio_obj.frecuencia_pago = frec_p_enum
        servicio_obj.monto_estimado_ars = Decimal(str(monto_estimado_ars))
        servicio_obj.monto_real_ars = Decimal(str(m_real))
        servicio_obj.monto_usd = m_usd
        servicio_obj.fecha_vencimiento = fecha_venc
        servicio_obj.observaciones = observaciones
        await db.commit()

    return RedirectResponse(f"/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/servicios/{servicio_id}/pagar")
async def pagar_servicio(request: Request, servicio_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    s_uuid = get_uuid(servicio_id)
    res = await db.execute(select(ServicioInstalado).where(ServicioInstalado.id == s_uuid))
    servicio_obj = res.scalars().first()

    if servicio_obj:
        servicio_obj.estado = EstadoServicioInstaladoEnum.AL_DIA
        await db.commit()

    return RedirectResponse(f"/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)


# ----------------------------------------------------------------------
# Módulo de Clima y Alertas Agronómicas por Geolocalización de Campo
# ----------------------------------------------------------------------

@app.get("/clima/campos", response_class=HTMLResponse)
async def clima_resumen_campos(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/clima/campos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    campos_clima = []
    for c in campos:
        weather_info = get_weather_for_location(
            c.get("latitud"),
            c.get("longitud"),
            c.get("localidad_referencia", "Laguna Larga, Córdoba"),
        )
        campos_clima.append({"campo": c, "weather": weather_info})

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

    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)
    campo = next((c for c in campos if c["id"] == campo_id), None)
    if not campo:
        return RedirectResponse("/clima/campos", status_code=status.HTTP_303_SEE_OTHER)

    weather_info = get_weather_for_location(
        campo.get("latitud"),
        campo.get("longitud"),
        campo.get("localidad_referencia", "Laguna Larga, Córdoba"),
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
