"""
app/services/labores_plantillas.py
--------------------------------------------------------------------------------
Servicio de gestión y auto-aprendizaje de Plantillas y Recetas de Labores de Campo.

Funcionalidades:
  1. Catálogo canónico predefinido para cada TipoLabor (Pulverización, Siembra, Fertilización, Labranza, Cosecha, Curado).
  2. Inicialización y persistencia automática en base de datos.
  3. Motor de Pensamiento / Similitud Léxica-Semántica:
     - Evalúa si una nueva labor ingresada por el operario coincide con una plantilla existente.
     - Si coincide (score >= 0.72), vincula e incrementa el contador de frecuencia.
     - Si es una técnica o receta nueva (score < 0.72), la aprende y registra en el catálogo automáticamente.
"""

from datetime import datetime, timezone
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_

from app.models import PlantillaLaborCampo
from app.enums import TipoLabor

logger = logging.getLogger("labores_plantillas")

# ==============================================================================
# CATÁLOGO CANÓNICO BASE DE LA ESTANCIA (CUADERNO AGRONÓMICO HISTÓRICO Y VIGENTE)
# ==============================================================================
PLANTILLAS_CANONICAS = [
    # --------------------------------------------------------------------------
    # 1. PULVERIZACIONES / BARBECHOS Y FITOSANITARIOS
    # --------------------------------------------------------------------------
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Barbecho Largo",
        "titulo": "Barbecho Largo Invierno",
        "descripcion_receta": "LT Box 1.5kg + 2,4-D Avstok 1.0L + Picloram 0.3L + Atrazina 0.6kg + Mictec 0.07L",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
            {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
            {"nombre": "Picloram", "dosis": 0.3, "unidad": "lt/ha"},
            {"nombre": "Atrazina", "dosis": 0.6, "unidad": "kg/ha"},
            {"nombre": "Mictec", "dosis": 0.07, "unidad": "lt/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Barbecho con Dicamba",
        "titulo": "Barbecho con Dicamba",
        "descripcion_receta": "Tijereta Box 1.5kg + 2,4-D 1.0L + Dicamba 0.15L + Atrazina 0.6kg + Altiva Pro 0.05L",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "Tijereta Box", "dosis": 1.5, "unidad": "kg/ha"},
            {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
            {"nombre": "Dicamba", "dosis": 0.15, "unidad": "lt/ha"},
            {"nombre": "Atrazina", "dosis": 0.6, "unidad": "kg/ha"},
            {"nombre": "Altiva Pro", "dosis": 0.05, "unidad": "lt/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Barbecho Corto",
        "titulo": "Barbecho Corto con Ligate",
        "descripcion_receta": "LT Box 1.5kg + 2,4-D Avstok 1.0L + Ligate 0.12kg + Atrazina 0.5kg + Altiva Pro 0.08L",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
            {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
            {"nombre": "Ligate", "dosis": 0.12, "unidad": "kg/ha"},
            {"nombre": "Atrazina", "dosis": 0.5, "unidad": "kg/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Barbecho Post-Cosecha",
        "titulo": "Barbecho Post-Cosecha Otoño",
        "descripcion_receta": "LT Box 1.6kg + Atrazina Atanor 1.1kg + 2,4-D Avstok 1.0L + Picloram 0.3L + Dash 0.13L",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "LT Box", "dosis": 1.6, "unidad": "kg/ha"},
            {"nombre": "Atrazina Atanor", "dosis": 1.1, "unidad": "kg/ha"},
            {"nombre": "2,4-D Avstok", "dosis": 1.0, "unidad": "lt/ha"},
            {"nombre": "Picloram", "dosis": 0.3, "unidad": "lt/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Pre-emergente Maíz",
        "titulo": "Pre-emergente Maíz",
        "descripcion_receta": "S-metolacloro 1.1L + Atrazina Gesaprim 1.0kg + Pastilla antideriva 0.15",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "S-metolacloro", "dosis": 1.1, "unidad": "lt/ha"},
            {"nombre": "Atrazina", "dosis": 1.0, "unidad": "kg/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Pre-siembra Maíz",
        "titulo": "Pre-siembra Maíz Alta Residualidad",
        "descripcion_receta": "LT Box 1.5kg + 2,4-D 1.0L + Gemmitop 0.156L + Pyroxasulfone Zidua 0.2kg + Altiva Pro 0.08L",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "LT Box", "dosis": 1.5, "unidad": "kg/ha"},
            {"nombre": "2,4-D", "dosis": 1.0, "unidad": "lt/ha"},
            {"nombre": "Gemmitop (Flumioxazin)", "dosis": 0.156, "unidad": "lt/ha"},
            {"nombre": "Zidua (Pyroxasulfone)", "dosis": 0.2, "unidad": "kg/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Pre-siembra Soja",
        "titulo": "Pre-siembra Soja",
        "descripcion_receta": "Sulfentrazone Capaz 0.533L + Graminicida Latium 0.69L + Dash MSO 0.12L + Altiva Pro 0.08L",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "Sulfentrazone Capaz", "dosis": 0.533, "unidad": "lt/ha"},
            {"nombre": "Graminicida Latium", "dosis": 0.69, "unidad": "lt/ha"},
            {"nombre": "Dash MSO", "dosis": 0.12, "unidad": "lt/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Pre-siembra Soja",
        "titulo": "Pre-siembra Soja Doble Golpe",
        "descripcion_receta": "Capaz 0.533L + Glufosinato Liberty 2.5L + Sulfato de Amonio 0.25kg + Dash MSO 0.25L",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "Sulfentrazone Capaz", "dosis": 0.533, "unidad": "lt/ha"},
            {"nombre": "Glufosinato Liberty", "dosis": 2.5, "unidad": "lt/ha"},
            {"nombre": "Sulfato de Amonio", "dosis": 0.25, "unidad": "kg/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Fitosanitario R3",
        "titulo": "Fitosanitario Completo Soja R3",
        "descripcion_receta": "Fungicida Melyra 0.5L + Latium 0.6L + Coragen 0.03L + Talstar Xtra 0.07L + Foliar Sett Stoller 2.0L",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "Fungicida Melyra", "dosis": 0.5, "unidad": "lt/ha"},
            {"nombre": "Graminicida Latium", "dosis": 0.6, "unidad": "lt/ha"},
            {"nombre": "Coragen", "dosis": 0.03, "unidad": "lt/ha"},
            {"nombre": "Talstar Xtra", "dosis": 0.07, "unidad": "lt/ha"},
            {"nombre": "Sett Stoller", "dosis": 2.0, "unidad": "lt/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Post-emergente",
        "titulo": "Post-emergente Maíz por Escape",
        "descripcion_receta": "Glifo Top 2.5L + Coadyuvante Mictec 0.11L a 60 L/ha de agua",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "Glifo Top", "dosis": 2.5, "unidad": "lt/ha"},
            {"nombre": "Mictec", "dosis": 0.11, "unidad": "lt/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.PULVERIZACION,
        "categoria_subtipo": "Cabeceras / Orillas",
        "titulo": "Pulverización Orillas y Cabeceras",
        "descripcion_receta": "Glifo Top 3.5L/ha vuelta alrededor por nacimiento de gramíneas en alambrados",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "Glifo Top", "dosis": 3.5, "unidad": "lt/ha"},
        ],
    },

    # --------------------------------------------------------------------------
    # 2. SIEMBRAS
    # --------------------------------------------------------------------------
    {
        "tipo_labor": TipoLabor.SIEMBRA,
        "categoria_subtipo": "Maíz Temprano",
        "titulo": "Siembra Maíz Temprano (4.2 sem/m)",
        "descripcion_receta": "Semilla Maíz DK 72-10 densidad 4.2 sem/metro + Fertilizante arrancador MicroEssentials SZ 80 kg/ha",
        "dosis_unidad_default": "semillas/m",
        "insumos_default": [
            {"nombre": "Semilla Maíz DK 72-10", "dosis": 4.2, "unidad": "semillas/m"},
            {"nombre": "MicroEssentials SZ", "dosis": 80.0, "unidad": "kg/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.SIEMBRA,
        "categoria_subtipo": "Maíz Tardío",
        "titulo": "Siembra Maíz Tardío (4.0 sem/m)",
        "descripcion_receta": "Semilla Maíz DK 72-10 / P2089 a 4.0 sem/metro con arrancador en línea",
        "dosis_unidad_default": "semillas/m",
        "insumos_default": [
            {"nombre": "Semilla Maíz DK 72-10", "dosis": 4.0, "unidad": "semillas/m"},
        ],
    },
    {
        "tipo_labor": TipoLabor.SIEMBRA,
        "categoria_subtipo": "Soja Convencional",
        "titulo": "Siembra Soja Convencional (28 gr/m)",
        "descripcion_receta": "Semilla Soja DM 46i20 / NS 5030 densidad 28 granos/metro a 4 cm de profundidad",
        "dosis_unidad_default": "granos/m",
        "insumos_default": [
            {"nombre": "Semilla Soja DM 46i20", "dosis": 28.0, "unidad": "granos/m"},
        ],
    },
    {
        "tipo_labor": TipoLabor.SIEMBRA,
        "categoria_subtipo": "Soja Estrecha",
        "titulo": "Siembra Soja Estrecha 0.35m",
        "descripcion_receta": "Siembra a 0.35m con doble pasada a 11-14 granos/metro para cierre rápido de entresurco",
        "dosis_unidad_default": "granos/m",
        "insumos_default": [
            {"nombre": "Semilla Soja", "dosis": 12.0, "unidad": "granos/m"},
        ],
    },
    {
        "tipo_labor": TipoLabor.SIEMBRA,
        "categoria_subtipo": "Soja de Segunda",
        "titulo": "Siembra Soja de 2da (Post-Trigo)",
        "descripcion_receta": "Semilla Soja AW 4326 / AW 4927 directa sobre rastrojo de trigo",
        "dosis_unidad_default": "granos/m",
        "insumos_default": [
            {"nombre": "Semilla Soja AW 4326", "dosis": 30.0, "unidad": "granos/m"},
        ],
    },
    {
        "tipo_labor": TipoLabor.SIEMBRA,
        "categoria_subtipo": "Re-siembra",
        "titulo": "Re-siembra por Planchado / Lluvia",
        "descripcion_receta": "Re-siembra localizada tras planchado por lluvias intensas con rotativa previa",
        "dosis_unidad_default": "ha",
        "insumos_default": [],
    },

    # --------------------------------------------------------------------------
    # 3. FERTILIZACIONES
    # --------------------------------------------------------------------------
    {
        "tipo_labor": TipoLabor.FERTILIZACION,
        "categoria_subtipo": "Fosfatada al Voleo",
        "titulo": "Fertilización Fosfatada SPS (102 kg/ha)",
        "descripcion_receta": "Superfosfato Simple (SPS) 102 kg/ha al voleo previo a siembra",
        "dosis_unidad_default": "kg/ha",
        "insumos_default": [
            {"nombre": "Superfosfato Simple (SPS)", "dosis": 102.0, "unidad": "kg/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.FERTILIZACION,
        "categoria_subtipo": "Nitrogenada al Voleo",
        "titulo": "Fertilización Nitrogenada Urea (118 kg/ha)",
        "descripcion_receta": "Urea N-Total granulada 118 kg/ha al voleo en estado V4-V6 con suelo húmedo",
        "dosis_unidad_default": "kg/ha",
        "insumos_default": [
            {"nombre": "Urea N-Total", "dosis": 118.0, "unidad": "kg/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.FERTILIZACION,
        "categoria_subtipo": "Arrancador en Línea",
        "titulo": "Fertilización MicroEssentials SZ (80 kg/ha)",
        "descripcion_receta": "MicroEssentials SZ (N-P-S-Zn) 80 kg/ha incorporado junto a la línea de siembra",
        "dosis_unidad_default": "kg/ha",
        "insumos_default": [
            {"nombre": "MicroEssentials SZ", "dosis": 80.0, "unidad": "kg/ha"},
        ],
    },
    {
        "tipo_labor": TipoLabor.FERTILIZACION,
        "categoria_subtipo": "Nutrición Foliar",
        "titulo": "Nutrición Foliar Complementaria",
        "descripcion_receta": "Sett Stoller 2.0 L/ha + Foliar Crescere 1.0 L/ha en floración R2-R3",
        "dosis_unidad_default": "lt/ha",
        "insumos_default": [
            {"nombre": "Sett Stoller", "dosis": 2.0, "unidad": "lt/ha"},
            {"nombre": "Crescere (Innoquim)", "dosis": 1.0, "unidad": "lt/ha"},
        ],
    },

    # --------------------------------------------------------------------------
    # 4. LABRANZAS / MECANIZADO
    # --------------------------------------------------------------------------
    {
        "tipo_labor": TipoLabor.LABRANZA,
        "categoria_subtipo": "Rotativa",
        "titulo": "Pasada de Rotativa Ligera (Planchado)",
        "descripcion_receta": "Pasada de rotativa ligera para romper costra de planchado superficial post-lluvia",
        "dosis_unidad_default": "ha",
        "insumos_default": [],
    },
    {
        "tipo_labor": TipoLabor.LABRANZA,
        "categoria_subtipo": "Rastra de Discos",
        "titulo": "Rastra de Discos Niveladora",
        "descripcion_receta": "Acondicionamiento de huellas de cosecha y emparejamiento de rastrojo",
        "dosis_unidad_default": "ha",
        "insumos_default": [],
    },
    {
        "tipo_labor": TipoLabor.LABRANZA,
        "categoria_subtipo": "Desmalezado Mecánico",
        "titulo": "Desmalezado Mecánico / Bordeadora",
        "descripcion_receta": "Corte mecánico de malezas en orillas, caminos y callejones de la estancia",
        "dosis_unidad_default": "ha",
        "insumos_default": [],
    },
    {
        "tipo_labor": TipoLabor.LABRANZA,
        "categoria_subtipo": "Subsolado",
        "titulo": "Descompactación Profunda (Paratill)",
        "descripcion_receta": "Subsolador / Paratill para descompactar pie de arado y huellas de tolva",
        "dosis_unidad_default": "ha",
        "insumos_default": [],
    },

    # --------------------------------------------------------------------------
    # 5. COSECHAS
    # --------------------------------------------------------------------------
    {
        "tipo_labor": TipoLabor.COSECHA,
        "categoria_subtipo": "Soja 1ra",
        "titulo": "Cosecha Soja de Primera (DM 46i20 / NS 5030)",
        "descripcion_receta": "Trilla directa con monitoreo de pérdidas y control de humedad (< 13.5%)",
        "dosis_unidad_default": "qq/ha",
        "insumos_default": [],
    },
    {
        "tipo_labor": TipoLabor.COSECHA,
        "categoria_subtipo": "Soja 2da",
        "titulo": "Cosecha Soja de Segunda",
        "descripcion_receta": "Trilla directa sobre rastrojo de trigo y pesada en tolva",
        "dosis_unidad_default": "qq/ha",
        "insumos_default": [],
    },
    {
        "tipo_labor": TipoLabor.COSECHA,
        "categoria_subtipo": "Maíz Grano",
        "titulo": "Cosecha Maíz Grano Comercial",
        "descripcion_receta": "Trilla directa de maíz DK 72-10 con humedad comercial (14.5%) y embolsado o camión",
        "dosis_unidad_default": "qq/ha",
        "insumos_default": [],
    },
    {
        "tipo_labor": TipoLabor.COSECHA,
        "categoria_subtipo": "Silaje Forrajero",
        "titulo": "Picado de Maíz para Silaje",
        "descripcion_receta": "Corte y picado fino de planta entera para silo bolsa / puente ganadero",
        "dosis_unidad_default": "ha",
        "insumos_default": [],
    },

    # --------------------------------------------------------------------------
    # 6. TRATAMIENTO DE SEMILLA / CURADO
    # --------------------------------------------------------------------------
    {
        "tipo_labor": TipoLabor.TRATAMIENTO_SEMILLA,
        "categoria_subtipo": "Inoculación Soja",
        "titulo": "Inoculación Soja Pack Larga Duración",
        "descripcion_receta": "Inoculante Bradyrhizobium + Fungicida Curasemilla de amplio espectro",
        "dosis_unidad_default": "dosis/100kg",
        "insumos_default": [
            {"nombre": "Inoculante Bradyrhizobium", "dosis": 1.0, "unidad": "dosis/100kg"},
            {"nombre": "Fungicida Curasemilla", "dosis": 0.1, "unidad": "lt/100kg"},
        ],
    },
    {
        "tipo_labor": TipoLabor.TRATAMIENTO_SEMILLA,
        "categoria_subtipo": "Insecticida Semilla",
        "titulo": "Tratamiento Insecticida para Suelo",
        "descripcion_receta": "Tiametoxam + Metalaxil para control de gusano blanco y cortadoras",
        "dosis_unidad_default": "lt/100kg",
        "insumos_default": [
            {"nombre": "Tiametoxam + Metalaxil", "dosis": 0.25, "unidad": "lt/100kg"},
        ],
    },
    {
        "tipo_labor": TipoLabor.TRATAMIENTO_SEMILLA,
        "categoria_subtipo": "Biológico Raíz",
        "titulo": "Tratamiento Biológico y Bioestimulante",
        "descripcion_receta": "Trichoderma harzianum + Bioestimulante de emergencia radicular",
        "dosis_unidad_default": "dosis/100kg",
        "insumos_default": [
            {"nombre": "Trichoderma Harzianum", "dosis": 1.0, "unidad": "dosis/100kg"},
        ],
    },
]


# ==============================================================================
# MOTOR DE SIMILITUD Y APRENDIZAJE
# ==============================================================================

def normalizar_texto(texto: str) -> str:
    """Limpia puntuación, acentos y espacios para comparación robusta."""
    if not texto:
        return ""
    texto = texto.lower()
    # Reemplazar tildes
    reemplazos = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
    for k, v in reemplazos.items():
        texto = texto.replace(k, v)
    # Quitar caracteres especiales
    texto = re.sub(r"[^\w\s]", " ", texto)
    return " ".join(texto.split())


def calcular_similitud_tokens(texto1: str, texto2: str) -> float:
    """
    Calcula similitud combinando:
      1. Coincidencia exacta de título / frase clave.
      2. Coeficiente de solapamiento (Overlap / Simpson) para recetas que comparten activos.
      3. Coeficiente de Jaccard.
    """
    t1 = normalizar_texto(texto1)
    t2 = normalizar_texto(texto2)
    if not t1 or not t2:
        return 0.0

    if t1 == t2 or t1 in t2 or t2 in t1:
        # Alta coincidencia directa de cadenas
        if len(min(t1, t2, key=len)) > 8:
            return 0.95

    tokens1 = set(t1.split())
    tokens2 = set(t2.split())

    # Palabras vacías comunes y ruidos espaciales
    stopwords = {"de", "la", "el", "en", "con", "y", "a", "por", "para", "un", "una", "ha", "al", "del", "lote", "completo", "sector", "zona", "lado"}
    tokens1 = tokens1 - stopwords
    tokens2 = tokens2 - stopwords

    if not tokens1 or not tokens2:
        return 0.0

    interseccion = tokens1.intersection(tokens2)
    if not interseccion:
        return 0.0

    jaccard = len(interseccion) / len(tokens1.union(tokens2))
    overlap = len(interseccion) / min(len(tokens1), len(tokens2))

    # Ponderación balanceada: 60% overlap + 40% jaccard
    score = (0.6 * overlap) + (0.4 * jaccard)
    return score


async def inicializar_plantillas_base(db: AsyncSession, cliente_id: Optional[uuid.UUID] = None) -> int:
    """Verifica si existen plantillas base; si no, inserta el catálogo canónico."""
    stmt = select(PlantillaLaborCampo)
    existentes = (await db.execute(stmt)).scalars().all()
    if existentes:
        return len(existentes)

    logger.info("Inicializando catálogo canónico de plantillas de labores...")
    count = 0
    for item in PLANTILLAS_CANONICAS:
        plantilla = PlantillaLaborCampo(
            id=uuid.uuid4(),
            cliente_id=cliente_id,
            tipo_labor=item["tipo_labor"],
            titulo=item["titulo"],
            categoria_subtipo=item.get("categoria_subtipo"),
            descripcion_receta=item["descripcion_receta"],
            insumos_default=item.get("insumos_default", []),
            dosis_unidad_default=item.get("dosis_unidad_default", "lt/ha"),
            es_sistema=True,
            veces_utilizada=1,
            creado_en=datetime.now(timezone.utc),
        )
        db.add(plantilla)
        count += 1

    await db.commit()
    logger.info(f"Se crearon {count} plantillas de labores canónicas exitosamente.")
    return count


async def obtener_plantillas_agrupadas(
    db: AsyncSession, cliente_id: Optional[uuid.UUID] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retorna las plantillas disponibles agrupadas por tipo_labor (value string),
    ordenadas por veces_utilizada desc y título.
    """
    # Asegurar que existan las plantillas base
    await inicializar_plantillas_base(db, cliente_id)

    stmt = select(PlantillaLaborCampo)
    if cliente_id:
        stmt = stmt.where(or_(PlantillaLaborCampo.cliente_id == cliente_id, PlantillaLaborCampo.cliente_id.is_(None)))
    stmt = stmt.order_by(PlantillaLaborCampo.veces_utilizada.desc(), PlantillaLaborCampo.titulo.asc())

    plantillas = (await db.execute(stmt)).scalars().all()

    # Agrupar por tipo_labor
    agrupadas: Dict[str, List[Dict[str, Any]]] = {
        "pulverizacion": [],
        "siembra": [],
        "fertilizacion": [],
        "labranza": [],
        "cosecha": [],
        "tratamiento_semilla": [],
    }

    for p in plantillas:
        t_key = p.tipo_labor.value if hasattr(p.tipo_labor, "value") else str(p.tipo_labor).lower()
        if t_key not in agrupadas:
            agrupadas[t_key] = []
        agrupadas[t_key].append(
            {
                "id": str(p.id),
                "tipo_labor": t_key,
                "titulo": p.titulo,
                "categoria_subtipo": p.categoria_subtipo or "",
                "descripcion_receta": p.descripcion_receta,
                "insumos_default": p.insumos_default or [],
                "dosis_unidad_default": p.dosis_unidad_default or "lt/ha",
                "veces_utilizada": p.veces_utilizada,
                "es_sistema": p.es_sistema,
            }
        )

    return agrupadas


async def evaluar_y_aprender_nueva_labor(
    db: AsyncSession,
    tipo_labor: TipoLabor,
    titulo: str,
    descripcion_o_insumos: str,
    cliente_id: Optional[uuid.UUID] = None,
    dosis_unidad: Optional[str] = "lt/ha",
    insumos_list: Optional[list] = None,
) -> Tuple[Optional[PlantillaLaborCampo], bool]:
    """
    Motor de Aprendizaje Inteligente:
      - Compara la labor ingresada contra el catálogo existente de ese tipo_labor.
      - Si encuentra una coincidencia (similitud >= 0.72), incrementa veces_utilizada y retorna (plantilla, False).
      - Si es una labor o receta no vista (similitud < 0.72), crea una nueva PlantillaLaborCampo y retorna (nueva_plantilla, True).
    """
    texto_ingresado = f"{titulo} {descripcion_o_insumos}".strip()
    if not texto_ingresado or len(texto_ingresado) < 4:
        return None, False

    # Buscar plantillas del mismo tipo_labor
    stmt = select(PlantillaLaborCampo).where(PlantillaLaborCampo.tipo_labor == tipo_labor)
    existentes = (await db.execute(stmt)).scalars().all()

    mejor_coincidencia: Optional[PlantillaLaborCampo] = None
    mejor_score = 0.0

    for p in existentes:
        texto_plantilla = f"{p.titulo} {p.descripcion_receta}".strip()
        score = calcular_similitud_tokens(texto_ingresado, texto_plantilla)
        if score > mejor_score:
            mejor_score = score
            mejor_coincidencia = p

    UMBRAL_SIMILITUD = 0.72

    if mejor_coincidencia and mejor_score >= UMBRAL_SIMILITUD:
        # Es una labor conocida/similar: sumar uso
        mejor_coincidencia.veces_utilizada += 1
        await db.commit()
        await db.refresh(mejor_coincidencia)
        logger.info(
            f"Labor reconocida como '{mejor_coincidencia.titulo}' (score={mejor_score:.2f}). Se sumó frecuencia."
        )
        return mejor_coincidencia, False
    else:
        # Es una labor nueva: crear nueva plantilla en el catálogo
        titulo_limpio = titulo.strip() if titulo.strip() else descripcion_o_insumos.split("+")[0].strip()[:100]
        if not titulo_limpio:
            titulo_limpio = f"Labor de {tipo_labor.value.capitalize()}"

        nueva_plantilla = PlantillaLaborCampo(
            id=uuid.uuid4(),
            cliente_id=cliente_id,
            tipo_labor=tipo_labor,
            titulo=titulo_limpio[:200],
            categoria_subtipo="Personalizada",
            descripcion_receta=descripcion_o_insumos.strip(),
            insumos_default=insumos_list or [],
            dosis_unidad_default=dosis_unidad or "lt/ha",
            es_sistema=False,
            veces_utilizada=1,
            creado_en=datetime.now(timezone.utc),
        )
        db.add(nueva_plantilla)
        await db.commit()
        await db.refresh(nueva_plantilla)
        logger.info(
            f"💡 ¡Nueva labor aprendida y catalogada!: '{nueva_plantilla.titulo}' (tipo={tipo_labor.value})."
        )
        return nueva_plantilla, True
