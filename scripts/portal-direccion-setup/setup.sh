#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# SETUP PORTAL DIRECCIÓN MME - Script Automatizado
# Ejecutar: chmod +x setup.sh && ./setup.sh
# ═══════════════════════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════════════════"
echo "🚀 PORTAL DE DIRECCIÓN MME - Setup Automático"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Directorio base
BASE_DIR="/home/admonctrlxm/portal-direccion-mme"

# ═══════════════════════════════════════════════════════════════════════════
# 1. VERIFICACIONES INICIALES
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}🔍 Verificando requisitos...${NC}"

# Verificar Node.js
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}⚠️  Node.js no encontrado. Instalando...${NC}"
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

NODE_VERSION=$(node -v)
echo -e "${GREEN}✅ Node.js: $NODE_VERSION${NC}"

# Verificar npm
NPM_VERSION=$(npm -v)
echo -e "${GREEN}✅ npm: $NPM_VERSION${NC}"

# Crear directorio
mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 2. CREAR PROYECTO NEXT.JS
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}⚛️  Creando proyecto Next.js...${NC}"

if [ -f "package.json" ]; then
    echo -e "${YELLOW}⚠️  Proyecto ya existe. ¿Sobrescribir? (s/N)${NC}"
    read -r respuesta
    if [[ ! "$respuesta" =~ ^[Ss]$ ]]; then
        echo "Cancelado."
        exit 0
    fi
    rm -rf node_modules package.json package-lock.json
fi

# Crear proyecto con create-next-app
echo "Inicializando Next.js (esto puede tardar 2-3 minutos)..."
npx create-next-app@latest . \
    --typescript \
    --tailwind \
    --eslint \
    --app \
    --src-dir \
    --import-alias "@/*" \
    --use-npm \
    --yes

echo -e "${GREEN}✅ Proyecto Next.js creado${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 3. INSTALAR DEPENDENCIAS
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}📦 Instalando dependencias...${NC}"

# Core dependencies
echo "Instalando Tremor UI, NextAuth, Recharts..."
npm install @tremor/react next-auth recharts framer-motion @tanstack/react-query date-fns clsx tailwind-merge

# Mapas
echo "Instalando React Leaflet..."
npm install react-leaflet leaflet

# Tipos
echo "Instalando tipos de TypeScript..."
npm install -D @types/leaflet

echo -e "${GREEN}✅ Dependencias instaladas${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 4. CREAR ESTRUCTURA DE CARPETAS
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}📁 Creando estructura de carpetas...${NC}"

mkdir -p src/app/\(dashboards\)/{energia,presupuesto,comunidades,supervision,subsidios}
mkdir -p src/app/api/{auth/\[...nextauth\],xm,presupuesto,comunidades,supervision,subsidios}
mkdir -p src/components/{ui,dashboard,home}
mkdir -p src/{lib,hooks,types}
mkdir -p scripts/{etl,sql}
mkdir -p public

echo -e "${GREEN}✅ Estructura creada${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 5. CONFIGURAR TAILWIND CON TEMA MME
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}🎨 Configurando tema MME...${NC}"

cat > tailwind.config.ts << 'EOF'
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Colores Institucionales MME
        'mme': {
          'gold': '#F5A623',
          'gold-light': '#FFB84D',
          'gold-dark': '#D4901A',
          'navy': '#1e3a8a',
          'navy-dark': '#152e6b',
        },
        // Dark theme
        'dark': {
          'bg': '#0A0E17',
          'card': '#111827',
          'elevated': '#1A2234',
          'border': '#2D3748',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
EOF

echo -e "${GREEN}✅ Tailwind configurado${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 6. CREAR CSS GLOBAL
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}📝 Creando estilos globales...${NC}"

cat > src/app/globals.css << 'EOF'
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #0A0E17;
  --foreground: #ffffff;
}

body {
  background-color: var(--background);
  color: var(--foreground);
  font-family: 'Inter', system-ui, sans-serif;
}

/* Scrollbar oscuro */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #1A2234;
}

::-webkit-scrollbar-thumb {
  background: #4A5568;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #718096;
}

/* Animaciones */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-fade-in {
  animation: fadeIn 0.5s ease-out forwards;
}

/* Gradientes institucionales */
.bg-gradient-mme {
  background: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);
}
EOF

echo -e "${GREEN}✅ Estilos globales creados${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 7. CREAR LAYOUT BASE
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}🏗️  Creando layout base...${NC}"

cat > src/app/layout.tsx << 'EOF'
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Portal de Dirección - Ministerio de Minas y Energía",
  description: "Dashboard de gestión y control del sector energético",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-dark-bg text-white antialiased">
        {children}
      </body>
    </html>
  );
}
EOF

echo -e "${GREEN}✅ Layout base creado${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 8. CREAR PÁGINA HOME (Placeholder)
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}🏠 Creando página Home (placeholder)...${NC}"

cat > src/app/page.tsx << 'EOF'
import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen p-8">
      <header className="mb-8">
        <h1 className="text-4xl font-bold text-mme-gold mb-2">
          Portal de Dirección
        </h1>
        <p className="text-gray-400">
          Ministerio de Minas y Energía - Dirección de Energía Eléctrica
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Card: Gestión del Sector */}
        <DashboardCard
          title="Gestión del Sector"
          description="Métricas del sector energético"
          href="/dashboards/energia"
          icon="⚡"
        />

        {/* Card: Ejecución Presupuestal */}
        <DashboardCard
          title="Ejecución Presupuestal 2026"
          description="Seguimiento presupuestal"
          href="/dashboards/presupuesto"
          icon="💰"
        />

        {/* Card: Comunidades Energéticas */}
        <DashboardCard
          title="Comunidades Energéticas"
          description="Estado de implementación"
          href="/dashboards/comunidades"
          icon="🏘️"
        />

        {/* Card: Supervisión */}
        <DashboardCard
          title="Supervisión"
          description="Contratos y proyectos"
          href="/dashboards/supervision"
          icon="📋"
        />

        {/* Card: Subsidios */}
        <DashboardCard
          title="Subsidios"
          description="Gestión de subsidios"
          href="/dashboards/subsidios"
          icon="🎁"
        />
      </div>
    </main>
  );
}

function DashboardCard({
  title,
  description,
  href,
  icon,
}: {
  title: string;
  description: string;
  href: string;
  icon: string;
}) {
  return (
    <Link
      href={href}
      className="block p-6 bg-dark-card rounded-lg border border-dark-border hover:border-mme-gold transition-all hover:shadow-lg hover:shadow-mme-gold/10"
    >
      <div className="flex items-start justify-between mb-4">
        <h2 className="text-xl font-semibold text-mme-gold">{title}</h2>
        <span className="text-2xl">{icon}</span>
      </div>
      <p className="text-gray-400 text-sm">{description}</p>
      <div className="mt-4 flex items-center text-sm text-gray-500">
        <span>Ver dashboard</span>
        <span className="ml-2">→</span>
      </div>
    </Link>
  );
}
EOF

echo -e "${GREEN}✅ Página Home creada${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 9. CREAR README
# ═══════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}📚 Creando README...${NC}"

cat > README.md << 'EOF'
# Portal de Dirección MME

Dashboard de gestión y control del sector energético del Ministerio de Minas y Energía.

## 🏗️ Arquitectura

- **Framework:** Next.js 14 con App Router
- **Estilos:** Tailwind CSS
- **UI Components:** Tremor React
- **Gráficas:** Recharts
- **Mapas:** React Leaflet
- **Auth:** NextAuth.js con Azure AD

## 🚀 Comandos

```bash
# Instalar dependencias
npm install

# Desarrollo
npm run dev

# Build producción
npm run build

# Producción
npm start
```

## 📁 Estructura

```
src/
├── app/                    # Rutas de Next.js
│   ├── (dashboards)/       # Dashboards agrupados
│   │   ├── energia/
│   │   ├── presupuesto/
│   │   ├── comunidades/
│   │   ├── supervision/
│   │   └── subsidios/
│   ├── api/                # API Routes
│   └── page.tsx            # Home
├── components/             # Componentes React
├── lib/                    # Utilidades
├── hooks/                  # Custom hooks
└── types/                  # Tipos TypeScript
```

## 📊 Dashboards

1. **Gestión del Sector** - Datos XM (energía, transmisión, etc.)
2. **Ejecución Presupuestal 2026** - Datos de Excel/OneDrive
3. **Comunidades Energéticas** - Implementación CE
4. **Supervisión** - Contratos y proyectos
5. **Subsidios** - Gestión de subsidios

## 🎨 Tema

Colores institucionales MME:
- **Gold:** #F5A623 (primario)
- **Navy:** #1e3a8a (secundario)
- **Dark:** #0A0E17 (fondo)

## 📝 Scripts de Datos

```bash
# Subir Excel a PostgreSQL
python scripts/etl/load_excel.py --file data.xlsx --table presupuesto
```

## 🔐 Autenticación

Configurar variables de entorno:
```
AZURE_AD_CLIENT_ID=
AZURE_AD_CLIENT_SECRET=
AZURE_AD_TENANT_ID=
```
EOF

echo -e "${GREEN}✅ README creado${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# 10. RESUMEN FINAL
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ SETUP COMPLETADO${NC}"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "📂 Proyecto creado en: $BASE_DIR"
echo ""
echo "🚀 Para empezar a desarrollar:"
echo ""
echo "  cd $BASE_DIR"
echo "  npm run dev"
echo ""
echo "🌐 URLs:"
echo "  - Desarrollo: http://localhost:3000"
echo "  - Dashboards: http://localhost:3000/dashboards/[nombre]"
echo ""
echo "📁 Estructura creada:"
echo "  - src/app/ - Rutas y páginas"
echo "  - src/components/ - Componentes UI"
echo "  - src/lib/ - Utilidades"
echo "  - scripts/ - Scripts ETL"
echo ""
echo "📚 Documentación:"
echo "  - README.md - Guía del proyecto"
echo "  - docs/PLAN_IMPLEMENTACION_REAL.md - Plan completo"
echo ""
echo -e "${YELLOW}⚠️  Siguientes pasos:${NC}"
echo "  1. Configurar variables de entorno (.env.local)"
echo "  2. Configurar PostgreSQL"
echo "  3. Subir datos de Excel"
echo "  4. Crear dashboards"
echo ""
echo "═══════════════════════════════════════════════════════════════"
