#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# SETUP AUTOMÁTICO - MIGRACIÓN API + REACT
# Ejecutar: chmod +x scripts/setup_migration.sh && ./scripts/setup_migration.sh
# ═══════════════════════════════════════════════════════════════════════════

set -e  # Detener en errores

echo "🚀 Setup de Migración API + React"
echo "═══════════════════════════════════════════════════════════"

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SERVER_DIR="/home/admonctrlxm/server"
cd "$SERVER_DIR"

# ═══════════════════════════════════════════════════════════════════════════
# PASO 1: Estructura de Carpetas
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}📁 Creando estructura de carpetas...${NC}"

mkdir -p backend/{api/v1/endpoints,schemas,tests}
mkdir -p frontend/src/{components/{common,charts,layout},pages/{Transmision,Generacion,Home},hooks,services,store,types}
mkdir -p frontend/public

echo -e "${GREEN}✅ Carpetas creadas${NC}"

# ═══════════════════════════════════════════════════════════════════════════
# PASO 2: Backend - Archivos base
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}🐍 Configurando Backend FastAPI...${NC}"

# requirements.txt
cat > backend/requirements.txt << 'EOF'
# API Core
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
python-multipart==0.0.6

# Usar dependencias del proyecto principal
# (pandas, numpy, psycopg2 ya están en el venv)
EOF

# main.py
cat > backend/main.py << 'EOF'
"""API Principal - Portal Energético MME"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Portal Energético MME API",
    version="1.0.0",
    docs_url="/api/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "portal-energetico-api"}

# Importar routers (se agregarán luego)
# from api.v1.endpoints import transmision
# app.include_router(transmision.router, prefix="/api/v1/transmision")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
EOF

echo -e "${GREEN}✅ Backend configurado${NC}"

# ═══════════════════════════════════════════════════════════════════════════
# PASO 3: Frontend - React + Vite
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}⚛️  Configurando Frontend React...${NC}"

cd frontend

# Verificar si ya existe package.json
if [ ! -f "package.json" ]; then
    echo "Inicializando proyecto React con Vite..."
    
    # Crear proyecto Vite temporalmente
    npm create vite@latest temp-vite -- --template react-ts
    
    # Mover archivos
    mv temp-vite/* .
    mv temp-vite/.* . 2>/dev/null || true
    rm -rf temp-vite
    
    # Instalar dependencias
    npm install
    
    # Instalar dependencias adicionales
    npm install @tanstack/react-query axios react-router-dom recharts
    npm install -D tailwindcss postcss autoprefixer
    
    # Setup Tailwind
    npx tailwindcss init -p
    
    # Configurar Tailwind
    cat > tailwind.config.js << 'EOF'
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        'mme-primary': '#1e3a8a',
        'mme-gold': '#F5A623',
      },
    },
  },
  plugins: [],
}
EOF

    # CSS base
    cat > src/index.css << 'EOF'
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  @apply bg-gray-50 text-gray-900;
  font-family: 'Inter', system-ui, sans-serif;
}
EOF

    # Crear App.tsx básica
    cat > src/App.tsx << 'EOF'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-gray-50 p-8">
        <h1 className="text-3xl font-bold text-mme-primary">
          Portal Energético MME - React
        </h1>
        <p className="mt-4 text-gray-600">
          Setup inicial completado. Listo para migrar componentes.
        </p>
      </div>
    </QueryClientProvider>
  )
}

export default App
EOF

    # Crear API service base
    mkdir -p src/services
    cat > src/services/api.ts << 'EOF'
import axios from 'axios'

export const api = axios.create({
  baseURL: 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
})

export const healthApi = {
  check: () => api.get('/api/health'),
}
EOF

    echo -e "${GREEN}✅ Frontend React configurado${NC}"
else
    echo -e "${GREEN}✅ Frontend ya existe${NC}"
fi

cd "$SERVER_DIR"

# ═══════════════════════════════════════════════════════════════════════════
# PASO 4: Scripts de ejecución
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}📝 Creando scripts de ejecución...${NC}"

# Script para correr backend
cat > scripts/run_api.sh << 'EOF'
#!/bin/bash
cd /home/admonctrlxm/server/backend
source ../venv/bin/activate
python main.py
EOF
chmod +x scripts/run_api.sh

# Script para correr frontend
cat > scripts/run_frontend.sh << 'EOF'
#!/bin/bash
cd /home/admonctrlxm/server/frontend
npm run dev
EOF
chmod +x scripts/run_frontend.sh

# Script para correr todo (en paralelo)
cat > scripts/run_all_dev.sh << 'EOF'
#!/bin/bash
echo "Iniciando todos los servicios en desarrollo..."
echo "API: http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Dash Legacy: http://localhost:8050 (correr manualmente)"
echo ""

# Backend en background
cd /home/admonctrlxm/server/backend && source ../venv/bin/activate && python main.py &
BACKEND_PID=$!

# Frontend en background  
cd /home/admonctrlxm/server/frontend && npm run dev &
FRONTEND_PID=$!

echo "Backend PID: $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo ""
echo "Presiona Ctrl+C para detener todo"

# Esperar
wait
EOF
chmod +x scripts/run_all_dev.sh

# ═══════════════════════════════════════════════════════════════════════════
# RESUMEN
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ SETUP COMPLETADO${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Estructura creada:"
echo "  backend/          → API FastAPI"
echo "  frontend/         → React + TypeScript + Vite"
echo ""
echo "Para iniciar desarrollo:"
echo ""
echo "  Terminal 1 - API:"
echo "    ./scripts/run_api.sh"
echo ""
echo "  Terminal 2 - Frontend:"
echo "    ./scripts/run_frontend.sh"
echo ""
echo "  O ambos en uno (background):"
echo "    ./scripts/run_all_dev.sh"
echo ""
echo "URLs:"
echo "  API Docs:  http://localhost:8000/api/docs"
echo "  Frontend:  http://localhost:5173"
echo "  Health:    http://localhost:8000/api/health"
echo ""
echo "═══════════════════════════════════════════════════════════"
