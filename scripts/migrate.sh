#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE MIGRACIÓN PRE-DEPLOYMENT - EDUAGRO
# ==============================================================================
# Este script se ejecuta en el VPS durante el paso 4 del despliegue ANTES de
# reiniciar el servicio de Uvicorn (systemctl restart eduagro).
# Si cualquier comando falla, el script aborta inmediatamente (exit status != 0)
# impidiendo la reinicialización de la aplicación.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=============================================================================="
echo "🚀 [MIGRACIÓN EDUAGRO] Iniciando verificación y ejecución de migraciones..."
echo "=============================================================================="

# 1. Cargar variables de entorno desde .env si existe
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "📄 [MIGRACIÓN] Cargando variables de entorno desde .env..."
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# 2. Verificar que DATABASE_URL esté definida
DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://fgabrielbustos@localhost:5432/eduagro}"
export DATABASE_URL

# 3. Activar entorno virtual si existe
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    echo "🐍 [MIGRACIÓN] Activando entorno virtual Python..."
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# 4. Registrar estado actual de Alembic ANTES de aplicar cambios
echo "🔍 [MIGRACIÓN] Estado actual de versión de Alembic (BEFORE):"
alembic current || true

# 5. Ejecutar Alembic Upgrade Head
echo "⚡ [MIGRACIÓN] Ejecutando 'alembic upgrade head'..."
alembic upgrade head

# 6. Registrar estado de Alembic DESPUÉS de aplicar cambios
echo "✅ [MIGRACIÓN] Estado final de versión de Alembic (AFTER):"
alembic current

echo "=============================================================================="
echo "🎉 [MIGRACIÓN EDUAGRO] Migraciones aplicadas exitosamente. La DB está al día."
echo "=============================================================================="
exit 0
