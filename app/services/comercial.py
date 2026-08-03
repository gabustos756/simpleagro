from decimal import Decimal
from typing import Dict, Any, Optional
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import TipoPrecioEnum, UbicacionStockEnum
from app.models import Campania, CompromisoGrano, ContratoVentaGrano, Lote, StockGrano


def normalizar_texto(texto: Optional[str]) -> str:
    """Remueve acentos y convierte a minusculas para comparaciones insensibles a tildes."""
    if not texto:
        return ""
    res = texto.strip().lower()
    reemplazos = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }
    for orig, dest in reemplazos.items():
        res = res.replace(orig, dest)
    return res


async def obtener_campania_activa_para_cliente(
    db: AsyncSession, cliente_id: uuid.UUID
) -> Optional[Campania]:
    """Retorna la campaña activa para un cliente o la más reciente si no hay activa."""
    stmt = (
        select(Campania)
        .where(Campania.cliente_id == cliente_id, Campania.activa.is_(True))
        .order_by(Campania.fecha_inicio.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    campania = result.scalars().first()

    if not campania:
        stmt_fallback = (
            select(Campania)
            .where(Campania.cliente_id == cliente_id)
            .order_by(Campania.fecha_inicio.desc())
            .limit(1)
        )
        res_fb = await db.execute(stmt_fallback)
        campania = res_fb.scalars().first()

    return campania


async def calcular_posicion_comercial(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    campania_id: uuid.UUID,
    cultivo: str,
) -> Dict[str, Any]:
    """Calcula la posición comercial completa (Producción, Ventas, Stock, Compromisos y Libres)

    para un cliente, campaña y cultivo (ej. 'soja' o 'maiz').
    """
    cultivo_norm = normalizar_texto(cultivo)

    # 1. Obtener Lotes de la campaña/cliente para el cultivo seleccionado
    stmt_lotes = select(Lote).where(Lote.cliente_id == cliente_id)
    if campania_id:
        stmt_lotes = stmt_lotes.where(
            (Lote.campania_id == campania_id) | (Lote.campania_id.is_(None))
        )

    res_lotes = await db.execute(stmt_lotes)
    lotes_raw = res_lotes.scalars().all()

    produccion_total_tn = Decimal("0.0")

    # Filtrar lotes en memoria por normalización de acentos
    lotes_filtrados = [
        l for l in lotes_raw if cultivo_norm in normalizar_texto(l.cultivo_actual)
    ]

    if lotes_filtrados:
        for lote in lotes_filtrados:
            sup_ha = Decimal(str(lote.superficie_productiva_ha or 0.0))
            if lote.qq_ha_real is not None and lote.qq_ha_real > 0:
                rinde_qq = Decimal(str(lote.qq_ha_real))
            elif lote.qq_ha_estimado is not None and lote.qq_ha_estimado > 0:
                rinde_qq = Decimal(str(lote.qq_ha_estimado))
            else:
                rinde_qq = Decimal("0.0")

            prod_lote_tn = (sup_ha * rinde_qq) / Decimal("10.0")
            produccion_total_tn += prod_lote_tn
    else:
        # Fallback a datos demo si la base de datos no tiene Lotes persistidos aún
        from app.seed import DEMO_LOTES

        for l_dict in DEMO_LOTES:
            cult_actual = normalizar_texto(l_dict.get("cultivo_actual"))
            cult_planif = normalizar_texto(l_dict.get("cultivo_planificado"))
            if cultivo_norm in cult_actual or cultivo_norm in cult_planif:
                sup_ha = Decimal(str(l_dict.get("superficie_productiva_ha", 0.0)))
                qq_real = l_dict.get("qq_ha_real")
                qq_est = l_dict.get("qq_ha_estimado")

                if qq_real is not None and float(qq_real) > 0:
                    rinde_qq = Decimal(str(qq_real))
                elif qq_est is not None and float(qq_est) > 0:
                    rinde_qq = Decimal(str(qq_est))
                else:
                    rinde_qq = Decimal("0.0")

                prod_lote_tn = (sup_ha * rinde_qq) / Decimal("10.0")
                produccion_total_tn += prod_lote_tn

    # 2. Obtener Contratos de Venta de Granos (Fijo vs A Fijar)
    stmt_contratos = select(ContratoVentaGrano).where(
        ContratoVentaGrano.cliente_id == cliente_id,
        ContratoVentaGrano.campania_id == campania_id,
    )
    res_contratos = await db.execute(stmt_contratos)
    contratos_raw = res_contratos.scalars().all()

    contratos = [
        c for c in contratos_raw if normalizar_texto(c.cultivo) == cultivo_norm
    ]

    tn_vendidas_precio_fijo = Decimal("0.0")
    tn_vendidas_a_fijar = Decimal("0.0")

    for contrato in contratos:
        tn = Decimal(str(contrato.toneladas or 0.0))
        if contrato.tipo_precio == TipoPrecioEnum.FIJO:
            tn_vendidas_precio_fijo += tn
        elif contrato.tipo_precio == TipoPrecioEnum.A_FIJAR:
            tn_vendidas_a_fijar += tn

    # 3. Obtener Stock Físico (Silo Bolsa vs Acopio)
    stmt_stock = select(StockGrano).where(
        StockGrano.cliente_id == cliente_id,
        StockGrano.campania_id == campania_id,
    )
    res_stock = await db.execute(stmt_stock)
    stocks_raw = res_stock.scalars().all()

    stocks = [s for s in stocks_raw if normalizar_texto(s.cultivo) == cultivo_norm]

    tn_stock_silo_bolsa = Decimal("0.0")
    tn_stock_acopio = Decimal("0.0")

    for st in stocks:
        tn = Decimal(str(st.toneladas_almacenadas or 0.0))
        if st.ubicacion_tipo == UbicacionStockEnum.SILO_BOLSA:
            tn_stock_silo_bolsa += tn
        else:
            tn_stock_acopio += tn

    tn_stock_total = tn_stock_silo_bolsa + tn_stock_acopio

    # 4. Obtener Compromisos (Alquileres / Canjes pendientes)
    stmt_comp = select(CompromisoGrano).where(
        CompromisoGrano.cliente_id == cliente_id,
        CompromisoGrano.campania_id == campania_id,
        CompromisoGrano.cumplido.is_(False),
    )
    res_comp = await db.execute(stmt_comp)
    comp_raw = res_comp.scalars().all()

    compromisos = [k for k in comp_raw if normalizar_texto(k.cultivo) == cultivo_norm]

    tn_comprometidas = Decimal("0.0")
    for comp in compromisos:
        tn_comprometidas += Decimal(str(comp.toneladas_comprometidas or 0.0))

    # 5. Calcular Toneladas Libres de Riesgo
    tn_libres = produccion_total_tn - (
        tn_vendidas_precio_fijo + tn_vendidas_a_fijar + tn_comprometidas
    )

    # 6. Calcular Porcentaje de Cobertura Comercial
    if produccion_total_tn > Decimal("0.0"):
        porcentaje_cobertura = (
            (tn_vendidas_precio_fijo + tn_comprometidas) / produccion_total_tn
        ) * Decimal("100.0")
    else:
        porcentaje_cobertura = Decimal("0.0")

    # 7. Obtener Cotización Vigente y Valorización del Stock Libre (Mercado V1)
    from app.services.mercado import obtener_precio_mercado_vigente

    precio_mercado_obj = await obtener_precio_mercado_vigente(db, cultivo_norm)
    if precio_mercado_obj:
        precio_mercado_usd_tn = Decimal(str(precio_mercado_obj.precio_usd_tn)).quantize(Decimal("0.01"))
        precio_mercado_ars_tn = Decimal(str(precio_mercado_obj.precio_ars_tn)).quantize(Decimal("0.01")) if precio_mercado_obj.precio_ars_tn else None
        dolar_referencia = Decimal(str(precio_mercado_obj.dolar_referencia)).quantize(Decimal("0.01")) if precio_mercado_obj.dolar_referencia else None
        fuente_precio_mercado = precio_mercado_obj.fuente
        fecha_precio_mercado = str(precio_mercado_obj.fecha)

        if tn_libres > Decimal("0.0"):
            valorizacion_stock_libre_usd = (tn_libres * precio_mercado_usd_tn).quantize(Decimal("0.01"))
            valorizacion_stock_libre_ars = (tn_libres * precio_mercado_ars_tn).quantize(Decimal("0.01")) if precio_mercado_ars_tn else None
        else:
            valorizacion_stock_libre_usd = Decimal("0.00")
            valorizacion_stock_libre_ars = Decimal("0.00")
    else:
        precio_mercado_usd_tn = None
        precio_mercado_ars_tn = None
        dolar_referencia = None
        fuente_precio_mercado = None
        fecha_precio_mercado = None
        valorizacion_stock_libre_usd = None
        valorizacion_stock_libre_ars = None

    return {
        "cultivo": cultivo_norm,
        "produccion_total_tn": produccion_total_tn.quantize(Decimal("0.01")),
        "tn_vendidas_precio_fijo": tn_vendidas_precio_fijo.quantize(Decimal("0.01")),
        "tn_vendidas_a_fijar": tn_vendidas_a_fijar.quantize(Decimal("0.01")),
        "tn_comprometidas": tn_comprometidas.quantize(Decimal("0.01")),
        "tn_libres": tn_libres.quantize(Decimal("0.01")),
        "porcentaje_cobertura": porcentaje_cobertura.quantize(Decimal("0.01")),
        "tn_stock_silo_bolsa": tn_stock_silo_bolsa.quantize(Decimal("0.01")),
        "tn_stock_acopio": tn_stock_acopio.quantize(Decimal("0.01")),
        "tn_stock_total": tn_stock_total.quantize(Decimal("0.01")),
        # Mercado V1
        "precio_mercado_usd_tn": precio_mercado_usd_tn,
        "precio_mercado_ars_tn": precio_mercado_ars_tn,
        "dolar_referencia": dolar_referencia,
        "fuente_precio_mercado": fuente_precio_mercado,
        "fecha_precio_mercado": fecha_precio_mercado,
        "valorizacion_stock_libre_usd": valorizacion_stock_libre_usd,
        "valorizacion_stock_libre_ars": valorizacion_stock_libre_ars,
    }
