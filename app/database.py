import os
from typing import AsyncGenerator
from dotenv import load_dotenv
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, create_async_engine, async_sessionmaker

# Cargar variables de entorno desde archivo .env si existe
load_dotenv()


class Base(AsyncAttrs, DeclarativeBase):
    """Base declarativa para todos los modelos SQLAlchemy 2.0 del ERP Agropecuario."""
    pass


# Obtener y formatear DATABASE_URL para el driver asyncpg
raw_db_url = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://fgabrielbustos@localhost:5432/eduagro"
)

if raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif raw_db_url.startswith("postgresql://") and not raw_db_url.startswith("postgresql+asyncpg://"):
    DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = raw_db_url

# Crear el motor asíncrono de SQLAlchemy 2.0
engine = create_async_engine(DATABASE_URL, echo=False)

# Creador de sesiones asíncronas
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Generador de dependencias para inyectar la sesión asíncrona de BD en FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """
    Verifica la conectividad a la base de datos PostgreSQL en startup.
    NO ejecuta mutaciones DDL (ALTER TABLE / CREATE TABLE) en producción.
    Las migraciones de esquema son gestionadas exclusivamente mediante Alembic (./scripts/migrate.sh).
    """
    import app.models  # Registra los modelos en Base.metadata
    from sqlalchemy import text

    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        _ = result.scalar()


