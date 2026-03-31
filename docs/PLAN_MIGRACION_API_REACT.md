# 🚀 PLAN DE MIGRACIÓN: API + React (Estrategia Gradual)

## 📋 Visión General

**Objetivo:** Migrar de Dash monolito a arquitectura API + React  
**Estrategia:** Migración incremental (Strangler Fig Pattern)  
**Riesgo:** Mínimo - sistema actual sigue funcionando durante la transición  
**Tiempo estimado:** 8-12 semanas (2-3 meses)

---

## 🏗️ Arquitectura Objetivo

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTE (React)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  React App   │  │  React App   │  │   React App (nueva)  │  │
│  │  (legacy)    │  │  (migrando)  │  │   página X           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│         │                 │                   │                  │
│         └─────────────────┴───────────────────┘                  │
│                           │                                     │
│                    ┌──────────────┐                            │
│                    │  API Client  │                            │
│                    │  (axios/fetch)│                            │
│                    └──────────────┘                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                      API Gateway                                │
│                 (FastAPI/Flask)                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Endpoints   │  │  Endpoints   │  │   Endpoints nuevos   │  │
│  │  legacy      │  │  híbridos    │  │   página X           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│              DOMINIO/SERVICIOS (REUTILIZAR 100%)                │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Transmission │  │  Generation  │  │      Services        │  │
│  │   Service    │  │   Service    │  │   (existentes)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Repositories │  │ Repositories │  │   Repositories       │  │
│  │ (PostgreSQL) │  │    (XM)      │  │   (existentes)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estructura de Carpetas Nueva

```
server/
├── backend/                          # API FastAPI (nuevo)
│   ├── api/
│   │   ├── v1/
│   │   │   ├── endpoints/           # Endpoints REST
│   │   │   │   ├── transmision.py
│   │   │   │   ├── generacion.py
│   │   │   │   └── metrics.py
│   │   │   └── router.py
│   │   └── main.py                  # App FastAPI
│   ├── schemas/                     # Pydantic models
│   │   ├── transmision.py
│   │   └── generacion.py
│   └── dependencies.py              # Inyección de dependencias
│
├── frontend/                         # React App (nuevo)
│   ├── public/
│   ├── src/
│   │   ├── components/              # Componentes UI
│   │   │   ├── common/              # Buttons, Cards, Tables
│   │   │   ├── charts/              # Gráficas (Plotly.js/Chart.js)
│   │   │   └── layout/              # Header, Sidebar
│   │   ├── pages/                   # Páginas (una por dashboard)
│   │   │   ├── Transmision/
│   │   │   ├── Generacion/
│   │   │   └── Home/
│   │   ├── hooks/                   # Custom React hooks
│   │   ├── services/                # API clients
│   │   ├── store/                   # State management (Zustand/Redux)
│   │   └── App.tsx
│   └── package.json
│
├── domain/                           # ✅ REUTILIZAR EXISTENTE
│   ├── services/                     # Lógica de negocio actual
│   ├── repositories/                 # Acceso a datos actual
│   └── models/                       # Modelos de dominio
│
├── interface/                        # ✅ Dash legacy (durante transición)
│   └── pages/                        # Se va migrando página por página
│
└── infrastructure/                   # ✅ REUTILIZAR EXISTENTE
    ├── database/
    └── cache/
```

---

## 🗓️ Fases de Migración (8-12 semanas)

### **FASE 0: Preparación y Setup (Semana 1)**

**Objetivo:** Infraestructura base sin tocar lo existente

**Tareas:**
1. ✅ Crear carpetas `backend/` y `frontend/` paralelas a lo existente
2. ✅ Setup FastAPI básico en `backend/api/main.py`
3. ✅ Setup React + TypeScript + Vite en `frontend/`
4. ✅ Configurar proxy para desarrollo (CORS)
5. ✅ Crear sistema de build integrado

**Entregable:** Ambos servidores corriendo en paralelo (puertos 8000 y 3000)

---

### **FASE 1: API Base + Shared Domain (Semanas 2-3)**

**Objetivo:** Exponer datos existentes via REST API sin modificar lógica

**Tareas:**
1. Crear Pydantic schemas para cada entidad
   ```python
   # backend/schemas/transmision.py
   class LineaTransmissionSchema(BaseModel):
       codigo: str
       nombre: str
       tension: float
       participacion: float
   ```

2. Crear endpoints que usen los services EXISTENTES
   ```python
   # backend/api/v1/endpoints/transmision.py
   from domain.services.transmission_service import TransmissionService
   
   @router.get("/lineas")
   def get_lineas(service: TransmissionService = Depends()):
       df = service.get_transmission_lines()
       return df.to_dict('records')  # Simple, funciona ya
   ```

3. Mapear todos los servicios a endpoints REST

**Entregable:** API funcional con datos reales, testeable en Swagger UI

---

### **FASE 2: Frontend Core + Sistema de Diseño (Semanas 4-5)**

**Objetivo:** Componentes UI base reutilizables

**Tareas:**
1. Configurar Material-UI o Tailwind + shadcn/ui
2. Crear componentes equivalentes a los de Dash:
   - `ChartCard` → `ChartCard.tsx` (usa Plotly.js o Chart.js)
   - `KpiCard` → `KpiCard.tsx`
   - `DataTable` → `DataTable.tsx` (usa TanStack Table)
3. Implementar tema institucional MME (colores, tipografía)
4. Crear layout base (header, navegación)

**Entregable:** Storybook con componentes documentados

---

### **FASE 3: Migración Página por Página (Semanas 6-10)**

**Estrategia:** Una página por semana, empezando por la más simple

**Ejemplo - Semana 6: Home/Portada**
```
1. Crear endpoint: GET /api/v1/home/stats
2. Crear página React: Home.tsx
3. Probar en paralelo con Dash
4. Routing: /new/home → React, /home → Dash legacy
5. Cuando esté listo: redirigir /home → React
```

**Ejemplo - Semana 7: Transmisión**
```
1. Analizar callbacks de transmision.py
2. Crear endpoints:
   - GET /api/v1/transmision/lineas
   - GET /api/v1/transmision/kpis
   - POST /api/v1/transmision/export
3. Crear componentes React equivalentes
4. Migrar visualizaciones (Plotly → Plotly.js o Chart.js)
5. Testear feature-parity
6. Switch de ruta
```

**Progresión:**
- Semana 6: Home (simple)
- Semana 7: Transmisión (media complejidad)
- Semana 8: Generación (compleja)
- Semana 9: Métricas/Reportes
- Semana 10: Páginas restantes

---

### **FASE 4: Features Avanzadas (Semana 11)**

**Objetivo:** Funcionalidades que no existían en Dash

**Tareas:**
1. **Offline/PWA:** Cache de datos con Service Workers
2. **Realtime:** WebSockets para actualizaciones en vivo
3. **Export avanzado:** PDF/Excel con mejor calidad
4. **Responsive:** Versión móvil optimizada
5. **Dark Mode:** Implementar correctamente con CSS variables

---

### **FASE 5: Deprecación Dash y Cleanup (Semana 12)**

**Objetivo:** Retirar código legacy

**Tareas:**
1. Mover `/new/*` a rutas principales
2. Eliminar carpeta `interface/pages/` (o archivarla)
3. Limpiar dependencias de Dash
4. Optimizar bundle de React (code splitting)
5. Documentación final

---

## 🔧 Estrategia de Reutilización de Código

### **100% Reutilizable (Sin cambios):**
```python
# domain/services/* - Toda la lógica de negocio
# infrastructure/repositories/* - Acceso a datos
# infrastructure/database/* - Conexiones
# core/cache_manager.py - Caché
```

### **Adaptación Ligera (Wrappers):**
```python
# API Endpoints que llaman a services existentes
# schemas/ para validación de entrada/salida
# dependency injection para instanciar services
```

### **Nuevo Desarrollo (Frontend):**
```typescript
// Todo el código React/TypeScript
// Componentes UI
// State management
// Routing
```

---

## 🌉 Estrategia de Routing (Transición Suave)

### **Durante la Migración:**
```javascript
// App.tsx - Router híbrido
function App() {
  return (
    <Router>
      <Routes>
        {/* Rutas ya migradas → React */}
        <Route path="/" element={<Home />} />
        <Route path="/transmision" element={<Transmision />} />
        
        {/* Rutas pendientes → Redirect a Dash legacy */}
        <Route path="/generacion" element={<LegacyRedirect to="/dash/generacion" />} />
        
        {/* Dash legacy iframe wrapper */}
        <Route path="/dash/*" element={<DashLegacyIframe />} />
      </Routes>
    </Router>
  );
}
```

### **Usuario ve:**
- Navegación consistente (mismo header)
- Transición transparente entre páginas
- URLs mantienen estructura

---

## 📊 Comparación Tecnologías

| Aspecto | Dash Actual | React Objetivo |
|---------|-------------|----------------|
| **Lenguaje** | Python | TypeScript |
| **Gráficos** | Plotly Python | Plotly.js / Chart.js / D3 |
| **Tablas** | dash-table | TanStack Table |
| **Estado** | dcc.Store | Zustand / Redux Toolkit |
| **Styling** | CSS + Bootstrap | Tailwind + CSS Modules |
| **Build** | - | Vite (ultra rápido) |
| **Testing** | Limitado | Jest + React Testing Library |
| **Bundle** | ~5MB (Dash) | ~200KB (solo lo usado) |

---

## ⚠️ Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **Pérdida de datos** | Baja | Alto | API usa mismos services/repositories |
| **Feature gap** | Media | Medio | Checklist de funcionalidades antes de switch |
| **Performance** | Baja | Medio | Code splitting, lazy loading |
| **Curva de aprendizaje** | Alta | Bajo | Capacitación equipo, documentación |
| **Tiempo extendido** | Media | Medio | MVP por fases, no big-bang |

---

## ✅ Checklist de Migración por Página

Antes de dar switch de cada página:

- [ ] Endpoint API funcional con datos correctos
- [ ] Componentes React renderizan igual (pixel-perfect opcional)
- [ ] Todas las interacciones funcionan (filtros, descargas, zoom)
- [ ] Responsive design implementado
- [ ] Tests unitarios pasan
- [ ] Performance aceptable (< 3s carga inicial)
- [ ] Feature-parity verificado con stakeholder
- [ ] Rollback plan preparado

---

## 🎯 Próximos Pasos

**Para empezar MAÑANA:**

1. **Crear estructura de carpetas**
   ```bash
   mkdir -p backend/api/v1/endpoints backend/schemas
   mkdir -p frontend/src/{components,pages,hooks,services,store}
   ```

2. **Setup FastAPI básico**
   ```python
   # backend/main.py
   from fastapi import FastAPI
   app = FastAPI(title="Portal Energético API")
   
   @app.get("/health")
   def health():
       return {"status": "ok"}
   ```

3. **Setup React**
   ```bash
   cd frontend
   npm create vite@latest . -- --template react-ts
   npm install @tanstack/react-query axios recharts
   ```

4. **Primer endpoint de prueba**
   - Exponer datos de transmisión vía API
   - Consumir desde React
   - Verificar que funciona

**¿Te parece bien este plan? ¿Empezamos con la FASE 0 mañana?**
