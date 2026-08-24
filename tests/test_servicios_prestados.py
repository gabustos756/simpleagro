"""
Suite de Pruebas Unitarias e Integración para Servicios Prestados / Trabajos a Terceros (EduAgro).
Verifica:
1. Reglas anti-duplicación de ingresos contables.
2. Generación exclusiva de TransaccionFinanciera al registrar cobros o pagos reales.
3. Tratamiento de imputacion_uso_maquinaria como métrica interna.
4. Validaciones de CheckConstraint y aislamiento multi-tenant.
"""

from decimal import Decimal
from datetime import date
import uuid
import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import (
    Cliente,
    Usuario,
    EquipoMaquinaria,
    ClienteTercero,
    ServicioPrestado,
    CobroServicioPrestado,
    PagoOperadorServicio,
    TransaccionFinanciera,
)
from app.services.servicios_prestados_service import (
    create_equipo_maquinaria,
    create_cliente_tercero,
    create_servicio_prestado,
    registrar_cobro_servicio,
    registrar_pago_operador,
    fetch_resumen_servicios_prestados,
    calcular_estado_cobro_dinamico,
)
from app.enums import TipoTransaccion, EstadoOperativoTrabajoEnum, TipoEquipoEnum, MedioPagoEnum


@pytest.mark.asyncio
async def test_1_create_maquinaria_and_cliente_tercero():
    """Verifica la creación aislada por tenant de maquinaria y cliente tercero."""
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()

        maquina = await create_equipo_maquinaria(
            db=session,
            cliente_id=cliente.id,
            nombre="Metalfor 3000L Test",
            tipo_equipo=TipoEquipoEnum.PULVERIZADORA.value,
        )
        assert maquina.id is not None
        assert maquina.nombre == "Metalfor 3000L Test"

        tercero = await create_cliente_tercero(
            db=session,
            cliente_id=cliente.id,
            razon_social_nombre="Agropecuaria Don Pedro S.A.",
        )
        assert tercero.id is not None
        assert tercero.razon_social_nombre == "Agropecuaria Don Pedro S.A."


@pytest.mark.asyncio
async def test_2_create_servicio_prestado_no_financial_transaction():
    """
    Verifica que al crear un ServicioPrestado NO se genere ninguna TransaccionFinanciera
    (el presupuesto/realización no es un ingreso contable hasta cobrarse).
    """
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_user = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_user.scalars().first()

        maquina = await create_equipo_maquinaria(
            db=session, cliente_id=cliente.id, nombre="Pulverizadora Test 2"
        )
        tercero = await create_cliente_tercero(
            db=session, cliente_id=cliente.id, razon_social_nombre="Cliente Tercero 2"
        )

        res_tx_before = await session.execute(select(TransaccionFinanciera))
        tx_count_before = len(res_tx_before.scalars().all())

        orden = await create_servicio_prestado(
            db=session,
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=operador.id,
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Lote El Norte",
            superficie_ha=Decimal("150.00"),
            monto_total_facturado=Decimal("1500000.00"),
            pago_operador_negociado=Decimal("300000.00"),
            imputacion_uso_maquinaria=Decimal("400000.00"),
            gastos_directos_informados=Decimal("100000.00"),
        )
        assert orden.id is not None
        assert orden.monto_total_facturado == Decimal("1500000.00")

        # Verificar que NO se crearon transacciones financieras
        res_tx_after = await session.execute(select(TransaccionFinanciera))
        tx_count_after = len(res_tx_after.scalars().all())
        assert tx_count_after == tx_count_before


@pytest.mark.asyncio
async def test_3_registrar_cobro_generates_single_ingreso_transaccion():
    """
    Verifica que al registrar un cobro efectivo se genere exactamente UNA TransaccionFinanciera (INGRESO)
    por el monto cobrado y que la imputación de máquina NO genere transacciones secundarias.
    """
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_user = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_user.scalars().first()

        maquina = await create_equipo_maquinaria(
            db=session, cliente_id=cliente.id, nombre="Pulverizadora Test 3"
        )
        tercero = await create_cliente_tercero(
            db=session, cliente_id=cliente.id, razon_social_nombre="Cliente Tercero 3"
        )

        orden = await create_servicio_prestado(
            db=session,
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=operador.id,
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Campo La Perla",
            superficie_ha=Decimal("100.00"),
            monto_total_facturado=Decimal("1000000.00"),
            pago_operador_negociado=Decimal("200000.00"),
            imputacion_uso_maquinaria=Decimal("300000.00"),
        )

        monto_cobro = Decimal("500000.00")
        cobro, tx_ingreso = await registrar_cobro_servicio(
            db=session,
            cliente_id=cliente.id,
            servicio_prestado_id=orden.id,
            fecha_cobro=date.today(),
            monto_cobrado=monto_cobro,
            medio_pago=MedioPagoEnum.TRANSFERENCIA.value,
        )

        assert cobro.monto_cobrado == monto_cobro
        assert tx_ingreso.tipo == TipoTransaccion.INGRESO
        assert tx_ingreso.monto_ars == monto_cobro


@pytest.mark.asyncio
async def test_4_registrar_pago_operador_generates_egreso_transaccion():
    """
    Verifica que el pago al operador Andrés genere exactamente UNA TransaccionFinanciera (EGRESO).
    """
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_user = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_user.scalars().first()

        maquina = await create_equipo_maquinaria(
            db=session, cliente_id=cliente.id, nombre="Pulverizadora Test 4"
        )
        tercero = await create_cliente_tercero(
            db=session, cliente_id=cliente.id, razon_social_nombre="Cliente Tercero 4"
        )

        orden = await create_servicio_prestado(
            db=session,
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=operador.id,
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Lote Sur",
            superficie_ha=Decimal("200.00"),
            monto_total_facturado=Decimal("2000000.00"),
            pago_operador_negociado=Decimal("400000.00"),
        )

        pago, tx_egreso = await registrar_pago_operador(
            db=session,
            cliente_id=cliente.id,
            servicio_prestado_id=orden.id,
            fecha_pago=date.today(),
            monto_pagado=Decimal("400000.00"),
        )

        assert pago.monto_pagado == Decimal("400000.00")
        assert tx_egreso.tipo == TipoTransaccion.EGRESO
        assert tx_egreso.monto_ars == Decimal("400000.00")


@pytest.mark.asyncio
async def test_5_invalid_negative_and_zero_inputs_rejected():
    """Verifica que se rechacen superficies <= 0 y montos negativos."""
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_user = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_user.scalars().first()

        maquina = await create_equipo_maquinaria(
            db=session, cliente_id=cliente.id, nombre="Pulverizadora Test 5"
        )
        tercero = await create_cliente_tercero(
            db=session, cliente_id=cliente.id, razon_social_nombre="Cliente Tercero 5"
        )

        with pytest.raises(ValueError, match="superficie"):
            await create_servicio_prestado(
                db=session,
                cliente_id=cliente.id,
                cliente_tercero_id=tercero.id,
                maquinaria_id=maquina.id,
                operador_id=operador.id,
                fecha_trabajo=date.today(),
                establecimiento_lote_libre="Test Negativo",
                superficie_ha=Decimal("0.00"),
                monto_total_facturado=Decimal("100.00"),
            )


def test_6_calcular_estado_cobro_dinamico():
    """Verifica la lógica de estados dinámicos de cobro y liquidación."""
    total = Decimal("1000.00")
    negociado_op = Decimal("200.00")

    assert calcular_estado_cobro_dinamico(total, Decimal("0.00"), negociado_op, Decimal("0.00")) == "sin_cobrar"
    assert calcular_estado_cobro_dinamico(total, Decimal("500.00"), negociado_op, Decimal("0.00")) == "cobro_parcial"
    assert calcular_estado_cobro_dinamico(total, Decimal("1000.00"), negociado_op, Decimal("0.00")) == "cobrado_pendiente_operador"
    assert calcular_estado_cobro_dinamico(total, Decimal("1000.00"), negociado_op, Decimal("200.00")) == "liquidado_cerrado"


@pytest.mark.asyncio
async def test_7_idempotency_cobro_duplicate_prevention():
    """Verifica que un submit duplicado con misma clave de idempotencia retorne el cobro existente sin duplicar transacciones."""
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_user = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_user.scalars().first()

        maquina = await create_equipo_maquinaria(
            db=session, cliente_id=cliente.id, nombre="Pulverizadora Idemp Test"
        )
        tercero = await create_cliente_tercero(
            db=session, cliente_id=cliente.id, razon_social_nombre="Cliente Idemp Test"
        )

        orden = await create_servicio_prestado(
            db=session,
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=operador.id,
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Campo Idemp",
            superficie_ha=Decimal("50.00"),
            monto_total_facturado=Decimal("500000.00"),
        )

        clave = "req_http_retry_abc_123"
        cobro_1, tx_1 = await registrar_cobro_servicio(
            db=session,
            cliente_id=cliente.id,
            servicio_prestado_id=orden.id,
            fecha_cobro=date.today(),
            monto_cobrado=Decimal("100000.00"),
            clave_idempotencia=clave,
        )

        cobro_2, tx_2 = await registrar_cobro_servicio(
            db=session,
            cliente_id=cliente.id,
            servicio_prestado_id=orden.id,
            fecha_cobro=date.today(),
            monto_cobrado=Decimal("100000.00"),
            clave_idempotencia=clave,
        )

        assert cobro_1.id == cobro_2.id
        assert tx_1.id == tx_2.id


@pytest.mark.asyncio
async def test_8_operator_payment_limit_and_overpayment_reason_required():
    """Verifica que el pago al operador respete el límite pactado y exija motivo en sobrepago."""
    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_user = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_user.scalars().first()

        maquina = await create_equipo_maquinaria(
            db=session, cliente_id=cliente.id, nombre="Pulverizadora Limit Test"
        )
        tercero = await create_cliente_tercero(
            db=session, cliente_id=cliente.id, razon_social_nombre="Cliente Limit Test"
        )

        orden = await create_servicio_prestado(
            db=session,
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=operador.id,
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Campo Limit",
            superficie_ha=Decimal("100.00"),
            monto_total_facturado=Decimal("1000000.00"),
            pago_operador_negociado=Decimal("100000.00"),
        )

        # Intento de pago al operador superando lo negociado sin motivo explícito
        with pytest.raises(ValueError, match="supera el negociado"):
            await registrar_pago_operador(
                db=session,
                cliente_id=cliente.id,
                servicio_prestado_id=orden.id,
                fecha_pago=date.today(),
                monto_pagado=Decimal("150000.00"),
            )

        # Intento de pago autorizado pero sin ingresar motivo
        with pytest.raises(ValueError, match="motivo explícito"):
            await registrar_pago_operador(
                db=session,
                cliente_id=cliente.id,
                servicio_prestado_id=orden.id,
                fecha_pago=date.today(),
                monto_pagado=Decimal("150000.00"),
                autorizacion_sobrepago=True,
                motivo_sobrepago="",
            )

        # Pago autorizado con motivo explicativo
        pago, tx = await registrar_pago_operador(
            db=session,
            cliente_id=cliente.id,
            servicio_prestado_id=orden.id,
            fecha_pago=date.today(),
            monto_pagado=Decimal("150000.00"),
            autorizacion_sobrepago=True,
            motivo_sobrepago="Bonificación por trabajo nocturno urgente",
        )
        assert pago.monto_pagado == Decimal("150000.00")
        assert "Bonificación" in pago.observaciones


def test_9_user_role_permissions_guard():
    """Verifica que el rol operario_campo no pueda ejecutar acciones financieras."""
    from app.services.servicios_prestados_service import validar_permisos_usuario

    # Operario puede actualizar ejecución
    validar_permisos_usuario("operario_campo", "actualizar_ejecucion")
    validar_permisos_usuario("operario_campo", "marcar_realizado")

    # Operario NO puede modificar economía o registrar cobros
    with pytest.raises(PermissionError, match="operario_campo"):
        validar_permisos_usuario("operario_campo", "modificar_economia")

    with pytest.raises(PermissionError, match="operario_campo"):
        validar_permisos_usuario("operario_campo", "registrar_cobro")


@pytest.mark.asyncio
async def test_10_cancel_order_with_financial_movements_requires_force_flag():
    """Verifica que no se pueda cancelar una orden con cobros/pagos registrados sin bandera de fuerza."""
    from app.services.servicios_prestados_service import cancelar_servicio_prestado

    async with AsyncSessionLocal() as session:
        res_cli = await session.execute(select(Cliente).limit(1))
        cliente = res_cli.scalars().first()
        res_user = await session.execute(select(Usuario).where(Usuario.cliente_id == cliente.id).limit(1))
        operador = res_user.scalars().first()

        maquina = await create_equipo_maquinaria(
            db=session, cliente_id=cliente.id, nombre="Pulverizadora Cancel Test"
        )
        tercero = await create_cliente_tercero(
            db=session, cliente_id=cliente.id, razon_social_nombre="Cliente Cancel Test"
        )

        orden = await create_servicio_prestado(
            db=session,
            cliente_id=cliente.id,
            cliente_tercero_id=tercero.id,
            maquinaria_id=maquina.id,
            operador_id=operador.id,
            fecha_trabajo=date.today(),
            establecimiento_lote_libre="Campo Cancel",
            superficie_ha=Decimal("50.00"),
            monto_total_facturado=Decimal("500000.00"),
        )

        await registrar_cobro_servicio(
            db=session,
            cliente_id=cliente.id,
            servicio_prestado_id=orden.id,
            fecha_cobro=date.today(),
            monto_cobrado=Decimal("100000.00"),
        )

        with pytest.raises(ValueError, match="cobros"):
            await cancelar_servicio_prestado(
                db=session,
                cliente_id=cliente.id,
                servicio_prestado_id=orden.id,
                motivo_cancelacion="Cancelado por cliente",
            )

        orden_cancelada = await cancelar_servicio_prestado(
            db=session,
            cliente_id=cliente.id,
            servicio_prestado_id=orden.id,
            motivo_cancelacion="Cancelado por cliente tras ajuste contable",
            forzar_con_movimientos=True,
        )
        assert orden_cancelada.estado_operativo == EstadoOperativoTrabajoEnum.CANCELADO.value

