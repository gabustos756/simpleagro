# 🛡️ Informe de Auditoría de Arquitectura y Seguridad: Módulo Servicios, Almacenamiento de Documentos y Hardening VPS

**Proyecto:** EduAgro  
**Área:** Arquitectura de Software, Seguridad & Despliegue en VPS  
**Fecha:** 21 de Agosto de 2026  
**Documento:** `docs/audits/services-documents-vps-security-audit.md`  
**Estado:** Auditoría de Descubrimiento y Propuesta de Diseño (Sin cambios en código)  

---

## 1. Resumen Ejecutivo

El presente informe constituye la auditoría técnica de descubrimiento y diseño de seguridad para la gestión de servicios operativos, vencimientos, comprobantes digitales y enlaces de pago en **EduAgro**. 

La aplicación EduAgro opera sobre **Python / FastAPI**, **SQLAlchemy AsyncIO**, **PostgreSQL**, **Jinja2** y **Tailwind CSS**, desplegada en un VPS Linux gestionado por `systemd` (`eduagro.service`), con `uvicorn` escuchando en `127.0.0.1:5051` y **Nginx** como Proxy Inverso.

### Principales Hallazgos:
1. **Desconexión Relacional de Vencimientos:** Actualmente existen dos modelos principales (`ServicioInstalado` y `ServicioVencimiento`), pero `ServicioVencimiento` carece de clave foránea hacia `ServicioInstalado`. Además, los vencimientos se representan hoy mediante una única `fecha_vencimiento` dentro de cada servicio instalado.
2. **Ausencia de Almacenamiento Real de Archivos:** No existe un directorio de uploads ni handlers de `UploadFile`. La tabla `servicios_instalados` posee un campo `comprobante_url: Text` que contiene URLs externas fijas de prueba (*Unsplash mock*).
3. **Ausencia de Links de Pago:** No existen campos para enlaces de portales de pago de proveedores (`payment_url`), números de cuenta/cliente ni referencias de pago.
4. **Credenciales en Configuración de Systemd:** El archivo de servicio systemd de producción (`DEPLOYMENT.md`) contiene cadenas de conexión en texto plano (`DATABASE_URL`, `SESSION_SECRET`).

---

## 2. Inventario Real de Modelos, Relaciones y Rutas de Servicios

### 2.1. Modelos SQLAlchemy Existentes (`app/models.py`)

#### `ServicioInstalado` (`servicios_instalados`)
- **Campos:**
  - `id`: `UUID` (PK)
  - `cliente_id`: `UUID` (FK `clientes.id`, nullable=True) — *Garantiza aislamiento multitenant*.
  - `campo_id`: `UUID` (FK `campos.id`, nullable=False) — *Asociación obligatoria al campo*.
  - `instalacion_id`: `UUID` (FK `instalaciones.id`, nullable=True) — *Asociación a instalación física*.
  - `tipo_servicio`: `TipoServicioEnum` (`LUZ_RURAL`, `AGUA_RIEGO`, `INTERNET_SATELITAL`, `IMPUESTO_INMOBILIARIO`, `TASA_VIAL`, `SEGURO`, `ALQUILER`, `OTRO`).
  - `concepto`: `String(200)`
  - `proveedor`: `String(150)`
  - `frecuencia_pago`: `FrecuenciaPagoEnum` (`MENSUAL`, `BIMESTRAL`, `TRIMESTRAL`, `ANUAL`, `UNICO`, `OTRO`).
  - `monto_estimado_ars`: `Numeric(14, 2)`
  - `monto_real_ars`: `Numeric(14, 2)`
  - `monto_usd`: `Numeric(14, 2)`
  - `fecha_vencimiento`: `Date` — *Vencimiento único actual*.
  - `estado`: `EstadoServicioInstaladoEnum` (`PENDIENTE`, `AL_DIA`, `VENCIDO`, `SUSPENDIDO`).
  - `comprobante_url`: `Text` (nullable=True) — *Almacena URL externa mock*.
  - `observaciones`: `Text` (nullable=True).
- **Relaciones:** `cliente`, `campo`, `instalacion`.

#### `ServicioVencimiento` (`servicios_vencimiento`)
- **Campos:**
  - `id`: `UUID` (PK)
  - `cliente_id`: `UUID` (FK `clientes.id`, nullable=True).
  - `concepto`: `String(200)`.
  - `monto_ars`: `Numeric(14, 2)`.
  - `monto_usd`: `Numeric(14, 2)`.
  - `fecha_vencimiento`: `Date`.
  - `estado`: `EstadoServicio` (`PENDIENTE`, `PAGADO`, `VENCIDO`).
  - `comprobante_url`: `Text` (nullable=True).
- **Inconsistencia Detectada:** No posee FK hacia `ServicioInstalado`. La tabla está huérfana en el esquema actual.

### 2.2. Rutas HTTP y Templates (`app/main.py`)

| Ruta HTTP | Método | Template Asociado | Descripción / Estado |
| :--- | :--- | :--- | :--- |
| `/servicios/campos` | `GET` | `servicios_resumen_campos.html` | Resumen de gastos por campo |
| `/servicios` | `GET` | `servicios_listado.html` | Listado y filtros de servicios |
| `/servicios/nuevo` | `GET` | `servicios_form.html` | Formulario de alta de servicio |
| `/servicios/nuevo` | `POST` | *Redirect `/servicios/{id}`* | Procesa alta e inyecta URL mock |
| `/servicios/vencimientos` | `GET` | `servicios_vencimientos.html` | Cronograma de vencimientos |
| `/servicios/instalaciones` | `GET` | `servicios_instalaciones.html` | Servicios por infraestructura |
| `/servicios/{id}` | `GET` | `servicios_ficha.html` | Ficha detallada del servicio |
| `/servicios/{id}/editar` | `GET` | `servicios_form.html` | Formulario de edición |

---

## 3. Estado Actual de Pagos, Vencimientos y Comprobantes

1. **Estado de Pagos:** Se maneja con estados simplificados en `ServicioInstalado.estado` (`PENDIENTE`, `AL_DIA`, `VENCIDO`, `SUSPENDIDO`). No existe un registro histórico de pagos realizados.
2. **Vencimientos Recurrentes:** Un `ServicioInstalado` sólo almacena una `fecha_vencimiento`. Para llevar el historial de boletas mensuales/bimestrales, se requiere vincular `ServicioVencimiento` a `ServicioInstalado` mediante una relación `1:N`.
3. **Comprobantes:** No hay almacenamiento en disco. El campo `comprobante_url` almacena enlaces estáticos de Unsplash al crear servicios vía UI.

---

## 4. Diseño Recomendado para Documentos (`ServiceDocument`)

Se propone la creación de la entidad dedicada `ServiceDocument` para gestionar comprobantes, facturas y contratos sin guardar binarios dentro de la base de datos.

### 4.1. Modelo Conceptual
```text
ServiceDocument
├── id: UUID (PK)
├── cliente_id: UUID (FK clientes.id, Not Null, Index)
├── servicio_id: UUID (FK servicios_instalados.id, Nullable, Index)
├── servicio_vencimiento_id: UUID (FK servicios_vencimiento.id, Nullable, Index)
├── document_type: Enum ('factura', 'recibo', 'presupuesto', 'contrato', 'comprobante_pago', 'otro')
├── original_filename: String(255) (Sanitizado sin caracteres de control)
├── stored_filename: String(255) (UUIDv4 + extensión segura)
├── mime_type: String(100) (Verificado por Magic Bytes, ej. 'application/pdf', 'image/jpeg')
├── size_bytes: BigInteger (Máximo 10 MB)
├── sha256_hash: String(64) (Integridad de archivo)
├── uploaded_at: DateTime(timezone=True) (server_default=func.now())
├── uploaded_by_user_id: UUID (FK usuarios.id, Nullable)
└── notes: Text (Nullable)
```

### 4.2. Reglas de Vínculo Específico
- **Asociación Preferida:** Un comprobante de pago/factura se asocia a `servicio_vencimiento_id` (período o boleta puntual).
- **Asociación Secundaria:** Un contrato o póliza anual se asocia directamente a `servicio_id`.
- **Almacenamiento Binario:** Prohibido almacenar binarios (BLOBs/Bytea) en PostgreSQL. La base de datos almacena exclusivamente metadatos estructurados.

---

## 5. Diseño Recomendado para Enlaces de Pago y Portales

### 5.1. Ubicación de Campos
1. **Portal Permanente del Proveedor (`ServicioInstalado.payment_portal_url`):**
   - URL fija del sitio web o portal de autogestión del prestador (ej. `https://www.epec.com.ar/oficina-virtual`).
2. **Enlace Específico de Boleta/Cupón (`ServicioVencimiento.payment_link`):**
   - Enlace dinámico o puntual correspondiente a una liquidación específica (ej. `https://pagos.epec.com.ar/pay?bill=984123`).

### 5.2. Reglas de Validación y Seguridad para URLs
- **Esquemas Permitidos:** Únicamente `https://` (preferido) y `http://`.
- **Esquemas Rechazados:** Rechazo estricto de `javascript:`, `data:`, `file:`, `ftp:`, URLs relativas (`/admin`), o sin protocolo.
- **Sanitización de Dominio:** Utilizar `urllib.parse.urlparse` para extraer y mostrar el dominio de destino en la UI (ej. *"Abrir portal de pago en epec.com.ar ↗"*).
- **Atributos HTML de Enlace:**
  ```html
  <a href="{{ servicio.payment_portal_url }}" target="_blank" rel="noopener noreferrer" class="btn-link">
    Abrir portal de pago externo (epec.com.ar) ↗
  </a>
  ```
- **Sin Iframes:** Prohibido incrustar portales externos en elementos `<iframe>` para evitar ataques de Clickjacking y errores de Mixed Content.
- **Sin Tokens de Sesión:** No incluir tokens privados de usuario ni contraseñas dentro de la URL.
- **Sin Cambio Automático de Estado:** Hacer clic en el enlace de pago **NO debe cambiar** el estado del servicio a `PAGADO` automáticamente. La confirmación requiere registrar el pago o subir el comprobante.

---

## 6. Arquitectura Actual de Deployment y Hallazgos No Sensibles

Según la especificación técnica en `DEPLOYMENT.md`:

- **Servidor VPS:** Linux Ubuntu (Host `vmi3481033`).
- **Usuario de Ejecución:** `gabi` (usuario no-root dedicado).
- **Ruta del Proyecto:** `/home/gabi/apps/eduagro`.
- **Proxy Inverso:** Nginx expuesto en puertos 80/443 con certificado SSL.
- **Servidor ASGI:** `uvicorn` escuchando exclusivamente en la interfaz de loopback `127.0.0.1:5051`.
- **Gestor de Procesos:** Systemd (`/etc/systemd/system/eduagro.service`).
- **Motor de Base de Datos:** PostgreSQL en `localhost:5432` (`database: eduagro`).

---

## 7. Diseño Recomendado para Almacenamiento en VPS

### 7.1. Estructura de Directorios Privada (Fuera de Nginx Root)
Los archivos subidos se almacenarán en una ruta privada del sistema, **completamente fuera** de la raíz web estática de Nginx (`/var/www/html`):

```text
/home/gabi/apps/eduagro/data/uploads/
└── servicios/
    └── <cliente_id>/
        └── <vencimiento_id_o_servicio_id>/
            └── <uuid_aleatorio>.<ext>
```

### 7.2. Permisos del Sistema de Archivos
- **Directorio Raíz de Uploads:** `0750` (`drwxr-x---`), Propietario `gabi:gabi`.
- **Archivos Almacenados:** `0640` (`-rw-r-----`), Propietario `gabi:gabi`.
- **Acceso Directo por Nginx:** **PROHIBIDO**. Nginx no posee regla `location /uploads/` ni acceso de lectura a `/home/gabi/apps/eduagro/data/uploads/`.

### 7.3. Descarga Segura y Autenticada vía FastAPI
Las descargas se realizan exclusivamente mediante un endpoint autenticado que valida el aislamiento multitenant:

- **Endpoint:** `GET /servicios/documentos/{document_id}/descargar`
- **Flujo de Seguridad:**
  1. Verifica que el usuario tenga sesión activa.
  2. Valida que `document.cliente_id == current_user.cliente_id`.
  3. Comprueba que el archivo físico exista en disco.
  4. Retorna `FileResponse` con cabeceras estrictas:
     - `Content-Disposition: attachment; filename="sanitized_original_filename.pdf"`
     - `Content-Type`: MIME type verificado (ej. `application/pdf`).
     - `X-Content-Type-Options: nosniff`

### 7.4. Validaciones al Cargar Archivos (`UploadFile`)
- **Límite de Tamaño:** 10 MB (`10 * 1024 * 1024` bytes).
- **Lista Blanca de Extensiones:** `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`.
- **Verificación por Magic Bytes:** Validación del contenido binario real utilizando cabeceras binarias (ej. `%PDF-` para PDF, `\xff\xd8\xff` para JPEG).
- **Sanitización del Nombre Original:** Eliminación de secuencias de Path Traversal (`../`, `..\`), caracteres de control y bytes nulos.

---

## 8. Matriz de Amenazas y Controles

| Vector de Ataque | Descripción del Riesgo | Control de Seguridad Recomendado |
| :--- | :--- | :--- |
| **Path Traversal** | Intentar leer archivos del sistema (`../../etc/passwd`) | Nombre en disco basado en UUIDv4; resolución de ruta con `Path.resolve()` |
| **Aislamiento Multitenant** | Usuario del Cliente A descarga facturas del Cliente B | Filtro estricto `WHERE cliente_id = user.cliente_id` antes de servir el archivo |
| **Ejecución de Código (RCE)** | Subida de scripts maliciosos (`.py`, `.php`, `.sh`, `.html`) | Guardar fuera de Nginx web root; lista blanca estricta; sin permisos de ejecución (`0640`) |
| **XSS vía Links de Pago** | Inyección de `javascript:alert(1)` en campo URL | Validación estricta con regex y `urllib.parse` (sólo `http://` y `https://`) |
| **XSS vía Nombre de Archivo** | Inyección HTML/JS en el atributo `filename` | Sanitización del nombre original y escapado de caracteres en Jinja2 |
| **Agotamiento de Disco (DoS)** | Subida masiva de archivos pesados que llene el VPS | Límite de 10 MB por archivo y cuota por cliente/tenant |

---

## 9. Matriz de Riesgos

| Nivel de Riesgo | Hallazgo | Acción Requerida |
| :--- | :--- | :--- |
| 🔴 **CRÍTICO** | Credenciales de DB/Secretos en `DEPLOYMENT.md` y archivos de servicio systemd | Mover secretos a `.env` con permisos `0600` (`-rw-------`) y rotar claves |
| 🟠 **ALTO** | URLs de comprobantes apuntan a fuentes externas sin validación de origen | Reemplazar por módulo `ServiceDocument` con storage privado en VPS |
| 🟡 **MEDIO** | Desconexión estructural entre `ServicioVencimiento` y `ServicioInstalado` | Agregar `servicio_instalado_id` (FK) en `ServicioVencimiento` |
| 🟢 **BAJO** | Falta de campos para portales de pago y referencias | Incorporar `payment_portal_url` y `referencia_pago` |

---

## 10. Plan de Implementación en Fases

### Fase 1: Módulo `ServiceDocument` y Almacenamiento Seguro (1-2 días)
1. Crear el modelo `ServiceDocument` en `app/models.py`.
2. Agregar FK `servicio_instalado_id` a `ServicioVencimiento`.
3. Crear el servicio de almacenamiento privado `app/services/document_storage.py` con validación de Magic Bytes y UUID.
4. Crear endpoint de carga `POST /servicios/documentos/subir` y descarga `GET /servicios/documentos/{id}/descargar`.

### Fase 2: Enlaces de Pago y Portales de Proveedor (0.5 días)
1. Agregar `payment_portal_url` a `ServicioInstalado` y `payment_link` a `ServicioVencimiento`.
2. Crear validador de URLs en `app/utils/url_validator.py` (`http/https` únicamente).
3. Actualizar la UI (`servicios_ficha.html` y `servicios_vencimientos.html`) con enlaces seguros `target="_blank" rel="noopener noreferrer"`.

### Fase 3: Hardening VPS y Nginx (0.5 días)
1. Verificar que `/home/gabi/apps/eduagro/data/uploads/` tenga permisos `0750`.
2. Asegurar que Nginx **no tenga** alias ni acceso estático a la carpeta de uploads.
3. Configurar cabeceras de seguridad en Nginx (`X-Content-Type-Options`, `X-Frame-Options`).

### Fase 4: Estrategia Unificada de Backups (0.5 días)
1. Configurar script de backup diario (`cron`) que realice `pg_dump` de PostgreSQL y empaquete comprimido el directorio `data/uploads/`.
2. Retención rotativa de 30 días en el servidor local/volumen secundario.

---

## 11. Checklist de Despliegue Seguro

- [ ] La base de datos almacena metadatos; los binarios residen exclusivamente en `/data/uploads/`.
- [ ] La carpeta de uploads está fuera de `/var/www/html` y no es accesible por Nginx.
- [ ] Los endpoints de descarga validan la sesión y la pertenencia de `cliente_id`.
- [ ] La descarga se realiza mediante `FileResponse` con `Content-Disposition: attachment`.
- [ ] Los archivos subidos se renombran con UUIDv4 en disco.
- [ ] Se verifica la extensión y los Magic Bytes antes de guardar en disco.
- [ ] Las URLs de pago se validan restringiendo a esquemas `http://` y `https://`.
- [ ] Los enlaces externos utilizan `target="_blank" rel="noopener noreferrer"`.
- [ ] Las credenciales y claves de sesión residen únicamente en `.env` (`0600`).
- [ ] Uvicorn escucha en `127.0.0.1:5051` y sólo Nginx recibe tráfico externo.

---

## 12. Preguntas de Negocio Bloqueantes (Máximo 3)

1. **Vencimientos Múltiples:** ¿Un servicio instalado (ej. Luz EPEC) debe generar automáticamente vencimientos mensuales recurrentes, o los vencimientos se crearán manualmente boleta por boleta?
2. **Tipos de Comprobantes:** ¿Se requiere restringir ciertos tipos de documentos (ej. sólo PDF para facturas) o se permite una lista amplia que incluya fotos de recibos tomadas con teléfono celular (`.jpg`, `.png`, `.webp`)?
3. **Moneda de Pago:** ¿Las facturas y recibos adjuntos deben soportar bimoneda explícita (monto en ARS con tipo de cambio oficial al día de emisión) o se mantiene la conversión estática actual?

---

## 13. Archivos o Configuraciones Que No Pudieron Inspeccionarse

- Archivo de configuración activo de Nginx en VPS (`/etc/nginx/sites-available/eduagro`) — *No accesible desde el repositorio local; verificado mediante la especificación en `DEPLOYMENT.md`*.
- Reglas UFW del cortafuegos de producción en el VPS — *Requiere ejecución remota por SSH*.

---

## 14. Recomendación Final

Se recomienda proceder en la siguiente fase de desarrollo con la **Fase 1** y **Fase 2**:
1. Conectar `ServicioVencimiento` a `ServicioInstalado` con FK `servicio_instalado_id`.
2. Crear el modelo `ServiceDocument` y el servicio de almacenamiento local seguro en `/home/gabi/apps/eduagro/data/uploads/`.
3. Agregar el campo `payment_portal_url` con sanitización `http/https` para que los usuarios puedan acceder fácilmente a los portales de pago de sus proveedores.
