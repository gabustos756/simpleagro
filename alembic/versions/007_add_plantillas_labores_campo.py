"""Add plantillas_labores_campo table

Revision ID: 007_add_plantillas_labores
Revises: 006_add_labores_campo_ext
Create Date: 2026-09-16 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sqla
from sqlalchemy.dialects import postgresql

revision = '007_add_plantillas_labores'
down_revision = '006_add_labores_campo_ext'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS plantillas_labores_campo (
        id UUID PRIMARY KEY,
        cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
        tipo_labor tipo_labor_enum NOT NULL,
        titulo VARCHAR(200) NOT NULL,
        categoria_subtipo VARCHAR(100),
        descripcion_receta TEXT NOT NULL,
        insumos_default JSONB NOT NULL DEFAULT '[]'::jsonb,
        dosis_unidad_default VARCHAR(50) DEFAULT 'lt/ha',
        es_sistema BOOLEAN NOT NULL DEFAULT false,
        veces_utilizada INTEGER NOT NULL DEFAULT 1,
        creado_en TIMESTAMPTZ DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_plantillas_labores_tipo ON plantillas_labores_campo(tipo_labor)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_plantillas_labores_cliente ON plantillas_labores_campo(cliente_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS plantillas_labores_campo CASCADE")
