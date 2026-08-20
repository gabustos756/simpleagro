# 📦 Especificación y Guía de Uso: Stock Físico & Comercial V1 (EduAgro)

**Módulo:** Comercial / Stock Físico & Comercial V1  
**Versión:** `1.3.0 (Stock 1B: Reservas, Asignaciones, Capacidad Física & Calidad Auditable)`  
**Estado:** Funcional e Implementado  

---

## 1. Introducción y Arquitectura

Stock V1 provee trazabilidad integral de inventario físico real, gestión de capacidad física de ubicaciones de guarda y control de bloqueos comerciales y operativos en EduAgro.

### Fases de Implementación:
- **Stock 1A:** Registro de partidas físicas (`StockPartida`), ubicaciones de guarda (`StorageLocation`), libro inmutable de movimientos auditables (`StockMovement`) y mediciones de calidad (`StockQualityMeasurement`).
- **Stock 1B (Fase Actual):** Reservas de stock por compromisos comerciales (`StockReservation`), asignaciones manuales a entregas (`StockDeliveryAllocation`) y control atómico de capacidad física de almacenamiento.
- **Histórico de Calidad:** Registro auditable append-only de mediciones de humedad y condición sobre partidas sin sobrescribir datos históricos.

---

## 2. Modelos de Datos (Stock 1B, Capacidad & Calidad)

### A. `StorageLocation` (`storage_locations`)
Ubicación física o custodia de grano (Silo propio, Silobolsa, Acopio tercero, Planta, etc.).
- **Capacidad Física:** Obligatoria (`> 0`) para tipos `silo_propio` y `silobolsa`. Opcional para acopios o depósitos terceros.
- **Ubicaciones Legacy:** Si una ubicación existente de tipo silo/silobolsa carece de capacidad nominal, se marca como `CAPACIDAD_PENDIENTE` y bloquea nuevos ingresos de grano hasta que un usuario complete su capacidad real mediante la acción *Completar Capacidad*.

### B. `StockReservation` (`stock_reservations`)
Reserva de stock físico para respaldar un compromiso comercial (`CompromisoGrano`).
- **Campos:** `id`, `cliente_id`, `stock_partida_id`, `compromiso_id`, `cantidad_reserva_kg`, `estado` (`activa`, `parcialmente_asignada`, `consumida`, `liberada`, `cancelada`), `fecha_reserva`, `fecha_liberacion`, `motivo_liberacion`, `observaciones`.

### C. `StockDeliveryAllocation` (`stock_delivery_allocations`)
Asignación manual de una partida física a una entrega de grano (`GrainDelivery`).
- **Campos:** `id`, `cliente_id`, `stock_partida_id`, `grain_delivery_id`, `stock_reservation_id`, `compromiso_id`, `cantidad_kg`, `origen_asignacion`, `estado`.

### D. `StockQualityMeasurement` (`stock_quality_measurements`)
Histórico append-only de condiciones de calidad y humedad asociadas a cada partida física.
- **Campos:** `id`, `cliente_id`, `stock_partida_id`, `measured_at`, `humedad_pct`, `temperatura_c`, `estado_calidad`, `fuente`, `observaciones`.

---

## 3. Ocupación Física vs. Disponibilidad Comercial

Es fundamental distinguir entre **Ocupación Física de la Ubicación** y **Disponible Comercial de la Partida**:

1. **Ocupación Física de Ubicación ($\text{occupied\_kg}$):**
   $$\text{occupied\_kg} = \sum_{p \in \text{PartidasActivasEnUbicacion}} \text{saldo\_fisico\_kg}(p)$$
   - Suma del grano real almacenado derivado estrictamente del libro de movimientos (`StockMovement`).
   - Las reservas comerciales o asignaciones operativas **NO alteran ni reducen** la ocupación física del silo o silobolsa, ya que el grano sigue físicamente presente en el depósito.
   - En el alta de una nueva partida, si $\text{occupied\_kg} + \text{nueva\_cantidad\_kg} > \text{capacity\_kg}$, el backend rechaza el alta de inmediato con el mensaje exacto:
     *“La ubicación ‘[Nombre]’ tiene capacidad de X Tn, posee Y Tn ocupadas y sólo dispone de Z Tn. No es posible cargar W Tn.”*

2. **Disponible Comercial de Partida ($\text{stock\_disponible\_kg}$):**
   $$\text{stock\_disponible\_kg} = \text{stock\_fisico\_kg} - \text{stock\_reservado\_kg} - \text{stock\_asignado\_kg}$$
   - Representa la fracción de grano de esa partida específica libre de compromisos comerciales y de entregas operativas.

---

## 4. Gestión de Calidad & Mediciones Históricas Inválidas (Legacy)

- **Validación de Rango:** La humedad debe ser Decimal dentro del rango **5,0% a 35,0% inclusive** (soporta notación argentina `13,5`, `13.5`, `13,5%`).
- **Registros Legacy Inválidos:**
  - Mediciones antiguas creadas antes de la regla con humedad fuera del rango (ej. `2%`) NO se eliminan ni modifican en la base de datos para preservar la auditabilidad.
  - La UI marca estas mediciones con la etiqueta `VALOR A REVISAR` y el aviso: *“Registro anterior a la validación actual; verificar o cargar una medición correctiva.”*
  - Las mediciones inválidas son excluidas automáticamente del cálculo de la "Última humedad útil" de la partida.
  - Para corregir un dato histórico inválido, el usuario debe cargar una **nueva medición de calidad válida**, la cual pasará a ser la última humedad vigente.

---

## 5. Invariantes de Seguridad y Concurrencia

- **Locking de Ubicación & Partida:** Consultas de ocupación e ingresos ejecutan bloqueos transaccionales para evitar carreras simultáneas en PostgreSQL.
- **Piso de Reducción de Capacidad:** No es posible editar la capacidad de una ubicación a un valor menor que su ocupación física actual.
- **Multitenancy Estricto:** Control de propiedad por `cliente_id` en todas las consultas y acciones de CRUD.
- **No Descuento Físico en Stock 1B:** Ni reservar ni asignar descuenta stock físico real ni altera la ocupación del silo.

---

## 6. Alcance y Roadmap

### Alcance Cumplido en Stock 1B:
- Mantenimiento de 4 saldos comerciales por partida en tiempo real.
- Bloqueo rígido de capacidad nominal en silos y silobolsas.
- Ocupación física derivada de movimientos inmutables.
- Reservas por compromisos y asignaciones a entregas.
- Detección de humedad fuera de rango en mediciones legacy sin alterar la historia.
- Edición de ubicaciones con control de piso de ocupación.

### Funcionalidades Postergadas para Stock 1C:
- Descuento automático de stock físico por despacho / recepción de cartas de porte (`GrainWaybill`).
- Ajustes por diferencias de pesaje origen vs destino.
- Mermas automáticas por secada / humedad.
- Transferencias entre silos.
