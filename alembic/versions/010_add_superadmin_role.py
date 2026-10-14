"""Add superadmin to rol_usuario_enum

Revision ID: 010_add_superadmin
Revises: 009_add_forma_pago
Create Date: 2026-09-23 16:45:00.000000

"""
from alembic import op

revision = '010_add_superadmin'
down_revision = '009_add_forma_pago'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rol_usuario_enum') THEN
                ALTER TYPE rol_usuario_enum ADD VALUE IF NOT EXISTS 'superadmin';
                ALTER TYPE rol_usuario_enum ADD VALUE IF NOT EXISTS 'SUPERADMIN';
            END IF;
        END$$;
    """)


def downgrade():
    pass
