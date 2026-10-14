"""Update registros_lluvia: make lote_id nullable, add campo_id and observaciones

Revision ID: 011_update_registros_lluvia
Revises: 010_add_superadmin
Create Date: 2026-10-14 13:30:00.000000

"""
from alembic import op

revision = '011_update_registros_lluvia'
down_revision = '010_add_superadmin'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE registros_lluvia ALTER COLUMN lote_id DROP NOT NULL")
    op.execute("ALTER TABLE registros_lluvia ADD COLUMN IF NOT EXISTS campo_id UUID REFERENCES campos(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE registros_lluvia ADD COLUMN IF NOT EXISTS observaciones TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS ix_registros_lluvia_campo_fecha ON registros_lluvia (campo_id, fecha)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_registros_lluvia_campo_fecha")
    op.execute("ALTER TABLE registros_lluvia DROP COLUMN IF EXISTS observaciones")
    op.execute("ALTER TABLE registros_lluvia DROP COLUMN IF EXISTS campo_id")
