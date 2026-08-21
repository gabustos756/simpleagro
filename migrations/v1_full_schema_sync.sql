-- ==============================================================================
-- SCRIPT DE RECUPERACIÓN Y SINCRONIZACIÓN COMPLETA DE ESQUEMA POSTGRESQL (EDUAGRO V1)
-- ==============================================================================
-- Propósito: Garantizar idempotencia total de las 29 entidades y sus columnas/índices
-- en la base de datos PostgreSQL de producción, registrando la versión en Alembic.
-- Ejecución: Este script es de ejecución única vía ./scripts/migrate.sh o psql.
-- ==============================================================================

BEGIN;

-- 1. TIPOS ENUM POSTGRESQL (Creación Idempotente)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rol_usuario_enum') THEN
        CREATE TYPE rol_usuario_enum AS ENUM ('administrador', 'productor', 'contador', 'operador', 'invitado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_servicio_enum') THEN
        CREATE TYPE tipo_servicio_enum AS ENUM ('luz_rural', 'internet', 'combustible', 'mantenimiento', 'impuesto_tasa');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'frecuencia_pago_enum') THEN
        CREATE TYPE frecuencia_pago_enum AS ENUM ('mensual', 'bimensual', 'trimestral', 'semestral', 'anual', '2_anios', '3_anios', 'eventual');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_servicio_instalado_enum') THEN
        CREATE TYPE estado_servicio_instalado_enum AS ENUM ('al_dia', 'vencido', 'pendiente', 'suspendido');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_servicio_enum') THEN
        CREATE TYPE estado_servicio_enum AS ENUM ('pendiente', 'pagado', 'vencido', 'anulado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'document_type_enum') THEN
        CREATE TYPE document_type_enum AS ENUM ('factura', 'recibo', 'presupuesto', 'contrato', 'comprobante_pago', 'otro');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tenencia_tipo_enum') THEN
        CREATE TYPE tenencia_tipo_enum AS ENUM ('propio', 'alquilado', 'aparceria');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_labor_enum') THEN
        CREATE TYPE tipo_labor_enum AS ENUM ('siembra', 'fertilizacion', 'fumigacion', 'cosecha', 'monitoreo', 'otro');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_cpe_enum') THEN
        CREATE TYPE estado_cpe_enum AS ENUM ('borrador', 'en_transito', 'descargado', 'anulado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_transaccion_enum') THEN
        CREATE TYPE tipo_transaccion_enum AS ENUM ('ingreso', 'egreso');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_precio_enum') THEN
        CREATE TYPE tipo_precio_enum AS ENUM ('hecho', 'a_fijar', 'canje');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ubicacion_stock_enum') THEN
        CREATE TYPE ubicacion_stock_enum AS ENUM ('silo_propio', 'silobolsa', 'acopio_terceros');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_compromiso_enum') THEN
        CREATE TYPE tipo_compromiso_enum AS ENUM ('contrato_venta', 'arrendamiento_fijo', 'canje_insumos', 'reserva_semilla', 'otro');
    END IF;
END $$;

-- 2. TABLAS DEL SISTEMA (Creación Idempotente)
CREATE TABLE IF NOT EXISTS clientes (
    id UUID PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    cuit VARCHAR(20),
    ubicacion VARCHAR(150),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS campos (
    id UUID PRIMARY KEY,
    cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
    nombre VARCHAR(150) NOT NULL,
    ubicacion VARCHAR(150),
    localidad_referencia VARCHAR(150),
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    hectareas_totales DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS instalaciones (
    id UUID PRIMARY KEY,
    cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
    campo_id UUID NOT NULL REFERENCES campos(id) ON DELETE CASCADE,
    nombre VARCHAR(150) NOT NULL,
    tipo VARCHAR(50) NOT NULL DEFAULT 'casa',
    ubicacion_notas TEXT
);

CREATE TABLE IF NOT EXISTS usuarios (
    id UUID PRIMARY KEY,
    cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol rol_usuario_enum NOT NULL,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS servicios_instalados (
    id UUID PRIMARY KEY,
    cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
    campo_id UUID NOT NULL REFERENCES campos(id) ON DELETE CASCADE,
    instalacion_id UUID REFERENCES instalaciones(id) ON DELETE SET NULL,
    tipo_servicio tipo_servicio_enum NOT NULL,
    concepto VARCHAR(200) NOT NULL,
    proveedor VARCHAR(150) NOT NULL,
    frecuencia_pago frecuencia_pago_enum NOT NULL DEFAULT 'mensual',
    monto_estimado_ars NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
    monto_real_ars NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
    monto_usd NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
    fecha_vencimiento DATE NOT NULL,
    estado estado_servicio_instalado_enum NOT NULL DEFAULT 'pendiente',
    comprobante_url TEXT,
    payment_portal_url TEXT,
    payment_reference VARCHAR(200),
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS servicios_vencimiento (
    id UUID PRIMARY KEY,
    cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
    servicio_instalado_id UUID REFERENCES servicios_instalados(id) ON DELETE CASCADE,
    concepto VARCHAR(200) NOT NULL,
    monto_ars NUMERIC(14, 2) NOT NULL,
    monto_usd NUMERIC(14, 2) NOT NULL,
    fecha_vencimiento DATE NOT NULL,
    estado estado_servicio_enum NOT NULL DEFAULT 'pendiente',
    comprobante_url TEXT,
    payment_link TEXT,
    periodo_referencia VARCHAR(100),
    fecha_pago DATE
);

CREATE TABLE IF NOT EXISTS service_documents (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    servicio_id UUID REFERENCES servicios_instalados(id) ON DELETE CASCADE,
    servicio_vencimiento_id UUID REFERENCES servicios_vencimiento(id) ON DELETE CASCADE,
    document_type document_type_enum NOT NULL DEFAULT 'factura',
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    storage_key VARCHAR(500) UNIQUE NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    uploaded_by_user_id UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    notes TEXT,
    estado VARCHAR(20) NOT NULL DEFAULT 'activo'
);

CREATE TABLE IF NOT EXISTS campanias (
    id UUID PRIMARY KEY,
    cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    activa BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS lotes (
    id UUID PRIMARY KEY,
    campo_id UUID REFERENCES campos(id) ON DELETE CASCADE,
    cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
    campania_id UUID REFERENCES campanias(id) ON DELETE SET NULL,
    nombre VARCHAR(100) NOT NULL,
    superficie_total_ha DOUBLE PRECISION NOT NULL,
    superficie_productiva_ha DOUBLE PRECISION NOT NULL,
    tenencia_tipo tenencia_tipo_enum NOT NULL DEFAULT 'propio',
    costo_alquiler_usd_ha NUMERIC(10, 2),
    vencimiento_alquiler DATE,
    notas_alquiler TEXT,
    cultivo_anterior VARCHAR(100),
    cultivo_actual VARCHAR(100),
    cultivo_planificado VARCHAR(100),
    tipo_suelo VARCHAR(100),
    geolocalizacion_lat_lng JSONB,
    qq_ha_estimado DOUBLE PRECISION,
    qq_ha_real DOUBLE PRECISION,
    produccion_total_qq DOUBLE PRECISION,
    observaciones TEXT,
    metadatos_agronomicos JSONB
);

CREATE TABLE IF NOT EXISTS labores_campo (
    id UUID PRIMARY KEY,
    lote_id UUID NOT NULL REFERENCES lotes(id) ON DELETE CASCADE,
    campania_id UUID NOT NULL REFERENCES campanias(id) ON DELETE CASCADE,
    tipo_labor tipo_labor_enum NOT NULL,
    fecha TIMESTAMP WITH TIME ZONE NOT NULL,
    insumos_utilizados JSONB NOT NULL DEFAULT '[]'::jsonb,
    responsable_id UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    costo_estimado_usd NUMERIC(12, 2),
    notas TEXT
);

CREATE TABLE IF NOT EXISTS registros_lluvia (
    id UUID PRIMARY KEY,
    lote_id UUID NOT NULL REFERENCES lotes(id) ON DELETE CASCADE,
    milimetros DOUBLE PRECISION NOT NULL,
    fecha TIMESTAMP WITH TIME ZONE NOT NULL,
    registrado_por_id UUID REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS cartas_de_porte (
    id UUID PRIMARY KEY,
    numero_cpe VARCHAR(50) UNIQUE NOT NULL,
    lote_origen_id UUID NOT NULL REFERENCES lotes(id) ON DELETE RESTRICT,
    chofer_camion VARCHAR(150) NOT NULL,
    kilos_brutos DOUBLE PRECISION NOT NULL,
    kilos_netos DOUBLE PRECISION NOT NULL,
    fecha_emision TIMESTAMP WITH TIME ZONE NOT NULL,
    estado estado_cpe_enum NOT NULL DEFAULT 'en_transito'
);

CREATE TABLE IF NOT EXISTS transacciones_financieras (
    id UUID PRIMARY KEY,
    concepto VARCHAR(255) NOT NULL,
    tipo tipo_transaccion_enum NOT NULL,
    monto_usd NUMERIC(14, 2) NOT NULL,
    monto_ars NUMERIC(14, 2) NOT NULL,
    cotizacion_dolar NUMERIC(10, 2) NOT NULL,
    lote_id UUID REFERENCES lotes(id) ON DELETE SET NULL,
    pagado BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS contratos_venta_grano (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    campania_id UUID NOT NULL REFERENCES campanias(id) ON DELETE CASCADE,
    cultivo VARCHAR(50) NOT NULL,
    comprador_acopio VARCHAR(150) NOT NULL,
    numero_contrato VARCHAR(100),
    toneladas NUMERIC(12, 2) NOT NULL,
    tipo_precio tipo_precio_enum NOT NULL,
    precio_usd_tn NUMERIC(10, 2),
    fecha_contrato DATE NOT NULL,
    fecha_entrega_limite DATE,
    observaciones TEXT,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_grano (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    campo_id UUID NOT NULL REFERENCES campos(id) ON DELETE CASCADE,
    campania_id UUID NOT NULL REFERENCES campanias(id) ON DELETE CASCADE,
    cultivo VARCHAR(50) NOT NULL,
    ubicacion_tipo ubicacion_stock_enum NOT NULL,
    identificador VARCHAR(150) NOT NULL,
    toneladas_almacenadas NUMERIC(12, 2) NOT NULL,
    fecha_ingreso DATE NOT NULL,
    observaciones TEXT,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compromisos_grano (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    campania_id UUID NOT NULL REFERENCES campanias(id) ON DELETE CASCADE,
    campo_id UUID REFERENCES campos(id) ON DELETE SET NULL,
    cultivo VARCHAR(50) NOT NULL,
    tipo_compromiso tipo_compromiso_enum NOT NULL,
    concepto VARCHAR(200) NOT NULL,
    beneficiario VARCHAR(150) NOT NULL,
    toneladas_comprometidas NUMERIC(12, 2) NOT NULL,
    fecha_vencimiento DATE,
    cumplido BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arrendamiento_terms (
    id UUID PRIMARY KEY,
    compromiso_id UUID NOT NULL UNIQUE REFERENCES compromisos_grano(id) ON DELETE CASCADE,
    superficie_arrendada_ha NUMERIC(10, 2) NOT NULL,
    alquiler_qq_ha NUMERIC(10, 2) NOT NULL,
    base_valorizacion VARCHAR(50) NOT NULL DEFAULT 'rosario',
    precio_referencia_usd_tn NUMERIC(12, 2),
    fecha_precio_referencia DATE,
    fuente_precio VARCHAR(50),
    flete_usd_tn NUMERIC(12, 2),
    comision_usd_tn NUMERIC(12, 2),
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS precios_mercado_cache (
    id UUID PRIMARY KEY,
    cultivo VARCHAR(50) NOT NULL,
    fuente VARCHAR(100) NOT NULL,
    fecha DATE NOT NULL,
    precio_usd_tn NUMERIC(12, 2) NOT NULL,
    precio_ars_tn NUMERIC(12, 2),
    dolar_referencia NUMERIC(12, 2),
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weather_snapshots (
    id UUID PRIMARY KEY,
    campo_id UUID REFERENCES campos(id) ON DELETE SET NULL,
    lote_id UUID REFERENCES lotes(id) ON DELETE SET NULL,
    provider VARCHAR(50) NOT NULL,
    provider_status VARCHAR(50) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    timezone VARCHAR(100) NOT NULL DEFAULT 'America/Argentina/Cordoba',
    observed_at TIMESTAMP WITH TIME ZONE,
    forecast_generated_at TIMESTAMP WITH TIME ZONE,
    retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    schema_version VARCHAR(20) NOT NULL DEFAULT 'v2.0',
    normalized_payload JSONB NOT NULL,
    raw_payload JSONB,
    data_quality JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS freight_quotes (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    campo_id UUID REFERENCES campos(id) ON DELETE SET NULL,
    lote_id UUID REFERENCES lotes(id) ON DELETE SET NULL,
    destination_name VARCHAR(150) NOT NULL,
    destination_type VARCHAR(100),
    cultivo VARCHAR(50),
    condicion_precio VARCHAR(50),
    distancia_estimada_km NUMERIC(8, 2),
    price_usd_tn NUMERIC(12, 2),
    freight_usd_tn NUMERIC(12, 2),
    conditioning_cost_usd_tn NUMERIC(12, 2),
    other_costs_usd_tn NUMERIC(12, 2),
    max_receiving_moisture_pct NUMERIC(5, 2),
    receiving_confirmed VARCHAR(50) NOT NULL DEFAULT 'unknown',
    detalle_cupo_turno VARCHAR(300),
    road_status VARCHAR(50) NOT NULL DEFAULT 'unknown',
    quote_observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    quote_valid_until TIMESTAMP WITH TIME ZONE,
    quote_source VARCHAR(50) NOT NULL DEFAULT 'manual',
    quote_confidence VARCHAR(50),
    notes TEXT,
    created_by_user_id UUID,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS grain_deliveries (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    tracking_number VARCHAR(50) NOT NULL,
    campo_id UUID REFERENCES campos(id) ON DELETE SET NULL,
    lote_id UUID REFERENCES lotes(id) ON DELETE SET NULL,
    compromiso_id UUID REFERENCES compromisos_grano(id) ON DELETE SET NULL,
    freight_quote_id UUID REFERENCES freight_quotes(id) ON DELETE SET NULL,
    acopio_receptor VARCHAR(150),
    destination_final_reference VARCHAR(150),
    cultivo VARCHAR(50),
    transportista_nombre VARCHAR(150),
    fecha_planificada DATE,
    fecha_salida TIMESTAMP WITH TIME ZONE,
    fecha_recepcion TIMESTAMP WITH TIME ZONE,
    toneladas_planificadas NUMERIC(12, 2),
    kg_neto_origen_total NUMERIC(12, 2),
    kg_recibido_total NUMERIC(12, 2),
    diferencia_total_kg NUMERIC(12, 2),
    diferencia_total_pct NUMERIC(8, 2),
    estado VARCHAR(50) NOT NULL DEFAULT 'planificada',
    documentacion_status VARCHAR(50) NOT NULL DEFAULT 'sin_documentacion',
    observaciones TEXT,
    created_by_user_id UUID,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_grain_deliveries_cliente_tracking UNIQUE (cliente_id, tracking_number)
);

CREATE TABLE IF NOT EXISTS grain_waybills (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    entrega_id UUID NOT NULL REFERENCES grain_deliveries(id) ON DELETE CASCADE,
    numero_carta_porte VARCHAR(100),
    tipo_camion VARCHAR(50),
    capacidad_referencia_kg NUMERIC(12, 2),
    tara_kg NUMERIC(12, 2),
    peso_bruto_origen_kg NUMERIC(12, 2),
    peso_neto_origen_kg NUMERIC(12, 2),
    peso_recibido_destino_kg NUMERIC(12, 2),
    diferencia_kg NUMERIC(12, 2),
    diferencia_pct NUMERIC(8, 2),
    fecha_carga TIMESTAMP WITH TIME ZONE,
    fecha_recepcion TIMESTAMP WITH TIME ZONE,
    despatched_at TIMESTAMP WITH TIME ZONE,
    despatched_by_user_id UUID,
    referencia_ticket_origen VARCHAR(100),
    referencia_ticket_destino VARCHAR(100),
    observaciones TEXT,
    estado VARCHAR(50) NOT NULL DEFAULT 'planificada',
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS storage_locations (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    nombre VARCHAR(150) NOT NULL,
    tipo VARCHAR(50) NOT NULL DEFAULT 'silo_propio',
    campo_id UUID REFERENCES campos(id) ON DELETE SET NULL,
    ubicacion_referencia VARCHAR(200),
    identificador_fisico VARCHAR(100),
    capacidad_nominal_tn NUMERIC(12, 2),
    estado VARCHAR(50) NOT NULL DEFAULT 'activo',
    observaciones TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_storage_locations_cliente_tipo_nombre UNIQUE (cliente_id, tipo, nombre)
);

CREATE TABLE IF NOT EXISTS stock_partidas (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    tracking_number VARCHAR(50) NOT NULL,
    cultivo VARCHAR(50) NOT NULL,
    campania_id UUID REFERENCES campanias(id) ON DELETE SET NULL,
    campo_id UUID REFERENCES campos(id) ON DELETE SET NULL,
    lote_id UUID REFERENCES lotes(id) ON DELETE SET NULL,
    storage_location_id UUID NOT NULL REFERENCES storage_locations(id) ON DELETE CASCADE,
    fecha_cosecha DATE,
    fecha_ingreso DATE NOT NULL,
    origen_conocido BOOLEAN NOT NULL DEFAULT TRUE,
    origen_descripcion VARCHAR(300),
    cantidad_inicial_kg NUMERIC(12, 2) NOT NULL,
    estado VARCHAR(50) NOT NULL DEFAULT 'activa',
    observaciones TEXT,
    created_by_user_id UUID,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_stock_partidas_cliente_tracking UNIQUE (cliente_id, tracking_number)
);

CREATE TABLE IF NOT EXISTS stock_reservations (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    stock_partida_id UUID NOT NULL REFERENCES stock_partidas(id) ON DELETE CASCADE,
    compromiso_id UUID NOT NULL REFERENCES compromisos_grano(id) ON DELETE CASCADE,
    cantidad_reserva_kg NUMERIC(12, 2) NOT NULL,
    estado VARCHAR(50) NOT NULL DEFAULT 'activa',
    fecha_reserva TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_liberacion TIMESTAMP WITH TIME ZONE,
    motivo_liberacion VARCHAR(255),
    observaciones TEXT,
    created_by_user_id UUID,
    released_by_user_id UUID,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    stock_partida_id UUID NOT NULL REFERENCES stock_partidas(id) ON DELETE CASCADE,
    tipo VARCHAR(50) NOT NULL,
    cantidad_kg NUMERIC(12, 2) NOT NULL,
    fecha_movimiento TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    referencia_tipo VARCHAR(100),
    referencia_id VARCHAR(100),
    grain_delivery_id UUID REFERENCES grain_deliveries(id) ON DELETE SET NULL,
    grain_waybill_id UUID REFERENCES grain_waybills(id) ON DELETE SET NULL,
    stock_delivery_allocation_id UUID,
    motivo VARCHAR(255),
    observaciones TEXT,
    created_by_user_id UUID,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_delivery_allocations (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    stock_partida_id UUID NOT NULL REFERENCES stock_partidas(id) ON DELETE CASCADE,
    grain_delivery_id UUID NOT NULL REFERENCES grain_deliveries(id) ON DELETE CASCADE,
    stock_reservation_id UUID REFERENCES stock_reservations(id) ON DELETE SET NULL,
    compromiso_id UUID REFERENCES compromisos_grano(id) ON DELETE SET NULL,
    cantidad_kg NUMERIC(12, 2) NOT NULL,
    origen_asignacion VARCHAR(50) NOT NULL DEFAULT 'libre',
    estado VARCHAR(50) NOT NULL DEFAULT 'activa',
    fecha_asignacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_cancelacion TIMESTAMP WITH TIME ZONE,
    motivo_cancelacion VARCHAR(255),
    despatched_at TIMESTAMP WITH TIME ZONE,
    observaciones TEXT,
    created_by_user_id UUID,
    cancelled_by_user_id UUID,
    despatched_by_user_id UUID,
    stock_movement_id UUID,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_weight_reconciliations (
    id UUID PRIMARY KEY,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    grain_delivery_id UUID NOT NULL REFERENCES grain_deliveries(id) ON DELETE CASCADE,
    grain_waybill_id UUID NOT NULL REFERENCES grain_waybills(id) ON DELETE CASCADE,
    peso_neto_origen_kg NUMERIC(12, 2) NOT NULL,
    peso_recibido_destino_kg NUMERIC(12, 2) NOT NULL,
    diferencia_kg NUMERIC(12, 2) NOT NULL,
    diferencia_pct NUMERIC(8, 2) NOT NULL,
    estado VARCHAR(50) NOT NULL DEFAULT 'pendiente',
    resolucion_tipo VARCHAR(50),
    resolucion_observaciones TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by_user_id UUID,
    stock_movement_id UUID REFERENCES stock_movements(id) ON DELETE SET NULL,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- 3. ADICIÓN IDEMPOTENTE DE COLUMNAS A TABLAS EXISTENTES
ALTER TABLE campos ADD COLUMN IF NOT EXISTS localidad_referencia VARCHAR(150);
ALTER TABLE campos ADD COLUMN IF NOT EXISTS latitud DOUBLE PRECISION;
ALTER TABLE campos ADD COLUMN IF NOT EXISTS longitud DOUBLE PRECISION;
ALTER TABLE campos ADD COLUMN IF NOT EXISTS hectareas_totales DOUBLE PRECISION DEFAULT 0.0;

ALTER TABLE servicios_instalados ADD COLUMN IF NOT EXISTS payment_portal_url TEXT;
ALTER TABLE servicios_instalados ADD COLUMN IF NOT EXISTS payment_reference VARCHAR(200);

ALTER TABLE servicios_vencimiento ADD COLUMN IF NOT EXISTS servicio_instalado_id UUID REFERENCES servicios_instalados(id) ON DELETE CASCADE;
ALTER TABLE servicios_vencimiento ADD COLUMN IF NOT EXISTS payment_link TEXT;
ALTER TABLE servicios_vencimiento ADD COLUMN IF NOT EXISTS periodo_referencia VARCHAR(100);
ALTER TABLE servicios_vencimiento ADD COLUMN IF NOT EXISTS fecha_pago DATE;

ALTER TABLE freight_quotes ADD COLUMN IF NOT EXISTS cultivo VARCHAR(50);
ALTER TABLE freight_quotes ADD COLUMN IF NOT EXISTS condicion_precio VARCHAR(50);
ALTER TABLE freight_quotes ADD COLUMN IF NOT EXISTS distancia_estimada_km NUMERIC(8, 2);
ALTER TABLE freight_quotes ADD COLUMN IF NOT EXISTS detalle_cupo_turno VARCHAR(300);

ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS grain_delivery_id UUID REFERENCES grain_deliveries(id) ON DELETE SET NULL;
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS grain_waybill_id UUID REFERENCES grain_waybills(id) ON DELETE SET NULL;
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS stock_delivery_allocation_id UUID REFERENCES stock_delivery_allocations(id) ON DELETE SET NULL;

ALTER TABLE stock_delivery_allocations ADD COLUMN IF NOT EXISTS despatched_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE stock_delivery_allocations ADD COLUMN IF NOT EXISTS despatched_by_user_id UUID;
ALTER TABLE stock_delivery_allocations ADD COLUMN IF NOT EXISTS stock_movement_id UUID REFERENCES stock_movements(id) ON DELETE SET NULL;

ALTER TABLE grain_waybills ADD COLUMN IF NOT EXISTS despatched_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE grain_waybills ADD COLUMN IF NOT EXISTS despatched_by_user_id UUID;

-- 4. CREACIÓN IDEMPOTENTE DE ÍNDICES
CREATE INDEX IF NOT EXISTS ix_servicios_vencimiento_cliente_fecha ON servicios_vencimiento(cliente_id, fecha_vencimiento);
CREATE INDEX IF NOT EXISTS ix_servicios_vencimiento_servicio_id ON servicios_vencimiento(servicio_instalado_id);
CREATE INDEX IF NOT EXISTS ix_service_documents_cliente_id ON service_documents(cliente_id);
CREATE INDEX IF NOT EXISTS ix_service_documents_servicio_id ON service_documents(servicio_id);
CREATE INDEX IF NOT EXISTS ix_service_documents_vencimiento_id ON service_documents(servicio_vencimiento_id);
CREATE INDEX IF NOT EXISTS ix_contratos_cliente_campania_cultivo ON contratos_venta_grano(cliente_id, campania_id, cultivo);
CREATE INDEX IF NOT EXISTS ix_stock_cliente_campania_cultivo ON stock_grano(cliente_id, campania_id, cultivo);
CREATE INDEX IF NOT EXISTS ix_stock_campo ON stock_grano(campo_id);
CREATE INDEX IF NOT EXISTS ix_compromisos_cliente_campania_cultivo ON compromisos_grano(cliente_id, campania_id, cultivo);
CREATE INDEX IF NOT EXISTS ix_precios_mercado_cultivo_fecha ON precios_mercado_cache(cultivo, fecha);
CREATE INDEX IF NOT EXISTS ix_weather_snapshots_campo_retrieved ON weather_snapshots(campo_id, retrieved_at);
CREATE INDEX IF NOT EXISTS ix_freight_quotes_cliente_destination ON freight_quotes(cliente_id, destination_name);
CREATE INDEX IF NOT EXISTS ix_grain_deliveries_cliente_estado ON grain_deliveries(cliente_id, estado);
CREATE INDEX IF NOT EXISTS ix_grain_waybills_cliente_numero ON grain_waybills(cliente_id, numero_carta_porte);
CREATE INDEX IF NOT EXISTS ix_grain_waybills_entrega ON grain_waybills(entrega_id);
CREATE INDEX IF NOT EXISTS ix_storage_locations_cliente_campo ON storage_locations(cliente_id, campo_id);
CREATE INDEX IF NOT EXISTS ix_stock_partidas_cliente_estado ON stock_partidas(cliente_id, estado);
CREATE INDEX IF NOT EXISTS ix_stock_partidas_storage_location ON stock_partidas(storage_location_id);
CREATE INDEX IF NOT EXISTS ix_stock_movements_cliente_partida ON stock_movements(cliente_id, stock_partida_id);
CREATE INDEX IF NOT EXISTS ix_stock_movements_fecha ON stock_movements(fecha_movimiento);
CREATE INDEX IF NOT EXISTS ix_stock_quality_partida_measured ON stock_quality_measurements(stock_partida_id, measured_at);
CREATE INDEX IF NOT EXISTS ix_stock_reservations_cliente_partida ON stock_reservations(cliente_id, stock_partida_id);
CREATE INDEX IF NOT EXISTS ix_stock_reservations_compromiso ON stock_reservations(compromiso_id);
CREATE INDEX IF NOT EXISTS ix_stock_reservations_estado ON stock_reservations(estado);
CREATE INDEX IF NOT EXISTS ix_stock_allocations_cliente_partida ON stock_delivery_allocations(cliente_id, stock_partida_id);
CREATE INDEX IF NOT EXISTS ix_stock_allocations_delivery ON stock_delivery_allocations(grain_delivery_id);
CREATE INDEX IF NOT EXISTS ix_stock_allocations_reservation ON stock_delivery_allocations(stock_reservation_id);
CREATE INDEX IF NOT EXISTS ix_stock_allocations_estado ON stock_delivery_allocations(estado);
CREATE INDEX IF NOT EXISTS ix_stock_reconciliations_cliente ON stock_weight_reconciliations(cliente_id);
CREATE INDEX IF NOT EXISTS ix_stock_reconciliations_delivery ON stock_weight_reconciliations(grain_delivery_id);
CREATE INDEX IF NOT EXISTS ix_stock_reconciliations_waybill ON stock_weight_reconciliations(grain_waybill_id);
CREATE INDEX IF NOT EXISTS ix_stock_reconciliations_estado ON stock_weight_reconciliations(estado);

-- 5. REGISTRO DE VERSIÓN DE ALEMBIC (Sincronización con Alembic Head)
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('001_initial_full_schema');

COMMIT;
