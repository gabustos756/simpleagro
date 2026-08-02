import os
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    """Base declarativa para todos los modelos SQLAlchemy 2.0 del ERP Agropecuario."""
    pass
