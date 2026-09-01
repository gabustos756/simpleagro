"""
scripts/migrar_cuaderno_productor_vps.py
--------------------------------------------------------------------------------
Script de migración e importación de labores históricas extraídas del cuaderno del productor.
Permite poblar la base de datos (local o VPS) vinculando las labores técnicas, los eventos climáticos
y las métricas de rendimiento a los lotes satelitales/GIS existentes ("Grasso N° 1", "Grasso N° 2 y 3").

Instrucciones de uso:
    python scripts/migrar_cuaderno_productor_vps.py [--dry-run]
"""

import asyncio
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import logging
import sys
import os
import uuid

# Asegurar path base del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.future import select
from sqlalchemy import or_

from app.database import AsyncSessionLocal
from app.models import Lote, Campo, Campania, LaborCampo, RegistroLluvia, Cliente
from app.enums import TipoLabor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrar_cuaderno")


# DATASET ESTRUCTURADO COMPLETO DE LABORES Y CLIMA EXTRAÍDOS DEL CUADERNO REAL
LOTE_DATA_MAP = {
    "grasso_1": {
        "alias_busqueda": [
            "grasso 1", "grasso n° 1", "grasso n°1", "grasso nº 1", "grasso1", 
            "graso 1", "graso n° 1", "graso n°1", "graso nº 1", "graso1", 
            "lote graso 1", "lote grasso 1", "graso-1", "grasso-1"
        ],
        "superficie_ha": 57.0,

        "cultivo_actual": "Maíz",
        "cultivo_anterior": "Soja 24/25 (DM 46i20)",
        "cultivo_planificado": "Soja 26/27",
        "qq_ha_estimado": 45.0,
        "qq_ha_real": 95.0,
        "labores": [
            {
                "fecha": "2025-04-22T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "detalles_cosecha": {
                    "variedad": "DM 46i20",
                    "cultivo": "Soja"
                },
                "notas": "Se cosechó Soja DM 46i20"
            },
            {
                "fecha": "2025-05-29T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 37.0,
                "sector_zona": "Lado Sur y Vuelta alrededor",
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "Atrazina Atramit", "dosis": 0.630, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Picloram", "dosis": 0.266, "unidad": "lt/ha"},
                    {"nombre": "Mictec", "dosis": 0.07, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Lado Sur y Vuelta alrededor (37 ha)"
            },
            {
                "fecha": "2025-05-29T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 20.0,
                "sector_zona": "Lado Norte",
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "Atrazina", "dosis": 0.630, "unidad": "kg/ha"},
                    {"nombre": "Percutor", "dosis": 0.045, "unidad": "kg/ha"},
                    {"nombre": "Picloram", "dosis": 0.266, "unidad": "lt/ha"},
                    {"nombre": "Mictec", "dosis": 0.07, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Lado Norte (20 ha)"
            },
            {
                "fecha": "2025-09-09T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "insumos_utilizados": [
                    {"nombre": "Superfosfato Simple (SPS)", "dosis": 103.0, "unidad": "kg/ha"}
                ],
                "notas": "Fertilización al voleo alrededor de 102-104 kg/ha"
            },
            {
                "fecha": "2025-09-26T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "parametros_aplicacion": {
                    "volumen_agua_lts_ha": 58.0,
                    "pastilla_boquilla": "Antideriva 0.15"
                },
                "insumos_utilizados": [
                    {"nombre": "S-metolacloro", "dosis": 1.1, "unidad": "lt/ha"},
                    {"nombre": "Atrazina (Gesaprim)", "dosis": 1.0, "unidad": "kg/ha"}
                ],
                "evaluacion_resultado": "Llovió 12mm el 27/09. Al 07/11 lote impecable con 26mm acumulados.",
                "notas": "Pre-emergente Maíz con pastilla antideriva 0.15"
            },
            {
                "fecha": "2025-11-10T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Flumioxazin Gemmitop", "dosis": 0.156, "unidad": "lt/ha"},
                    {"nombre": "Pyroxasulfone Zidua", "dosis": 0.200, "unidad": "kg/ha"},
                    {"nombre": "Mictec", "dosis": 0.100, "unidad": "lt/ha"}
                ],
                "notas": "Pulverización pre-siembra"
            },
            {
                "fecha": "2025-12-23T00:00:00Z",
                "tipo_labor": TipoLabor.SIEMBRA,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Dividido por Híbridos",
                "detalles_siembra": {
                    "densidad_semillas_m": 4.2,
                    "cultivo": "Maíz",
                    "distribucion_semillas": [
                        {
                            "variedad": "Stine 9720",
                            "superficie_ha": 27.0,
                            "curado_semilla": "40 BB curadas con Potenza (Innoquim) sobre Ricardo Gallo, 10 BB sin curar (testigo)"
                        },
                        {"variedad": "DK 7208 Tre", "superficie_ha": 13.0, "curado_semilla": "10 BB curadas"},
                        {"variedad": "LT 721 TRE", "superficie_ha": 15.0},
                        {"variedad": "LT 721 RR", "superficie_ha": 2.0, "sector": "Cabecera Este"}
                    ]
                },
                "evaluacion_resultado": "El 24/12 llovió de golpe 15mm y a las 22hs otros 20mm. Produjo mucho planchado y encharcado.",
                "notas": "Siembra de Maíz con densidad 4.2 sem/m"
            },
            {
                "fecha": "2025-12-28T00:00:00Z",
                "tipo_labor": TipoLabor.LABRANZA,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "evaluacion_resultado": "Error: había que hacerlo todo 1 día antes.",
                "notas": "Pasada de rotativa a 1/2 litro para romper planchado"
            },
            {
                "fecha": "2026-01-11T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 57.0,
                "blanco_biologico": "Escape de Pastillo y Maizbón",
                "insumos_utilizados": [
                    {"nombre": "Glifo Top", "dosis": 2.5, "unidad": "lt/ha"},
                    {"nombre": "Mictec", "dosis": 0.110, "unidad": "lt/ha"}
                ],
                "notas": "Post-emergente por escape de pastillo y maizbón"
            },
            {
                "fecha": "2026-01-24T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "insumos_utilizados": [
                    {"nombre": "Urea N-Total", "dosis": 118.0, "unidad": "kg/ha"}
                ],
                "evaluacion_resultado": "Llovió 7mm a la noche del 25/01/2026.",
                "notas": "Fertilización Urea N-Total al voleo (116-120 kg/ha)"
            }
        ],
        "lluvias": [
            {"fecha": "2025-09-27T00:00:00Z", "mm": 12.0},
            {"fecha": "2025-11-07T00:00:00Z", "mm": 26.0},
            {"fecha": "2025-12-24T14:00:00Z", "mm": 15.0},
            {"fecha": "2025-12-24T22:00:00Z", "mm": 20.0},
            {"fecha": "2026-01-25T22:00:00Z", "mm": 7.0}
        ]
    },

    "grasso_2_3": {
        "alias_busqueda": [
            "grasso 2", "grasso 3", "grasso 2 y 3", "grasso n° 2", "grasso n° 3", "grasso n° 2 y 3", "grasso 2y3",
            "graso 2", "graso 3", "graso 2 y 3", "graso n° 2", "graso n° 3", "graso n° 2 y 3", "graso 2y3",
            "lote graso 2", "lote graso 3", "lote grasso 2", "lote grasso 3"
        ],

        "superficie_ha": 57.0,
        "cultivo_actual": "Soja",
        "cultivo_anterior": "Maíz 24/25 (Rinde 96 qq/ha)",
        "cultivo_planificado": "Maíz 26/27",
        "qq_ha_estimado": 40.0,
        "qq_ha_real": 96.07,
        "produccion_total_qq": 5480.4,
        "labores": [
            {
                "fecha": "2025-07-06T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lotes 2 y 3",
                "detalles_cosecha": {
                    "humedad_porcentaje": 12.5,
                    "rendimiento_qq_ha": 96.07,
                    "total_cosechado_qq": 5480.4,
                    "cultivo": "Maíz"
                },
                "notas": "Cosecha Maíz con 12.5% humedad. Total cosechado: 5480.4 qq"
            },
            {
                "fecha": "2025-08-06T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 27.0,
                "sector_zona": "Lote 3",
                "parametros_aplicacion": {
                    "volumen_agua_lts_ha": 68.0,
                    "presion_bar": 2.5,
                    "velocidad_kmh": 17.0,
                    "horario": "17:30 - 19:00 hs"
                },
                "insumos_utilizados": [
                    {"nombre": "Tijereta Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Dicamba", "dosis": 0.085, "unidad": "lt/ha"},
                    {"nombre": "Atrazina", "dosis": 0.600, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.100, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Lote 3 con 68 L/ha a 2.5 Bar y 17 km/h"
            },
            {
                "fecha": "2025-08-08T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 30.0,
                "sector_zona": "Lote 2",
                "parametros_aplicacion": {
                    "volumen_agua_lts_ha": 35.0,
                    "presion_bar": 4.0,
                    "velocidad_kmh": 16.0,
                    "pastilla_boquilla": "Disco (5) Núcleo (13)"
                },
                "insumos_utilizados": [
                    {"nombre": "Tijereta Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Dicamba", "dosis": 0.166, "unidad": "lt/ha"},
                    {"nombre": "Atrazina", "dosis": 0.600, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.100, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Lote 2 con pastilla Disco(5) Núcleo(13) a 4 Bar y 16 km/h"
            },
            {
                "fecha": "2025-09-08T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lotes 2 y 3",
                "insumos_utilizados": [
                    {"nombre": "Superfosfato Simple (SPS)", "dosis": 103.0, "unidad": "kg/ha"}
                ],
                "notas": "Fertilización SPS al voleo alrededor de 102-104 kg/ha"
            },
            {
                "fecha": "2025-10-06T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 27.0,
                "sector_zona": "Lote 3",
                "parametros_aplicacion": {"volumen_agua_lts_ha": 70.0},
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Atrazina Gesaprim", "dosis": 0.500, "unidad": "kg/ha"},
                    {"nombre": "Ligate", "dosis": 0.120, "unidad": "kg/ha"}
                ],
                "notas": "Pulverización Lote 3 (27 ha) con 70 L/ha agua"
            },
            {
                "fecha": "2025-10-08T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 30.0,
                "sector_zona": "Lote 2",
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Atrazina Gesaprim", "dosis": 0.500, "unidad": "kg/ha"},
                    {"nombre": "Ligate", "dosis": 0.120, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.08, "unidad": "lt/ha"}
                ],
                "evaluacion_resultado": "Llovió recién el 07/11: 28 mm.",
                "notas": "Pulverización Lote 2 (30 ha) con Altiva Pro agregada"
            },
            {
                "fecha": "2025-11-14T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 40.0,
                "sector_zona": "Sector 40 ha",
                "insumos_utilizados": [
                    {"nombre": "Sulfentrazone Capaz", "dosis": 0.533, "unidad": "lt/ha"},
                    {"nombre": "Sulfato de Amonio Trophen", "dosis": 0.250, "unidad": "kg/ha"},
                    {"nombre": "Glufosinato Liberty", "dosis": 2.5, "unidad": "lt/ha"},
                    {"nombre": "Dash MSO", "dosis": 0.250, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.05, "unidad": "lt/ha"}
                ],
                "notas": "Pre-siembra sector 40 ha"
            },
            {
                "fecha": "2025-11-14T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 17.0,
                "sector_zona": "Resto 17 ha",
                "insumos_utilizados": [
                    {"nombre": "Sulfentrazone Capaz", "dosis": 0.580, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.100, "unidad": "lt/ha"}
                ],
                "notas": "Pre-siembra resto 17 ha"
            },
            {
                "fecha": "2025-12-04T00:00:00Z",
                "tipo_labor": TipoLabor.SIEMBRA,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lotes 2 y 3",
                "detalles_siembra": {
                    "densidad_semillas_m": 26.0,
                    "cultivo": "Soja",
                    "distribucion_semillas": [
                        {"variedad": "NS 5030", "superficie_ha": 18.0, "sector": "Lote 3", "nota": "Variedad nueva"},
                        {"variedad": "DM 46i20", "superficie_ha": 39.0, "sector": "Resto del lote"}
                    ]
                },
                "notas": "Siembra Soja con 26 granos/m (NS 5030 en 18 ha y DM 46i20 en 39 ha)"
            },
            {
                "fecha": "2026-02-10T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lotes 2 y 3 (Con ensayo orilla)",
                "parametros_aplicacion": {"volumen_agua_lts_ha": 50.0},
                "insumos_utilizados": [
                    {"nombre": "Fungicida Melyra", "dosis": 0.5, "unidad": "lt/ha"},
                    {"nombre": "Graminicida Latium", "dosis": 0.6, "unidad": "lt/ha"},
                    {"nombre": "Coragen", "dosis": 0.03, "unidad": "lt/ha"},
                    {"nombre": "Tolstar Xtra", "dosis": 0.070, "unidad": "lt/ha"},
                    {"nombre": "Dash MSO", "dosis": 0.150, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.050, "unidad": "lt/ha"},
                    {"nombre": "Selt (Stoller)", "dosis": 2.0, "unidad": "lt/ha", "nota": "7 ha orilla Ricardo Gallo"},
                    {"nombre": "Crescere (Innoquim)", "dosis": 1.0, "unidad": "lt/ha", "nota": "Resto 50 ha"}
                ],
                "evaluacion_resultado": "Orilla contra Ricardo Gallo (7 ha) con Selt 2 L/ha, resto con Crescere de Innoquim.",
                "notas": "Fungicida + Graminicida + Insecticida con ensayo foliar en orilla"
            }
        ],
        "lluvias": [
            {"fecha": "2025-11-07T00:00:00Z", "mm": 28.0}
        ]
    }
}


async def migrar_cuaderno_vps(dry_run: bool = False, session=None):
    logger.info(f"=== INICIANDO MIGRACIÓN DEL CUADERNO DEL PRODUCTOR (Dry Run: {dry_run}) ===")

    async def _ejecutar(db):

        # 1. Obtener campaña por defecto o crear 2025/2026
        res_camp = await db.execute(select(Campania).order_by(Campania.fecha_inicio.desc()).limit(1))
        campania_obj = res_camp.scalars().first()
        
        if not campania_obj:
            logger.info("Creando campaña 2025/2026...")
            campania_obj = Campania(
                id=uuid.uuid4(),
                nombre="Campaña 2025/2026",
                fecha_inicio=datetime.strptime("2025-06-01", "%Y-%m-%d").date(),
                activa=True
            )
            db.add(campania_obj)
            await db.flush()


        # 2. Consultar lotes existentes
        res_lotes = await db.execute(select(Lote))
        lotes_existentes = res_lotes.scalars().all()
        logger.info(f"Se encontraron {len(lotes_existentes)} lotes en la base de datos.")

        for key_lote, info_data in LOTE_DATA_MAP.items():
            logger.info(f"Procesando grupo del cuaderno: {key_lote.upper()}...")

            # Buscar lote coincidente por alias de nombre
            lote_target = None
            for l in lotes_existentes:
                nombre_clean = (l.nombre or "").lower().strip()
                if any(alias in nombre_clean for alias in info_data["alias_busqueda"]):
                    lote_target = l
                    break

            if not lote_target:
                logger.warning(f"No se encontró un Lote existente en la BD para '{key_lote}'. Creando lote borrador con datos del cuaderno...")
                lote_target = Lote(
                    id=uuid.uuid4(),
                    nombre=f"Grasso N° {'1' if key_lote == 'grasso_1' else '2 y 3'}",
                    superficie_total_ha=info_data["superficie_ha"],
                    superficie_productiva_ha=info_data["superficie_ha"],
                    cultivo_actual=info_data.get("cultivo_actual"),
                    cultivo_anterior=info_data.get("cultivo_anterior"),
                    cultivo_planificado=info_data.get("cultivo_planificado"),
                    qq_ha_estimado=info_data.get("qq_ha_estimado"),
                    qq_ha_real=info_data.get("qq_ha_real"),
                    produccion_total_qq=info_data.get("produccion_total_qq"),
                    campania_id=campania_obj.id,
                )
                db.add(lote_target)
                await db.flush()
                logger.info(f"✅ Lote '{lote_target.nombre}' creado (ID: {lote_target.id}).")
            else:
                logger.info(f"📍 Coincidencia hallada: Lote BD '{lote_target.nombre}' (ID: {lote_target.id}). Actualizando metadatos agronómicos...")
                lote_target.cultivo_actual = info_data.get("cultivo_actual", lote_target.cultivo_actual)
                lote_target.cultivo_anterior = info_data.get("cultivo_anterior", lote_target.cultivo_anterior)
                lote_target.cultivo_planificado = info_data.get("cultivo_planificado", lote_target.cultivo_planificado)
                lote_target.qq_ha_estimado = info_data.get("qq_ha_estimado", lote_target.qq_ha_estimado)
                lote_target.qq_ha_real = info_data.get("qq_ha_real", lote_target.qq_ha_real)
                if info_data.get("produccion_total_qq"):
                    lote_target.produccion_total_qq = info_data.get("produccion_total_qq")

            # 3. Insertar Labores
            for labor_data in info_data["labores"]:
                fecha_dt = datetime.fromisoformat(labor_data["fecha"].replace("Z", "+00:00"))
                
                # Verificar idempotencia
                res_exist = await db.execute(
                    select(LaborCampo).where(
                        LaborCampo.lote_id == lote_target.id,
                        LaborCampo.tipo_labor == labor_data["tipo_labor"],
                        LaborCampo.fecha == fecha_dt,
                    )
                )
                labor_existente = res_exist.scalars().first()

                if labor_existente:
                    logger.info(f"  - Labor en {fecha_dt.strftime('%d/%m/%Y')} ({labor_data['tipo_labor'].value}) ya existe. Omitiendo...")
                    continue

                nueva_labor = LaborCampo(
                    id=uuid.uuid4(),
                    lote_id=lote_target.id,
                    campania_id=lote_target.campania_id or campania_obj.id,
                    tipo_labor=labor_data["tipo_labor"],
                    fecha=fecha_dt,
                    superficie_afectada_ha=labor_data.get("superficie_afectada_ha"),
                    sector_zona=labor_data.get("sector_zona"),
                    insumos_utilizados=labor_data.get("insumos_utilizados", []),
                    parametros_aplicacion=labor_data.get("parametros_aplicacion"),
                    detalles_siembra=labor_data.get("detalles_siembra"),
                    detalles_cosecha=labor_data.get("detalles_cosecha"),
                    blanco_biologico=labor_data.get("blanco_biologico"),
                    evaluacion_resultado=labor_data.get("evaluacion_resultado"),
                    notas=labor_data.get("notas"),
                )
                db.add(nueva_labor)
                logger.info(f"  + Registrada labor: {labor_data['tipo_labor'].value} ({fecha_dt.strftime('%d/%m/%Y')}) en {lote_target.nombre}")

            # 4. Insertar Registros de Lluvia
            for lluvia_data in info_data.get("lluvias", []):
                fecha_lluvia = datetime.fromisoformat(lluvia_data["fecha"].replace("Z", "+00:00"))
                res_lluvia = await db.execute(
                    select(RegistroLluvia).where(
                        RegistroLluvia.lote_id == lote_target.id,
                        RegistroLluvia.fecha == fecha_lluvia
                    )
                )
                if not res_lluvia.scalars().first():
                    nuevo_registro_lluvia = RegistroLluvia(
                        id=uuid.uuid4(),
                        lote_id=lote_target.id,
                        milimetros=lluvia_data["mm"],
                        fecha=fecha_lluvia
                    )
                    db.add(nuevo_registro_lluvia)
                    logger.info(f"  🌧️ Lluvia registrada: {lluvia_data['mm']} mm el {fecha_lluvia.strftime('%d/%m/%Y')}")

        if dry_run:
            logger.info("DRY RUN activado: revirtiendo cambios sin impactar la base de datos.")
            await db.rollback()
        else:
            await db.commit()
            logger.info("✅ MIGRACIÓN COMPLETADA CON ÉXITO Y CAMBIOS GUARDADOS EN LA BD.")

    if session is not None:
        await _ejecutar(session)
    else:
        async with AsyncSessionLocal() as db:
            await _ejecutar(db)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Migración del Cuaderno del Productor a EduAgro")
    parser.add_argument("--dry-run", action="store_true", help="Simular ejecución sin guardar en la BD")
    args = parser.parse_args()

    asyncio.run(migrar_cuaderno_vps(dry_run=args.dry_run))
