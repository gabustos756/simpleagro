import os
from typing import AsyncGenerator
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, create_async_engine, async_sessionmaker


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
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Inicializa la estructura de tablas en la base de datos PostgreSQL."""
    import app.models  # Importa los modelos para registrarlos en Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


