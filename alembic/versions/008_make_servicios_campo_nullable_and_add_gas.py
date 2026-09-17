"""Make campo_id nullable in servicios_instalados and add GAS to tipo_servicio_enum

Revision ID: 008_servicios_campo_nullable
Revises: 007_add_plantillas_labores
Create Date: 2026-09-17 14:00:00.000000

"""
from alembic import op

revision = '008_servicios_campo_nullable'
down_revision = '007_add_plantillas_labores'
branch_labels = None
depends_on = None


def upgrade():
    # Make campo_id nullable in servicios_instalados
    op.execute("ALTER TABLE servicios_instalados ALTER COLUMN campo_id DROP NOT NULL")
    # Add GAS to tipo_servicio_enum if not exists
    op.execute("ALTER TYPE tipo_servicio_enum ADD VALUE IF NOT EXISTS 'GAS'")


def downgrade():
    op.execute("ALTER TABLE servicios_instalados ALTER COLUMN campo_id SET NOT NULL")
