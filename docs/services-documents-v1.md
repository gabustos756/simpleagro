# 📄 Especificación Técnica: Servicios V1, Documentos Privados y Links de Pago

**Proyecto:** EduAgro  
**Módulo:** Servicios V1 (`app/services/document_storage.py`, `app/utils/url_validator.py`)  
**Versión del Documento:** `1.0.0`  
**Estado:** Implementado  

---

## 1. Resumen y Objetivos del Módulo

El módulo **Servicios V1** amplía la gestión de servicios operativos e infraestructura rural en EduAgro permitiendo:
1. **Relación Relacional Real:** Vincular vencimientos/boletas puntuales (`ServicioVencimiento`) a un servicio permanente (`ServicioInstalado`).
2. **Adjuntos Digitales Privados:** Gestionar facturas, recibos, presupuestos, contratos y comprobantes de pago mediante el modelo `ServiceDocument`.
3. **Almacenamiento Privado en VPS:** Guardar los archivos físicos fuera de la raíz pública de Nginx, accediendo exclusivamente a través de endpoints autenticados con control multitenant por `cliente_id`.
4. **Enlaces Seguros a Portales de Pago:** Registrar enlaces a sitios de pago externos con validación anti-SSRF y renderizado transparente del dominio de destino.

---

## 2. Modelo de Datos y Relaciones (`app/models.py`)

### `ServicioInstalado` (`servicios_instalados`)
- Representa el servicio permanente por campo o instalación.
- Nuevos campos:
  - `payment_portal_url` (Text, Nullable): URL del portal institucional/autogestión del proveedor.
  - `payment_reference` (String(200), Nullable): Número de cliente, contrato o referencia de pago.
- Relaciones:
  - `vencimientos`: Relación 1:N con `ServicioVencimiento`.
  - `documentos`: Relación 1:N con `ServiceDocument` (contratos, presupuestos genéricos).

### `ServicioVencimiento` (`servicios_vencimiento`)
- Representa una boleta o liquidación mensual/periódica.
- Nuevos campos:
  - `servicio_instalado_id` (UUID FK, Nullable, Indexed): Clave foránea al servicio correspondiente.
  - `payment_link` (Text, Nullable): Enlace específico para pagar la boleta.
  - `periodo_referencia` (String(100), Nullable): Mes o período de la liquidación (ej: `Enero 2026`).
  - `fecha_pago` (Date, Nullable): Fecha efectiva en que se registró el pago.
- Relaciones:
  - `servicio_instalado`: Relación N:1 con `ServicioInstalado`.
  - `documentos`: Relación 1:N con `ServiceDocument` (factura, comprobante de pago).

### `ServiceDocument` (`service_documents`)
- Almacena exclusivamente **metadatos** de los archivos digitales adjuntos. **No almacena binarios BLOB en la base de datos**.
- Campos principales:
  - `id` (UUID PK).
  - `cliente_id` (UUID FK, Not Null, Indexed): Garantiza aislamiento multitenant estricto.
  - `servicio_id` (UUID FK, Nullable, Indexed).
  - `servicio_vencimiento_id` (UUID FK, Nullable, Indexed).
  - `document_type`: `DocumentTypeEnum` (`factura`, `recibo`, `presupuesto`, `contrato`, `comprobante_pago`, `otro`).
  - `original_filename` (String(255)): Nombre sanitizado original del archivo.
  - `stored_filename` (String(255)): Nombre basado en UUIDv4 generado en disco.
  - `storage_key` (String(500), Unique): Clave relativa de almacenamiento (`servicios/<cliente_id>/<target_id>/<uuid>.<ext>`).
  - `mime_type` (String(100)): Tipo MIME real validado por Magic Bytes.
  - `size_bytes` (BigInteger): Tamaño real del archivo en bytes (máx. 10 MiB).
  - `sha256_hash` (String(64)): Hash de verificación de integridad.
  - `uploaded_at` (DateTime): Fecha y hora de carga.
  - `uploaded_by_user_id` (UUID FK, Nullable): Usuario que subió el documento.
  - `notes` (Text, Nullable).
  - `estado` (String(20)): Estado del registro (`activo` o `anulado`).

---

## 3. Almacenamiento Privado en VPS (`app/services/document_storage.py`)

### 3.1. Estructura de Directorios
Los archivos se guardan fuera del directorio público web de Nginx:
- **Desarrollo Local:** `data/uploads/servicios/<cliente_id>/<target_id>/<uuid>.<ext>` (excluido de Git vía `.gitignore`).
- **Producción (VPS):** Configurable mediante `DOCUMENT_STORAGE_ROOT` (ej. `/home/gabi/apps/eduagro/data/uploads`).

### 3.2. Reglas de Seguridad
1. **Prevención de Path Traversal:** Toda clave de almacenamiento se resuelve usando `Path.resolve()`, comprobando estrictamente que pertenezca al directorio `DOCUMENT_STORAGE_ROOT`.
2. **Límite de Tamaño:** Máximo 10 MiB por archivo.
3. **Allowlist de Extensiones:** Únicamente `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`.
4. **Verificación por Magic Bytes:**
   - PDF: `%PDF-`
   - JPEG: `\xff\xd8\xff`
   - PNG: `\x89PNG\r\n\x1a\n`
   - WEBP: `RIFF....WEBP`
   - Se rechazan archivos HTML, SVG, ZIP, ejecutables o modificados maliciosamente.
5. **Streaming con SHA-256:** El guardado procesa chunks de 64 KiB y calcula la firma SHA-256 en tiempo real.
6. **Rollback Compensatorio:** Si falla la escritura en disco o la transacción posterior en PostgreSQL, el archivo en disco se elimina automáticamente.

---

## 4. Validación de URLs de Pago (`app/utils/url_validator.py`)

1. **Esquemas Permitidos:** Exclusivamente `http://` y `https://`.
2. **Protección Anti-SSRF:** Se rechazan URLs que apunten a interfaces locales o redes privadas: `localhost`, `127.0.0.1`, `::1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `.local`, `.lan`, `.internal`.
3. **Sanitización de Dominio:** La función `get_display_domain` extrae el hostname limpio (ej. `epec.com.ar`) para renderizarlo de forma transparente en los botones de la interfaz.
4. **Comportamiento en UI:** Abrir un enlace de pago externo abre una nueva pestaña (`target="_blank" rel="noopener noreferrer"`) y **no cambia** el estado de pago del vencimiento a `PAGADO`.

---

## 5. Endpoints HTTP (`app/main.py`)

- `POST /servicios/{servicio_id}/vencimientos/crear`: Registra un vencimiento manual para el servicio.
- `POST /servicios/{servicio_id}/documentos/subir`: Subida multipart `UploadFile` de documento asociado a un servicio.
- `POST /servicios/vencimientos/{vencimiento_id}/documentos/subir`: Subida multipart `UploadFile` de documento asociado a un vencimiento.
- `GET /servicios/documentos/{document_id}/descargar`: Descarga autenticada que retorna `FileResponse` con cabeceras `Content-Disposition: attachment; filename="..."`, `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`.
- `POST /servicios/documentos/{document_id}/eliminar`: Desactiva el registro de metadatos (soft-delete) y elimina el archivo del disco.

---

## 6. Estrategia de Backups Requerida en VPS

1. **Base de Datos:** Respaldo diario con `pg_dump -Fc eduagro > backup_db_YYYYMMDD.dump`.
2. **Archivos Adjuntos:** Sincronización diaria del directorio de uploads mediante `rsync -avz /home/gabi/apps/eduagro/data/uploads/ /backup/eduagro/uploads/`.
3. **Retención:** 30 días de retención rotativa.
