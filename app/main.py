from typing import Optional
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
import os
import time
import logging

from app.auth import verify_password
from app.enums import (
    EstadoServicioInstaladoEnum,
    FrecuenciaPagoEnum,
    RolUsuario,
    TenenciaTipoEnum,
    TipoServicioEnum,
)
from app.seed import (
    find_user_by_email,
    find_user_by_id,
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

app = FastAPI(
    title="EduAgro ERP Agropecuario",
    description="Plataforma ERP Agropecuaria (Laguna Larga, Córdoba) - Cliente: Familia Matteuda",
    version="1.0.0",
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


from fastapi.staticfiles import StaticFiles

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

# Data Stores en Memoria (Inicializados con Datos Seed Demo para Familia Matteuda)
CAMPOS_STORE = list(DEMO_CAMPOS)
LOTES_STORE = list(DEMO_LOTES)
INSTALACIONES_STORE = list(DEMO_INSTALACIONES)
SERVICIOS_STORE = list(DEMO_SERVICIOS_INSTALADOS)
TAREAS_STORE = list(DEMO_TAREAS)


def get_current_user_from_session(request: Request) -> Optional[dict]:
    """Helper para obtener el usuario autenticado en la sesión actual (cacheado en request.state)."""
    if hasattr(request.state, "user"):
        return request.state.user

    user_id = request.session.get("user_id")
    user = find_user_by_id(user_id) if user_id else None
    request.state.user = user
    return user


def get_campo_activo(request: Request) -> dict:
    """Helper para obtener el Campo Activo de trabajo actual desde la sesión (cacheado en request.state)."""
    if hasattr(request.state, "campo_activo"):
        return request.state.campo_activo

    campo_id = request.session.get("campo_activo_id")
    campo = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
    if not campo and CAMPOS_STORE:
        campo = CAMPOS_STORE[0]
        request.session["campo_activo_id"] = campo["id"]

    result = campo or {"id": "campo-001", "nombre": "Estancia La Esperanza", "ubicacion": "Laguna Larga, Córdoba", "latitud": -31.7766, "longitud": -63.8011}
    request.state.campo_activo = result
    return result


# ----------------------------------------------------------------------
# Rutas de Autenticación & Selección de Campo Activo
# ----------------------------------------------------------------------


@app.post("/cambiar-campo-activo")
def cambiar_campo_activo(request: Request, campo_id: str = Form(...)):
    """Cambia el campo activo de trabajo para toda la sesión del usuario."""
    campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
    if campo_sel:
        request.session["campo_activo_id"] = campo_sel["id"]

    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: Optional[str] = None):
    user = get_current_user_from_session(request)
    if user:
        if user["rol"] == RolUsuario.OPERARIO_CAMPO:
            return RedirectResponse("/campo", status_code=status.HTTP_303_SEE_OTHER)
        elif user["rol"] == RolUsuario.ADMINISTRADOR_FINANZAS:
            return RedirectResponse("/servicios/vencimientos", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "next_url": next or "/",
            "error": None,
            "demo_cliente": DEMO_CLIENTE,
            "demo_usuarios": DEMO_USUARIOS,
        },
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form("/"),
):
    user = find_user_by_email(email)

    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "next_url": next,
                "error": "Credenciales inválidas. Por favor intenta de nuevo.",
                "email": email,
                "demo_cliente": DEMO_CLIENTE,
                "demo_usuarios": DEMO_USUARIOS,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session["user_id"] = user["id"]
    if CAMPOS_STORE:
        request.session["campo_activo_id"] = CAMPOS_STORE[0]["id"]

    target_url = next if next and next != "/" else None
    if not target_url:
        if user["rol"] == RolUsuario.OPERARIO_CAMPO:
            target_url = "/campo"
        elif user["rol"] == RolUsuario.ADMINISTRADOR_FINANZAS:
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
def read_portal_entrada(request: Request):
    """Portal de entrada por operador/área. Renderiza únicamente el portal de entrada."""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )

    lotes_campo_activo = [l for l in LOTES_STORE if l["campo_id"] == campo_activo["id"]]
    servicios_vencidos_count = len([s for s in SERVICIOS_STORE if s.get("estado") == "vencido"])

    return templates.TemplateResponse(
        "portal_entrada.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "campos": CAMPOS_STORE,
            "lotes_count": len(lotes_campo_activo),
            "weather": weather_data,
            "servicios_vencidos_count": servicios_vencidos_count,
            "cotizacion_dolar": "1285.50",
            "campania_activa": "2025-2026",
        },
    )


@app.get("/dashboard", response_class=HTMLResponse)
def read_dashboard_familiar(request: Request, perfil: Optional[str] = "dueno"):
    """Dashboard Gerencial Consolidado (Vista secundaria)."""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )

    lotes_campo_activo = [l for l in LOTES_STORE if l["campo_id"] == campo_activo["id"]]

    vencimientos_demo = [
        {
            "id": 1,
            "concepto": f"EPEC - Luz Rural ({campo_activo['nombre']})",
            "categoria": "Servicios",
            "monto_ars": 485000.00,
            "monto_usd": 377.28,
            "fecha_vencimiento": "2026-08-02",
            "estado": "vencido",
            "comprobante_url": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80",
        },
        {
            "id": 2,
            "concepto": "Arrendamiento Lote 2 - La Escuela (Cuota 2/4)",
            "categoria": "Arrendamiento",
            "monto_ars": 3850000.00,
            "monto_usd": 2994.94,
            "fecha_vencimiento": "2026-08-10",
            "estado": "pendiente",
            "comprobante_url": "https://images.unsplash.com/photo-1450133064473-71024230f91b?auto=format&fit=crop&w=600&q=80",
        },
    ]

    return templates.TemplateResponse(
        "dashboard_familiar.html",
        {
            "request": request,
            "user": user,
            "perfil": perfil,
            "campo_activo": campo_activo,
            "campos": CAMPOS_STORE,
            "lotes_campo": lotes_campo_activo,
            "weather": weather_data,
            "campania_activa": "2025-2026",
            "cotizacion_dolar": "1285.50",
            "ha_totales": campo_activo.get("hectareas_totales", 520),
            "ha_soja": 310,
            "ha_trigo": 185,
            "lluvia_mes": 84.5,
            "gastos_usd": "3,854.52",
            "gastos_ars": "4,955,000",
            "toneladas_estimadas": "2,840",
            "vencimientos": vencimientos_demo,
        },
    )


@app.get("/campo", response_class=HTMLResponse)
def read_modo_campo(
    request: Request,
    campo_id: Optional[str] = None,
    estado_filtro: Optional[str] = "todas",
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/campo", status_code=status.HTTP_303_SEE_OTHER)

    if campo_id:
        campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
        if campo_sel:
            request.session["campo_activo_id"] = campo_sel["id"]

    campo_activo = get_campo_activo(request)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )

    lotes_campo_activo = [l for l in LOTES_STORE if l["campo_id"] == campo_activo["id"]]

    # Tareas del Campo Activo
    tareas_campo = [t for t in TAREAS_STORE if t["campo_id"] == campo_activo["id"]]
    pendientes_count = len([t for t in tareas_campo if t["estado"] == "pendiente"])
    en_curso_count = len([t for t in tareas_campo if t["estado"] == "en_curso"])
    hechas_count = len([t for t in tareas_campo if t["estado"] == "hecha"])

    if estado_filtro in ["pendiente", "en_curso", "hecha"]:
        tareas_filtradas = [t for t in tareas_campo if t["estado"] == estado_filtro]
    else:
        tareas_filtradas = tareas_campo

    return templates.TemplateResponse(
        "modo_campo.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "campos": CAMPOS_STORE,
            "lotes_campo": lotes_campo_activo,
            "weather": weather_data,
            "tareas": tareas_filtradas,
            "estado_filtro": estado_filtro or "todas",
            "pendientes_count": pendientes_count,
            "en_curso_count": en_curso_count,
            "hechas_count": hechas_count,
        },
    )


@app.post("/campo/tareas/{tarea_id}/iniciar")
def iniciar_tarea_campo(request: Request, tarea_id: str):
    """Acción rápida: Iniciar labor de campo (Pendiente -> En Curso)."""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    tarea = next((t for t in TAREAS_STORE if t["id"] == tarea_id), None)
    if tarea:
        tarea["estado"] = "en_curso"
        tarea["estado_label"] = "En Curso"

    referer = request.headers.get("referer", "/campo")
    return RedirectResponse(referer, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/campo/tareas/{tarea_id}/completar")
def completar_tarea_campo(request: Request, tarea_id: str):
    """Acción rápida: Marcar labor realizada (En Curso/Pendiente -> Hecha)."""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    tarea = next((t for t in TAREAS_STORE if t["id"] == tarea_id), None)
    if tarea:
        tarea["estado"] = "hecha"
        tarea["estado_label"] = "Hecha"

    referer = request.headers.get("referer", "/campo")
    return RedirectResponse(referer, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/campo/acciones/lluvia")
def registrar_lluvia_rapida(
    request: Request,
    campo_id: str = Form(...),
    lote_id: Optional[str] = Form(None),
    milimetros: float = Form(...),
    observaciones: Optional[str] = Form(""),
):
    """Acción rápida: Registrar precipitaciones en mm desde camioneta."""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
    lote_sel = next((l for l in LOTES_STORE if l["id"] == lote_id), None) if lote_id else None

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
def registrar_incidencia_rapida(
    request: Request,
    campo_id: str = Form(...),
    lote_id: Optional[str] = Form(None),
    titulo: str = Form(...),
    prioridad: str = Form("alta"),
    observaciones: Optional[str] = Form(""),
):
    """Acción rápida: Reportar rotura, maleza resistente o problema de campo."""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
    lote_sel = next((l for l in LOTES_STORE if l["id"] == lote_id), None) if lote_id else None

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
def registrar_movimiento_stock(
    request: Request,
    campo_id: str = Form(...),
    insumo: str = Form(...),
    cantidad: float = Form(...),
    unidad: str = Form("litros"),
    observaciones: Optional[str] = Form(""),
):
    """Acción rápida: Cargar egreso o consumo simple de insumos/gasoil."""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)

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
def crear_tarea_campo(
    request: Request,
    campo_id: str = Form(...),
    lote_id: Optional[str] = Form(None),
    tipo: str = Form("siembra"),
    titulo: str = Form(...),
    responsable: str = Form(...),
    prioridad: str = Form("media"),
    observaciones: Optional[str] = Form(""),
):
    """Crear una nueva labor o tarea de campo."""
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
    lote_sel = next((l for l in LOTES_STORE if l["id"] == lote_id), None) if lote_id else None

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
def list_campos(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/productivo/campos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    ha_totales_suma = sum(c["hectareas_totales"] for c in CAMPOS_STORE)
    ha_productivas_suma = sum(l["superficie_productiva_ha"] for l in LOTES_STORE)

    return templates.TemplateResponse(
        "productivo_campos.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "campos": CAMPOS_STORE,
            "ha_totales_suma": ha_totales_suma,
            "ha_productivas_suma": ha_productivas_suma,
        },
    )


@app.post("/productivo/campos")
def create_campo(
    request: Request,
    nombre: str = Form(...),
    ubicacion: str = Form(...),
    latitud: Optional[float] = Form(None),
    longitud: Optional[float] = Form(None),
    hectareas_totales: float = Form(...),
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    nuevo_id = f"campo-00{len(CAMPOS_STORE) + 1}"
    nuevo_campo = {
        "id": nuevo_id,
        "nombre": nombre.strip(),
        "ubicacion": ubicacion.strip(),
        "localidad_referencia": ubicacion.strip(),
        "latitud": float(latitud) if latitud else -31.7766,
        "longitud": float(longitud) if longitud else -63.8011,
        "hectareas_totales": float(hectareas_totales),
        "hectareas_productivas": float(hectareas_totales) * 0.95,
        "lotes_count": 0,
    }
    CAMPOS_STORE.append(nuevo_campo)
    request.session["campo_activo_id"] = nuevo_id

    return RedirectResponse("/productivo/campos", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/productivo/lotes", response_class=HTMLResponse)
def list_lotes(
    request: Request,
    campo: Optional[str] = None,
    tenencia: Optional[str] = None,
    cultivo: Optional[str] = None,
    q: Optional[str] = None,
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/productivo/lotes", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    lotes_filtrados = list(LOTES_STORE)

    # Si no se especifica campo en URL, se prioriza el campo activo
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
        "productivo_lotes.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "lotes": lotes_filtrados,
            "campos": CAMPOS_STORE,
            "campo_filtro": campo or campo_activo["id"],
            "tenencia_filtro": tenencia,
            "cultivo_filtro": cultivo,
            "search_q": q,
        },
    )


@app.get("/productivo/lotes/nuevo", response_class=HTMLResponse)
def form_nuevo_lote(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/productivo/lotes/nuevo", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)

    return templates.TemplateResponse(
        "productivo_form_lote.html",
        {"request": request, "user": user, "campo_activo": campo_activo, "lote": None, "campos": CAMPOS_STORE},
    )


@app.post("/productivo/lotes/nuevo")
def create_lote(
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
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
    campo_nombre = campo_sel["nombre"] if campo_sel else "Campo General"

    nuevo_id = f"lote-00{len(LOTES_STORE) + 1}"
    sup_prod = float(superficie_productiva_ha)
    r_real = float(qq_ha_real or 0.0)
    prod_qq = sup_prod * r_real
    prod_t = prod_qq / 10.0

    nuevo_lote = {
        "id": nuevo_id,
        "campo_id": campo_id,
        "campo_nombre": campo_nombre,
        "nombre": nombre.strip(),
        "superficie_total_ha": float(superficie_total_ha),
        "superficie_productiva_ha": sup_prod,
        "tenencia_tipo": tenencia_tipo,
        "tenencia_label": "Propio" if tenencia_tipo == "propio" else "Alquilado",
        "costo_alquiler_usd_ha": float(costo_alquiler_usd_ha or 0.0),
        "vencimiento_alquiler": vencimiento_alquiler,
        "notas_alquiler": "Contrato de arrendamiento registrado",
        "cultivo_anterior": cultivo_anterior,
        "cultivo_actual": cultivo_actual,
        "cultivo_planificado": cultivo_planificado,
        "tipo_suelo": "Argiudol Típico",
        "qq_ha_estimado": float(qq_ha_estimado or 0.0),
        "qq_ha_real": r_real,
        "produccion_total_qq": prod_qq,
        "produccion_total_t": prod_t,
        "observaciones": "Lote registrado en el Módulo Productivo de EduAgro",
        "estado_productivo": "en_crecimiento",
        "estado_productivo_label": "En Crecimiento",
    }
    LOTES_STORE.append(nuevo_lote)

    return RedirectResponse(f"/productivo/lotes/{nuevo_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/productivo/lotes/{lote_id}", response_class=HTMLResponse)
def ficha_lote(request: Request, lote_id: str):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse(f"/login?next=/productivo/lotes/{lote_id}", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    lote = next((l for l in LOTES_STORE if l["id"] == lote_id), None)
    if not lote:
        return RedirectResponse("/productivo/lotes", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "productivo_lote_ficha.html",
        {"request": request, "user": user, "campo_activo": campo_activo, "lote": lote},
    )


@app.get("/productivo/lotes/{lote_id}/editar", response_class=HTMLResponse)
def form_editar_lote(request: Request, lote_id: str):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    lote = next((l for l in LOTES_STORE if l["id"] == lote_id), None)
    if not lote:
        return RedirectResponse("/productivo/lotes", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "productivo_form_lote.html",
        {"request": request, "user": user, "campo_activo": campo_activo, "lote": lote, "campos": CAMPOS_STORE},
    )


@app.post("/productivo/lotes/{lote_id}/editar")
def update_lote(
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
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    lote = next((l for l in LOTES_STORE if l["id"] == lote_id), None)
    if lote:
        campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
        if campo_sel:
            lote["campo_id"] = campo_id
            lote["campo_nombre"] = campo_sel["nombre"]

        sup_prod = float(superficie_productiva_ha)
        r_real = float(qq_ha_real or 0.0)
        prod_qq = sup_prod * r_real

        lote["nombre"] = nombre.strip()
        lote["superficie_total_ha"] = float(superficie_total_ha)
        lote["superficie_productiva_ha"] = sup_prod
        lote["tenencia_tipo"] = tenencia_tipo
        lote["tenencia_label"] = "Propio" if tenencia_tipo == "propio" else "Alquilado"
        lote["costo_alquiler_usd_ha"] = float(costo_alquiler_usd_ha or 0.0)
        lote["vencimiento_alquiler"] = vencimiento_alquiler
        lote["cultivo_anterior"] = cultivo_anterior
        lote["cultivo_actual"] = cultivo_actual
        lote["cultivo_planificado"] = cultivo_planificado
        lote["qq_ha_estimado"] = float(qq_ha_estimado or 0.0)
        lote["qq_ha_real"] = r_real
        lote["produccion_total_qq"] = prod_qq
        lote["produccion_total_t"] = prod_qq / 10.0

    return RedirectResponse(f"/productivo/lotes/{lote_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/productivo/rendimientos", response_class=HTMLResponse)
def list_rendimientos(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/productivo/rendimientos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    lotes_filtrados = [l for l in LOTES_STORE if l["campo_id"] == campo_activo["id"]]

    return templates.TemplateResponse(
        "productivo_rendimientos.html",
        {"request": request, "user": user, "campo_activo": campo_activo, "lotes": lotes_filtrados},
    )


# ----------------------------------------------------------------------
# Módulo de Servicios por Campo e Instalación
# ----------------------------------------------------------------------


@app.get("/servicios/campos", response_class=HTMLResponse)
def servicios_resumen_campos(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/servicios/campos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    total_monto_ars = sum(s["monto_real_ars"] for s in SERVICIOS_STORE)
    total_monto_usd = sum(s["monto_usd"] for s in SERVICIOS_STORE)
    servicios_vencidos_count = len([s for s in SERVICIOS_STORE if s["estado"] == "vencido"])
    servicios_al_dia_count = len([s for s in SERVICIOS_STORE if s["estado"] == "al_dia"])

    return templates.TemplateResponse(
        "servicios_resumen_campos.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "campos": CAMPOS_STORE,
            "servicios": SERVICIOS_STORE,
            "total_monto_ars": total_monto_ars,
            "total_monto_usd": total_monto_usd,
            "servicios_vencidos_count": servicios_vencidos_count,
            "servicios_al_dia_count": servicios_al_dia_count,
        },
    )


@app.get("/servicios", response_class=HTMLResponse)
def list_servicios(
    request: Request,
    campo: Optional[str] = None,
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    q: Optional[str] = None,
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/servicios", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    servicios_filtrados = list(SERVICIOS_STORE)

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
        "servicios_listado.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "servicios": servicios_filtrados,
            "campos": CAMPOS_STORE,
            "campo_filtro": campo or campo_activo["id"],
            "tipo_filtro": tipo,
            "estado_filtro": estado,
            "search_q": q,
        },
    )


@app.get("/servicios/nuevo", response_class=HTMLResponse)
def form_nuevo_servicio(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/servicios/nuevo", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)

    return templates.TemplateResponse(
        "servicios_form.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "servicio": None,
            "campos": CAMPOS_STORE,
            "instalaciones": INSTALACIONES_STORE,
        },
    )


@app.post("/servicios/nuevo")
def create_servicio(
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
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
    inst_sel = next((i for i in INSTALACIONES_STORE if i["id"] == instalacion_id), None)

    nuevo_id = f"serv-00{len(SERVICIOS_STORE) + 1}"
    m_real = float(monto_real_ars)
    m_usd = round(m_real / 1285.50, 2)

    nuevo_servicio = {
        "id": nuevo_id,
        "campo_id": campo_id,
        "campo_nombre": campo_sel["nombre"] if campo_sel else "Campo General",
        "instalacion_id": instalacion_id,
        "instalacion_nombre": inst_sel["nombre"] if inst_sel else "Instalación General",
        "tipo_servicio": tipo_servicio,
        "tipo_servicio_label": tipo_servicio.replace("_", " ").title(),
        "concepto": concepto.strip(),
        "proveedor": proveedor.strip(),
        "frecuencia_pago": frecuencia_pago,
        "frecuencia_label": frecuencia_pago.title(),
        "monto_estimado_ars": float(monto_estimado_ars),
        "monto_real_ars": m_real,
        "monto_usd": m_usd,
        "fecha_vencimiento": fecha_vencimiento,
        "estado": EstadoServicioInstaladoEnum.PENDIENTE.value,
        "estado_label": "Pendiente",
        "comprobante_url": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80",
        "observaciones": observaciones or "Servicio operativo registrado",
    }
    SERVICIOS_STORE.append(nuevo_servicio)

    return RedirectResponse(f"/servicios/{nuevo_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/servicios/vencimientos", response_class=HTMLResponse)
def list_servicios_vencimientos(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/servicios/vencimientos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    servicios_ordenados = sorted(SERVICIOS_STORE, key=lambda s: s["fecha_vencimiento"])

    return templates.TemplateResponse(
        "servicios_vencimientos.html",
        {"request": request, "user": user, "campo_activo": campo_activo, "servicios": servicios_ordenados},
    )


@app.get("/servicios/instalaciones", response_class=HTMLResponse)
def list_instalaciones(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/servicios/instalaciones", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)

    return templates.TemplateResponse(
        "servicios_instalaciones.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "instalaciones": INSTALACIONES_STORE,
            "servicios": SERVICIOS_STORE,
        },
    )


@app.get("/servicios/{servicio_id}", response_class=HTMLResponse)
def ficha_servicio(request: Request, servicio_id: str):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse(f"/login?next=/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    servicio = next((s for s in SERVICIOS_STORE if s["id"] == servicio_id), None)
    if not servicio:
        return RedirectResponse("/servicios", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "servicios_ficha.html",
        {"request": request, "user": user, "campo_activo": campo_activo, "servicio": servicio},
    )


@app.get("/servicios/{servicio_id}/editar", response_class=HTMLResponse)
def form_editar_servicio(request: Request, servicio_id: str):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    servicio = next((s for s in SERVICIOS_STORE if s["id"] == servicio_id), None)
    if not servicio:
        return RedirectResponse("/servicios", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "servicios_form.html",
        {
            "request": request,
            "user": user,
            "campo_activo": campo_activo,
            "servicio": servicio,
            "campos": CAMPOS_STORE,
            "instalaciones": INSTALACIONES_STORE,
        },
    )


@app.post("/servicios/{servicio_id}/editar")
def update_servicio(
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
):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    servicio = next((s for s in SERVICIOS_STORE if s["id"] == servicio_id), None)
    if servicio:
        campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
        inst_sel = next((i for i in INSTALACIONES_STORE if i["id"] == instalacion_id), None)

        m_real = float(monto_real_ars)

        servicio["campo_id"] = campo_id
        servicio["campo_nombre"] = campo_sel["nombre"] if campo_sel else "Campo General"
        servicio["instalacion_id"] = instalacion_id
        servicio["instalacion_nombre"] = inst_sel["nombre"] if inst_sel else "Instalación General"
        servicio["tipo_servicio"] = tipo_servicio
        servicio["concepto"] = concepto.strip()
        servicio["proveedor"] = proveedor.strip()
        servicio["frecuencia_pago"] = frecuencia_pago
        servicio["monto_estimado_ars"] = float(monto_estimado_ars)
        servicio["monto_real_ars"] = m_real
        servicio["monto_usd"] = round(m_real / 1285.50, 2)
        servicio["fecha_vencimiento"] = fecha_vencimiento
        servicio["observaciones"] = observaciones

    return RedirectResponse(f"/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/servicios/{servicio_id}/pagar")
def pagar_servicio(request: Request, servicio_id: str):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    servicio = next((s for s in SERVICIOS_STORE if s["id"] == servicio_id), None)
    if servicio:
        servicio["estado"] = EstadoServicioInstaladoEnum.AL_DIA.value
        servicio["estado_label"] = "Al día"

    return RedirectResponse(f"/servicios/{servicio_id}", status_code=status.HTTP_303_SEE_OTHER)


# ----------------------------------------------------------------------
# Módulo de Clima y Alertas Agronómicas por Geolocalización de Campo
# ----------------------------------------------------------------------


@app.get("/clima/campos", response_class=HTMLResponse)
def clima_resumen_campos(request: Request):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse("/login?next=/clima/campos", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    campos_clima = []
    for c in CAMPOS_STORE:
        weather_info = get_weather_for_location(
            c.get("latitud"),
            c.get("longitud"),
            c.get("localidad_referencia", "Laguna Larga, Córdoba"),
        )
        campos_clima.append({"campo": c, "weather": weather_info})

    return templates.TemplateResponse(
        "clima_resumen_campos.html",
        {"request": request, "user": user, "campo_activo": campo_activo, "campos_clima": campos_clima},
    )


@app.get("/clima/campos/{campo_id}", response_class=HTMLResponse)
def clima_semanal_campo(request: Request, campo_id: str):
    user = get_current_user_from_session(request)
    if not user:
        return RedirectResponse(f"/login?next=/clima/campos/{campo_id}", status_code=status.HTTP_303_SEE_OTHER)

    campo_activo = get_campo_activo(request)
    campo = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
    if not campo:
        return RedirectResponse("/clima/campos", status_code=status.HTTP_303_SEE_OTHER)

    weather_info = get_weather_for_location(
        campo.get("latitud"),
        campo.get("longitud"),
        campo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )

    return templates.TemplateResponse(
        "clima_semanal_campo.html",
        {"request": request, "user": user, "campo_activo": campo_activo, "campo": campo, "weather": weather_info},
    )


# ----------------------------------------------------------------------
# Endpoints API JSON para PWA Offline-First & Sincronización (/campo)
# ----------------------------------------------------------------------

PROCESSED_ACTION_IDS = set()


@app.get("/api/campo/estado")
def get_campo_estado_api(request: Request):
    """Endpoint JSON para hidratación de IndexedDB en Modo Campo PWA."""
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=status.HTTP_401_UNAUTHORIZED)

    campo_activo = get_campo_activo(request)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )
    lotes_campo_activo = [l for l in LOTES_STORE if l["campo_id"] == campo_activo["id"]]
    tareas_campo = [t for t in TAREAS_STORE if t["campo_id"] == campo_activo["id"]]

    return JSONResponse({
        "user": {"id": user["id"], "nombre": user["nombre"], "email": user["email"]},
        "campo_activo": campo_activo,
        "campos": CAMPOS_STORE,
        "lotes_campo": lotes_campo_activo,
        "weather": weather_data,
        "tareas": tareas_campo,
    })


@app.post("/api/campo/sync-actions")
async def sync_campo_actions_api(request: Request):
    """
    Endpoint JSON para procesar acciones diferidas acumuladas en IndexedDB (offline_queue).
    Soporta idempotencia por client_action_id para prevenir duplicados.
    """
    user = get_current_user_from_session(request)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=status.HTTP_401_UNAUTHORIZED)

    data = await request.json()
    actions = data.get("actions", [])
    processed_count = 0

    for act in actions:
        action_id = act.get("client_action_id")
        if not action_id or action_id in PROCESSED_ACTION_IDS:
            continue

        tipo = act.get("tipo")
        payload = act.get("payload", {})
        campo_id = payload.get("campo_id") or request.session.get("campo_activo_id", "campo-001")
        campo_sel = next((c for c in CAMPOS_STORE if c["id"] == campo_id), None)
        campo_nombre = campo_sel["nombre"] if campo_sel else "Campo General"

        if tipo == "registrar_lluvia":
            mm = payload.get("milimetros", 0.0)
            lote_id = payload.get("lote_id")
            lote_sel = next((l for l in LOTES_STORE if l["id"] == lote_id), None) if lote_id else None
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
            lote_sel = next((l for l in LOTES_STORE if l["id"] == lote_id), None) if lote_id else None
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
            lote_sel = next((l for l in LOTES_STORE if l["id"] == lote_id), None) if lote_id else None
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

    campo_activo = get_campo_activo(request)
    weather_data = get_weather_for_location(
        campo_activo.get("latitud", -31.7766),
        campo_activo.get("longitud", -63.8011),
        campo_activo.get("localidad_referencia", "Laguna Larga, Córdoba"),
    )
    lotes_campo_activo = [l for l in LOTES_STORE if l["campo_id"] == campo_activo["id"]]
    tareas_campo = [t for t in TAREAS_STORE if t["campo_id"] == campo_activo["id"]]

    return JSONResponse({
        "success": True,
        "processed_count": processed_count,
        "state": {
            "user": {"id": user["id"], "nombre": user["nombre"], "email": user["email"]},
            "campo_activo": campo_activo,
            "campos": CAMPOS_STORE,
            "lotes_campo": lotes_campo_activo,
            "weather": weather_data,
            "tareas": tareas_campo,
        }
    })

