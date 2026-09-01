"""Add technical and agronomic extended fields to labores_campo table

Revision ID: 006_add_labores_campo_ext
Revises: 005_add_lotes_gis_columns
Create Date: 2026-09-01 02:35:00.000000

"""
from alembic import op
import sqlalchemy as sqla
from sqlalchemy.dialects import postgresql

revision = '006_add_labores_campo_ext'
down_revision = '005_add_lotes_gis_columns'
branch_labels = None
depends_on = None


def upgrade():
    # Update enum values if using native enum in PostgreSQL
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'siembra'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'cosecha'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'fertilizacion'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'pulverizacion'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'labranza'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'tratamiento_semilla'")

    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'SIEMBRA'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'COSECHA'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'FERTILIZACION'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'PULVERIZACION'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'LABRANZA'")
    op.execute("ALTER TYPE tipo_labor_enum ADD VALUE IF NOT EXISTS 'TRATAMIENTO_SEMILLA'")



    op.add_column('labores_campo', sqla.Column('superficie_afectada_ha', sqla.Float(), nullable=True))
    op.add_column('labores_campo', sqla.Column('sector_zona', sqla.String(length=150), nullable=True))
    op.add_column('labores_campo', sqla.Column('parametros_aplicacion', postgresql.JSONB, nullable=True))
    op.add_column('labores_campo', sqla.Column('detalles_siembra', postgresql.JSONB, nullable=True))
    op.add_column('labores_campo', sqla.Column('detalles_cosecha', postgresql.JSONB, nullable=True))
    op.add_column('labores_campo', sqla.Column('blanco_biologico', sqla.String(length=200), nullable=True))
    op.add_column('labores_campo', sqla.Column('evaluacion_resultado', sqla.Text(), nullable=True))


def downgrade():
    op.drop_column('labores_campo', 'evaluacion_resultado')
    op.drop_column('labores_campo', 'blanco_biologico')
    op.drop_column('labores_campo', 'detalles_cosecha')
    op.drop_column('labores_campo', 'detalles_siembra')
    op.drop_column('labores_campo', 'parametros_aplicacion')
    op.drop_column('labores_campo', 'sector_zona')
    op.drop_column('labores_campo', 'superficie_afectada_ha')
