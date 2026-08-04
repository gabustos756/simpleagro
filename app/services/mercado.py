import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PrecioMercadoCache
from app.services.comercial import normalizar_texto
from app.services.fetchers import (
    obtener_cotizacion_dolar,
    obtener_cotizacion_dolar_cac,
    obtener_precios_sagyp,
    obtener_precios_pizarra_cac,
)

logger = logging.getLogger("eduagro.mercado")

# Precios fallback demo por defecto alineados con CAC/BCR (Soja, Maíz y Sorgo)
DEMO_PRECIOS_MERCADO = [
    {
        "cultivo": "soja",
        "fuente": "Pizarra Rosario (CAC / BCR)",
        "fecha": date.today(),
        "precio_ars_tn": Decimal("506000.00"),
        "precio_usd_tn": Decimal("340.51"),
        "dolar_referencia": Decimal("1486.00"),
    },
    {
        "cultivo": "maiz",
        "fuente": "Pizarra Rosario (CAC / BCR)",
        "fecha": date.today(),
        "precio_ars_tn": Decimal("276400.00"),
        "precio_usd_tn": Decimal("186.00"),
        "dolar_referencia": Decimal("1486.00"),
    },
    {
        "cultivo": "sorgo",
        "fuente": "Pizarra Rosario (CAC / BCR)",
        "fecha": date.today(),
        "precio_ars_tn": Decimal("271940.00"),
        "precio_usd_tn": Decimal("183.00"),
        "dolar_referencia": Decimal("1486.00"),
    },
]


async def actualizar_precios_mercado(
    db: AsyncSession,
    usar_fetcher_real: bool = True,
    fuente_preferida: str = "pizarra",
) -> List[Dict[str, Any]]:
    """
    Actualiza la tabla de caché `PrecioMercadoCache` consumiendo los fetchers HTTP reales.
    """
    logger.info("[MERCADO SERVICIO] Iniciando actualización de precios con fetchers HTTP...")
    registros_guardados = []

    try:
        data_dolar = obtener_cotizacion_dolar_cac()
        dolar_ref = data_dolar.get("dolar_comprador", Decimal("1486.00"))
    except Exception as e:
        logger.warning(f"[MERCADO SERVICIO] Falla al obtener cotización CAC Rosario ({e}). Usando dólar BNA secundario.")
        try:
            data_dolar = obtener_cotizacion_dolar()
            dolar_ref = data_dolar.get("dolar_comprador", Decimal("1486.00"))
        except Exception:
            dolar_ref = Decimal("1486.00")

    precios_obtenidos = []
    if usar_fetcher_real:
        try:
            if fuente_preferida == "sagyp":
                precios_obtenidos = obtener_precios_sagyp(dolar_referencia=dolar_ref)
            else:
                precios_obtenidos = obtener_precios_pizarra_cac(dolar_referencia=dolar_ref)
        except Exception as e:
            logger.warning(f"[MERCADO SERVICIO] Falla en fetcher real ({e}). Usando datos demo de reserva.")
            precios_obtenidos = []

    if not precios_obtenidos:
        precios_obtenidos = DEMO_PRECIOS_MERCADO

    for p_item in precios_obtenidos:
        cult_norm = normalizar_texto(p_item["cultivo"])
        fecha_ref = p_item.get("fecha", date.today())
        p_ars = Decimal(str(p_item["precio_ars_tn"]))
        p_usd = Decimal(str(p_item["precio_usd_tn"]))
        tc_usado = Decimal(str(p_item.get("dolar_referencia", dolar_ref)))
        fuente_nombre = p_item.get("fuente", "Pizarra Rosario (CAC / BCR)")

        stmt = select(PrecioMercadoCache).where(
            func.lower(PrecioMercadoCache.cultivo) == cult_norm,
            PrecioMercadoCache.fuente == fuente_nombre,
            PrecioMercadoCache.fecha == fecha_ref,
        )
        res = await db.execute(stmt)
        existente = res.scalars().first()

        if existente:
            existente.precio_usd_tn = p_usd
            existente.precio_ars_tn = p_ars
            existente.dolar_referencia = tc_usado
            existente.fuente = fuente_nombre
            reg_id = str(existente.id)
            accion = "Actualización"
        else:
            n_id = uuid.uuid4()
            nuevo = PrecioMercadoCache(
                id=n_id,
                cultivo=cult_norm,
                fuente=fuente_nombre,
                fecha=fecha_ref,
                precio_usd_tn=p_usd,
                precio_ars_tn=p_ars,
                dolar_referencia=tc_usado,
            )
            db.add(nuevo)
            reg_id = str(n_id)
            accion = "Inserción"

        logger.info(
            f"[MERCADO CACHÉ] {accion} DB -> ID={reg_id} | Cultivo={cult_norm.upper()} | "
            f"Fuente={fuente_nombre} | ARS/Tn=${p_ars} | TC_BNA_Comprador=${tc_usado} | "
            f"USD/Tn=${p_usd} | Fecha={fecha_ref}"
        )

        registros_guardados.append({
            "id": reg_id,
            "cultivo": cult_norm,
            "fuente": fuente_nombre,
            "fecha": str(fecha_ref),
            "precio_usd_tn": float(p_usd),
            "precio_ars_tn": float(p_ars),
            "dolar_referencia": float(tc_usado),
        })

    await db.commit()
    logger.info(f"[MERCADO SERVICIO] Proceso finalizado. {len(registros_guardados)} cotizaciones guardadas en PostgreSQL.")
    return registros_guardados


async def obtener_precio_mercado_vigente(
    db: AsyncSession,
    cultivo: str,
) -> Optional[PrecioMercadoCache]:
    """
    Obtiene la última cotización vigente en caché local para un cultivo dado.
    """
    cult_norm = normalizar_texto(cultivo)

    stmt = (
        select(PrecioMercadoCache)
        .where(func.lower(PrecioMercadoCache.cultivo) == cult_norm)
        .order_by(PrecioMercadoCache.fecha.desc(), PrecioMercadoCache.creado_en.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    registro = res.scalars().first()

    if not registro or registro.fecha < date.today():
        logger.info(f"[MERCADO CACHÉ] Cotización para {cult_norm} no existente o de fecha anterior. Ejecutando refresh en vivo...")
        await actualizar_precios_mercado(db, usar_fetcher_real=True)
        res = await db.execute(stmt)
        registro = res.scalars().first()

    return registro


async def obtener_historico_precios_mercado(
    db: AsyncSession,
    cultivo: str,
    limit: int = 7,
) -> List[Dict[str, Any]]:
    """
    Obtiene los últimos N registros históricos almacenados en `PrecioMercadoCache`
    para un cultivo dado, ordenados por fecha descendente, calculando la variación diaria
    en USD/Tn y ARS/Tn respecto a la jornada anterior.
    
    Returns:
        List[Dict[str, Any]]: Lista de registros históricos enriquecidos con variación y tendencia.
    """
    cult_norm = normalizar_texto(cultivo)

    stmt = (
        select(PrecioMercadoCache)
        .where(func.lower(PrecioMercadoCache.cultivo) == cult_norm)
        .order_by(PrecioMercadoCache.fecha.desc(), PrecioMercadoCache.creado_en.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    registros_desc = res.scalars().all()

    if not registros_desc:
        return []

    # Invertir para calcular variaciones en orden cronológico (antiguo -> reciente)
    registros_asc = list(reversed(registros_desc))

    historico_cronologico = []
    precio_usd_prev = None
    precio_ars_prev = None

    for idx, r in enumerate(registros_asc):
        p_usd = float(r.precio_usd_tn)
        p_ars = float(r.precio_ars_tn) if r.precio_ars_tn else 0.0

        if idx > 0 and precio_usd_prev is not None and precio_usd_prev > 0:
            var_usd = round(p_usd - precio_usd_prev, 2)
            var_pct_usd = round(((p_usd - precio_usd_prev) / precio_usd_prev) * 100.0, 2)
        else:
            var_usd = 0.0
            var_pct_usd = 0.0

        if idx > 0 and precio_ars_prev is not None and precio_ars_prev > 0:
            var_ars = round(p_ars - precio_ars_prev, 2)
        else:
            var_ars = 0.0

        if var_usd > 0:
            tendencia = "suba"
        elif var_usd < 0:
            tendencia = "baja"
        else:
            tendencia = "neutro"

        precio_usd_prev = p_usd
        precio_ars_prev = p_ars

        historico_cronologico.append({
            "id": str(r.id),
            "cultivo": r.cultivo.capitalize(),
            "fuente": r.fuente,
            "fecha": str(r.fecha),
            "precio_usd_tn": p_usd,
            "precio_ars_tn": p_ars,
            "dolar_referencia": float(r.dolar_referencia) if r.dolar_referencia else None,
            "var_usd": var_usd,
            "var_pct_usd": var_pct_usd,
            "var_ars": var_ars,
            "tendencia": tendencia,
        })

    # Devolver orden descendente (más reciente arriba) para mostrar en UI
    return list(reversed(historico_cronologico))


MAPA_FUENTES_URL = {
    "Pizarra Rosario (CAC / BCR)": "https://www.cac.bcr.com.ar/es/precios-de-pizarra",
    "SAGyP / FAS Teórico Oficial": "https://www.magyp.gob.ar/sitio/areas/ss_mercados_agropecuarios/precios/",
    "Dólar BNA / Bluelytics API": "https://www.bna.com.ar/Personas",
}


async def obtener_snapshot_precios_mercado(
    db: AsyncSession,
    cultivos: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Obtiene el snapshot con el registro más reciente por cultivo (Soja, Maíz, Sorgo),
    enriquecido con la variación del precio respecto a la jornada anterior.
    Si la cotización almacenada es de una fecha anterior, ejecuta refresh en vivo.
    """
    if cultivos is None:
        cultivos = ["soja", "maiz", "sorgo"]

    hoy_str = str(date.today())
    snapshot = []

    # Chequeo previo de obsolescencia en DB
    historico_test = await obtener_historico_precios_mercado(db, cultivo=cultivos[0], limit=1)
    if not historico_test or (historico_test and historico_test[0]["fecha"] < hoy_str):
        f_previa = historico_test[0]['fecha'] if historico_test else 'vacía'
        logger.info(f"[MERCADO SNAPSHOT] Cotización en DB obsoleta ({f_previa}). Ejecutando refresh automático para fecha {hoy_str}...")
        try:
            await actualizar_precios_mercado(db, usar_fetcher_real=True)
        except Exception as e:
            logger.warning(f"[MERCADO SNAPSHOT] Error durante auto-refresh de cotizaciones ({e}). Servir datos almacenados.")

    for c in cultivos:
        historico_c = await obtener_historico_precios_mercado(db, cultivo=c, limit=2)
        if historico_c:
            reciente = historico_c[0]
            f_nombre = reciente.get("fuente", "Pizarra Rosario (CAC / BCR)")
            reciente["url_fuente"] = MAPA_FUENTES_URL.get(f_nombre, "https://www.bcr.com.ar")
            reciente["es_hoy"] = (reciente["fecha"] == hoy_str)
            snapshot.append(reciente)
        else:
            demo_item = next((dp for dp in DEMO_PRECIOS_MERCADO if dp["cultivo"].lower() == c.lower()), None)
            if demo_item:
                f_nombre = demo_item["fuente"]
                snapshot.append({
                    "id": "demo",
                    "cultivo": demo_item["cultivo"].capitalize(),
                    "fuente": f_nombre,
                    "url_fuente": MAPA_FUENTES_URL.get(f_nombre, "https://www.bcr.com.ar"),
                    "fecha": str(demo_item["fecha"]),
                    "precio_usd_tn": float(demo_item["precio_usd_tn"]),
                    "precio_ars_tn": float(demo_item["precio_ars_tn"]),
                    "dolar_referencia": float(demo_item["dolar_referencia"]),
                    "var_usd": 0.0,
                    "var_pct_usd": 0.0,
                    "var_ars": 0.0,
                    "tendencia": "neutro",
                    "es_hoy": True,
                })

    return snapshot


def generar_sparkline_data(
    historico_desc: List[Dict[str, Any]],
    width: int = 500,
    height: int = 70,
    padding: int = 12,
) -> Dict[str, Any]:
    """
    Genera coordenadas SVG, caminos de trazado, área de degradado y métricas de tendencia
    global para ser renderizados como un mini gráfico Sparkline de precios en el cliente.
    """
    if not historico_desc:
        return {
            "points": [],
            "svg_path": "",
            "svg_area_path": "",
            "tendencia_global": "neutro",
            "var_total_usd": 0.0,
            "ultimo_precio_usd": 0.0,
            "primer_precio_usd": 0.0,
            "min_usd": 0.0,
            "max_usd": 0.0,
        }

    # Invertir a orden cronológico (antiguo a la izquierda -> reciente a la derecha)
    asc = list(reversed(historico_desc))
    val_usd = [float(item["precio_usd_tn"]) for item in asc]

    min_v = min(val_usd)
    max_v = max(val_usd)
    diff = max_v - min_v if max_v != min_v else 1.0

    points = []
    n = len(asc)
    w_effective = width - 2 * padding
    h_effective = height - 2 * padding

    for i, item in enumerate(asc):
        p_val = float(item["precio_usd_tn"])
        x = round(padding + (i * w_effective / (n - 1 if n > 1 else 1)), 1)
        y = round((height - padding) - ((p_val - min_v) / diff * h_effective), 1)
        points.append({
            "x": x,
            "y": y,
            "fecha": item["fecha"],
            "precio_usd_tn": p_val,
            "precio_ars_tn": float(item["precio_ars_tn"]) if item.get("precio_ars_tn") else 0.0,
        })

    path_cmds = [f"M {points[0]['x']} {points[0]['y']}"]
    for p in points[1:]:
        path_cmds.append(f"L {p['x']} {p['y']}")

    svg_path = " ".join(path_cmds)
    first_x = points[0]["x"]
    last_x = points[-1]["x"]
    svg_area_path = f"{svg_path} L {last_x} {height} L {first_x} {height} Z"

    var_total_usd = round(val_usd[-1] - val_usd[0], 2)
    if var_total_usd > 0:
        tendencia_global = "suba"
    elif var_total_usd < 0:
        tendencia_global = "baja"
    else:
        tendencia_global = "neutro"

    return {
        "points": points,
        "svg_path": svg_path,
        "svg_area_path": svg_area_path,
        "tendencia_global": tendencia_global,
        "var_total_usd": var_total_usd,
        "ultimo_precio_usd": val_usd[-1],
        "primer_precio_usd": val_usd[0],
        "min_usd": min_v,
        "max_usd": max_v,
    }


def obtener_comparativa_futuros_mercado(
    snapshot_fisico: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Combina las cotizaciones de referencia de futuros (Matba Rofex) para Soja y Maíz
    con los precios físicos del día en caché local, calculando la brecha/spread en USD/Tn.
    """
    from app.services.fetchers import obtener_futuros_matba_rofex
    futuros_raw = obtener_futuros_matba_rofex()

    mapa_fisico = {
        item["cultivo"].lower(): float(item["precio_usd_tn"])
        for item in snapshot_fisico
    }

    resultado = []
    for item in futuros_raw:
        c_key = item["cultivo"].lower()
        p_fisico_usd = mapa_fisico.get(c_key, 0.0)
        p_futuro_usd = float(item["precio_usd_tn"])

        if p_fisico_usd > 0:
            spread_usd = round(p_futuro_usd - p_fisico_usd, 2)
            spread_pct = round(((p_futuro_usd - p_fisico_usd) / p_fisico_usd) * 100.0, 2)
        else:
            spread_usd = 0.0
            spread_pct = 0.0

        if spread_usd > 0:
            relacion = "pase"
        elif spread_usd < 0:
            relacion = "descuento"
        else:
            relacion = "paridad"

        pos_label = "Posición Cercana" if item["posicion_tipo"] == "cercana" else "Posición Cosecha"

        resultado.append({
            "cultivo": item["cultivo"].capitalize(),
            "posicion_tipo": item["posicion_tipo"],
            "posicion_label": pos_label,
            "contrato": item["contrato"],
            "mercado": item["mercado"],
            "precio_futuro_usd": p_futuro_usd,
            "precio_fisico_usd": p_fisico_usd,
            "spread_usd": spread_usd,
            "spread_pct": spread_pct,
            "relacion": relacion,
            "url_fuente": item.get("url_fuente", "https://www.matbarofex.com.ar"),
            "fecha": str(item.get("fecha", date.today())),
        })

    return resultado



