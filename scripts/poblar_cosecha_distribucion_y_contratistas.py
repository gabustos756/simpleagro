"""
scripts/poblar_cosecha_distribucion_y_contratistas.py
--------------------------------------------------------------------------------
Script de sincronización e importación integral de datos de Cosecha 25/26, 
distribución física de granos (Acopio AFA, Silos de Chapa 3 y 4, Silobolsas), 
liquidaciones de contratistas de trilla y recomendaciones agronómicas reportadas
por la encargada de campo (Verónica).

Ejecución:
    venv/bin/python scripts/poblar_cosecha_distribucion_y_contratistas.py [--dry-run]
"""

import asyncio
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import logging
import os
import sys
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.future import select
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models import (
    Cliente, Campo, Lote, Campania, Instalacion, StorageLocation, StockPartida, StockMovement,
    StockGrano, ContratoVentaGrano, GrainDelivery, TransaccionFinanciera
)
from app.enums import (
    TipoLabor, TipoTransaccion, TipoPrecioEnum, UbicacionStockEnum
)
from app.seed import DEMO_CLIENTE, get_uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("poblar_cosecha")


async def poblar_datos_cosecha_y_contratistas(dry_run: bool = False):
    logger.info("=== INICIANDO POBLACIÓN DE COSECHA, ACOPIOS, SILOS, CONTRATOS Y CONTRATISTAS (25/26) ===")

    async with AsyncSessionLocal() as db:
        # 1. Obtener Cliente Principal
        cliente_id = get_uuid(DEMO_CLIENTE["id"])
        res_c = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
        cliente = res_c.scalars().first()
        if not cliente:
            logger.error("No se encontró el Cliente principal en la base de datos.")
            return

        # 2. Obtener Campaña 25/26
        res_camp = await db.execute(
            select(Campania).where(Campania.cliente_id == cliente_id).order_by(Campania.fecha_inicio.desc()).limit(1)
        )
        campania = res_camp.scalars().first()
        campania_id = campania.id if campania else None

        # 3. Mapear Campos y Lotes
        res_campos = await db.execute(select(Campo).where(Campo.cliente_id == cliente_id))
        campos = {c.nombre.lower(): c for c in res_campos.scalars().all()}
        campo_grasso = next((c for k, c in campos.items() if "grasso" in k or "graso" in k), None)
        campo_gontero = next((c for k, c in campos.items() if "gontero" in k), None)
        campo_venier = next((c for k, c in campos.items() if "venier" in k), None)

        res_lotes = await db.execute(select(Lote).where(Lote.cliente_id == cliente_id))
        lotes = {l.nombre.lower(): l for l in res_lotes.scalars().all()}

        # 4. Actualizar Rendimientos de Lotes con los datos reportados por Verónica
        lotes_update_map = [
            ("grasso 1", 57.0, 86.35, 4835.8, "Barbecho (Post-Maíz)", "Maíz 25/26 (Cosechado 86.35 qq/ha)", "Cosecha Maíz 25/26: 4835.8 qq totales. Merma por viento sur y planchado inicial."),
            ("grasso 2", 30.0, 41.73, 1251.9, "Barbecho Químico (Post-Soja)", "Soja 25/26 (Cosechada 41.73 qq/ha DM 46i20)", "Cosecha Soja 25/26: 1251.9 qq totales."),
            ("grasso 3", 27.0, 37.41, 1010.1, "Barbecho Químico (Post-Soja)", "Soja 25/26 (Cosechada 37.41 qq/ha)", "Cosecha Soja 25/26: 1010.1 qq totales."),
            ("gontero 1 (norte)", 50.5, 85.00, 4253.6, "Barbecho (Post-Maíz)", "Maíz 25/26 (Cosechado 85.00 qq/ha)", "Cosecha Maíz 25/26: 4253.6 qq totales."),
            ("gontero 2 (sur)", 50.5, 38.50, 1925.0, "Barbecho Químico (Post-Soja)", "Soja 25/26 (Cosechada 38.50 qq/ha)", "Cosecha Soja 25/26: 1925.0 qq totales."),
            ("venier 1", 41.0, 92.15, 3778.4, "Barbecho (Post-Maíz)", "Maíz 25/26 (Cosechado 92.15 qq/ha)", "Cosecha Maíz 25/26: 3778.4 qq totales (Rinde excelente 92.15 qq/ha)."),
            ("venier 2", 42.0, 36.62, 1538.4, "Barbecho Químico (Post-Soja)", "Soja 25/26 (Cosechada 36.62 qq/ha)", "Cosecha Soja 25/26: 1538.4 qq totales. Incluye lote grande (1101.6 qq @ 35.53 qq/ha) y lote ensayo 35cm doble pasada (436.8 qq @ 37.98 qq/ha).")
        ]

        for l_key, sup, rinde, prod, cult_act, cult_ant, obs in lotes_update_map:
            l_obj = next((l for k, l in lotes.items() if l_key in k), None)
            if l_obj:
                l_obj.superficie_productiva_ha = float(sup)
                l_obj.qq_ha_real = float(rinde)
                l_obj.produccion_total_qq = float(prod)
                l_obj.cultivo_actual = cult_act
                l_obj.cultivo_anterior = cult_ant
                l_obj.observaciones = obs
                meta = dict(l_obj.metadatos_agronomicos or {})
                meta["estado_productivo"] = "cosechado"
                meta["rinde_final_qq_ha"] = float(rinde)
                meta["produccion_final_qq"] = float(prod)
                l_obj.metadatos_agronomicos = meta
                logger.info(f"✔ Lote actualizado: {l_obj.nombre} -> {prod} qq ({rinde} qq/ha)")

        # 5. Crear Instalaciones Físicas (Instalaciones de Campo)
        instalaciones_defs = [
            {
                "campo": campo_grasso,
                "nombre": "Planta de Silos Central (Silos 1 a 4)",
                "tipo": "silo",
                "ubicacion_notas": "Batería de 4 silos aéreos de chapa galvanizada. Silos 3 y 4 con 210 Tn de Soja 25/26."
            },
            {
                "campo": campo_grasso,
                "nombre": "Galpón y Taller Central",
                "tipo": "galpon",
                "ubicacion_notas": "Área de resguardo de maquinaria pesada, herramientas y stock de insumos."
            },
            {
                "campo": campo_gontero,
                "nombre": "Casco y Galpón Gontero",
                "tipo": "galpon",
                "ubicacion_notas": "Infraestructura operativa y patio de embolsado de granos."
            },
            {
                "campo": campo_venier,
                "nombre": "Casco Operativo Venier",
                "tipo": "galpon",
                "ubicacion_notas": "Área operativa y sector de silobolsas."
            },
        ]

        for inst_def in instalaciones_defs:
            if not inst_def["campo"]:
                continue
            res_inst = await db.execute(
                select(Instalacion).where(
                    Instalacion.cliente_id == cliente_id,
                    Instalacion.campo_id == inst_def["campo"].id,
                    Instalacion.nombre == inst_def["nombre"]
                )
            )
            inst = res_inst.scalars().first()
            if not inst:
                inst = Instalacion(
                    id=uuid.uuid4(),
                    cliente_id=cliente_id,
                    campo_id=inst_def["campo"].id,
                    nombre=inst_def["nombre"],
                    tipo=inst_def["tipo"],
                    ubicacion_notas=inst_def["ubicacion_notas"]
                )
                db.add(inst)
                logger.info(f"✔ Instalación creada: {inst.nombre} en {inst_def['campo'].nombre}")
            else:
                inst.ubicacion_notas = inst_def["ubicacion_notas"]
                logger.info(f"✔ Instalación existente actualizada: {inst.nombre}")

        # 6. Crear o Actualizar Ubicaciones de Almacenamiento (StorageLocations)
        storage_defs = [
            {
                "nombre": "Acopio AFA (Agricultores Federados Argentinos)",
                "tipo": "acopio",
                "capacidad_nominal_tn": Decimal("5000.00"),
                "ubicacion_referencia": "AFA San Lorenzo / Rosario",
                "campo_id": None,
                "observaciones": "Acopio cooperativo de terceros para entregas y fijación comercial."
            },
            {
                "nombre": "Silo Chapa N° 1 - Planta Principal",
                "tipo": "silo_propio",
                "capacidad_nominal_tn": Decimal("200.00"),
                "ubicacion_referencia": "Planta de Silos Central - Grasso",
                "campo_id": campo_grasso.id if campo_grasso else None,
                "observaciones": "Silo aéreo de chapa galvanizada N° 1 (200 Tn)."
            },
            {
                "nombre": "Silo Chapa N° 2 - Planta Principal",
                "tipo": "silo_propio",
                "capacidad_nominal_tn": Decimal("200.00"),
                "ubicacion_referencia": "Planta de Silos Central - Grasso",
                "campo_id": campo_grasso.id if campo_grasso else None,
                "observaciones": "Silo aéreo de chapa galvanizada N° 2 (200 Tn)."
            },
            {
                "nombre": "Silo Chapa N° 3 - Planta Principal",
                "tipo": "silo_propio",
                "capacidad_nominal_tn": Decimal("200.00"),
                "ubicacion_referencia": "Planta de Silos Central - Grasso",
                "campo_id": campo_grasso.id if campo_grasso else None,
                "observaciones": "Silo aéreo de chapa galvanizada N° 3 (200 Tn). Destinado a Soja nueva."
            },
            {
                "nombre": "Silo Chapa N° 4 - Planta Principal",
                "tipo": "silo_propio",
                "capacidad_nominal_tn": Decimal("200.00"),
                "ubicacion_referencia": "Planta de Silos Central - Grasso",
                "campo_id": campo_grasso.id if campo_grasso else None,
                "observaciones": "Silo aéreo de chapa galvanizada N° 4 (200 Tn). Destinado a Soja nueva."
            },
            {
                "nombre": "Silobolsa Soja 25/26 - Grasso",
                "tipo": "silobolsa",
                "capacidad_nominal_tn": Decimal("250.00"),
                "ubicacion_referencia": "Cabecera Lote Grasso 2",
                "campo_id": campo_grasso.id if campo_grasso else None,
                "observaciones": "Silobolsa 9 pies para remanente de Soja 25/26."
            },
            {
                "nombre": "Silobolsa Maíz 25/26 - Gontero",
                "tipo": "silobolsa",
                "capacidad_nominal_tn": Decimal("450.00"),
                "ubicacion_referencia": "Establecimiento Gontero",
                "campo_id": campo_gontero.id if campo_gontero else None,
                "observaciones": "Silobolsa para Maíz 25/26 cosechado en Gontero (425.36 Tn)."
            },
            {
                "nombre": "Silobolsa Maíz 25/26 - Grasso",
                "tipo": "silobolsa",
                "capacidad_nominal_tn": Decimal("500.00"),
                "ubicacion_referencia": "Establecimiento Grasso 1",
                "campo_id": campo_grasso.id if campo_grasso else None,
                "observaciones": "Silobolsa para Maíz 25/26 cosechado en Grasso 1 (483.58 Tn)."
            },
            {
                "nombre": "Silobolsa Maíz 25/26 - Venier",
                "tipo": "silobolsa",
                "capacidad_nominal_tn": Decimal("400.00"),
                "ubicacion_referencia": "Establecimiento Venier",
                "campo_id": campo_venier.id if campo_venier else None,
                "observaciones": "Silobolsa para Maíz 25/26 cosechado en Venier (377.84 Tn)."
            },
        ]

        loc_objs = {}
        for s_def in storage_defs:
            res_s = await db.execute(
                select(StorageLocation).where(
                    StorageLocation.cliente_id == cliente_id,
                    StorageLocation.tipo == s_def["tipo"],
                    StorageLocation.nombre == s_def["nombre"]
                )
            )
            loc = res_s.scalars().first()
            if not loc:
                loc = StorageLocation(
                    id=uuid.uuid4(),
                    cliente_id=cliente_id,
                    nombre=s_def["nombre"],
                    tipo=s_def["tipo"],
                    capacidad_nominal_tn=s_def["capacidad_nominal_tn"],
                    ubicacion_referencia=s_def["ubicacion_referencia"],
                    campo_id=s_def["campo_id"],
                    observaciones=s_def["observaciones"],
                    estado="activo"
                )
                db.add(loc)
                await db.flush()
                logger.info(f"✔ Nueva ubicación de almacenamiento creada: {loc.nombre}")
            else:
                loc.capacidad_nominal_tn = s_def["capacidad_nominal_tn"]
                loc.observaciones = s_def["observaciones"]
                loc.campo_id = s_def["campo_id"]
                logger.info(f"✔ Ubicación existente actualizada: {loc.nombre}")
            loc_objs[s_def["nombre"]] = loc

        # 7. Crear Partidas de Stock Físico y Trazable (StockPartida)
        partidas_defs = [
            # SOJA
            {
                "tracking_number": "STK-SOJA-2526-AFA",
                "cultivo": "soja",
                "cantidad_kg": Decimal("270000.00"),
                "storage_location": loc_objs["Acopio AFA (Agricultores Federados Argentinos)"],
                "campo": campo_grasso,
                "lote": lotes.get("grasso 2"),
                "fecha_cosecha": date(2026, 5, 20),
                "observaciones": "Entrega de Soja 25/26 a Acopio AFA (2,700.0 qq / 270 Tn). Pendiente liquidación final Andrés."
            },
            {
                "tracking_number": "STK-SOJA-2526-SILO3",
                "cultivo": "soja",
                "cantidad_kg": Decimal("172000.00"),
                "storage_location": loc_objs["Silo Chapa N° 3 - Planta Principal"],
                "campo": campo_grasso,
                "lote": lotes.get("grasso 2"),
                "fecha_cosecha": date(2026, 5, 20),
                "observaciones": "Soja 25/26 almacenada en Silo de Chapa 3 (1,720.0 qq / 172 Tn)."
            },
            {
                "tracking_number": "STK-SOJA-2526-SILO4",
                "cultivo": "soja",
                "cantidad_kg": Decimal("38000.00"),
                "storage_location": loc_objs["Silo Chapa N° 4 - Planta Principal"],
                "campo": campo_grasso,
                "lote": lotes.get("grasso 3"),
                "fecha_cosecha": date(2026, 5, 20),
                "observaciones": "Soja 25/26 almacenada en Silo de Chapa 4 (380.0 qq / 38 Tn)."
            },
            {
                "tracking_number": "STK-SOJA-2526-BOLSA",
                "cultivo": "soja",
                "cantidad_kg": Decimal("92540.00"),
                "storage_location": loc_objs["Silobolsa Soja 25/26 - Grasso"],
                "campo": campo_grasso,
                "lote": lotes.get("grasso 3"),
                "fecha_cosecha": date(2026, 5, 20),
                "observaciones": "Remanente de Soja 25/26 embolsada en campo (925.4 qq / 92.54 Tn)."
            },
            # MAÍZ
            {
                "tracking_number": "STK-MAIZ-2526-GONTERO",
                "cultivo": "maiz",
                "cantidad_kg": Decimal("425360.00"),
                "storage_location": loc_objs["Silobolsa Maíz 25/26 - Gontero"],
                "campo": campo_gontero,
                "lote": lotes.get("gontero 1 (norte)"),
                "fecha_cosecha": date(2026, 8, 20),
                "observaciones": "Maíz 25/26 cosecha Gontero (4,253.6 qq / 425.36 Tn @ 85 qq/ha)."
            },
            {
                "tracking_number": "STK-MAIZ-2526-GRASSO",
                "cultivo": "maiz",
                "cantidad_kg": Decimal("483580.00"),
                "storage_location": loc_objs["Silobolsa Maíz 25/26 - Grasso"],
                "campo": campo_grasso,
                "lote": lotes.get("grasso 1"),
                "fecha_cosecha": date(2026, 8, 21),
                "observaciones": "Maíz 25/26 cosecha Grasso 1 (4,835.8 qq / 483.58 Tn @ 86.35 qq/ha)."
            },
            {
                "tracking_number": "STK-MAIZ-2526-VENIER",
                "cultivo": "maiz",
                "cantidad_kg": Decimal("377840.00"),
                "storage_location": loc_objs["Silobolsa Maíz 25/26 - Venier"],
                "campo": campo_venier,
                "lote": lotes.get("venier 1"),
                "fecha_cosecha": date(2026, 8, 22),
                "observaciones": "Maíz 25/26 cosecha Venier (3,778.4 qq / 377.84 Tn @ 92.15 qq/ha)."
            },
        ]

        for p_def in partidas_defs:
            res_p = await db.execute(
                select(StockPartida).where(
                    StockPartida.cliente_id == cliente_id,
                    StockPartida.tracking_number == p_def["tracking_number"]
                )
            )
            partida = res_p.scalars().first()
            if not partida:
                partida = StockPartida(
                    id=uuid.uuid4(),
                    cliente_id=cliente_id,
                    tracking_number=p_def["tracking_number"],
                    cultivo=p_def["cultivo"],
                    campania_id=campania_id,
                    campo_id=p_def["campo"].id if p_def["campo"] else None,
                    lote_id=p_def["lote"].id if p_def["lote"] else None,
                    storage_location_id=p_def["storage_location"].id,
                    fecha_cosecha=p_def["fecha_cosecha"],
                    fecha_ingreso=p_def["fecha_cosecha"],
                    cantidad_inicial_kg=p_def["cantidad_kg"],
                    estado="activa",
                    observaciones=p_def["observaciones"]
                )
                db.add(partida)
                await db.flush()

                # Registrar movimiento de ingreso inicial
                mov = StockMovement(
                    id=uuid.uuid4(),
                    cliente_id=cliente_id,
                    stock_partida_id=partida.id,
                    tipo="ingreso_cosecha",
                    cantidad_kg=p_def["cantidad_kg"],
                    fecha_movimiento=datetime.combine(p_def["fecha_cosecha"], datetime.min.time(), tzinfo=timezone.utc),
                    motivo=f"Ingreso Cosecha {p_def['cultivo'].upper()}",
                    observaciones=f"Ingreso por cosecha campaña 25/26 ({p_def['cantidad_kg']/1000} Tn) en {p_def['storage_location'].nombre}"
                )
                db.add(mov)
                logger.info(f"✔ Partida creada: {partida.tracking_number} ({partida.cultivo.upper()}: {partida.cantidad_inicial_kg/1000} Tn en {p_def['storage_location'].nombre})")
            else:
                partida.cantidad_inicial_kg = p_def["cantidad_kg"]
                partida.observaciones = p_def["observaciones"]
                partida.storage_location_id = p_def["storage_location"].id
                logger.info(f"✔ Partida actualizada: {partida.tracking_number}")

        # 8. Sincronizar Stock Comercial Legacy (StockGrano)
        stock_grano_defs = [
            {
                "campo": campo_grasso,
                "cultivo": "soja",
                "ubicacion_tipo": UbicacionStockEnum.ACOPIO_TERCERO,
                "identificador": "Acopio AFA San Lorenzo / Rosario",
                "toneladas": Decimal("270.00"),
                "fecha_ingreso": date(2026, 5, 20),
                "obs": "Entrega física a AFA (2.700 qq) pendiente de liquidación."
            },
            {
                "campo": campo_grasso,
                "cultivo": "soja",
                "ubicacion_tipo": UbicacionStockEnum.SILO_BOLSA,
                "identificador": "Silos Chapa N° 3 y 4 - Grasso",
                "toneladas": Decimal("210.00"),
                "fecha_ingreso": date(2026, 5, 20),
                "obs": "Silo 3 (172 Tn) + Silo 4 (38 Tn) en planta propia."
            },
            {
                "campo": campo_grasso,
                "cultivo": "soja",
                "ubicacion_tipo": UbicacionStockEnum.SILO_BOLSA,
                "identificador": "Silobolsa Soja Grasso",
                "toneladas": Decimal("92.54"),
                "fecha_ingreso": date(2026, 5, 20),
                "obs": "Silobolsa en campo Grasso (925.4 qq)."
            },
            {
                "campo": campo_gontero,
                "cultivo": "maiz",
                "ubicacion_tipo": UbicacionStockEnum.SILO_BOLSA,
                "identificador": "Silobolsa Maíz Gontero",
                "toneladas": Decimal("425.36"),
                "fecha_ingreso": date(2026, 8, 20),
                "obs": "Silobolsa Maíz 25/26 Gontero (4.253,6 qq)."
            },
            {
                "campo": campo_grasso,
                "cultivo": "maiz",
                "ubicacion_tipo": UbicacionStockEnum.SILO_BOLSA,
                "identificador": "Silobolsa Maíz Grasso",
                "toneladas": Decimal("483.58"),
                "fecha_ingreso": date(2026, 8, 21),
                "obs": "Silobolsa Maíz 25/26 Grasso 1 (4.835,8 qq)."
            },
            {
                "campo": campo_venier,
                "cultivo": "maiz",
                "ubicacion_tipo": UbicacionStockEnum.SILO_BOLSA,
                "identificador": "Silobolsa Maíz Venier",
                "toneladas": Decimal("377.84"),
                "fecha_ingreso": date(2026, 8, 22),
                "obs": "Silobolsa Maíz 25/26 Venier (3.778,4 qq)."
            },
        ]

        for sg_def in stock_grano_defs:
            if not sg_def["campo"] or not campania_id:
                continue
            res_sg = await db.execute(
                select(StockGrano).where(
                    StockGrano.cliente_id == cliente_id,
                    StockGrano.campo_id == sg_def["campo"].id,
                    StockGrano.campania_id == campania_id,
                    StockGrano.cultivo == sg_def["cultivo"],
                    StockGrano.identificador == sg_def["identificador"]
                )
            )
            sg = res_sg.scalars().first()
            if not sg:
                sg = StockGrano(
                    id=uuid.uuid4(),
                    cliente_id=cliente_id,
                    campo_id=sg_def["campo"].id,
                    campania_id=campania_id,
                    cultivo=sg_def["cultivo"],
                    ubicacion_tipo=sg_def["ubicacion_tipo"],
                    identificador=sg_def["identificador"],
                    toneladas_almacenadas=sg_def["toneladas"],
                    fecha_ingreso=sg_def["fecha_ingreso"],
                    observaciones=sg_def["obs"]
                )
                db.add(sg)
                logger.info(f"✔ StockGrano registrado: {sg.cultivo.upper()} {sg.toneladas_almacenadas} Tn ({sg.identificador})")
            else:
                sg.toneladas_almacenadas = sg_def["toneladas"]
                sg.observaciones = sg_def["obs"]
                logger.info(f"✔ StockGrano actualizado: {sg.cultivo.upper()} {sg.toneladas_almacenadas} Tn")

        # 9. Crear Compromisos / Contratos de Venta y Entregas Físicas
        # Contrato de venta a fijar con AFA por 270 Tn entregadas
        if campania_id:
            num_contrato = "CTR-2526-AFA-SOJA-01"
            res_ct = await db.execute(
                select(ContratoVentaGrano).where(
                    ContratoVentaGrano.cliente_id == cliente_id,
                    ContratoVentaGrano.numero_contrato == num_contrato
                )
            )
            contrato = res_ct.scalars().first()
            if not contrato:
                contrato = ContratoVentaGrano(
                    id=uuid.uuid4(),
                    cliente_id=cliente_id,
                    campania_id=campania_id,
                    cultivo="soja",
                    comprador_acopio="Agricultores Federados Argentinos (AFA)",
                    numero_contrato=num_contrato,
                    toneladas=Decimal("270.00"),
                    tipo_precio=TipoPrecioEnum.A_FIJAR,
                    precio_usd_tn=None,
                    fecha_contrato=date(2026, 5, 20),
                    fecha_entrega_limite=date(2026, 6, 30),
                    observaciones="Entrega física directa a Acopio AFA San Lorenzo / Rosario (2.700 qq). Pendiente fijación de precio de venta por Andrés."
                )
                db.add(contrato)
                logger.info(f"✔ Contrato de venta creado: {contrato.numero_contrato} (270 Tn Soja A FIJAR)")
            else:
                contrato.toneladas = Decimal("270.00")
                logger.info(f"✔ Contrato de venta existente actualizado: {contrato.numero_contrato}")

            # Registro de Entrega Física (GrainDelivery)
            delivery_tracking = "DELIV-2526-AFA-SOJA-01"
            res_deliv = await db.execute(
                select(GrainDelivery).where(
                    GrainDelivery.cliente_id == cliente_id,
                    GrainDelivery.tracking_number == delivery_tracking
                )
            )
            delivery = res_deliv.scalars().first()
            if not delivery:
                delivery = GrainDelivery(
                    id=uuid.uuid4(),
                    cliente_id=cliente_id,
                    tracking_number=delivery_tracking,
                    campo_id=campo_grasso.id if campo_grasso else None,
                    lote_id=lotes.get("grasso 2").id if lotes.get("grasso 2") else None,
                    acopio_receptor="Agricultores Federados Argentinos (AFA)",
                    destination_final_reference="AFA San Lorenzo / Rosario",
                    cultivo="soja",
                    transportista_nombre="Transporte Cerealero Regional",
                    fecha_planificada=date(2026, 5, 20),
                    fecha_salida=datetime(2026, 5, 20, 9, 30, tzinfo=timezone.utc),
                    fecha_recepcion=datetime(2026, 5, 20, 16, 0, tzinfo=timezone.utc),
                    toneladas_planificadas=Decimal("270.00"),
                    kg_neto_origen_total=Decimal("270000.00"),
                    kg_recibido_total=Decimal("270000.00"),
                    diferencia_total_kg=Decimal("0.00"),
                    diferencia_total_pct=Decimal("0.00"),
                    estado="completada",
                    documentacion_status="conforme",
                    observaciones="Entrega física 2.700 qq (270 Tn) ingresadas y descargadas con éxito en AFA."
                )
                db.add(delivery)
                logger.info(f"✔ GrainDelivery registrado: {delivery.tracking_number} (270 Tn Soja completada)")

        # 10. Registrar Transacciones de Contratistas de Trilla
        dolar_tc = Decimal("1497.50")
        contratistas_gastos = [
            {
                "concepto": "Servicio Trilla Soja 25/26 - Cervelli Maximiliano (98 Has @ $125.000/ha)",
                "monto_ars": Decimal("12250000.00"),
                "lote": lotes.get("grasso 2"),
            },
            {
                "concepto": "Servicio Trilla Soja 25/26 - Emiliano Vagni (35 Has @ $125.000/ha)",
                "monto_ars": Decimal("4375000.00"),
                "lote": lotes.get("grasso 3"),
            },
            {
                "concepto": "Servicio Trilla Soja 25/26 - Matelica Julio (19 Has @ $125.000/ha)",
                "monto_ars": Decimal("2375000.00"),
                "lote": lotes.get("venier 2"),
            },
            {
                "concepto": "Servicio Trilla Maíz 25/26 (Estimado 149 Has @ $150.000/ha)",
                "monto_ars": Decimal("22350000.00"),
                "lote": lotes.get("grasso 1"),
            }
        ]

        for cg in contratistas_gastos:
            res_t = await db.execute(
                select(TransaccionFinanciera).where(
                    TransaccionFinanciera.concepto == cg["concepto"]
                )
            )
            tx = res_t.scalars().first()
            m_usd = cg["monto_ars"] / dolar_tc
            if not tx:
                tx = TransaccionFinanciera(
                    id=uuid.uuid4(),
                    concepto=cg["concepto"],
                    tipo=TipoTransaccion.EGRESO,
                    monto_ars=cg["monto_ars"],
                    monto_usd=m_usd.quantize(Decimal("0.01")),
                    cotizacion_dolar=dolar_tc,
                    lote_id=cg["lote"].id if cg["lote"] else None,
                    pagado=False,
                )
                db.add(tx)
                logger.info(f"✔ Transacción financiera devengada: {cg['concepto']} (${cg['monto_ars']:,.2f} ARS / USD {m_usd:,.2f})")

        if dry_run:
            logger.info("Modo --dry-run activo: Deshaciendo cambios (rollback)...")
            await db.rollback()
        else:
            await db.commit()
            logger.info("🎉 ¡Todos los datos de infraestructura, silos, acopios, contratos y cosechas fueron persistidos exitosamente!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poblar datos de cosecha, acopios y contratistas 25/26.")
    parser.add_argument("--dry-run", action="store_true", help="Ejecuta sin persistir cambios en la BD.")
    args = parser.parse_args()
    asyncio.run(poblar_datos_cosecha_y_contratistas(dry_run=args.dry_run))

