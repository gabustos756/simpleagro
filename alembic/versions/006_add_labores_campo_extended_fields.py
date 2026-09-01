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
    op.execute("ALTER TABLE labores_campo ADD COLUMN IF NOT EXISTS superficie_afectada_ha FLOAT;")
    op.execute("ALTER TABLE labores_campo ADD COLUMN IF NOT EXISTS sector_zona VARCHAR(150);")
    op.execute("ALTER TABLE labores_campo ADD COLUMN IF NOT EXISTS parametros_aplicacion JSONB;")
    op.execute("ALTER TABLE labores_campo ADD COLUMN IF NOT EXISTS detalles_siembra JSONB;")
    op.execute("ALTER TABLE labores_campo ADD COLUMN IF NOT EXISTS detalles_cosecha JSONB;")
    op.execute("ALTER TABLE labores_campo ADD COLUMN IF NOT EXISTS blanco_biologico VARCHAR(200);")
    op.execute("ALTER TABLE labores_campo ADD COLUMN IF NOT EXISTS evaluacion_resultado TEXT;")









def downgrade():
    op.drop_column('labores_campo', 'evaluacion_resultado')
    op.drop_column('labores_campo', 'blanco_biologico')
    op.drop_column('labores_campo', 'detalles_cosecha')
    op.drop_column('labores_campo', 'detalles_siembra')
    op.drop_column('labores_campo', 'parametros_aplicacion')
    op.drop_column('labores_campo', 'sector_zona')
    op.drop_column('labores_campo', 'superficie_afectada_ha')
