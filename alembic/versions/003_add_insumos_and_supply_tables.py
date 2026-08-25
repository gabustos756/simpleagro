"""Add insumos and supply tables

Revision ID: 003_add_insumos
Revises: 002_add_servicios_prestados
Create Date: 2026-08-24 20:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_add_insumos'
down_revision: Union[str, None] = '002_add_servicios_prestados'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enums
    categoriainsumoenum = postgresql.ENUM('SEMILLA', 'COMBUSTIBLE', 'FERTILIZANTE', 'FITOSANITARIO', 'REPUESTO', 'OTRO', name='categoriainsumoenum', create_type=False)
    categoriainsumoenum.create(op.get_bind(), checkfirst=True)

    unidadmedidainsumoenum = postgresql.ENUM('LITRO', 'KG', 'BOLSA', 'DOSIS', 'UNIDAD', 'METRO', name='unidadmedidainsumoenum', create_type=False)
    unidadmedidainsumoenum.create(op.get_bind(), checkfirst=True)

    tipomovimientoinsumoenum = postgresql.ENUM('COMPRA_INGRESO', 'CONSUMO_LABOR', 'CONSUMO_SERVICIO_TERCERO', 'TRANSFERENCIA_SALIDA', 'TRANSFERENCIA_ENTRADA', 'AJUSTE_RECUENTO_POSITIVO', 'AJUSTE_RECUENTO_NEGATIVO', 'MERMA_DESPERDICIO', 'DEVOLUCION_PROVEEDOR', name='tipomovimientoinsumoenum', create_type=False)
    tipomovimientoinsumoenum.create(op.get_bind(), checkfirst=True)

    monedaenum = postgresql.ENUM('USD', 'ARS', name='monedaenum', create_type=False)
    monedaenum.create(op.get_bind(), checkfirst=True)

    # 2. insumos
    op.create_table(
        'insumos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('categoria', categoriainsumoenum, nullable=False),
        sa.Column('unidad_medida', unidadmedidainsumoenum, nullable=False),
        sa.Column('principio_activo_formula', sa.String(length=200), nullable=True),
        sa.Column('concentracion', sa.String(length=50), nullable=True),
        sa.Column('unidad_empaque', sa.String(length=100), nullable=True),
        sa.Column('punto_pedido_minimo', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('punto_pedido_minimo >= 0', name='chk_insumo_minimo_no_negativo'),
        sa.UniqueConstraint('cliente_id', 'nombre', name='uq_insumo_nombre_cliente')
    )
    op.create_index('idx_insumo_cliente_cat', 'insumos', ['cliente_id', 'categoria'])

    # 3. insumo_lotes
    op.create_table(
        'insumo_lotes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('numero_lote', sa.String(length=100), nullable=False),
        sa.Column('fecha_vencimiento', sa.Date(), nullable=True),
        sa.Column('proveedor_origen', sa.String(length=150), nullable=True),
        sa.Column('registro_senasa', sa.String(length=100), nullable=True),
        sa.Column('cultivo', sa.String(length=50), nullable=True),
        sa.Column('hibrido_variedad', sa.String(length=100), nullable=True),
        sa.Column('tratamiento_semilla', sa.String(length=150), nullable=True),
        sa.Column('poder_germinativo_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('peso_mil_granos_gr', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('fecha_registro', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('cliente_id', 'insumo_id', 'numero_lote', name='uq_insumo_lote_cliente')
    )
    op.create_index(op.f('ix_insumo_lotes_cliente_id'), 'insumo_lotes', ['cliente_id'])
    op.create_index(op.f('ix_insumo_lotes_insumo_id'), 'insumo_lotes', ['insumo_id'])
    op.create_index(op.f('ix_insumo_lotes_fecha_vencimiento'), 'insumo_lotes', ['fecha_vencimiento'])

    # 4. insumo_saldos_ubicacion
    op.create_table(
        'insumo_saldos_ubicacion',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('storage_location_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('storage_locations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('cantidad_disponible', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('costo_ppp_usd', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('costo_ppp_ars', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('ultima_actualizacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cantidad_disponible >= 0', name='chk_insumo_saldo_no_negativo'),
        sa.CheckConstraint('costo_ppp_usd >= 0 AND costo_ppp_ars >= 0', name='chk_insumo_costo_ppp_no_negativo'),
        sa.UniqueConstraint('cliente_id', 'insumo_id', 'storage_location_id', name='uq_insumo_saldo_loc')
    )

    # 5. insumo_lote_saldos_ubicacion
    op.create_table(
        'insumo_lote_saldos_ubicacion',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_lote_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumo_lotes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('storage_location_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('storage_locations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('cantidad_disponible', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('ultima_actualizacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cantidad_disponible >= 0', name='chk_insumo_lote_saldo_no_negativo'),
        sa.UniqueConstraint('cliente_id', 'insumo_id', 'insumo_lote_id', 'storage_location_id', name='uq_insumo_lote_saldo_loc')
    )

    # 6. insumo_movimientos
    op.create_table(
        'insumo_movimientos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_lote_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumo_lotes.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('tipo_movimiento', tipomovimientoinsumoenum, nullable=False),
        sa.Column('fecha_movimiento', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ubicacion_origen_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('storage_locations.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('ubicacion_destino_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('storage_locations.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('cantidad', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('moneda_origen', monedaenum, nullable=False, server_default='USD'),
        sa.Column('cotizacion_usd_ars', sa.Numeric(precision=14, scale=4), nullable=False, server_default='1.0000'),
        sa.Column('costo_unitario_usd', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('costo_total_usd', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('costo_unitario_ars', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('costo_total_ars', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('grupo_transferencia_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('transaccion_financiera_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transacciones_financieras.id', ondelete='SET NULL'), nullable=True),
        sa.Column('labor_campo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('labores_campo.id', ondelete='SET NULL'), nullable=True),
        sa.Column('servicio_prestado_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('servicios_prestados.id', ondelete='SET NULL'), nullable=True),
        sa.Column('campania_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campanias.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('lote_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('lotes.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('clave_idempotencia', sa.String(length=120), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('registrado_por_usuario_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cantidad > 0', name='chk_insumo_mov_cantidad_positiva'),
        sa.CheckConstraint('cotizacion_usd_ars > 0', name='chk_insumo_mov_cotizacion_positiva'),
        sa.CheckConstraint('costo_unitario_usd >= 0 AND costo_total_usd >= 0', name='chk_insumo_mov_costo_usd_no_negativo'),
        sa.CheckConstraint('costo_unitario_ars >= 0 AND costo_total_ars >= 0', name='chk_insumo_mov_costo_ars_no_negativo'),
        sa.UniqueConstraint('cliente_id', 'tipo_movimiento', 'clave_idempotencia', name='uq_insumo_mov_tenant_idempotencia')
    )
    op.create_index('idx_insumo_mov_tenant_fecha', 'insumo_movimientos', ['cliente_id', 'fecha_movimiento'])

    # 7. insumo_compras
    op.create_table(
        'insumo_compras',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('transaccion_financiera_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transacciones_financieras.id', ondelete='SET NULL'), nullable=True),
        sa.Column('proveedor_nombre', sa.String(length=150), nullable=False),
        sa.Column('proveedor_cuit', sa.String(length=20), nullable=True),
        sa.Column('numero_factura_remito', sa.String(length=100), nullable=True),
        sa.Column('fecha_compra', sa.Date(), nullable=False),
        sa.Column('moneda', monedaenum, nullable=False, server_default='USD'),
        sa.Column('monto_total', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('cotizacion_dolar', sa.Numeric(precision=14, scale=4), nullable=False, server_default='1.0000'),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('registrado_por_usuario_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('monto_total >= 0', name='chk_insumo_compra_monto_no_negativo'),
        sa.CheckConstraint('cotizacion_dolar > 0', name='chk_insumo_compra_cotizacion_positiva')
    )

    # 8. insumo_recuentos
    op.create_table(
        'insumo_recuentos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_lote_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumo_lotes.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('storage_location_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('storage_locations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha_recuento', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cantidad_sistema', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('cantidad_fisica', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('diferencia', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('motivo_ajuste', sa.Text(), nullable=False),
        sa.Column('usuario_contador_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        sa.Column('usuario_aprobador_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cantidad_sistema >= 0 AND cantidad_fisica >= 0', name='chk_insumo_recuento_cantidades_no_negativas')
    )

    # 9. insumo_necesidades_plan
    op.create_table(
        'insumo_necesidades_plan',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insumo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('insumos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('campania_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campanias.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('lote_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('lotes.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('superficie_ha', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('dosis_por_ha', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('cantidad_total_requerida', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('completado', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('superficie_ha > 0 AND dosis_por_ha > 0 AND cantidad_total_requerida > 0', name='chk_insumo_plan_cantidades_positivas')
    )


def downgrade() -> None:
    op.drop_table('insumo_necesidades_plan')
    op.drop_table('insumo_recuentos')
    op.drop_table('insumo_compras')
    op.drop_table('insumo_movimientos')
    op.drop_table('insumo_lote_saldos_ubicacion')
    op.drop_table('insumo_saldos_ubicacion')
    op.drop_table('insumo_lotes')
    op.drop_table('insumos')

    op.execute('DROP TYPE IF EXISTS monedaenum')
    op.execute('DROP TYPE IF EXISTS tipomovimientoinsumoenum')
    op.execute('DROP TYPE IF EXISTS unidadmedidainsumoenum')
    op.execute('DROP TYPE IF EXISTS categoriainsumoenum')
