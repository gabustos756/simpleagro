# Manual de Usuario Didáctico - Plataforma EduAgro ERP
*Sistema Integral de Gestión Agropecuaria para la Provincia de Córdoba, Argentina*

---

## ¿Qué es EduAgro y cuál es su objetivo?

**EduAgro** es la plataforma informática creada especialmente para conectar el trabajo del campo ("sobre la camioneta") con la administración del establecimiento rural.

Organiza en un solo lugar la información de hectáreas, siembras por lote, estimación de rindes, precipitaciones (lluvias), stock de granos en silobolsas, cotizaciones de mercado y pago de facturas de servicios e impuestos.

---

## Enlace de Acceso al Servidor

Acceso directo en el navegador web:
🌐 **Servidor Local**: [https://eduagro.ggsolutions.com.ar](https://eduagro.ggsolutions.com.ar)

---

## Módulos del Sistema y Capturas de Pantalla Correspondientes

A continuación se detalla para qué sirve cada módulo, cómo utilizarlo y la imagen correspondiente guardada en `static/img/`:

### 1. 🏠 Portal de Entrada Principal (`dashboard.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/](https://eduagro.ggsolutions.com.ar/)
- **¿Para qué sirve?**: Es el patio principal de la aplicación. Muestra de un vistazo la superficie total trabajada, la cotización oficial del dólar divisa del día, el clima actual y los accesos rápidos a cada área de trabajo.
- **¿Cómo se usa?**: Al ingresar, consulte la cotización de pizarra del dólar divisa y seleccione la tarjeta del área que va a operar hoy.

### 2. 📍 Campos y Establecimientos (`productivo_campos.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/productivo/campos](https://eduagro.ggsolutions.com.ar/productivo/campos)
- **¿Para qué sirve?**: Organiza la superficie rural total del establecimiento. Separa las hectáreas de propiedad familiar de las hectáreas alquiladas a terceros (arrendamientos) y calcula los costos por hectárea.
- **¿Cómo se usa?**: Presione "Nuevo Campo" para ingresar un establecimiento con su superficie en hectáreas y tipo de tenencia.

### 3. 🌱 Lotes y Cultivos Activos (`productivo_lotes.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/productivo/lotes](https://eduagro.ggsolutions.com.ar/productivo/lotes)
- **¿Para qué sirve?**: Es la pizarra visual de siembra. Muestra los cuadros o lotes del campo, qué cultivo está sembrado (Soja 1ra, Trigo, Maíz), la etapa de crecimiento y los rindes estimados en Quintales por Hectárea (qq/ha).
- **¿Cómo se usa?**: Haga clic sobre la tarjeta de un lote para modificar el cultivo planificado, el rinde estimado o ingresar el rinde cosechado.
- *Regla rápida*: 10 Quintales (qq) = 1 Tonelada (Tn). Ejemplo: 35 qq/ha en 100 ha = 350 Toneladas cosechadas.

### 4. 🌤️ Agrometeorología y Clima (`clima.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/clima/campos](https://eduagro.ggsolutions.com.ar/clima/campos)
- **¿Para qué sirve?**: Brinda información agrometeorológica del campo. Incluye serie de 72 horas y pronóstico extendido a 14 días con porcentaje de probabilidad de precipitación.
- **¿Cómo se usa?**: Consulte antes de programar pulverizaciones, siembras o fertilizaciones para evitar pérdidas por lluvias imprevistas o vientos fuertes.

### 5. 📱 Modo Campo para Celular (`campo.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/campo](https://eduagro.ggsolutions.com.ar/campo)
- **¿Para qué sirve?**: Versión táctil para celulares o tablets. Diseñado con botones grandes para registrar precipitaciones (lluvias en mm) u observaciones con una sola mano desde el vehículo o el galpón.
- **¿Cómo se usa?**: Abra la pantalla en el celular tras una lluvia, presione los botones de milímetros (+5mm, +10mm) o escriba la lectura del lluviómetro. Funciona sin señal de celular guardando los datos offline.

### 6. 📈 Resumen Comercial y Pizarra (`comercial.png` y `comercial_tabla.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/comercial](https://eduagro.ggsolutions.com.ar/comercial)
- **¿Para qué sirve?**: Informa diariamente las cotizaciones de Pizarra Rosario (Cámara Arbitral de Cereales - BCR) en Dólares por Tonelada (US$/Tn) y Pesos ($ARS/Tn), junto al Dólar BNA Comprador.
- **¿Cómo se usa?**: Seleccione el cultivo (Soja, Maíz, Trigo) para valorizar las toneladas guardadas en dólares y pesos sin vender.

### 7. 🚜 Stock Físico en Silobolsa y Acopio (`stock.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/comercial/stock](https://eduagro.ggsolutions.com.ar/comercial/stock)
- **¿Para qué sirve?**: Controla las toneladas cosechadas y guardadas. Diferencia el volumen almacenado en silobolsas en el campo de lo entregado a acopios o puerto.
- **¿Cómo se usa?**: Registre la ubicación e identificador de cada silobolsa armada durante la cosecha.

### 8. 📝 Contratos y Ventas (`contratos-compromisos.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/comercial/contratos](https://eduagro.ggsolutions.com.ar/comercial/contratos)
- **¿Para qué sirve?**: Administra los contratos celebrados con acopios o corredores de granos:
  - 🟢 **Precio Fijo**: Venta con precio cerrado en US$/Tn.
  - 🔵 **Precio A Fijar**: Grano entregado en acopio pendiente de poner precio.
  - 🟧 **Canje Agropecuario**: Granos comprometidos para pagar fertilizantes, semillas o alquileres.
- **¿Cómo se usa?**: Cargue los contratos para saber cuántas toneladas faltan entregar o fijar precio.

### 9. 🤖 Motor de Decisiones Comercial (`comercial_agente-decisiones.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/comercial](https://eduagro.ggsolutions.com.ar/comercial)
- **¿Para qué sirve?**: Asistente inteligente que calcula las mermas por humedad y costo de secado en planta vs. embolsar en silobolsa o fijar futuro en Matba Rofex.
- **¿Cómo se usa?**: Ingrese el porcentaje de humedad del grano y el sistema le indicará la decisión más conveniente.

### 10. ⚡ Servicios Rurales e Instalaciones (`servicios.png`)
- **Enlace**: [https://eduagro.ggsolutions.com.ar/servicios/campos](https://eduagro.ggsolutions.com.ar/servicios/campos)
- **¿Para qué sirve?**: Controla el pago de facturas y servicios rurales:
  - 🟢 **Al día**: Comprobante pagado.
  - 🟡 **Próximo Vencer**: Vence en los próximos días.
  - 🔴 **Vencido**: Pago urgente requerido.
- **¿Cómo se usa?**: Revise el semáforo para llevar al día las facturas de Luz Rural EPEC, patentes de vehículos, combustible e impuestos.

---

## 11. 🚀 Guía Paso a Paso: ¿Cómo comenzar a usar EduAgro en tu Campo?

Para configurar tu establecimiento desde cero y sacarle el máximo provecho al sistema desde el primer día, te sugerimos seguir este orden sencillo de trabajo:

1. **Paso 1 - Crear tu Campo / Finca**:
   - Ingresa el nombre de tu campo, superficie total en hectáreas y si es Propio o Alquilado.
   - 🔗 [Ir a Módulo Campos](https://eduagro.ggsolutions.com.ar/productivo/campos)
2. **Paso 2 - Dividir y Cargar tus Lotes**:
   - Crea cada cuadro o lote con su nombre, hectáreas productivas, tipo de suelo y cultivo actual (Soja, Trigo, Maíz).
   - 🔗 [Ir a Módulo Lotes](https://eduagro.ggsolutions.com.ar/productivo/lotes)
3. **Paso 3 - Cargar Instalaciones y Servicios**:
   - Vincula las bombas de agua, casas o galpones y agrega las facturas de Luz Rural (EPEC), patentes e impuestos.
   - 🔗 [Ir a Módulo Servicios](https://eduagro.ggsolutions.com.ar/productivo/servicios)
4. **Paso 4 - Cargar Lluvias y Labores ('Modo Campo')**:
   - Instala el acceso en el celular y empieza a anotar las lluvias del pluviómetro (+5mm, +10mm) y las tareas del día.
   - 🔗 [Ir a Modo Campo](https://eduagro.ggsolutions.com.ar/campo)
5. **Paso 5 - 'Jugar' con los Estados del Campo**:
   - A medida que avance la campaña, cambia el estado del lote (`Barbecho` ➔ `Sembrado` ➔ `En Crecimiento` ➔ `Cosechado`) y registra los rindes obtenidos en quintales por hectárea ($qq/ha$).
   - 🔗 [Ir a Módulo Lotes](https://eduagro.ggsolutions.com.ar/productivo/lotes)
6. **Paso 6 - Cargar Silobolsas y Vender Granos**:
   - Al cosechar, registra el stock guardado en silobolsas, consulta la pizarra de precios BCR y carga tus contratos a fijar o de canje.
   - 🔗 [Ir a Módulo Comercialización](https://eduagro.ggsolutions.com.ar/comercial)

