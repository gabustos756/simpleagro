#!/usr/bin/env python3
from __future__ import annotations

"""
Herramienta CLI de mantenimiento y limpieza segura de datos QA-MOCK para entorno local (EduAgro).

Uso:
  # Modo predeterminado (Dry-Run seguro):
  python scripts/cleanup_qa_mock_data.py --environment local --prefix QA-MOCK- --dry-run

  # Modo de eliminación real (exige confirmación explicita):
  python scripts/cleanup_qa_mock_data.py --environment local --prefix QA-MOCK- --confirm-delete --confirm-phrase DELETE_QA_MOCK_LOCAL
"""

import sys
import os
import argparse
import asyncio
from datetime import datetime
from typing import Dict, List, Set, Any, Tuple
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, delete, func, or_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Asegurar path de la app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import DATABASE_URL
from app.models import (
    StorageLocation,
    StockPartida,
    StockMovement,
    StockQualityMeasurement,
    StockReservation,
    StockDeliveryAllocation,
    StockWeightReconciliation,
    CompromisoGrano,
    FreightQuote,
    GrainDelivery,
    GrainWaybill,
)


def mask_db_url(url: str) -> str:
    """Mantiene ocultas las credenciales de la cadena de conexión."""
    parsed = urlparse(url)
    if parsed.password:
        return url.replace(parsed.password, "******")
    return url


def is_local_db_host(url: str) -> bool:
    """Verifica si el host de la base de datos es local."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    local_hosts = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
    if hostname in local_hosts or not hostname:
        return True
    if "sqlite" in parsed.scheme:
        return True
    return False


async def run_qa_mock_cleanup(
    *,
    environment: str,
    prefix: str,
    dry_run: bool,
    confirm_delete: bool,
    confirm_phrase: str,
    output_report_dir: str = "docs/qa",
) -> Dict[str, Any]:
    """
    Ejecuta el protocolo de análisis y limpieza segura de datos QA-MOCK.
    """
    # 1. Validaciones de Seguridad Estrictas
    if environment.lower() != "local":
        raise PermissionError(f"Entorno denegado: Se requiere '--environment local', pero se especificó '{environment}'.")

    if prefix != "QA-MOCK-":
        raise PermissionError(f"Prefijo denegado: El prefijo de limpieza debe ser exactamente 'QA-MOCK-', se recibió '{prefix}'.")

    app_env = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "local")).lower()
    if app_env in ["production", "prod", "staging"]:
        raise PermissionError(f"Seguridad: Se aborta la ejecución porque el entorno del sistema está configurado como '{app_env}'.")

    if not is_local_db_host(DATABASE_URL):
        raise PermissionError("Seguridad: La conexión a base de datos apunta a un host no reconocido como entorno local.")

    if not dry_run and confirm_delete:
        if confirm_phrase != "DELETE_QA_MOCK_LOCAL":
            raise ValueError("Confirmación denegada: Para ejecutar el borrado real se exige pasar '--confirm-phrase DELETE_QA_MOCK_LOCAL'.")

    mode_label = "DRY-RUN (Simulación)" if dry_run else "DELETE REAL (Ejecución Destructiva)"
    print(f"=== INICIANDO LIMPIEZA QA-MOCK EN MODO {mode_label} ===")
    print(f"Base de datos: {mask_db_url(DATABASE_URL)}")
    print(f"Prefijo filtrado: '{prefix}'")
    print(f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    report_summary: Dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "environment": environment,
        "mode": mode_label,
        "prefix": prefix,
        "db_url_masked": mask_db_url(DATABASE_URL),
        "counts": {},
        "affected_ids": {},
        "blocked_records": [],
        "errors": [],
    }

    async with session_factory() as session:
        try:
            # 2. Identificación de Entidades Primarias QA por prefijo
            stmt_loc = select(StorageLocation.id, StorageLocation.nombre).where(StorageLocation.nombre.startswith(prefix))
            res_loc = (await session.execute(stmt_loc)).all()
            qa_loc_ids = {row.id for row in res_loc}

            stmt_comp = select(CompromisoGrano.id, CompromisoGrano.concepto).where(CompromisoGrano.concepto.startswith(prefix))
            res_comp = (await session.execute(stmt_comp)).all()
            qa_comp_ids = {row.id for row in res_comp}

            stmt_quote = select(FreightQuote.id, FreightQuote.destination_name).where(FreightQuote.destination_name.startswith(prefix))
            res_quote = (await session.execute(stmt_quote)).all()
            qa_quote_ids = {row.id for row in res_quote}

            # Entregas QA: por tracking/acopio o vinculadas a compromisos/cotizaciones QA
            stmt_del = select(GrainDelivery.id, GrainDelivery.tracking_number).where(
                or_(
                    GrainDelivery.tracking_number.startswith(prefix),
                    GrainDelivery.acopio_receptor.startswith(prefix),
                    GrainDelivery.compromiso_id.in_(qa_comp_ids) if qa_comp_ids else False,
                    GrainDelivery.freight_quote_id.in_(qa_quote_ids) if qa_quote_ids else False,
                )
            )
            res_del = (await session.execute(stmt_del)).all()
            qa_del_ids = {row.id for row in res_del}

            # Cartas QA: por número o vinculadas a entregas QA
            stmt_way = select(GrainWaybill.id, GrainWaybill.numero_carta_porte).where(
                or_(
                    GrainWaybill.numero_carta_porte.startswith(prefix),
                    GrainWaybill.entrega_id.in_(qa_del_ids) if qa_del_ids else False,
                )
            )
            res_way = (await session.execute(stmt_way)).all()
            qa_way_ids = {row.id for row in res_way}

            # Partidas QA: vinculadas a ubicaciones QA u observaciones QA
            stmt_part = select(StockPartida.id, StockPartida.tracking_number).where(
                or_(
                    StockPartida.storage_location_id.in_(qa_loc_ids) if qa_loc_ids else False,
                    StockPartida.observaciones.startswith(prefix),
                )
            )
            res_part = (await session.execute(stmt_part)).all()
            qa_part_ids = {row.id for row in res_part}

            # Asociaciones y movimientos QA
            stmt_res = select(StockReservation.id).where(
                or_(
                    StockReservation.compromiso_id.in_(qa_comp_ids) if qa_comp_ids else False,
                    StockReservation.stock_partida_id.in_(qa_part_ids) if qa_part_ids else False,
                )
            )
            qa_res_ids = set((await session.execute(stmt_res)).scalars().all())

            stmt_asig = select(StockDeliveryAllocation.id).where(
                or_(
                    StockDeliveryAllocation.grain_delivery_id.in_(qa_del_ids) if qa_del_ids else False,
                    StockDeliveryAllocation.stock_partida_id.in_(qa_part_ids) if qa_part_ids else False,
                )
            )
            qa_asig_ids = set((await session.execute(stmt_asig)).scalars().all())

            stmt_rec = select(StockWeightReconciliation.id).where(
                or_(
                    StockWeightReconciliation.grain_delivery_id.in_(qa_del_ids) if qa_del_ids else False,
                    StockWeightReconciliation.grain_waybill_id.in_(qa_way_ids) if qa_way_ids else False,
                )
            )
            qa_rec_ids = set((await session.execute(stmt_rec)).scalars().all())

            stmt_meas = select(StockQualityMeasurement.id).where(
                StockQualityMeasurement.stock_partida_id.in_(qa_part_ids) if qa_part_ids else False
            )
            qa_meas_ids = set((await session.execute(stmt_meas)).scalars().all())

            stmt_mov = select(StockMovement.id).where(
                or_(
                    StockMovement.stock_partida_id.in_(qa_part_ids) if qa_part_ids else False,
                    StockMovement.grain_delivery_id.in_(qa_del_ids) if qa_del_ids else False,
                    StockMovement.grain_waybill_id.in_(qa_way_ids) if qa_way_ids else False,
                )
            )
            qa_mov_ids = set((await session.execute(stmt_mov)).scalars().all())

            # 3. Verificación de Protección (Registros Bloqueados por relación activa no-QA)
            # Verificar si alguna GrainDelivery no-QA referencia una partida o compromiso QA
            blocked_reasons: List[str] = []
            if qa_part_ids:
                stmt_check_alloc = select(StockDeliveryAllocation.id, StockDeliveryAllocation.grain_delivery_id).where(
                    StockDeliveryAllocation.stock_partida_id.in_(qa_part_ids),
                    StockDeliveryAllocation.grain_delivery_id.not_in(qa_del_ids) if qa_del_ids else True,
                )
                res_check_alloc = (await session.execute(stmt_check_alloc)).all()
                for r in res_check_alloc:
                    msg = f"Allocation {r.id} vincula Partida QA con Entrega Real {r.grain_delivery_id}"
                    blocked_reasons.append(msg)
                    report_summary["blocked_records"].append(msg)

            if blocked_reasons:
                print("⚠️ ATENCIÓN: Se detectaron registros QA bloqueados por vinculación con datos reales:")
                for b in blocked_reasons:
                    print(f"  - {b}")
                if not dry_run:
                    raise RuntimeError("Abortando eliminación real: existen registros QA vinculados a entidades reales no QA.")

            # Conteo de Entidades a Afectar
            counts = {
                "StockWeightReconciliation": len(qa_rec_ids),
                "StockMovement": len(qa_mov_ids),
                "GrainWaybill": len(qa_way_ids),
                "StockDeliveryAllocation": len(qa_asig_ids),
                "StockReservation": len(qa_res_ids),
                "GrainDelivery": len(qa_del_ids),
                "FreightQuote": len(qa_quote_ids),
                "CompromisoGrano": len(qa_comp_ids),
                "StockQualityMeasurement": len(qa_meas_ids),
                "StockPartida": len(qa_part_ids),
                "StorageLocation": len(qa_loc_ids),
            }
            report_summary["counts"] = counts
            report_summary["affected_ids"] = {
                "StorageLocation": [str(i) for i in qa_loc_ids],
                "CompromisoGrano": [str(i) for i in qa_comp_ids],
                "FreightQuote": [str(i) for i in qa_quote_ids],
                "GrainDelivery": [str(i) for i in qa_del_ids],
                "GrainWaybill": [str(i) for i in qa_way_ids],
                "StockPartida": [str(i) for i in qa_part_ids],
            }

            print("Resumen de Registros QA Identificados:")
            for entity, count in counts.items():
                print(f"  - {entity}: {count}")

            # 4. Borrado Real si se pasó --confirm-delete (Orden Inverso FK)
            if not dry_run and confirm_delete:
                print("\nEjecutando borrado en base de datos en transacción...")

                if qa_rec_ids:
                    await session.execute(delete(StockWeightReconciliation).where(StockWeightReconciliation.id.in_(qa_rec_ids)))
                if qa_mov_ids:
                    await session.execute(delete(StockMovement).where(StockMovement.id.in_(qa_mov_ids)))
                if qa_way_ids:
                    await session.execute(delete(GrainWaybill).where(GrainWaybill.id.in_(qa_way_ids)))
                if qa_asig_ids:
                    await session.execute(delete(StockDeliveryAllocation).where(StockDeliveryAllocation.id.in_(qa_asig_ids)))
                if qa_res_ids:
                    await session.execute(delete(StockReservation).where(StockReservation.id.in_(qa_res_ids)))
                if qa_del_ids:
                    await session.execute(delete(GrainDelivery).where(GrainDelivery.id.in_(qa_del_ids)))
                if qa_quote_ids:
                    await session.execute(delete(FreightQuote).where(FreightQuote.id.in_(qa_quote_ids)))
                if qa_comp_ids:
                    await session.execute(delete(CompromisoGrano).where(CompromisoGrano.id.in_(qa_comp_ids)))
                if qa_meas_ids:
                    await session.execute(delete(StockQualityMeasurement).where(StockQualityMeasurement.id.in_(qa_meas_ids)))
                if qa_part_ids:
                    await session.execute(delete(StockPartida).where(StockPartida.id.in_(qa_part_ids)))
                if qa_loc_ids:
                    await session.execute(delete(StorageLocation).where(StorageLocation.id.in_(qa_loc_ids)))

                await session.commit()
                print("✅ Borrado de registros QA completado y commiteado exitosamente.")
            else:
                print("\nℹ️ Modo Dry-run finalizado sin realizar cambios en la base de datos.")

        except Exception as err:
            await session.rollback()
            report_summary["errors"].append(str(err))
            print(f"❌ ERROR durante la ejecución: {err}")
            raise
        finally:
            await engine.dispose()

    # 5. Escritura de Reporte de Auditoría
    os.makedirs(output_report_dir, exist_ok=True)
    report_filename = f"qa-mock-cleanup-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    report_path = os.path.join(output_report_dir, report_filename)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Reporte de Limpieza de Datos QA-MOCK\n\n")
        f.write(f"- **Timestamp**: `{report_summary['timestamp']}`\n")
        f.write(f"- **Entorno**: `{report_summary['environment']}`\n")
        f.write(f"- **Modo**: `{report_summary['mode']}`\n")
        f.write(f"- **Prefijo**: `{report_summary['prefix']}`\n")
        f.write(f"- **Base de datos**: `{report_summary['db_url_masked']}`\n\n")
        f.write(f"## Registros Identificados\n\n")
        for ent, count in report_summary["counts"].items():
            f.write(f"- **{ent}**: {count}\n")
        f.write(f"\n## Registros Bloqueados\n\n")
        if report_summary["blocked_records"]:
            for b in report_summary["blocked_records"]:
                f.write(f"- ⚠️ `{b}`\n")
        else:
            f.write("Ninguno. Todos los registros identificados son 100% aislados QA.\n")
        f.write(f"\n## Errores\n\n")
        if report_summary["errors"]:
            for e in report_summary["errors"]:
                f.write(f"- ❌ `{e}`\n")
        else:
            f.write("Sin errores.\n")

    print(f"Reporte de auditoría generado en: {report_path}")
    return report_summary


def main():
    parser = argparse.ArgumentParser(description="Herramienta de limpieza segura de datos QA-MOCK (EduAgro)")
    parser.add_argument("--environment", required=True, help="Entorno de ejecución (debe ser 'local')")
    parser.add_argument("--prefix", required=True, help="Prefijo de filtrado (debe ser 'QA-MOCK-')")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Simula el proceso sin borrar datos (por defecto True)")
    parser.add_argument("--confirm-delete", action="store_true", default=False, help="Habilita la eliminación real")
    parser.add_argument("--confirm-phrase", default="", help="Frase de confirmación obligatoria para delete real ('DELETE_QA_MOCK_LOCAL')")

    args = parser.parse_args()

    # Si se pasa --confirm-delete, desactivar el modo dry-run por defecto
    dry_run = not args.confirm_delete

    try:
        asyncio.run(
            run_qa_mock_cleanup(
                environment=args.environment,
                prefix=args.prefix,
                dry_run=dry_run,
                confirm_delete=args.confirm_delete,
                confirm_phrase=args.confirm_phrase,
            )
        )
    except Exception as e:
        sys.exit(1)


if __name__ == "__main__":
    main()
