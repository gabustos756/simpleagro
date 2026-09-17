#!/usr/bin/env bash
# ==============================================================================
# scripts/import_servicios_vps.sh
# ------------------------------------------------------------------------------
# Ejecutor para importar automáticamente en la VPS los servicios operativos
# reales de la Familia Matteuda y vincular sus comprobantes PDF.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${APP_DIR}"

echo "🌾 EduAgro - Importación de Servicios Operativos Reales"
echo "--------------------------------------------------------"

# 1. Detectar entorno virtual
if [[ -d "${APP_DIR}/venv" ]]; then
    PYTHON="${APP_DIR}/venv/bin/python"
elif [[ -d "${APP_DIR}/.venv" ]]; then
    PYTHON="${APP_DIR}/.venv/bin/python"
else
    PYTHON="python3"
fi

# 2. Ejecutar migraciones primero por si hay columnas pendientes
echo ">> Verificando migraciones de base de datos..."
if [[ -f "${APP_DIR}/venv/bin/alembic" ]]; then
    "${APP_DIR}/venv/bin/alembic" upgrade head
else
    alembic upgrade head || true
fi

# 3. Ejecutar script de importación
echo ">> Importando facturas y servicios desde docs/servicios/..."
"${PYTHON}" "${APP_DIR}/scripts/import_servicios_reales.py"

echo "--------------------------------------------------------"
echo "✅ Importación finalizada con éxito."
