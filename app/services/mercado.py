import logging
from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PrecioMercadoCache
from app.services.comercial import normalizar_texto
from app.services.fetchers import (
    obtener_cotizacion_dolar,
    obtener_precios_sagyp,
    obtener_precios_pizarra_cac,
)

logger = logging.getLogger("eduagro.mercado")

# Precios fallback demo por defecto alineados con CAC/BCR
DEMO_PRECIOS_MERCADO = [
    {
        "cultivo": "soja",
        "fuente": "Pizarra Rosario (CAC / BCR)",
        "fecha": date.today(),
        "precio_ars_tn": Decimal("480500.00"),
        "precio_usd_tn": Decimal("325.21"),
        "dolar_referencia": Decimal("1477.50"),
    },
    {
        "cultivo": "maiz",
        "fuente": "Pizarra Rosario (CAC / BCR)",
        "fecha": date.today(),
        "precio_ars_tn": Decimal("268900.00"),
        "precio_usd_tn": Decimal("182.00"),
        "dolar_referencia": Decimal("1477.50"),
    },
]


async def actualizar_precios_mercado(
    db: AsyncSession,
    usar_fetcher_real: bool = True,
    fuente_preferida: str = "pizarra",
) -> List[Dict[str, Any]]:
    """
    Actualiza la tabla de caché `PrecioMercadoCache` consumiendo los fetchers HTTP reales.
    
    Proceso:
      1. Consulta la cotización BNA Divisa Comprador desde `bna_fetcher`.
      2. Consulta los precios de mercado desde `cac_fetcher` o `sagyp_fetcher`.
      3. Loggea la trazabilidad completa del cálculo y los valores en ARS/USD.
      4. Inserta/actualiza los registros por `(cultivo, fuente, fecha)` en PostgreSQL.
      
    Returns:
        List[Dict[str, Any]]: Registros de cotización persistidos.
    """
    logger.info("[MERCADO SERVICIO] Iniciando actualización de precios con fetchers HTTP...")
    registros_guardados = []

    # 1. Obtenemos cotización del dólar en vivo (TC Comprador BNA)
    try:
        data_dolar = obtener_cotizacion_dolar()
        dolar_ref = data_dolar.get("dolar_comprador", Decimal("1477.50"))
    except Exception as e:
        logger.warning(f"[MERCADO SERVICIO] Falla al obtener cotización del dólar ({e}). Usando dólar comprador por defecto.")
        dolar_ref = Decimal("1477.50")

    # 2. Obtenemos cotizaciones según la fuente preferida
    precios_obtenidos = []
    if usar_fetcher_real:
        try:
            if fuente_preferida == "sagyp":
                precios_obtenidos = obtener_precios_sagyp(dolar_referencia=dolar_ref)
            else:
                # Pizarra Rosario es autocontenida: extrae ARS, USD y TC publicados por CAC
                precios_obtenidos = obtener_precios_pizarra_cac()
        except Exception as e:
            logger.warning(f"[MERCADO SERVICIO] Falla en fetcher real ({e}). Usando datos demo de reserva.")
            precios_obtenidos = []

    if not precios_obtenidos:
        precios_obtenidos = DEMO_PRECIOS_MERCADO

    # 3. Persistir en PrecioMercadoCache (Upsert por cultivo, fuente y fecha)
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

    # Si no hay registro en BD, invocar actualización automática con fetcher
    if not registro:
        await actualizar_precios_mercado(db, usar_fetcher_real=True)
        res = await db.execute(stmt)
        registro = res.scalars().first()

    return registro
