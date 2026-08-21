# Documentación Técnica: Dashboard Comercial V2

## Descripción General
El **Dashboard Comercial V2** (`/comercial`) sincroniza y consolida la posición comercial agregada de EduAgro utilizando exclusivamente la arquitectura **Stock 1A/1B/1C** (`StockPartida`, `StockMovement`, `StockReservation`, `StockDeliveryAllocation`, `StockWeightReconciliation`, `CompromisoGrano`, `GrainDelivery`).

Se ha desacoplado por completo de la tabla agregada legacy `StockGrano` y se ha aislado la producción teórica de lotes para garantizar que no altere los saldos disponibles libres ni induzca a decisiones comerciales erróneas.

---

## Bloques Ejecutivos del Dashboard V2

### Bloque 1: KPIs de Stock Físico Registrado
- **Stock Físico Registrado**: Saldo total de existencias físicas derivadas exclusivamente de movimientos transaccionales.
- **Stock Reservado**: Toneladas bloqueadas activas vinculadas a compromisos comerciales.
- **Stock Asignado a Entregas**: Toneladas asignadas a entregas planificadas sin despacho confirmado.
- **Stock Disponible Libre**: Físico Registrado − Reservado − Asignado.

### Bloque 2: Prioridades de Hoy
Alertas accionables ordenadas por nivel de criticidad (`critical`, `warning`, `info`):
1. **Diferencias de Pesaje Pendientes** (`CONCILIACION_PENDIENTE`): Pesajes de destino con diferencias superiores al límite de tolerancia.
2. **Compromisos Vencidos o sin Reserva** (`COMPROMISO_VENCIDO` / `COBERTURA_PENDIENTE`): Alerta preventiva a 15 días o vencimientos superados.
3. **Entregas en Tránsito sin Recepción** (`ENTREGA_EN_TRANSITO`): Camiones en camino hacia acopio/puerto pendientes de pesaje final.

### Bloque 3: Compromisos Próximos
- Muestra hasta 5 compromisos comerciales pendientes con su etiqueta normalizada construida por `build_commitment_display_label`.
- Incluye el estado de cobertura (`cubierto`, `parcial`, `sin_cobertura`) y acceso directo al módulo de contratos `/comercial/contratos`.

### Bloque 4: Stock por Cultivo y Guarda
- Desglose por cultivo (Soja, Maíz, Trigo, Sorgo) detallando existencias físicas, reservas y disponible libre.
- Etiqueta automáticamente el grano almacenado en instalaciones tipo `"acopio"` como **"En Custodia/Acopio"**.

### Bloque 5: Operaciones Recientes y Logística
- Listado de las últimas 5 entregas/cartas de porte con número de tracking, descripción, estado y CTA directo a `/comercial/entregas`.

---

## Referencia Agronómica Secundaria (Producción Teórica)
- **Ubicación**: Sección informativa al pie del dashboard.
- **Leyenda**: *"Producción estimada de lotes — Referencia agronómica estimada, no representa stock físico registrado."*
- **Aislamiento**: Se calcula en vivo como $\text{superficie productiva (ha)} \times \text{rinde (qq/ha)} / 10$, pero **NUNCA** se suma a las toneladas disponibles ni al stock libre.

---

## Aislamiento Multitenant
- Toda la capa de lectura (`app/services/commercial_dashboard_service.py`) requiere explícitamente el parámetro `cliente_id`.
- Las consultas en base de datos están estrictamente aisladas por `cliente_id`, impidiendo fugas cross-tenant de información comercial.
