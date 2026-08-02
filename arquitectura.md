# ERP Agropecuario - Contexto de Dominio y Arquitectura (Córdoba, Argentina)

## 1. Visión del Producto
Software ERP integral de gestión agropecuaria enfocado en pequeñas y medianas empresas familiares en la provincia de Córdoba (Argentina). El sistema busca unificar la operativa de campo ("sobre la camioneta") con la administración de servicios, trámites, logística y finanzas familiares en una única plataforma web.

## 2. Dominio Agropecuario (Córdoba, Argentina)
- [cite_start]**Cultivos Clave:** Trigo (Cultivo de invierno: mayo-julio a nov-dic) y Soja de 1ra / Soja de 2da (verano: oct-diciembre a marzo-mayo)[cite: 5, 6, 7, 8, 9].
- [cite_start]**Métrica de Rinde:** Quintales por hectárea (qq/ha) o Toneladas por hectárea (1 t = 10 qq)[cite: 9].
- **Comercialización y Fiscalidad:**
  - [cite_start]Emisión de CPE (Carta de Porte Electrónica) y CTG para traslado de granos[cite: 23].
  - [cite_start]Liquidación Primaria de Granos (LPG) para facturación y mermas[cite: 24, 26, 35].
  - [cite_start]Dolarización de insumos/costos ($USD/ha$) con conversión a $ARS$ al oficial[cite: 27, 36].
  - [cite_start]Canje agropecuario y gestión de vencimientos rurales (luz rural, patentes, arrendamientos)[cite: 32, 85].

## 3. Perfiles de Usuario Familares (Roles)
1. `admin`: Control total del sistema.
2. `productor`: Gestión de lotes, campañas, rotación y toma de decisiones agronómicas.
3. `operario_campo`: Acceso simplificado "Modo Campo" (carga rápida de lluvias, notas y labores).
4. `administrador_finanzas`: Gestión de cuentas, pagos de servicios, vencimientos, LPGs y facturación.

## 4. Stack Tecnológico
- [cite_start]**Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.0 (AsyncIO)[cite: 3, 94, 96].
- [cite_start]**Base de Datos:** PostgreSQL (aprovechando dialecto nativo JSONB, campos UUID y soporte PostGIS)[cite: 125, 126].
- [cite_start]**Frontend:** Jinja2 para servidor server-side / React + Tailwind CSS para componentes dinámicos y "Modo Campo"[cite: 3, 94, 103].
- [cite_start]**Infraestructura/Persistencia Local:** PWA / LocalStorage para soporte Offline-First en lotes con baja señal[cite: 51, 81, 111].