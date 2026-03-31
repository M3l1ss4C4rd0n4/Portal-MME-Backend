# 🚀 GUÍA DE IMPLEMENTACIÓN - FASE 0: Setup Inicial

## 📋 Objetivo
Tener corriendo en paralelo:
- Backend API (FastAPI) en `localhost:8000`
- Frontend React en `localhost:5173`
- Dash legacy sigue funcionando en `localhost:8050`

---

## 🗂️ Paso 1: Estructura de Carpetas

Ejecutar en la terminal:

```bash
cd /home/admonctrlxm/server

# Crear estructura nueva
mkdir -p backend/api/v1/endpoints
mkdir -p backend/schemas
mkdir -p backend/tests
mkdir -p frontend/src/{components/{common,charts,layout},pages,hooks,services,store,types}
mkdir -p frontend/public

# Verificar
ls -la backend/
ls -la frontend/
```

---

## 🐍 Paso 2: Backend FastAPI

### 2.1 Crear `backend/requirements.txt`

```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
python-multipart==0.0.6

# Reutilizar del proyecto existente (no duplicar)
# - pandas
# - numpy
# - psycopg2-binary
# - sqlalchemy
```

### 2.2 Crear `backend/main.py`

```python
"""
API Principal - Portal Energético MME
FastAPI + Reutilización de Domain Services
"""

import sys
from pathlib import Path

# Agregar el proyecto al path para reutilizar domain
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(
    title="Portal Energético MME API",
    description="API REST para el dashboard de energía",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS para desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS DE PRUEBA
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health_check():
    """Endpoint de salud del API"""
    return {
        "status": "healthy",
        "service": "portal-energetico-api",
        "version": "1.0.0"
    }


# ═══════════════════════════════════════════════════════════════════════════
# IMPORTAR RUTAS (se irán agregando)
# ═══════════════════════════════════════════════════════════════════════════

# Descomentar cuando se creen:
# from api.v1.endpoints import transmision, generacion, metrics
# app.include_router(transmision.router, prefix="/api/v1/transmision", tags=["Transmisión"])
# app.include_router(generacion.router, prefix="/api/v1/generacion", tags=["Generación"])


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
```

### 2.3 Crear `backend/schemas/transmision.py`

```python
"""
Schemas Pydantic para Transmisión
"""

from pydantic import BaseModel
from typing import List, Optional
from datetime import date


class LineaBase(BaseModel):
    codigo: str
    nombre: str
    tension: float
    longitud: float
    participacion_total: float
    criticidad: Optional[str] = None
    anos_operacion: Optional[int] = None
    
    class Config:
        from_attributes = True


class DashboardTransmision(BaseModel):
    total_lineas: int
    lineas_criticas: int
    longitud_total: float
    tension_promedio: float
    lineas: List[LineaBase]
    
    class Config:
        from_attributes = True
```

### 2.4 Crear `backend/api/v1/endpoints/transmision.py`

```python
"""
Endpoints para Transmisión
USA LOS SERVICIOS EXISTENTES - No reescribe lógica
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date

# REUTILIZAR SERVICE EXISTENTE
from domain.services.transmission_service import TransmissionService

router = APIRouter()

# Instancia del service (en producción usar Dependency Injection)
transmission_service = TransmissionService()


@router.get("/lineas")
def get_lineas(
    tension: Optional[float] = Query(None, description="Filtrar por nivel de tensión"),
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None)
):
    """
    Obtiene todas las líneas de transmisión.
    Reutiliza el service existente sin modificarlo.
    """
    try:
        # Llamar al service existente
        df = transmission_service.get_transmission_lines()
        
        if df.empty:
            return {"data": [], "count": 0, "message": "No hay datos disponibles"}
        
        # Aplicar filtros si vienen
        if tension:
            df = df[df['Tension'] == tension]
        
        # Convertir a dict para JSON
        records = df.head(100).fillna('').to_dict('records')  # Limitar a 100 para demo
        
        return {
            "data": records,
            "count": len(records),
            "total": len(df)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
def get_dashboard_stats():
    """
    Estadísticas para el dashboard de transmisión.
    """
    try:
        df = transmission_service.get_transmission_lines()
        
        if df.empty:
            return {"error": "No hay datos"}
        
        stats = {
            "total_lineas": len(df),
            "tensiones": df['Tension'].unique().tolist() if 'Tension' in df.columns else [],
            "longitud_total": df['Longitud'].sum() if 'Longitud' in df.columns else 0,
            "ultima_actualizacion": df['Fecha'].max() if 'Fecha' in df.columns else None
        }
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## ⚛️ Paso 3: Frontend React

### 3.1 Inicializar proyecto

```bash
cd /home/admonctrlxm/server/frontend

# Crear con Vite (rápido y moderno)
npm create vite@latest . -- --template react-ts

# Instalar dependencias base
npm install

# Instalar librerías necesarias
npm install @tanstack/react-query axios react-router-dom recharts
npm install -D tailwindcss postcss autoprefixer

# Setup Tailwind
npx tailwindcss init -p
```

### 3.2 Configurar `tailwind.config.js`

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Colores institucionales MME
        'mme-primary': '#1e3a8a',
        'mme-gold': '#F5A623',
        'mme-navy': '#152e6b',
      },
    },
  },
  plugins: [],
}
```

### 3.3 Crear `src/index.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Estilos base */
body {
  @apply bg-gray-50 text-gray-900;
  font-family: 'Inter', system-ui, sans-serif;
}
```

### 3.4 Crear servicio API

```typescript
// src/services/api.ts
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para errores
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// Servicios específicos
export const transmisionApi = {
  getLineas: (params?: any) => api.get('/api/v1/transmision/lineas', { params }),
  getDashboard: () => api.get('/api/v1/transmision/dashboard'),
};
```

### 3.5 Crear componente de prueba

```typescript
// src/components/TestApi.tsx
import { useQuery } from '@tanstack/react-query';
import { transmisionApi } from '../services/api';

export function TestApi() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const response = await transmisionApi.getDashboard();
      return response.data;
    },
  });

  if (isLoading) return <div className="p-4">Cargando...</div>;
  if (error) return <div className="p-4 text-red-500">Error: {error.message}</div>;

  return (
    <div className="p-4 bg-white rounded-lg shadow">
      <h2 className="text-xl font-bold mb-4">Dashboard Transmisión (React)</h2>
      <pre className="bg-gray-100 p-4 rounded overflow-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
```

### 3.6 Actualizar `App.tsx`

```typescript
// src/App.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TestApi } from './components/TestApi';
import './index.css';

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-gray-50">
        <header className="bg-mme-primary text-white p-4">
          <h1 className="text-2xl font-bold">Portal Energético MME</h1>
          <p className="text-sm opacity-80">Versión React (En desarrollo)</p>
        </header>
        
        <main className="p-6">
          <TestApi />
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
```

---

## 🚀 Paso 4: Ejecutar y Probar

### Terminal 1 - Backend:
```bash
cd /home/admonctrlxm/server/backend
source ../venv/bin/activate  # Usar el mismo venv del proyecto
python main.py
# Debería iniciar en http://localhost:8000
# Probar: http://localhost:8000/api/health
```

### Terminal 2 - Frontend:
```bash
cd /home/admonctrlxm/server/frontend
npm run dev
# Debería iniciar en http://localhost:5173
```

### Terminal 3 - Dash legacy (sigue funcionando):
```bash
cd /home/admonctrlxm/server
gunicorn -c gunicorn_config.py app:server
# Sigue en http://localhost:8050
```

---

## ✅ Checklist de Verificación

- [ ] Backend responde en `http://localhost:8000/api/health`
- [ ] Docs de API visibles en `http://localhost:8000/api/docs`
- [ ] Frontend carga en `http://localhost:5173`
- [ ] Frontend muestra datos de la API (TestApi component)
- [ ] Dash legacy sigue funcionando en puerto 8050
- [ ] No hay errores de CORS

---

## 🔄 Siguiente Paso (FASE 1)

Una vez esto funcione, continuamos con:

1. Crear endpoints reales para todas las páginas
2. Crear componentes UI equivalentes a los de Dash
3. Migrar primera página (Home)
4. Routing entre Dash y React

**¿Empezamos con esta FASE 0?**
