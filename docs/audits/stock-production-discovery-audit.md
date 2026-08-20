# 🔍 Auditoría de Descubrimiento Técnico: Módulos de Stock, Producción, Cosecha y Comercial

**Proyecto:** EduAgro  
**Fecha:** 20 de Agosto de 2026  
**Documento:** `docs/audits/stock-production-discovery-audit.md`  
**Estado:** Informe de Arquitectura y Descubrimiento Previo a Stock V1  

---

## 1. Resumen Ejecutivo

Esta auditoría analiza en profundidad el estado técnico y funcional del código fuente real de EduAgro (`app/models.py`, `app/main.py`, `app/services/comercial.py`, `app/enums.py`) con el propósito de diseñar el futuro módulo **Stock V1** sin duplicar modelos existentes, sin romper los flujos de Comercial ni del Motor de Decisiones, y preservando la trazabilidad multitenant por `cliente_id`.

### Principales Hallazgos:
1. **Módulo Comercial V1 Consolidado:** Existen entidades maduras para cotizaciones de flete (`FreightQuote`), entregas comerciales (`GrainDelivery`) y pesajes de cartas de porte (`GrainWaybill`), con aislamiento estricto por `cliente_id` y reglas determinísticas registradas.
2. **Modelo de Stock Actual (`StockGrano`):** Es una entidad estática y agregada por campo/campaña/cultivo/ubicación. No registra lotes de origen, eventos de cosecha, mediciones de humedad/calidad, reservas ni historial de movimientos auditables.
3. **Cálculo de Posición Comercial:** La cifra de "Toneladas Libres" en `/comercial` (Resumen) no se calcula actualmente desde `StockGrano`, sino multiplicando la superficie productiva del lote por su rinde real/estimado (`qq_ha_real` / `qq_ha_estimado`) y restando ventas y compromisos.
4. **Ausencia de Entidad `Cosecha`:** Los eventos de cosecha hoy se registran únicamente como labores generales (`LaborCampo` con `tipo_labor="cosecha"`) o como métricas de rinde estáticas en el modelo `Lote`.
5. **Rotación de Cultivos en `Lote`:** El historial de rotación se almacena en campos de texto plano sobre la misma fila del lote (`cultivo_anterior`, `cultivo_actual`, `cultivo_planificado`), lo que implica riesgo de sobreescritura al cambiar de campaña si no se independiza la rotación histórica.

---

## 2. Inventario de Modelos y Tablas SQLAlchemy

| Entidad | Tabla | PK | `cliente_id` | Relaciones Principales | Campos Relevantes | Estado de Uso |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Cliente` | `clientes` | `id` (UUID) | N/A (Root) | `campos`, `lotes`, `stocks_grano`, `deliveries`, `freight_quotes` | `nombre`, `cuit`, `activo` | Activa y usada en UI/rutas |
| `Campo` | `campos` | `id` (UUID) | FK `clientes.id` | `lotes`, `instalaciones`, `stocks_grano`, `compromisos_grano` | `nombre`, `latitud`, `longitud`, `hectareas_totales` | Activa y usada en UI/rutas |
| `Lote` | `lotes` | `id` (UUID) | FK `clientes.id` | `campo`, `campania`, `labores`, `cartas_de_porte`, `transacciones` | `superficie_productiva_ha`, `cultivo_actual`, `qq_ha_real` | Activa y usada en UI/rutas |
| `Campania` | `campanias` | `id` (UUID) | FK `clientes.id` | `lotes`, `labores`, `contratos_venta`, `stocks_grano`, `compromisos` | `nombre`, `fecha_inicio`, `fecha_fin`, `activa` | Activa y usada en UI/rutas |
| `LaborCampo` | `labores_campo` | `id` (UUID) | Vía `lote_id` | `lote`, `campania`, `responsable` | `tipo_labor`, `fecha`, `insumos_utilizados`, `costo_estimado` | Activa en `/campo` |
| `RegistroLluvia` | `registros_lluvia` | `id` (UUID) | Vía `lote_id` | `lote`, `registrado_por` | `milimetros`, `fecha` | Activa en `/campo` |
| `StockGrano` | `stock_grano` | `id` (UUID) | FK `clientes.id` | `cliente`, `campo`, `campania` | `cultivo`, `ubicacion_tipo`, `identificador`, `toneladas_almacenadas` | Activa en `/comercial/stock` |
| `CompromisoGrano` | `compromisos_grano` | `id` (UUID) | FK `clientes.id` | `cliente`, `campania`, `campo` | `cultivo`, `tipo_compromiso`, `toneladas_comprometidas`, `cumplido` | Activa en `/comercial/contratos` |
| `ContratoVentaGrano` | `contratos_venta_grano` | `id` (UUID) | FK `clientes.id` | `cliente`, `campania` | `cultivo`, `comprador_acopio`, `toneladas`, `tipo_precio` | Activa en `/comercial/contratos` |
| `FreightQuote` | `freight_quotes` | `id` (UUID) | FK `clientes.id` | `cliente`, `campo`, `lote` | `destination_name`, `price_usd_tn`, `freight_usd_tn`, `road_status` | Activa en `/comercial/fletes` |
| `GrainDelivery` | `grain_deliveries` | `id` (UUID) | FK `clientes.id` | `cliente`, `campo`, `lote`, `compromiso`, `freight_quote`, `waybills` | `tracking_number`, `acopio_receptor`, `estado`, `documentacion_status` | Activa en `/comercial/entregas` |
| `GrainWaybill` | `grain_waybills` | `id` (UUID) | FK `clientes.id` | `entrega` (`GrainDelivery`) | `numero_carta_porte`, `tara_kg`, `peso_bruto_origen_kg`, `peso_recibido_destino_kg` | Activa en `/comercial/entregas` |
| `CartaDePorte` | `cartas_de_porte` | `id` (UUID) | **No posee** | `lote_origen` (`Lote`) | `numero_cpe`, `kilos_brutos`, `kilos_netos` | **Legacy / Obsolescente** |
| `TransaccionFinanciera` | `transacciones_financieras` | `id` (UUID) | Vía `lote_id` | `lote` | `concepto`, `monto_usd`, `tipo` | Activa en `/finanzas` |

---

## 3. Inventario de Rutas, Templates y Servicios

| Ruta / Componente | Finalidad | Modelos Usados | Multi-tenant | Datos Reales vs Mock | Riesgos Identificados |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /productivo/campos` | Listado general de campos y hectáreas | `Campo`, `Lote` | Sí (`cliente_id`) | Reales (DB) | Ninguno |
| `GET /productivo/lotes` | Listado y filtro de lotes por campo/cultivo | `Lote`, `Campo` | Sí (`cliente_id`) | Reales (DB) | Sobreescritura de cultivos al cambiar campaña |
| `POST /productivo/lotes/nuevo` | Registro de lote con rendimientos | `Lote` | Sí (`cliente_id`) | Reales (DB) | Rinde en quintales (`qq_ha_real`) sin fecha de cosecha |
| `POST /campo/acciones/stock` | Consumo rápido de insumos desde app móvil | In-memory `TAREAS_STORE` | No (Demo) | Mock (En memoria) | No persiste en base de datos |
| `GET /comercial` | Resumen de posición comercial e insights | `Lote`, `ContratoVentaGrano`, `StockGrano`, `CompromisoGrano` | Sí (`cliente_id`) | Reales (DB) | "Tn libres" usa estimación de lote, no stock almacenado |
| `GET /comercial/stock` | Gestión visual de stock físico en silos y acopios | `StockGrano`, `Campo`, `Campania` | Sí (`cliente_id`) | Reales (DB) | Edición manual directa sin registro de movimientos |
| `POST /comercial/stock/crear` | Alta de registro de stock por campo/cultivo | `StockGrano` | Sí (`cliente_id`) | Reales (DB) | No valida lote de origen ni humedad del grano |
| `GET /comercial/fletes` | Cotización y ranking de fletes y destinos | `FreightQuote`, `DecisionEngine` | Sí (`cliente_id`) | Reales (DB) | Ninguno |
| `GET /comercial/entregas` | Gestión de entregas y pesajes de cartas de porte | `GrainDelivery`, `GrainWaybill` | Sí (`cliente_id`) | Reales (DB) | Ninguno |

---

## 4. Estado Real de Campaña, Rotación, Producción y Cosecha

### A. Campañas (`Campania`)
- Existe el modelo `Campania` en `app/models.py`.
- Se identifica por `nombre` (ej. "Campaña 2025/2026"), `fecha_inicio`, `fecha_fin` y un indicador booleano `activa`.
- Está vinculada correctamente con `Lote`, `ContratoVentaGrano`, `StockGrano` y `CompromisoGrano`.

### B. Rotación e Historial de Cultivos
- `Lote` posee los campos de texto `cultivo_anterior`, `cultivo_actual` y `cultivo_planificado`.
- **Riesgo:** No existe una tabla intermedia de rotación (`LoteCampaniaCultivo`). Si el usuario cambia la campaña activa o modifica el `cultivo_actual`, se pierde la trazabilidad histórica del cultivo anterior a menos que se mantengan los registros de labores.

### C. Cosecha y Rendimientos
- No existe una tabla de entidad `Cosecha`.
- Las toneladas producidas se calculan en runtime multiplicando `superficie_productiva_ha` por `qq_ha_real` (o `qq_ha_estimado`) dividido por 10.
- `LaborCampo` permite guardar `tipo_labor="cosecha"`, pero esto guarda fecha e insumos sin generar un lote/partida de stock físico ni registrar mediciones de humedad en la cosecha.

---

## 5. Estado Real del Stock Existente (`StockGrano`)

1. **Estructura:** Asocia `cliente_id`, `campo_id`, `campania_id`, `cultivo`, `ubicacion_tipo` (`silo_bolsa`, `acopio_tercero`, `puerto`), `identificador` y `toneladas_almacenadas`.
2. **Deficiencias Actuales para Trazabilidad Físico-Comercial:**
   - No está vinculado a un `lote_id` de origen.
   - No registra la fecha ni evento de cosecha.
   - No almacena porcentaje de humedad, condición comercial ni calidad (zarandeo/tierra/picado).
   - No cuenta con tabla de **Movimientos de Stock** (`StockMovimiento`), por lo que no hay auditoría de entradas, salidas, mermas o transferencias.
   - No distingue entre stock físico real, stock disponible, stock reservado o asignado a entregas.

---

## 6. Hallazgos de Integridad y Multitenancy

- **Aislamiento Multitenant:** Todos los modelos comerciales recientes (`FreightQuote`, `GrainDelivery`, `GrainWaybill`, `StockGrano`, `CompromisoGrano`, `ContratoVentaGrano`) filtran correctamente por `cliente_id`.
- **Excepción / Deuda Legacy:** El modelo legacy `CartaDePorte` (`cartas_de_porte`) en `app/models.py` no posee `cliente_id` ni relación con `GrainDelivery`. Debe ser marcado como deprecado en favor de `GrainWaybill`.
- **Tipos Numéricos:** Las entidades comerciales y de flete utilizan `Decimal`/`Numeric(12,2)`. El modelo `Lote` utiliza `Float` para superficies y rendimientos en quintales, por lo que al calcular toneladas en `calcular_posicion_comercial` se convierte explícitamente a `Decimal(str(...))` para prevenir imprecisiones.

---

## 7. Mapa de Datos Actual y Huecos Identificados

```text
[Lote] (superficie, rinde qq)
  │
  ├──> (Producción Teórica Calculada) ──> [Posición Comercial - Tn Libres]
  │
[StockGrano] (Almacenado manual por campo/campaña)
  │
  └──> (Sin vínculo con Cosecha, Lote ni Movimientos Auditables)
```

### Huecos Detectados para Stock V1:
1. **Entidad Partida / Lote de Stock (`GrainLot` / `StockPartida`):** Falta representar partidas físicas de grano cosechado con fecha, humedad de ingreso y origen exacto.
2. **Entidad Ubicación Físico-Almacén (`StorageLocation` / `Deposito`):** Falta representar depósitos, celdas, silos fijos con capacidad o silobolsas numerados.
3. **Libro de Movimientos (`StockMovement`):** Falta el registro inmutable de movimientos (Ingreso Cosecha, Egreso Entrega, Merma Secada, Transferencia Acopio, Ajuste Auditoría).
4. **Vínculo Entrega ↔ Stock:** La entrega (`GrainDelivery`) posee FKs a campo, lote y compromiso, pero no se vincula a la partida física de stock de donde se retira el grano.

---

## 8. Mapa de Integración Futura hacia Stock V1

```text
Campaña / Lote
   │
   ▼
[Evento Cosecha] (Fecha, Tn húmedas, % Humedad origen)
   │
   ▼
[Partida de Stock / StockLot] (Grano, Campaña, Calidad)
   │
   ├──> [Ubicación de Guarda] (Silo N°, Silobolsa X, Acopio Y)
   │
   ├──> [Medición Calidad/Condición] (% Humedad, Zarandeo)
   │
   └──> [Movimiento de Reserva / Salida]
           │
           ▼
     [Compromiso] ──> [GrainDelivery] ──> [GrainWaybill] (Pesaje Balanza)
```

---

## 9. Riesgos de Duplicación y Migración

1. **Riesgo de Doble Conteo en Posición Comercial:** Al introducir Stock V1 real, la pantalla `/comercial` debe migrar gradualmente de usar la producción teórica estimada (`Lote.qq_ha_real`) a utilizar el stock físico disponible real sin sumar ambos valores.
2. **Duplicación de Cartas de Porte:** Evitar reactivar el modelo legacy `CartaDePorte` y consolidar toda la trazabilidad de viajes en `GrainDelivery` y `GrainWaybill`.
3. **Mutaciones Directas en BD:** Asegurar que los saldos de partidas de stock sean siempre el resultado de la suma de sus movimientos auditables, impidiendo updates manuales directos sobre `toneladas_almacenadas`.

---

## 10. Plan de Carga Histórica en Fases

### Fase 1A (Indispensable para Stock V1):
- Campañas activas y anteriores (ej. 2024/2025 y 2025/2026).
- Lotes por campo con superficie productiva y cultivo asignado.
- Stock inicial actual (toneladas, cultivo, ubicación/silo y campaña).

### Fase 1B (Trazabilidad y Calidad Operativa):
- Histórico de las últimas 3 rotaciones por lote.
- Registros de humedad e ingreso por silobolsa/depósito.
- Compromisos pendientes de entrega (alquileres, canjes).

### Fase 1C (Auditoría Avanzada y Análisis del Motor):
- Histórico completo de pesajes de cartas de porte pasadas.
- Métricas históricas de rinde por hectárea calibradas.

---

## 11. Recomendación de Orden de Implementación para Stock V1

1. **Paso 1 (Modelos de Almacenamiento y Partida):** Crear los modelos inmutables de ubicación de guarda (`StorageLocation`), partida física (`GrainLot`) y libro de movimientos (`StockMovement`) con aislamiento multitenant estricto.
2. **Paso 2 (Servicios Calculadores Puros de Stock):** Implementar calculadoras puras en `app/services/stock/` para obtener saldo disponible, reservado y despachado a partir de movimientos.
3. **Paso 3 (Integración con Entregas):** Permitir la imputación opcional de un retiro de stock al crear una `GrainDelivery`.
4. **Paso 4 (UI y Pantallas de Stock):** Actualizar la vista `/comercial/stock` para mostrar el desglose por partida, silobolsa y movimientos sin romper endpoints existentes.

---

## 12. Preguntas Técnicas Internas Pendientes

1. ¿Se debe permitir que un silobolsa contenga grano de múltiples lotes del mismo campo si se cosecharon el mismo día con igual humedad? *(Decisión recomendada: Sí, mediante partidas unificadas por silobolsa/ubicación).*
2. En caso de mermas por secada en acopio, ¿el ajuste de toneladas debe registrarse como un movimiento de egreso por merma en el libro de movimientos? *(Decisión recomendada: Sí, tipo de movimiento `merma_secada`).*
