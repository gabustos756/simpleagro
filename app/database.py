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
    """Inicializa la estructura de tablas en la base de datos PostgreSQL."""
    import app.models  # Importa los modelos para registrarlos en Base.metadata
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(text("ALTER TABLE freight_quotes ADD COLUMN IF NOT EXISTS cultivo VARCHAR(50);"))
            await conn.execute(text("ALTER TABLE freight_quotes ADD COLUMN IF NOT EXISTS condicion_precio VARCHAR(50);"))
            await conn.execute(text("ALTER TABLE freight_quotes ADD COLUMN IF NOT EXISTS distancia_estimada_km NUMERIC(8, 2);"))
            await conn.execute(text("ALTER TABLE freight_quotes ADD COLUMN IF NOT EXISTS detalle_cupo_turno VARCHAR(300);"))

            # Stock 1C Columns
            await conn.execute(text("ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS grain_delivery_id UUID REFERENCES grain_deliveries(id) ON DELETE SET NULL;"))
            await conn.execute(text("ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS grain_waybill_id UUID REFERENCES grain_waybills(id) ON DELETE SET NULL;"))
            await conn.execute(text("ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS stock_delivery_allocation_id UUID REFERENCES stock_delivery_allocations(id) ON DELETE SET NULL;"))

            await conn.execute(text("ALTER TABLE stock_delivery_allocations ADD COLUMN IF NOT EXISTS despatched_at TIMESTAMP WITH TIME ZONE;"))
            await conn.execute(text("ALTER TABLE stock_delivery_allocations ADD COLUMN IF NOT EXISTS despatched_by_user_id UUID;"))
            await conn.execute(text("ALTER TABLE stock_delivery_allocations ADD COLUMN IF NOT EXISTS stock_movement_id UUID REFERENCES stock_movements(id) ON DELETE SET NULL;"))

            await conn.execute(text("ALTER TABLE grain_waybills ADD COLUMN IF NOT EXISTS despatched_at TIMESTAMP WITH TIME ZONE;"))
            await conn.execute(text("ALTER TABLE grain_waybills ADD COLUMN IF NOT EXISTS despatched_by_user_id UUID;"))

            # Servicios V1 DDL
            await conn.execute(text("ALTER TABLE servicios_instalados ADD COLUMN IF NOT EXISTS payment_portal_url TEXT;"))
            await conn.execute(text("ALTER TABLE servicios_instalados ADD COLUMN IF NOT EXISTS payment_reference VARCHAR(200);"))

            await conn.execute(text("ALTER TABLE servicios_vencimiento ADD COLUMN IF NOT EXISTS servicio_instalado_id UUID REFERENCES servicios_instalados(id) ON DELETE CASCADE;"))
            await conn.execute(text("ALTER TABLE servicios_vencimiento ADD COLUMN IF NOT EXISTS payment_link TEXT;"))
            await conn.execute(text("ALTER TABLE servicios_vencimiento ADD COLUMN IF NOT EXISTS periodo_referencia VARCHAR(100);"))
            await conn.execute(text("ALTER TABLE servicios_vencimiento ADD COLUMN IF NOT EXISTS fecha_pago DATE;"))
        except Exception:
            pass


