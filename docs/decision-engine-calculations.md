# 🧠 Especificación Técnica de Fórmulas, Reglas y Parámetros del Motor de Decisiones

**Proyecto:** EduAgro  
**Módulo:** Motor de Decisiones Determinístico (`app/services/decision_engine/`)  
**Versión del Documento:** `2.1.0`  
**Estado:** Documentación Técnica Interna Versionada  

---

## 1. Alcance y Principios de Diseño

El motor de decisiones de EduAgro es un núcleo puramente determinístico, trazable y explicable diseñado para respaldar la toma de decisiones agrometeorológicas, financieras y logístico-comerciales en el sector agropecuario argentino.

### Principios Innegociables:
1. **Determinismo Absoluto:** Dadas las mismas entradas (`DecisionContext`) y las mismas políticas efectivas (`EffectivePolicyValue`), el motor produce exactamente el mismo resultado (`DecisionResult`), sin variabilidad aleatoria.
2. **Cero Cajas Negras e Inteligencia No Probabilística:** No se emplean modelos de aprendizaje automático (ML), modelos de lenguaje (LLM) ni funciones no determinísticas (`eval`, `exec`, scripts dinámicos en base de datos) para generar recomendaciones.
3. **Deslinde de Asesoramiento Definitivo:** Las decisiones emitidas por el motor son herramientas de apoyo y evaluación técnica de referencia. No constituyen asesoramiento agronómico, financiero, legal o fiscal vinculante.
4. **Preservación Estricta de Datos Faltantes:** Un dato no disponible (`None`) nunca se convierte implícitamente a `0.0`. La falta de datos genera estados explícitos (`missing`, `not_evaluable`, `partial`) y activa avisos de calidad de datos.
5. **Transparencia en Traza:** Cada evaluación genera una traza inmutable (`DecisionTrace`) que documenta qué reglas fueron evaluadas, cuáles se activaron, las variables determinantes (`drivers`), las compensaciones (`tradeoffs`) y la procedencia exacta de la política aplicada.

---

## 2. Arquitectura de Datos y Políticas

### Esquemas Clave (`app/services/decision_engine/models.py`)
- **`DecisionContext`:** Contenedor inmutable de entradas (datos de mercado, cosecha, logística, pulverización, clima, opciones de flete `delivery_options` y entregas `deliveries`).
- **`EffectivePolicyValue`:** Encapsula el valor efectivo final de un parámetro de política junto con su procedencia explícita (`source_scope`, `source_id`, `policy_id`, `policy_version`).
- **`DecisionInsight`:** Recomendación estructurada generada por una regla activada (`codigo`, `nivel`, `titulo`, `mensaje`, `datos`, `accion_recomendada`, `confidence`).
- **`DecisionTrace`:** Registro completo sanitizado para auditoría (`evaluations`, `effective_policy`, `warnings`).
- **`DecisionResult`:** Resultado final retornado por el orquestador sincrónico `DecisionEngine`.

### Jerarquía de Precedencia de Políticas (7 Capas)
La política efectiva se resuelve fusionando inmutablemente las capas de política según el siguiente orden estricto de precedencia:

$$\text{run\_override} > \text{lot} > \text{field} > \text{family\_client} > \text{organization} > \text{agronomic\_template} > \text{system\_base}$$

### Estados de Calidad y Clima Multiproveedor
- **Estados de Calidad:** `available`, `missing`, `invalid`, `estimated`, `live`, `cached`, `stale_cached`, `partial`, `unavailable`.
- **Clima Multiproveedor (`app/services/weather/`):** Coexisten Google Weather API (proveedor configurable) y Open-Meteo (fallback). El servicio normaliza snapshots, gestiona caché y detecta discrepancias de precipitación/viento entre proveedores sin promediar arbitrariamente datos divergentes.

---

## 3. Convenciones, Unidades y Tipos Numéricos

### Unidades Estándar:
- **Moneda:** Dólares Estadounidenses (USD).
- **Precio y Costo Comercial:** USD por Tonelada ($\mathrm{USD/Tn}$).
- **Masa / Peso:** Kilogramos ($\mathrm{kg}$) y Toneladas ($\mathrm{Tn}$), donde $1\ \mathrm{Tn} = 1000\ \mathrm{kg}$.
- **Humedad del Grano:** Porcentaje ($\%$).
- **Precipitación Pluvial:** Milímetros ($\mathrm{mm}$).
- **Velocidad del Viento:** Kilómetros por Hora ($\mathrm{km/h}$).
- **Temperatura:** Grados Celsius ($\mathrm{^\circ C}$).
- **Distancia:** Kilómetros ($\mathrm{km}$); representa un dato de referencia contextual que no modifica la tarifa de flete automáticamente en la versión actual.

### Precisión Numérica:
- Toda la aritmética financiera, monetaria y de pesaje se ejecuta utilizando la clase `Decimal` de Python para prevenir errores de redondeo en punto flotante (`float`).
- Los redondeos se aplican únicamente en la capa de serialización y presentación visual (UI/templates), conservando la precisión exacta dentro de las calculadoras puras.

---

## 4. Fórmulas Implementadas

### A. Secada y Reacondicionamiento de Grano

#### 1. Exceso de Humedad ($\%$)
\[
exceso\_humedad = \max\left(0,\, humedad\_grano - humedad\_base\_comercial\right)
\]
- **Variables:**
  - $humedad\_grano$ ($\%$): Humedad medida del grano cosechado.
  - $humedad\_base\_comercial$ ($\%$): Humedad base libre de mermas según tarifa (ej. 14,5% en maíz, 13,5% en soja).
- **Precondiciones:** Ambas variables deben estar presentes. Si falta alguna, no se calcula.
- **Resultado:** Porcentaje de humedad en exceso a secar.

#### 2. Costo de Secada ($\mathrm{USD/Tn}$)
\[
costo\_secada_{\mathrm{USD/Tn}} = exceso\_humedad \times costo\_secada\_por\_punto_{\mathrm{USD/Tn}}
\]
- **Variables:**
  - $costo\_secada\_por\_punto_{\mathrm{USD/Tn}}$: Tarifa en USD por cada punto porcentual de humedad en exceso (default: US$ 2,50/Tn).
- **Resultado:** Costo total estimado de secada en origen.

#### 3. Impacto de Secada sobre Precio Spot ($\%$)
\[
impacto\_secada_{\%} = \frac{costo\_secada_{\mathrm{USD/Tn}}}{precio\_spot_{\mathrm{USD/Tn}}} \times 100
\]
- **Consumidores:** `HumedadAltaVentanaSecaRule`, `CostoSecadaElevadoRule`.

---

### B. Mercado y Diferimiento Comercial (Commercial Carry)

#### 1. Spread Futuro vs Spot ($\mathrm{USD/Tn}$)
\[
spread\_futuro_{\mathrm{USD/Tn}} = precio\_futuro_{\mathrm{USD/Tn}} - precio\_spot_{\mathrm{USD/Tn}}
\]

#### 2. Carry Neto Estimado ($\mathrm{USD/Tn}$)
\[
carry\_neto_{\mathrm{USD/Tn}} = precio\_futuro - precio\_spot - costo\_financiero - almacenaje - seguro - merma - flete\_inc - riesgo\_calidad - cobertura
\]
- **Aclaración de Estado:** Varias componentes del carry completo (como seguro o riesgo de calidad) se encuentran en estado parcial/stub. Por ello, la regla `FuturoFavorableFijacionRule` advierte que un spread positivo entre futuro y spot no garantiza un carry neto favorable tras descontar los costos totales de almacenamiento y financiamiento.

---

### C. Flete y Economía de Entregas Comercial

#### 1. Precio Neto Estimado en Origen ($\mathrm{USD/Tn}$)
\[
precio\_neto\_origen_{\mathrm{USD/Tn}} = precio\_ofrecido - flete - acondicionamiento - otros\_costos
\]
- **Variables:**
  - $precio\_ofrecido$ ($\mathrm{USD/Tn}$): Precio bruto ofrecido por el comprador/puerto.
  - $flete$ ($\mathrm{USD/Tn}$): Tarifa de flete en camión hasta el destino.
  - $acondicionamiento$ ($\mathrm{USD/Tn}$): Costo estimado de secada o zarandeo.
  - $otros\_costos$ ($\mathrm{USD/Tn}$): Comisiones, paritaria u otros gastos comerciales.
- **Precondición:** $precio\_ofrecido$ y $flete$ no deben ser nulos. Si falta $flete$, la calculadora marca `is_net_price_fully_calculated = False` y no inventa un precio neto.

#### 2. Evaluación de Elegibilidad de Destino
Un destino se clasifica en uno de cuatro estados determinísticos:
- `eligible`: Camino bueno/condicionado, cupo disponible y humedad dentro del límite aceptado por el destino.
- `conditionally_eligible`: Camino transitable pero con cupo por confirmar (`unknown`) o humedad superior al límite de recibo.
- `not_eligible`: Bloqueado por camino intransitable (`impassable`) o recepción no disponible (`unavailable`).
- `not_evaluable`: Falta de datos críticos para evaluar.

#### 3. Diferencia Neta Material entre Destinos ($\mathrm{USD/Tn}$)
\[
diferencia\_neta = precio\_neto\_optimo - precio\_neto\_segundo
\]
- Si $diferencia\_neta < diferencia\_neta\_minima\_relevante\_usd\_tn$ (default: US$ 1,00/Tn), se emite la regla `SinDiferenciaNetaMaterialEntreDestinosRule`.

---

### D. Entrega y Pesaje de Granos

#### 1. Peso Neto de Origen ($\mathrm{kg}$)
\[
peso\_neto\_origen_{\mathrm{kg}} = peso\_bruto\_origen_{\mathrm{kg}} - tara_{\mathrm{kg}}
\]
- **Precondición:** $peso\_bruto\_origen_{\mathrm{kg}} \ge tara_{\mathrm{kg}}$. Si el bruto es menor a la tara, la calculadora rechaza el cálculo y retorna un aviso de pesaje inválido.

#### 2. Diferencia de Pesaje Destino vs Origen ($\mathrm{kg}$ y $\%$)
\[
diferencia\_pesaje_{\mathrm{kg}} = peso\_recibido\_destino_{\mathrm{kg}} - peso\_neto\_origen_{\mathrm{kg}}
\]
\[
diferencia\_pesaje_{\%} = \frac{diferencia\_pesaje_{\mathrm{kg}}}{peso\_neto\_origen_{\mathrm{kg}}} \times 100
\]
- **Evaluación:** Evaluada únicamente cuando existen ambos pesajes reales. Si la diferencia absoluta supera `weight_difference_review_pct` (default: 1,0%) o `weight_difference_review_kg` (default: 300 kg), se activa la regla `DIFERENCIA_DE_PESAJE_A_REVISAR`.

#### 3. Costo Estimado de Flete por Entrega ($\mathrm{USD}$)
\[
flete\_estimado_{\mathrm{USD}} = \frac{peso\_base_{\mathrm{kg}}}{1000} \times tarifa\_flete_{\mathrm{USD/Tn}}
\]
- **Prioridad de Peso Base:**
  1. Peso recibido en destino ($peso\_recibido\_destino_{\mathrm{kg}}$) $\rightarrow$ Flete Definitivo.
  2. Peso neto en origen ($peso\_neto\_origen_{\mathrm{kg}}$) $\rightarrow$ Flete Estimado.
  3. Si faltan ambos o la tarifa, no se calcula monto.

#### 4. Capacidades Referenciales de Camión
- `normal`: 35.000 kg (referencia operativa editable).
- `vulcano`: 45.000 kg (referencia operativa editable).
- *Aclaración:* La capacidad de referencia sirve exclusivamente para emitir alertas preventivas de carga sobre referencia (`CARGA_SUPERA_CAPACIDAD_REFERENCIA`) y jamás sustituye el pesaje real documentado en balanza.

---

### E. Compromisos Comerciales

#### Saldo Estimado de Compromiso ($\mathrm{Tn}$) — *[Diseño Previsto; no implementado con mutación automática]*
\[
saldo\_compromiso_{\mathrm{Tn}} = toneladas\_comprometidas_{\mathrm{Tn}} - toneladas\_entregadas_{\mathrm{Tn}}
\]
- **Estado Actual:** En la versión V1, la regla `ENTREGA_ASOCIADA_A_COMPROMISO` informa la imputación comercial y las toneladas planificadas de la entrega sin descontar ni alterar automáticamente los saldos del compromiso.

---

## 5. Tabla Completa de Reglas Registradas

| Dominio | Código de Regla | Inputs Requeridos | Resultado / Acción Recomendada | Estado de Madurez |
| :--- | :--- | :--- | :--- | :--- |
| `data_quality` | `CLIMA_NO_DISPONIBLE` | `weather.provider_status` | `VERIFICAR_CONEXION_CLIMA` | Implementada y activa |
| `data_quality` | `ALTA_INCERTIDUMBRE_METEOROLOGICA` | `weather.disagreement_level` | `VERIFICAR_EN_CAMPO` | Implementada y activa |
| `data_quality` | `DATOS_INSUFICIENTES_PARA_COSECHA` | `harvest.humedad_grano_pct` | `INGRESAR_DATOS_COSECHA` | Implementada y activa |
| `data_quality` | `DATOS_INSUFICIENTES_PARA_COMERCIALIZACION` | `market.precio_spot_usd` | `INGRESAR_DATOS_MERCADO` | Implementada y activa |
| `harvest` | `HUMEDAD_ALTA_Y_VENTANA_SECA` | `humedad_grano_pct`, `precipitation` | `ESPERAR_SECADO_NATURAL` | Implementada y activa |
| `harvest` | `HUMEDAD_ALTA_Y_LLUVIA_PROXIMA` | `humedad_grano_pct`, `precipitation` | `COSECHAR_Y_SECAR` | Implementada y activa |
| `harvest` | `COSTO_SECADA_ELEVADO` | `costo_secada_usd_tn` | `EVALUAR_COSTO_SECADA` | Implementada y activa |
| `commercialization` | `FUTURO_FAVORABLE_PARA_FIJACION` | `precio_spot_usd`, `precio_futuro_usd` | `EVALUAR_COBERTURA_FUTURA` | Implementada y activa |
| `trafficability` | `RIESGO_DE_PISO_POR_PRECIPITACION` | `precipitation_next_72h_mm` | `VERIFICAR_TRANSITABILIDAD` | Implementada y activa |
| `spraying` | `ALERTA_PULVERIZACION_VIENTO` | `wind_max_kmh` | `SUSPENDER_PULVERIZACION` | Implementada y activa |
| `frost` | `RIESGO_TERMICO_A_VERIFICAR` | `temp_min_next_72h_c` | `VERIFICAR_ALERTA_HELADA` | Implementada y activa |
| `freight` | `FLETE_SIN_COTIZACION` | `delivery_options` | `ACTUALIZAR_COTIZACION` | Implementada y activa |
| `freight` | `COTIZACION_FLETE_DESACTUALIZADA` | `quote_observed_at` | `ACTUALIZAR_COTIZACION` | Implementada y activa |
| `freight` | `DESTINO_NO_APTO_POR_CAMINO` | `road_status` | `EVITAR_DESTINO` | Implementada y activa |
| `freight` | `DESTINO_SIN_CUPO_CONFIRMADO` | `receiving_confirmed` | `CONFIRMAR_CUPO` | Implementada y activa |
| `freight` | `DESTINO_CONDICIONADO_POR_HUMEDAD` | `max_receiving_moisture_pct` | `EVALUAR_RECONDICIONAMIENTO` | Implementada y activa |
| `freight` | `PRECIO_NETO_ORIGEN_CALCULADO` | `net_origin_price_usd_tn` | `CONSULTAR_PRECIO_NETO` | Implementada y activa |
| `freight` | `DESTINO_NETO_MAS_CONVENIENTE` | `delivery_options` | `EVALUAR_DESTINO_NETO` | Implementada y activa |
| `freight` | `SIN_DIFERENCIA_NETA_MATERIAL_ENTRE_DESTINOS` | `delivery_options` | `EVALUAR_DESTINO_CERCANO` | Implementada y activa |
| `freight` | `DATOS_INSUFICIENTES_PARA_COMPARAR_DESTINOS` | `delivery_options` | `COMPLETAR_DATOS_DESTINO` | Implementada y activa |
| `deliveries` | `ENTREGA_SIN_CARTA_DE_PORTE` | `deliveries` | `REGISTRAR_CARTA_DE_PORTE` | Implementada y activa |
| `deliveries` | `CARTA_PORTE_SIN_PESO_ORIGEN` | `waybills.peso_bruto_origen_kg` | `COMPLETAR_PESAJE_ORIGEN` | Implementada y activa |
| `deliveries` | `CARTA_PORTE_SIN_PESO_DESTINO` | `waybills.peso_recibido_destino_kg` | `COMPLETAR_PESAJE_DESTINO` | Implementada y activa |
| `deliveries` | `DIFERENCIA_DE_PESAJE_A_REVISAR` | `diferencia_kg`, `diferencia_pct` | `REVISAR_DIFERENCIA_PESAJE` | Implementada y activa |
| `deliveries` | `CARGA_SUPERA_CAPACIDAD_REFERENCIA` | `capacidad_referencia_kg` | `VERIFICAR_TOLERANCIA_CARGA` | Implementada y activa |
| `deliveries` | `FLETE_ESTIMADO_POR_ENTREGA` | `freight_quote_id`, `pesos` | `AUDITAR_COSTO_FLETE` | Implementada y activa |
| `deliveries` | `ENTREGA_ASOCIADA_A_COMPROMISO` | `compromiso_id` | `VERIFICAR_CUMPLIMIENTO_COMPROMISO` | Implementada y activa |
| `deliveries` | `ENTREGA_CON_DOCUMENTACION_PENDIENTE` | `documentacion_status` | `REGISTRAR_NUMERO_CARTA_PORTE` | Implementada y activa |

---

## 6. Parámetros de Política por Defecto (`policy_defaults.py`)

| Bloque | Clave de Política | Default Actual | Unidad | Scope que puede modificarlo | Regla/Fórmula que Impacta |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `cosecha` | `costo_secada_punto_usd` | `2.50` | $\mathrm{USD/Tn}$ | `organization`, `family_client` | `CostoSecadaElevadoRule` |
| `cosecha` | `costo_secada_alerta_pct_spot` | `3.0` | $\%$ | `organization` | `CostoSecadaElevadoRule` |
| `cosecha` | `lluvia_critica_72h_mm` | `10.0` | $\mathrm{mm}$ | `agronomic_template`, `field` | `HumedadAltaLluviaProximaRule` |
| `comercializacion` | `spread_futuro_min_usd_legacy` | `4.0` | $\mathrm{USD/Tn}$ | `organization` | `FuturoFavorableFijacionRule` |
| `pulverizacion` | `viento_maximo_kmh` | `15.0` | $\mathrm{km/h}$ | `agronomic_template` | `AlertaPulverizacionVientoRule` |
| `helada` | `umbral_temperatura_minima_c` | `4.0` | $\mathrm{^\circ C}$ | `agronomic_template`, `field` | `RiesgoTermicoAVerificarRule` |
| `freight` | `diferencia_neta_minima_relevante_usd_tn` | `1.0` | $\mathrm{USD/Tn}$ | `organization`, `family_client` | `SinDiferenciaNetaMaterialEntreDestinosRule` |
| `freight` | `max_quote_age_hours` | `48` | Horas | `organization` | `CotizacionFleteDesactualizadaRule` |
| `deliveries` | `normal_truck_reference_capacity_kg` | `35000` | $\mathrm{kg}$ | `organization` | `CargaSuperaCapacidadReferenciaRule` |
| `deliveries` | `vulcano_truck_reference_capacity_kg` | `45000` | $\mathrm{kg}$ | `organization` | `CargaSuperaCapacidadReferenciaRule` |
| `deliveries` | `weight_difference_review_pct` | `1.0` | $\%$ | `organization`, `family_client` | `DiferenciaDePesajeARevisarRule` |
| `deliveries` | `weight_difference_review_kg` | `300` | $\mathrm{kg}$ | `organization`, `family_client` | `DiferenciaDePesajeARevisarRule` |
| `deliveries` | `require_waybill_for_completed_delivery` | `False` | Booleano | `organization` | `EntregaSinCartaDePorteRule` |
| `safety` | `allow_override_safety_controls` | `False` | Booleano | `system_base` | `DecisionPolicyResolver` |

---

## 7. Contrato JSON Propuesto para Trazabilidad en UI

Se propone la siguiente estructura JSON estandarizada para exponer a futuro el desglose interactivo de fórmulas al usuario en la interfaz:

```json
{
  "calculation_id": "calc-net-origin-price-9921",
  "title": "Cálculo de Precio Neto en Origen",
  "formula_key": "net_origin_price",
  "formula_display": "precio_neto_origen = precio_ofrecido - flete - acondicionamiento - otros_costos",
  "inputs": [
    {
      "key": "price_usd_tn",
      "label": "Precio Ofrecido",
      "value": 220.00,
      "unit": "USD/Tn",
      "source": "manual_quote",
      "availability": "available"
    },
    {
      "key": "freight_usd_tn",
      "label": "Tarifa de Flete",
      "value": 15.00,
      "unit": "USD/Tn",
      "source": "transporter_quote",
      "availability": "available"
    },
    {
      "key": "conditioning_cost_usd_tn",
      "label": "Acondicionamiento / Secada",
      "value": 0.00,
      "unit": "USD/Tn",
      "source": "calculated",
      "availability": "available"
    },
    {
      "key": "other_costs_usd_tn",
      "label": "Otros Costos",
      "value": 0.00,
      "unit": "USD/Tn",
      "source": "user_input",
      "availability": "available"
    }
  ],
  "result": {
    "value": 205.00,
    "unit": "USD/Tn",
    "evaluation_status": "complete"
  },
  "policy": {
    "policy_id": "system-base",
    "policy_version": "2.0.0",
    "source_scope": "system_base"
  },
  "warnings": []
}
```

---

## 8. Roadmap Técnico Pre-Stock V1

1. **Stock V1 y Movimientos Auditables:** Implementar entidades de depósitos/silos, movimientos de entrada/salida y conciliación física.
2. **Asignación de Stock a Entregas:** Imputar entregas recibidas a lotes de stock físico sin duplicar movimientos.
3. **Imputación Definitiva a Compromisos:** Descontar saldos de compromisos comerciales mediante confirmación explícita del usuario.
4. **Adjuntos de Documentos a Cartas de Porte:** Permitir adjuntar fotos o PDFs de los tickets de balanza y cartas oficiales.
5. **Migración a Alembic:** Configurar scripts de migración versionados para desinstalar la migración liviana en `init_db()`.
6. **Calibración Agronómica y Comercial:** Ajustar las políticas base de secada, heladas y transitabilidad con asesores locales.
