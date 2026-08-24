"""Submódulo Servicios Prestados / Trabajos a Terceros - EduAgro V2

Revision ID: 002_add_servicios_prestados
Revises: 001_initial_full_schema
Create Date: 2026-08-24 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_add_servicios_prestados"
down_revision: Union[str, None] = "001_initial_full_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tabla equipos_maquinaria
    op.create_table(
        "equipos_maquinaria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cliente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("tipo_equipo", sa.String(length=50), server_default="pulverizadora", nullable=False),
        sa.Column("marca_modelo", sa.String(length=150), nullable=True),
        sa.Column("patente_serie", sa.String(length=100), nullable=True),
        sa.Column("propiedad_empresa", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("activo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_equipos_maquinaria_cliente", "equipos_maquinaria", ["cliente_id"])
    op.create_index("ix_equipos_maquinaria_tipo", "equipos_maquinaria", ["tipo_equipo"])

    # 2. Tabla clientes_terceros
    op.create_table(
        "clientes_terceros",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cliente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("razon_social_nombre", sa.String(length=200), nullable=False),
        sa.Column("cuit_dni", sa.String(length=30), nullable=True),
        sa.Column("telefono", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("localidad_direccion", sa.String(length=255), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_clientes_terceros_cliente", "clientes_terceros", ["cliente_id"])
    op.create_index("ix_clientes_terceros_nombre", "clientes_terceros", ["razon_social_nombre"])

    # 3. Tabla servicios_prestados
    op.create_table(
        "servicios_prestados",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cliente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cliente_tercero_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clientes_terceros.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("maquinaria_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("equipos_maquinaria.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operador_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tipo_servicio", sa.String(length=50), server_default="pulverizacion", nullable=False),
        sa.Column("fecha_trabajo", sa.Date(), nullable=False),
        sa.Column("establecimiento_lote_libre", sa.String(length=255), nullable=False),
        sa.Column("superficie_ha", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("precio_unitario_ha", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("monto_total_facturado", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("pago_operador_negociado", sa.Numeric(precision=14, scale=2), server_default="0.00", nullable=False),
        sa.Column("imputacion_uso_maquinaria", sa.Numeric(precision=14, scale=2), server_default="0.00", nullable=False),
        sa.Column("gastos_directos_informados", sa.Numeric(precision=14, scale=2), server_default="0.00", nullable=False),
        sa.Column("estado_operativo", sa.String(length=50), server_default="presupuesto", nullable=False),
        sa.Column("tipo_aplicacion", sa.String(length=100), nullable=True),
        sa.Column("volumen_caldo_lha", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("insumos_aportados_por", sa.String(length=50), server_default="cliente", nullable=True),
        sa.Column("datos_adicionales_json", postgresql.JSONB(), nullable=True),
        sa.Column("creado_por_usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actualizado_por_usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("superficie_ha > 0", name="chk_superficie_positiva"),
        sa.CheckConstraint("monto_total_facturado >= 0", name="chk_monto_facturado_nn"),
        sa.CheckConstraint("pago_operador_negociado >= 0", name="chk_pago_operador_nn"),
        sa.CheckConstraint("imputacion_uso_maquinaria >= 0", name="chk_imputacion_maquina_nn"),
        sa.CheckConstraint("gastos_directos_informados >= 0", name="chk_gastos_informados_nn"),
    )
    op.create_index("ix_servicios_prestados_cliente", "servicios_prestados", ["cliente_id"])
    op.create_index("ix_servicios_prestados_tercero", "servicios_prestados", ["cliente_tercero_id"])
    op.create_index("ix_servicios_prestados_maquina", "servicios_prestados", ["maquinaria_id"])
    op.create_index("ix_servicios_prestados_operador", "servicios_prestados", ["operador_id"])
    op.create_index("ix_servicios_prestados_estado", "servicios_prestados", ["estado_operativo"])

    # 4. Tabla cobros_servicios_prestados
    op.create_table(
        "cobros_servicios_prestados",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cliente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("servicio_prestado_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("servicios_prestados.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaccion_financiera_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transacciones_financieras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fecha_cobro", sa.Date(), nullable=False),
        sa.Column("monto_cobrado", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("medio_pago", sa.String(length=50), server_default="transferencia", nullable=False),
        sa.Column("numero_comprobante", sa.String(length=100), nullable=True),
        sa.Column("clave_idempotencia", sa.String(length=100), nullable=True),
        sa.Column("registrado_por_usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("monto_cobrado > 0", name="chk_monto_cobrado_positivo"),
    )
    op.create_index("ix_cobros_servicios_cliente", "cobros_servicios_prestados", ["cliente_id"])
    op.create_index("ix_cobros_servicios_servicio", "cobros_servicios_prestados", ["servicio_prestado_id"])
    op.create_index("ix_cobros_servicios_idempotencia", "cobros_servicios_prestados", ["clave_idempotencia"])

    # 5. Tabla pagos_operadores_servicios
    op.create_table(
        "pagos_operadores_servicios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cliente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("servicio_prestado_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("servicios_prestados.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaccion_financiera_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transacciones_financieras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fecha_pago", sa.Date(), nullable=False),
        sa.Column("monto_pagado", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("medio_pago", sa.String(length=50), server_default="transferencia", nullable=False),
        sa.Column("clave_idempotencia", sa.String(length=100), nullable=True),
        sa.Column("registrado_por_usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("monto_pagado > 0", name="chk_monto_pagado_positivo"),
    )
    op.create_index("ix_pagos_operadores_cliente", "pagos_operadores_servicios", ["cliente_id"])
    op.create_index("ix_pagos_operadores_servicio", "pagos_operadores_servicios", ["servicio_prestado_id"])
    op.create_index("ix_pagos_operadores_idempotencia", "pagos_operadores_servicios", ["clave_idempotencia"])


def downgrade() -> None:
    op.drop_table("pagos_operadores_servicios")
    op.drop_table("cobros_servicios_prestados")
    op.drop_table("servicios_prestados")
    op.drop_table("clientes_terceros")
    op.drop_table("equipos_maquinaria")
