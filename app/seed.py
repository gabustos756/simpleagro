from datetime import date
from decimal import Decimal
import uuid
from app.auth import hash_password
from app.enums import (
    EstadoProductivoLoteEnum,
    EstadoServicioInstaladoEnum,
    FrecuenciaPagoEnum,
    RolUsuario,
    TenenciaTipoEnum,
    TipoCompromisoEnum,
    TipoPrecioEnum,
    TipoServicioEnum,
    UbicacionStockEnum,
)

# Cliente Real: Familia Matteuda (Laguna Larga, Córdoba)
DEMO_CLIENTE = {
    "id": "e0a1b2c3-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
    "nombre": "Familia Matteuda",
    "cuit": "30-71894235-9",
    "ubicacion": "Laguna Larga, Córdoba",
    "activo": True,
}

# Campañas Agrícolas Demo
DEMO_CAMPANIAS = [
    {
        "id": "campania-2025-2026",
        "nombre": "Campaña 2025/2026",
        "fecha_inicio": "2025-07-01",
        "fecha_fin": "2026-06-30",
        "activa": True,
    },
    {
        "id": "campania-2024-2025",
        "nombre": "Campaña 2024/2025",
        "fecha_inicio": "2024-07-01",
        "fecha_fin": "2025-06-30",
        "activa": False,
    },
]

# Contratos de Venta de Grano Demo (Familia Matteuda - Maíz y Soja)
DEMO_CONTRATOS_GRANO = [
    {
        "id": "contrato-soja-001",
        "campania_id": "campania-2025-2026",
        "cultivo": "soja",
        "comprador_acopio": "Cargill S.A. (Puerto San Martín)",
        "numero_contrato": "SOJ-2026-0412",
        "toneladas": Decimal("300.00"),
        "tipo_precio": TipoPrecioEnum.FIJO,
        "precio_usd_tn": Decimal("295.00"),
        "fecha_contrato": date(2026, 3, 15),
        "fecha_entrega_limite": date(2026, 5, 31),
        "observaciones": "Forward Soja 1ra entregado en puerto San Martín.",
    },
    {
        "id": "contrato-soja-002",
        "campania_id": "campania-2025-2026",
        "cultivo": "soja",
        "comprador_acopio": "ACA Cooperativa Laguna Larga",
        "numero_contrato": "SOJ-2026-0889",
        "toneladas": Decimal("200.00"),
        "tipo_precio": TipoPrecioEnum.A_FIJAR,
        "precio_usd_tn": None,
        "fecha_contrato": date(2026, 4, 10),
        "fecha_entrega_limite": date(2026, 6, 30),
        "observaciones": "Venta A Fijar a precio Pizarra Rosario mayo/junio.",
    },
    {
        "id": "contrato-maiz-001",
        "campania_id": "campania-2025-2026",
        "cultivo": "maiz",
        "comprador_acopio": "Bunge Argentina (Puerto Rosario)",
        "numero_contrato": "MAI-2026-0155",
        "toneladas": Decimal("450.00"),
        "tipo_precio": TipoPrecioEnum.FIJO,
        "precio_usd_tn": Decimal("180.00"),
        "fecha_contrato": date(2026, 2, 20),
        "fecha_entrega_limite": date(2026, 7, 31),
        "observaciones": "Forward Maíz Temprano julio 2026.",
    },
]

# Stock Físico de Grano Demo (Silo Bolsa y Acopio)
DEMO_STOCKS_GRANO = [
    {
        "id": "stock-001",
        "campo_id": "campo-001",
        "campania_id": "campania-2025-2026",
        "cultivo": "soja",
        "ubicacion_tipo": UbicacionStockEnum.SILO_BOLSA,
        "identificador": "SiloBolsa N° 2 - Lote 1 El Silo",
        "toneladas_almacenadas": Decimal("180.50"),
        "fecha_ingreso": date(2026, 5, 20),
        "observaciones": "Bolsa Ipacal 9 pies. Humedad 13.2%.",
    },
    {
        "id": "stock-002",
        "campo_id": "campo-002",
        "campania_id": "campania-2025-2026",
        "cultivo": "maiz",
        "ubicacion_tipo": UbicacionStockEnum.ACOPIO_TERCERO,
        "identificador": "Acopio ACA Laguna Larga - Planta N° 1",
        "toneladas_almacenadas": Decimal("320.00"),
        "fecha_ingreso": date(2026, 7, 10),
        "observaciones": "Cosecha Maíz 1ra depositada en acopio sin liquidar.",
    },
]

# Compromisos de Grano Demo (Alquileres en Quintales / Canjes)
DEMO_COMPROMISOS_GRANO = [
    {
        "id": "compromiso-001",
        "campania_id": "campania-2025-2026",
        "campo_id": "campo-001",
        "cultivo": "soja",
        "tipo_compromiso": TipoCompromisoEnum.ALQUILER_ARRENDAMIENTO,
        "concepto": "Alquiler Lote 2 La Escuela (200 ha a 12 qq/ha soja)",
        "beneficiario": "Familia Donati (Propietarios)",
        "toneladas_comprometidas": Decimal("240.00"),
        "fecha_vencimiento": date(2026, 11, 30),
        "cumplido": False,
    },
]

# Campos de la Familia Matteuda en Laguna Larga, Córdoba (Coordenadas Reales: -31.7766, -63.8011)
DEMO_CAMPOS = [
    {
        "id": "campo-001",
        "nombre": "Estancia La Esperanza",
        "ubicacion": "Laguna Larga, Córdoba",
        "localidad_referencia": "Laguna Larga, Córdoba",
        "latitud": -31.7766,
        "longitud": -63.8011,
        "hectareas_totales": 520.0,
        "hectareas_productivas": 495.0,
        "lotes_count": 3,
    },
    {
        "id": "campo-002",
        "nombre": "Campo Don Ramón",
        "ubicacion": "Laguna Larga, Córdoba",
        "localidad_referencia": "Laguna Larga, Córdoba",
        "latitud": -31.7820,
        "longitud": -63.7950,
        "hectareas_totales": 380.0,
        "hectareas_productivas": 360.0,
        "lotes_count": 2,
    },
]

# Lotes de la Familia Matteuda (Laguna Larga)
DEMO_LOTES = [
    {
        "id": "lote-001",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "nombre": "Lote 1 - El Silo",
        "superficie_total_ha": 160.0,
        "superficie_productiva_ha": 155.0,
        "tenencia_tipo": TenenciaTipoEnum.PROPIO.value,
        "tenencia_label": "Propio",
        "costo_alquiler_usd_ha": 0.0,
        "vencimiento_alquiler": None,
        "notas_alquiler": "Tierra propia de la Familia Matteuda.",
        "cultivo_anterior": "Trigo 24/25",
        "cultivo_actual": "Soja 1ra",
        "cultivo_planificado": "Maíz Tardío 26/27",
        "tipo_suelo": "Argiudol Típico (Clase I)",
        "qq_ha_estimado": 38.0,
        "qq_ha_real": 42.5,
        "produccion_total_qq": 6587.5,
        "produccion_total_t": 658.75,
        "observaciones": "Lote con excelente desarrollo vegetativo R3 en Laguna Larga.",
        "estado_productivo": EstadoProductivoLoteEnum.EN_CRECIMIENTO.value,
        "estado_productivo_label": "En Crecimiento",
    },
    {
        "id": "lote-002",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "nombre": "Lote 2 - La Escuela",
        "superficie_total_ha": 210.0,
        "superficie_productiva_ha": 200.0,
        "tenencia_tipo": TenenciaTipoEnum.ALQUILADO.value,
        "tenencia_label": "Alquilado",
        "costo_alquiler_usd_ha": 185.0,
        "vencimiento_alquiler": "2026-12-31",
        "notas_alquiler": "Contrato trienal a fijar en quintales de soja a valor pizarra Rosario.",
        "cultivo_anterior": "Maíz 24/25",
        "cultivo_actual": "Trigo / Soja 2da",
        "cultivo_planificado": "Soja 1ra 26/27",
        "tipo_suelo": "Haplustol Lúvico",
        "qq_ha_estimado": 35.0,
        "qq_ha_real": 36.8,
        "produccion_total_qq": 7360.0,
        "produccion_total_t": 736.00,
        "observaciones": "Humedad de grano en 13.5%. Cosechadora lista.",
        "estado_productivo": EstadoProductivoLoteEnum.LISTO_COSECHA.value,
        "estado_productivo_label": "Listo para Cosecha",
    },
    {
        "id": "lote-003",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "nombre": "Lote 3 - El Boquerón",
        "superficie_total_ha": 150.0,
        "superficie_productiva_ha": 140.0,
        "tenencia_tipo": TenenciaTipoEnum.PROPIO.value,
        "tenencia_label": "Propio",
        "costo_alquiler_usd_ha": 0.0,
        "vencimiento_alquiler": None,
        "notas_alquiler": "Lote propio familiar.",
        "cultivo_anterior": "Girasol 24/25",
        "cultivo_actual": "Soja 1ra",
        "cultivo_planificado": "Trigo / Soja 2da 26/27",
        "tipo_suelo": "Argiudol Típico",
        "qq_ha_estimado": 36.0,
        "qq_ha_real": 31.0,
        "produccion_total_qq": 4340.0,
        "produccion_total_t": 434.0,
        "observaciones": "⚠️ Mancha de Amaranthus (Yuyo Colorado) detectada en cabecera norte.",
        "estado_productivo": EstadoProductivoLoteEnum.CON_ALERTA.value,
        "estado_productivo_label": "Con Alerta Fitosanitaria",
    },
    {
        "id": "lote-004",
        "campo_id": "campo-002",
        "campo_nombre": "Campo Don Ramón",
        "nombre": "Lote 4 - El Bajo",
        "superficie_total_ha": 200.0,
        "superficie_productiva_ha": 190.0,
        "tenencia_tipo": TenenciaTipoEnum.ALQUILADO.value,
        "tenencia_label": "Alquilado",
        "costo_alquiler_usd_ha": 190.0,
        "vencimiento_alquiler": "2027-05-31",
        "notas_alquiler": "Contrato arrendamiento Laguna Larga con vencimiento mayo 2027.",
        "cultivo_anterior": "Soja 2da 24/25",
        "cultivo_actual": "Barbecho Químico",
        "cultivo_planificado": "Maíz Tardío 26/27",
        "tipo_suelo": "Entisol Psammentic",
        "qq_ha_estimado": 85.0,
        "qq_ha_real": 0.0,
        "produccion_total_qq": 0.0,
        "produccion_total_t": 0.0,
        "observaciones": "Barbecho limpio a la espera de acumulación de agua en perfil.",
        "estado_productivo": EstadoProductivoLoteEnum.BARBECHO.value,
        "estado_productivo_label": "Barbecho / Vacío",
    },
    {
        "id": "lote-005",
        "campo_id": "campo-002",
        "campo_nombre": "Campo Don Ramón",
        "nombre": "Lote 5 - El Potrero",
        "superficie_total_ha": 180.0,
        "superficie_productiva_ha": 170.0,
        "tenencia_tipo": TenenciaTipoEnum.PROPIO.value,
        "tenencia_label": "Propio",
        "costo_alquiler_usd_ha": 0.0,
        "vencimiento_alquiler": None,
        "notas_alquiler": "Lote propio sector alto.",
        "cultivo_anterior": "Soja 1ra 24/25",
        "cultivo_actual": "Maíz 1ra",
        "cultivo_planificado": "Soja 2da 26/27",
        "tipo_suelo": "Argiudol Típico",
        "qq_ha_estimado": 90.0,
        "qq_ha_real": 0.0,
        "produccion_total_qq": 0.0,
        "produccion_total_t": 0.0,
        "observaciones": "Sembrado hace 10 días. Emergencia uniforme en Laguna Larga.",
        "estado_productivo": EstadoProductivoLoteEnum.RECIEN_SEMBRADO.value,
        "estado_productivo_label": "Recién Sembrado",
    },
]

# Instalaciones Físicas de la Familia Matteuda (Laguna Larga)
DEMO_INSTALACIONES = [
    {
        "id": "inst-001",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "nombre": "Casa Principal La Esperanza",
        "tipo": "casa",
        "tipo_label": "🏡 Casa Principal",
        "ubicacion_notas": "Casco principal de la Familia Matteuda, Laguna Larga.",
    },
    {
        "id": "inst-002",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "nombre": "Galpón Maquinarias Norte",
        "tipo": "galpon",
        "tipo_label": "🚜 Galpón Maquinarias",
        "ubicacion_notas": "Guardado de tractores, cosechadora y tanque de combustible.",
    },
    {
        "id": "inst-003",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "nombre": "Pozo y Bomba de Riego Lote 2",
        "tipo": "pozo_bomba",
        "tipo_label": "⚡ Pozo / Bomba Riego",
        "ubicacion_notas": "Electrobomba sumergible trífasica en perforación Lote 2.",
    },
    {
        "id": "inst-004",
        "campo_id": "campo-002",
        "campo_nombre": "Campo Don Ramón",
        "nombre": "Depósito de Insumos Laguna Larga",
        "tipo": "deposito",
        "tipo_label": "📦 Depósito Insumos",
        "ubicacion_notas": "Galpón estanco para fitosanitarios y semillas.",
    },
]

# Servicios Instalados Demo para Familia Matteuda
DEMO_SERVICIOS_INSTALADOS = [
    {
        "id": "serv-001",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "instalacion_id": "inst-003",
        "instalacion_nombre": "Pozo y Bomba de Riego Lote 2",
        "tipo_servicio": TipoServicioEnum.LUZ_RURAL.value,
        "tipo_servicio_label": "⚡ Luz Rural",
        "concepto": "EPEC - Luz Rural Laguna Larga (Bomba Lote 2)",
        "proveedor": "EPEC Laguna Larga / Villa Rosario",
        "frecuencia_pago": FrecuenciaPagoEnum.MENSUAL.value,
        "frecuencia_label": "Mensual",
        "monto_estimado_ars": 450000.0,
        "monto_real_ars": 485000.0,
        "monto_usd": 377.28,
        "fecha_vencimiento": "2026-08-02",
        "estado": EstadoServicioInstaladoEnum.VENCIDO.value,
        "estado_label": "Vencido",
        "comprobante_url": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80",
        "observaciones": "Facturación por consumo pico de bomba en riego presiembra.",
    },
    {
        "id": "serv-002",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "instalacion_id": "inst-001",
        "instalacion_nombre": "Casa Principal La Esperanza",
        "tipo_servicio": TipoServicioEnum.INTERNET.value,
        "tipo_servicio_label": "📡 Internet Satelital",
        "concepto": "Starlink Internet Campo - Conexión Casa Matteuda",
        "proveedor": "Starlink Argentina",
        "frecuencia_pago": FrecuenciaPagoEnum.MENSUAL.value,
        "frecuencia_label": "Mensual",
        "monto_estimado_ars": 68000.0,
        "monto_real_ars": 68000.0,
        "monto_usd": 52.90,
        "fecha_vencimiento": "2026-08-10",
        "estado": EstadoServicioInstaladoEnum.AL_DIA.value,
        "estado_label": "Al día",
        "comprobante_url": "https://images.unsplash.com/photo-1450133064473-71024230f91b?auto=format&fit=crop&w=600&q=80",
        "observaciones": "Servicio de alta velocidad en casa principal del casco.",
    },
    {
        "id": "serv-003",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "instalacion_id": "inst-002",
        "instalacion_nombre": "Galpón Maquinarias Norte",
        "tipo_servicio": TipoServicioEnum.COMBUSTIBLE.value,
        "tipo_servicio_label": "🛢️ Combustible Diesel",
        "concepto": "Gasoil Ultra Diesel YPF - Tanque Galpón Esperanza",
        "proveedor": "YPF Directo Manfredi / Laguna Larga",
        "frecuencia_pago": FrecuenciaPagoEnum.EVENTUAL.value,
        "frecuencia_label": "Eventual",
        "monto_estimado_ars": 2500000.0,
        "monto_real_ars": 2850000.0,
        "monto_usd": 2217.00,
        "fecha_vencimiento": "2026-08-12",
        "estado": EstadoServicioInstaladoEnum.PENDIENTE.value,
        "estado_label": "Pendiente",
        "comprobante_url": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80",
        "observaciones": "Carga de 2.000 litros de gasoil para inicio de labores.",
    },
    {
        "id": "serv-004",
        "campo_id": "campo-002",
        "campo_nombre": "Campo Don Ramón",
        "instalacion_id": "inst-004",
        "instalacion_nombre": "Depósito de Insumos Laguna Larga",
        "tipo_servicio": TipoServicioEnum.IMPUESTO_TASA.value,
        "tipo_servicio_label": "🏛️ Tasa Viaria / Conservación",
        "concepto": "Tasa Conservación Caminos Rurales (Cuota 4)",
        "proveedor": "Municipalidad de Laguna Larga",
        "frecuencia_pago": FrecuenciaPagoEnum.BIMENSUAL.value,
        "frecuencia_label": "Bimensual",
        "monto_estimado_ars": 280000.0,
        "monto_real_ars": 295000.0,
        "monto_usd": 229.50,
        "fecha_vencimiento": "2026-08-25",
        "estado": EstadoServicioInstaladoEnum.PENDIENTE.value,
        "estado_label": "Pendiente",
        "comprobante_url": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80",
        "observaciones": "Tasa municipal conservadora de caminos vecinales.",
    },
]

# Usuarios Demo de la Familia Matteuda
# Usuarios Demo de Validación (6 Superadmins)
DEMO_USUARIOS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "nombre": "Andrés",
        "email": "andres@eduagro.com.ar",
        "password": "andres123",
        "password_hash": hash_password("andres123"),
        "rol": RolUsuario.ADMIN,
        "rol_label": "Super Admin",
        "cliente_nombre": DEMO_CLIENTE["nombre"],
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "nombre": "Belén",
        "email": "belen@eduagro.com.ar",
        "password": "belen123",
        "password_hash": hash_password("belen123"),
        "rol": RolUsuario.ADMIN,
        "rol_label": "Super Admin",
        "cliente_nombre": DEMO_CLIENTE["nombre"],
    },
    {
        "id": "33333333-3333-3333-3333-333333333333",
        "nombre": "Florencia",
        "email": "florencia@eduagro.com.ar",
        "password": "florencia123",
        "password_hash": hash_password("florencia123"),
        "rol": RolUsuario.ADMIN,
        "rol_label": "Super Admin",
        "cliente_nombre": DEMO_CLIENTE["nombre"],
    },
    {
        "id": "44444444-4444-4444-4444-444444444444",
        "nombre": "Noris",
        "email": "noris@eduagro.com.ar",
        "password": "noris123",
        "password_hash": hash_password("noris123"),
        "rol": RolUsuario.ADMIN,
        "rol_label": "Super Admin",
        "cliente_nombre": DEMO_CLIENTE["nombre"],
    },
    {
        "id": "55555555-5555-5555-5555-555555555555",
        "nombre": "Verónica",
        "email": "veronica@eduagro.com.ar",
        "password": "veronica123",
        "password_hash": hash_password("veronica123"),
        "rol": RolUsuario.ADMIN,
        "rol_label": "Super Admin",
        "cliente_nombre": DEMO_CLIENTE["nombre"],
    },
    {
        "id": "66666666-6666-6666-6666-666666666666",
        "nombre": "Romina",
        "email": "romina@eduagro.com.ar",
        "password": "romina123",
        "password_hash": hash_password("romina123"),
        "rol": RolUsuario.ADMIN,
        "rol_label": "Super Admin",
        "cliente_nombre": DEMO_CLIENTE["nombre"],
    },
]


def find_user_by_email(email: str):
    email_clean = email.strip().lower()
    for user in DEMO_USUARIOS:
        if user["email"].lower() == email_clean:
            return user
    return None


def find_user_by_id(user_id: str):
    for user in DEMO_USUARIOS:
        if user["id"] == user_id:
            return user
    return None


# Tareas de Campo Operativas Demo (Modo Campo Hoy)
DEMO_TAREAS = [
    {
        "id": "tarea-001",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "lote_id": "lote-001",
        "lote_nombre": "Lote 1 - El Silo",
        "tipo": "siembra",
        "tipo_label": "🌱 Siembra",
        "titulo": "Siembra de Soja de 1ra (Variedad DM 46E25)",
        "responsable": "Andrés",
        "prioridad": "alta",
        "prioridad_label": "Alta",
        "estado": "en_curso",
        "estado_label": "En Curso",
        "fecha": "2026-07-28",
        "observaciones": "Trabajando en lote con sembradora John Deere 1590 a 52 cm. Densidad objetivo: 320.000 semillas/ha.",
        "valor_registrado": "320.000 sem/ha",
    },
    {
        "id": "tarea-002",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "lote_id": "lote-002",
        "lote_nombre": "Lote 2 - La Escuela",
        "tipo": "lluvia_suelo",
        "tipo_label": "🌧️ Lluvia / Suelo",
        "titulo": "Registro de Lluvia Tormenta del Domingo",
        "responsable": "Belén",
        "prioridad": "media",
        "prioridad_label": "Media",
        "estado": "hecha",
        "estado_label": "Hecha",
        "fecha": "2026-07-27",
        "observaciones": "Lluvia registrada en pluviómetro de casco principal. Buena recarga de humedad en perfil de suelo.",
        "valor_registrado": "42.5 mm",
    },
    {
        "id": "tarea-003",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "lote_id": "lote-003",
        "lote_nombre": "Lote 3 - El Boquerón",
        "tipo": "incidencia",
        "tipo_label": "⚠️ Novedad / Incidencia",
        "titulo": "Alerta Fitosanitaria: Mancha Yuyo Colorado en Cabecera",
        "responsable": "Florencia",
        "prioridad": "alta",
        "prioridad_label": "Alta",
        "estado": "pendiente",
        "estado_label": "Pendiente",
        "fecha": "2026-07-28",
        "observaciones": "Mancha localizada de Amaranthus resistente en cabecera norte junto al alambre. Preparar mochila o pulverizador.",
        "valor_registrado": "Foco maleza resistente",
    },
    {
        "id": "tarea-004",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "lote_id": None,
        "lote_nombre": "Galpón Maquinarias Norte",
        "tipo": "stock_insumos",
        "tipo_label": "📦 Stock e Insumos",
        "titulo": "Carga de Combustible Diesel para Tractores",
        "responsable": "Noris",
        "prioridad": "media",
        "prioridad_label": "Media",
        "estado": "hecha",
        "estado_label": "Hecha",
        "fecha": "2026-07-28",
        "observaciones": "Retiro de 450 litros de Gasoil Ultra Diesel de tanque principal para inicio de labores de siembra.",
        "valor_registrado": "450 Litros Gasoil",
    },
    {
        "id": "tarea-005",
        "campo_id": "campo-001",
        "campo_nombre": "Estancia La Esperanza",
        "lote_id": "lote-001",
        "lote_nombre": "Lote 1 - El Silo",
        "tipo": "revision_lote",
        "tipo_label": "🔍 Monitoreo / Control Lote",
        "titulo": "Control de Cobertura y Humedad de Cama de Siembra",
        "responsable": "Verónica",
        "prioridad": "baja",
        "prioridad_label": "Baja",
        "estado": "pendiente",
        "estado_label": "Pendiente",
        "fecha": "2026-07-29",
        "observaciones": "Revisar nacencia uniforme y nivel de rastrojo previo a la pasada de fertilizadora.",
        "valor_registrado": "Evaluación visual",
    },
    {
        "id": "tarea-006",
        "campo_id": "campo-002",
        "campo_nombre": "Campo Don Ramón",
        "lote_id": "lote-004",
        "lote_nombre": "Lote 4 - El Bajo",
        "tipo": "siembra",
        "tipo_label": "🌱 Siembra / Barbecho",
        "titulo": "Pulverización Barbecho Químico Pre-Maíz",
        "responsable": "Romina",
        "prioridad": "media",
        "prioridad_label": "Media",
        "estado": "pendiente",
        "estado_label": "Pendiente",
        "fecha": "2026-07-28",
        "observaciones": "Aplicación de atrazina + glifosato. Chequear velocidad de viento previo a iniciar.",
        "valor_registrado": "150 l/ha",
    },
    {
        "id": "tarea-007",
        "campo_id": "campo-002",
        "campo_nombre": "Campo Don Ramón",
        "lote_id": "lote-005",
        "lote_nombre": "Lote 5 - El Potrero",
        "tipo": "cosecha",
        "tipo_label": "🚜 Cosecha",
        "titulo": "Cosecha de Maíz de 1ra",
        "responsable": "Andrés",
        "prioridad": "alta",
        "prioridad_label": "Alta",
        "estado": "en_curso",
        "estado_label": "En Curso",
        "fecha": "2026-07-28",
        "observaciones": "Humedad de grano en 14.2%. Cosechadora Case 7120 trabajando en sector alto.",
        "valor_registrado": "Rinde est. 90 qq/ha",
    },
]


def get_uuid(key_str: str) -> uuid.UUID:
    """Convierte una cadena a UUID; genera uno determinista si no es un UUID válido."""
    try:
        return uuid.UUID(key_str)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, key_str)


async def seed_initial_data(session):
    """Pobla la base de datos PostgreSQL con datos iniciales del ERP y del Módulo Comercial."""
    from sqlalchemy import select
    from app.models import (
        Campo,
        Campania,
        Cliente,
        CompromisoGrano,
        ContratoVentaGrano,
        StockGrano,
        Usuario,
    )

    # 1. Crear Cliente
    cliente_id = get_uuid(DEMO_CLIENTE["id"])
    cliente = await session.get(Cliente, cliente_id)
    if not cliente:
        cliente = Cliente(
            id=cliente_id,
            nombre=DEMO_CLIENTE["nombre"],
            cuit=DEMO_CLIENTE.get("cuit"),
            ubicacion=DEMO_CLIENTE.get("ubicacion"),
            activo=True,
        )
        session.add(cliente)
        await session.flush()

    # 2. Crear Usuarios Iniciales si no existen
    result = await session.execute(select(Usuario).limit(1))
    if not result.scalars().first():
        for u_dict in DEMO_USUARIOS:
            rol_val = u_dict["rol"]
            if not isinstance(rol_val, RolUsuario):
                rol_val = RolUsuario(rol_val)
            user_obj = Usuario(
                id=get_uuid(u_dict["id"]),
                cliente_id=cliente_id,
                nombre=u_dict["nombre"],
                email=u_dict["email"],
                password_hash=u_dict["password_hash"],
                rol=rol_val,
            )
            session.add(user_obj)
        await session.flush()

    # 3. Crear Campos si no existen
    for c_dict in DEMO_CAMPOS:
        campo_id = get_uuid(c_dict["id"])
        c_obj = await session.get(Campo, campo_id)
        if not c_obj:
            c_obj = Campo(
                id=campo_id,
                cliente_id=cliente_id,
                nombre=c_dict["nombre"],
                ubicacion=c_dict.get("ubicacion"),
                localidad_referencia=c_dict.get("localidad_referencia"),
                latitud=c_dict.get("latitud"),
                longitud=c_dict.get("longitud"),
                hectareas_totales=c_dict.get("hectareas_totales", 0.0),
            )
            session.add(c_obj)
    await session.flush()

    # 4. Crear Campañas si no existen
    for camp_dict in DEMO_CAMPANIAS:
        camp_id = get_uuid(camp_dict["id"])
        camp_obj = await session.get(Campania, camp_id)
        if not camp_obj:
            camp_obj = Campania(
                id=camp_id,
                cliente_id=cliente_id,
                nombre=camp_dict["nombre"],
                fecha_inicio=date.fromisoformat(camp_dict["fecha_inicio"]),
                fecha_fin=date.fromisoformat(camp_dict["fecha_fin"]) if camp_dict.get("fecha_fin") else None,
                activa=camp_dict.get("activa", True),
            )
            session.add(camp_obj)
    await session.flush()

    # 5. Crear Contratos de Venta Grano si no existen
    res_contratos = await session.execute(select(ContratoVentaGrano).limit(1))
    if not res_contratos.scalars().first():
        for contr_dict in DEMO_CONTRATOS_GRANO:
            contr_obj = ContratoVentaGrano(
                id=get_uuid(contr_dict["id"]),
                cliente_id=cliente_id,
                campania_id=get_uuid(contr_dict["campania_id"]),
                cultivo=contr_dict["cultivo"],
                comprador_acopio=contr_dict["comprador_acopio"],
                numero_contrato=contr_dict.get("numero_contrato"),
                toneladas=contr_dict["toneladas"],
                tipo_precio=contr_dict["tipo_precio"],
                precio_usd_tn=contr_dict.get("precio_usd_tn"),
                fecha_contrato=contr_dict["fecha_contrato"],
                fecha_entrega_limite=contr_dict.get("fecha_entrega_limite"),
                observaciones=contr_dict.get("observaciones"),
            )
            session.add(contr_obj)

    # 6. Crear Stock Grano si no existen
    res_stock = await session.execute(select(StockGrano).limit(1))
    if not res_stock.scalars().first():
        for st_dict in DEMO_STOCKS_GRANO:
            st_obj = StockGrano(
                id=get_uuid(st_dict["id"]),
                cliente_id=cliente_id,
                campo_id=get_uuid(st_dict["campo_id"]),
                campania_id=get_uuid(st_dict["campania_id"]),
                cultivo=st_dict["cultivo"],
                ubicacion_tipo=st_dict["ubicacion_tipo"],
                identificador=st_dict["identificador"],
                toneladas_almacenadas=st_dict["toneladas_almacenadas"],
                fecha_ingreso=st_dict["fecha_ingreso"],
                observaciones=st_dict.get("observaciones"),
            )
            session.add(st_obj)

    # 7. Crear Compromisos Grano si no existen
    res_comp = await session.execute(select(CompromisoGrano).limit(1))
    if not res_comp.scalars().first():
        for comp_dict in DEMO_COMPROMISOS_GRANO:
            comp_obj = CompromisoGrano(
                id=get_uuid(comp_dict["id"]),
                cliente_id=cliente_id,
                campania_id=get_uuid(comp_dict["campania_id"]),
                campo_id=get_uuid(comp_dict["campo_id"]) if comp_dict.get("campo_id") else None,
                cultivo=comp_dict["cultivo"],
                tipo_compromiso=comp_dict["tipo_compromiso"],
                concepto=comp_dict["concepto"],
                beneficiario=comp_dict["beneficiario"],
                toneladas_comprometidas=comp_dict["toneladas_comprometidas"],
                fecha_vencimiento=comp_dict.get("fecha_vencimiento"),
                cumplido=comp_dict.get("cumplido", False),
            )
            session.add(comp_obj)

    await session.commit()



