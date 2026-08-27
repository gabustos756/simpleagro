# 🌾 EduAgro - Manual Funcional de Módulos, Interconexiones y Reglas del Agente

**Destinatario:** Socio Estratégico & Equipo de Agronomía  
**Ámbito:** Arquitectura Funcional de Negocio, Conexión de Módulos y Agente Inteligente  
**Fecha:** 26 de Agosto de 2026  
**Documento Generado:** `docs/audits/MANUAL_FUNCIONAL_MODULOS_Y_REGLAS_EDUAGRO.pdf` y `.md`  

---

## 🏛️ 1. Estructura de Módulos Funcionales (Qué guarda la aplicación)

EduAgro organiza la gestión de la empresa agropecuaria en **módulos funcionales desacoplados**, eliminando la complejidad técnica para centrarse exclusivamente en la operativa y estrategia del productor.

| Módulo Funcional | Información y Objetos de Negocio Almacenados |
| :--- | :--- |
| **1. Lotes y Producción Agrícola** | Establecimientos (campos), lotes productivos con su delimitación geográfica, superficie cultivable (ha), historia de cultivos por campaña (soja, maíz, trigo, sorgo), rendimientos estimados ($qq/ha$) y rendimientos reales post-cosecha. |
| **2. Stock Físico y Acopios (Estándar 1A/1B/1C)** | Ubicaciones físicas de almacenamiento (silos propios, silobolsas en campo, celdas, acopios y cooperativas en custodia). Partidas trazables de grano con fecha de cosecha, lote de origen, tipo de grano, peso físico real ($\mathrm{kg}$), mediciones de calidad (humedad \%, temperatura) y movimientos de inventario. |
| **3. Comercial y Contratos de Venta** | Contratos comerciales de venta de grano (precios fijos, ventas "A Fijar" Pizarra), compromisos comerciales de entrega, compradores/puertos consignatarios, fechas de vencimiento y volumen pactado en toneladas. |
| **4. Arrendamientos Agrícolas** | Contratos de alquiler de campo pagaderos en producto ($qq/ha$), conversión a quintales totales y toneladas equivalentes ($1\ \mathrm{Tn} = 10\ \mathrm{qq}$), y valorización en USD según base Rosario directo o Acopio (deduciendo flete y comisión). |
| **5. Logística, Fletes y Cartas de Porte** | Tarifarios de fletes por transportista y destino, estado de transitabilidad de caminos rurales (transitables/intransitables), turnos y cupos asignados en puerto, cartas de porte oficiales, validez de pesaje de origen (bruto y tara) y pesaje en balanza de destino. |
| **6. Agrometeorología y Clima** | Pronósticos agrometeorológicos geolocalizados por campo (Google Weather y Open-Meteo), lluvia acumulada proyectada a 24h/72h ($mm$), velocidad máxima de viento y ráfagas ($km/h$), temperatura mínima/máxima ($^\circ C$) y nivel de coincidencia entre fuentes climáticas. |
| **7. Insumos y Depósito** | Catálogo de semillas, fitosanitarios, fertilizantes, combustibles y repuestos. Saldo por depósito, Precio Promedio Ponderado Móvil (PPP en USD/ARS), historial de compras, transferencias y reservas para labores agrícolas. |

---

## 🔗 2. Interconexión e Integración de Módulos (Cómo se conectan)

Ningún módulo funciona como una isla. La información fluye automáticamente entre ellos para reflejar la realidad del establecimiento:

1. **De Cosecha a Stock Físico:** Al registrar la cosecha de un lote, la plataforma crea una *Partida de Stock Físico Real* en silobolsa o planta de acopio, registrando sus toneladas exactas y humedad inicial.
2. **Subdivisión de Stock (Estándar 1A/1B/1C):** El stock físico se divide dinámicamente en 4 saldos:
   - **Stock Físico Real:** Peso real de grano almacenado.
   - **Stock Reservado:** Toneladas apartadas para pagar alquileres de campo o cumplir contratos de venta.
   - **Stock Asignado:** Toneladas asignadas a camiones despachados.
   - **Stock Disponible Libre:** Grano líquido disponible para capturar oportunidades de mercado ($\text{Físico} - \text{Reservado} - \text{Asignado}$).
3. **Clima + Stock Físico & Logística:** Si el módulo climático pronostica precipitaciones importantes a 72h, el módulo de logística evalúa si los caminos rurales de tierra del campo perderán sustentación, alertando que el grano en silobolsa quedará bloqueado temporalmente.
4. **Mercado de Granos + Fletes $\rightarrow$ Precio Neto en Origen:** Resta al precio ofrecido en puerto la tarifa del flete, el costo de secada y las comisiones, calculando el valor neto real del grano en la tranquera del campo.
5. **Insumos + Productivo:** Al programar una pulverización o siembra, el módulo de insumos verifica automáticamente la disponibilidad en el depósito antes de autorizar la orden de trabajo.

---

## 🧠 3. Razonamiento del Agente Inteligente (Cómo calcula sus decisiones)

El Agente de EduAgro opera de forma **100% determinística y explicable**. No genera respuestas aleatorias ni utiliza modelos de texto impredecibles para calcular valores. Su proceso de razonamiento consta de 5 etapas:

1. **Consolidación del Contexto:** El agente reúne la foto completa de la empresa (humedad del grano, clima a 72h, precios spot/futuros, tarifas de flete, stock libre y contratos por vencer).
2. **Ajuste de Umbrales (Política):** Aplica las preferencias del productor o la zona agronómica (ej. viento máximo para aplicar o prima mínima deseada en futuros).
3. **Calculadoras Matemáticas Puramente Determinísticas:** Ejecuta los modelos numéricos de costo de secada, precio neto por destino, desvío de balanza entre origen y destino, y pase de futuros (carry comercial).
4. **Evaluación de Reglas de Negocio:** Contrasta los resultados contra el catálogo de reglas agronómicas, comerciales y logísticas.
5. **Emisión de Recomendaciones Trazables:** Genera consejos prácticos ordenados por severidad (Crítica, Advertencia, Información, Éxito) indicando el motivo, las variables determinantes y la acción sugerida.

---

## ⚙️ 4. Catálogo de Reglas y Escenarios del Agente

### 4.1. Reglas del Agente Comercial (`comercial_rules.py`)

| Código de Regla | Nivel | Umbral / Disparador | Razonamiento y Escenario del Agente |
| :--- | :--- | :--- | :--- |
| **`COBERTURA_BAJA`** | **Warning** | Cobertura $< 25\%$ de la producción. | El productor tiene la mayor parte de su cosecha expuesta a la volatilidad de precios. El agente sugiere evaluar fijaciones o coberturas para defender el margen. |
| **`COBERTURA_MEDIA`** | **Info** | Cobertura entre $25\%$ y $60\%$. | Posición comercial equilibrada. Existe un nivel de protección aceptable conservando volumen libre para capturar subas de mercado. |
| **`COBERTURA_ALTA`** | **Success** | Cobertura $\ge 60\%$ de la cosecha. | Posición fuertemente protegida contra caídas de mercado mediante ventas fijas y reservas comerciales firmes. |
| **`EXPOSICION_A_FIJAR_ELEVADA`** | **Warning** | Ventas "A Fijar" $\ge 15\%$ de la cosecha. | Alerta que un volumen importante de granos ya fue entregado sin precio firme, estando expuesto a las variaciones de la Pizarra. |
| **`CARGA_COMPROMISOS_ELEVADA`** | **Info** | Compromisos por alquiler o insumos $\ge 30\%$ de la cosecha. | Identifica la porción de grano retenida para cancelar obligaciones contractuales que no aportará flujo de caja líquido neto. |
| **`CONCENTRACION_SILO_BOLSA`** | **Info** | Stock en silobolsa $\ge 70\%$ del stock total. | Alerta la alta concentración de existencias en el campo, recomendando controles periódicos de humedad y roturas de bolsa. |
| **`VALORIZACION_STOCK_LIBRE`** | **Success** | Valor de stock libre $\ge \mathrm{US\$}\ 10.000$. | Informa el activo comercial líquido disponible estimado a la cotización Pizarra Rosario para oportuna toma de decisiones de venta. |

---

### 4.2. Reglas Agronómicas, Meteorológicas y Logísticas (`decision_rules` / `decision_engine`)

| Código de Regla | Nivel | Escenario / Condición Disparadora | Conclusión del Agente y Recomendación Operativa |
| :--- | :--- | :--- | :--- |
| **`HUMEDAD_ALTA_Y_VENTANA_SECA`** | **Warning** | Humedad de grano $>$ base comercial ($>14.5\%$ en maíz) AND lluvia a 72h $< 10\ \mathrm{mm}$. | **Esperar secado natural en pie.** No hay riesgo inminente de lluvia y se evita pagar costo de secada ($\approx \mathrm{US\$}\ 2.50/\mathrm{Tn}/\text{punto}$). |
| **`HUMEDAD_ALTA_Y_LLUVIA_PROXIMA`** | **Danger** | Humedad de grano $>$ base comercial AND lluvia a 72h $\ge 10\ \mathrm{mm}$. | **Cosechar e ingresar a secadora inmediatamente.** El riesgo de vuelco, brotado o pérdida de piso supera el costo económico de secar el grano. |
| **`COSTO_SECADA_ELEVADO`** | **Info** | Costo de secada $\ge 3\%$ del precio spot del grano. | Alerta revisar la tabla tarifaria de mermas del acopio/puerto antes de enviar el camión. |
| **`ALERTA_PULVERIZACION_VIENTO`** | **Danger / Info** | Viento o ráfagas fuera del rango óptimo ($5-10\ \mathrm{km/h}$) o $> 15\ \mathrm{km/h}$. | **Suspender o extremar precauciones.** Viento $>15\ \mathrm{km/h}$ provoca deriva de producto; viento $<5\ \mathrm{km/h}$ genera riesgo de inversión térmica. |
| **`RIESGO_TERMICO_A_VERIFICAR`** | **Warning / Danger** | Temperatura mínima a 72h $\le 4.0^\circ\mathrm{C}$. | Alerta preventivo por helada. Recomienda inspeccionar bajíos y estaciones agrometeorológicas según la etapa fenológica del cultivo. |
| **`RIESGO_DE_PISO_POR_PRECIPITACION`** | **Warning / Danger** | Lluvia proyectada a 72h $\ge 10\ \mathrm{mm}$. | Alerta pérdida de sustentación en caminos rurales de tierra. Puede bloquear el ingreso de cosechadoras y camiones al lote. |
| **`DESTINO_NETO_MAS_CONVENIENTE`** | **Success** | Comparación de destinos donde el más conveniente saca $\ge \mathrm{US\$}\ 1.00/\mathrm{Tn}$ de ventaja. | Recomienda el puerto o acopio con mayor *Precio Neto en Origen* (descontando flete y secada), detallando la ventaja económica por tonelada. |
| **`DIFERENCIA_DE_PESAJE_A_REVISAR`** | **Danger** | Diferencia balanza destino vs origen $> 1.0\%$ o $> 300\ \mathrm{kg}$. | Detiene la transacción y la envía a reconciliación explícita para auditar posibles mermas o pérdidas en el trayecto. |
| **`FUTURO_FAVORABLE_PARA_FIJACION`** | **Success** | Cotización a futuro Matba Rofex supera al spot por $\ge \mathrm{US\$}\ 4.00/\mathrm{Tn}$. | Recomienda analizar la cobertura a futuro comparando el pase bruto contra los costos de almacenaje e inmovilización financiera del grano. |

---

*Manual elaborado para la presentación comercial y agronómica de EduAgro v2.0 / v3.0.*
