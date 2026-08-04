"""
Fetcher HTTP para Cotización del Dólar Oficial / Divisa BNA (Banco Nación Argentina).
Utilizado por la Cámara Arbitral de Cereales (CAC/BCR) para la conversión oficial ARS/Tn -> USD/Tn.
"""

from datetime import datetime, date
from decimal import Decimal
import json
import logging
from typing import Dict, Any
import urllib.request

logger = logging.getLogger("eduagro.fetchers.bna")

USER_AGENT_BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Cotización de respaldo BNA Comprador trazable
FALLBACK_DOLAR = {
    "dolar_comprador": Decimal("1477.50"),  # TC BNA Divisa Comprador al cierre de Pizarra
    "dolar_vendedor": Decimal("1511.00"),
    "dolar_promedio": Decimal("1485.50"),
    "fuente": "Dólar BNA Divisa (Respaldo)",
    "fecha": date.today(),
    "ultima_actualizacion_iso": datetime.now().isoformat(),
    "es_fallback": True,
}


def obtener_cotizacion_dolar(timeout_sec: int = 5) -> Dict[str, Any]:
    """
    Obtiene la cotización oficial del dólar divisa BNA al cierre tipo comprador.
    
    Estrategia Multi-Fuente:
    1. Primary: API Bluelytics (https://api.bluelytics.com.ar/v2/latest)
    2. Secondary: DolarAPI (https://dolarapi.com/v1/dolares/oficial)
    3. Fallback: Cotización de respaldo con flag es_fallback=True.
    """
    # 1. Intentar con Bluelytics API
    url_bluelytics = "https://api.bluelytics.com.ar/v2/latest"
    try:
        req = urllib.request.Request(
            url_bluelytics,
            headers={"User-Agent": USER_AGENT_BROWSER}
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                oficial = data.get("oficial", {})
                last_upd = data.get("last_update", datetime.now().isoformat())
                
                val_buy = Decimal(str(oficial.get("value_buy", 1477.50)))
                val_sell = Decimal(str(oficial.get("value_sell", 1511.00)))
                val_avg = Decimal(str(oficial.get("value_avg", 1485.50)))
                
                logger.info(f"[MERCADO BNA] TC BNA Comprador (Bluelytics): ${val_buy} ARS | TC Vendedor: ${val_sell} ARS | TC Promedio: ${val_avg} ARS")
                return {
                    "dolar_comprador": val_buy,
                    "dolar_vendedor": val_sell,
                    "dolar_promedio": val_avg,
                    "fuente": "Dólar BNA Divisa Comprador (API Bluelytics)",
                    "fecha": date.today(),
                    "ultima_actualizacion_iso": last_upd,
                    "es_fallback": False,
                }
    except Exception as e:
        logger.warning(f"[MERCADO BNA] Falla en Bluelytics API ({e}). Intentando DolarAPI...")

    # 2. Intentar con DolarAPI
    url_dolarapi = "https://dolarapi.com/v1/dolares/oficial"
    try:
        req = urllib.request.Request(
            url_dolarapi,
            headers={"User-Agent": USER_AGENT_BROWSER}
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                val_buy = Decimal(str(data.get("compra", 1477.50)))
                val_sell = Decimal(str(data.get("venta", 1511.00)))
                val_avg = ((val_buy + val_sell) / Decimal("2.0")).quantize(Decimal("0.01"))
                last_upd = data.get("fechaActualizacion", datetime.now().isoformat())

                logger.info(f"[MERCADO BNA] TC BNA Comprador (DolarAPI): ${val_buy} ARS | TC Vendedor: ${val_sell} ARS")
                return {
                    "dolar_comprador": val_buy,
                    "dolar_vendedor": val_sell,
                    "dolar_promedio": val_avg,
                    "fuente": "Dólar BNA Divisa Comprador (DolarAPI)",
                    "fecha": date.today(),
                    "ultima_actualizacion_iso": last_upd,
                    "es_fallback": False,
                }
    except Exception as e:
        logger.warning(f"[MERCADO BNA] Falla en DolarAPI ({e}). Usando cotización BNA comprador de respaldo ${FALLBACK_DOLAR['dolar_comprador']} ARS.")

    # 3. Respaldo Trazable
    return {
        "dolar_comprador": FALLBACK_DOLAR["dolar_comprador"],
        "dolar_vendedor": FALLBACK_DOLAR["dolar_vendedor"],
        "dolar_promedio": FALLBACK_DOLAR["dolar_promedio"],
        "fuente": FALLBACK_DOLAR["fuente"],
        "fecha": date.today(),
        "ultima_actualizacion_iso": datetime.now().isoformat(),
        "es_fallback": True,
    }
