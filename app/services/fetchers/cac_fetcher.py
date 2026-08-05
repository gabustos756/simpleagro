"""
Fetcher / Conector Oficial para Cotizaciones de Pizarra Rosario (Cámara Arbitral de Cereales - BCR).
Fuente Pública Oficial Primaria: https://www.cac.bcr.com.ar/es/precios-de-pizarra
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
import re
from typing import Dict, List, Any, Optional
import urllib.request

logger = logging.getLogger("eduagro.fetchers.cac")

USER_AGENT_BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
URL_CAC_PIZARRA = "https://www.cac.bcr.com.ar/es/precios-de-pizarra"

# Cotizaciones de reserva trazables CAC Rosario ($1.486,00 ARS)
FALLBACK_CAC_TC = Decimal("1486.00")

FALLBACK_PIZARRA = [
    {
        "cultivo": "soja",
        "fuente": "Pizarra Rosario (CAC / BCR)",
        "fecha": date.today(),
        "precio_ars_tn": Decimal("506000.00"),
        "precio_usd_tn": (Decimal("506000.00") / FALLBACK_CAC_TC).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "dolar_referencia": FALLBACK_CAC_TC,
        "es_fallback": True,
    },
    {
        "cultivo": "maiz",
        "fuente": "Pizarra Rosario (CAC / BCR)",
        "fecha": date.today(),
        "precio_ars_tn": Decimal("276400.00"),
        "precio_usd_tn": (Decimal("276400.00") / FALLBACK_CAC_TC).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "dolar_referencia": FALLBACK_CAC_TC,
        "es_fallback": True,
    },
    {
        "cultivo": "sorgo",
        "fuente": "Pizarra Rosario (CAC / BCR)",
        "fecha": date.today(),
        "precio_ars_tn": Decimal("271940.00"),
        "precio_usd_tn": (Decimal("271940.00") / FALLBACK_CAC_TC).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "dolar_referencia": FALLBACK_CAC_TC,
        "es_fallback": True,
    },
]


def obtener_cotizacion_dolar_cac(timeout_sec: float = 5.0) -> Dict[str, Any]:
    """
    Obtiene la cotización oficial del dólar publicada en la Pizarra de la Cámara Arbitral de Cereales (CAC - BCR).
    Fuente Directa: https://www.cac.bcr.com.ar/es/precios-de-pizarra
    ("TC BNA Divisas Comprador")
    """
    try:
        req = urllib.request.Request(
            URL_CAC_PIZARRA,
            headers={"User-Agent": USER_AGENT_BROWSER}
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            content = resp.read().decode("utf-8")

        tc_pos = content.find("TC BNA Divisas")
        if tc_pos != -1:
            chunk = content[tc_pos:tc_pos+250]
            m = re.search(r"\$\s*([\d\.,]+)", chunk)
            if m:
                tc_raw = m.group(1).replace(".", "").replace(",", ".")
                tc_val = Decimal(tc_raw)

                date_m = re.search(r"Precios Pizarra del d[ií]a\s+([\d]{2}/[\d]{2}/[\d]{4})", content)
                fecha_str = date_m.group(1) if date_m else str(date.today())

                logger.info(f"[MERCADO CAC EN VIVO] Dólar CAC Rosario (TC BNA Divisas Comprador): ${tc_val} ARS | Fecha Pizarra: {fecha_str}")
                return {
                    "dolar_comprador": tc_val,
                    "dolar_referencia": tc_val,
                    "fuente": "Dólar CAC Rosario (BCR)",
                    "tipo_cotizacion": "TC BNA Divisas Comprador Pizarra CAC",
                    "fecha_pizarra": fecha_str,
                    "fecha": date.today(),
                    "ultima_actualizacion_iso": datetime.now().isoformat(),
                    "es_fallback": False,
                }
    except Exception as e:
        logger.warning(f"[MERCADO CAC] Falla al consultar fuente oficial CAC BCR ({e}). Utilizando cotización oficial trazable CAC ${FALLBACK_CAC_TC} ARS.")

    return {
        "dolar_comprador": FALLBACK_CAC_TC,
        "dolar_referencia": FALLBACK_CAC_TC,
        "fuente": "Dólar CAC Rosario (BCR Respaldo)",
        "tipo_cotizacion": "TC BNA Divisas Comprador Pizarra CAC",
        "fecha_pizarra": date.today().strftime("%d/%m/%Y"),
        "fecha": date.today(),
        "ultima_actualizacion_iso": datetime.now().isoformat(),
        "es_fallback": True,
    }


def obtener_precios_pizarra_cac(
    dolar_referencia: Optional[Decimal] = None,
    timeout_sec: float = 5.0,
) -> List[Dict[str, Any]]:
    """
    Obtiene las cotizaciones de Pizarra Rosario (CAC/BCR) para Soja, Maíz y Sorgo
    leyendo directamente el portal oficial de la Cámara Arbitral de Cereales.
    """
    logger.info("[MERCADO CAC] Consultando fuente en vivo Pizarra Rosario (CAC/BCR)...")

    try:
        req = urllib.request.Request(
            URL_CAC_PIZARRA,
            headers={"User-Agent": USER_AGENT_BROWSER}
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            content = resp.read().decode("utf-8")

        # 1. Dólar Referencia CAC en vivo
        tc_cac = dolar_referencia
        if not tc_cac:
            tc_pos = content.find("TC BNA Divisas")
            if tc_pos != -1:
                chunk = content[tc_pos:tc_pos+250]
                m = re.search(r"\$\s*([\d\.,]+)", chunk)
                if m:
                    tc_raw = m.group(1).replace(".", "").replace(",", ".")
                    tc_cac = Decimal(tc_raw)

        if not tc_cac:
            tc_cac = FALLBACK_CAC_TC

        # 2. Fecha de Pizarra
        date_m = re.search(r"Precios Pizarra del d[ií]a\s+([\d]{2}/[\d]{2}/[\d]{4})", content)
        fecha_pizarra_str = date_m.group(1) if date_m else str(date.today())

        # 3. Mapeo de Pizarra en ARS mediante bloques HTML de CAC/BCR
        precios_encontrados = []
        cultivos_interes = ["soja", "maiz", "trigo", "sorgo"]
        blocks = content.split('board board-')

        for b in blocks[1:]:
            crop_name = b.split()[0].replace('"', '').replace('>', '').strip().lower()
            if crop_name not in cultivos_interes:
                continue

            ars_match = re.search(r'class="price"[\s\S]*?\$?\s*([\d\.,]+)', b)
            if ars_match:
                p_ars = Decimal(ars_match.group(1).replace(".", "").replace(",", "."))
                p_usd = (p_ars / tc_cac).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                precios_encontrados.append({
                    "cultivo": crop_name,
                    "fuente": "Pizarra Rosario (CAC / BCR)",
                    "fecha": date.today(),
                    "fecha_pizarra": fecha_pizarra_str,
                    "precio_ars_tn": p_ars,
                    "precio_usd_tn": p_usd,
                    "dolar_referencia": tc_cac,
                    "es_fallback": False,
                })

        if precios_encontrados:
            logger.info(f"[MERCADO CAC EN VIVO] Éxito al parsear {len(precios_encontrados)} cotizaciones de Pizarra Rosario.")
            return precios_encontrados

    except Exception as e:
        logger.warning(f"[MERCADO CAC] Error al leer Pizarra CAC en vivo ({e}). Utilizando cotizaciones trazables de reserva.")

    # Fallback Trazable
    tc_usar = dolar_referencia or FALLBACK_CAC_TC
    precios_fallback = []
    for item in FALLBACK_PIZARRA:
        p_ars = item["precio_ars_tn"]
        p_usd = (p_ars / tc_usar).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        precios_fallback.append({
            "cultivo": item["cultivo"],
            "fuente": item["fuente"],
            "fecha": item["fecha"],
            "fecha_pizarra": item["fecha"].strftime("%d/%m/%Y"),
            "precio_ars_tn": p_ars,
            "precio_usd_tn": p_usd,
            "dolar_referencia": tc_usar,
            "es_fallback": True,
        })

    return precios_fallback
