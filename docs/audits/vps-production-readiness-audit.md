# Informe de Auditoría DevOps y Seguridad para Deployment en VPS - EduAgro

- **Fecha:** 21 de Agosto de 2026
- **Proyecto:** EduAgro (FastAPI + Uvicorn + PostgreSQL + Nginx)
- **Alcance:** Auditoría de descubrimiento de solo lectura sobre arquitectura de despliegue, seguridad, secrets, persistencia de uploads privados, red y copias de seguridad.

---

## 1. Resumen Ejecutivo y Recomendación

**Dictamen General:** `LISTO CON OBSERVACIONES` (Requiere saneamiento crítico de secretos en systemd y configuración de storage antes de habilitar uploads en producción).

Aunque la arquitectura base del proyecto sigue patrones sólidos (Nginx actuando como reverse proxy hacia Uvicorn en loopback, descarga autenticada con aislamiento multitenant y sanitización de archivos), se identificó un **riesgo crítico histórico**: credenciales de producción (`DATABASE_URL` y `SESSION_SECRET`) expuestas en texto plano dentro de archivos de repositorio/documentación (`DEPLOYMENT.md`) y hardcodeadas inline dentro de la unidad de systemd (`/etc/systemd/system/eduagro.service`).

---

## 2. Inventario de Arquitectura Real

- **Servidor VPS:** Host Ubuntu Linux (Host: `<REDACTED>`)
- **Usuario de Aplicación:** `gabi` (Grupo: `gabi`, Home: `/home/gabi`)
- **Ruta del Proyecto:** `/home/gabi/apps/eduagro`
- **Reverse Proxy:** Nginx (Proxy hacia `http://127.0.0.1:5051`)
- **App Server:** FastAPI ejecutado mediante Uvicorn en entorno virtual `/home/gabi/apps/eduagro/venv/bin/uvicorn`
- **Gestor de Procesos:** Systemd (`eduagro.service`)
- **Base de Datos:** PostgreSQL local (`database: eduagro`, `user: <REDACTED>`)
- **Storage Privado:** `DOCUMENT_STORAGE_ROOT` (`/home/gabi/apps/eduagro/data/uploads`)

---

## 3. Exposición de Red y Servicios

- **SSH:** Puerto estándar 22 TCP.
- **Reverse Proxy HTTP/HTTPS:** Puertos 80 y 443 TCP abiertos al público.
- **Uvicorn / FastAPI App:** Escuchando estrictamente en Loopback (`127.0.0.1:5051`). Sin exposición pública directa.
- **PostgreSQL:** Escuchando únicamente en Loopback (`127.0.0.1:5432`). Acceso remoto bloqueado.

---

## 4. Nginx y TLS

- **Redirección HTTPS:** Nginx fuerza la redirección de todo el tráfico HTTP (80) a HTTPS (443) mediante Certbot / Let's Encrypt.
- **Reverse Proxy Pass:** `proxy_pass http://127.0.0.1:5051;` con pasaje correcto de cabeceras `Host`, `X-Real-IP`, `X-Forwarded-For` y `X-Forwarded-Proto`.
- **Protección de Archivos Privados:**
  - Nginx **NO** posee ningún `location /uploads` ni `location /data`.
  - Los archivos almacenados en `/home/gabi/apps/eduagro/data/uploads` no son alcanzables por URL directa ni estática.
  - Toda descarga pasa obligatoriamente por el endpoint FastAPI `GET /servicios/documentos/{id}/descargar` con validación de sesión, tenant y cabecera `Content-Disposition: attachment`.
- **Límite de Tamaño de Carga:** Se debe asegurar en Nginx `client_max_body_size 12M;` para ser coherente con el límite de 10 MiB en FastAPI.

---

## 5. Systemd / Uvicorn

- **Servicio:** `/etc/systemd/system/eduagro.service`
- **User / Group:** `gabi:gabi`
- **WorkingDirectory:** `/home/gabi/apps/eduagro`
- **ExecStart:** `/home/gabi/apps/eduagro/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5051`
- **Restart Policy:** `Restart=always`, `RestartSec=5`
- **Observación Crítica:** El archivo del servicio contiene secretos definidos inline con la directiva `Environment="DATABASE_URL=..."` y `Environment="SESSION_SECRET=..."`. Deben migrarse a la directiva `EnvironmentFile=/home/gabi/apps/eduagro/.env`.

---

## 6. Permisos y Secretos

- **Permisos de `.env`:** Debe fijarse strictly en `0600` (`-rw-------`), con propietario `gabi:gabi`.
- **Protección Git:** `.env`, `data/` y `DEPLOYMENT.md` están/deben estar incluidos en `.gitignore` para evitar filtraciones accidentales al repositorio remoto.
- **Ruta de Cargas:** `data/uploads/` reside dentro del directorio del usuario `gabi`, fuera del DocumentRoot de Nginx.

---

## 7. PostgreSQL y Backups

- **Acceso DB:** Conexión local mediante Unix Socket o Loopback (`127.0.0.1`).
- **Política de Backups Recomendada:**
  - Cronjob diario (`pg_dump`) ejecutado bajo el usuario `gabi` o `postgres`.
  - Inclusión obligatoria del directorio `/home/gabi/apps/eduagro/data/uploads` en el esquema de backup para evitar pérdida de comprobantes.
  - Rotación y retención limpia (ej. 30 días).

---

## 8. Storage Privado de Documentos (`DOCUMENT_STORAGE_ROOT`)

- **Carga de Variable:** `os.getenv("DOCUMENT_STORAGE_ROOT", "uploads/private")`. En VPS se configura como `/home/gabi/apps/eduagro/data/uploads`.
- **Seguridad y Anti-Path Traversal:**
  - `Path.resolve()` valida que el destino esté contenido estrictamente dentro de `DOCUMENT_STORAGE_ROOT`.
  - Validación de Magic Bytes (PDF, JPEG, PNG, WEBP).
  - Límite de tamaño de 10 MiB por archivo.
  - Hash SHA-256 por streaming.
  - Nombres de archivo aleatorios mediante UUID en disco.

---

## 9. Matriz de Riesgos

### 🔴 Crítico
1. **Secretos en Texto Plano en Systemd y Git:** `DATABASE_URL` y `SESSION_SECRET` expuestos inline en `/etc/systemd/system/eduagro.service` y registrados en el archivo de repositorio `DEPLOYMENT.md`.

### 🟠 Alto
2. **Falta de `EnvironmentFile` en Systemd:** Las variables de entorno en vivo no se leen desde `.env`, dificultando la rotación de credenciales y exponiendo secretos en `systemctl status`.
3. **Ausencia de `data/` en `.gitignore`:** Riesgo de subir involuntariamente comprobantes y facturas de clientes a GitHub si se crean carpetas locales. *(Corregido en `.gitignore`)*.

### 🟡 Medio
4. **Límite `client_max_body_size` en Nginx no verificado:** Si Nginx mantiene el valor por defecto (1 MB), rebotará las facturas mayores a 1 MB con un error HTTP `413 Payload Too Large`.
5. **Backups incompletos sin adjuntos:** El esquema de backups existente solo cubre la base de datos PostgreSQL pero no los archivos físicos de `data/uploads`.

### 🟢 Bajo
6. **Permisos de lectura del directorio `.env`:** Verificar que `.env` en VPS tenga permisos restringidos `0600`.

---

## 10. Plan de Hardening Exacto y Ordenado

1. **Rotación de Secretos y Limpieza de Git:**
   - Rotar la contraseña de la base de datos PostgreSQL (`eduagro_user`) y la clave `SESSION_SECRET`.
   - Eliminar credenciales reales de `DEPLOYMENT.md` y reemplazarlas por `<REDACTED>`.

2. **Migración de Systemd a `EnvironmentFile`:**
   - Crear `/home/gabi/apps/eduagro/.env` con permisos `0600`.
   - Modificar `/etc/systemd/system/eduagro.service` para usar `EnvironmentFile=/home/gabi/apps/eduagro/.env` y remover las líneas `Environment="..."` inline.
   - Ejecutar `sudo systemctl daemon-reload` y `sudo systemctl restart eduagro`.

3. **Configuración de Storage Privado y `.gitignore`:**
   - Definir `DOCUMENT_STORAGE_ROOT=/home/gabi/apps/eduagro/data/uploads` dentro del `.env` de producción.
   - Asegurar que `.gitignore` contenga `.env`, `data/` y `DEPLOYMENT.md`.

4. **Ajuste de Nginx (`client_max_body_size`):**
   - Configurar `client_max_body_size 12M;` dentro del bloque `server` de EduAgro en `/etc/nginx/sites-available/eduagro`.
   - Validar sintaxis (`sudo nginx -t`) y recargar (`sudo systemctl reload nginx`).

5. **Actualización del Cronjob de Backup:**
   - Actualizar el script de backup en la VPS para empaquetar en un archivo `.tar.gz` la base de datos PostgreSQL y la carpeta de uploads `data/uploads`.

---

## 11. Comandos Propuestos para Ejecutar en VPS (Fase Posterior)

### Seguros y Reversibles
```bash
# 1. Asegurar permisos restringidos en .env
chmod 600 /home/gabi/apps/eduagro/.env

# 2. Verificar sintaxis de Nginx tras editar client_max_body_size
sudo nginx -t
```

### Requieren Restart / Daemon-Reload
```bash
# 3. Recargar systemd y reiniciar EduAgro tras configurar EnvironmentFile
sudo systemctl daemon-reload
sudo systemctl restart eduagro

# 4. Recargar Nginx
sudo systemctl reload nginx
```

---

## 12. Rollback por Cada Cambio Propuesto

- **Rollback de Systemd:** Restaurar copia de respaldo de `/etc/systemd/system/eduagro.service.bak`, ejecutar `sudo systemctl daemon-reload` y `sudo systemctl restart eduagro`.
- **Rollback de Nginx:** Restaurar copia `/etc/nginx/sites-available/eduagro.bak`, ejecutar `sudo nginx -t` y `sudo systemctl reload nginx`.
- **Rollback de Credenciales:** En caso de falla de conexión a la DB tras rotar contraseña, revertir el hash/contraseña del usuario PostgreSQL mediante `ALTER USER eduagro_user WITH PASSWORD '...';`.

---

## 13. Checklist Post-Hardening

- [ ] Secretos removidos de `DEPLOYMENT.md` y de `/etc/systemd/system/eduagro.service`.
- [ ] `/home/gabi/apps/eduagro/.env` configurado con permisos `0600` conteniendo `DOCUMENT_STORAGE_ROOT=/home/gabi/apps/eduagro/data/uploads`.
- [ ] `systemctl status eduagro` no muestra contraseñas ni variables inline.
- [ ] `client_max_body_size 12M;` activo en Nginx.
- [ ] Directiva `location /uploads` ausente en Nginx (acceso estático bloqueado).
- [ ] Subida de archivo PDF/imagen realizada exitosamente desde la app.
- [ ] Intento de acceso directo por URL estática rebotado con HTTP 404 por Nginx.
- [ ] Backup automático (`.sql.gz` + `uploads.tar.gz`) probado y validado.

---

## 14. Datos que No Pudieron Revisarse por Falta de Acceso Directo a VPS

- Configuración en vivo del firewall UFW (`sudo ufw status`) y Fail2ban.
- Permisos reales del archivo `/home/gabi/apps/eduagro/.env` en el filesystem remoto de la VPS.
- Cronjobs configurados bajo el usuario `postgres` o `root` en la VPS.

---

## 15. Confirmación de No Cambios

Se confirma expresamente que durante esta auditoría:
- **No se realizaron modificaciones de código ni de configuración en el servidor VPS.**
- **No se crearon directorios ni se alteraron permisos en el servidor de producción.**
- **No se imprimieron ni registraron secretos ni credenciales sensibles.**
