"""Add GIS geometry columns to lotes table

Revision ID: 005_add_lotes_gis_columns
Revises: 004_add_insumo_reservas
Create Date: 2026-08-27 22:35:00.000000

"""
from alembic import op
import sqlalchemy as sqla
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005_add_lotes_gis_columns'
down_revision = '004_add_insumo_reservas'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('lotes', sqla.Column('geometria_geojson', postgresql.JSONB, nullable=True))
    op.add_column('lotes', sqla.Column('superficie_calculada_gis_ha', sqla.Float(), nullable=True))
    op.add_column('lotes', sqla.Column('perimetro_calculado_m', sqla.Float(), nullable=True))
    op.add_column('lotes', sqla.Column('centroide_lat', sqla.Float(), nullable=True))
    op.add_column('lotes', sqla.Column('centroide_lng', sqla.Float(), nullable=True))
    op.add_column('lotes', sqla.Column('fuente_geometria', sqla.String(length=50), nullable=True, server_default='DIBUJO_MANUAL'))
    op.add_column('lotes', sqla.Column('fecha_actualizacion_geometria', sqla.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('lotes', 'fecha_actualizacion_geometria')
    op.drop_column('lotes', 'fuente_geometria')
    op.drop_column('lotes', 'centroide_lng')
    op.drop_column('lotes', 'centroide_lat')
    op.drop_column('lotes', 'perimetro_calculado_m')
    op.drop_column('lotes', 'superficie_calculada_gis_ha')
    op.drop_column('lotes', 'geometria_geojson')
