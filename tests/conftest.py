"""
Configuración Global de Pytest para EduAgro.
Redirige todas las pruebas hacia la base de datos dedicada de pruebas (eduagro_test).
Configura NullPool en app.database para aislar conexiones entre tests asíncronos HTTP.
Protege la base de datos de desarrollo/producción (eduagro) de cualquier mutación o inserción de datos.
"""

import os
import sys

# Forzar la variable de entorno DATABASE_URL hacia eduagro_test antes de importar app.database
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fgabrielbustos@localhost:5432/eduagro_test"
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["ENVIRONMENT"] = "testing"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
import app.database

# Sobrescribir motor y sessionmaker de app.database con NullPool para aislamiento en tests
test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
app.database.DATABASE_URL = TEST_DB_URL
app.database.engine = test_engine
app.database.AsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
