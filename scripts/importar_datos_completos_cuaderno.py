"""
scripts/importar_datos_completos_cuaderno.py
--------------------------------------------------------------------------------
Script integral de importación y actualización de labores agronómicas históricas y 
vigentes para la familia productora (EduAgro).

Diseñado para ejecutarse tanto en entorno local como en VPS de producción:
  1. Detecta si los Campos y Lotes ya existen (por coincidencia exacta o alias) y los actualiza 
     sin duplicarlos, preservando su cliente_id y geometrías.
  2. Si no existen, los crea vinculados al Cliente activo.
  3. Reemplaza limpiamente (sobreescribe) las labores y registros climáticos previos del lote, 
     dejando el historial técnico completo y la campaña actual lista para continuar trabajando.

Uso:
  python scripts/importar_datos_completos_cuaderno.py [--dry-run]
"""

import asyncio
import argparse
from datetime import datetime, timezone, date
import logging
import sys
import os
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.future import select
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models import Lote, Campo, Campania, LaborCampo, RegistroLluvia, Cliente
from app.enums import TipoLabor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("importar_cuaderno")

DATOS_CAMPOS = [
    {
        "key": "grasso",
        "nombre": "Establecimiento Grasso",
        "alias": ["grasso", "establecimiento grasso", "campo grasso", "graso", "establecimiento graso"],
        "hectareas_totales": 114.0,
        "ubicacion": "Laguna Larga / Pilar, Córdoba",
        "localidad_referencia": "Laguna Larga, Córdoba",
        "latitud": -31.78,
        "longitud": -63.80,
    },
    {
        "key": "gontero",
        "nombre": "Establecimiento Gontero",
        "alias": ["gontero", "establecimiento gontero", "campo gontero"],
        "hectareas_totales": 101.0,
        "ubicacion": "Laguna Larga / Pilar, Córdoba",
        "localidad_referencia": "Laguna Larga, Córdoba",
        "latitud": -31.75,
        "longitud": -63.78,
    },
    {
        "key": "venier",
        "nombre": "Establecimiento Venier",
        "alias": ["venier", "establecimiento venier", "campo venier"],
        "hectareas_totales": 85.0,
        "ubicacion": "Laguna Larga / Pilar, Córdoba",
        "localidad_referencia": "Laguna Larga, Córdoba",
        "latitud": -31.80,
        "longitud": -63.82,
    },
]

DATOS_LOTES = {
    # ==================== GRASSO 1 ====================
    "grasso_1": {
        "campo_key": "grasso",
        "nombre": "Grasso 1",
        "alias": ["grasso 1", "grasso n° 1", "grasso nº 1", "grasso n°1", "grasso nº1", "grasso-1", "lote grasso 1", "graso 1", "graso lote 1", "grasso lote 1", "graso n° 1", "graso nº 1"],
        "superficie_ha": 57.0,
        "cultivo_actual": "Barbecho (Post-Maíz)",
        "cultivo_anterior": "Maíz 25/26 (Cosechado 86.3 qq/ha)",
        "cultivo_planificado": "Soja 26/27",
        "qq_ha_estimado": 90.0,
        "qq_ha_real": 86.3,
        "produccion_total_qq": 4835.8,
        "observaciones": "Lote 1 (57 ha). Campaña 25/26 maíz con merma por viento sur del 06/08 y planchado al nacimiento.",
        "labores": [
            {
                "fecha": "2025-04-22T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "detalles_cosecha": {"variedad": "DM 46i20", "cultivo": "Soja"},
                "notas": "Cosecha Soja campaña 24/25 variedad DM 46i20"
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
                "notas": "Barbecho Lado Sur y vuelta alrededor (37 ha)"
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
                "notas": "Fertilización al voleo SPS (102-104 kg/ha)"
            },
            {
                "fecha": "2025-09-26T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "parametros_aplicacion": {"volumen_agua_lts_ha": 58.0, "pastilla_boquilla": "Antideriva 0.15"},
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
                "notas": "Pulverización pre-siembra Maíz"
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
                        {"variedad": "Stine 9720", "superficie_ha": 27.0, "curado_semilla": "40 BB curadas con Potenza (Innoquim) sobre Ricardo Gallo, 10 BB sin curar (testigo)"},
                        {"variedad": "DK 7208 Tre", "superficie_ha": 13.0, "curado_semilla": "10 BB curadas"},
                        {"variedad": "LT 721 TRE", "superficie_ha": 15.0},
                        {"variedad": "LT 721 RR", "superficie_ha": 2.0, "sector": "Cabecera Este"}
                    ]
                },
                "evaluacion_resultado": "El 24/12 llovió de golpe 15mm y a las 22hs otros 20mm. Produjo planchado y encharcado.",
                "notas": "Siembra de Maíz densidad 4.2 sem/m"
            },
            {
                "fecha": "2025-12-28T00:00:00Z",
                "tipo_labor": TipoLabor.LABRANZA,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "notas": "Pasada de rotativa para romper planchado"
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
                "notas": "Post-emergente por escape de malezas"
            },
            {
                "fecha": "2026-01-24T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "insumos_utilizados": [
                    {"nombre": "Urea N-Total", "dosis": 118.0, "unidad": "kg/ha"}
                ],
                "evaluacion_resultado": "Llovió 7mm la noche del 25/01/2026.",
                "notas": "Fertilización Urea N-Total al voleo (116-120 kg/ha)"
            },
            {
                "fecha": "2026-08-21T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 57.0,
                "sector_zona": "Lote Completo",
                "detalles_cosecha": {
                    "cultivo": "Maíz",
                    "rendimiento_qq_ha": 86.3,
                    "total_cosechado_qq": 4835.8,
                    "ensayos": [
                        {"hibrido": "Stine 9820", "rinde_qq_ha": 97.0, "observacion": "Casi nada de daño"},
                        {"hibrido": "LT 721", "rinde_qq_ha": 90.0, "observacion": "Daño intermedio"},
                        {"hibrido": "DK 7208", "rinde_qq_ha": 89.0, "observacion": "El más afectado por viento, pérdida aprox 8 qq"}
                    ]
                },
                "evaluacion_resultado": "Cosechado 8, 21 y 22/08/2026 tras viento sur muy fuerte del 06/08. Merma por viento y falta de población inicial por planchado.",
                "notas": "Cosecha de Maíz 25/26 Grasso 1 (86.3 qq/ha)"
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

    # ==================== GRASSO 2 ====================
    "grasso_2": {
        "campo_key": "grasso",
        "nombre": "Grasso 2",
        "alias": ["grasso 2", "grasso n° 2", "grasso nº 2", "grasso n°2", "grasso nº2", "grasso-2", "lote grasso 2", "graso 2", "graso lote 2", "grasso lote 2", "graso n° 2", "graso nº 2"],
        "superficie_ha": 30.0,
        "cultivo_actual": "Barbecho Químico (Post-Soja)",
        "cultivo_anterior": "Soja 25/26 (Cosechada 41.73 qq/ha DM 46i20)",
        "cultivo_planificado": "Maíz 26/27",
        "qq_ha_estimado": 40.0,
        "qq_ha_real": 41.73,
        "produccion_total_qq": 1251.9,
        "observaciones": "Lote 2 (30 ha). Cosecha soja 25/26 DM 46i20 y barbecho 26/27 aplicado.",
        "labores": [
            {
                "fecha": "2025-07-06T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 30.0,
                "detalles_cosecha": {"cultivo": "Maíz", "rendimiento_qq_ha": 96.07, "humedad_porcentaje": 12.5},
                "notas": "Cosecha Maíz campaña 24/25 con 12.5% humedad"
            },
            {
                "fecha": "2025-08-08T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 30.0,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 35.0, "presion_bar": 4.0, "velocidad_kmh": 16.0, "pastilla_boquilla": "Disco (5) Núcleo (13)"},
                "insumos_utilizados": [
                    {"nombre": "Tijereta Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Dicamba", "dosis": 0.166, "unidad": "lt/ha"},
                    {"nombre": "Atrazina", "dosis": 0.600, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.100, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Grasso 2 con Disco (5) Núcleo (13)"
            },
            {
                "fecha": "2025-09-08T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 30.0,
                "insumos_utilizados": [{"nombre": "Superfosfato Simple (SPS)", "dosis": 103.0, "unidad": "kg/ha"}],
                "notas": "Fertilización SPS al voleo 103 kg/ha"
            },
            {
                "fecha": "2025-10-08T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 30.0,
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Atrazina Gesaprim", "dosis": 0.500, "unidad": "kg/ha"},
                    {"nombre": "Ligate", "dosis": 0.120, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.080, "unidad": "lt/ha"}
                ],
                "evaluacion_resultado": "Llovió el 07/11: 28 mm.",
                "notas": "Pulverización Barbecho Grasso 2"
            },
            {
                "fecha": "2025-11-14T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 30.0,
                "insumos_utilizados": [
                    {"nombre": "Sulfentrazone Capaz", "dosis": 0.533, "unidad": "lt/ha"},
                    {"nombre": "Sulfato de Amonio Trophen", "dosis": 0.250, "unidad": "kg/ha"},
                    {"nombre": "Glufosinato Liberty", "dosis": 2.5, "unidad": "lt/ha"},
                    {"nombre": "Dash MSO", "dosis": 0.250, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.050, "unidad": "lt/ha"}
                ],
                "notas": "Pre-siembra Grasso 2"
            },
            {
                "fecha": "2025-12-04T00:00:00Z",
                "tipo_labor": TipoLabor.SIEMBRA,
                "superficie_afectada_ha": 30.0,
                "detalles_siembra": {"densidad_semillas_m": 26.0, "cultivo": "Soja", "variedad": "DM 46i20"},
                "notas": "Siembra Soja DM 46i20 con 26 granos/m"
            },
            {
                "fecha": "2026-02-10T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 30.0,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 50.0},
                "insumos_utilizados": [
                    {"nombre": "Fungicida Melyra", "dosis": 0.5, "unidad": "lt/ha"},
                    {"nombre": "Graminicida Latium", "dosis": 0.6, "unidad": "lt/ha"},
                    {"nombre": "Coragen", "dosis": 0.030, "unidad": "lt/ha"},
                    {"nombre": "Tolstar Xtra", "dosis": 0.070, "unidad": "lt/ha"},
                    {"nombre": "Dash MSO", "dosis": 0.150, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.050, "unidad": "lt/ha"},
                    {"nombre": "Crescere (Innoquim)", "dosis": 1.0, "unidad": "lt/ha"}
                ],
                "notas": "Fungicida + Insecticida + Nutrición Foliar Soja"
            },
            {
                "fecha": "2026-04-29T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 30.0,
                "detalles_cosecha": {"cultivo": "Soja", "variedad": "DM 46i20", "rendimiento_qq_ha": 41.73, "total_cosechado_qq": 1251.9},
                "notas": "Cosecha Soja 25/26 DM 46i20 (41.73 qq/ha)"
            },
            {
                "fecha": "2026-05-25T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 30.0,
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.6, "unidad": "kg/ha"},
                    {"nombre": "Atrazina Atanor", "dosis": 1.1, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Picloram opsAvst", "dosis": 0.300, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.050, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Químico Grasso 2 Campaña 2026/2027"
            }
        ],
        "lluvias": [
            {"fecha": "2025-11-07T00:00:00Z", "mm": 28.0}
        ]
    },

    # ==================== GRASSO 3 ====================
    "grasso_3": {
        "campo_key": "grasso",
        "nombre": "Grasso 3",
        "alias": ["grasso 3", "grasso n° 3", "grasso nº 3", "grasso n°3", "grasso nº3", "grasso-3", "lote grasso 3", "graso 3", "graso lote 3", "grasso lote 3", "graso n° 3", "graso nº 3"],
        "superficie_ha": 27.0,
        "cultivo_actual": "Barbecho Químico (Post-Soja)",
        "cultivo_anterior": "Soja 25/26 (Cosechada 39.65 qq/ha NS 5030)",
        "cultivo_planificado": "Maíz 26/27",
        "qq_ha_estimado": 40.0,
        "qq_ha_real": 39.65,
        "produccion_total_qq": 1070.55,
        "observaciones": "Lote 3 (27 ha). Cosecha soja 25/26 variedad NS 5030 y barbecho 26/27 aplicado.",
        "labores": [
            {
                "fecha": "2025-07-06T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 27.0,
                "detalles_cosecha": {"cultivo": "Maíz", "rendimiento_qq_ha": 96.07, "humedad_porcentaje": 12.5},
                "notas": "Cosecha Maíz campaña 24/25"
            },
            {
                "fecha": "2025-08-06T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 27.0,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 68.0, "presion_bar": 2.5, "velocidad_kmh": 17.0, "horario": "17:30 - 19:00 hs"},
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
                "fecha": "2025-09-08T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 27.0,
                "insumos_utilizados": [{"nombre": "Superfosfato Simple (SPS)", "dosis": 103.0, "unidad": "kg/ha"}],
                "notas": "Fertilización SPS al voleo 103 kg/ha"
            },
            {
                "fecha": "2025-10-06T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 27.0,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 70.0},
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Atrazina Gesaprim", "dosis": 0.500, "unidad": "kg/ha"},
                    {"nombre": "Ligate", "dosis": 0.120, "unidad": "kg/ha"}
                ],
                "notas": "Pulverización Lote 3 con 70 L/ha agua"
            },
            {
                "fecha": "2025-11-14T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 27.0,
                "insumos_utilizados": [
                    {"nombre": "Sulfentrazone Capaz", "dosis": 0.580, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.100, "unidad": "lt/ha"}
                ],
                "notas": "Pre-siembra Lote 3"
            },
            {
                "fecha": "2025-12-04T00:00:00Z",
                "tipo_labor": TipoLabor.SIEMBRA,
                "superficie_afectada_ha": 27.0,
                "detalles_siembra": {
                    "densidad_semillas_m": 26.0,
                    "cultivo": "Soja",
                    "distribucion_semillas": [
                        {"variedad": "NS 5030", "superficie_ha": 18.0, "nota": "Variedad nueva"},
                        {"variedad": "DM 46i20", "superficie_ha": 9.0}
                    ]
                },
                "notas": "Siembra Soja (18 ha NS 5030 y 9 ha DM 46i20)"
            },
            {
                "fecha": "2026-02-10T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 27.0,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 50.0},
                "insumos_utilizados": [
                    {"nombre": "Fungicida Melyra", "dosis": 0.5, "unidad": "lt/ha"},
                    {"nombre": "Graminicida Latium", "dosis": 0.6, "unidad": "lt/ha"},
                    {"nombre": "Coragen", "dosis": 0.030, "unidad": "lt/ha"},
                    {"nombre": "Tolstar Xtra", "dosis": 0.070, "unidad": "lt/ha"},
                    {"nombre": "Dash MSO", "dosis": 0.150, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.050, "unidad": "lt/ha"},
                    {"nombre": "Selt (Stoller)", "dosis": 2.0, "unidad": "lt/ha", "nota": "7 ha orilla Ricardo Gallo"},
                    {"nombre": "Crescere (Innoquim)", "dosis": 1.0, "unidad": "lt/ha", "nota": "Resto 20 ha"}
                ],
                "evaluacion_resultado": "Ensayo orilla contra Ricardo Gallo (7 ha) con Selt 2 L/ha, resto con Crescere.",
                "notas": "Fungicida + Insecticida con ensayo foliar en orilla"
            },
            {
                "fecha": "2026-04-29T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 27.0,
                "detalles_cosecha": {"cultivo": "Soja", "variedad": "NS 5030", "rendimiento_qq_ha": 39.65, "total_cosechado_qq": 1070.55},
                "notas": "Cosecha Soja 25/26 NS 5030 (39.65 qq/ha)"
            },
            {
                "fecha": "2026-05-25T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 27.0,
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.6, "unidad": "kg/ha"},
                    {"nombre": "Atrazina Atanor", "dosis": 1.1, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Picloram opsAvst", "dosis": 0.300, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.050, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Químico Grasso 3 Campaña 2026/2027"
            }
        ],
        "lluvias": [
            {"fecha": "2025-11-07T00:00:00Z", "mm": 28.0}
        ]
    },

    # ==================== GONTERO 1 / NORTE ====================
    "gontero_1": {
        "campo_key": "gontero",
        "nombre": "Gontero 1 (Norte)",
        "alias": ["gontero 1", "gontero norte", "gontero n° 1", "gontero nº 1", "gontero 1 (norte)", "gontero 1 / norte", "lote gontero 1", "gontero lote 1", "gontero n°1", "gontero nº1"],
        "superficie_ha": 50.5,
        "cultivo_actual": "Barbecho (Post-Maíz)",
        "cultivo_anterior": "Maíz 25/26 (Cosechado 85.0 qq/ha)",
        "cultivo_planificado": "Soja 26/27",
        "qq_ha_estimado": 90.0,
        "qq_ha_real": 85.0,
        "produccion_total_qq": 4253.6,
        "observaciones": "Gontero 1 (50.5 ha). Maíz 25/26 con ensayos LT 3-02, BASF 5747, LT 721 y DK 7447.",
        "labores": [
            {
                "fecha": "2025-04-30T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 50.5,
                "detalles_cosecha": {"variedad": "AW 4927", "cultivo": "Soja", "rendimiento_qq_ha": 37.5, "total_cosechado_qq": 1893.0},
                "notas": "Cosecha Soja AW 4927 Campaña 24/25"
            },
            {
                "fecha": "2025-08-18T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 50.5,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 52.0, "presion_bar": 2.0, "velocidad_kmh": 19.0, "pastilla_boquilla": "Cono hueco 0.20"},
                "insumos_utilizados": [
                    {"nombre": "Tijereta Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.176, "unidad": "lt/ha"},
                    {"nombre": "Picloram", "dosis": 0.240, "unidad": "lt/ha"},
                    {"nombre": "Atrazina", "dosis": 0.900, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.100, "unidad": "lt/ha"},
                    {"nombre": "Mictec", "dosis": 0.100, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Gontero 1 con cono hueco 0.20 a 52 L/ha"
            },
            {
                "fecha": "2025-09-18T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 50.5,
                "insumos_utilizados": [{"nombre": "Superfosfato Simple (SPS)", "dosis": 101.0, "unidad": "kg/ha"}],
                "notas": "Fertilización SPS al voleo 101 kg/ha"
            },
            {
                "fecha": "2025-09-26T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 50.5,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 58.0, "pastilla_boquilla": "Antideriva 0.15"},
                "insumos_utilizados": [
                    {"nombre": "S-metolacloro", "dosis": 1.1, "unidad": "lt/ha"},
                    {"nombre": "Atrazina", "dosis": 1.0, "unidad": "kg/ha"}
                ],
                "notas": "Pre-emergente Maíz Gontero 1"
            },
            {
                "fecha": "2025-11-13T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 50.5,
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Flumioxazin Gemmitop", "dosis": 0.156, "unidad": "lt/ha"},
                    {"nombre": "Pyroxasulfone Zidua", "dosis": 0.200, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.080, "unidad": "lt/ha"}
                ],
                "notas": "Pre-siembra Maíz Gontero 1"
            },
            {
                "fecha": "2025-12-24T00:00:00Z",
                "tipo_labor": TipoLabor.SIEMBRA,
                "superficie_afectada_ha": 50.5,
                "detalles_siembra": {
                    "densidad_semillas_m": 4.2,
                    "cultivo": "Maíz",
                    "horario": "02:00 am a 16:30 hs",
                    "distribucion_semillas": [
                        {"variedad": "LT 721 RR", "superficie_ha": 18.0, "sector": "Norte a Sur", "nota": "Incluye 20 surcos BASF 5747 VIP3CL"},
                        {"variedad": "LT 3-02 TRE", "superficie_ha": 21.0, "curado_semilla": "10 bolsas curadas con Potenza"},
                        {"variedad": "DK 7447 TRE", "superficie_ha": 10.0}
                    ]
                },
                "evaluacion_resultado": "Sufrió planchado tras siembra. Se pasó rotativa en cabecera Este y 2 esquinas Este.",
                "notas": "Siembra de Maíz con rotativa por planchado"
            },
            {
                "fecha": "2026-01-24T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 50.5,
                "insumos_utilizados": [{"nombre": "Urea N-Total", "dosis": 119.0, "unidad": "kg/ha"}],
                "evaluacion_resultado": "Llovió 7 mm el 25/01/2026 a la noche.",
                "notas": "Fertilización Urea N-Total al voleo (118-120 kg/ha)"
            },
            {
                "fecha": "2026-08-18T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 50.5,
                "detalles_cosecha": {
                    "cultivo": "Maíz",
                    "rendimiento_qq_ha": 85.0,
                    "total_cosechado_qq": 4253.6,
                    "ensayos": [
                        {"hibrido": "LT 3-02", "rinde_qq_ha": 95.83},
                        {"hibrido": "BASF 5747 VIP3CL", "rinde_qq_ha": 95.37},
                        {"hibrido": "LT 721 RR", "rinde_qq_ha": 89.0, "observacion": "Bastante daño de viento"},
                        {"hibrido": "DK 7447", "rinde_qq_ha": 86.0, "observacion": "Afectado por planchado inicial"}
                    ]
                },
                "evaluacion_resultado": "Cosechado 9, 17 y 18/08/2026. Merma por viento, planchado a minutos de sembrar y falta de población en mitad sur 3-02 por error de placa.",
                "notas": "Cosecha Maíz 25/26 Gontero 1 (85 qq/ha)"
            }
        ],
        "lluvias": [
            {"fecha": "2026-01-25T22:00:00Z", "mm": 7.0}
        ]
    },

    # ==================== GONTERO 2 / SUR ====================
    "gontero_2": {
        "campo_key": "gontero",
        "nombre": "Gontero 2 (Sur)",
        "alias": ["gontero 2", "gontero sur", "gontero n° 2", "gontero nº 2", "gontero 2 (sur)", "gontero 2 / sur", "lote gontero 2", "gontero lote 2", "gontero n°2", "gontero nº2"],
        "superficie_ha": 50.5,
        "cultivo_actual": "Barbecho Químico (Post-Soja)",
        "cultivo_anterior": "Soja 25/26 (Cosechada 38.35 qq/ha A4927)",
        "cultivo_planificado": "Maíz 26/27",
        "qq_ha_estimado": 40.0,
        "qq_ha_real": 38.35,
        "produccion_total_qq": 1936.8,
        "observaciones": "Gontero 2 (50.5 ha). Soja A4927 ists y barbecho 26/27 aplicado.",
        "labores": [
            {
                "fecha": "2025-07-04T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 50.5,
                "detalles_cosecha": {"cultivo": "Maíz", "rendimiento_qq_ha": 98.8, "total_cosechado_qq": 4989.6, "humedad_porcentaje": 12.8},
                "notas": "Cosecha Maíz 24/25 Gontero 2 con 12.8% humedad"
            },
            {
                "fecha": "2025-08-18T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 50.5,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 51.0, "presion_bar": 1.8, "velocidad_kmh": 19.0, "pastilla_boquilla": "Cono hueco 0.20"},
                "insumos_utilizados": [
                    {"nombre": "Tijereta Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.176, "unidad": "lt/ha"},
                    {"nombre": "Atrazina", "dosis": 0.820, "unidad": "kg/ha"},
                    {"nombre": "Dicamba", "dosis": 0.157, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.050, "unidad": "lt/ha"},
                    {"nombre": "Mictec", "dosis": 0.060, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Gontero 2 a 51 L/ha"
            },
            {
                "fecha": "2025-09-19T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 50.5,
                "insumos_utilizados": [{"nombre": "Superfosfato Simple (SPS)", "dosis": 101.0, "unidad": "kg/ha"}],
                "notas": "Fertilización SPS al voleo 101 kg/ha"
            },
            {
                "fecha": "2025-10-08T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 50.5,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 40.0, "horario": "Nocturno"},
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Atrazina Gesaprim", "dosis": 0.500, "unidad": "kg/ha"},
                    {"nombre": "Ligate", "dosis": 0.120, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.080, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho nocturno a 40 L/ha agua"
            },
            {
                "fecha": "2025-11-14T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 50.5,
                "insumos_utilizados": [
                    {"nombre": "Sulfentrazone Capaz", "dosis": 0.540, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.100, "unidad": "lt/ha"}
                ],
                "notas": "Pre-siembra Gontero 2"
            },
            {
                "fecha": "2025-11-22T00:00:00Z",
                "tipo_labor": TipoLabor.SIEMBRA,
                "superficie_afectada_ha": 50.5,
                "detalles_siembra": {
                    "cultivo": "Soja",
                    "variedad": "A4927 ists",
                    "densidad_semillas_m": 28.0,
                    "profundidad_cm": 4.0,
                    "orientacion": "NO a SE",
                    "dosis_kg_ha": 60.0
                },
                "notas": "Siembra Soja A4927 a 28 granos/m a 4 cm prof"
            },
            {
                "fecha": "2026-01-23T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 50.5,
                "insumos_utilizados": [
                    {"nombre": "Control Max", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "Graminicida Latium", "dosis": 0.700, "unidad": "lt/ha"},
                    {"nombre": "Coragen", "dosis": 0.030, "unidad": "lt/ha"},
                    {"nombre": "Talstar Xtra", "dosis": 0.070, "unidad": "lt/ha"},
                    {"nombre": "Sett Stoller", "dosis": 2.0, "unidad": "lt/ha"},
                    {"nombre": "Fungicida Melyra", "dosis": 0.600, "unidad": "lt/ha"},
                    {"nombre": "Dash BASF", "dosis": 0.200, "unidad": "lt/ha"}
                ],
                "notas": "Fitosanitario completo: Graminicida + Fungicida + Insecticida + Foliar"
            },
            {
                "fecha": "2026-04-12T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 50.5,
                "detalles_cosecha": {"cultivo": "Soja", "variedad": "AW 4927", "rendimiento_qq_ha": 38.35, "total_cosechado_qq": 1936.8},
                "notas": "Cosechado 10, 11 y 13/04/2026 (1936.8 qq totales)"
            },
            {
                "fecha": "2026-05-26T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 50.5,
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.6, "unidad": "kg/ha"},
                    {"nombre": "Atrazina", "dosis": 1.1, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Picloram", "dosis": 0.300, "unidad": "lt/ha"},
                    {"nombre": "A35T", "dosis": 0.077, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.070, "unidad": "lt/ha"},
                    {"nombre": "Dash", "dosis": 0.135, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Químico Gontero 2 Campaña 2026/2027"
            }
        ],
        "lluvias": []
    },

    # ==================== VENIER 1 ====================
    "venier_1": {
        "campo_key": "venier",
        "nombre": "Venier 1",
        "alias": ["venier 1", "venier n° 1", "venier nº 1", "venier n°1", "venier nº1", "lote venier 1", "venier lote 1", "venier-1", "venier 1 (42 has)"],
        "superficie_ha": 42.0,
        "cultivo_actual": "Barbecho (Post-Maíz)",
        "cultivo_anterior": "Maíz 25/26 (Cosechado 92.15 qq/ha)",
        "cultivo_planificado": "Soja 26/27",
        "qq_ha_estimado": 90.0,
        "qq_ha_real": 92.15,
        "produccion_total_qq": 3778.0,
        "observaciones": "Venier 1 (42 ha). Maíz 25/26 con ensayos DK 7220, Acrux, Aron y LT 721.",
        "labores": [
            {
                "fecha": "2025-04-15T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 42.0,
                "detalles_cosecha": {"variedad": "AW 4326", "cultivo": "Soja", "rendimiento_qq_ha": 45.75, "total_cosechado_qq": 1612.4},
                "notas": "Cosecha Soja AW 4326 Campaña 24/25"
            },
            {
                "fecha": "2025-05-24T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 42.0,
                "insumos_utilizados": [
                    {"nombre": "Roundup Top", "dosis": 2.3, "unidad": "lt/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Picloram", "dosis": 0.266, "unidad": "lt/ha"},
                    {"nombre": "Atrazina", "dosis": 0.630, "unidad": "kg/ha"},
                    {"nombre": "Mictec", "dosis": 0.070, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Venier 1"
            },
            {
                "fecha": "2025-09-12T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 42.0,
                "insumos_utilizados": [{"nombre": "Superfosfato Simple (SPS)", "dosis": 102.0, "unidad": "kg/ha"}],
                "notas": "Fertilización SPS al voleo 102 kg/ha (11-13/09/25)"
            },
            {
                "fecha": "2025-09-26T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 42.0,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 58.0, "pastilla_boquilla": "Abanico plano 0.15"},
                "insumos_utilizados": [
                    {"nombre": "S-metolacloro", "dosis": 1.1, "unidad": "lt/ha"},
                    {"nombre": "Atrazina", "dosis": 1.0, "unidad": "kg/ha"}
                ],
                "notas": "Pre-emergente Maíz Venier 1 con pastilla 0.15 abanico plano"
            },
            {
                "fecha": "2025-12-17T00:00:00Z",
                "tipo_labor": TipoLabor.SIEMBRA,
                "superficie_afectada_ha": 42.0,
                "detalles_siembra": {
                    "cultivo": "Maíz",
                    "densidad_semillas_m": 4.2,
                    "fertilizante_linea": "80 kg/ha MicroEssentials SZ",
                    "distribucion_semillas": [
                        {"variedad": "DK 7220 RR", "superficie_ha": 4.0, "sector": "Sur a Norte"},
                        {"variedad": "Nord Acrux", "superficie_ha": 16.0},
                        {"variedad": "Nord Aron", "superficie_ha": 14.0},
                        {"variedad": "LT 721 Trecepta", "superficie_ha": 8.5}
                    ]
                },
                "notas": "Siembra Maíz con 80 kg MicroEssentials SZ a 4.2 pl/m"
            },
            {
                "fecha": "2026-01-07T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 10.0,
                "sector_zona": "Vuelta alrededor",
                "insumos_utilizados": [{"nombre": "Glifo Top", "dosis": 3.5, "unidad": "lt/ha"}],
                "notas": "Vuelta alrededor por nacimiento de gramíneas"
            },
            {
                "fecha": "2026-01-07T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 42.0,
                "insumos_utilizados": [{"nombre": "Urea N-Total", "dosis": 114.0, "unidad": "kg/ha"}],
                "evaluacion_resultado": "Llovió 5mm esa noche y 48mm el 08/01.",
                "notas": "Fertilización Urea N-Total al voleo 114 kg/ha"
            },
            {
                "fecha": "2026-01-11T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 42.0,
                "blanco_biologico": "Escape de porotillo y malvón",
                "insumos_utilizados": [
                    {"nombre": "Glifo Top", "dosis": 2.5, "unidad": "lt/ha"},
                    {"nombre": "Mictec", "dosis": 0.110, "unidad": "lt/ha"}
                ],
                "notas": "Post-emergente Maíz Venier 1"
            },
            {
                "fecha": "2026-08-21T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 42.0,
                "detalles_cosecha": {
                    "cultivo": "Maíz",
                    "rendimiento_qq_ha": 92.15,
                    "total_cosechado_qq": 3778.0,
                    "ensayos": [
                        {"hibrido": "DK 7220 RR", "rinde_qq_ha": 95.6},
                        {"hibrido": "Nord Acrux", "rinde_qq_ha": 94.3},
                        {"hibrido": "Nord Aron", "rinde_qq_ha": 92.0},
                        {"hibrido": "LT 721 TRE", "rinde_qq_ha": 90.0}
                    ]
                },
                "evaluacion_resultado": "Cosechado 20-21/08/2026 con poco daño de viento pero algo de pérdida.",
                "notas": "Cosecha Maíz 25/26 Venier 1 (92.15 qq/ha)"
            }
        ],
        "lluvias": [
            {"fecha": "2026-01-07T22:00:00Z", "mm": 5.0},
            {"fecha": "2026-01-08T18:00:00Z", "mm": 48.0}
        ]
    },

    # ==================== VENIER 2 ====================
    "venier_2": {
        "campo_key": "venier",
        "nombre": "Venier 2",
        "alias": ["venier 2", "venier n° 2", "venier nº 2", "venier n°2", "venier nº2", "venier 2 y 3", "venier 2y3", "lote venier 2", "venier lote 2", "venier-2", "venier 2 y 3 (43 has)", "venier 2 (43 has)"],
        "superficie_ha": 43.0,
        "cultivo_actual": "Barbecho Químico (Post-Soja)",
        "cultivo_anterior": "Soja 25/26 (Cosechada 36.62 qq/ha AW 4326/NS 5030)",
        "cultivo_planificado": "Maíz 26/27",
        "qq_ha_estimado": 40.0,
        "qq_ha_real": 36.62,
        "produccion_total_qq": 1538.4,
        "observaciones": "Venier 2 (43 ha = Lote 2 de 32 ha + Lote 3 de 11 ha). Cosecha soja 25/26 y barbecho 26/27 aplicado.",
        "labores": [
            {
                "fecha": "2025-06-01T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 43.0,
                "detalles_cosecha": {
                    "cultivo": "Maíz",
                    "rendimiento_qq_ha": 95.3,
                    "total_cosechado_qq": 4003.3,
                    "ensayos": [
                        {"hibrido": "DK 7272", "rinde_qq_ha": 105.0},
                        {"hibrido": "Acrux", "rinde_qq_ha": 98.6}
                    ]
                },
                "notas": "Cosecha Maíz 24/25 Venier 2 (30/05 y 01/06/25)"
            },
            {
                "fecha": "2025-08-18T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 42.5,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 65.0, "presion_bar": 2.5, "velocidad_kmh": 18.0, "pastilla_boquilla": "Cono hueco 0.20"},
                "insumos_utilizados": [
                    {"nombre": "Tijereta Box", "dosis": 1.62, "unidad": "kg/ha"},
                    {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Dicamba", "dosis": 0.163, "unidad": "lt/ha"},
                    {"nombre": "Atrazina Atramit", "dosis": 0.700, "unidad": "kg/ha"}
                ],
                "notas": "Barbecho aplicado junto con el N°3 (42.5 ha)"
            },
            {
                "fecha": "2025-09-15T00:00:00Z",
                "tipo_labor": TipoLabor.FERTILIZACION,
                "superficie_afectada_ha": 43.0,
                "insumos_utilizados": [{"nombre": "Superfosfato Simple (SPS)", "dosis": 102.0, "unidad": "kg/ha"}],
                "notas": "Fertilización SPS al voleo 102 kg/ha"
            },
            {
                "fecha": "2025-10-15T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 43.0,
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Atrazina Gesaprim", "dosis": 0.500, "unidad": "kg/ha"},
                    {"nombre": "Pyroxasulfone Zidua", "dosis": 0.200, "unidad": "kg/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.080, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Venier 2 (faltó gemmitop flumioxazin)"
            },
            {
                "fecha": "2025-11-13T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 43.0,
                "insumos_utilizados": [
                    {"nombre": "Sulfentrazone Capaz", "dosis": 0.533, "unidad": "lt/ha"},
                    {"nombre": "Graminicida Latium", "dosis": 0.690, "unidad": "lt/ha"},
                    {"nombre": "Dash MSO", "dosis": 0.120, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.080, "unidad": "lt/ha"}
                ],
                "notas": "Pre-siembra Soja Venier 2"
            },
            {
                "fecha": "2025-12-04T00:00:00Z",
                "tipo_labor": TipoLabor.SIEMBRA,
                "superficie_afectada_ha": 43.0,
                "detalles_siembra": {
                    "cultivo": "Soja",
                    "distribucion_semillas": [
                        {"sector": "Lote 3", "superficie_ha": 11.0, "distancia_cm": 35.0, "pasadas": 2, "densidad_gr_m": 11.0, "variedad": "AW 4326"},
                        {"sector": "Lote 2", "superficie_ha": 32.0, "densidad_gr_m": 28.0, "variedad": "AW 4326 (25 ha) y NS 5030 (6 ha)"}
                    ]
                },
                "notas": "Siembra Soja: Lote 3 a 0.35m con 2 pasadas (11 ha) y Lote 2 normal (32 ha)"
            },
            {
                "fecha": "2026-01-17T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 43.0,
                "insumos_utilizados": [
                    {"nombre": "Cletodim Latium", "dosis": 0.700, "unidad": "lt/ha"},
                    {"nombre": "Crescere (Innoquim)", "dosis": 0.200, "unidad": "lt/ha"},
                    {"nombre": "Mictec (Innoquim)", "dosis": 0.110, "unidad": "lt/ha"},
                    {"nombre": "Dash MSO BASF", "dosis": 0.110, "unidad": "lt/ha"}
                ],
                "notas": "Post-emergente Graminicida + Nutrición Foliar"
            },
            {
                "fecha": "2026-02-07T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 43.0,
                "parametros_aplicacion": {"volumen_agua_lts_ha": 57.0},
                "insumos_utilizados": [
                    {"nombre": "Fungicida Melyra", "dosis": 0.500, "unidad": "lt/ha"},
                    {"nombre": "Glifo Top", "dosis": 2.0, "unidad": "lt/ha"},
                    {"nombre": "Coragen", "dosis": 0.030, "unidad": "lt/ha"},
                    {"nombre": "Talstar Xtra", "dosis": 0.070, "unidad": "lt/ha"},
                    {"nombre": "Sett Stoller", "dosis": 2.0, "unidad": "lt/ha"},
                    {"nombre": "Dash", "dosis": 0.150, "unidad": "lt/ha"}
                ],
                "notas": "Fungicida + Insecticida + Foliar a 57 L/ha agua"
            },
            {
                "fecha": "2026-05-01T00:00:00Z",
                "tipo_labor": TipoLabor.COSECHA,
                "superficie_afectada_ha": 43.0,
                "detalles_cosecha": {
                    "cultivo": "Soja",
                    "variedad": "AW 4326 y NS 5030",
                    "rendimiento_qq_ha": 36.62,
                    "total_cosechado_qq": 1538.4
                },
                "notas": "Cosechado 30/04 y 01/05/2026 (1538.4 qq totales)"
            },
            {
                "fecha": "2026-05-23T00:00:00Z",
                "tipo_labor": TipoLabor.PULVERIZACION,
                "superficie_afectada_ha": 43.0,
                "insumos_utilizados": [
                    {"nombre": "LT Box", "dosis": 1.6, "unidad": "kg/ha"},
                    {"nombre": "Atrazina", "dosis": 1.1, "unidad": "kg/ha"},
                    {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
                    {"nombre": "Picloram", "dosis": 0.300, "unidad": "lt/ha"},
                    {"nombre": "A35T", "dosis": 0.050, "unidad": "lt/ha"},
                    {"nombre": "Altiva Pro", "dosis": 0.050, "unidad": "lt/ha"}
                ],
                "notas": "Barbecho Químico Venier 2 Campaña 2026/2027"
            }
        ],
        "lluvias": []
    }
}


def encontrar_campo_coincidente(campos_bd, campo_dict):
    """Busca un campo existente por nombre exacto o por alias."""
    nombre_target = campo_dict["nombre"].lower().strip()
    aliases = [a.lower().strip() for a in campo_dict.get("alias", [])]

    # 1. Búsqueda exacta
    for c in campos_bd:
        c_name = (c.nombre or "").lower().strip()
        if c_name == nombre_target:
            return c

    # 2. Búsqueda por alias
    for c in campos_bd:
        c_name = (c.nombre or "").lower().strip()
        if any(al == c_name or al in c_name or c_name in al for al in aliases):
            return c

    return None


def encontrar_lote_coincidente(lotes_bd, lote_dict, campo_id=None):
    """Busca un lote existente dentro del campo (o globalmente) por coincidencia de nombre o alias."""
    candidatos = [l for l in lotes_bd if campo_id is None or l.campo_id == campo_id]
    nombre_target = lote_dict["nombre"].lower().strip()
    aliases = [a.lower().strip() for a in lote_dict.get("alias", [])]

    # 1. Coincidencia exacta
    for l in candidatos:
        l_name = (l.nombre or "").lower().strip()
        if l_name == nombre_target:
            return l

    # 2. Coincidencia por alias
    for l in candidatos:
        l_name = (l.nombre or "").lower().strip()
        if any(al == l_name or al in l_name or l_name in al for al in aliases):
            return l

    return None


async def ejecutar_importacion(dry_run: bool = False):
    logger.info(f"=== INICIANDO IMPORTACIÓN INTEGRAL DE CAMPOS, LOTES Y LABORES (Dry Run: {dry_run}) ===")

    async with AsyncSessionLocal() as db:
        # 1. Obtener Cliente Activo si existe (para vincular entidades en VPS)
        res_cli = await db.execute(select(Cliente).where(Cliente.activo == True).limit(1))
        cliente_activo = res_cli.scalars().first()
        cliente_id_default = cliente_activo.id if cliente_activo else None
        if cliente_activo:
            logger.info(f"🏢 Cliente detectado en el entorno: '{cliente_activo.nombre}' (ID: {cliente_id_default})")

        # 2. Verificar/Crear Campañas
        res_c25 = await db.execute(select(Campania).where(Campania.nombre.ilike("%2025/2026%")).limit(1))
        camp_25_26 = res_c25.scalars().first()
        if not camp_25_26:
            camp_25_26 = Campania(
                id=uuid.uuid4(),
                nombre="Campaña 2025/2026",
                fecha_inicio=date(2025, 6, 1),
                fecha_fin=date(2026, 5, 31),
                activa=False
            )
            db.add(camp_25_26)
            await db.flush()

        res_c26 = await db.execute(select(Campania).where(Campania.nombre.ilike("%2026/2027%")).limit(1))
        camp_26_27 = res_c26.scalars().first()
        if not camp_26_27:
            camp_26_27 = Campania(
                id=uuid.uuid4(),
                nombre="Campaña 2026/2027",
                fecha_inicio=date(2026, 6, 1),
                activa=True
            )
            db.add(camp_26_27)
            await db.flush()

        # 3. Consultar Campos y Lotes existentes en la base de datos
        res_campos_bd = await db.execute(select(Campo))
        campos_bd = list(res_campos_bd.scalars().all())

        res_lotes_bd = await db.execute(select(Lote))
        lotes_bd = list(res_lotes_bd.scalars().all())

        campos_map = {}
        for campo_data in DATOS_CAMPOS:
            campo_obj = encontrar_campo_coincidente(campos_bd, campo_data)
            if not campo_obj:
                campo_obj = Campo(
                    id=uuid.uuid4(),
                    cliente_id=cliente_id_default,
                    nombre=campo_data["nombre"],
                    hectareas_totales=campo_data["hectareas_totales"],
                    ubicacion=campo_data["ubicacion"],
                    localidad_referencia=campo_data["localidad_referencia"],
                    latitud=campo_data["latitud"],
                    longitud=campo_data["longitud"]
                )
                db.add(campo_obj)
                await db.flush()
                campos_bd.append(campo_obj)
                logger.info(f"🌾 Campo creado: '{campo_obj.nombre}' (ID: {campo_obj.id})")
            else:
                campo_obj.hectareas_totales = campo_data["hectareas_totales"]
                campo_obj.ubicacion = campo_data["ubicacion"] or campo_obj.ubicacion
                campo_obj.localidad_referencia = campo_data["localidad_referencia"] or campo_obj.localidad_referencia
                if not campo_obj.cliente_id and cliente_id_default:
                    campo_obj.cliente_id = cliente_id_default
                logger.info(f"🌾 Campo coincidente hallado: '{campo_obj.nombre}' (ID: {campo_obj.id})")
            campos_map[campo_data["key"]] = campo_obj

        # 4. Limpiar lotes agrupados obsoletos (ej: 'Grasso N° 2 y 3') si persistieran
        res_old = await db.execute(select(Lote).where(Lote.nombre.in_(["Grasso N° 2 y 3", "Grasso 2 y 3", "Grasso 2 y 3 (57 has)"])))
        lotes_old = res_old.scalars().all()
        for old_lote in lotes_old:
            logger.info(f"🗑️ Eliminando lote agrupado obsoleto '{old_lote.nombre}'...")
            await db.execute(delete(LaborCampo).where(LaborCampo.lote_id == old_lote.id))
            await db.execute(delete(RegistroLluvia).where(RegistroLluvia.lote_id == old_lote.id))
            await db.delete(old_lote)
            if old_lote in lotes_bd:
                lotes_bd.remove(old_lote)
        await db.flush()

        # 5. Poblar / Actualizar Lotes y sobreescribir sus labores técnicas
        for lote_key, l_data in DATOS_LOTES.items():
            campo_parent = campos_map[l_data["campo_key"]]
            lote_obj = encontrar_lote_coincidente(lotes_bd, l_data, campo_id=campo_parent.id)

            if not lote_obj:
                lote_obj = Lote(
                    id=uuid.uuid4(),
                    campo_id=campo_parent.id,
                    cliente_id=campo_parent.cliente_id or cliente_id_default,
                    campania_id=camp_26_27.id,
                    nombre=l_data["nombre"],
                    superficie_total_ha=l_data["superficie_ha"],
                    superficie_productiva_ha=l_data["superficie_ha"],
                    cultivo_actual=l_data["cultivo_actual"],
                    cultivo_anterior=l_data["cultivo_anterior"],
                    cultivo_planificado=l_data["cultivo_planificado"],
                    qq_ha_estimado=l_data["qq_ha_estimado"],
                    qq_ha_real=l_data["qq_ha_real"],
                    produccion_total_qq=l_data["produccion_total_qq"],
                    observaciones=l_data["observaciones"]
                )
                db.add(lote_obj)
                await db.flush()
                lotes_bd.append(lote_obj)
                logger.info(f"📍 Lote creado: '{lote_obj.nombre}' ({lote_obj.superficie_total_ha} ha) en {campo_parent.nombre}")
            else:
                lote_obj.superficie_total_ha = l_data["superficie_ha"]
                lote_obj.superficie_productiva_ha = l_data["superficie_ha"]
                lote_obj.cultivo_actual = l_data["cultivo_actual"]
                lote_obj.cultivo_anterior = l_data["cultivo_anterior"]
                lote_obj.cultivo_planificado = l_data["cultivo_planificado"]
                lote_obj.qq_ha_estimado = l_data["qq_ha_estimado"]
                lote_obj.qq_ha_real = l_data["qq_ha_real"]
                lote_obj.produccion_total_qq = l_data["produccion_total_qq"]
                lote_obj.observaciones = l_data["observaciones"]
                lote_obj.campania_id = camp_26_27.id
                if not lote_obj.cliente_id and (campo_parent.cliente_id or cliente_id_default):
                    lote_obj.cliente_id = campo_parent.cliente_id or cliente_id_default
                logger.info(f"📍 Lote coincidente actualizado: '{lote_obj.nombre}' (ID: {lote_obj.id}) en {campo_parent.nombre}")

            # Sobreescribir labores y lluvias previas del lote para dejarlo 100% limpio y consistente
            await db.execute(delete(LaborCampo).where(LaborCampo.lote_id == lote_obj.id))
            await db.execute(delete(RegistroLluvia).where(RegistroLluvia.lote_id == lote_obj.id))
            await db.flush()

            # Insertar Labores
            for lab in l_data["labores"]:
                fecha_dt = datetime.fromisoformat(lab["fecha"].replace("Z", "+00:00"))
                c_id = camp_26_27.id if fecha_dt >= datetime(2026, 5, 20, tzinfo=timezone.utc) else camp_25_26.id

                nueva_labor = LaborCampo(
                    id=uuid.uuid4(),
                    lote_id=lote_obj.id,
                    campania_id=c_id,
                    tipo_labor=lab["tipo_labor"],
                    fecha=fecha_dt,
                    superficie_afectada_ha=lab.get("superficie_afectada_ha", lote_obj.superficie_total_ha),
                    sector_zona=lab.get("sector_zona"),
                    insumos_utilizados=lab.get("insumos_utilizados", []),
                    parametros_aplicacion=lab.get("parametros_aplicacion"),
                    detalles_siembra=lab.get("detalles_siembra"),
                    detalles_cosecha=lab.get("detalles_cosecha"),
                    blanco_biologico=lab.get("blanco_biologico"),
                    evaluacion_resultado=lab.get("evaluacion_resultado"),
                    notas=lab.get("notas")
                )
                db.add(nueva_labor)
            
            logger.info(f"   🌱 {len(l_data['labores'])} labores registradas para {lote_obj.nombre}")

            # Insertar Lluvias
            for llu in l_data.get("lluvias", []):
                fecha_ll = datetime.fromisoformat(llu["fecha"].replace("Z", "+00:00"))
                reg_lluvia = RegistroLluvia(
                    id=uuid.uuid4(),
                    lote_id=lote_obj.id,
                    fecha=fecha_ll,
                    milimetros=llu["mm"]
                )
                db.add(reg_lluvia)

        if dry_run:
            logger.info("⚠️ DRY RUN: Revirtiendo todos los cambios sin escribir en la base de datos.")
            await db.rollback()
        else:
            await db.commit()
            logger.info("✅ IMPORTACIÓN Y REESTRUCTURACIÓN DE LABORES FINALIZADA CON ÉXITO.")

    # 4. Sincronizar Cosecha, Silos, Acopios y Contratistas
    try:
        from scripts.poblar_cosecha_distribucion_y_contratistas import poblar_datos_cosecha_y_contratistas
        logger.info("🌾 Ejecutando sincronización de cosecha, distribución física de granos y contratistas...")
        await poblar_datos_cosecha_y_contratistas(dry_run=dry_run)
    except Exception as e:
        logger.warning(f"No se pudo ejecutar sincronización de cosecha y silos: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importación integral de lotes y labores de EduAgro")
    parser.add_argument("--dry-run", action="store_true", help="Simular ejecución sin guardar cambios")
    args = parser.parse_args()

    asyncio.run(ejecutar_importacion(dry_run=args.dry_run))

