from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict
import uuid
import os
import time
import logging
import asyncio
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

from fastapi import FastAPI, Request, Form, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func
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
    StockGrano,
    ContratoVentaGrano,
    CompromisoGrano,
    PrecioMercadoCache,
)
from app.services.comercial import calcular_posicion_comercial, obtener_campania_activa_para_cliente
from app.enums import (
    EstadoProductivoLoteEnum,
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


def servicio_to_dict(s: ServicioInstalado, campo_nombre: str = "Campo General", inst_nombre: str = "Instalación General") -> dict:
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
        logger.error(f"Error al eliminar campo {campo_id}: {e}")

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
    campos = await fetch_campos_dicts(db)
    servicios = await fetch_servicios_dicts(db)
    servicios_ordenados = sorted(servicios, key=lambda s: s["fecha_vencimiento"])

    return templates.TemplateResponse(
        request=request,
        name="servicios_vencimientos.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "servicios": servicios_ordenados,
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
    servicios = await fetch_servicios_dicts(db)

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

    from app.services.clima import obtener_clima_para_campo_async
    campo_activo = await get_campo_activo_db(request, db)
    campos = await fetch_campos_dicts(db)

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
    db: AsyncSession = Depends(get_db),
):
    """
    Vista operativa de gestión de Stock Físico (Silos Bolsa & Acopios).
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

    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    camp_uuid = camp_obj.id if camp_obj else None
    camp_nombre = camp_obj.nombre if camp_obj else "Campaña 2025/2026"

    cultivo_sel = (cultivo or "soja").strip().lower()

    stmt_stock = select(StockGrano).where(
        StockGrano.cliente_id == cliente_id,
        func.lower(StockGrano.cultivo) == cultivo_sel,
    )
    if camp_uuid:
        stmt_stock = stmt_stock.where(StockGrano.campania_id == camp_uuid)

    res_stock = await db.execute(stmt_stock)
    stocks_objs = res_stock.scalars().all()

    campos_map = {str(c["id"]): c["nombre"] for c in campos}

    stocks_list = []
    if stocks_objs:
        for st in stocks_objs:
            ub_val = st.ubicacion_tipo.value if hasattr(st.ubicacion_tipo, "value") else str(st.ubicacion_tipo)
            stocks_list.append({
                "id": str(st.id),
                "campo_id": str(st.campo_id),
                "campo_nombre": campos_map.get(str(st.campo_id), "Campo General"),
                "cultivo": st.cultivo,
                "ubicacion_tipo": ub_val,
                "identificador": st.identificador,
                "toneladas_almacenadas": float(st.toneladas_almacenadas or 0.0),
                "fecha_ingreso": str(st.fecha_ingreso) if st.fecha_ingreso else "",
                "observaciones": st.observaciones or "",
            })

    tn_silo_bolsa = sum(s["toneladas_almacenadas"] for s in stocks_list if s["ubicacion_tipo"] == "silo_bolsa")
    tn_acopio = sum(s["toneladas_almacenadas"] for s in stocks_list if s["ubicacion_tipo"] != "silo_bolsa")
    tn_total = tn_silo_bolsa + tn_acopio

    return templates.TemplateResponse(
        request=request,
        name="comercial_stock.html",
        context={
            "user": user,
            "campo_activo": campo_activo,
            "campos": campos,
            "campania_activa": camp_nombre,
            "cultivo_seleccionado": cultivo_sel,
            "stocks": stocks_list,
            "tn_silo_bolsa": round(tn_silo_bolsa, 2),
            "tn_acopio": round(tn_acopio, 2),
            "tn_total": round(tn_total, 2),
            "mensaje": mensaje,
        },
    )


@app.post("/comercial/stock/crear")
async def create_comercial_stock(
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
    Alta mínima funcional de un registro de Stock Físico (Silo Bolsa o Acopio).
    """
    user = await get_current_user_from_session(request, db)
    if not user:
        return RedirectResponse("/login?next=/comercial/stock", status_code=status.HTTP_303_SEE_OTHER)

    rol_user = user.get("rol")
    if rol_user == RolUsuario.OPERARIO_CAMPO:
        return RedirectResponse("/modo-campo", status_code=status.HTTP_303_SEE_OTHER)

    cliente_id = get_uuid(user.get("cliente_id", DEMO_CLIENTE["id"]))
    camp_obj = await obtener_campania_activa_para_cliente(db, cliente_id)
    if not camp_obj:
        return JSONResponse({"error": "No hay campaña registrada para el cliente"}, status_code=400)

    try:
        f_ingreso = date.fromisoformat(fecha_ingreso)
    except Exception:
        f_ingreso = date.today()

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

    msg = f"Stock '{identificador.strip()}' registrado exitosamente ({toneladas_almacenadas} Tn)."
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

    from app.models import GrainDelivery, GrainWaybill, CompromisoGrano, FreightQuote
    from sqlalchemy.orm import selectinload

    stmt_del = (
        select(GrainDelivery)
        .options(
            selectinload(GrainDelivery.waybills),
            selectinload(GrainDelivery.compromiso),
            selectinload(GrainDelivery.freight_quote),
        )
        .where(GrainDelivery.cliente_id == cliente_id)
        .order_by(GrainDelivery.fecha_creacion.desc())
    )
    res_del = await db.execute(stmt_del)
    deliveries_objs = res_del.scalars().all()

    stmt_comp = select(CompromisoGrano).where(CompromisoGrano.cliente_id == cliente_id)
    res_comp = await db.execute(stmt_comp)
    compromisos_objs = res_comp.scalars().all()

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
            "compromisos": compromisos_objs,
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
    unique_suffix = uuid4().hex[:4].upper()
    tracking_number = f"ENT-{date_str}-{unique_suffix}"

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
        compromiso_id=get_uuid(compromiso_id) if compromiso_id and compromiso_id.strip() else None,
        freight_quote_id=get_uuid(freight_quote_id) if freight_quote_id and freight_quote_id.strip() else None,
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
    delivery.compromiso_id = get_uuid(compromiso_id) if compromiso_id and compromiso_id.strip() else None
    delivery.freight_quote_id = get_uuid(freight_quote_id) if freight_quote_id and freight_quote_id.strip() else None
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







