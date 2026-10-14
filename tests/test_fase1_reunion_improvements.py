import pytest
from httpx import AsyncClient, ASGITransport
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from app.main import app
from app.database import AsyncSessionLocal
from app.models import (
    Usuario, Cliente, Campo, Lote,
    ServicioInstalado, ServicioVencimiento, RegistroLluvia,
    TipoServicioEnum, FrecuenciaPagoEnum, EstadoServicioInstaladoEnum, EstadoServicio
)


@pytest.mark.asyncio
async def test_eliminar_servicio_vencimiento_and_servicio_instalado():
    transport = ASGITransport(app=app)
    async with AsyncSessionLocal() as session:
        res_u = await session.execute(select(Usuario).limit(1))
        user = res_u.scalars().first()
        assert user is not None

        # Crear un servicio temporal
        serv_id = uuid.uuid4()
        nuevo_serv = ServicioInstalado(
            id=serv_id,
            cliente_id=user.cliente_id,
            tipo_servicio=TipoServicioEnum.LUZ_RURAL,
            concepto="Servicio Test Eliminación",
            proveedor="Proveedor Test",
            frecuencia_pago=FrecuenciaPagoEnum.MENSUAL,
            monto_estimado_ars=Decimal("15000.00"),
            monto_real_ars=Decimal("15000.00"),
            monto_usd=Decimal("12.00"),
            fecha_vencimiento=date(2026, 10, 20),
            estado=EstadoServicioInstaladoEnum.PENDIENTE,
        )
        session.add(nuevo_serv)

        # Crear un vencimiento temporal para ese servicio
        venc_id = uuid.uuid4()
        nuevo_venc = ServicioVencimiento(
            id=venc_id,
            cliente_id=user.cliente_id,
            servicio_instalado_id=serv_id,
            concepto="Factura Período Test",
            monto_ars=Decimal("15000.00"),
            monto_usd=Decimal("12.00"),
            fecha_vencimiento=date(2026, 10, 20),
            estado=EstadoServicio.PENDIENTE,
            periodo_referencia="Octubre 2026",
        )
        session.add(nuevo_venc)
        await session.commit()

    # Probar eliminar vencimiento vía endpoint autenticado con session cookie
    cookies = {"session_user_id": str(user.id)}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Eliminar el vencimiento
        del_venc_res = await ac.post(f"/servicios/vencimientos/{venc_id}/eliminar", cookies=cookies, follow_redirects=False)
        assert del_venc_res.status_code == 303

        async with AsyncSessionLocal() as session:
            v_check = await session.get(ServicioVencimiento, venc_id)
            assert v_check is None, "El vencimiento debería haber sido eliminado de la BD"

        # 2. Eliminar el servicio completo
        del_serv_res = await ac.post(f"/servicios/{serv_id}/eliminar", cookies=cookies, follow_redirects=False)
        assert del_serv_res.status_code == 303

        async with AsyncSessionLocal() as session:
            s_check = await session.get(ServicioInstalado, serv_id)
            assert s_check is None, "El servicio debería haber sido eliminado de la BD"


@pytest.mark.asyncio
async def test_registrar_lluvia_persiste_en_db_con_fecha():
    transport = ASGITransport(app=app)
    async with AsyncSessionLocal() as session:
        res_u = await session.execute(select(Usuario).limit(1))
        user = res_u.scalars().first()
        res_c = await session.execute(select(Campo).limit(1))
        campo = res_c.scalars().first()
        assert user is not None and campo is not None

    cookies = {"session_user_id": str(user.id)}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Registrar lluvia de 42.5 mm con fecha específica
        payload = {
            "campo_id": str(campo.id),
            "milimetros": "42.5",
            "fecha": "2026-10-12",
            "observaciones": "Lluvia primaveral registrada en test",
        }
        res = await ac.post("/campo/acciones/lluvia", data=payload, cookies=cookies, follow_redirects=False)
        assert res.status_code == 303

        # Verificar persistencia en base de datos real
        async with AsyncSessionLocal() as session:
            res_ll = await session.execute(
                select(RegistroLluvia)
                .where(
                    RegistroLluvia.campo_id == campo.id,
                    RegistroLluvia.milimetros == 42.5
                )
                .order_by(RegistroLluvia.fecha.desc())
            )
            reg = res_ll.scalars().first()
            assert reg is not None
            assert reg.observaciones == "Lluvia primaveral registrada en test"
            assert reg.fecha.year == 2026
            assert reg.fecha.month == 10
            assert reg.fecha.day == 12

            # Limpiar registro creado por el test
            await session.delete(reg)
            await session.commit()
