# Guía de Despliegue (Deploy) - EduAgro

Este documento describe el procedimiento estándar para realizar despliegues (deploys) en el servidor VPS de producción/staging para la aplicación **EduAgro**.

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

## 🚀 Pasos para Realizar un Deploy (Rama `develop`)

Cada vez que realices cambios en el código y los subas a GitHub en la rama **`develop`**, sigue estos pasos en el servidor VPS:

### 1. Conectarse a la VPS por SSH
```bash
ssh gabi@vmi3481033
```

### 2. Ir al directorio del proyecto
```bash
cd /home/gabi/apps/eduagro
```

### 3. Cambiar a la rama `develop` y obtener los últimos cambios
```bash
git checkout develop
git pull origin develop
```

### 4. Activar el entorno virtual e instalar nuevas dependencias (si aplica)
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Reiniciar el servicio de la aplicación
```bash
uvicorn app.main:app --reload --port 8000
sudo systemctl restart eduagro
```

### 6. Verificar que la aplicación esté corriendo correctamente
```bash
sudo systemctl status eduagro
```
Debe mostrar el estado **`active (running)`**.

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
