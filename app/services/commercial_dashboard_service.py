from __future__ import annotations

"""
Servicio del Dashboard Comercial V2 (EduAgro).

Sincroniza y consolida la posición comercial agregada utilizando exclusivamente
el estándar Stock 1A/1B/1C (StockPartida, StockMovement, StockReservation,
StockDeliveryAllocation, StockWeightReconciliation, CompromisoGrano, GrainDelivery).

NO utiliza la tabla legacy StockGrano para saldos comerciales ni suma la producción
teórica de lotes al stock disponible libre.
"""

from decimal import Decimal
from datetime import datetime, date
from uuid import UUID
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    StockPartida,
    StockMovement,
    StockReservation,
    StockDeliveryAllocation,
    StockWeightReconciliation,
    StorageLocation,
    CompromisoGrano,
    ArrendamientoTerms,
    GrainDelivery,
    GrainWaybill,
    Lote,
    ContratoVentaGrano,
    TipoPrecioEnum,
)
from app.services.stock_service import (
    get_stock_partida_commercial_balance,
    get_compromisos_saldos_map,
    build_commitment_display_label,
)
from app.services.lease_calculator import calculate_field_lease_terms


@dataclass
class DashboardPriorityItem:
    codigo: str
    titulo: str
    motivo: str
    nivel: str  # 'critical', 'warning', 'info'
    toneladas_tn: Optional[Decimal] = None
    fecha_str: Optional[str] = None
    cta_texto: str = "Ver detalle"
    cta_url: str = "/comercial"


@dataclass
class UpcomingCommitmentItem:
    id: UUID
    display_label: str
    cultivo: str
    concepto: str
    beneficiario: str
    toneladas_comprometidas_tn: Decimal
    saldo_pendiente_tn: Decimal
    toneladas_reservadas_tn: Decimal
    fecha_vencimiento_str: str
    estado_cobertura: str  # 'cubierto', 'parcial', 'sin_cobertura'
    arrendamiento_terms: Optional[Dict[str, Any]] = None


@dataclass
class StockByCropItem:
    cultivo: str
    stock_fisico_tn: Decimal
    stock_reservado_tn: Decimal
    stock_asignado_tn: Decimal
    stock_disponible_tn: Decimal
    tiene_stock_acopio: bool = False
    partidas_count: int = 0
    ubicaciones_nombres: List[str] = field(default_factory=list)


@dataclass
class LocationStockSummaryItem:
    location_id: UUID
    nombre: str
    tipo: str  # 'silo_propio', 'silobolsa', 'acopio', 'celda', etc.
    campo_nombre: Optional[str]
    es_custodia_acopio: bool
    stock_fisico_tn: Decimal
    stock_reservado_tn: Decimal
    stock_asignado_tn: Decimal
    stock_disponible_tn: Decimal
    partidas_count: int
    capacidad_nominal_tn: Optional[Decimal] = None
    ocupacion_pct: Optional[Decimal] = None
    grupo_categoria: str = "EN CAMPO"  # 'EN CAMPO', 'EN CUSTODIA / ACOPIOS', 'OTRAS UBICACIONES'
    cta_url: str = "/comercial/stock"


@dataclass
class LocationGroupSummary:
    nombre_grupo: str  # 'EN CAMPO', 'EN CUSTODIA / ACOPIOS', 'OTRAS UBICACIONES'
    stock_fisico_tn: Decimal
    stock_reservado_tn: Decimal
    stock_asignado_tn: Decimal
    stock_disponible_tn: Decimal
    locations: List[LocationStockSummaryItem] = field(default_factory=list)


@dataclass
class RecentOperationItem:
    id: UUID
    tracking_number: str
    tipo_operacion: str  # 'entrega', 'despacho', 'recepcion', 'conciliacion'
    descripcion: str
    estado: str
    fecha_str: str
    cta_url: str


@dataclass
class CommercialDashboardSummary:
    # 1. KPIs Físicos Reales (Stock 1A/1B/1C)
    stock_fisico_total_tn: Decimal
    stock_reservado_total_tn: Decimal
    stock_asignado_total_tn: Decimal
    stock_disponible_libre_tn: Decimal

    # 2. Ventas Formales Registradas (Contratos)
    tn_vendidas_precio_fijo: Decimal
    tn_vendidas_a_fijar: Decimal

    # 3. Cobertura y Posición
    porcentaje_cobertura_stock: Decimal
    cultivo_seleccionado: str

    # 4. Listas de Bloques de Dashboard V2
    priorities: List[DashboardPriorityItem]
    upcoming_commitments: List[UpcomingCommitmentItem]
    stock_by_crop: List[StockByCropItem]
    location_groups: List[LocationGroupSummary]
    recent_operations: List[RecentOperationItem]

    # 5. Referencia Secundaria Informativa (No Físico)
    produccion_estimada_lotes_tn: Decimal = Decimal("0.0")
    as_of: datetime = field(default_factory=datetime.now)


def normalizar_texto(txt: Optional[str]) -> str:
    if not txt:
        return ""
    import unicodedata
    return unicodedata.normalize("NFD", txt).encode("ascii", "ignore").decode("utf-8").lower().strip()


async def get_commercial_dashboard_summary(
    db: AsyncSession,
    cliente_id: UUID,
    cultivo: Optional[str] = "soja",
    campania_id: Optional[UUID] = None,
) -> CommercialDashboardSummary:
    """
    Calcula y consolida el resumen del Dashboard Comercial V2 sin N+1 queries.
    """
    cultivo_sel = (cultivo or "soja").strip().lower()

    # -------------------------------------------------------------------------
    # 1. CARGA DE PARTIDAS Y SALDOS FÍSICOS REALES (STOCK 1A/1B/1C)
    # -------------------------------------------------------------------------
    stmt_partidas = select(StockPartida).options(
        selectinload(StockPartida.storage_location)
    ).where(
        StockPartida.cliente_id == cliente_id,
        StockPartida.estado != "anulada",
    )
    res_partidas = await db.execute(stmt_partidas)
    partidas_all = res_partidas.scalars().all()

    # Mapeo de balances por partida
    partida_balances: Dict[UUID, Dict[str, Any]] = {}
    for p in partidas_all:
        bal = await get_stock_partida_commercial_balance(db, cliente_id, p.id)
        partida_balances[p.id] = bal

    total_fisico_all = Decimal("0.0")
    total_reservado_all = Decimal("0.0")
    total_asignado_all = Decimal("0.0")
    total_disponible_all = Decimal("0.0")

    crop_stock_map: Dict[str, Dict[str, Any]] = {}

    for p in partidas_all:
        b = partida_balances[p.id]
        c_norm = normalizar_texto(p.cultivo)

        if c_norm not in crop_stock_map:
            crop_stock_map[c_norm] = {
                "cultivo": p.cultivo.capitalize(),
                "fisico_tn": Decimal("0.0"),
                "reservado_tn": Decimal("0.0"),
                "asignado_tn": Decimal("0.0"),
                "disponible_tn": Decimal("0.0"),
                "tiene_acopio": False,
                "partidas_count": 0,
                "ubicaciones": set(),
            }

        crop_stock_map[c_norm]["fisico_tn"] += b["stock_fisico_tn"]
        crop_stock_map[c_norm]["reservado_tn"] += b["stock_reservado_tn"]
        crop_stock_map[c_norm]["asignado_tn"] += b["stock_asignado_tn"]
        crop_stock_map[c_norm]["disponible_tn"] += b["stock_disponible_tn"]
        crop_stock_map[c_norm]["partidas_count"] += 1

        if p.storage_location:
            crop_stock_map[c_norm]["ubicaciones"].add(p.storage_location.nombre)
            if p.storage_location.tipo == "acopio":
                crop_stock_map[c_norm]["tiene_acopio"] = True

        total_fisico_all += b["stock_fisico_tn"]
        total_reservado_all += b["stock_reservado_tn"]
        total_asignado_all += b["stock_asignado_tn"]
        total_disponible_all += b["stock_disponible_tn"]

    # Determinar KPIs para el cultivo seleccionado
    c_sel_norm = normalizar_texto(cultivo_sel)
    if c_sel_norm in crop_stock_map:
        sel_info = crop_stock_map[c_sel_norm]
        kpi_fisico = sel_info["fisico_tn"]
        kpi_reservado = sel_info["reservado_tn"]
        kpi_asignado = sel_info["asignado_tn"]
        kpi_disponible = sel_info["disponible_tn"]
    else:
        kpi_fisico = Decimal("0.0")
        kpi_reservado = Decimal("0.0")
        kpi_asignado = Decimal("0.0")
        kpi_disponible = Decimal("0.0")

    stock_by_crop_list = [
        StockByCropItem(
            cultivo=v["cultivo"],
            stock_fisico_tn=v["fisico_tn"],
            stock_reservado_tn=v["reservado_tn"],
            stock_asignado_tn=v["asignado_tn"],
            stock_disponible_tn=v["disponible_tn"],
            tiene_stock_acopio=v["tiene_acopio"],
            partidas_count=v["partidas_count"],
            ubicaciones_nombres=sorted(list(v["ubicaciones"])),
        )
        for v in crop_stock_map.values()
    ]

    # -------------------------------------------------------------------------
    # 1.B DESGLOSE POR UBICACIÓN Y CUSTODIA (EN CAMPO / CUSTODIA / OTRAS)
    # -------------------------------------------------------------------------
    stmt_locs = select(StorageLocation).options(
        selectinload(StorageLocation.campo)
    ).where(
        StorageLocation.cliente_id == cliente_id,
        StorageLocation.estado == "activo",
    ).order_by(StorageLocation.tipo.asc(), StorageLocation.nombre.asc())

    res_locs = await db.execute(stmt_locs)
    locs_all = res_locs.scalars().all()

    group_campo_locs: List[LocationStockSummaryItem] = []
    group_custodia_locs: List[LocationStockSummaryItem] = []
    group_otras_locs: List[LocationStockSummaryItem] = []

    for loc in locs_all:
        loc_partidas = [p for p in partidas_all if p.storage_location_id == loc.id]
        loc_fisico = Decimal("0.0")
        loc_reservado = Decimal("0.0")
        loc_asignado = Decimal("0.0")
        loc_disponible = Decimal("0.0")

        for p in loc_partidas:
            b = partida_balances[p.id]
            loc_fisico += b["stock_fisico_tn"]
            loc_reservado += b["stock_reservado_tn"]
            loc_asignado += b["stock_asignado_tn"]
            loc_disponible += b["stock_disponible_tn"]

        # Calcular ocupación % si posee capacidad nominal
        cap_tn = loc.capacidad_nominal_tn
        ocu_pct: Optional[Decimal] = None
        if cap_tn and cap_tn > Decimal("0.0"):
            ocu_pct = ((loc_fisico / cap_tn) * Decimal("100.0")).quantize(Decimal("0.1"))

        es_acopio = (loc.tipo == "acopio")
        campo_nom = loc.campo.nombre if loc.campo else loc.ubicacion_referencia

        # Clasificación por categoría
        if loc.tipo in ("silo_propio", "silobolsa", "silo_bolsa", "celda", "silo"):
            categoria = "EN CAMPO"
        elif loc.tipo == "acopio":
            categoria = "EN CUSTODIA / ACOPIOS"
        else:
            categoria = "OTRAS UBICACIONES"

        item_loc = LocationStockSummaryItem(
            location_id=loc.id,
            nombre=loc.nombre,
            tipo=loc.tipo,
            campo_nombre=campo_nom,
            es_custodia_acopio=es_acopio,
            stock_fisico_tn=loc_fisico,
            stock_reservado_tn=loc_reservado,
            stock_asignado_tn=loc_asignado,
            stock_disponible_tn=loc_disponible,
            partidas_count=len(loc_partidas),
            capacidad_nominal_tn=cap_tn,
            ocupacion_pct=ocu_pct,
            grupo_categoria=categoria,
            cta_url=f"/comercial/stock?ubicacion_id={loc.id}",
        )

        if categoria == "EN CAMPO":
            group_campo_locs.append(item_loc)
        elif categoria == "EN CUSTODIA / ACOPIOS":
            group_custodia_locs.append(item_loc)
        else:
            group_otras_locs.append(item_loc)

    def _build_group(nombre: str, locs: List[LocationStockSummaryItem]) -> LocationGroupSummary:
        f_tot = sum((x.stock_fisico_tn for x in locs), Decimal("0.0"))
        r_tot = sum((x.stock_reservado_tn for x in locs), Decimal("0.0"))
        a_tot = sum((x.stock_asignado_tn for x in locs), Decimal("0.0"))
        d_tot = sum((x.stock_disponible_tn for x in locs), Decimal("0.0"))
        return LocationGroupSummary(
            nombre_grupo=nombre,
            stock_fisico_tn=f_tot,
            stock_reservado_tn=r_tot,
            stock_asignado_tn=a_tot,
            stock_disponible_tn=d_tot,
            locations=locs,
        )

    location_groups_list = [
        _build_group("EN CAMPO", group_campo_locs),
        _build_group("EN CUSTODIA / ACOPIOS", group_custodia_locs),
    ]
    if group_otras_locs:
        location_groups_list.append(_build_group("OTRAS UBICACIONES", group_otras_locs))

    # -------------------------------------------------------------------------
    # 2. CONTRATOS DE VENTA DE GRANOS
    # -------------------------------------------------------------------------
    stmt_contratos = select(ContratoVentaGrano).where(ContratoVentaGrano.cliente_id == cliente_id)
    if campania_id:
        stmt_contratos = stmt_contratos.where(ContratoVentaGrano.campania_id == campania_id)
    res_contratos = await db.execute(stmt_contratos)
    contratos_all = res_contratos.scalars().all()

    tn_vendidas_fijo = Decimal("0.0")
    tn_vendidas_a_fijar = Decimal("0.0")

    for c in contratos_all:
        if normalizar_texto(c.cultivo) == c_sel_norm:
            tn = Decimal(str(c.toneladas or 0.0))
            if c.tipo_precio == TipoPrecioEnum.FIJO:
                tn_vendidas_fijo += tn
            elif c.tipo_precio == TipoPrecioEnum.A_FIJAR:
                tn_vendidas_a_fijar += tn

    # -------------------------------------------------------------------------
    # 3. COMPROMISOS PRÓXIMOS Y RESERVAS DE STOCK (INCLUYE ARRENDAMIENTOS V1)
    # -------------------------------------------------------------------------
    saldos_map = await get_compromisos_saldos_map(db, cliente_id)

    stmt_comp = select(CompromisoGrano).options(
        selectinload(CompromisoGrano.arrendamiento_terms),
        selectinload(CompromisoGrano.campo),
    ).where(
        CompromisoGrano.cliente_id == cliente_id,
        CompromisoGrano.cumplido.is_(False),
    ).order_by(CompromisoGrano.fecha_vencimiento.asc().nulls_last(), CompromisoGrano.fecha_creacion.desc())

    res_comp = await db.execute(stmt_comp)
    compromisos_all = res_comp.scalars().all()

    upcoming_commitments: List[UpcomingCommitmentItem] = []
    priorities: List[DashboardPriorityItem] = []

    for comp in compromisos_all:
        c_norm = normalizar_texto(comp.cultivo)
        if c_norm != c_sel_norm and len(upcoming_commitments) >= 5:
            continue

        saldo_tn = saldos_map.get(comp.id, Decimal(str(comp.toneladas_comprometidas)))

        # Calcular reservas activas para este compromiso
        stmt_res_comp = select(func.coalesce(func.sum(StockReservation.cantidad_reserva_kg), 0)).where(
            StockReservation.compromiso_id == comp.id,
            StockReservation.estado == "activa",
        )
        res_kg = (await db.execute(stmt_res_comp)).scalar() or Decimal("0.0")
        reservadas_tn = (Decimal(str(res_kg)) / Decimal("1000.0")).quantize(Decimal("0.01"))

        if reservadas_tn >= saldo_tn and saldo_tn > Decimal("0.0"):
            estado_cob = "cubierto"
        elif reservadas_tn > Decimal("0.0"):
            estado_cob = "parcial"
        else:
            estado_cob = "sin_cobertura"

        label = build_commitment_display_label(comp, saldo_tn=saldo_tn)
        venc_str = comp.fecha_vencimiento.strftime("%d/%m/%Y") if comp.fecha_vencimiento else "S/V"

        # Términos de arrendamiento si aplican
        lease_dict: Optional[Dict[str, Any]] = None
        if comp.arrendamiento_terms:
            t = comp.arrendamiento_terms
            calc_res = calculate_field_lease_terms(
                superficie_arrendada_ha=t.superficie_arrendada_ha,
                alquiler_qq_ha=t.alquiler_qq_ha,
                base_valorizacion=t.base_valorizacion,
                precio_referencia_usd_tn=t.precio_referencia_usd_tn,
                fecha_precio_referencia=t.fecha_precio_referencia,
                fuente_precio=t.fuente_precio,
                flete_usd_tn=t.flete_usd_tn,
                comision_usd_tn=t.comision_usd_tn,
            )
            lease_dict = {
                "superficie_ha": calc_res.superficie_arrendada_ha,
                "alquiler_qq_ha": calc_res.alquiler_qq_ha,
                "qq_totales": calc_res.qq_totales,
                "base_valorizacion": calc_res.base_valorizacion,
                "status_valorizacion": calc_res.status_valorizacion,
                "valor_neto_estimado_usd": calc_res.valor_neto_estimado_usd,
                "missing_fields": calc_res.missing_fields,
            }

            # Alerta de valorización incompleta para acopio
            if calc_res.status_valorizacion == "partial":
                priorities.append(
                    DashboardPriorityItem(
                        codigo="ARRENDAMIENTO_INCOMPLETO",
                        titulo=f"Valorización Incompleta: {comp.concepto}",
                        motivo=f"Base Acopio requiere flete/comisión para calcular neto USD (Faltan: {', '.join(calc_res.missing_fields)}).",
                        nivel="warning",
                        toneladas_tn=saldo_tn,
                        fecha_str=venc_str,
                        cta_texto="Editar arrendamiento",
                        cta_url="/comercial/contratos",
                    )
                )

        item_comp = UpcomingCommitmentItem(
            id=comp.id,
            display_label=label,
            cultivo=comp.cultivo.capitalize(),
            concepto=comp.concepto,
            beneficiario=comp.beneficiario,
            toneladas_comprometidas_tn=Decimal(str(comp.toneladas_comprometidas)),
            saldo_pendiente_tn=saldo_tn,
            toneladas_reservadas_tn=reservadas_tn,
            fecha_vencimiento_str=venc_str,
            estado_cobertura=estado_cob,
            arrendamiento_terms=lease_dict,
        )

        if c_norm == c_sel_norm and len(upcoming_commitments) < 5:
            upcoming_commitments.append(item_comp)

        # Evaluar alertas de prioridad por compromiso
        if comp.fecha_vencimiento:
            days_until = (comp.fecha_vencimiento - date.today()).days
            if days_until < 0 and not comp.cumplido:
                priorities.append(
                    DashboardPriorityItem(
                        codigo="COMPROMISO_VENCIDO",
                        titulo=f"Compromiso Vencido: {comp.concepto}",
                        motivo=f"Venció el {venc_str} con saldo pendiente de {saldo_tn:.2f} Tn.",
                        nivel="critical",
                        toneladas_tn=saldo_tn,
                        fecha_str=venc_str,
                        cta_texto="Ver compromiso",
                        cta_url="/comercial/contratos",
                    )
                )
            elif days_until <= 15 and estado_cob == "sin_cobertura":
                priorities.append(
                    DashboardPriorityItem(
                        codigo="COBERTURA_PENDIENTE",
                        titulo=f"Compromiso Próximo sin Reserva: {comp.beneficiario}",
                        motivo=f"Vence en {days_until} días ({venc_str}) y no posee stock reservado.",
                        nivel="warning",
                        toneladas_tn=saldo_tn,
                        fecha_str=venc_str,
                        cta_texto="Reservar stock",
                        cta_url="/comercial/stock",
                    )
                )

    # -------------------------------------------------------------------------
    # 4. RECONCILIACIONES Y ENTREGAS EN TRÁNSITO (PRIORIDADES LOGÍSTICAS)
    # -------------------------------------------------------------------------
    stmt_rec = select(StockWeightReconciliation).where(
        StockWeightReconciliation.cliente_id == cliente_id,
        StockWeightReconciliation.estado == "pendiente",
    )
    reconciliaciones_pendientes = (await db.execute(stmt_rec)).scalars().all()

    for r in reconciliaciones_pendientes:
        priorities.append(
            DashboardPriorityItem(
                codigo="CONCILIACION_PENDIENTE",
                titulo="Diferencia de Pesaje Pendiente",
                motivo=f"Diferencia de {r.diferencia_kg} kg ({r.diferencia_pct}%) pendiente de resolución explícita.",
                nivel="critical",
                toneladas_tn=abs(r.diferencia_kg) / Decimal("1000.0"),
                cta_texto="Resolver en entregas",
                cta_url="/comercial/entregas",
            )
        )

    stmt_del = select(GrainDelivery).where(
        GrainDelivery.cliente_id == cliente_id,
        GrainDelivery.estado == "en_transito",
    )
    entregas_transito = (await db.execute(stmt_del)).scalars().all()

    for d in entregas_transito:
        priorities.append(
            DashboardPriorityItem(
                codigo="ENTREGA_EN_TRANSITO",
                titulo=f"Entrega en Tránsito: {d.tracking_number}",
                motivo=f"Camión despachado hacia {d.acopio_receptor or 'destino'} sin confirmación de pesaje en balanza.",
                nivel="warning",
                toneladas_tn=Decimal(str(d.toneladas_planificadas or 0.0)),
                cta_texto="Registrar peso recibido",
                cta_url="/comercial/entregas",
            )
        )

    # Ordenar prioridades por criticidad
    priority_order = {"critical": 0, "warning": 1, "info": 2}
    priorities.sort(key=lambda p: priority_order.get(p.nivel, 3))
    priorities = priorities[:5]

    # -------------------------------------------------------------------------
    # 5. OPERACIONES RECIENTES (LOGÍSTICA / CARTA DE PORTE)
    # -------------------------------------------------------------------------
    stmt_ops = select(GrainDelivery).where(
        GrainDelivery.cliente_id == cliente_id
    ).order_by(GrainDelivery.fecha_creacion.desc()).limit(5)
    
    deliv_ops = (await db.execute(stmt_ops)).scalars().all()

    recent_operations: List[RecentOperationItem] = []
    for d in deliv_ops:
        dt_str = d.fecha_creacion.strftime("%d/%m/%Y") if d.fecha_creacion else date.today().strftime("%d/%m/%Y")
        cult_str = d.cultivo.capitalize() if d.cultivo else "Grano"
        recent_operations.append(
            RecentOperationItem(
                id=d.id,
                tracking_number=d.tracking_number,
                tipo_operacion="entrega",
                descripcion=f"Entrega {cult_str} ({d.toneladas_planificadas or 0} Tn) -> {d.acopio_receptor or 'Sin especificar'}",
                estado=d.estado,
                fecha_str=dt_str,
                cta_url="/comercial/entregas",
            )
        )

    # -------------------------------------------------------------------------
    # 6. PRODUCCIÓN ESTIMADA DE LOTES (REFERENCIA SECUNDARIA INFORMATIVA)
    # -------------------------------------------------------------------------
    stmt_lotes = select(Lote).where(Lote.cliente_id == cliente_id)
    if campania_id:
        stmt_lotes = stmt_lotes.where((Lote.campania_id == campania_id) | (Lote.campania_id.is_(None)))
    res_lotes = await db.execute(stmt_lotes)
    lotes_all = res_lotes.scalars().all()

    prod_estimada_tn = Decimal("0.0")
    for lote in lotes_all:
        if c_sel_norm in normalizar_texto(lote.cultivo_actual):
            sup_ha = Decimal(str(lote.superficie_productiva_ha or 0.0))
            if lote.qq_ha_real and lote.qq_ha_real > 0:
                rinde_qq = Decimal(str(lote.qq_ha_real))
            elif lote.qq_ha_estimado and lote.qq_ha_estimado > 0:
                rinde_qq = Decimal(str(lote.qq_ha_estimado))
            else:
                rinde_qq = Decimal("0.0")

            prod_estimada_tn += (sup_ha * rinde_qq) / Decimal("10.0")

    # Cobertura % sobre stock físico registrado (o producción si stock es 0)
    denom = kpi_fisico if kpi_fisico > Decimal("0.0") else prod_estimada_tn
    if denom > Decimal("0.0"):
        pct_cobertura = ((tn_vendidas_fijo + kpi_reservado) / denom) * Decimal("100.0")
    else:
        pct_cobertura = Decimal("0.0")

    return CommercialDashboardSummary(
        stock_fisico_total_tn=kpi_fisico,
        stock_reservado_total_tn=kpi_reservado,
        stock_asignado_total_tn=kpi_asignado,
        stock_disponible_libre_tn=kpi_disponible,
        tn_vendidas_precio_fijo=tn_vendidas_fijo,
        tn_vendidas_a_fijar=tn_vendidas_a_fijar,
        porcentaje_cobertura_stock=pct_cobertura.quantize(Decimal("0.01")),
        cultivo_seleccionado=cultivo_sel,
        priorities=priorities,
        upcoming_commitments=upcoming_commitments,
        stock_by_crop=stock_by_crop_list,
        location_groups=location_groups_list,
        recent_operations=recent_operations,
        produccion_estimada_lotes_tn=prod_estimada_tn.quantize(Decimal("0.01")),
        as_of=datetime.now(),
    )
