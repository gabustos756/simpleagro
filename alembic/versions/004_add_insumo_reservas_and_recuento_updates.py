"""Add insumo_reservas table and update insumo_recuentos

Revision ID: 004_add_insumo_reservas
Revises: 003_add_insumos
Create Date: 2026-08-24 17:48:00.000000

"""
from alembic import op
import sqlalchemy as sqla
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_insumo_reservas'
down_revision = '003_add_insumos'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Nuevas columnas en insumo_recuentos
    op.add_column('insumo_recuentos', sqla.Column('estado_recuento', sqla.String(length=30), nullable=False, server_default='aprobado'))
    op.add_column('insumo_recuentos', sqla.Column('movimiento_ajuste_id', postgresql.UUID(as_uuid=True), sqla.ForeignKey('insumo_movimientos.id', ondelete='SET NULL'), nullable=True))

    # 2. Nueva tabla insumo_reservas
    op.create_table(
        'insumo_reservas',
        sqla.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sqla.Column('cliente_id', postgresql.UUID(as_uuid=True), sqla.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False),
        sqla.Column('insumo_id', postgresql.UUID(as_uuid=True), sqla.ForeignKey('insumos.id', ondelete='RESTRICT'), nullable=False),
        sqla.Column('storage_location_id', postgresql.UUID(as_uuid=True), sqla.ForeignKey('storage_locations.id', ondelete='RESTRICT'), nullable=True),
        sqla.Column('insumo_lote_id', postgresql.UUID(as_uuid=True), sqla.ForeignKey('insumo_lotes.id', ondelete='RESTRICT'), nullable=True),
        sqla.Column('labor_campo_id', postgresql.UUID(as_uuid=True), sqla.ForeignKey('labores_campo.id', ondelete='SET NULL'), nullable=True),
        sqla.Column('servicio_prestado_id', postgresql.UUID(as_uuid=True), sqla.ForeignKey('servicios_prestados.id', ondelete='SET NULL'), nullable=True),
        sqla.Column('cantidad_reservada', sqla.Numeric(14, 4), nullable=False),
        sqla.Column('estado_reserva', sqla.String(30), nullable=False, server_default='activa'),
        sqla.Column('fecha_reserva', sqla.DateTime(timezone=True), nullable=False),
        sqla.Column('fecha_expiracion', sqla.Date(), nullable=True),
        sqla.Column('observaciones', sqla.Text(), nullable=True),
        sqla.Column('registrado_por_usuario_id', postgresql.UUID(as_uuid=True), sqla.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        sqla.Column('fecha_creacion', sqla.DateTime(timezone=True), server_default=sqla.func.now(), nullable=False),
        sqla.CheckConstraint('cantidad_reservada > 0', name='chk_insumo_reserva_cantidad_positiva'),
    )
    op.create_index('ix_insumo_reservas_cliente_id', 'insumo_reservas', ['cliente_id'])
    op.create_index('ix_insumo_reservas_insumo_id', 'insumo_reservas', ['insumo_id'])
    op.create_index('ix_insumo_reservas_storage_location_id', 'insumo_reservas', ['storage_location_id'])
    op.create_index('idx_insumo_reserva_tenant_insumo', 'insumo_reservas', ['cliente_id', 'insumo_id', 'estado_reserva'])


def downgrade():
    op.drop_index('idx_insumo_reserva_tenant_insumo', table_name='insumo_reservas')
    op.drop_index('ix_insumo_reservas_storage_location_id', table_name='insumo_reservas')
    op.drop_index('ix_insumo_reservas_insumo_id', table_name='insumo_reservas')
    op.drop_index('ix_insumo_reservas_cliente_id', table_name='insumo_reservas')
    op.drop_table('insumo_reservas')

    op.drop_column('insumo_recuentos', 'movimiento_ajuste_id')
    op.drop_column('insumo_recuentos', 'estado_recuento')
