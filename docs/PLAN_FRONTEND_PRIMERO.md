# 🎨 PLAN: Frontend Primero con Datos de Prueba (Mock Data)

## 📋 Estrategia: "Visual First, Data Later"

### Fase 1: Frontend + Mock Data (Semanas 1-3)
✅ Construir UI con datos de prueba realistas  
✅ Validar arquitectura y componentes  
✅ Iterar diseño sin depender de backend  

### Fase 2: Conexión Datos Reales (Semana 4+)
✅ Compartir archivos OneDrive  
✅ Crear scripts ETL  
✅ Reemplazar mocks por datos reales  

---

## 🎯 Ventajas de este Enfoque

| Aspecto | Beneficio |
|---------|-----------|
| **Velocidad** | Ver resultados visuales en días, no semanas |
| **Iteración** | Cambiar diseño sin tocar datos complejos |
| **Validación** | Probar UX antes de invertir en ETL |
| **Paralelismo** | Tú revisas UI mientras yo preparo parsers de Excel |
| **Riesgo bajo** | Si algo no funciona visualmente, se detecta temprano |

---

## 📊 Datos de Prueba (Mock Data) por Dashboard

### 1. Portal Home (5 Cards)

```typescript
// mocks/home-data.ts
export const homeDashboardData = {
  gestionSector: {
    title: "Gestión del Sector",
    kpis: [
      { label: "Precio de bolsa", value: 332.2, unit: "COP/kWh", trend: "up" },
      { label: "Energía Generada", value: 245.5, unit: "GWh", trend: "up" },
    ],
    gauges: [
      { label: "% Embalses", value: 66, color: "amber" },
    ],
    lastUpdate: "2026-03-24T02:00:00",
    link: "/dashboards/energia"
  },
  
  ejecucionPresupuestal: {
    title: "Ejecución Presupuestal 2026",
    apropiacion: 7105844200047,
    comprometido: 2396981420251,
    obligado: 6028108212,
    gauges: [
      { label: "% Comprometido", value: 33.7, color: "amber" },
      { label: "% Obligado", value: 0.08, color: "gray" },
    ],
    link: "/dashboards/presupuesto"
  },
  
  comunidadesEnergeticas: {
    title: "Comunidades Energéticas",
    kpis: [
      { label: "CE Implementadas", value: 469, icon: "🏘️" },
      { label: "Inversión Estimada", value: 290379880159.74, unit: "$", format: "currency" },
      { label: "Capacidad", value: 12837.12, unit: "kWp" },
    ],
    subSection: {
      title: "Contratos OR 2025",
      avanceFinanciero: 53.29,
      avanceGeneral: 16.0,
      contratos: 17,
      usuarios: 295911,
      ce: 2297,
      inversionTotal: 914360289397,
      potenciaInstalar: 37.0
    },
    link: "/dashboards/comunidades"
  },
  
  supervision: {
    title: "Supervisión",
    kpis: [
      { label: "No. Contratos", value: 840 },
      { label: "No. Proyectos", value: 2426 },
    ],
    subKpis: [
      { label: "Contratos en ejecución", value: 319 },
      { label: "Contratos liquidados", value: 295 },
    ],
    gauges: [
      { label: "Avance Físico", value: 87, color: "amber" },
      { label: "Avance Financiero", value: 85, color: "amber" },
    ],
    link: "/dashboards/supervision"
  },
  
  subsidios: {
    title: "Subsidios",
    deficitAcumulado: 3469667088497,
    resoluciones: {
      2025: { expedidas: 78, valorAsignado: 3272346470818 },
      2026: { expedidas: 10, valorAsignado: 1444288578199 }
    },
    pendientes: {
      2025: 0,
      2026: 1172216464039
    },
    link: "/dashboards/subsidios"
  }
};
```

### 2. Dashboard Presupuesto (Mock)

```typescript
// mocks/presupuesto-data.ts
export const presupuestoData = {
  resumen: {
    apropiacionTotal: 7105844200047,
    comprometido: 2396981420251,
    obligado: 6028108212,
    saldo: 4708836079828
  },
  
  avanceMensual: [
    { mes: "Ene", comprometido: 15, obligado: 2 },
    { mes: "Feb", comprometido: 22, obligado: 3 },
    { mes: "Mar", comprometido: 33.7, obligado: 0.08 },
    // ... hasta Dic
  ],
  
  rubros: [
    { nombre: "Funcionamiento", apropiacion: 1200000000000, ejecutado: 35 },
    { nombre: "Inversión", apropiacion: 4500000000000, ejecutado: 28 },
    { nombre: "Servicio Deuda", apropiacion: 1405844200047, ejecutado: 42 },
  ],
  
  alertas: [
    { tipo: "warning", mensaje: "Rubro Inversión por debajo del 30%" },
  ]
};
```

### 3. Dashboard Comunidades (Mock)

```typescript
// mocks/comunidades-data.ts
export const comunidadesData = {
  resumen: {
    totalCE: 469,
    implementadas: 312,
    construccion: 89,
    planeacion: 68,
    inversionTotal: 290379880159.74,
    capacidadTotal: 12837.12,
    usuarios: 295911,
    co2Evitado: 45000 // toneladas
  },
  
  porDepartamento: [
    { depto: "Antioquia", ce: 45, inversion: 45000000000 },
    { depto: "Cundinamarca", ce: 38, inversion: 38000000000 },
    { depto: "Valle del Cauca", ce: 32, inversion: 32000000000 },
    // ... más departamentos
  ],
  
  contratosOR2025: {
    total: 17,
    usuarios: 295911,
    ce: 2297,
    inversion: 914360289397,
    potencia: 37.0,
    avance: {
      financiero: 53.29,
      fisico: 16.0
    }
  },
  
  evolucionTemporal: [
    { anio: 2021, ce: 45 },
    { anio: 2022, ce: 120 },
    { anio: 2023, ce: 245 },
    { anio: 2024, ce: 380 },
    { anio: 2025, ce: 469 },
  ]
};
```

### 4. Dashboard Supervisión (Mock)

```typescript
// mocks/supervision-data.ts
export const supervisionData = {
  resumen: {
    totalContratos: 840,
    enEjecucion: 319,
    liquidados: 295,
    enLicitacion: 226
  },
  
  avances: {
    fisico: 87,
    financiero: 85,
    tiempo: 92
  },
  
  proyectos: [
    { 
      id: "PRY-001",
      nombre: "Ampliación Subestación Bogotá",
      contratista: "Empresa Eléctrica XYZ",
      valor: 25000000000,
      avanceFisico: 92,
      avanceFinanciero: 88,
      estado: "En ejecución",
      alerta: false
    },
    { 
      id: "PRY-002",
      nombre: "Línea Transmisión 500kV",
      contratista: "Consorcio ABC",
      valor: 180000000000,
      avanceFisico: 45,
      avanceFinanciero: 60,
      estado: "En ejecución",
      alerta: true // Atrasado
    },
    // ... más proyectos
  ]
};
```

### 5. Dashboard Subsidios (Mock)

```typescript
// mocks/subsidios-data.ts
export const subsidiosData = {
  resumen: {
    deficitAcumulado: 3469667088497,
    resoluciones2025: { cantidad: 78, valor: 3272346470818 },
    resoluciones2026: { cantidad: 10, valor: 1444288578199 },
    pendientePago2025: 0,
    pendientePago2026: 1172216464039
  },
  
  evolucionMensual: [
    { mes: "Ene", subsidio: 45000000000, usuarios: 12500000 },
    { mes: "Feb", subsidio: 42000000000, usuarios: 12450000 },
    // ... más meses
  ],
  
  porEstrato: [
    { estrato: 1, subsidio: 1200000000000, porcentaje: 45 },
    { estrato: 2, subsidio: 980000000000, porcentaje: 32 },
    { estrato: 3, subsidio: 450000000000, porcentaje: 15 },
    { estrato: "Comercial", subsidio: 280000000000, porcentaje: 8 },
  ],
  
  alertas: [
    { nivel: "critical", mensaje: "Déficit acumulado supera 3.4 billones" },
    { nivel: "warning", mensaje: "Resoluciones 2026 con retraso" },
  ]
};
```

---

## 🏗️ Estructura del Proyecto (Mock-First)

```
portal-direccion-mme/
├── src/
│   ├── app/
│   │   ├── page.tsx                    # Home con 5 cards
│   │   ├── layout.tsx
│   │   └── (dashboards)/
│   │       ├── energia/
│   │       ├── presupuesto/
│   │       ├── comunidades/
│   │       ├── supervision/
│   │       └── subsidios/
│   │
│   ├── components/
│   │   ├── ui/                         # Componentes base
│   │   │   ├── DashboardCard.tsx       # Card del home
│   │   │   ├── KpiGauge.tsx           # Gauge semicircular
│   │   │   ├── MetricValue.tsx        # Valor grande animado
│   │   │   ├── SparkLine.tsx          # Mini gráfico
│   │   │   └── ProgressBar.tsx        # Barra de progreso
│   │   │
│   │   └── dashboard/                  # Componentes específicos
│   │       ├── FilterBar.tsx
│   │       ├── DataTable.tsx
│   │       └── ChartCard.tsx
│   │
│   ├── mocks/                          # 📊 DATOS DE PRUEBA
│   │   ├── home-data.ts
│   │   ├── presupuesto-data.ts
│   │   ├── comunidades-data.ts
│   │   ├── supervision-data.ts
│   │   └── subsidios-data.ts
│   │
│   ├── hooks/                          # Hooks con datos mock
│   │   ├── useHomeData.ts
│   │   ├── usePresupuestoData.ts
│   │   └── ...
│   │
│   └── lib/
│       └── utils.ts
│
├── public/
│   └── logo-mme.png
│
└── package.json
```

---

## 🎨 Componentes UI a Construir

### Componentes Base (Semana 1)

1. **DashboardCard** - Card del home con KPIs y gauges
2. **KpiGauge** - Gauge semicircular (como en imagen: 66%, 53%)
3. **MetricValue** - Número grande con animación
4. **SparkLine** - Mini gráfico de tendencia
5. **ProgressBar** - Barra de progreso con porcentaje

### Componentes Dashboard (Semana 2)

1. **FilterBar** - Barra de filtros por fecha/región
2. **DataTable** - Tabla con sorting y filtros
3. **ChartCard** - Contenedor de gráficas
4. **MapCard** - Mapa con marcadores
5. **AlertBanner** - Banner de alertas/notificaciones

---

## ✅ Criterios de "Listo para Datos Reales"

Antes de conectar los Excel de OneDrive, validamos:

- [ ] **Home page** se ve exactamente como la imagen de ArcGIS
- [ ] **5 Cards** con datos mock se ven profesionales
- [ ] **Navegación** funciona entre dashboards
- [ ] **Responsive** en móvil, tablet y desktop
- [ ] **Dark mode** consistente en toda la app
- [ ] **Animaciones** fluidas (carga, transiciones)
- [ ] **Tema MME** aplicado correctamente (colores, tipografía)

---

## 🚀 Plan de 3 Semanas (Frontend + Mock Data)

### Semana 1: Setup + Componentes Base
- [ ] Crear proyecto Next.js
- [ ] Instalar Tremor UI
- [ ] Configurar tema MME (dark)
- [ ] Crear componentes base (DashboardCard, KpiGauge, MetricValue)
- [ ] Crear mock data para Home

**Entregable:** Home page con 5 cards funcionando con datos de prueba

### Semana 2: Dashboards + Mock Data
- [ ] Crear páginas de cada dashboard
- [ ] Mock data para cada dashboard
- [ ] Componentes específicos (tablas, gráficas)
- [ ] Navegación completa

**Entregable:** Todos los dashboards navegables con datos de prueba

### Semana 3: Polish + Validación Visual
- [ ] Animaciones con Framer Motion
- [ ] Responsive design
- [ ] Ajustes visuales según feedback
- [ ] Testing en diferentes dispositivos

**Entregable:** Portal visual completo, listo para conectar datos reales

**Luego:** Compartes archivos OneDrive y empezamos Fase 2 (datos reales)

---

## ❓ Checklist para Empezar Mañana

Confirmar:

- [ ] **¿Empezamos mañana con este plan?**
- [ ] **¿Tienes la imagen de ArcGIS para referencia visual?** (para copiar exactamente)
- [ ] **¿Tienes acceso a logos/oficialidad MME?** (logo ministerio para el header)
- [ ] **¿Hay algún color específico adicional?** (más allá del gold #F5A623)

**Si todo es SÍ:** Mañana ejecuto el script de setup y empezamos con el Home page 🚀
