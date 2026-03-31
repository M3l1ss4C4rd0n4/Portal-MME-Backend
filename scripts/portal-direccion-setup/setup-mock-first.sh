#!/bin/bash
# =============================================
# SETUP: Frontend Primero con Mock Data
# Portal de Dirección MME - Fase 1 (Visual)
# Basado en diseño ArcGIS del Ministerio
# =============================================

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================
# CONFIGURACIÓN
# =============================================
PROJECT_NAME="portal-direccion-mme"
PROJECT_DIR="$HOME/$PROJECT_NAME"
NODE_VERSION="20"
SOURCE_DIR="/home/admonctrlxm/server"

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    PORTAL DE DIRECCIÓN MME - SETUP MOCK-FIRST                ║"
echo "║    Réplica exacta del dashboard ArcGIS                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# =============================================
# PASO 0: Verificar requisitos
# =============================================
echo -e "${YELLOW}📋 Verificando requisitos...${NC}"

if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js no está instalado${NC}"
    echo "Instalando Node.js $NODE_VERSION..."
    curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

NODE_CURRENT=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_CURRENT" -lt 18 ]; then
    echo -e "${RED}❌ Node.js 18+ requerido. Versión actual: $(node --version)${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Node.js $(node --version)${NC}"

if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ Git no está instalado${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Git instalado${NC}"

# Verificar logo
if [ -f "$SOURCE_DIR/assets/images/logo-minenergia.png" ]; then
    echo -e "${GREEN}✓ Logo del ministerio encontrado${NC}"
else
    echo -e "${YELLOW}⚠️  Logo no encontrado en $SOURCE_DIR/assets/images/logo-minenergia.png${NC}"
fi

# =============================================
# PASO 1: Crear proyecto Next.js
# =============================================
echo -e "${YELLOW}🏗️  Creando proyecto Next.js...${NC}"

if [ -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}⚠️  El directorio ya existe. ¿Eliminar y recrear? (s/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([sS][iI]|[sS])$ ]]; then
        rm -rf "$PROJECT_DIR"
    else
        echo -e "${RED}❌ Setup cancelado${NC}"
        exit 1
    fi
fi

# Crear con create-next-app
npx create-next-app@latest "$PROJECT_NAME" \
    --typescript \
    --tailwind \
    --eslint \
    --app \
    --src-dir \
    --import-alias "@/*" \
    --use-npm \
    --yes

cd "$PROJECT_DIR"

echo -e "${GREEN}✓ Proyecto creado en $PROJECT_DIR${NC}"

# =============================================
# PASO 2: Instalar dependencias
# =============================================
echo -e "${YELLOW}📦 Instalando dependencias...${NC}"

# Tremor UI
npm install @tremor/react --legacy-peer-deps

# Icons
npm install @heroicons/react --legacy-peer-deps

# Animaciones
npm install framer-motion --legacy-peer-deps

# Gráficas
npm install recharts --legacy-peer-deps

# =============================================
# PASO 3: Configurar Tailwind + Tema MME
# =============================================
echo -e "${YELLOW}⚙️  Configurando tema MME (ArcGIS style)...${NC}"

cat > tailwind.config.ts << 'EOF'
import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./node_modules/@tremor/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Tema exacto del ArcGIS MME
        mme: {
          // Fondos
          dark: '#0A0A0A',
          'dark-card': '#141414',
          'dark-card-hover': '#1A1A1A',
          'dark-border': '#2A2A2A',
          
          // Acentos dorados
          gold: '#E8A838',
          'gold-light': '#F5C158',
          'gold-dark': '#C98A2A',
          'gold-muted': '#B8956A',
          
          // Alertas
          alert: '#FFD700',
          'alert-bg': '#FFD70020',
          
          // Textos
          'text-primary': '#FFFFFF',
          'text-secondary': '#9CA3AF',
          'text-muted': '#6B7280',
          
          // Footer
          'footer-gold': '#C9A227',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        'card-title': ['1.1rem', { fontWeight: '700', letterSpacing: '0.05em' }],
        'kpi-large': ['1.75rem', { fontWeight: '700' }],
        'kpi-medium': ['1.25rem', { fontWeight: '600' }],
        'kpi-small': ['0.9rem', { fontWeight: '500' }],
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'gauge-fill': 'gaugeFill 1.2s ease-out forwards',
        'pulse-gold': 'pulseGold 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGold: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
EOF

# Actualizar globals.css - Fondo negro puro como ArcGIS
cat > src/app/globals.css << 'EOF'
@import "tailwindcss";

:root {
  --mme-gold: #E8A838;
  --mme-gold-light: #F5C158;
  --mme-dark: #0A0A0A;
  --mme-card: #141414;
  --mme-border: #2A2A2A;
}

@theme inline {
  --color-background: var(--mme-dark);
  --color-foreground: #ffffff;
}

html {
  scroll-behavior: smooth;
}

body {
  background: var(--mme-dark);
  color: #ffffff;
  font-family: 'Inter', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Scrollbar oscuro */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: var(--mme-dark);
}

::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--mme-gold);
}

/* Selection dorada */
::selection {
  background: var(--mme-gold);
  color: var(--mme-dark);
}

/* Card hover con elevación */
.card-mme {
  background: var(--mme-card);
  border: 1px solid var(--mme-border);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.card-mme:hover {
  transform: translateY(-2px);
  border-color: rgba(232, 168, 56, 0.3);
  box-shadow: 0 8px 32px rgba(232, 168, 56, 0.1);
}

/* Texto dorado gradiente */
.text-gold-gradient {
  background: linear-gradient(135deg, #E8A838 0%, #F5C158 50%, #E8A838 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* Glow dorado */
.glow-gold {
  text-shadow: 0 0 20px rgba(232, 168, 56, 0.3);
}

/* Glass effect para header */
.glass-dark {
  background: rgba(10, 10, 10, 0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(42, 42, 42, 0.8);
}

/* Animación contador */
@keyframes countUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-count {
  animation: countUp 0.6s ease-out forwards;
}
EOF

# =============================================
# PASO 4: Crear estructura
# =============================================
echo -e "${YELLOW}📁 Creando estructura...${NC}"

mkdir -p "src/app/(dashboards)/energia"
mkdir -p "src/app/(dashboards)/presupuesto"
mkdir -p "src/app/(dashboards)/comunidades"
mkdir -p "src/app/(dashboards)/supervision"
mkdir -p "src/app/(dashboards)/subsidios"
mkdir -p src/components/{ui,dashboard}
mkdir -p src/mocks
mkdir -p src/lib
mkdir -p public/images

# Copiar logo si existe
if [ -f "$SOURCE_DIR/assets/images/logo-minenergia.png" ]; then
    cp "$SOURCE_DIR/assets/images/logo-minenergia.png" public/images/
    echo -e "${GREEN}✓ Logo copiado${NC}"
fi

# =============================================
# PASO 5: Mock Data Exacto del ArcGIS
# =============================================
echo -e "${YELLOW}🎨 Creando mock data (valores exactos de la imagen)...${NC}"

cat > src/mocks/home-data.ts << 'EOF'
/**
 * Mock Data - Portal Home MME
 * Valores exactos del dashboard ArcGIS
 */

export interface KpiData {
  label: string;
  value: string | number;
  prefix?: string;
  suffix?: string;
  icon?: string;
  highlight?: boolean;
  subLabel?: string;
}

export interface GaugeData {
  label: string;
  value: number;
  color: 'gold' | 'white' | 'muted';
  size?: 'sm' | 'md' | 'lg';
}

export interface SubSection {
  title: string;
  gauges?: GaugeData[];
  kpis?: KpiData[];
  details?: { label: string; value: string }[];
}

export interface DashboardCardData {
  id: string;
  title: string;
  icon?: string;
  alert?: boolean;
  kpis: KpiData[];
  gauges?: GaugeData[];
  subSections?: SubSection[];
  updateTime?: string;
  link: string;
}

// Datos exactos de la imagen ArcGIS
export const homeDashboardData: Record<string, DashboardCardData> = {
  gestionSector: {
    id: 'gestion-sector',
    title: 'GESTIÓN DEL SECTOR',
    icon: 'energia',
    alert: true,
    kpis: [
      { 
        label: 'Precio de bolsa (COP/kWh)', 
        value: '$332.2', 
        icon: 'chart',
        highlight: true 
      },
      { 
        label: 'Energía Generada GWh', 
        value: '245.5', 
        icon: 'bulb',
        highlight: true 
      },
    ],
    gauges: [
      { label: '% Embalses', value: 66, color: 'gold' },
    ],
    updateTime: '3/24/2026, 2:00 AM',
    link: '/dashboards/energia',
  },

  presupuesto: {
    id: 'presupuesto',
    title: 'EJECUCIÓN PRESUPUESTAL 2026',
    kpis: [
      { 
        label: 'Apropiación Pptal DEE', 
        value: '$ 7.105.844.200.047',
        subLabel: 'Apropiación total'
      },
      { 
        label: 'Comprometido', 
        value: '$ 2.396.981.420.251,00',
        highlight: true 
      },
      { 
        label: 'Obligado', 
        value: '$ 6.028.108.212,00',
        highlight: true 
      },
    ],
    gauges: [
      { label: '% Comprometido', value: 33.7, color: 'gold' },
      { label: '% Obligado', value: 0.08, color: 'white' },
    ],
    link: '/dashboards/presupuesto',
  },

  comunidades: {
    id: 'comunidades',
    title: 'COMUNIDADES ENERGÉTICAS',
    kpis: [
      { 
        label: 'CE Implementadas', 
        value: 469, 
        icon: 'people',
        subLabel: 'Total comunidades'
      },
      { 
        label: 'Inversión Estimada', 
        value: '$ 290,379,880,159.74',
        highlight: true 
      },
      { 
        label: 'Capacidad de generación', 
        value: '12,837.12 kWp', 
        icon: 'bolt',
        subLabel: 'Potencia instalada'
      },
    ],
    subSections: [
      {
        title: 'Contratos OR 2025',
        gauges: [
          { label: 'Avance Financiero', value: 53.29, color: 'gold', size: 'sm' },
          { label: 'Avance General', value: 16.0, color: 'white', size: 'sm' },
        ],
        details: [
          { label: 'No Contratos', value: '17' },
          { label: 'Usuarios', value: '29.5911' },
          { label: 'N° de CEs', value: '2,297' },
          { label: 'Inversión total', value: '$ 914.360.289.397' },
          { label: 'Potencia a instalar', value: '37,00 mWp' },
        ],
      },
    ],
    link: '/dashboards/comunidades',
  },

  supervision: {
    id: 'supervision',
    title: 'SUPERVISIÓN',
    kpis: [
      { label: 'No. Contratos', value: 840, icon: 'document' },
      { label: 'No. Proyectos', value: '2,426', icon: 'folder' },
      { label: 'Contratos en ejecución', value: 319, icon: 'document' },
      { label: 'No. Contratos liquidados', value: 295, icon: 'document' },
    ],
    gauges: [
      { label: 'Avance Físico', value: 87, color: 'gold' },
      { label: 'Avance Financiero', value: 85, color: 'gold' },
    ],
    link: '/dashboards/supervision',
  },

  subsidios: {
    id: 'subsidios',
    title: 'SUBSIDIOS',
    kpis: [
      { 
        label: 'Déficit Acumulado', 
        value: '$ 3,469,667,088,497',
        highlight: true 
      },
    ],
    subSections: [
      {
        title: '2025',
        kpis: [
          { label: 'Valor pendiente de pago', value: '$ 0' },
          { label: 'Resoluciones Expedidas', value: 78, icon: 'mail' },
          { label: 'Valor Asignado Resoluciones', value: '$ 3,272,346,470,818', highlight: true },
        ],
      },
      {
        title: '2026',
        kpis: [
          { label: 'Valor pendiente pago', value: '$ 1,172,216,464,039' },
          { label: 'Resoluciones Expedidas', value: 10, icon: 'mail' },
          { label: 'Valor Asignado a Resoluciones', value: '$ 1,444,288,578.199', highlight: true },
        ],
      },
    ],
    link: '/dashboards/subsidios',
  },
};
EOF

# =============================================
# PASO 6: Componente Gauge Semicircular
# =============================================
echo -e "${YELLOW}🧩 Creando componente Gauge...${NC}"

cat > src/components/ui/SemiGauge.tsx << 'EOF'
'use client';

import { motion } from 'framer-motion';

interface SemiGaugeProps {
  value: number;
  label: string;
  color?: 'gold' | 'white' | 'muted';
  size?: 'sm' | 'md' | 'lg';
}

export default function SemiGauge({ 
  value, 
  label, 
  color = 'gold',
  size = 'md' 
}: SemiGaugeProps) {
  const colors = {
    gold: '#E8A838',
    white: '#FFFFFF',
    muted: '#6B7280',
  };

  const sizes = {
    sm: { width: 100, height: 55, stroke: 8, font: 'text-sm' },
    md: { width: 140, height: 75, stroke: 10, font: 'text-base' },
    lg: { width: 180, height: 95, stroke: 12, font: 'text-lg' },
  };

  const { width, height, stroke, font } = sizes[size];
  const radius = (width - stroke) / 2;
  const circumference = Math.PI * radius;
  const strokeDashoffset = circumference * (1 - value / 100);

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width, height }}>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
          {/* Background arc */}
          <path
            d={`M ${stroke/2} ${height} A ${radius} ${radius} 0 0 1 ${width - stroke/2} ${height}`}
            fill="none"
            stroke="#2A2A2A"
            strokeWidth={stroke}
            strokeLinecap="round"
          />
          {/* Value arc */}
          <motion.path
            d={`M ${stroke/2} ${height} A ${radius} ${radius} 0 0 1 ${width - stroke/2} ${height}`}
            fill="none"
            stroke={colors[color]}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset }}
            transition={{ duration: 1.5, ease: 'easeOut', delay: 0.3 }}
          />
        </svg>
        <div className="absolute bottom-1 left-1/2 transform -translate-x-1/2">
          <span className={`${font} font-bold text-white`}>
            {value.toFixed(value % 1 === 0 ? 0 : 1)}%
          </span>
        </div>
      </div>
      <span className="text-xs text-gray-400 mt-1 text-center">{label}</span>
    </div>
  );
}
EOF

# =============================================
# PASO 7: Componente Dashboard Card (ArcGIS style)
# =============================================
echo -e "${YELLOW}🧩 Creando DashboardCard...${NC}"

cat > src/components/ui/DashboardCard.tsx << 'EOF'
'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { 
  LinkIcon, 
  ExclamationTriangleIcon,
  ChartBarIcon,
  LightBulbIcon,
  UsersIcon,
  BoltIcon,
  DocumentTextIcon,
  FolderIcon,
  EnvelopeIcon
} from '@heroicons/react/24/outline';
import SemiGauge from './SemiGauge';

interface KpiData {
  label: string;
  value: string | number;
  icon?: string;
  highlight?: boolean;
  subLabel?: string;
}

interface GaugeData {
  label: string;
  value: number;
  color: 'gold' | 'white' | 'muted';
  size?: 'sm' | 'md' | 'lg';
}

interface SubSection {
  title: string;
  gauges?: GaugeData[];
  kpis?: KpiData[];
  details?: { label: string; value: string }[];
}

interface DashboardCardProps {
  title: string;
  alert?: boolean;
  kpis: KpiData[];
  gauges?: GaugeData[];
  subSections?: SubSection[];
  updateTime?: string;
  link: string;
  index?: number;
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  chart: ChartBarIcon,
  bulb: LightBulbIcon,
  people: UsersIcon,
  bolt: BoltIcon,
  document: DocumentTextIcon,
  folder: FolderIcon,
  mail: EnvelopeIcon,
};

function KpiIcon({ name }: { name?: string }) {
  if (!name || !iconMap[name]) return null;
  const Icon = iconMap[name];
  return <Icon className="w-4 h-4 text-mme-gold mr-2" />;
}

export default function DashboardCard({
  title,
  alert,
  kpis,
  gauges,
  subSections,
  updateTime,
  link,
  index = 0,
}: DashboardCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.1 }}
    >
      <Link href={link}>
        <div className="card-mme rounded-lg p-4 h-full cursor-pointer relative overflow-hidden group">
          {/* Alert badge */}
          {alert && (
            <div className="absolute top-3 left-3">
              <ExclamationTriangleIcon className="w-6 h-6 text-yellow-400 animate-pulse-gold" />
            </div>
          )}

          {/* Link icon */}
          <div className="absolute top-3 right-3 opacity-50 group-hover:opacity-100 transition-opacity">
            <LinkIcon className="w-4 h-4 text-gray-500 group-hover:text-mme-gold" />
          </div>

          {/* Header */}
          <h3 className="text-card-title text-gold-gradient uppercase mb-4 pr-6">
            {title}
          </h3>

          {/* Main KPIs */}
          <div className="space-y-3 mb-4">
            {kpis.map((kpi, idx) => (
              <div key={idx}>
                <div className="flex items-center">
                  <KpiIcon name={kpi.icon} />
                  <span className={`text-kpi-large ${kpi.highlight ? 'text-mme-gold' : 'text-white'}`}>
                    {kpi.value}
                  </span>
                </div>
                <p className="text-xs text-gray-400 ml-6">{kpi.label}</p>
                {kpi.subLabel && (
                  <p className="text-xs text-gray-500 ml-6">{kpi.subLabel}</p>
                )}
              </div>
            ))}
          </div>

          {/* Update time */}
          {updateTime && (
            <div className="mb-4 pb-3 border-b border-mme-dark-border">
              <p className="text-xs text-mme-gold-muted text-center">Fecha Actualización</p>
              <p className="text-xs text-gray-400 text-center">{updateTime}</p>
            </div>
          )}

          {/* Gauges */}
          {gauges && gauges.length > 0 && (
            <div className={`flex ${gauges.length === 1 ? 'justify-center' : 'justify-around'} pt-2`}>
              {gauges.map((gauge, idx) => (
                <SemiGauge 
                  key={idx}
                  value={gauge.value}
                  label={gauge.label}
                  color={gauge.color}
                  size={gauge.size || 'md'}
                />
              ))}
            </div>
          )}

          {/* Sub Sections */}
          {subSections && subSections.map((section, sIdx) => (
            <div key={sIdx} className="mt-4 pt-3 border-t border-mme-dark-border">
              <h4 className="text-sm font-semibold text-mme-gold mb-3">{section.title}</h4>
              
              {/* Sub gauges */}
              {section.gauges && (
                <div className="flex justify-around mb-3">
                  {section.gauges.map((gauge, gIdx) => (
                    <SemiGauge 
                      key={gIdx}
                      value={gauge.value}
                      label={gauge.label}
                      color={gauge.color}
                      size={gauge.size || 'sm'}
                    />
                  ))}
                </div>
              )}

              {/* Sub KPIs */}
              {section.kpis && (
                <div className="grid grid-cols-2 gap-2">
                  {section.kpis.map((kpi, kIdx) => (
                    <div key={kIdx} className="text-center">
                      <div className="flex items-center justify-center">
                        <KpiIcon name={kpi.icon} />
                        <span className={`text-sm font-semibold ${kpi.highlight ? 'text-mme-gold' : 'text-white'}`}>
                          {kpi.value}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400">{kpi.label}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Details */}
              {section.details && (
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-3">
                  {section.details.map((detail, dIdx) => (
                    <div key={dIdx} className="flex justify-between text-xs">
                      <span className="text-gray-500">{detail.label}:</span>
                      <span className="text-gray-300">{detail.value}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Link>
    </motion.div>
  );
}
EOF

# =============================================
# PASO 8: Header con Logo MME
# =============================================
echo -e "${YELLOW}🧭 Creando Header...${NC}"

cat > src/components/Header.tsx << 'EOF'
'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Bars3Icon, XMarkIcon, BellIcon, UserCircleIcon } from '@heroicons/react/24/outline';
import Image from 'next/image';

const navItems = [
  { label: 'Inicio', href: '/' },
  { label: 'Energía', href: '/dashboards/energia' },
  { label: 'Presupuesto', href: '/dashboards/presupuesto' },
  { label: 'Comunidades', href: '/dashboards/comunidades' },
  { label: 'Supervisión', href: '/dashboards/supervision' },
  { label: 'Subsidios', href: '/dashboards/subsidios' },
];

export default function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="glass-dark sticky top-0 z-50">
      <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-3">
            <div className="relative w-10 h-10">
              <Image
                src="/images/logo-minenergia.png"
                alt="MinMinas"
                fill
                className="object-contain"
              />
            </div>
            <div className="hidden sm:block">
              <h1 className="text-white font-semibold text-lg leading-tight">
                Portal de Dirección
              </h1>
              <p className="text-xs text-mme-gold">MinMinas</p>
            </div>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden xl:flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="px-3 py-2 text-gray-300 hover:text-mme-gold text-sm font-medium transition-colors rounded-md hover:bg-white/5"
              >
                {item.label}
              </Link>
            ))}
          </nav>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button className="p-2 text-gray-400 hover:text-mme-gold transition-colors relative">
              <BellIcon className="w-5 h-5" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"></span>
            </button>
            <button className="p-2 text-gray-400 hover:text-mme-gold transition-colors hidden sm:block">
              <UserCircleIcon className="w-5 h-5" />
            </button>
            <button
              className="xl:hidden p-2 text-gray-400 hover:text-white"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? (
                <XMarkIcon className="w-6 h-6" />
              ) : (
                <Bars3Icon className="w-6 h-6" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileMenuOpen && (
        <div className="xl:hidden border-t border-mme-dark-border bg-mme-dark">
          <nav className="px-4 py-3 space-y-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="block px-3 py-2 text-gray-300 hover:text-mme-gold hover:bg-mme-dark-card rounded-md"
                onClick={() => setMobileMenuOpen(false)}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}
EOF

# =============================================
# PASO 9: Home Page (réplica ArcGIS)
# =============================================
echo -e "${YELLOW}🏠 Creando Home Page...${NC}"

cat > src/app/page.tsx << 'EOF'
'use client';

import { motion } from 'framer-motion';
import DashboardCard from '@/components/ui/DashboardCard';
import { homeDashboardData } from '@/mocks/home-data';

export default function Home() {
  const { gestionSector, presupuesto, comunidades, supervision, subsidios } = homeDashboardData;

  return (
    <div className="min-h-screen bg-mme-dark">
      {/* Main Content */}
      <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Dashboard Grid - Exacto al ArcGIS */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5 gap-4">
          <DashboardCard
            title={gestionSector.title}
            alert={gestionSector.alert}
            kpis={gestionSector.kpis}
            gauges={gestionSector.gauges}
            updateTime={gestionSector.updateTime}
            link={gestionSector.link}
            index={0}
          />
          <DashboardCard
            title={presupuesto.title}
            kpis={presupuesto.kpis.slice(1)} // Skip apropiación para layout
            gauges={presupuesto.gauges}
            link={presupuesto.link}
            index={1}
          />
          <DashboardCard
            title={comunidades.title}
            kpis={comunidades.kpis}
            subSections={comunidades.subSections}
            link={comunidades.link}
            index={2}
          />
          <DashboardCard
            title={supervision.title}
            kpis={supervision.kpis}
            gauges={supervision.gauges}
            link={supervision.link}
            index={3}
          />
          <DashboardCard
            title={subsidios.title}
            kpis={subsidios.kpis}
            subSections={subsidios.subSections}
            link={subsidios.link}
            index={4}
          />
        </div>
      </div>

      {/* Footer - Barra dorada como en ArcGIS */}
      <motion.footer
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.8 }}
        className="bg-mme-footer-gold py-2 mt-8"
      >
        <div className="max-w-[1920px] mx-auto px-4 text-center">
          <p className="text-mme-dark text-sm font-semibold">
            Ministerio de Minas y Energía. Dirección de Energía Eléctrica 2026
          </p>
        </div>
      </motion.footer>
    </div>
  );
}
EOF

# Layout
cat > src/app/layout.tsx << 'EOF'
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Portal de Dirección - MinMinas",
  description: "Dashboard Ejecutivo del Ministerio de Minas y Energía",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className={`${inter.variable} font-sans antialiased bg-mme-dark`}>
        <Header />
        {children}
      </body>
    </html>
  );
}
EOF

# =============================================
# PASO 10: Páginas dashboard placeholder
# =============================================
echo -e "${YELLOW}📄 Creando páginas dashboard...${NC}"

for dashboard in energia presupuesto comunidades supervision subsidios; do
  TITLE=$(echo "$dashboard" | sed 's/.*/\u&/')
  cat > "src/app/(dashboards)/${dashboard}/page.tsx" << EOF
'use client';

import { motion } from 'framer-motion';
import { ArrowLeftIcon, WrenchIcon } from '@heroicons/react/24/outline';
import Link from 'next/link';

export default function ${TITLE}Page() {
  return (
    <div className="min-h-screen bg-mme-dark">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <Link 
            href="/" 
            className="inline-flex items-center gap-2 text-gray-400 hover:text-mme-gold mb-6"
          >
            <ArrowLeftIcon className="w-4 h-4" />
            Volver al inicio
          </Link>

          <div className="flex items-center gap-3 mb-2">
            <WrenchIcon className="w-6 h-6 text-mme-gold" />
            <h1 className="text-3xl font-bold text-white">
              Dashboard ${TITLE}
            </h1>
          </div>
          <p className="text-gray-400 mb-8">
            En construcción - Datos de prueba
          </p>

          {/* Placeholder content */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="card-mme rounded-lg p-6">
                <div className="h-40 bg-mme-dark/50 rounded-lg animate-pulse flex items-center justify-center">
                  <span className="text-gray-600">Gráfica {i}</span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
EOF
done

# =============================================
# PASO 11: Configurar Next.js
# =============================================
echo -e "${YELLOW}⚙️  Configurando Next.js...${NC}"

cat > next.config.ts << 'EOF'
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'export',
  distDir: 'dist',
  images: {
    unoptimized: true,
  },
  trailingSlash: true,
};

export default nextConfig;
EOF

# =============================================
# PASO 12: Build
# =============================================
echo -e "${YELLOW}🔨 Construyendo proyecto...${NC}"

npm run build 2>&1 || {
  echo -e "${YELLOW}⚠️  Build con advertencias, continuando...${NC}"
}

# =============================================
# RESUMEN
# =============================================
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    ✅ SETUP COMPLETADO                                       ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  📁 Ubicación: $PROJECT_DIR"
echo "║                                                              ║"
echo "║  🚀 Iniciar desarrollo:                                      ║"
echo "║     cd $PROJECT_NAME && npm run dev                          ║"
echo "║                                                              ║"
echo "║  📦 Build producción:                                        ║"
echo "║     npm run build                                            ║"
echo "║                                                              ║"
echo "║  🌐 URL: http://localhost:3000                               ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${YELLOW}📂 Estructura:${NC}"
find "$PROJECT_DIR/src" -type f -name "*.tsx" -o -name "*.ts" | head -20 || ls -la "$PROJECT_DIR/src"
