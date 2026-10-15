"""Add retiros_capital_socios and update tipo_servicio_enum with TRILLA_COSECHA and GASTOS_GENERALES

Revision ID: 012_add_retiros_and_trilla
Revises: 011_update_registros_lluvia
Create Date: 2026-10-15 08:00:00.000000

"""
from alembic import op

revision = '012_add_retiros_and_trilla'
down_revision = '011_update_registros_lluvia'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Update tipo_servicio_enum
    op.execute("ALTER TYPE tipo_servicio_enum ADD VALUE IF NOT EXISTS 'TRILLA_COSECHA'")
    op.execute("ALTER TYPE tipo_servicio_enum ADD VALUE IF NOT EXISTS 'GASTOS_GENERALES'")

    # 2. Create retiros_capital_socios table
    op.execute("""
    CREATE TABLE IF NOT EXISTS retiros_capital_socios (
        id UUID PRIMARY KEY,
        cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
        socio_nombre VARCHAR(100) NOT NULL,
        campania_nombre VARCHAR(50) NOT NULL DEFAULT '2025/2026',
        cultivo VARCHAR(50) NOT NULL DEFAULT 'soja',
        tipo_movimiento VARCHAR(50) NOT NULL DEFAULT 'retiro',
        quintales NUMERIC(12, 2) NOT NULL,
        fecha DATE NOT NULL DEFAULT CURRENT_DATE,
        precio_usd_qq NUMERIC(10, 2),
        monto_total_usd NUMERIC(12, 2),
        concepto VARCHAR(200) NOT NULL,
        comprobante_o_referencia VARCHAR(150),
        observaciones TEXT,
        fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_retiros_socio_cliente_campania 
    ON retiros_capital_socios (cliente_id, campania_nombre, socio_nombre);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS retiros_capital_socios CASCADE;")
