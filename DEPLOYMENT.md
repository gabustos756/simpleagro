# Guía de Despliegue (Deploy) - EduAgro

Este documento describe el procedimiento estándar para realizar despliegues (deploys) en el servidor VPS de producción/staging para la aplicación **EduAgro**.

## Flujo obligatorio de deploy

1. Backup de PostgreSQL.
2. Actualizar código desde la rama de deploy.
3. Reconstruir/actualizar dependencias si cambió requirements.txt.
4. Ejecutar migraciones: ./scripts/migrate.sh.
5. Ejecutar tests o smoke tests contra una base de testing.
6. Reiniciar systemd.
7. Verificar health check y módulos afectados.

---

## 📌 Datos de la Infraestructura

- **Dominio:** `eduagro.ggsolutions.com.ar`
- **Servidor VPS:** `vmi3481033` (Usuario SSH: `gabi`)
- **Directorio de la App:** `/home/gabi/apps/eduagro`
- **Rama de Despliegue:** `develop`
- **Puerto de Aplicación (Uvicorn):** `5051` (escuchando en `127.0.0.1:5051`)
- **Reverse Proxy:** Nginx
- **Gestor de Procesos:** Systemd (`eduagro.service`)
- **Base de Datos:** PostgreSQL (`database: eduagro`, `user: eduagro_user`)

---

## 🚀 Pasos para Realizar un Deploy Obligatorio (Rama `develop`)

Cada vez que realices cambios en el código y los subas a GitHub en la rama **`develop`**, sigue estrictamente esta secuencia en la VPS:

### 1. Conectarse a la VPS por SSH
```bash
ssh gabi@vmi3481033
```

### 2. Ir al directorio del proyecto
```bash
cd /home/gabi/apps/eduagro
```

### 3. Generar Copia de Seguridad Preventiva de PostgreSQL
```bash
mkdir -p ~/backups
pg_dump -U eduagro_user eduagro | gzip > ~/backups/eduagro_pre_deploy_$(date +%Y%m%d_%H%M%S).sql.gz
```

### 4. Obtener los últimos cambios de Git
```bash
git fetch origin develop
git reset --hard origin/develop
```

### 5. Activar entorno virtual e instalar dependencias
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 6. Ejecutar Script de Migraciones Versionadas de Alembic
```bash
./scripts/migrate.sh
```
> **⚠️ REGLA OBLIGATORIA DE SEGURIDAD:** Si `./scripts/migrate.sh` falla o devuelve exit code `1`, **ABORTAR INMEDIATAMENTE**. **NO REINICIAR UVICORN/SYSTEMD**.

### 7. Ejecutar Smoke Tests y Verificación de Esquema
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_schema_drift_and_migrations.py -v
```

### 8. Reiniciar el Servicio de la Aplicación
```bash
sudo systemctl restart eduagro
```

### 9. Health Check Final
```bash
curl -I http://127.0.0.1:5051/
sudo systemctl status eduagro --no-pager
```
Debe responder **`HTTP/1.1 200 OK`** (o 303 Redirect) y estado **`active (running)`**.

---

## 📜 Monitoreo y Logs en Tiempo Real

Para ver los logs de Uvicorn/FastAPI en vivo (útil para detectar errores tras un deploy):

```bash
sudo journalctl -u eduagro -f
```

Para ver las últimas 50 líneas del log:
```bash
sudo journalctl -u eduagro -n 50
```

---

## ⚙️ Referencia de Configuración de Systemd

El servicio está configurado en `/etc/systemd/system/eduagro.service`:

```ini
[Unit]
Description=EduAgro FastAPI Application
After=network.target postgresql.service

[Service]
User=gabi
WorkingDirectory=/home/gabi/apps/eduagro
Environment="DATABASE_URL=postgresql+asyncpg://eduagro_user:belu0420@localhost:5432/eduagro"
Environment="SESSION_SECRET=eduagro_secrect_vps_0420"
ExecStart=/home/gabi/apps/eduagro/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5051

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Si modificas el archivo del servicio, ejecuta:
```bash
sudo systemctl daemon-reload
sudo systemctl restart eduagro
```

---

## 🛠️ Solución de Problemas Frecuentes

### 1. Error de Permisos en PostgreSQL (`permission denied for table ...`)
Si al iniciar la app aparece un error de privilegios en tablas:
```bash
sudo -u postgres psql -d eduagro
```
Y ejecuta dentro de PostgreSQL:
```sql
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO eduagro_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO eduagro_user;
GRANT ALL ON SCHEMA public TO eduagro_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO eduagro_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO eduagro_user;
\q
```

### 2. Reiniciar Nginx
Si realizaste cambios en el proxy inverso de Nginx (`/etc/nginx/sites-available/`):
```bash
sudo nginx -t
sudo systemctl restart nginx
```
