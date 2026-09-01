"""
test_labores_campo_extendidas.py
Pruebas unitarias para verificar el modelo extendido de LaborCampo, los nuevos enums de labores y el script de migración.
"""

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy.future import select

from app.enums import TipoLabor
from app.models import LaborCampo, Lote, Campania
from app.schemas import (
    LaborCampoCreate,
    ParametrosAplicacionSchema,
    DetallesSiembraSchema,
    DetallesCosechaSchema,
)
from scripts.migrar_cuaderno_productor_vps import migrar_cuaderno_vps, LOTE_DATA_MAP


def test_tipo_labor_enums_extended():
    """Verifica que los nuevos tipos de labor existan en TipoLabor."""
    assert TipoLabor.LABRANZA == "labranza"
    assert TipoLabor.TRATAMIENTO_SEMILLA == "tratamiento_semilla"
    assert TipoLabor.SIEMBRA == "siembra"
    assert TipoLabor.PULVERIZACION == "pulverizacion"


def test_labor_campo_pydantic_schema_extended():
    """Verifica la validación de esquemas Pydantic extendidos para labores."""
    lote_id = uuid.uuid4()
    campania_id = uuid.uuid4()

    labor_in = LaborCampoCreate(
        lote_id=lote_id,
        campania_id=campania_id,
        tipo_labor=TipoLabor.PULVERIZACION,
        fecha=datetime.now(timezone.utc),
        superficie_afectada_ha=37.0,
        sector_zona="Lado Sur y Vuelta",
        parametros_aplicacion=ParametrosAplicacionSchema(
            volumen_agua_lts_ha=68.0,
            presion_bar=2.5,
            velocidad_kmh=17.0,
            pastilla_boquilla="Disco (5) Núcleo (13)",
        ),
        blanco_biologico="Pastillo y Maizbón",
        evaluacion_resultado="Lote impecable",
    )

    assert labor_in.superficie_afectada_ha == 37.0
    assert labor_in.sector_zona == "Lado Sur y Vuelta"
    assert labor_in.parametros_aplicacion.volumen_agua_lts_ha == 68.0
    assert labor_in.parametros_aplicacion.presion_bar == 2.5
    assert labor_in.blanco_biologico == "Pastillo y Maizbón"


@pytest.mark.asyncio
async def test_migracion_cuaderno_dry_run():
    """Verifica que el script de migración corra en modo dry-run sobre la sesión de prueba."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await migrar_cuaderno_vps(dry_run=True, session=db)

    # Verificar que el dataset original contiene todas las claves requeridas
    assert "grasso_1" in LOTE_DATA_MAP
    assert "grasso_2_3" in LOTE_DATA_MAP
    assert len(LOTE_DATA_MAP["grasso_1"]["labores"]) == 10
    assert len(LOTE_DATA_MAP["grasso_2_3"]["labores"]) == 10

