from __future__ import annotations

"""
Servicio de Stock Físico V1 y Stock Comercial 1B (EduAgro).
Provee cálculo de saldos derivados (Físico, Reservado, Asignado y Disponible),
reservas por compromisos, asignaciones a entregas y validaciones multitenant transaccionales.
"""

from decimal import Decimal
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    StockPartida,
    StockMovement,
    StorageLocation,
    StockQualityMeasurement,
    StockReservation,
    StockDeliveryAllocation,
    CompromisoGrano,
    GrainDelivery,
)


async def get_stock_partida_balance(
    db: AsyncSession,
    cliente_id: UUID,
    partida_id: UUID,
) -> Dict[str, Any]:
    """
    Calcula el saldo FÍSICO derivado de los movimientos inmutables de una partida.
    El saldo FÍSICO es la suma de `cantidad_kg` de sus movimientos (`StockMovement`).
    """
    stmt = (
        select(
            func.coalesce(func.sum(StockMovement.cantidad_kg), Decimal("0.0")).label("total_kg"),
            func.count(StockMovement.id).label("cant_movimientos"),
            func.max(StockMovement.fecha_movimiento).label("ultimo_movimiento"),
        )
        .where(
            StockMovement.cliente_id == cliente_id,
            StockMovement.stock_partida_id == partida_id,
        )
    )

    res = await db.execute(stmt)
    row = res.first()

    total_kg = Decimal(str(row.total_kg)) if row and row.total_kg is not None else Decimal("0.0")
    cant_movs = int(row.cant_movimientos) if row and row.cant_movimientos is not None else 0
    ult_mov = row.ultimo_movimiento if row else None

    total_tn = (total_kg / Decimal("1000.0")).quantize(Decimal("0.01"))

    if cant_movs == 0:
        estado_eval = "sin_movimientos"
    elif total_kg < Decimal("0.0"):
        estado_eval = "saldo_negativo_error"
    elif total_kg == Decimal("0.0"):
        estado_eval = "agotada"
    else:
        estado_eval = "con_saldo"

    return {
        "partida_id": str(partida_id),
        "saldo_fisico_kg": total_kg,
        "saldo_fisico_tn": total_tn,
        "cantidad_movimientos": cant_movs,
        "fecha_ultimo_movimiento": ult_mov,
        "estado_evaluacion": estado_eval,
    }


async def get_stock_partida_commercial_balance(
    db: AsyncSession,
    cliente_id: UUID,
    partida_id: UUID,
) -> Dict[str, Any]:
    """
    Calcula los 4 saldos derivados de una partida física (Stock 1B):
    1. stock_fisico = SUM(movimientos)
    2. stock_asignado = SUM(asignaciones_activas)
    3. stock_reservado = SUM(max(0, reserva - asignaciones_desde_esa_reserva))
    4. stock_disponible = stock_fisico - stock_reservado - stock_asignado
    """
    # 1. Saldo Físico
    bal_fisico = await get_stock_partida_balance(db, cliente_id, partida_id)
    fisico_kg = bal_fisico["saldo_fisico_kg"]

    # 2. Asignaciones Activas Totales de esta partida
    stmt_asig = select(
        func.coalesce(func.sum(StockDeliveryAllocation.cantidad_kg), Decimal("0.0")).label("total_asignado"),
        func.count(StockDeliveryAllocation.id).label("count_asig"),
    ).where(
        StockDeliveryAllocation.cliente_id == cliente_id,
        StockDeliveryAllocation.stock_partida_id == partida_id,
        StockDeliveryAllocation.estado == "activa",
    )
    res_asig = await db.execute(stmt_asig)
    row_asig = res_asig.first()
    asignado_kg = Decimal(str(row_asig.total_asignado)) if row_asig and row_asig.total_asignado is not None else Decimal("0.0")
    count_asig = int(row_asig.count_asig) if row_asig and row_asig.count_asig is not None else 0

    # 3. Reservas Activas y Remanente (Evitando doble conteo con asignaciones nacidas de la reserva)
    stmt_res = select(StockReservation).where(
        StockReservation.cliente_id == cliente_id,
        StockReservation.stock_partida_id == partida_id,
        StockReservation.estado.in_(["activa", "parcialmente_asignada"]),
    )
    res_res = await db.execute(stmt_res)
    reservas_activas = res_res.scalars().all()

    reservado_remanente_kg = Decimal("0.0")
    count_res = len(reservas_activas)

    for r in reservas_activas:
        # Calcular asignaciones activas nacidas de esta reserva
        stmt_res_asig = select(
            func.coalesce(func.sum(StockDeliveryAllocation.cantidad_kg), Decimal("0.0"))
        ).where(
            StockDeliveryAllocation.cliente_id == cliente_id,
            StockDeliveryAllocation.stock_reservation_id == r.id,
            StockDeliveryAllocation.estado == "activa",
        )
        res_res_asig = await db.execute(stmt_res_asig)
        asig_desde_r = Decimal(str(res_res_asig.scalar_one_or_none() or "0.0"))

        rem_r = max(Decimal("0.0"), r.cantidad_reserva_kg - asig_desde_r)
        reservado_remanente_kg += rem_r

    # 4. Stock Disponible
    disponible_kg = max(Decimal("0.0"), fisico_kg - reservado_remanente_kg - asignado_kg)

    return {
        "partida_id": str(partida_id),
        "stock_fisico_kg": fisico_kg,
        "stock_reservado_kg": reservado_remanente_kg,
        "stock_asignado_kg": asignado_kg,
        "stock_disponible_kg": disponible_kg,
        "stock_fisico_tn": (fisico_kg / Decimal("1000.0")).quantize(Decimal("0.01")),
        "stock_reservado_tn": (reservado_remanente_kg / Decimal("1000.0")).quantize(Decimal("0.01")),
        "stock_asignado_tn": (asignado_kg / Decimal("1000.0")).quantize(Decimal("0.01")),
        "stock_disponible_tn": (disponible_kg / Decimal("1000.0")).quantize(Decimal("0.01")),
        "reservas_activas_count": count_res,
        "asignaciones_activas_count": count_asig,
        "as_of": datetime.now(),
    }


async def fetch_aggregated_stock_v1_summary(
    db: AsyncSession,
    cliente_id: UUID,
    cultivo: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calcula el resumen agregado de Stock Físico Registrado y Saldos Comerciales V1.
    """
    stmt_loc = select(func.count(StorageLocation.id)).where(
        StorageLocation.cliente_id == cliente_id,
        StorageLocation.estado == "activo",
    )
    res_loc = await db.execute(stmt_loc)
    cant_ubicaciones = res_loc.scalar_one_or_none() or 0

    stmt_partidas = select(StockPartida).where(
        StockPartida.cliente_id == cliente_id,
    )
    if cultivo and cultivo.strip():
        stmt_partidas = stmt_partidas.where(func.lower(StockPartida.cultivo) == cultivo.strip().lower())

    res_partidas = await db.execute(stmt_partidas)
    partidas = res_partidas.scalars().all()

    total_tn_registrado = Decimal("0.0")
    total_tn_reservado = Decimal("0.0")
    total_tn_asignado = Decimal("0.0")
    total_tn_disponible = Decimal("0.0")
    cant_activas = 0
    cant_observadas = 0

    for p in partidas:
        if p.estado == "activa":
            cant_activas += 1
        elif p.estado == "observada":
            cant_observadas += 1

        bal = await get_stock_partida_commercial_balance(db, cliente_id, p.id)
        if bal["stock_fisico_kg"] > Decimal("0.0"):
            total_tn_registrado += bal["stock_fisico_tn"]
            total_tn_reservado += bal["stock_reservado_tn"]
            total_tn_asignado += bal["stock_asignado_tn"]
            total_tn_disponible += bal["stock_disponible_tn"]

    return {
        "etiqueta_titulo": "Stock físico registrado",
        "total_tn_fisico_registrado": total_tn_registrado,
        "total_tn_reservado": total_tn_reservado,
        "total_tn_asignado": total_tn_asignado,
        "total_tn_disponible": total_tn_disponible,
        "partidas_activas_count": cant_activas,
        "partidas_observadas_count": cant_observadas,
        "ubicaciones_activas_count": cant_ubicaciones,
    }


async def reserve_stock_for_commitment(
    db: AsyncSession,
    cliente_id: UUID,
    stock_partida_id: UUID,
    compromiso_id: UUID,
    cantidad_valor: Decimal,
    unidad_medida: str = "tn",
    observaciones: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> StockReservation:
    """
    Crea una reserva de stock físico para un compromiso comercial.
    Ejecuta bloqueo pesimista `with_for_update()` y valida que la cantidad no supere el disponible.
    """
    # 1. Lock y validación de multitenancy de la partida
    stmt_p = (
        select(StockPartida)
        .where(StockPartida.id == stock_partida_id, StockPartida.cliente_id == cliente_id)
        .with_for_update()
    )
    res_p = await db.execute(stmt_p)
    partida = res_p.scalars().first()
    if not partida:
        raise ValueError("Partida física no encontrada o no autorizada para el cliente")

    # 2. Validación de multitenancy del compromiso
    stmt_c = select(CompromisoGrano).where(CompromisoGrano.id == compromiso_id, CompromisoGrano.cliente_id == cliente_id)
    res_c = await db.execute(stmt_c)
    compromiso = res_c.scalars().first()
    if not compromiso:
        raise ValueError("Compromiso comercial no encontrado o no autorizado para el cliente")

    # 3. Conversión a kg en Decimal
    if (unidad_medida or "").strip().lower() == "tn":
        cant_kg = cantidad_valor * Decimal("1000.0")
    else:
        cant_kg = cantidad_valor

    if cant_kg <= Decimal("0.0"):
        raise ValueError("La cantidad a reservar debe ser mayor a 0 kg")

    # 4. Validar disponibilidad actual
    bal = await get_stock_partida_commercial_balance(db, cliente_id, partida.id)
    disponible_kg = bal["stock_disponible_kg"]

    if cant_kg > disponible_kg:
        disponible_tn = bal["stock_disponible_tn"]
        solicitado_tn = (cant_kg / Decimal("1000.0")).quantize(Decimal("0.01"))
        raise ValueError(
            f"La reserva ({solicitado_tn:.2f} Tn) supera el stock disponible actual ({disponible_tn:.2f} Tn) de la partida"
        )

    # 5. Crear Reserva
    reserva = StockReservation(
        cliente_id=cliente_id,
        stock_partida_id=partida.id,
        compromiso_id=compromiso.id,
        cantidad_reserva_kg=cant_kg,
        estado="activa",
        observaciones=observaciones.strip() if observaciones else None,
        created_by_user_id=user_id,
    )
    db.add(reserva)
    await db.commit()
    await db.refresh(reserva)
    return reserva


async def release_stock_reservation(
    db: AsyncSession,
    cliente_id: UUID,
    reservation_id: UUID,
    motivo_liberacion: str,
    observaciones: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> StockReservation:
    """
    Libera el remanente no asignado de una reserva de stock.
    """
    if not motivo_liberacion or not motivo_liberacion.strip():
        raise ValueError("El motivo de liberación de la reserva es obligatorio")

    stmt_res = (
        select(StockReservation)
        .where(StockReservation.id == reservation_id, StockReservation.cliente_id == cliente_id)
        .with_for_update()
    )
    res_r = await db.execute(stmt_res)
    reserva = res_r.scalars().first()
    if not reserva:
        raise ValueError("Reserva de stock no encontrada o no autorizada")

    if reserva.estado in ["liberada", "cancelada", "consumida"]:
        raise ValueError(f"La reserva ya se encuentra en estado '{reserva.estado}'")

    # Verificar asignaciones activas nacidas de esta reserva
    stmt_asig = select(
        func.coalesce(func.sum(StockDeliveryAllocation.cantidad_kg), Decimal("0.0"))
    ).where(
        StockDeliveryAllocation.cliente_id == cliente_id,
        StockDeliveryAllocation.stock_reservation_id == reserva.id,
        StockDeliveryAllocation.estado == "activa",
    )
    res_asig = await db.execute(stmt_asig)
    asig_kg = Decimal(str(res_asig.scalar_one_or_none() or "0.0"))

    if asig_kg >= reserva.cantidad_reserva_kg:
        reserva.estado = "consumida"
    else:
        reserva.estado = "liberada"

    reserva.fecha_liberacion = datetime.now()
    reserva.motivo_liberacion = motivo_liberacion.strip()
    if observaciones:
        reserva.observaciones = (reserva.observaciones or "") + f" | Liberación: {observaciones.strip()}"
    reserva.released_by_user_id = user_id

    await db.commit()
    await db.refresh(reserva)
    return reserva


async def allocate_stock_to_delivery(
    db: AsyncSession,
    cliente_id: UUID,
    stock_partida_id: UUID,
    grain_delivery_id: UUID,
    cantidad_valor: Decimal,
    unidad_medida: str = "tn",
    stock_reservation_id: Optional[UUID] = None,
    observaciones: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> StockDeliveryAllocation:
    """
    Asigna una partida de stock a una entrega de grano.
    Si se especifica `stock_reservation_id`, valida que provenga de la misma reserva.
    Si no, valida disponibilidad en el stock libre.
    """
    # 1. Lock y validación de la partida
    stmt_p = (
        select(StockPartida)
        .where(StockPartida.id == stock_partida_id, StockPartida.cliente_id == cliente_id)
        .with_for_update()
    )
    res_p = await db.execute(stmt_p)
    partida = res_p.scalars().first()
    if not partida:
        raise ValueError("Partida física no encontrada o no autorizada para el cliente")

    # 2. Validación de la entrega
    stmt_d = select(GrainDelivery).where(GrainDelivery.id == grain_delivery_id, GrainDelivery.cliente_id == cliente_id)
    res_d = await db.execute(stmt_d)
    delivery = res_d.scalars().first()
    if not delivery:
        raise ValueError("Entrega de grano no encontrada o no autorizada para el cliente")

    # 3. Conversión a kg
    if (unidad_medida or "").strip().lower() == "tn":
        cant_kg = cantidad_valor * Decimal("1000.0")
    else:
        cant_kg = cantidad_valor

    if cant_kg <= Decimal("0.0"):
        raise ValueError("La cantidad a asignar debe ser mayor a 0 kg")

    reserva_obj = None
    origen_asig = "libre"
    compromiso_id_assoc = delivery.compromiso_id

    if stock_reservation_id:
        stmt_res = select(StockReservation).where(
            StockReservation.id == stock_reservation_id,
            StockReservation.cliente_id == cliente_id,
        ).with_for_update()
        res_r = await db.execute(stmt_res)
        reserva_obj = res_r.scalars().first()
        if not reserva_obj:
            raise ValueError("Reserva de stock asociada no encontrada o no autorizada")

        if reserva_obj.stock_partida_id != partida.id:
            raise ValueError("La reserva seleccionada no pertenece a la misma partida física")

        # Validar que si la entrega tiene compromiso, sea el mismo de la reserva
        if delivery.compromiso_id and delivery.compromiso_id != reserva_obj.compromiso_id:
            raise ValueError("El compromiso de la entrega no coincide con el compromiso de la reserva")

        compromiso_id_assoc = reserva_obj.compromiso_id
        origen_asig = "desde_reserva"

        # Calcular remanente disponible de la reserva
        stmt_rem = select(
            func.coalesce(func.sum(StockDeliveryAllocation.cantidad_kg), Decimal("0.0"))
        ).where(
            StockDeliveryAllocation.cliente_id == cliente_id,
            StockDeliveryAllocation.stock_reservation_id == reserva_obj.id,
            StockDeliveryAllocation.estado == "activa",
        )
        res_rem = await db.execute(stmt_rem)
        asig_prev_kg = Decimal(str(res_rem.scalar_one_or_none() or "0.0"))
        rem_reserva_kg = reserva_obj.cantidad_reserva_kg - asig_prev_kg

        if cant_kg > rem_reserva_kg:
            rem_tn = (rem_reserva_kg / Decimal("1000.0")).quantize(Decimal("0.01"))
            sol_tn = (cant_kg / Decimal("1000.0")).quantize(Decimal("0.01"))
            raise ValueError(f"La asignación ({sol_tn:.2f} Tn) supera el remanente de la reserva ({rem_tn:.2f} Tn)")

    else:
        # Asignación desde stock libre: validar disponible actual
        bal = await get_stock_partida_commercial_balance(db, cliente_id, partida.id)
        disponible_kg = bal["stock_disponible_kg"]

        if cant_kg > disponible_kg:
            dispon_tn = bal["stock_disponible_tn"]
            sol_tn = (cant_kg / Decimal("1000.0")).quantize(Decimal("0.01"))
            raise ValueError(f"La asignación ({sol_tn:.2f} Tn) supera el stock disponible libre ({dispon_tn:.2f} Tn)")

    # 4. Crear Asignación
    asignacion = StockDeliveryAllocation(
        cliente_id=cliente_id,
        stock_partida_id=partida.id,
        grain_delivery_id=delivery.id,
        stock_reservation_id=reserva_obj.id if reserva_obj else None,
        compromiso_id=compromiso_id_assoc,
        cantidad_kg=cant_kg,
        origen_asignacion=origen_asig,
        estado="activa",
        observaciones=observaciones.strip() if observaciones else None,
        created_by_user_id=user_id,
    )
    db.add(asignacion)

    # Actualizar estado de reserva si queda consumida
    if reserva_obj:
        stmt_check_rem = select(
            func.coalesce(func.sum(StockDeliveryAllocation.cantidad_kg), Decimal("0.0"))
        ).where(
            StockDeliveryAllocation.cliente_id == cliente_id,
            StockDeliveryAllocation.stock_reservation_id == reserva_obj.id,
            StockDeliveryAllocation.estado == "activa",
        )
        res_check_rem = await db.execute(stmt_check_rem)
        total_asig_now = Decimal(str(res_check_rem.scalar_one_or_none() or "0.0")) + cant_kg
        if total_asig_now >= reserva_obj.cantidad_reserva_kg:
            reserva_obj.estado = "consumida"
        else:
            reserva_obj.estado = "parcialmente_asignada"

    await db.commit()
    await db.refresh(asignacion)
    return asignacion


async def cancel_stock_delivery_allocation(
    db: AsyncSession,
    cliente_id: UUID,
    allocation_id: UUID,
    motivo_cancelacion: str,
    user_id: Optional[UUID] = None,
) -> StockDeliveryAllocation:
    """
    Cancela una asignación a entrega y restituye automáticamente la disponibilidad.
    Si venía de una reserva, el remanente vuelve a la reserva.
    """
    if not motivo_cancelacion or not motivo_cancelacion.strip():
        raise ValueError("El motivo de cancelación de la asignación es obligatorio")

    stmt_asig = (
        select(StockDeliveryAllocation)
        .where(StockDeliveryAllocation.id == allocation_id, StockDeliveryAllocation.cliente_id == cliente_id)
        .with_for_update()
    )
    res_a = await db.execute(stmt_asig)
    asig = res_a.scalars().first()
    if not asig:
        raise ValueError("Asignación de stock no encontrada o no autorizada")

    if asig.estado == "cancelada":
        raise ValueError("La asignación ya fue cancelada previamente")

    asig.estado = "cancelada"
    asig.fecha_cancelacion = datetime.now()
    asig.motivo_cancelacion = motivo_cancelacion.strip()
    asig.cancelled_by_user_id = user_id

    # Si provenía de una reserva consumida o parcialmente asignada, restituir estado si corresponde
    if asig.stock_reservation_id:
        stmt_r = select(StockReservation).where(
            StockReservation.id == asig.stock_reservation_id,
            StockReservation.cliente_id == cliente_id,
        )
        res_r = await db.execute(stmt_r)
        reserva = res_r.scalars().first()
        if reserva and reserva.estado in ["consumida", "parcialmente_asignada"]:
            # Recalcular asignaciones activas
            stmt_active = select(
                func.coalesce(func.sum(StockDeliveryAllocation.cantidad_kg), Decimal("0.0"))
            ).where(
                StockDeliveryAllocation.cliente_id == cliente_id,
                StockDeliveryAllocation.stock_reservation_id == reserva.id,
                StockDeliveryAllocation.id != asig.id,
                StockDeliveryAllocation.estado == "activa",
            )
            res_active = await db.execute(stmt_active)
            active_kg = Decimal(str(res_active.scalar_one_or_none() or "0.0"))

            if active_kg == Decimal("0.0"):
                reserva.estado = "activa"
            elif active_kg < reserva.cantidad_reserva_kg:
                reserva.estado = "parcialmente_asignada"

    await db.commit()
    await db.refresh(asig)
    return asig


async def get_commitment_stock_coverage(
    db: AsyncSession,
    cliente_id: UUID,
    compromiso_id: UUID,
) -> Dict[str, Any]:
    """
    Calcula la cobertura de reservas y asignaciones sobre un compromiso comercial.
    """
    stmt_c = select(CompromisoGrano).where(CompromisoGrano.id == compromiso_id, CompromisoGrano.cliente_id == cliente_id)
    res_c = await db.execute(stmt_c)
    comp = res_c.scalars().first()
    if not comp:
        raise ValueError("Compromiso no encontrado")

    req_tn = comp.toneladas_comprometidas or Decimal("0.0")

    # Sumar reservas activas
    stmt_res = select(
        func.coalesce(func.sum(StockReservation.cantidad_reserva_kg), Decimal("0.0"))
    ).where(
        StockReservation.cliente_id == cliente_id,
        StockReservation.compromiso_id == comp.id,
        StockReservation.estado.in_(["activa", "parcialmente_asignada"]),
    )
    res_res = await db.execute(stmt_res)
    res_kg = Decimal(str(res_res.scalar_one_or_none() or "0.0"))
    res_tn = (res_kg / Decimal("1000.0")).quantize(Decimal("0.01"))

    # Sumar asignaciones activas directas
    stmt_asig = select(
        func.coalesce(func.sum(StockDeliveryAllocation.cantidad_kg), Decimal("0.0"))
    ).where(
        StockDeliveryAllocation.cliente_id == cliente_id,
        StockDeliveryAllocation.compromiso_id == comp.id,
        StockDeliveryAllocation.estado == "activa",
    )
    res_asig = await db.execute(stmt_asig)
    asig_kg = Decimal(str(res_asig.scalar_one_or_none() or "0.0"))
    asig_tn = (asig_kg / Decimal("1000.0")).quantize(Decimal("0.01"))

    pct_cobertura = (res_tn / req_tn * Decimal("100.0")) if req_tn > Decimal("0.0") else Decimal("0.0")
    pendiente_tn = max(Decimal("0.0"), req_tn - res_tn)

    return {
        "compromiso_id": str(compromiso_id),
        "concepto": comp.concepto,
        "beneficiario": comp.beneficiario,
        "toneladas_requeridas": req_tn,
        "toneladas_reservadas": res_tn,
        "toneladas_asignadas": asig_tn,
        "porcentaje_cobertura": pct_cobertura.quantize(Decimal("0.1")),
        "toneladas_pendientes": pendiente_tn,
    }


async def get_delivery_stock_assignments(
    db: AsyncSession,
    cliente_id: UUID,
    delivery_id: UUID,
) -> Dict[str, Any]:
    """
    Retorna la lista de asignaciones de partidas a una entrega y compara contra las Tn planificadas.
    """
    stmt_d = select(GrainDelivery).where(GrainDelivery.id == delivery_id, GrainDelivery.cliente_id == cliente_id)
    res_d = await db.execute(stmt_d)
    deliv = res_d.scalars().first()
    if not deliv:
        raise ValueError("Entrega no encontrada")

    plan_tn = deliv.toneladas_planificadas or Decimal("0.0")

    stmt_asig = select(StockDeliveryAllocation).where(
        StockDeliveryAllocation.cliente_id == cliente_id,
        StockDeliveryAllocation.grain_delivery_id == deliv.id,
        StockDeliveryAllocation.estado == "activa",
    )
    res_asig = await db.execute(stmt_asig)
    asigs = res_asig.scalars().all()

    asig_kg = sum(a.cantidad_kg for a in asigs)
    asig_tn = (asig_kg / Decimal("1000.0")).quantize(Decimal("0.01"))
    diferencia_tn = asig_tn - plan_tn

    return {
        "delivery_id": str(delivery_id),
        "tracking_number": deliv.tracking_number,
        "toneladas_planificadas": plan_tn,
        "toneladas_asignadas": asig_tn,
        "diferencia_tn": diferencia_tn,
        "supera_plan": diferencia_tn > Decimal("0.0"),
        "asignaciones_count": len(asigs),
    }


def parse_decimal_ar(val: Optional[str]) -> Optional[Decimal]:
    """Parseador seguro de montos con formato numérico argentino (ej. '13,5' o '13.5')."""
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
        return Decimal(s)
    except Exception:
        return None


def validate_humedad_pct(val: Any) -> Optional[Decimal]:
    """
    Valida y parsea el porcentaje de humedad.
    - Opcional (retorna None si no se informa o está vacío).
    - Rango permitido: 5.0% a 35.0% inclusive.
    - Notación argentina permitida ('13,5', '13.5').
    - Lanza ValueError con mensaje de usuario si está fuera de rango o es inválido.
    """
    if val is None:
        return None
    if isinstance(val, Decimal):
        d = val
    else:
        s = str(val).strip()
        if not s:
            return None
        if s.endswith("%"):
            s = s[:-1].strip()
        d = parse_decimal_ar(s)
    if d is None:
        raise ValueError("La humedad debe ser un número válido.")
    if d < Decimal("5.0") or d > Decimal("35.0"):
        raise ValueError("La humedad debe estar entre 5% y 35%. Revisá la unidad o el valor ingresado.")
    return d


def validate_temperatura_c(val: Any) -> Optional[Decimal]:
    """
    Valida y parsea la temperatura en °C.
    - Opcional (retorna None si no se informa o está vacío).
    - Rango permitido: -10.0°C a 60.0°C.
    """
    if val is None:
        return None
    if isinstance(val, Decimal):
        d = val
    else:
        s = str(val).strip()
        if not s:
            return None
        d = parse_decimal_ar(s)
    if d is None:
        raise ValueError("La temperatura debe ser un número válido.")
    if d < Decimal("-10.0") or d > Decimal("60.0"):
        raise ValueError("La temperatura debe estar entre -10°C y 60°C.")
    return d


async def add_quality_measurement_to_partida(
    db: AsyncSession,
    cliente_id: UUID,
    stock_partida_id: UUID,
    measured_at: Optional[datetime] = None,
    humedad_pct_val: Optional[str] = None,
    temperatura_c_val: Optional[str] = None,
    estado_calidad: str = "apto",
    fuente: str = "propia",
    observaciones: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> StockQualityMeasurement:
    """
    Registra una nueva medición histórica de calidad sobre una partida.
    Valida la humedad y la temperatura sin sobrescribir mediciones anteriores.
    """
    stmt = select(StockPartida).where(StockPartida.id == stock_partida_id, StockPartida.cliente_id == cliente_id)
    res = await db.execute(stmt)
    partida = res.scalars().first()
    if not partida:
        raise ValueError("Partida física no encontrada o no autorizada")

    hum_dec = validate_humedad_pct(humedad_pct_val)
    temp_dec = validate_temperatura_c(temperatura_c_val)

    valid_estados = {"apto", "a_revisar", "comprometido", "no_apto", "desconocido"}
    st_calidad = (estado_calidad or "apto").strip().lower()
    if st_calidad not in valid_estados:
        st_calidad = "apto"

    valid_fuentes = {"propia", "acopio", "laboratorio", "estimada", "no_informada"}
    src = (fuente or "propia").strip().lower()
    if src not in valid_fuentes:
        src = "propia"

    m_date = measured_at or datetime.now()

    medicion = StockQualityMeasurement(
        cliente_id=cliente_id,
        stock_partida_id=partida.id,
        measured_at=m_date,
        humedad_pct=hum_dec,
        temperatura_c=temp_dec,
        estado_calidad=st_calidad,
        fuente=src,
        observaciones=observaciones.strip() if observaciones else None,
        created_by_user_id=user_id,
    )

    db.add(medicion)
    await db.commit()
    await db.refresh(medicion)
    return medicion


async def get_partida_quality_history(
    db: AsyncSession,
    cliente_id: UUID,
    stock_partida_id: UUID,
) -> List[Dict[str, Any]]:
    """
    Retorna el historial completo de mediciones de calidad de una partida ordenado por measured_at DESC.
    """
    stmt = (
        select(StockQualityMeasurement)
        .where(
            StockQualityMeasurement.cliente_id == cliente_id,
            StockQualityMeasurement.stock_partida_id == stock_partida_id,
        )
        .order_by(StockQualityMeasurement.measured_at.desc())
    )
    res = await db.execute(stmt)
    measurements = res.scalars().all()
    history = []
    for m in measurements:
        history.append({
            "id": str(m.id),
            "measured_at": m.measured_at.strftime("%d/%m/%Y %H:%M") if m.measured_at else "",
            "humedad_pct": float(m.humedad_pct) if m.humedad_pct is not None else None,
            "temperatura_c": float(m.temperatura_c) if m.temperatura_c is not None else None,
            "estado_calidad": m.estado_calidad,
            "fuente": m.fuente,
            "observaciones": m.observaciones or "",
            "is_invalid_legacy": not is_valid_humidity(m.humedad_pct) if m.humedad_pct is not None else False,
        })
    return history


def is_valid_humidity(hum: Any) -> bool:
    """Verifica si un valor de humedad se encuentra dentro del rango válido 5.0% a 35.0%."""
    if hum is None:
        return False
    if isinstance(hum, Decimal):
        d = hum
    else:
        d = parse_decimal_ar(str(hum))
    if d is None:
        return False
    return Decimal("5.0") <= d <= Decimal("35.0")


async def get_storage_location_occupancy(
    db: AsyncSession,
    cliente_id: UUID,
    location_id: UUID,
) -> Dict[str, Any]:
    """
    Calcula la ocupación física real de una ubicación de guarda desde los saldos físicos derivados
    por movimientos de las partidas activas (no cerradas ni anuladas) asociadas a ella.
    """
    stmt_loc = select(StorageLocation).where(StorageLocation.id == location_id, StorageLocation.cliente_id == cliente_id)
    res_loc = await db.execute(stmt_loc)
    loc = res_loc.scalars().first()
    if not loc:
        raise ValueError("Ubicación no encontrada o no autorizada")

    stmt_p = select(StockPartida).where(
        StockPartida.cliente_id == cliente_id,
        StockPartida.storage_location_id == loc.id,
        StockPartida.estado.notin_(["cerrada", "anulada"]),
    )
    res_p = await db.execute(stmt_p)
    partidas = res_p.scalars().all()

    occupied_kg = Decimal("0.0")
    for p in partidas:
        bal = await get_stock_partida_balance(db, cliente_id, p.id)
        occupied_kg += bal["saldo_fisico_kg"]

    cap_tn = loc.capacidad_nominal_tn
    tipo_norm = loc.tipo.strip().lower()
    requires_capacity = tipo_norm in ["silo_propio", "silobolsa"]

    capacity_kg = cap_tn * Decimal("1000.0") if cap_tn is not None and cap_tn > Decimal("0.0") else None
    available_capacity_kg = (capacity_kg - occupied_kg) if capacity_kg is not None else None

    occupied_tn = (occupied_kg / Decimal("1000.0")).quantize(Decimal("0.01"))
    available_capacity_tn = (available_capacity_kg / Decimal("1000.0")).quantize(Decimal("0.01")) if available_capacity_kg is not None else None

    if capacity_kg is not None and capacity_kg > Decimal("0.0"):
        occupancy_pct = ((occupied_kg / capacity_kg) * Decimal("100.0")).quantize(Decimal("0.1"))
    else:
        occupancy_pct = None

    if requires_capacity and (cap_tn is None or cap_tn <= Decimal("0.0")):
        status = "capacidad_pendiente"
    elif capacity_kg is not None and occupied_kg > capacity_kg:
        status = "sobrecapacidad"
    elif capacity_kg is not None:
        status = "ok"
    else:
        status = "sin_limite"

    return {
        "location_id": str(loc.id),
        "nombre": loc.nombre,
        "tipo": loc.tipo,
        "capacidad_nominal_tn": cap_tn,
        "capacity_kg": capacity_kg,
        "occupied_kg": occupied_kg,
        "occupied_tn": occupied_tn,
        "available_capacity_kg": available_capacity_kg,
        "available_capacity_tn": available_capacity_tn,
        "occupancy_pct": occupancy_pct,
        "estado_capacidad": status,
        "requires_capacity": requires_capacity,
    }


async def confirm_delivery_dispatch(
    db: AsyncSession,
    cliente_id: UUID,
    user_id: Optional[UUID],
    delivery_id: UUID,
    waybill_id: UUID,
    allocations_breakdown: Optional[List[Dict[str, Any]]] = None,
    observaciones: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Confirma el despacho físico de una entrega con carta de porte (Stock 1C).
    Precondiciones:
    - Mismo cliente_id.
    - Delivery existe, no cancelada/liquidada.
    - Waybill existe, estado != 'despachada', peso_neto_origen_kg > 0.
    - Asignaciones activas disponibles cubren o coinciden con peso_neto_origen_kg.
    Acciones:
    1. Lock pesimista en delivery, waybill, allocations y partidas.
    2. Crea 1 o más StockMovement de salida ('despacho_entrega', cantidad_kg < 0).
    3. Reclasifica asignaciones usadas a 'despachada'.
    4. Actualiza GrainWaybill a 'despachada' y GrainDelivery a 'en_transito' (si planificada).
    5. Valida que el saldo físico no quede negativo.
    """
    from app.models import GrainWaybill, StockWeightReconciliation

    # 1. Obtener Delivery con Lock
    stmt_d = (
        select(GrainDelivery)
        .where(GrainDelivery.id == delivery_id, GrainDelivery.cliente_id == cliente_id)
        .with_for_update()
    )
    res_d = await db.execute(stmt_d)
    delivery = res_d.scalars().first()
    if not delivery:
        raise ValueError("Entrega no encontrada o no autorizada.")

    if delivery.estado in ["cancelada", "liquidada"]:
        raise ValueError(f"No se puede despachar una entrega en estado '{delivery.estado}'.")

    # 2. Obtener Waybill con Lock
    stmt_w = (
        select(GrainWaybill)
        .where(GrainWaybill.id == waybill_id, GrainWaybill.entrega_id == delivery_id, GrainWaybill.cliente_id == cliente_id)
        .with_for_update()
    )
    res_w = await db.execute(stmt_w)
    waybill = res_w.scalars().first()
    if not waybill:
        raise ValueError("Carta de porte no encontrada o no pertenece a la entrega.")

    if waybill.estado == "despachada":
        raise ValueError("La carta de porte ya fue despachada anteriormente.")

    peso_neto_kg = waybill.peso_neto_origen_kg
    if not peso_neto_kg or peso_neto_kg <= Decimal("0.0"):
        if waybill.peso_bruto_origen_kg and waybill.tara_kg and waybill.peso_bruto_origen_kg > waybill.tara_kg:
            peso_neto_kg = waybill.peso_bruto_origen_kg - waybill.tara_kg
            waybill.peso_neto_origen_kg = peso_neto_kg
        else:
            raise ValueError("La carta de porte no posee peso neto de origen válido (bruto y tara requeridos).")

    # 3. Obtener Asignaciones Activas de la Entrega con Lock
    stmt_alloc = (
        select(StockDeliveryAllocation)
        .where(
            StockDeliveryAllocation.cliente_id == cliente_id,
            StockDeliveryAllocation.grain_delivery_id == delivery_id,
            StockDeliveryAllocation.estado == "activa",
        )
        .with_for_update()
    )
    res_alloc = await db.execute(stmt_alloc)
    allocations = res_alloc.scalars().all()

    if not allocations:
        raise ValueError("La entrega no posee asignaciones activas de stock para despachar.")

    total_asig_kg = sum((a.cantidad_kg for a in allocations), Decimal("0.0"))
    if total_asig_kg < peso_neto_kg:
        raise ValueError(
            f"El total asignado activo ({total_asig_kg / Decimal('1000.0'):.2f} Tn) "
            f"es insuficiente para cubrir el peso neto de origen ({peso_neto_kg / Decimal('1000.0'):.2f} Tn)."
        )

    # 4. Procesar distribución del consumo de asignaciones por partida
    movements_created = []
    remanente_despacho_kg = peso_neto_kg
    now_dt = datetime.now()

    if allocations_breakdown:
        for item in allocations_breakdown:
            alloc_id = UUID(item["allocation_id"]) if isinstance(item["allocation_id"], str) else item["allocation_id"]
            desp_kg = Decimal(str(item["despachar_kg"]))
            alloc = next((a for a in allocations if a.id == alloc_id), None)
            if not alloc:
                raise ValueError(f"Asignación {alloc_id} no válida o no pertenece a la entrega.")
            if desp_kg > alloc.cantidad_kg:
                raise ValueError(f"La cantidad a despachar ({desp_kg} kg) supera la asignación ({alloc.cantidad_kg} kg).")
            
            bal = await get_stock_partida_balance(db, cliente_id, alloc.stock_partida_id)
            if bal["saldo_fisico_kg"] < desp_kg:
                raise ValueError(f"Stock físico insuficiente en la partida para despachar {desp_kg} kg.")

            mov = StockMovement(
                cliente_id=cliente_id,
                stock_partida_id=alloc.stock_partida_id,
                tipo="despacho_entrega",
                cantidad_kg=-desp_kg,
                fecha_movimiento=now_dt,
                referencia_tipo="grain_delivery",
                referencia_id=str(delivery_id),
                grain_delivery_id=delivery_id,
                grain_waybill_id=waybill_id,
                stock_delivery_allocation_id=alloc.id,
                motivo=f"Despacho Carta de Porte N° {waybill.numero_carta_porte or 'S/N'}",
                observaciones=observaciones or f"Despacho físico confirmación de entrega {delivery.tracking_number}",
                created_by_user_id=user_id,
            )
            db.add(mov)
            await db.flush()

            alloc.estado = "despachada"
            alloc.despatched_at = now_dt
            alloc.despatched_by_user_id = user_id
            alloc.stock_movement_id = mov.id
            movements_created.append(mov)
    else:
        for alloc in allocations:
            if remanente_despacho_kg <= Decimal("0.0"):
                break
            desp_kg = min(alloc.cantidad_kg, remanente_despacho_kg)

            bal = await get_stock_partida_balance(db, cliente_id, alloc.stock_partida_id)
            if bal["saldo_fisico_kg"] < desp_kg:
                raise ValueError(f"Stock físico insuficiente en la partida para despachar {desp_kg} kg.")

            mov = StockMovement(
                cliente_id=cliente_id,
                stock_partida_id=alloc.stock_partida_id,
                tipo="despacho_entrega",
                cantidad_kg=-desp_kg,
                fecha_movimiento=now_dt,
                referencia_tipo="grain_delivery",
                referencia_id=str(delivery_id),
                grain_delivery_id=delivery_id,
                grain_waybill_id=waybill_id,
                stock_delivery_allocation_id=alloc.id,
                motivo=f"Despacho Carta de Porte N° {waybill.numero_carta_porte or 'S/N'}",
                observaciones=observaciones or f"Despacho físico confirmación de entrega {delivery.tracking_number}",
                created_by_user_id=user_id,
            )
            db.add(mov)
            await db.flush()

            remanente_despacho_kg -= desp_kg
            alloc.estado = "despachada"
            alloc.despatched_at = now_dt
            alloc.despatched_by_user_id = user_id
            alloc.stock_movement_id = mov.id
            movements_created.append(mov)

    # 5. Actualizar Estados de Carta y Entrega
    waybill.estado = "despachada"
    waybill.despatched_at = now_dt
    waybill.despatched_by_user_id = user_id

    if delivery.estado == "planificada":
        delivery.estado = "en_transito"
    delivery.kg_neto_origen_total = peso_neto_kg

    await db.commit()

    return {
        "delivery_id": str(delivery_id),
        "waybill_id": str(waybill_id),
        "peso_despachado_kg": peso_neto_kg,
        "movimientos_creados": len(movements_created),
        "nuevo_estado_entrega": delivery.estado,
        "nuevo_estado_carta": waybill.estado,
    }


async def record_delivery_reception_and_reconciliation(
    db: AsyncSession,
    cliente_id: UUID,
    user_id: Optional[UUID],
    delivery_id: UUID,
    waybill_id: UUID,
    peso_recibido_destino_kg: Decimal,
    observaciones: Optional[str] = None,
    fecha_recepcion: Optional[datetime] = None,
    referencia_ticket_destino: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Registra el peso recibido en destino y evalúa conciliación (Stock 1C).
    NO genera salida física adicional de stock.
    Calcula diferencia = recibido_destino - neto_origen.
    Si supera umbral de política (1.0% o 300 kg), marca estado 'pendiente'.
    Si está dentro de tolerancia, marca estado 'dentro_tolerancia'.
    """
    from app.models import GrainWaybill, StockWeightReconciliation, GrainDelivery

    if peso_recibido_destino_kg is None or peso_recibido_destino_kg <= Decimal("0.0"):
        raise ValueError("El peso recibido en destino debe ser un valor numérico mayor a 0 kg.")

    stmt_w = (
        select(GrainWaybill)
        .where(GrainWaybill.id == waybill_id, GrainWaybill.entrega_id == delivery_id, GrainWaybill.cliente_id == cliente_id)
        .with_for_update()
    )
    res_w = await db.execute(stmt_w)
    waybill = res_w.scalars().first()
    if not waybill:
        raise ValueError("Carta de porte no encontrada.")

    stmt_d = (
        select(GrainDelivery)
        .where(GrainDelivery.id == delivery_id, GrainDelivery.cliente_id == cliente_id)
        .with_for_update()
    )
    res_d = await db.execute(stmt_d)
    delivery = res_d.scalars().first()
    if not delivery:
        raise ValueError("Entrega no encontrada.")

    if waybill.estado == "recibida" and waybill.peso_recibido_destino_kg is not None:
        raise ValueError("La carta de porte ya cuenta con una recepción registrada. Usá la acción de conciliación de pesaje para ajustar diferencias.")

    if waybill.estado not in ["despachada", "en_transito", "recibida"]:
        raise ValueError("La carta de porte debe estar despachada antes de poder registrar la recepción en destino.")

    peso_origen_kg = waybill.peso_neto_origen_kg or Decimal("0.0")
    if peso_origen_kg <= Decimal("0.0"):
        raise ValueError("La carta de porte no cuenta con peso neto de origen para calcular la diferencia.")

    diferencia_kg = peso_recibido_destino_kg - peso_origen_kg
    diferencia_pct = (diferencia_kg / peso_origen_kg) * Decimal("100.0")

    rec_dt = fecha_recepcion or datetime.now()

    waybill.peso_recibido_destino_kg = peso_recibido_destino_kg
    waybill.diferencia_kg = diferencia_kg
    waybill.diferencia_pct = diferencia_pct.quantize(Decimal("0.01"))
    waybill.estado = "recibida"
    waybill.fecha_recepcion = rec_dt
    if referencia_ticket_destino and referencia_ticket_destino.strip():
        waybill.referencia_ticket_destino = referencia_ticket_destino.strip()

    if delivery.estado in ["planificada", "en_transito"]:
        delivery.estado = "recibida"
    delivery.kg_recibido_total = peso_recibido_destino_kg
    delivery.diferencia_total_kg = diferencia_kg
    delivery.diferencia_total_pct = diferencia_pct.quantize(Decimal("0.01"))
    delivery.fecha_recepcion = rec_dt

    abs_pct = abs(diferencia_pct)
    abs_kg = abs(diferencia_kg)

    threshold_pct = Decimal("1.0")
    threshold_kg = Decimal("300.0")

    if abs_pct <= threshold_pct or abs_kg <= threshold_kg:
        estado_reconciliacion = "dentro_tolerancia"
    else:
        estado_reconciliacion = "pendiente"

    stmt_rec = select(StockWeightReconciliation).where(
        StockWeightReconciliation.cliente_id == cliente_id,
        StockWeightReconciliation.grain_waybill_id == waybill_id,
    ).with_for_update()
    res_rec = await db.execute(stmt_rec)
    reconciliation = res_rec.scalars().first()

    if not reconciliation:
        reconciliation = StockWeightReconciliation(
            cliente_id=cliente_id,
            grain_delivery_id=delivery_id,
            grain_waybill_id=waybill_id,
            peso_neto_origen_kg=peso_origen_kg,
            peso_recibido_destino_kg=peso_recibido_destino_kg,
            diferencia_kg=diferencia_kg,
            diferencia_pct=diferencia_pct.quantize(Decimal("0.01")),
            estado=estado_reconciliacion,
            resolucion_observaciones=observaciones,
        )
        db.add(reconciliation)
    else:
        reconciliation.peso_neto_origen_kg = peso_origen_kg
        reconciliation.peso_recibido_destino_kg = peso_recibido_destino_kg
        reconciliation.diferencia_kg = diferencia_kg
        reconciliation.diferencia_pct = diferencia_pct.quantize(Decimal("0.01"))
        reconciliation.estado = estado_reconciliacion
        if observaciones:
            reconciliation.resolucion_observaciones = observaciones

    await db.commit()

    return {
        "delivery_id": str(delivery_id),
        "waybill_id": str(waybill_id),
        "reconciliation_id": str(reconciliation.id),
        "peso_recibido_destino_kg": peso_recibido_destino_kg,
        "diferencia_kg": diferencia_kg,
        "diferencia_pct": diferencia_pct.quantize(Decimal("0.01")),
        "estado_reconciliacion": estado_reconciliacion,
    }


async def resolve_weight_reconciliation(
    db: AsyncSession,
    cliente_id: UUID,
    user_id: Optional[UUID],
    reconciliation_id: UUID,
    resolucion_tipo: str,
    observaciones: str,
    ajuste_cantidad_valor: Optional[Decimal] = None,
    stock_partida_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """
    Resuelve explícitamente una conciliación de pesaje (Stock 1C).
    Tipos de resolución:
    - 'aceptada_sin_ajuste': No modifica stock físico. Marca estado 'resuelta'.
    - 'ajuste_inventario': Crea un StockMovement explícito 'ajuste_diferencia_pesaje'. Valida saldo no negativo.
    - 'diferencia_documentada': Documenta observaciones sin modificar físico. Marca 'resuelta'.
    - 'anulada': Válida si la entrega fue anulada. Marca 'anulada'.
    """
    from app.models import StockWeightReconciliation

    valid_types = ["aceptada_sin_ajuste", "ajuste_inventario", "diferencia_documentada", "anulada"]
    if resolucion_tipo not in valid_types:
        raise ValueError(f"Tipo de resolución '{resolucion_tipo}' no válido. Opciones: {', '.join(valid_types)}.")

    if not observaciones or not observaciones.strip():
        raise ValueError("Las observaciones de resolución son obligatorias.")

    stmt_rec = (
        select(StockWeightReconciliation)
        .where(StockWeightReconciliation.id == reconciliation_id, StockWeightReconciliation.cliente_id == cliente_id)
        .with_for_update()
    )
    res_rec = await db.execute(stmt_rec)
    reconciliation = res_rec.scalars().first()
    if not reconciliation:
        raise ValueError("Registro de conciliación no encontrado o no autorizado.")

    if reconciliation.estado in ["resuelta", "anulada"] and resolucion_tipo != "anulada":
        raise ValueError(f"La conciliación ya fue resuelta anteriormente con estado '{reconciliation.estado}'.")

    now_dt = datetime.now()
    mov_created = None

    if resolucion_tipo == "ajuste_inventario":
        if not ajuste_cantidad_valor or ajuste_cantidad_valor == Decimal("0.0"):
            raise ValueError("Para 'ajuste_inventario' debe indicar la cantidad de ajuste en kg (positiva o negativa).")
        if not stock_partida_id:
            raise ValueError("Para 'ajuste_inventario' debe especificar la partida física a ajustar.")

        bal = await get_stock_partida_balance(db, cliente_id, stock_partida_id)
        nuevo_saldo = bal["saldo_fisico_kg"] + ajuste_cantidad_valor
        if nuevo_saldo < Decimal("0.0"):
            raise ValueError(f"El ajuste propuesto ({ajuste_cantidad_valor} kg) dejaría la partida con saldo negativo.")

        mov_created = StockMovement(
            cliente_id=cliente_id,
            stock_partida_id=stock_partida_id,
            tipo="ajuste_diferencia_pesaje",
            cantidad_kg=ajuste_cantidad_valor,
            fecha_movimiento=now_dt,
            referencia_tipo="weight_reconciliation",
            referencia_id=str(reconciliation.id),
            grain_delivery_id=reconciliation.grain_delivery_id,
            grain_waybill_id=reconciliation.grain_waybill_id,
            motivo=f"Ajuste por conciliación de pesaje ({reconciliation.diferencia_kg} kg)",
            observaciones=observaciones,
            created_by_user_id=user_id,
        )
        db.add(mov_created)
        await db.flush()
        reconciliation.stock_movement_id = mov_created.id

    reconciliation.estado = "anulada" if resolucion_tipo == "anulada" else "resuelta"
    reconciliation.resolucion_tipo = resolucion_tipo
    reconciliation.resolucion_observaciones = observaciones
    reconciliation.resolved_at = now_dt
    reconciliation.resolved_by_user_id = user_id

    await db.commit()

    return {
        "reconciliation_id": str(reconciliation.id),
        "resolucion_tipo": resolucion_tipo,
        "nuevo_estado": reconciliation.estado,
        "movimiento_ajuste_id": str(mov_created.id) if mov_created else None,
    }


def formato_ar_decimal(val: Any) -> str:
    """
    Formatea un valor numérico a formato argentino con 2 decimales:
    18.0 -> "18,00"
    1234.56 -> "1.234,56"
    """
    if val is None:
        return "0,00"
    if isinstance(val, (float, int, str)):
        try:
            val = Decimal(str(val))
        except Exception:
            return "0,00"
    if not isinstance(val, Decimal):
        return "0,00"
    val_quant = val.quantize(Decimal("0.01"))
    parts = f"{val_quant:f}".split(".")
    integer_part = parts[0]
    decimal_part = parts[1] if len(parts) > 1 else "00"
    negative = integer_part.startswith("-")
    if negative:
        integer_part = integer_part[1:]
    
    formatted_int = ""
    for i, char in enumerate(reversed(integer_part)):
        if i > 0 and i % 3 == 0:
            formatted_int = "." + formatted_int
        formatted_int = char + formatted_int
    
    if negative:
        formatted_int = "-" + formatted_int
        
    return f"{formatted_int},{decimal_part}"


def _format_vencimiento(venc: Any) -> str:
    if not venc:
        return "Sin vencimiento informado"
    if isinstance(venc, (date, datetime)):
        v_date = venc.date() if isinstance(venc, datetime) else venc
        return f"Vence: {v_date.strftime('%d/%m/%Y')}"
    if isinstance(venc, str):
        venc_clean = venc.strip()
        if not venc_clean:
            return "Sin vencimiento informado"
        try:
            dt = datetime.strptime(venc_clean[:10], "%Y-%m-%d")
            return f"Vence: {dt.strftime('%d/%m/%Y')}"
        except ValueError:
            return f"Vence: {venc_clean}"
    return "Sin vencimiento informado"


def build_commitment_display_label(
    compromiso: Any,
    *,
    saldo_tn: Decimal | float | int | None = None,
) -> str:
    """
    Construye una etiqueta descriptiva, única y consistente para compromisos comerciales.
    Formato preferido: '[TIPO] · [CONTRAPARTE/BENEFICIARIO] · [REFERENCIA/CONCEPTO] · Saldo: [X,XX Tn] · Vence: [DD/MM/AAAA]'
    Ejemplo: 'Canje · Murature · Semilla maíz 2026/27 · Saldo: 18,00 Tn · Vence: 30/09/2026'
    Fallback robusto: 'Compromiso sin referencia · Saldo: 18,00 Tn · ID: ABCD'
    """
    if compromiso is None:
        return "Compromiso no especificado"

    def _get_val(attr: str, default: Any = None) -> Any:
        if isinstance(compromiso, dict):
            return compromiso.get(attr, default)
        return getattr(compromiso, attr, default)

    c_id = str(_get_val("id", ""))
    short_id = c_id[-4:].upper() if len(c_id) >= 4 else "N/A"

    tipo_raw = _get_val("tipo_compromiso")
    if hasattr(tipo_raw, "value"):
        tipo_str = str(tipo_raw.value)
    else:
        tipo_str = str(tipo_raw or "")

    tipo_lower = tipo_str.lower()
    if "alquiler" in tipo_lower or "arrendamiento" in tipo_lower:
        tipo_lbl = "Alquiler"
    elif "canje" in tipo_lower:
        tipo_lbl = "Canje"
    elif tipo_str.strip():
        tipo_lbl = tipo_str.replace("_", " ").title()
    else:
        tipo_lbl = "Compromiso"

    beneficiario = _get_val("beneficiario")
    ben_has_value = bool(beneficiario and str(beneficiario).strip())
    ben_str = str(beneficiario).strip() if ben_has_value else "Contraparte no informada"

    concepto = _get_val("concepto")
    conc_has_value = bool(concepto and str(concepto).strip())
    conc_str = str(concepto).strip() if conc_has_value else "Sin referencia"

    if saldo_tn is None:
        st_val = _get_val("toneladas_comprometidas", Decimal("0.0"))
        if st_val is not None:
            try:
                saldo_tn = Decimal(str(st_val))
            except Exception:
                saldo_tn = Decimal("0.0")
        else:
            saldo_tn = Decimal("0.0")
    elif not isinstance(saldo_tn, Decimal):
        try:
            saldo_tn = Decimal(str(saldo_tn))
        except Exception:
            saldo_tn = Decimal("0.0")

    saldo_fmt = formato_ar_decimal(saldo_tn)
    saldo_lbl = f"Saldo: {saldo_fmt} Tn"

    venc_val = _get_val("fecha_vencimiento")
    venc_lbl = _format_vencimiento(venc_val)

    cumplido = bool(_get_val("cumplido", False))

    venc_date = None
    if isinstance(venc_val, (date, datetime)):
        venc_date = venc_val.date() if isinstance(venc_val, datetime) else venc_val
    elif isinstance(venc_val, str) and venc_val.strip():
        try:
            venc_date = datetime.strptime(venc_val.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            pass

    estado_prefix = ""
    if cumplido:
        estado_prefix = "[Cumplido] "
    elif venc_date and venc_date < date.today():
        estado_prefix = "[Vencido] "

    # Fallback robusto si faltan concepto y contraparte
    if not ben_has_value and not conc_has_value:
        return f"{estado_prefix}Compromiso sin referencia · {saldo_lbl} · ID: {short_id}"

    return f"{estado_prefix}{tipo_lbl} · {ben_str} · {conc_str} · {saldo_lbl} · {venc_lbl}"


async def get_compromisos_saldos_map(
    db: AsyncSession,
    cliente_id: UUID,
) -> Dict[UUID, Decimal]:
    """
    Calcula de manera eficiente (sin N+1 queries) el saldo pendiente (no reservado)
    de cada compromiso comercial perteneciente al cliente especificado.
    """
    stmt = select(CompromisoGrano.id, CompromisoGrano.toneladas_comprometidas).where(CompromisoGrano.cliente_id == cliente_id)
    res = await db.execute(stmt)
    saldos = {row.id: Decimal(str(row.toneladas_comprometidas or "0.0")) for row in res.all()}

    if not saldos:
        return {}

    stmt_res = select(
        StockReservation.compromiso_id,
        func.coalesce(func.sum(StockReservation.cantidad_reserva_kg), Decimal("0.0")).label("res_kg")
    ).where(
        StockReservation.cliente_id == cliente_id,
        StockReservation.estado.in_(["activa", "parcialmente_asignada"])
    ).group_by(StockReservation.compromiso_id)

    res_res = await db.execute(stmt_res)
    for row in res_res.all():
        if row.compromiso_id in saldos:
            res_tn = Decimal(str(row.res_kg or "0.0")) / Decimal("1000.0")
            saldos[row.compromiso_id] = max(Decimal("0.0"), saldos[row.compromiso_id] - res_tn)

    return saldos


def format_compromiso_dict(
    compromiso: Any,
    saldo_tn: Decimal | float | int | None = None,
) -> Dict[str, Any]:
    """
    Formatea un objeto o diccionario de compromiso comercial a un diccionario estandarizado para Jinja context.
    """
    def _get_val(attr: str, default: Any = None) -> Any:
        if isinstance(compromiso, dict):
            return compromiso.get(attr, default)
        return getattr(compromiso, attr, default)

    c_id = _get_val("id", "")
    c_cumplido = _get_val("cumplido", False)
    c_cultivo = _get_val("cultivo", "")
    c_venc = _get_val("fecha_vencimiento", None)
    c_concepto = _get_val("concepto", "")
    c_beneficiario = _get_val("beneficiario", "")
    c_tn = _get_val("toneladas_comprometidas", Decimal("0.0"))

    if saldo_tn is None:
        saldo_tn = Decimal(str(c_tn)) if c_tn is not None else Decimal("0.0")
    elif not isinstance(saldo_tn, Decimal):
        try:
            saldo_tn = Decimal(str(saldo_tn))
        except Exception:
            saldo_tn = Decimal("0.0")

    label = build_commitment_display_label(compromiso, saldo_tn=saldo_tn)

    venc_str = ""
    if isinstance(c_venc, (date, datetime)):
        venc_str = c_venc.strftime("%d/%m/%Y")
    elif isinstance(c_venc, str):
        venc_str = c_venc

    return {
        "id": str(c_id) if c_id else "",
        "label": label,
        "saldo_tn": float(saldo_tn),
        "estado": "cumplido" if c_cumplido else "pendiente",
        "cultivo": str(c_cultivo or ""),
        "fecha_vencimiento": venc_str,
        "concepto": str(c_concepto or ""),
        "beneficiario": str(c_beneficiario or ""),
        "toneladas_comprometidas": float(c_tn) if c_tn is not None else 0.0,
    }

