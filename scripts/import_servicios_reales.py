#!/usr/bin/env python3
"""
scripts/import_servicios_reales.py
--------------------------------------------------------------------------------
Script de importación automatizada de Servicios Operativos de la Familia Matteuda.
Diseñado para ejecutarse en entorno local o en la VPS de producción.

Lee las 5 facturas reales en 'docs/servicios/':
1. UCOOPGAS.pdf              -> Gas Propano a Granel (Zeppelín Casco)
2. claro.pdf                 -> Flota Móvil e Internet (6 Líneas) [Débito Automático]
3. 25500000001002100018387.pdf -> Luz Rural - Coop. Laguna Larga (Suministro 2550000)
4. 25500000001002100018388.pdf -> Tasa Hospital Municipal - Coop. Laguna Larga (Suministro 2550000)
5. 999992210002002000128244.pdf -> Internet Fibra Óptica 10/5 - Coop. Laguna Larga (Adm. Laguna Larga)

Para cada servicio:
- Crea el registro en 'servicios_instalados' (idempotente: evita duplicados por concepto).
- Copia y valida el archivo PDF en el almacenamiento seguro de EduAgro ('data/uploads/documents/').
- Registra el 'ServiceDocument' oficial para visualización y descarga directa en la plataforma.
- Genera el primer 'ServicioVencimiento' para seguimiento contable y control de pagos.
"""

import asyncio
import hashlib
import logging
import os
import shutil
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

# Añadir directorio raíz al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select, or_
from app.database import AsyncSessionLocal, engine
from app.models import Cliente, Campo, ServicioInstalado, ServicioVencimiento, ServiceDocument
from app.enums import (
    TipoServicioEnum,
    FrecuenciaPagoEnum,
    FormaPagoServicioEnum,
    EstadoServicioInstaladoEnum,
    EstadoServicio,
    DocumentTypeEnum,
)
from app.services.document_storage import get_storage_root

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import_servicios")


# DEFINICIÓN EXACTA DE LOS SERVICIOS EXTRAÍDOS DE LAS FACTURAS
SERVICIOS_MATTEUDA = [
    {
        "pdf_filename": "UCOOPGAS.pdf",
        "concepto": "Gas Propano a Granel - Zeppelín Casco",
        "proveedor": "UCOOPGAS (Coop. de Gas y Vivienda Cba. Ltda.)",
        "cuit_proveedor": "30-62329693-4",
        "tipo_servicio": TipoServicioEnum.GAS,
        "frecuencia_pago": FrecuenciaPagoEnum.EVENTUAL,
        "forma_pago": FormaPagoServicioEnum.TRANSFERENCIA,
        "monto_estimado_ars": Decimal("250000.00"),
        "monto_real_ars": Decimal("261901.73"),
        "fecha_vencimiento": date(2026, 5, 4),  # Vto CAE / Cta Corriente
        "payment_portal_url": "https://www.ucoopgas.com.ar",
        "payment_reference": "Cuenta: 00819 | Roela: 0000008195150067278 | Link: 0000819 | CBU Bco Cba: 0200337301000000312047",
        "observaciones": "Carga de 256 Lts Propano a Granel (Remito 000600049202). Factura A 0021-00015183. CUIT Titular: 23-13930157-9.",
        "periodo": "Abril 2026",
    },
    {
        "pdf_filename": "claro.pdf",
        "concepto": "Flota Móvil e Internet 4G/5G (6 Líneas)",
        "proveedor": "Claro (AMX Argentina S.A.)",
        "cuit_proveedor": "30-66328849-7",
        "tipo_servicio": TipoServicioEnum.INTERNET,
        "frecuencia_pago": FrecuenciaPagoEnum.MENSUAL,
        "forma_pago": FormaPagoServicioEnum.DEBITO_AUTOMATICO,
        "monto_estimado_ars": Decimal("280000.00"),
        "monto_real_ars": Decimal("286962.62"),
        "fecha_vencimiento": date(2026, 9, 16),
        "payment_portal_url": "https://autogestionempresas.claro.com.ar",
        "payment_reference": "Cuenta: 2/0214117830 | Cliente: 4480169 | Débito Banco Nación",
        "observaciones": "6 líneas móviles en zona rural (Planes 1GB, 3GB, 15GB). Factura A 1340-00505864. Débito automático en cuenta Banco Nación.",
        "periodo": "Agosto 2026",
    },
    {
        "pdf_filename": "25500000001002100018387.pdf",
        "concepto": "Luz Rural - Líneas Rurales y Seguro Transformador",
        "proveedor": "Cooperativa Eléctrica de Laguna Larga Ltda.",
        "cuit_proveedor": "30-54572894-6",
        "tipo_servicio": TipoServicioEnum.LUZ_RURAL,
        "frecuencia_pago": FrecuenciaPagoEnum.MENSUAL,
        "forma_pago": FormaPagoServicioEnum.TRANSFERENCIA,
        "monto_estimado_ars": Decimal("50000.00"),
        "monto_real_ars": Decimal("52394.00"),
        "fecha_vencimiento": date(2026, 8, 18),
        "payment_portal_url": "https://www.cooponlineweb.com.ar/LAGUNALARGA",
        "payment_reference": "Suministro: 2550000 | Cód. SIRO: 0025500005150071619 | Link: 0002550000",
        "observaciones": "Zona Rural Sur Laguna Larga. Cuota Capital + Mantenimiento Líneas Rurales + Seguro Transformador. Factura A 0021-00018387.",
        "periodo": "Julio 2026",
    },
    {
        "pdf_filename": "25500000001002100018388.pdf",
        "concepto": "Tasa Hospital Municipal - Suministro Rural",
        "proveedor": "Cooperativa Eléctrica de Laguna Larga Ltda.",
        "cuit_proveedor": "30-54572894-6",
        "tipo_servicio": TipoServicioEnum.IMPUESTO_TASA,
        "frecuencia_pago": FrecuenciaPagoEnum.MENSUAL,
        "forma_pago": FormaPagoServicioEnum.TRANSFERENCIA,
        "monto_estimado_ars": Decimal("6500.00"),
        "monto_real_ars": Decimal("6596.00"),
        "fecha_vencimiento": date(2026, 8, 18),
        "payment_portal_url": "https://www.cooponlineweb.com.ar/LAGUNALARGA",
        "payment_reference": "Suministro: 2550000 | Cód. SIRO: 0025500005150071619 | Link: 0002550000",
        "observaciones": "Tasa Hospital Municipal vinculada al suministro rural 2550000. Factura A 0021-00018388.",
        "periodo": "Julio 2026",
    },
    {
        "pdf_filename": "999992210002002000128244.pdf",
        "concepto": "Internet Fibra Óptica 10/5 Mbps - Administración",
        "proveedor": "Cooperativa Eléctrica de Laguna Larga Ltda.",
        "cuit_proveedor": "30-54572894-6",
        "tipo_servicio": TipoServicioEnum.INTERNET,
        "frecuencia_pago": FrecuenciaPagoEnum.MENSUAL,
        "forma_pago": FormaPagoServicioEnum.TRANSFERENCIA,
        "monto_estimado_ars": Decimal("20000.00"),
        "monto_real_ars": Decimal("20909.00"),
        "fecha_vencimiento": date(2026, 8, 18),
        "payment_portal_url": "https://www.cooponlineweb.com.ar/LAGUNALARGA",
        "payment_reference": "Suministro: 99999221 | Cód. SIRO: 0999992215150071619 | Link: 0099999221",
        "observaciones": "Conexión en Administración / Casa Central (25 de Mayo 184, Laguna Larga). Factura B 0020-00128244.",
        "periodo": "Julio 2026",
    },
]


async def importar_servicios():
    docs_dir = BASE_DIR / "docs" / "servicios"
    if not docs_dir.exists():
        logger.error(f"No se encontró el directorio de documentos en: {docs_dir}")
        return

    storage_root = get_storage_root()
    logger.info(f"Directorio raíz de almacenamiento de documentos: {storage_root}")

    async with AsyncSessionLocal() as session:
        # 1. Obtener cliente de la familia
        res = await session.execute(select(Cliente).where(Cliente.nombre.ilike("%Matteuda%")))
        cliente = res.scalars().first()
        if not cliente:
            res_any = await session.execute(select(Cliente))
            cliente = res_any.scalars().first()
            if not cliente:
                logger.error("No se encontró ningún cliente en la base de datos.")
                return

        logger.info(f"Importando para Cliente: {cliente.nombre} ({cliente.id})")

        total_creados = 0
        total_adjuntos = 0

        for s_data in SERVICIOS_MATTEUDA:
            concepto = s_data["concepto"]
            # Verificar si ya existe
            res_s = await session.execute(
                select(ServicioInstalado).where(
                    ServicioInstalado.cliente_id == cliente.id,
                    ServicioInstalado.concepto == concepto,
                )
            )
            servicio_existente = res_s.scalars().first()

            m_ars = s_data["monto_real_ars"]
            m_usd = Decimal(str(round(float(m_ars) / 1285.50, 2)))

            if not servicio_existente:
                s_id = uuid.uuid4()
                nuevo_servicio = ServicioInstalado(
                    id=s_id,
                    cliente_id=cliente.id,
                    campo_id=None,  # Servicio General de la explotación
                    instalacion_id=None,  # Sin instalación física fija
                    tipo_servicio=s_data["tipo_servicio"],
                    concepto=concepto,
                    proveedor=s_data["proveedor"],
                    frecuencia_pago=s_data["frecuencia_pago"],
                    forma_pago=s_data["forma_pago"],
                    monto_estimado_ars=s_data["monto_estimado_ars"],
                    monto_real_ars=m_ars,
                    monto_usd=m_usd,
                    fecha_vencimiento=s_data["fecha_vencimiento"],
                    estado=EstadoServicioInstaladoEnum.AL_DIA if s_data["forma_pago"] == FormaPagoServicioEnum.DEBITO_AUTOMATICO else EstadoServicioInstaladoEnum.PENDIENTE,
                    payment_portal_url=s_data["payment_portal_url"],
                    payment_reference=s_data["payment_reference"],
                    observaciones=s_data["observaciones"],
                )
                session.add(nuevo_servicio)
                await session.flush()
                servicio_obj = nuevo_servicio
                total_creados += 1
                logger.info(f"✓ Servicio Creado: {concepto} ({s_data['proveedor']})")
            else:
                servicio_obj = servicio_existente
                logger.info(f"ℹ Servicio ya existente: {concepto}")

            # 2. Copiar y adjuntar el archivo PDF si está presente
            pdf_path = docs_dir / s_data["pdf_filename"]
            if pdf_path.exists():
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()

                sha256 = hashlib.sha256(pdf_bytes).hexdigest()

                # Verificar si el documento ya fue adjuntado
                res_doc = await session.execute(
                    select(ServiceDocument).where(
                        ServiceDocument.servicio_id == servicio_obj.id,
                        ServiceDocument.sha256_hash == sha256,
                    )
                )
                if not res_doc.scalars().first():
                    dest_dir = storage_root / "documents" / str(cliente.id) / str(servicio_obj.id)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    stored_name = f"{uuid.uuid4()}.pdf"
                    dest_file = dest_dir / stored_name

                    with open(dest_file, "wb") as f_out:
                        f_out.write(pdf_bytes)

                    storage_key = f"documents/{cliente.id}/{servicio_obj.id}/{stored_name}"

                    nuevo_doc = ServiceDocument(
                        id=uuid.uuid4(),
                        cliente_id=cliente.id,
                        servicio_id=servicio_obj.id,
                        servicio_vencimiento_id=None,
                        document_type=DocumentTypeEnum.FACTURA,
                        original_filename=s_data["pdf_filename"],
                        stored_filename=stored_name,
                        storage_key=storage_key,
                        mime_type="application/pdf",
                        size_bytes=len(pdf_bytes),
                        sha256_hash=sha256,
                        notes=f"Factura original importada: {s_data['concepto']}",
                        estado="activo",
                    )
                    session.add(nuevo_doc)
                    await session.flush()
                    total_adjuntos += 1
                    logger.info(f"   ↳ Adjunto PDF: {s_data['pdf_filename']} ({len(pdf_bytes) // 1024} KB)")

            # 3. Generar vencimiento histórico para el período
            res_venc = await session.execute(
                select(ServicioVencimiento).where(
                    ServicioVencimiento.servicio_instalado_id == servicio_obj.id,
                    ServicioVencimiento.periodo_referencia == s_data["periodo"],
                )
            )
            if not res_venc.scalars().first():
                nuevo_venc = ServicioVencimiento(
                    id=uuid.uuid4(),
                    cliente_id=cliente.id,
                    servicio_instalado_id=servicio_obj.id,
                    concepto=f"Factura Período {s_data['periodo']}",
                    periodo_referencia=s_data["periodo"],
                    monto_ars=m_ars,
                    monto_usd=m_usd,
                    fecha_vencimiento=s_data["fecha_vencimiento"],
                    estado=EstadoServicio.PAGADO if s_data["forma_pago"] == FormaPagoServicioEnum.DEBITO_AUTOMATICO else EstadoServicio.PENDIENTE,
                    payment_link=s_data["payment_portal_url"],
                )
                session.add(nuevo_venc)
                logger.info(f"   ↳ Vencimiento Período: {s_data['periodo']}")

        await session.commit()
        logger.info("=========================================================")
        logger.info(f"Proceso finalizado: {total_creados} servicios creados, {total_adjuntos} comprobantes PDF vinculados.")
        logger.info("=========================================================")


if __name__ == "__main__":
    asyncio.run(importar_servicios())
