from __future__ import annotations

"""
Módulo Calculador Puro de Contratos de Arrendamiento por Campo (EduAgro V1).

Calcula la conversión determinística de quintales por hectárea (qq/ha) a quintales totales
y toneladas equivalentes (qq/10), evaluando la valorización en USD según base 'rosario'
o base 'acopio' con flete y comisión en USD/Tn.

Mantiene separación estricta: NO realiza llamadas DB ni HTTP, no muta estado.
"""

from decimal import Decimal
from datetime import date
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class LeaseCalculationResult:
    superficie_arrendada_ha: Decimal
    alquiler_qq_ha: Decimal
    qq_totales: Decimal
    toneladas_equivalentes: Decimal
    base_valorizacion: str  # 'rosario' | 'acopio'
    status_valorizacion: str  # 'complete', 'partial', 'not_evaluated'
    precio_referencia_usd_tn: Optional[Decimal] = None
    fecha_precio_referencia: Optional[date] = None
    fuente_precio: Optional[str] = None
    flete_usd_tn: Optional[Decimal] = None
    comision_usd_tn: Optional[Decimal] = None
    precio_neto_usd_tn: Optional[Decimal] = None
    valor_neto_estimado_usd: Optional[Decimal] = None
    missing_fields: List[str] = field(default_factory=list)
    observaciones_calculo: str = ""


def calculate_field_lease_terms(
    superficie_arrendada_ha: Decimal | float | int,
    alquiler_qq_ha: Decimal | float | int,
    base_valorizacion: str = "rosario",
    precio_referencia_usd_tn: Optional[Decimal | float | int] = None,
    fecha_precio_referencia: Optional[date] = None,
    fuente_precio: Optional[str] = None,
    flete_usd_tn: Optional[Decimal | float | int] = None,
    comision_usd_tn: Optional[Decimal | float | int] = None,
) -> LeaseCalculationResult:
    """
    Calcula los términos de arrendamiento en qq/ha, Tn equivalentes y valorización USD.
    """
    sup_ha = Decimal(str(superficie_arrendada_ha))
    qq_ha = Decimal(str(alquiler_qq_ha))

    if sup_ha <= Decimal("0.0"):
        raise ValueError("La superficie arrendada debe ser mayor a 0 ha.")
    if qq_ha <= Decimal("0.0"):
        raise ValueError("El alquiler en qq/ha debe ser mayor a 0.")

    base_val = (base_valorizacion or "rosario").strip().lower()
    if base_val not in ("rosario", "acopio"):
        raise ValueError(f"Base de valorización inválida '{base_valorizacion}'. Usar 'rosario' o 'acopio'.")

    # 1. Quintales totales y Toneladas equivalentes
    qq_totales = (sup_ha * qq_ha).quantize(Decimal("0.01"))
    tn_equivalentes = (qq_totales / Decimal("10.0")).quantize(Decimal("0.01"))

    # Convertir argumentos opcionales a Decimal
    p_ref = Decimal(str(precio_referencia_usd_tn)) if precio_referencia_usd_tn is not None else None
    flete = Decimal(str(flete_usd_tn)) if flete_usd_tn is not None else None
    comision = Decimal(str(comision_usd_tn)) if comision_usd_tn is not None else None

    missing: List[str] = []
    status = "not_evaluated"
    p_neto: Optional[Decimal] = None
    val_neto: Optional[Decimal] = None
    obs = ""

    if base_val == "rosario":
        if p_ref is not None:
            p_neto = p_ref
            val_neto = (tn_equivalentes * p_neto).quantize(Decimal("0.01"))
            status = "complete"
            obs = "Valorización base Rosario (logística y comisiones incluidas)."
        else:
            status = "not_evaluated"
            missing.append("precio_referencia_usd_tn")
            obs = "Falta precio de referencia para evaluar valorización USD."

    elif base_val == "acopio":
        if p_ref is None:
            missing.append("precio_referencia_usd_tn")
        if flete is None:
            missing.append("flete_usd_tn")
        if comision is None:
            missing.append("comision_usd_tn")

        if p_ref is not None and flete is not None and comision is not None:
            p_neto = p_ref - flete - comision
            val_neto = (tn_equivalentes * p_neto).quantize(Decimal("0.01"))
            status = "complete"
            obs = f"Valorización base Acopio (Precio {p_ref} - Flete {flete} - Comisión {comision} = Neto {p_neto} USD/Tn)."
        elif p_ref is not None:
            status = "partial"
            obs = f"Valorización parcial: faltan datos de logística ({', '.join(missing)})."
        else:
            status = "not_evaluated"
            obs = f"Sin evaluar: faltan datos requeridos ({', '.join(missing)})."

    return LeaseCalculationResult(
        superficie_arrendada_ha=sup_ha,
        alquiler_qq_ha=qq_ha,
        qq_totales=qq_totales,
        toneladas_equivalentes=tn_equivalentes,
        base_valorizacion=base_val,
        status_valorizacion=status,
        precio_referencia_usd_tn=p_ref,
        fecha_precio_referencia=fecha_precio_referencia,
        fuente_precio=fuente_precio,
        flete_usd_tn=flete,
        comision_usd_tn=comision,
        precio_neto_usd_tn=p_neto,
        valor_neto_estimado_usd=val_neto,
        missing_fields=missing,
        observaciones_calculo=obs,
    )
