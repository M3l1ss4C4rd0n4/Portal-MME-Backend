# 🏛️ ARQUITECTURA: Plataforma Multi-Dashboard (Portal de Dirección)

## 📊 Visión General

**Portal de Dirección MME** - Plataforma centralizada de Business Intelligence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PORTAL DE DIRECCIÓN (Home)                               │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐   │
│  │  GESTIÓN    │  EJECUCIÓN  │ COMUNIDADES │ SUPERVISIÓN │  SUBSIDIOS  │   │
│  │   SECTOR    │ PRESUPUESTAL│  ENERGÉTICAS│             │             │   │
│  │  (XM)       │   2026      │             │             │             │   │
│  └──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘   │
│         │             │             │             │             │          │
│         ▼             ▼             ▼             ▼             ▼          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Dashboard│ │ Dashboard│ │ Dashboard│ │ Dashboard│ │ Dashboard│        │
│  │  XM API  │ │  CSV/Excel│ │  CSV/Excel│ │  CSV/Excel│ │  CSV/Excel│        │
│  │  (Existe)│ │  (Nuevo) │ │  (Nuevo) │ │  (Nuevo) │ │  (Nuevo) │        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estructura de Carpetas - Arquitectura Multi-Tenant

```
portal-direccion-mme/
│
├── 📁 apps/                          # Aplicaciones (monorepo)
│   │
│   ├── 📁 portal-web/                # Portal Principal (Next.js/React)
│   │   ├── app/
│   │   │   ├── page.tsx              # Home con KPIs agregados
│   │   │   ├── layout.tsx            # Layout principal
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── DashboardCard/        # Cards del home (como en imagen)
│   │   │   ├── KpiWidget/            # Widgets individuales
│   │   │   └── Navigation/           # Navegación entre dashboards
│   │   └── package.json
│   │
│   ├── 📁 dashboard-xm/              # Dashboard Energía (actual)
│   │   ├── src/
│   │   │   ├── pages/                # Transmisión, Generación, etc.
│   │   │   ├── components/
│   │   │   └── services/             # API client
│   │   └── package.json
│   │
│   ├── 📁 dashboard-presupuesto/     # Ejecución Presupuestal 2026
│   │   └── src/
│   │
│   ├── 📁 dashboard-comunidades/     # Comunidades Energéticas
│   │   └── src/
│   │
│   ├── 📁 dashboard-supervision/     # Supervisión de Contratos
│   │   └── src/
│   │
│   └── 📁 dashboard-subsidios/       # Subsidios
│       └── src/
│
├── 📁 packages/                      # Librerías compartidas
│   │
│   ├── 📁 ui/                        # Design System (componentes compartidos)
│   │   ├── src/
│   │   │   ├── components/
│   │   │   │   ├── Button/
│   │   │   │   ├── Card/
│   │   │   │   ├── Chart/            # Gráficas unificadas
│   │   │   │   ├── Map/              # Mapas (Leaflet/Mapbox)
│   │   │   │   ├── KpiGauge/         # Gauge charts (como en imagen)
│   │   │   │   ├── DataTable/
│   │   │   │   └── Modal/
│   │   │   ├── theme/                # Colores MME, tipografía
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── 📁 data-access/               # Clientes API unificados
│   │   ├── src/
│   │   │   ├── clients/
│   │   │   │   ├── xm-api.ts         # Cliente API XM
│   │   │   │   ├── csv-parser.ts     # Parser de CSVs
│   │   │   │   └── excel-parser.ts   # Parser de Excel
│   │   │   └── hooks/                # React Query hooks
│   │   └── package.json
│   │
│   └── 📁 config/                    # Configuración compartida
│       ├── eslint-config/
│       ├── ts-config/
│       └── tailwind-config/
│
├── 📁 api/                           # Backend API Gateway (FastAPI)
│   ├── gateways/
│   │   ├── xm_gateway.py             # Proxy a datos XM
│   │   ├── csv_gateway.py            # Lectura de CSVs
│   │   └── excel_gateway.py          # Lectura de Excels
│   ├── connectors/
│   │   ├── postgresql/               # Conexión a BD XM
│   │   └── file-storage/             # Storage de archivos CSV/Excel
│   └── main.py
│
├── 📁 data/                          # Fuentes de datos
│   ├── xm/                           # Scripts ETL XM (existentes)
│   ├── presupuesto/
│   │   ├── raw/                      # CSVs/Excels originales
│   │   └── processed/                # Datos procesados
│   ├── comunidades/
│   ├── supervision/
│   └── subsidios/
│
├── 📁 infra/                         # Docker, K8s, Terraform
│   ├── docker/
│   └── kubernetes/
│
└── turbo.json                        # Orquestación monorepo
```

---

## 🏛️ Arquitectura de Componentes - Design System

### Componentes del Portal Home (basado en imagen ArcGIS)

```typescript
// packages/ui/src/components/DashboardCard/DashboardCard.tsx
interface DashboardCardProps {
  title: string;           // "GESTIÓN DEL SECTOR"
  icon: string;            // Icono del tema
  kpiSections: {
    label: string;         // "Precio de bolsa"
    value: string | number; // "$332.2"
    unit?: string;         // "COP/kWh"
    trend?: 'up' | 'down' | 'neutral';
    sparkline?: number[];  // Mini gráfico
  }[];
  subSections?: {
    title: string;         // "Contratos OR 2025"
    metrics: Metric[];
  }[];
  link: string;            // URL al dashboard detallado
  theme: 'dark' | 'light';
}
```

### Componentes Visuales Reutilizables

```typescript
// packages/ui/src/components/
│
├── KpiGauge/              // Gauge semicircular (66%, 53.29%, etc.)
├── SparkLine/             // Mini gráficos de línea
├── MetricCard/            // KPI con icono y valor
├── ProgressBar/           // Barras de progreso
├── CountUpNumber/         // Animación de números
├── StatusBadge/           // Badges de estado
├── MiniChart/             // Gráficos pequeños
└── DataGrid/              // Tablas con sorting/filtering
```

---

## 🎨 Sistema de Diseño - Tema Institucional MME

### Paleta de Colores (Dark Theme - como imagen)

```css
:root {
  /* Colores Primarios */
  --mme-gold: #F5A623;           /* Destacados, títulos */
  --mme-gold-light: #FFB84D;     /* Hover */
  
  /* Backgrounds */
  --bg-primary: #0A0E17;         /* Fondo principal */
  --bg-card: #111827;            /* Tarjetas */
  --bg-elevated: #1A2234;        /* Elevación */
  
  /* Texto */
  --text-primary: #FFFFFF;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
  
  /* Métricas */
  --metric-high: #10B981;        /* Verde - bueno */
  --metric-medium: #F5A623;      /* Amarillo - advertencia */
  --metric-low: #EF4444;         /* Rojo - crítico */
  
  /* Gráficas */
  --chart-primary: #3B82F6;
  --chart-secondary: #F5A623;
  --chart-tertiary: #10B981;
}
```

### Tipografía
- **Títulos:** Inter Bold
- **KPIs:** Inter Bold/Heavy
- **Labels:** Inter Medium
- **Datos:** Inter Regular

---

## 📊 Arquitectura de Datos

### Conectores de Datos (Data Sources)

```typescript
// packages/data-access/src/connectors/
│
├── XmConnector.ts              // API XM (datos energía)
├── CsvConnector.ts             // Archivos CSV
├── ExcelConnector.ts           // Archivos Excel
├── DatabaseConnector.ts        // PostgreSQL
└── FileSystemConnector.ts      // Archivos locales
```

### Configuración por Dashboard

```typescript
// Configuración declarativa de cada dashboard
const dashboardConfig = {
  gestionSector: {
    name: 'Gestión del Sector',
    icon: 'energy',
    dataSource: 'xm-api',
    refreshInterval: 300000, // 5 minutos
    kpis: ['precio_bolsa', 'generacion', 'embalces'],
    link: '/dashboards/energia'
  },
  
  ejecucionPresupuestal: {
    name: 'Ejecución Presupuestal',
    icon: 'budget',
    dataSource: 'csv',
    filePattern: 'Matriz_Ejecucion_Presupuestal_*.xlsx',
    refreshInterval: 86400000, // 24 horas
    kpis: ['apropiacion', 'comprometido', 'obligado'],
    gauges: ['% comprometido', '% obligado'],
    link: '/dashboards/presupuesto'
  },
  
  comunidadesEnergeticas: {
    name: 'Comunidades Energéticas',
    icon: 'community',
    dataSource: 'csv',
    files: [
      'Seguimiento_Completo_CE_Contratos.xlsx',
      'Resumen_Implementacion.xlsx'
    ],
    kpis: ['ce_implementadas', 'inversion', 'capacidad'],
    link: '/dashboards/comunidades'
  },
  
  supervision: {
    name: 'Supervisión',
    icon: 'supervision',
    dataSource: 'csv',
    filePattern: 'Matriz_General_de_Reparto.xlsx',
    kpis: ['contratos', 'proyectos', 'avance_fisico', 'avance_financiero'],
    gauges: ['avance fisico %', 'avance financiero %'],
    link: '/dashboards/supervision'
  },
  
  subsidios: {
    name: 'Subsidios',
    icon: 'subsidy',
    dataSource: 'csv',
    filePattern: 'Base_Subsidios_DDE.xlsx',
    kpis: ['deficit_acumulado', 'valor_pendiente', 'resoluciones'],
    link: '/dashboards/subsidios'
  }
};
```

---

## 🛠️ Stack Tecnológico Recomendado

### Frontend
| Tecnología | Uso | Por qué |
|------------|-----|---------|
| **Next.js 14** | Framework | SSR, App Router, optimización |
| **TypeScript** | Lenguaje | Type safety, mejor DX |
| **Tailwind CSS** | Styling | Rápido, consistente, dark mode fácil |
| **shadcn/ui** | Componentes Base | Accesible, customizable |
| **Tremor** | Dashboard Components | Charts, metrics cards (hecho para dashboards) |
| **TanStack Query** | Data Fetching | Caching, revalidación, offline |
| **Zustand** | State Management | Simple, efectivo |
| **Recharts/Plotly.js** | Gráficas | Flexible, React-friendly |
| **React-Leaflet** | Mapas | Mapas interactivos |
| **Framer Motion** | Animaciones | Transiciones suaves |

### Backend
| Tecnología | Uso |
|------------|-----|
| **FastAPI** | API Gateway |
| **Pandas** | Procesamiento CSV/Excel |
| **Openpyxl/XLRD** | Lectura Excel |
| **Celery** | Tareas background (ETL) |
| **Redis** | Cache y broker |
| **PostgreSQL** | Datos estructurados |
| **MinIO/S3** | Almacenamiento archivos |

### DevOps
| Tecnología | Uso |
|------------|-----|
| **Turborepo** | Monorepo management |
| **Docker** | Contenedores |
| **GitHub Actions** | CI/CD |
| **Vercel** | Hosting frontend |
| **AWS/GCP** | Infraestructura |

---

## 🚀 Plantillas y Recursos Aceleradores

### Plantillas Dashboard (comprar/modificar)

1. **Tremor.so** (Recomendado #1)
   - Componentes React para dashboards
   - Métricas, charts, gauges
   - Dark mode nativo
   - Gratis/Open source

2. **Material Tailwind Pro**
   - Componentes Material Design
   - Dashboard templates

3. **Creative Tim - Dashboard Templates**
   - Next.js Dashboards
   - Black Dashboard, Argon Dashboard

4. **AdminJS** (Si necesitas panel de admin)
   - Auto-genera admin panels
   - Conecta a cualquier BD

### Recursos UI Específicos

```bash
# Tremor (gratis)
npm install @tremor/react

# Componentes de métricas/gauges
npm install react-circular-progressbar
npm install recharts

# Mapas
npm install react-leaflet leaflet

# Tablas avanzadas
npm install @tanstack/react-table

# Fechas
npm install date-fns

# Animaciones
npm install framer-motion
```

---

## 📅 Plan de Implementación Actualizado

### FASE 0: Setup y Arquitectura (2 semanas)
- [ ] Setup Turborepo + Next.js
- [ ] Configurar Design System (colores MME)
- [ ] Componentes base: Card, Kpi, Gauge, Chart
- [ ] Layout del Portal Home (igual que imagen ArcGIS)

### FASE 1: Conectores de Datos (1 semana)
- [ ] Connector XM API (reutilizar existente)
- [ ] Connector CSV/Excel
- [ ] Sistema de caché
- [ ] Refresh automático

### FASE 2: Portal Home (1 semana)
- [ ] Home page con 5 cards (como imagen)
- [ ] KPIs estáticos conectados a datos reales
- [ ] Navegación entre dashboards
- [ ] Responsive

### FASE 3: Dashboard XM (migración, 2 semanas)
- [ ] Migrar página por página
- [ ] Mantener funcionalidad actual

### FASE 4: Nuevos Dashboards (4 semanas)
- [ ] Presupuesto
- [ ] Comunidades
- [ ] Supervisión
- [ ] Subsidios

### FASE 5: Polish (1 semana)
- [ ] Animaciones
- [ ] Dark mode refinado
- [ ] Optimización performance

**Total: 11 semanas (~3 meses)**

---

## ❓ Preguntas Clave

Antes de empezar, necesito saber:

1. **¿Tienes acceso a los archivos CSV/Excel ya?**
   - ¿Dónde están alojados?
   - ¿Se actualizan manualmente o automáticamente?

2. **¿Necesitas autenticación?**
   - ¿Diferentes usuarios ven diferentes dashboards?
   - ¿O es público para todos?

3. **¿Presupuesto para plantillas/licencias?**
   - Tremor es gratis
   - Algunas plantillas premium cuestan $50-200

4. **¿Equipo de desarrollo?**
   - ¿Solo tú o hay más developers?
   - ¿Conocimientos de React/TypeScript?

5. **¿Timeline crítico?**
   - ¿Hay una fecha de entrega específica?

**¿Empezamos con el setup de esta arquitectura multi-dashboard?**
