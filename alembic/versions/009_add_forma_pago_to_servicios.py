"""Add forma_pago to servicios_instalados

Revision ID: 009_add_forma_pago
Revises: 008_servicios_campo_nullable
Create Date: 2026-09-17 14:15:00.000000

"""
from alembic import op

revision = '009_add_forma_pago'
down_revision = '008_servicios_campo_nullable'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Crear tipo ENUM si no existe
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'forma_pago_servicio_enum') THEN
                CREATE TYPE forma_pago_servicio_enum AS ENUM (
                    'DEBITO_AUTOMATICO',
                    'TRANSFERENCIA',
                    'PORTAL_WEB',
                    'EFECTIVO',
                    'CHEQUE'
                );
            END IF;
        END$$;
    """)

    # 2. Agregar columna forma_pago
    op.execute("""
        ALTER TABLE servicios_instalados 
        ADD COLUMN IF NOT EXISTS forma_pago forma_pago_servicio_enum DEFAULT 'TRANSFERENCIA';
    """)


def downgrade():
    op.execute("ALTER TABLE servicios_instalados DROP COLUMN IF EXISTS forma_pago;")
    op.execute("DROP TYPE IF EXISTS forma_pago_servicio_enum;")
