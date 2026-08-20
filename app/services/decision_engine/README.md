# 🧠 Motor de Decisiones Determinístico, Explicable y Trazable (EduAgro v2.0)

Núcleo determinístico de apoyo a decisiones agrometeorológicas, financieras y operativas para el sector agropecuario argentino.

---

## 🏗️ Arquitectura y Principios de Diseño

El motor está ubicado en `app/services/decision_engine/` y se rige por cinco principios innegociables:

1. **Determinístico y Reproducible:** Dadas las mismas entradas y políticas, el motor siempre produce exactamente la misma salida sin aleatoriedad.
2. **Cero Cajas Negras (Explicable):** Cada recomendación emite sus variables determinantes (`drivers`), compensaciones (`tradeoffs`), códigos de razón (`reason_codes`) y nivel de confianza.
3. **Cero Código Dinámico en DB:** Prohíbe `eval`, `exec` o scripts de Python almacenados en base de datos.
4. **Funciones Puras (Sin I/O):** Las calculadoras y reglas no realizan consultas HTTP, no acceden a la base de datos ni leen la hora global del sistema.
5. **Transparencia en Datos Faltantes:** Nunca convierte `None` a `0.0`. Si falta información, el motor registra datos faltantes en la traza y emite avisos de calidad de datos.

```text
app/services/decision_engine/
├── __init__.py                # Exportación del motor v2 y fachada legacy
├── models.py                  # Esquemas Pydantic v2 (DecisionContext, DecisionResult, DecisionTrace, etc.)
├── policy.py                  # Resolutor jerárquico de políticas (7 capas de precedencia)
├── policy_defaults.py         # SYSTEM_BASE_DECISION_POLICY ("2.0.0")
├── registry.py                # RuleRegistry desacoplado por dominio
├── trace.py                   # Generador de trazas inmutables y sanitizadas
├── context_builder.py         # Constructor de DecisionContext desde legacy o Pydantic
├── compatibility.py           # Transformador de DecisionResult a lista legacy de insights
├── engine.py                  # Orquestador sincrónico principal (DecisionEngine)
├── README.md                  # Documentación técnica del motor
├── calculators/               # Calculadoras puras desacopladas
│   ├── __init__.py
│   ├── drying.py              # Cálculo de exceso de humedad y costo de secada
│   ├── trafficability.py      # Evaluación de piso por precipitaciones acumuladas
│   ├── harvest_risk.py        # Riesgo de calidad y pérdida en cosecha
│   ├── commercial.py          # Pase de futuros y carry neto estimado
│   ├── spraying.py            # Condiciones de viento para fitosanitarios
│   ├── freight.py             # Precio neto en origen descontando flete y reacondicionamiento (Decimal)
│   └── delivery_economics.py  # Elegibilidad de destino y ranking por valor neto
└── rules/                     # Reglas determinísticas por dominio
    ├── __init__.py
    ├── base.py                # Protocolo abstracto DecisionRule
    ├── data_quality.py        # Reglas DATOS_INSUFICIENTES_*, CLIMA_NO_DISPONIBLE
    ├── harvest.py             # HUMEDAD_ALTA_Y_VENTANA_SECA, HUMEDAD_ALTA_Y_LLUVIA_PROXIMA
    ├── commercialization.py   # FUTURO_FAVORABLE_PARA_FIJACION
    ├── trafficability.py      # RIESGO_DE_PISO_POR_PRECIPITACION
    ├── spraying.py            # ALERTA_PULVERIZACION_VIENTO
    ├── frost.py               # RIESGO_TERMICO_A_VERIFICAR
    └── freight.py             # Reglas del dominio de flete (DESTINO_NETO_MAS_CONVENIENTE, etc.)
```

---

## 🚚 Dominio de Flete y Economía de Entregas (`freight`)

El dominio `freight` permite comparar determinísticamente opciones de entrega comercial para un lote/grano.

### Propósito Acotado
- Compara precio offered por comprador/acopio menos flete, acondicionamiento y otros costos.
- **Fórmula de Precio Neto en Origen (USD/Tn):**
  $$\text{precio\_neto\_origen} = \text{precio\_ofrecido} - \text{flete} - \text{acondicionamiento} - \text{otros\_costos}$$
- **Estados de Elegibilidad:**
  - `eligible`: Accesible por camino, cupo confirmado y dentro de límites de humedad.
  - `conditionally_eligible`: Accesible pero con cupo sin confirmar (`unknown`) o humedad superior al límite de recibo.
  - `not_eligible`: Bloqueado por camino intransitable (`impassable`) o recepción no disponible (`unavailable`).
  - `not_evaluable`: Falta de datos requeridos para evaluar.
- **Campos Contextuales Opcionales:**
  - `cultivo`: Representa el cultivo aplicable a la cotización (maíz, soja, trigo, sorgo, no especificado).
  - `condicion_precio`: Condición comercial del precio (`disponible_spot`, `a_fijar`, `contrato`, `futuro`, `a_confirmar`). Al comparar cotizaciones con distintas condiciones de precio, se genera una advertencia informativa no bloqueante.
  - `distancia_estimada_km`: Distancia estimada de referencia en km. No modifica la tarifa de flete automáticamente.
  - `detalle_cupo_turno`: Detalle de cupo o turno informado por el destino (ej. "2 camiones hoy").
  - `humedad_max_recepcion_pct`: Humedad máxima aceptada por el destino. Es opcional y sin defaults precargados.
- **Inactividad por Defecto:** Si `context.delivery_options` está vacío (`[]`), el motor omite la generación de alertas de flete.

### Ejemplo de JSON de Entrada en `DecisionContext`:
```json
{
  "cultivo": "maiz",
  "harvest": { "humedad_grano_pct": 14.5 },
  "delivery_options": [
    {
      "destination_name": "Puerto San Lorenzo",
      "price_usd_tn": 220.00,
      "freight_usd_tn": 15.00,
      "conditioning_cost_usd_tn": 0.00,
      "other_costs_usd_tn": 0.00,
      "receiving_confirmed": "available",
      "road_status": "good"
    },
    {
      "destination_name": "Acopio Local",
      "price_usd_tn": 200.00,
      "freight_usd_tn": 5.00,
      "conditioning_cost_usd_tn": 0.00,
      "other_costs_usd_tn": 0.00,
      "receiving_confirmed": "available",
      "road_status": "good"
    }
  ]
}
```

### Resultado Generado (`DecisionInsight`):
```json
{
  "codigo": "DESTINO_NETO_MAS_CONVENIENTE",
  "nivel": "success",
  "titulo": "Destino Sugerido: Puerto San Lorenzo (+US$ 10,00 USD/Tn Neto)",
  "mensaje": "La alternativa con mayor valor neto estimado en origen es Puerto San Lorenzo (US$ 205,00 USD/Tn neto), ofreciendo una ventaja económica de +US$ 10,00 USD/Tn respecto a la segunda opción elegible.",
  "datos": {
    "destino_optimo": "Puerto San Lorenzo",
    "neto_origen_usd_tn": 205.00,
    "diferencia_ventaja_usd_tn": 10.00,
    "diferencia_minima_material_usd": 1.00
  },
  "domain": "freight",
  "accion_recomendada": "EVALUAR_DESTINO_NETO",
  "confidence": "high"
}
```

---

## 📦 Dominio de Entregas y Cartas de Porte (`deliveries`)

El dominio `deliveries` gestiona la trazabilidad operativa y agromercantil de viajes y cartas de porte.

### Principios y Funcionalidad:
- **Diferencia entre Cotización de Flete, Entrega y Carta de Porte:**
  - `FreightQuote`: Cotización de tarifa y condiciones por comprador/destino.
  - `GrainDelivery`: Operación/viaje comercial (con seguimiento interno `ENT-YYYYMMDD-XXXX`).
  - `GrainWaybill`: Movimiento físico / pesaje (con número opcional de carta de porte).
- **Fórmulas de Pesaje Puras (`Decimal`):**
  $$\text{peso\_neto\_origen} = \text{peso\_bruto\_origen} - \text{tara}$$
  $$\text{diferencia\_pesaje} = \text{peso\_recibido\_destino} - \text{peso\_neto\_origen}$$
- **Capacidades Referenciales Configurables:**
  - `normal` (35.000 kg por defecto) y `vulcano` (45.000 kg por defecto). Son referencias operativas editables, nunca sustituyen el peso real documentado.
- **Trazabilidad y Documentación Pendiente:**
  - La carta de porte no es obligatoria para planificar o registrar viajes en etapas tempranas.
  - El sistema muestra recordatorios visuales y reglas determinísticas de "documentación pendiente" cuando la entrega avanza sin número de carta de porte registrado.
- **Reglas Determinísticas Registradas:**
  - `ENTREGA_SIN_CARTA_DE_PORTE`
  - `CARTA_PORTE_SIN_PESO_ORIGEN`
  - `CARTA_PORTE_SIN_PESO_DESTINO`
  - `DIFERENCIA_DE_PESAJE_A_REVISAR`
  - `CARGA_SUPERA_CAPACIDAD_REFERENCIA`
  - `FLETE_ESTIMADO_POR_ENTREGA`
  - `ENTREGA_ASOCIADA_A_COMPROMISO`
  - `ENTREGA_CON_DOCUMENTACION_PENDIENTE`

---

## 🏛️ Orden de Resoluciones de Política Jerárquica

La política efectiva final se construye aplicando una fusión inmutable de capas según este orden estricto de precedencia:

$$\text{run\_override} > \text{lot} > \text{field} > \text{family\_client} > \text{organization} > \text{agronomic\_template} > \text{system\_base}$$

Cada valor resuelto retiene su procedencia exacta (`EffectivePolicyValue`), especificando `source_scope`, `source_id`, `policy_id` y `policy_version`.

---

## 🧪 Ejecución de Pruebas Unitarias

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_freight_domain.py tests/test_decision_engine.py tests/test_weather_service.py -v
```
