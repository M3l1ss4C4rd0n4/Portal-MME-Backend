# Frontend - SIEA

Dashboard interactivo para visualización de datos y métricas del sector energético.

## Opciones de Stack

### Opción 1: React + Next.js (Recomendado para producción)
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Plotly.js / Recharts para gráficos
- Leaflet para mapas

### Opción 2: Dash (Python)
- Dash + Plotly
- Bootstrap components
- Más rápido para prototipado
- Integración directa con backend Python

## Estructura (Next.js)

```
frontend/
├── src/
│   ├── app/                # App Router
│   │   ├── page.tsx        # Home
│   │   ├── demanda/
│   │   ├── perdidas/
│   │   └── asistente/      # Chat con agente
│   ├── components/
│   │   ├── charts/
│   │   ├── maps/
│   │   └── chat/
│   ├── services/           # API calls
│   │   └── api.ts
│   ├── store/              # Zustand/Redux
│   └── types/              # TypeScript types
├── public/
├── package.json
└── Dockerfile
```

## Instalación

```bash
cd frontend
npm install
# o
yarn install
```

## Desarrollo

```bash
npm run dev
# http://localhost:3000
```

## Build

```bash
npm run build
npm run start
```

## Variables de entorno

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MAPBOX_TOKEN=your_token
```
