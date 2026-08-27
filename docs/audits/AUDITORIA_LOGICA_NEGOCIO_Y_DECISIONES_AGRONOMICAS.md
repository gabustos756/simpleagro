# 🌾 Auditoría Integral de Lógica de Negocio y Motor de Decisiones - EduAgro

**Destinatario:** Ingeniero Estratégico en Agronomía / Dirección Técnica Agropecuaria  
**Proyecto:** EduAgro (v2.0 / v3.0)  
**Fecha:** 26 de Agosto de 2026  
**Estado:** Auditoría Técnica y Comercial Completa  
**Repositorio:** `gabustos756/simpleagro`  

---

## 📋 Resumen Ejecutivo

El presente documento constituye una auditoría exhaustiva e informe técnico-operativo sobre toda la **lógica de negocio, modelos matemáticos, reglas agronómicas, logística de fletes, gestión de stock y recomendaciones comerciales** integradas en la plataforma **EduAgro**.

EduAgro cuenta con un **Motor de Decisiones Determinístico, Explicable y Trazable (V2.0)** ubicado en `app/services/decision_engine/`, complementado por los módulos de **Stock Comercial 1A/1B/1C**, **Logística y Cartas de Porte V2**, **Gestión de Insumos V3** y el **Dashboard Comercial Integrado**.

El objetivo de esta auditoría es transparentar el 100% de los algoritmos y reglas de toma de decisiones para que un **socio agrónomo** o **director técnico** comprenda cómo el sistema transforma datos meteorológicos, financieros, de inventario y de mercado en recomendaciones prácticas para el productor.

---

## 🏛️ 1. Principios de Diseño del Motor de Decisiones

El núcleo de toma de decisiones de EduAgro opera bajo cinco principios rectores innegociables:

1. **Determinismo Absoluto (Cero Cajas Negras):** Dadas las mismas entradas de campo/mercado/clima (`DecisionContext`) y la misma política (`EffectivePolicyValue`), el sistema **siempre produce exactamente la misma recomendación**, sin aleatoriedad. No se utilizan modelos probabilísticos o LLMs para generar cálculos numéricos o alertas críticas.
2. **Explicabilidad Estructurada:** Cada recomendación emitida (`DecisionInsight`) adjunta explícitamente:
   - **Drivers:** Variables determinantes (ej. % humedad, mm lluvia, tarifa flete).
   - **Tradeoffs:** Compensaciones económico-operativas (ej. costo de secada vs. riesgo de brotado/vuelco).
   - **Reason Codes:** Códigos únicos de razón para trazabilidad (`HIGH_GRAIN_MOISTURE`, `IMMINENT_RAINFALL`).
   - **Nivel de Confianza:** Clasificado en `high`, `medium` o `low` según la frescura y coincidencia de fuentes de datos.
3. **Preservación Estricta de Datos Faltantes:** Si un dato no está disponible (`None`), **nunca se asume 0.0**. La falta de información genera estados explícitos (`missing`, `not_evaluable`, `partial`) y activa avisos de calidad de datos.
4. **Funciones Puras:** Calculadoras desacopladas sin llamadas I/O a base de datos ni servicios externos, garantizando alta velocidad y facilidad de auditoría.
5. **Jerarquía de Precedencia de Políticas (7 Capas):** Permite personalizar umbrales agronómicos y comerciales desde la base del sistema hasta el lote individual:
   $$\text{run\_override} > \text{lot} > \text{field} > \text{family\_client} > \text{organization} > \text{agronomic\_template} > \text{system\_base}$$

---

## 🚜 2. Lógica Agronómica y Agrometeorológica

### A. Cosecha y Economía de Secada de Granos (`app/services/decision_engine/rules/harvest.py`)

El sistema evalúa el momento óptimo de cosecha balanceando la humedad medida del grano en lote contra el costo de acondicionamiento y el pronóstico de precipitaciones.

#### 1. Fórmulas de Secada
- **Exceso de Humedad ($\%$):**
  $$\text{exceso\_humedad} = \max\left(0,\, \text{humedad\_grano} - \text{humedad\_base\_comercial}\right)$$
  *Bases comerciales por defecto:* Maíz: $14.5\%$, Soja: $13.5\%$, Sorgo: $15.0\%$, Trigo: $14.0\%$.

- **Costo Total de Secada ($\mathrm{USD/Tn}$):**
  $$\text{costo\_secada}_{\mathrm{USD/Tn}} = \text{exceso\_humedad} \times \text{costo\_punto}_{\mathrm{USD/Tn}}$$
  *Default:* $\mathrm{US\$}\ 2.50\ \mathrm{USD/Tn}$ por punto porcentual en exceso.

- **Impacto sobre Precio Spot ($\%$):**
  $$\text{impacto\_secada}_{\%} = \frac{\text{costo\_secada}_{\mathrm{USD/Tn}}}{\text{precio\_spot}_{\mathrm{USD/Tn}}} \times 100$$

#### 2. Reglas Determinísticas de Cosecha
- **`HUMEDAD_ALTA_Y_VENTANA_SECA`:**
  - *Condición:* Humedad de grano por encima de la base comercial AND lluvia prevista a 72 horas $< 10.0\ \mathrm{mm}$.
  - *Recomendación:* **Esperar secado natural en pie**. Informa el ahorro potencial de secada ($\approx \mathrm{US\$}\ 2.50/\mathrm{Tn}/\text{punto}$) si las condiciones del lote (vuelco, desgrane, presión de plagas y transitabilidad) lo permiten.
- **`HUMEDAD_ALTA_Y_LLUVIA_PROXIMA`:**
  - *Condición:* Humedad de grano por encima de la base comercial AND lluvia prevista a 72 horas $\ge 10.0\ \mathrm{mm}$.
  - *Recomendación:* **Cosechar e ingresar a secadora de inmediato**. El riesgo de pérdida de calidad, brotado o pérdida de piso supera el costo económico del acondicionamiento artificial.
- **`COSTO_SECADA_ELEVADO`:**
  - *Condición:* El costo de secada absorbe $\ge 3.0\%$ del valor total de la tonelada spot.
  - *Recomendación:* **Alerta tarifaria**. Sugiere auditar la tabla de mermas del acopio antes de autorizar el despacho.

---

### B. Ventana de Pulverización y Fitosanitarios (`app/services/decision_engine/rules/spraying.py`)

Evalúa las condiciones micrometeorológicas para aplicaciones aéreas o terrestres de agroquímicos.

#### 1. Parámetros de Control
- **Viento Mínimo Ideal:** $5.0\ \mathrm{km/h}$ (evita condiciones de calma chicha e inversión térmica).
- **Viento Máximo Ideal:** $10.0\ \mathrm{km/h}$.
- **Límite Crítico Operativo:** $15.0\ \mathrm{km/h}$ (parada de máquina por deriva de producto).

#### 2. Regla Registrada
- **`ALERTA_PULVERIZACION_VIENTO`:**
  - *Acción:* Emite nivel `danger` si la velocidad del viento o ráfagas proyectadas superan los $15.0\ \mathrm{km/h}$, o nivel `info/warning` si es inferior a $5.0\ \mathrm{km/h}$. Recomienda medición manual con anemómetro en lote previo a la carga de caldo.

---

### C. Riesgo Térmico y Heladas (`app/services/decision_engine/rules/frost.py`)

- **Umbral de Alerta Preventiva:** Temperatura mínima proyectada a 72 horas $\le 4.0^\circ\mathrm{C}$.
- **Regla `RIESGO_TERMICO_A_VERIFICAR`:**
  - Si $0.0^\circ\mathrm{C} < T_{\min} \le 4.0^\circ\mathrm{C} \rightarrow$ Estado `warning` (Alerta por helada agrometeorológica/superficial).
  - Si $T_{\min} \le 0.0^\circ\mathrm{C} \rightarrow$ Estado `danger` (Helada meteorológica crítica).
  - Recomienda inspeccionar bajíos y estaciones agrometeorológicas locales según la ventana fenológica del cultivo.

---

### D. Soil Floor y Transitabilidad de Caminos (`app/services/decision_engine/rules/trafficability.py`)

- **Regla `RIESGO_DE_PISO_POR_PRECIPITACION`:**
  - *Condición:* Precipitaciones acumuladas a 72 horas $\ge 10.0\ \mathrm{mm}$ o estado de camino rural condicionado.
  - *Recomendación:* Advierte sobre la posible pérdida de sustentación del suelo para el tránsito de cosechadoras y tolvas, y bloquea o condiciona los destinos de flete asociados a caminos de tierra.

---

### E. Motor Climático Multiproveedor (`app/services/weather/`)

EduAgro cuenta con una arquitectura multiproveedor agnóstica:
- **Proveedor Primario:** Google Weather API.
- **Proveedor Fallback:** Open-Meteo API.
- **Consenso Meteorológico:** En lugar de promediar arbitrariamente valores divergentes, el módulo calcula el grado de discrepancia (`disagreement_level`: `low`, `medium`, `high`). Si los proveedores difieren significativamente en lluvias o viento, la confianza del insight se degrada automáticamente a `medium` o `low`, alertando al usuario sobre la incertidumbre.

---

## 📈 3. Lógica Comercial y Mercado de Granos

### A. Cotizaciones e Integración de Mercados (`app/services/mercado.py`)

- **Pizarra Rosario (CAC / BCR) y SAGyP:** Servicio de ingesta automática con fallback en caché y datos demo de respaldo.
- **Conversión Monetaria:** Convierte precios publicados en Pesos Argentinos ($\mathrm{ARS/Tn}$) a Dólares ($\mathrm{USD/Tn}$) utilizando el tipo de cambio comprador Pizarra/CAC o Dólar BNA Oficial.

---

### B. Mercado de Futuros y Commercial Carry (`app/services/decision_engine/rules/commercialization.py`)

Evalúa la conveniencia de diferir la venta mediante contratos a futuro en Matba Rofex.

#### 1. Fórmulas de Carry Comercial
- **Spread Futuro vs. Spot ($\mathrm{USD/Tn}$):**
  $$\text{spread}_{\mathrm{USD/Tn}} = \text{precio\_futuro}_{\mathrm{USD/Tn}} - \text{precio\_spot}_{\mathrm{USD/Tn}}$$

- **Carry Neto Estimado ($\mathrm{USD/Tn}$):**
  $$\text{carry\_neto} = \text{precio\_futuro} - \text{precio\_spot} - \text{costo\_financiero} - \text{almacenaje} - \text{seguro} - \text{merma} - \text{flete\_inc}$$

#### 2. Regla Registrada
- **`FUTURO_FAVORABLE_PARA_FIJACION`:**
  - *Condición:* Spread positivo mayor o igual al umbral fijado ($\mathrm{US\$}\ 4.00\ \mathrm{USD/Tn}$ por defecto).
  - *Insight:* Alerta oportunista de cobertura (`EVALUAR_COBERTURA_FUTURA`), explicitando en la traza que el pase bruto es positivo pero requiriendo validar los costos de inmovilización financiera del grano en stock.

---

### C. Contratos de Arrendamiento Agrícola V1 (`app/services/lease_calculator.py`)

Gestión determinística de alquileres de campo pagaderos en producto (quintales de grano por hectárea).

#### 1. Conversión de Obligación Física
- **Quintales Totales:**
  $$\text{qq\_totales} = \text{superficie\_arrendada}_{\mathrm{ha}} \times \text{alquiler}_{\mathrm{qq/ha}}$$
- **Toneladas Equivalentes ($1\ \mathrm{Tn} = 10\ \mathrm{qq}$):**
  $$\text{toneladas\_equivalentes} = \frac{\text{qq\_totales}}{10}$$
  *Nota:* Las toneladas equivalentes constituyen la fuente única de verdad para la reserva automática en inventario (`CompromisoGrano`).

#### 2. Valorización Monetaria Informativa ($\mathrm{USD}$)
- **Base Rosario:**
  $$\text{precio\_neto}_{\mathrm{USD/Tn}} = \text{precio\_referencia}_{\mathrm{USD/Tn}}$$
  $$\text{valor\_estimado}_{\mathrm{USD}} = \text{toneladas\_equivalentes} \times \text{precio\_neto}$$
- **Base Acopio:**
  $$\text{precio\_neto}_{\mathrm{USD/Tn}} = \text{precio\_referencia}_{\mathrm{USD/Tn}} - \text{flete}_{\mathrm{USD/Tn}} - \text{comision}_{\mathrm{USD/Tn}}$$
  $$\text{valor\_estimado}_{\mathrm{USD}} = \text{toneladas\_equivalentes} \times \text{precio\_neto}$$
  *Control de integridad:* Si en base acopio falta la tarifa de flete o comisión, el cálculo pasa a estado `partial` y no imputa costo cero.

---

## 🚚 4. Logística, Fletes y Cartas de Porte

### A. Economía de Entregas y Net Origin Price (`app/services/decision_engine/rules/freight.py`)

Compara determinísticamente las distintas alternativas de comercialización/destino (puerto, acopio local, industria).

#### 1. Precio Neto Estimado en Origen ($\mathrm{USD/Tn}$)
$$\text{precio\_neto\_origen}_{\mathrm{USD/Tn}} = \text{precio\_ofrecido} - \text{flete} - \text{acondicionamiento} - \text{otros\_costos}$$

#### 2. Matriz de Elegibilidad de Destino
- **`eligible`:** Camino rural en buen estado, cupo confirmado en destino y humedad de grano dentro del límite de recibo directo.
- **`conditionally_eligible`:** Accesible por camino, pero con cupo sin confirmar (`unknown`) o humedad superior a la tolerancia de recepción sin secada.
- **`not_eligible`:** Bloqueado por camino intransitable (`IMPASSABLE`) o planta consumidora sin recepción disponible (`UNAVAILABLE`).
- **`not_evaluable`:** Falta de tarifa de flete o precio ofrecido.

#### 3. Reglas de Ranking Logístico
- **`DESTINO_NETO_MAS_CONVENIENTE`:** Identifica la opción con mayor margen neto en origen e informa la ventaja económica exacta ($\Delta\ \mathrm{USD/Tn}$) respecto al segundo destino elegible.
- **`SIN_DIFERENCIA_NETA_MATERIAL_ENTRE_DESTINOS`:** Se activa si la diferencia entre destinos es menor a $\mathrm{US\$}\ 1.00\ \mathrm{USD/Tn}$, recomendando priorizar el destino más cercano para reducir riesgo logístico.

---

### B. Control de Entregas y Cartas de Porte (`app/services/decision_engine/rules/delivery.py`)

Maneja la trazabilidad operativa desde el pesaje en campo hasta la balanza de destino.

#### 1. Pesaje de Precisión (`Decimal`)
- **Peso Neto Origen ($\mathrm{kg}$):**
  $$\text{peso\_neto\_origen} = \text{peso\_bruto\_origen} - \text{tara}$$
- **Diferencia de Pesaje Destino vs. Origen ($\mathrm{kg}$ y $\%$):**
  $$\text{diferencia\_pesaje}_{\mathrm{kg}} = \text{peso\_recibido\_destino} - \text{peso\_neto\_origen}$$
  $$\text{diferencia\_pesaje}_{\%} = \frac{\text{diferencia\_pesaje}_{\mathrm{kg}}}{\text{peso\_neto\_origen}} \times 100$$

#### 2. Reglas de Control Documental
- **`DIFERENCIA_DE_PESAJE_A_REVISAR`:** Se activa si $|\text{diferencia\_pesaje}| > 1.0\%$ o $> 300\ \mathrm{kg}$, enviando la entrega al panel de reconciliaciones del Dashboard Comercial.
- **`CARGA_SUPERA_CAPACIDAD_REFERENCIA`:** Advierte si la carga neta excede las capacidades teóricas de camión chasis/acoplado ($35.000\ \mathrm{kg}$) o bitren/vulcano ($45.000\ \mathrm{kg}$).
- **`ENTREGA_SIN_CARTA_DE_PORTE`:** Alerta preventivamente cuando un viaje avanza en estado despachado sin número oficial de carta de porte registrado.

---

## 📦 5. Gestión de Stock de Granos e Insumos

### A. Estándar de Stock Comercial 1A/1B/1C (`app/services/stock_service.py`)

Supera las deficiencias de los sistemas tradicionales al desglosar las existencias físicas en 4 saldos concurrentes:

1. **Stock Físico Real ($\mathrm{Tn}$):** Peso real en kilogramos consolidado por partidas en silos propios, silobolsas o acopios.
2. **Stock Reservado ($\mathrm{Tn}$):** Toneladas vinculadas a compromisos comerciales u obligaciones de arrendamiento.
3. **Stock Asignado ($\mathrm{Tn}$):** Toneladas asignadas a entregas logísticas o viajes en tránsito.
4. **Stock Disponible Libre ($\mathrm{Tn}$):**
   $$\text{Stock Disponible Libre} = \text{Stock Físico} - \text{Stock Reservado} - \text{Stock Asignado}$$

*Regla de integridad:* El Dashboard Comercial prohíbe sumar la producción teórica de lotes al stock físico libre disponible para venta.

---

### B. Módulo de Insumos y Abastecimiento V3 (`app/services/insumos_service.py`)

- **Precio Promedio Ponderado Móvil (PPP) Bimoneda:** Mantiene el valor monetario del inventario de agroquímicos, semillas y fertilizantes tanto en USD como en ARS tras cada compra o ajuste.
- **Verificación de Disponibilidad Pre-Labor:** Antes de registrar una labor de campo (ej. pulverización o fertilización), el sistema verifica la disponibilidad física de los productos en el depósito seleccionado. Si el saldo es insuficiente, emite una advertencia bloqueante.
- **Acoplamiento Categórico Estricto:**
  - Semillas $\rightarrow$ Bolsas / kg.
  - Combustibles $\rightarrow$ Litros.
  - Fertilizantes $\rightarrow$ kg / Bolsas.
  - Fitosanitarios $\rightarrow$ Litros / kg / Unidades.
- **Alerta de Punto de Pedido Mínimo:** Dispara notificaciones cuando el stock disponible cae por debajo de la reserva de seguridad configurada (`punto_pedido_minimo`).

---

## 🗺️ 6. Dashboard Comercial Integrado (Consolidación V2)

El servicio `app/services/commercial_dashboard_service.py` consolida la toma de decisiones en un tablero unificado:

```text
+-----------------------------------------------------------------------------------+
|                           DASHBOARD COMERCIAL EDUAGRO                            |
+-----------------------------------------------------------------------------------+
|  STOCK FÍSICO      STOCK RESERVADO      STOCK ASIGNADO      STOCK DISPONIBLE LIBRE|
|  1.250,00 Tn       400,00 Tn (Arrend.)  150,00 Tn (Viajes)  700,00 Tn Libre       |
+-----------------------------------------------------------------------------------+
|  COBERTURA COMERCIAL: 44,0% (Ventas Fijas + Reservas / Stock Físico)               |
+-----------------------------------------------------------------------------------+
|  PRIORIDADES CRÍTICAS Y ALERTAS OPERATIVAS:                                      |
|  • [CRÍTICO] Diferencia de pesaje en Entrega ENT-2026-081 (-450 kg vs destino)    |
|  • [WARNING] Compromiso Arrendamiento "Don Pedro" vence en 12 días sin reserva   |
|  • [INFO] Pase de futuros favorable en Soja (+US$ 12,00 USD/Tn en Matba)          |
+-----------------------------------------------------------------------------------+
|  UBICACIONES Y CUSTODIA:                                                          |
|  • EN CAMPO: Silobolsa Lote 4 (450 Tn) | Silo Planta (300 Tn)                    |
|  • EN CUSTODIA: Acopio AFA Maciel (500 Tn)                                        |
+-----------------------------------------------------------------------------------+
```

---

## 🎯 7. Recomendaciones Estratégicas para el Socio Agrónomo (Roadmap Agronómico)

Como resultado de esta auditoría, identificamos las siguientes oportunidades para potenciar el módulo agronómico de EduAgro en conjunto con el nuevo equipo técnico:

1. **Incorporación de la Ecuación Térmico-Higrométrica ($\Delta T$):**
   - *Estado actual:* La regla de pulverización evalúa la velocidad del viento.
   - *Mejora propuesta:* Integrar el cálculo de Delta T ($\Delta T = T_{\text{seca}} - T_{\text{húmeda}}$) derivado de temperatura y humedad relativa para alertar sobre la evaporación de gotas finas ($\Delta T > 8^\circ\mathrm{C}$) o inversión térmica ($\Delta T < 2^\circ\mathrm{C}$).
2. **Balance Hídrico del Suelo y Agua Útil por Perfil:**
   - *Estado actual:* El módulo de humedad evalúa lluvias a 72h.
   - *Mejora propuesta:* Incorporar la estimación del Agua Útil ($AU\%$) acumulada hasta $1\ \mathrm{m}$ de profundidad según la capacidad de campo y punto de marchitez permanente del tipo de suelo del campo.
3. **Modelos de Grados Días Acumulados (GDD / Fenología):**
   - *Estado actual:* El estado del cultivo se carga manualmente.
   - *Mejora propuesta:* Calcular automáticamente la suma de Grados Días Acumulados ($GDD = \frac{T_{\max} + T_{\min}}{2} - T_{\text{base}}$) según el hibrido/variedad para predecir la fecha estimada de madurez fisiológica y cosecha.
4. **Modelos Predictivos de Alertas Fitosanitarias (Tizón, Roya, Mancha Marrón):**
   - *Mejora propuesta:* Integrar módulos de horas foliares mojadas (Leaf Wetness Duration) cruzadas con temperatura media para generar un índice de riesgo de infección fúngica.

---

## 🔍 Conclusión de Auditoría

El proyecto **EduAgro** cuenta con una base sólida, determinística y profesionalmente estructurada para la gestión agronómica, logística y comercial de empresas agrícolas argentinas. La separación estricta entre calculadoras puras, políticas jerárquicas y modelos de datos garantiza que las decisiones no dependan de "cajas negras" impredecibles, sino de reglas claras, auditables y adaptables a las condiciones reales de cada establecimiento.
