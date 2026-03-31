# 🚀 PLAN DE IMPLEMENTACIÓN REAL - Portal Dirección MME

## 📋 Contexto Confirmado

| Aspecto | Situación | Solución |
|---------|-----------|----------|
| **Datos** | Excel local | Subir a PostgreSQL |
| **Actualización** | Manual (OneDrive) | Automatizar con OneDrive API |
| **Auth** | Correo ministerio | Azure AD (gratis con Office 365) |
| **Presupuesto** | $0 | Open source + servicios existentes |
| **Timeline** | Flexible | Priorizar funcionalidad sobre velocidad |
| **Equipo** | 1 persona | Arquitectura simple y documentada |

---

## 🏗️ Arquitectura Recomendada: "Single App + Multi-Database"

### Por qué esta arquitectura:
- ✅ **Simple**: Un solo proyecto Next.js (fácil de mantener sola)
- ✅ **Escalable**: Agregar dashboards es copiar y pegar
- ✅ **Gratis**: Todo open source o servicios incluidos
- ✅ **Automatizable**: OneDrive sync automático

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEXT.JS APP (Single Deploy)                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐    │
│  │  Portal Home │ │  Dashboard   │ │   Dashboard          │    │
│  │  (5 cards)   │ │  Energía     │ │   Presupuesto        │    │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────────────┘    │
│         │                │                │                     │
│         └────────────────┴────────────────┘                     │
│                          │                                      │
│              ┌───────────┴───────────┐                          │
│              │   Tremor UI (gratis)   │                          │
│              │   Components           │                          │
│              └────────────────────────┘                          │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────┼──────────────────────────────┐
│                                  │                               │
│  ┌───────────────────────────────┴───────────────────────────┐   │
│  │              API ROUTES (Next.js API)                     │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │   │
│  │  │ /api/xm  │ │/api/pres │ │/api/com  │ │/api/subs │     │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘     │   │
│  └───────┼────────────┼────────────┼────────────┼────────────┘   │
│          │            │            │            │                 │
│  ┌───────┴────────────┴────────────┴────────────┴────────────┐   │
│  │              POSTGRESQL (Base de Datos Única)              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │   │
│  │  │  xm_*    │ │presup_*  │ │comun_*   │ │subsid_*  │     │   │
│  │  │  tables  │ │  tables  │ │  tables  │ │  tables  │     │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │              ETL/SCRIPTS (Python - mismo server)           │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │   │
│  │  │ OneDrive │ │  Parse   │ │  Transform│ │  Load    │     │   │
│  │  │  Sync    │ │  Excel   │ │   Data    │ │  to DB   │     │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🗂️ Estructura de Carpetas (Simple y Práctica)

```
portal-direccion-mme/
│
├── 📁 src/
│   │
│   ├── 📁 app/                          # Next.js App Router
│   │   ├── page.tsx                     # Portal Home (5 cards)
│   │   ├── layout.tsx                   # Layout con auth
│   │   ├── globals.css                  # Tema MME
│   │   │
│   │   ├── 📁 (dashboards)/             # Grupo de dashboards
│   │   │   ├── 📁 energia/
│   │   │   │   ├── page.tsx             # Dashboard XM
│   │   │   │   └── layout.tsx
│   │   │   ├── 📁 presupuesto/
│   │   │   │   ├── page.tsx             # Ejecución Presupuestal
│   │   │   │   └── layout.tsx
│   │   │   ├── 📁 comunidades/
│   │   │   │   └── page.tsx             # Comunidades Energéticas
│   │   │   ├── 📁 supervision/
│   │   │   │   └── page.tsx             # Supervisión
│   │   │   └── 📁 subsidios/
│   │   │       └── page.tsx             # Subsidios
│   │   │
│   │   └── 📁 api/                      # API Routes
│   │       ├── 📁 auth/
│   │       │   └── [...nextauth]/route.ts  # Azure AD Auth
│   │       ├── 📁 xm/
│   │       │   └── route.ts             # Datos XM
│   │       ├── 📁 presupuesto/
│   │       │   └── route.ts             # Datos Presupuesto
│   │       ├── 📁 comunidades/
│   │       │   └── route.ts             # Datos Comunidades
│   │       ├── 📁 supervision/
│   │       │   └── route.ts             # Datos Supervisión
│   │       └── 📁 subsidios/
│   │           └── route.ts             # Datos Subsidios
│   │
│   ├── 📁 components/
│   │   ├── 📁 ui/                       # Componentes base
│   │   │   ├── DashboardCard.tsx        # Card del home
│   │   │   ├── KpiGauge.tsx             # Gauge semicircular
│   │   │   ├── MetricValue.tsx          # Valor grande con animación
│   │   │   ├── SparkLine.tsx            # Mini gráfico
│   │   │   └── Navigation.tsx           # Menú de navegación
│   │   │
│   │   ├── 📁 dashboard/                # Componentes de dashboard
│   │   │   ├── FilterBar.tsx
│   │   │   ├── DataTable.tsx
│   │   │   ├── ChartCard.tsx
│   │   │   └── MapCard.tsx
│   │   │
│   │   └── 📁 home/                     # Componentes del home
│   │       ├── KpiCard.tsx              # Card con KPI
│   │       ├── GaugeSection.tsx         # Sección con gauges
│   │       └── DashboardGrid.tsx        # Grid de 5 cards
│   │
│   ├── 📁 lib/
│   │   ├── db.ts                        # Conexión PostgreSQL
│   │   ├── auth.ts                      # Config Azure AD
│   │   └── utils.ts                     # Utilidades
│   │
│   ├── 📁 hooks/
│   │   ├── useDashboardData.ts          # Fetch datos dashboard
│   │   └── useAuth.ts                   # Hook de autenticación
│   │
│   └── 📁 types/
│       ├── dashboard.ts                 # Tipos de dashboards
│       └── index.ts
│
├── 📁 scripts/                          # Scripts ETL
│   ├── 📁 etl/
│   │   ├── onedrive_sync.py             # Sync desde OneDrive
│   │   ├── parse_excel.py               # Parsear Excel
│   │   └── load_to_db.py                # Cargar a PostgreSQL
│   │
│   └── 📁 sql/                          # Scripts SQL
│       ├── create_tables_presupuesto.sql
│       ├── create_tables_comunidades.sql
│       ├── create_tables_supervision.sql
│       └── create_tables_subsidios.sql
│
├── 📁 public/                           # Assets estáticos
│   ├── logo-mme.png
│   └── favicon.ico
│
├── .env.local.example                   # Variables de entorno
├── next.config.js
├── tailwind.config.ts
├── package.json
└── README.md
```

---

## 🎨 Stack Tecnológico (Todo Gratis)

### Frontend
```json
{
  "dependencies": {
    "next": "14.x",                    // Framework (gratis)
    "react": "18.x",                   // UI (gratis)
    "@tremor/react": "latest",         // Componentes dashboard (gratis)
    "next-auth": "4.x",                // Auth con Azure AD (gratis)
    "recharts": "2.x",                 // Gráficas (gratis)
    "react-leaflet": "4.x",            // Mapas (gratis)
    "tailwindcss": "3.x",              // CSS (gratis)
    "framer-motion": "11.x",           // Animaciones (gratis)
    "@tanstack/react-query": "5.x",    // Data fetching (gratis)
    "date-fns": "3.x"                  // Fechas (gratis)
  }
}
```

### Backend/Database
- **PostgreSQL**: Ya lo tienes en el servidor
- **Next.js API Routes**: Incluido en Next.js (gratis)
- **Prisma** (opcional): ORM para PostgreSQL (gratis)

### Autenticación
- **Azure AD**: Incluido con Office 365 del ministerio (gratis)
- **Next-Auth**: Librería open source

### Sincronización OneDrive
- **Microsoft Graph API**: Gratis con cuenta Office 365
- **Python + Requests**: Descargar archivos automáticamente

---

## 📊 Esquema de Base de Datos

### Dashboard Presupuesto
```sql
CREATE TABLE presupuesto_resumen (
    id SERIAL PRIMARY KEY,
    anio INTEGER NOT NULL,
    apropiacion_total DECIMAL(18,2),
    comprometido DECIMAL(18,2),
    obligado DECIMAL(18,2),
    porcentaje_comprometido DECIMAL(5,2),
    porcentaje_obligado DECIMAL(5,2),
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE presupuesto_detalle (
    id SERIAL PRIMARY KEY,
    concepto VARCHAR(255),
    valor_comprometido DECIMAL(18,2),
    valor_obligado DECIMAL(18,2),
    fecha_movimiento DATE,
    fuente VARCHAR(50)
);
```

### Dashboard Comunidades Energéticas
```sql
CREATE TABLE comunidades_resumen (
    id SERIAL PRIMARY KEY,
    total_ce INTEGER,
    ce_implementadas INTEGER,
    inversion_total DECIMAL(18,2),
    capacidad_total_kw DECIMAL(10,2),
    usuarios_beneficiados INTEGER,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE comunidades_detalle (
    id SERIAL PRIMARY KEY,
    nombre_ce VARCHAR(255),
    departamento VARCHAR(100),
    municipio VARCHAR(100),
    estado VARCHAR(50), -- 'Implementada', 'En construcción', etc.
    capacidad_kw DECIMAL(10,2),
    inversion DECIMAL(18,2),
    usuarios INTEGER,
    fecha_implementacion DATE
);
```

### (Similar para Supervisión y Subsidios)

---

## 🔧 Proceso de Carga de Datos (Automatizado)

### Opción A: Script Manual (Inicio Rápido)
```bash
# 1. Subir Excel a servidor
scp presupuesto_2026.xlsx usuario@servidor:/tmp/

# 2. Ejecutar script de carga
python scripts/etl/load_excel_to_db.py \
  --file /tmp/presupuesto_2026.xlsx \
  --table presupuesto_resumen
```

### Opción B: Sync Automático desde OneDrive (Después)
```python
# scripts/etl/onedrive_sync.py
import requests
from office365.runtime.auth.authentication_context import AuthenticationContext
from office365.sharepoint.client_context import ClientContext

def sync_onedrive_files():
    """Descarga archivos de OneDrive y los carga a PostgreSQL"""
    
    # 1. Conectar a OneDrive (Graph API)
    # 2. Buscar archivos nuevos
    # 3. Descargar
    # 4. Parsear Excel
    # 5. Cargar a PostgreSQL
    # 6. Actualizar timestamp
    
    pass

# Ejecutar cada hora o cuando se solicite
if __name__ == "__main__":
    sync_onedrive_files()
```

---

## 🚀 Plan de Implementación Paso a Paso

### **SEMANA 1: Setup Inicial**
- [ ] Instalar Node.js y crear proyecto Next.js
- [ ] Instalar Tremor y componentes base
- [ ] Configurar Tailwind con colores MME
- [ ] Crear layout base con navegación

### **SEMANA 2: Portal Home + Auth**
- [ ] Crear página Home con 5 cards vacías
- [ ] Configurar Azure AD (Next-Auth)
- [ ] Componentes: DashboardCard, KpiGauge, MetricValue
- [ ] Responsive design

### **SEMANA 3: Dashboard Energía (Migración)**
- [ ] Migrar datos XM existentes
- [ ] Crear página /dashboards/energia
- [ ] Conectar con datos existentes
- [ ] Testear funcionalidad

### **SEMANA 4-5: Dashboard Presupuesto**
- [ ] Crear tablas en PostgreSQL
- [ ] Script para subir Excel a BD
- [ ] Crear página /dashboards/presupuesto
- [ ] Componentes específicos (gauges de porcentaje)

### **SEMANA 6-7: Dashboard Comunidades**
- [ ] Crear tablas
- [ ] Subir datos
- [ ] Crear página
- [ ] Mapa de Colombia con ubicaciones

### **SEMANA 8-9: Dashboard Supervisión**
- [ ] Tablas y datos
- [ ] Gráficas de avance físico/financiero
- [ ] Tablas de contratos

### **SEMANA 10: Dashboard Subsidios**
- [ ] Tablas y datos
- [ ] KPIs de subsidio
- [ ] Comparativos año vs año

### **SEMANA 11: Polish**
- [ ] Animaciones con Framer Motion
- [ ] Dark mode refinado
- [ ] Optimización de imágenes
- [ ] Testing

### **SEMANA 12: Deploy + Documentación**
- [ ] Deploy en servidor
- [ ] Documentación de uso
- [ ] Documentación de actualización de datos
- [ ] Capacitación (si aplica)

---

## 💻 Scripts de Setup (Para empezar mañana)

### Script 1: Setup Inicial
```bash
#!/bin/bash
# setup.sh - Ejecutar en el servidor

echo "🚀 Setup Portal Dirección MME"

# 1. Crear directorio
mkdir -p /home/admonctrlxm/portal-direccion
cd /home/admonctrlxm/portal-direccion

# 2. Inicializar proyecto Next.js
npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir

# 3. Instalar dependencias
npm install @tremor/react next-auth recharts react-leaflet framer-motion @tanstack/react-query date-fns

# 4. Instalar dependencias dev
npm install -D @types/leaflet

echo "✅ Proyecto creado"
echo "Siguiente paso: Configurar variables de entorno y empezar a desarrollar"
```

### Script 2: Crear Estructura
```bash
#!/bin/bash
# create-structure.sh

mkdir -p src/app/(dashboards)/{energia,presupuesto,comunidades,supervision,subsidios}
mkdir -p src/app/api/{auth/[...nextauth],xm,presupuesto,comunidades,supervision,subsidios}
mkdir -p src/components/{ui,dashboard,home}
mkdir -p src/{lib,hooks,types}
mkdir -p scripts/{etl,sql}
mkdir -p public

echo "✅ Estructura de carpetas creada"
```

---

## ❓ Decisiones que necesito de ti

### 1. **¿Quieres que empiece mañana?**
- [ ] SÍ - Ejecutar scripts de setup
- [ ] NO - Necesito revisar algo primero

### 2. **¿Tienes acceso para crear aplicación en Azure AD?**
- Necesitas permisos en el portal de Azure del ministerio
- O pedir a TI que te ayuden con la config de auth

### 3. **¿Quieres que priorice algún dashboard?**
- [ ] Presupuesto (parece más urgente)
- [ ] Comunidades (tiene mapas, más visual)
- [ ] Todos igual

### 4. **¿Tienes los archivos Excel listos para subir?**
- Si los tienes, puedo crear los scripts de importación primero

---

## 🎯 Resumen: Por qué esta arquitectura es perfecta para ti

| Necesidad | Solución |
|-----------|----------|
| **1 developer** | Un solo codebase Next.js |
| **$0 presupuesto** | Todo open source o incluido en Office 365 |
| **Múltiples dashboards** | Uno por carpeta, misma estructura |
| **Datos en Excel** | Scripts Python para importar automáticamente |
| **Actualización manual** | Botón "Actualizar datos" en cada dashboard |
| **Auth con correo ministerio** | Azure AD incluido gratis |
| **Bonita e interfaz moderna** | Tremor UI hecho para dashboards |
| **Fácil de mantener** | TypeScript + documentación + estructura clara |

---

**¿Empezamos mañana? Solo necesito el "SÍ" y ejecuto los scripts de setup.**
