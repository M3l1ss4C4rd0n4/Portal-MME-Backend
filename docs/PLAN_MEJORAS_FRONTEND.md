# 🎯 PLAN DE ACCIÓN: MEJORAS FRONTEND
## Portal Energético MME - Optimización Plotly Dash

**Versión:** 1.0  
**Fecha:** 2026-03-22  
**Duración Estimada:** 6-8 semanas  
**Prioridad:** Alta

---

## 📊 RESUMEN EJECUTIVO

Este plan detalla la transformación progresiva del frontend del Portal Energético para maximizar el potencial de Plotly Dash, mejorar la experiencia de usuario y optimizar el rendimiento.

**Impacto Esperado:**
- ⚡ **40%** reducción en tiempo de carga
- 🎨 **Sistema de diseño unificado** consistente
- 📱 **100% responsive** en todos los dispositivos
- ♿ **Nivel AA** de accesibilidad WCAG

---

## 🗓️ FASES DEL PROYECTO

```
┌─────────────────────────────────────────────────────────────────┐
│  FASE 1        FASE 2        FASE 3        FASE 4        FASE 5 │
│  Sem 1-2       Sem 3-4       Sem 5         Sem 6         Sem 7-8│
│  ───────────   ───────────   ───────────   ───────────   ──────│
│  Fundamentos   Componentes   Performance   UX/UI         Acces. │
│  + CSS         Reutilizables + Cache      Avanzado      + Test │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ FASE 1: FUNDAMENTOS Y SISTEMA DE DISEÑO
**Duración:** Semanas 1-2  
**Objetivo:** Consolidar CSS y establecer base sólida

### 1.1 Consolidación de CSS (Día 1-3)

**Tarea:** Unificar 11 archivos CSS en 3 archivos maestros

```
assets/css/
├── 01-variables.css      # Variables globales
├── 02-components.css     # Componentes reutilizables
├── 03-utilities.css      # Utilidades y helpers
└── 04-pages.css          # Estilos específicos por página
```

**Código: `assets/css/01-variables.css`**
```css
/* ============================================================
   VARIABLES GLOBALES - Portal Energético MME
   ============================================================ */

:root {
  /* Paleta Institucional */
  --mme-primary: #1e3a8a;
  --mme-primary-light: #3b82f6;
  --mme-primary-dark: #1e40af;
  --mme-accent: #0ea5e9;
  
  /* Semánticos */
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --info: #6366f1;
  
  /* Neutros */
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-300: #d1d5db;
  --gray-400: #9ca3af;
  --gray-500: #6b7280;
  --gray-600: #4b5563;
  --gray-700: #374151;
  --gray-800: #1f2937;
  --gray-900: #111827;
  
  /* Tipografía */
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  
  /* Tamaños de fuente */
  --text-xs: 10px;
  --text-sm: 11px;
  --text-base: 12px;
  --text-md: 13px;
  --text-lg: 15px;
  --text-xl: 18px;
  --text-2xl: 22px;
  
  /* Espaciado (4px grid) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  
  /* Bordes */
  --radius-sm: 4px;
  --radius: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  
  /* Sombras */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
  --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.05), 0 2px 4px rgba(0,0,0,0.04);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.05), 0 4px 6px rgba(0,0,0,0.03);
  
  /* Transiciones */
  --transition-fast: 0.15s ease;
  --transition: 0.2s ease;
  --transition-slow: 0.3s ease;
  
  /* Z-index */
  --z-dropdown: 1000;
  --z-sticky: 1020;
  --z-modal: 1030;
  --z-tooltip: 1040;
}

/* Tema Oscuro */
[data-theme="dark"] {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-tertiary: #334155;
  --text-primary: #f1f5f9;
  --text-secondary: #cbd5e1;
  --text-muted: #94a3b8;
  --border-color: #334155;
}
```

### 1.2 Sistema de Componentes CSS (Día 4-7)

**Código: `assets/css/02-components.css`**
```css
/* ============================================================
   COMPONENTES REUTILIZABLES
   ============================================================ */

/* ─── KPI CARD ─── */
.kpi-card {
  background: white;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius);
  padding: var(--space-3) var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  transition: all var(--transition);
  min-height: 72px;
}

.kpi-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--mme-primary-light);
  transform: translateY(-1px);
}

.kpi-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 16px;
}

.kpi-icon.blue { background: #eff6ff; color: var(--mme-primary); }
.kpi-icon.green { background: #ecfdf5; color: var(--success); }
.kpi-icon.orange { background: #fffbeb; color: var(--warning); }
.kpi-icon.red { background: #fef2f2; color: var(--danger); }
.kpi-icon.purple { background: #eef2ff; color: var(--info); }

.kpi-content {
  flex: 1;
  min-width: 0;
}

.kpi-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--gray-500);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kpi-value {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--gray-800);
  line-height: 1.1;
}

.kpi-unit {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--gray-500);
  margin-left: 3px;
}

.kpi-subtext {
  font-size: var(--text-xs);
  color: var(--gray-400);
  margin-top: 2px;
}

/* ─── CHART CARD ─── */
.chart-card {
  background: white;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius);
  overflow: hidden;
  transition: box-shadow var(--transition);
}

.chart-card:hover {
  box-shadow: var(--shadow-md);
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--gray-100);
}

.chart-title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--gray-800);
  margin: 0;
}

.chart-subtitle {
  font-size: var(--text-sm);
  color: var(--gray-500);
  margin: 0;
}

.chart-body {
  padding: var(--space-2);
}

/* ─── DATA TABLE COMPACT ─── */
.table-compact {
  --table-font-size: var(--text-sm);
  --table-header-bg: var(--gray-50);
  --table-border: var(--gray-200);
}

.table-compact .dash-header {
  font-size: var(--text-xs) !important;
  font-weight: 600 !important;
  padding: 6px 8px !important;
  background: var(--table-header-bg) !important;
  border-bottom: 2px solid var(--table-border) !important;
}

.table-compact .dash-cell {
  font-size: var(--table-font-size) !important;
  padding: 5px 8px !important;
  border-bottom: 1px solid var(--gray-100) !important;
}

.table-compact tr:nth-child(even) .dash-cell {
  background: #fafbfc !important;
}

/* ─── FILTER BAR ─── */
.filter-bar {
  background: white;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius);
  padding: var(--space-3) var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}

.filter-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--gray-500);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

/* ─── BUTTONS ─── */
.btn {
  font-weight: 600;
  letter-spacing: 0.3px;
  border-radius: var(--radius);
  padding: 8px 16px;
  transition: all var(--transition-fast);
  border: none;
  font-size: var(--text-sm);
  cursor: pointer;
}

.btn-primary {
  background: var(--mme-primary);
  color: white;
}

.btn-primary:hover {
  background: var(--mme-primary-dark);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-secondary {
  background: white;
  color: var(--gray-700);
  border: 1px solid var(--gray-300);
}

.btn-secondary:hover {
  background: var(--gray-50);
  border-color: var(--gray-400);
}

/* ─── ALERTS ─── */
.alert {
  border: none;
  border-left: 4px solid;
  border-radius: var(--radius);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
}

.alert-info {
  background: #eff6ff;
  border-color: var(--mme-primary-light);
  color: var(--mme-primary);
}

.alert-success {
  background: #ecfdf5;
  border-color: var(--success);
  color: #065f46;
}

.alert-warning {
  background: #fffbeb;
  border-color: var(--warning);
  color: #92400e;
}

.alert-danger {
  background: #fef2f2;
  border-color: var(--danger);
  color: #991b1b;
}
```

### 1.3 Actualizar app_factory.py (Día 8-10)

```python
# core/app_factory.py

def create_app():
    """Application factory con configuración optimizada."""
    
    app = dash.Dash(
        __name__,
        use_pages=True,
        pages_folder="interface/pages",
        assets_folder="assets",
        assets_ignore='.*\.scss',  # Ignorar archivos SCSS si los hay
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
            # Nuevo sistema CSS unificado
            "/assets/css/01-variables.css",
            "/assets/css/02-components.css",
            "/assets/css/03-utilities.css",
            "/assets/css/04-pages.css",
        ],
        suppress_callback_exceptions=True,
        # Meta tags para SEO y responsive
        meta_tags=[
            {"name": "viewport", "content": "width=device-width, initial-scale=1"},
            {"http-equiv": "X-UA-Compatible", "content": "IE=edge"},
            {"name": "theme-color", "content": "#1e3a8a"},
            # SEO
            {"property": "og:title", "content": "Portal Energético — MME"},
            {"property": "og:description", "content": "Indicadores energéticos de Colombia"},
            {"property": "og:type", "content": "website"},
            {"property": "og:image", "content": "/assets/images/og-preview.jpg"},
        ],
        # Configuración de carga
        eager_loading=False,  # Lazy loading de páginas
        compress=True,  # Compresión de assets
    )
    
    # Configurar caché
    setup_cache(app)
    
    return app
```

### ✅ CRITERIOS DE ÉXITO FASE 1
- [ ] Todos los CSS consolidados en 4 archivos
- [ ] Sistema de variables funcionando
- [ ] Componentes base estilizados
- [ ] Carga inicial de CSS reducida en 50%

---

## 🧩 FASE 2: COMPONENTES REUTILIZABLES EN PYTHON
**Duración:** Semanas 3-4  
**Objetivo:** Crear librería de componentes Python

### 2.1 Estructura de Componentes (Día 1-3)

```
interface/components/
├── __init__.py
├── layout/
│   ├── __init__.py
│   ├── navbar.py
│   ├── sidebar.py
│   └── footer.py
├── data_display/
│   ├── __init__.py
│   ├── kpi_card.py
│   ├── chart_card.py
│   └── data_table.py
├── feedback/
│   ├── __init__.py
│   ├── toast.py
│   ├── modal.py
│   └── skeleton.py
├── inputs/
│   ├── __init__.py
│   ├── date_range.py
│   ├── multi_select.py
│   └── search.py
└── navigation/
    ├── __init__.py
    ├── breadcrumbs.py
    ├── pagination.py
    └── tabs.py
```

### 2.2 Componentes Clave (Día 4-10)

**`interface/components/data_display/kpi_card.py`**
```python
"""
Componente KPI Card reutilizable con múltiples variantes.
"""
from dash import html
import dash_bootstrap_components as dbc
from typing import Optional, Literal


def kpi_card(
    title: str,
    value: str,
    unit: str = "",
    icon: str = "fas fa-chart-line",
    color: Literal["blue", "green", "orange", "red", "purple", "cyan"] = "blue",
    subtitle: Optional[str] = None,
    trend: Optional[str] = None,
    trend_direction: Literal["up", "down", "flat"] = "flat",
    sparkline: Optional[html.Component] = None,
    id: Optional[str] = None,
) -> html.Div:
    """
    Crea una tarjeta KPI con estilo consistente.
    
    Args:
        title: Título de la métrica
        value: Valor numérico
        unit: Unidad (GWh, %, etc.)
        icon: Icono FontAwesome
        color: Color del tema
        subtitle: Texto secundario
        trend: Cambio porcentual
        trend_direction: Dirección del trend
        sparkline: Gráfico sparkline opcional
        id: ID del componente
    
    Returns:
        Componente html.Div
    """
    
    # Variación (trend)
    trend_component = None
    if trend:
        arrow = {"up": "▲", "down": "▼", "flat": "—"}[trend_direction]
        trend_class = f"kpi-trend {trend_direction}"
        trend_component = html.Span(
            f"{arrow} {trend}",
            className=trend_class
        )
    
    # Subtítulo
    subtitle_component = None
    if subtitle:
        subtitle_component = html.Div(
            subtitle,
            className="kpi-subtitle"
        )
    
    return html.Div(
        className=f"kpi-card kpi-{color}",
        id=id,
        children=[
            # Icono
            html.Div(
                html.I(className=icon),
                className=f"kpi-icon {color}"
            ),
            
            # Contenido
            html.Div(
                className="kpi-content",
                children=[
                    html.Div(title, className="kpi-label"),
                    html.Div(
                        className="kpi-value-wrapper",
                        children=[
                            html.Span(value, className="kpi-value"),
                            html.Span(unit, className="kpi-unit") if unit else None,
                            trend_component,
                        ]
                    ),
                    subtitle_component,
                ]
            ),
            
            # Sparkline opcional
            html.Div(
                sparkline,
                className="kpi-sparkline"
            ) if sparkline else None,
        ]
    )


def kpi_row(
    kpis: list,
    columns: int = 3,
) -> dbc.Row:
    """
    Crea una fila de KPIs responsive.
    
    Args:
        kpis: Lista de diccionarios con props de kpi_card
        columns: Número de columnas (1-4)
    
    Returns:
        dbc.Row con los KPIs
    """
    # Calcular ancho de columna
    width = 12 // columns
    
    return dbc.Row(
        [
            dbc.Col(
                kpi_card(**kpi),
                width=12,
                md=width,
                className="mb-3"
            )
            for kpi in kpis
        ],
        className="kpi-row"
    )
```

**`interface/components/data_display/chart_card.py`**
```python
"""
Componente Chart Card con header y controles opcionales.
"""
from dash import html, dcc
import dash_bootstrap_components as dbc
from typing import Optional, List, Dict
import plotly.graph_objects as go


def chart_card(
    title: str,
    figure: go.Figure,
    id: str,
    subtitle: Optional[str] = None,
    controls: Optional[List[html.Component]] = None,
    download_button: bool = False,
    height: int = 350,
    className: str = "",
) -> dbc.Card:
    """
    Crea una tarjeta de gráfica consistente.
    
    Args:
        title: Título de la gráfica
        figure: Figura de Plotly
        id: ID base para el componente
        subtitle: Subtítulo opcional
        controls: Controles adicionales (botones, dropdowns)
        download_button: Mostrar botón de descarga
        height: Altura de la gráfica
        className: Clases CSS adicionales
    
    Returns:
        dbc.Card con la gráfica
    """
    
    # Header con título y controles
    header_children = [
        html.Div(
            [
                html.H5(title, className="chart-title"),
                html.Small(subtitle, className="chart-subtitle") if subtitle else None,
            ]
        )
    ]
    
    if controls:
        header_children.append(
            html.Div(controls, className="chart-controls")
        )
    
    if download_button:
        header_children.append(
            html.Button(
                html.I(className="fas fa-download"),
                className="btn btn-sm btn-outline-secondary",
                id=f"{id}-download-btn"
            )
        )
    
    return dbc.Card(
        className=f"chart-card {className}",
        children=[
            dbc.CardHeader(
                header_children,
                className="chart-header d-flex justify-content-between align-items-center"
            ),
            dbc.CardBody(
                dcc.Graph(
                    id=id,
                    figure=figure,
                    config={
                        'displayModeBar': False,
                        'responsive': True,
                    },
                    style={'height': f'{height}px'}
                ),
                className="chart-body p-0"
            ),
        ]
    )
```

**`interface/components/feedback/skeleton.py`**
```python
"""
Componentes Skeleton para estados de carga.
"""
from dash import html


def skeleton_card():
    """Skeleton para tarjetas de KPI."""
    return html.Div(
        className="skeleton-card",
        children=[
            html.Div(className="skeleton-icon"),
            html.Div(
                className="skeleton-content",
                children=[
                    html.Div(className="skeleton-line w-50"),
                    html.Div(className="skeleton-line w-75"),
                ]
            )
        ]
    )


def skeleton_chart():
    """Skeleton para gráficas."""
    return html.Div(
        className="skeleton-chart",
        children=[
            html.Div(className="skeleton-header"),
            html.Div(className="skeleton-body"),
        ]
    )


def skeleton_table(rows: int = 5):
    """Skeleton para tablas."""
    return html.Div(
        className="skeleton-table",
        children=[
            html.Div(className="skeleton-row header"),
            *[html.Div(className="skeleton-row") for _ in range(rows)]
        ]
    )
```

### 2.3 CSS para Skeleton (Día 11-14)

```css
/* assets/css/03-utilities.css */

/* ─── SKELETON LOADING ─── */
.skeleton-card,
.skeleton-chart,
.skeleton-table {
  background: white;
  border-radius: var(--radius);
  overflow: hidden;
}

.skeleton-icon,
.skeleton-line,
.skeleton-header,
.skeleton-body,
.skeleton-row {
  background: linear-gradient(
    90deg,
    var(--gray-100) 25%,
    var(--gray-200) 50%,
    var(--gray-100) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
  border-radius: var(--radius-sm);
}

@keyframes skeleton-loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.skeleton-icon {
  width: 40px;
  height: 40px;
}

.skeleton-line {
  height: 12px;
  margin-bottom: 8px;
}

.skeleton-line.w-50 { width: 50%; }
.skeleton-line.w-75 { width: 75%; }

.skeleton-header {
  height: 40px;
  margin-bottom: 16px;
}

.skeleton-body {
  height: 200px;
}

.skeleton-row {
  height: 32px;
  margin-bottom: 4px;
}

.skeleton-row.header {
  background: var(--gray-200);
  animation: none;
}
```

### ✅ CRITERIOS DE ÉXITO FASE 2
- [ ] 15+ componentes reutilizables creados
- [ ] Documentación de uso de cada componente
- [ ] Todas las páginas migradas a componentes nuevos
- [ ] Skeleton loading implementado

---

## ⚡ FASE 3: PERFORMANCE Y OPTIMIZACIÓN
**Duración:** Semana 5  
**Objetivo:** Reducir tiempos de carga en 40%

### 3.1 Sistema de Caché con Redis (Día 1-2)

**`core/cache_manager.py`**
```python
"""
Sistema de caché centralizado con Redis.
"""
from functools import wraps
import pickle
import hashlib
from datetime import datetime, timedelta
import redis
from flask_caching import Cache
import logging

logger = logging.getLogger(__name__)

# Configuración de Redis
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
    decode_responses=False  # Para poder usar pickle
)

# Flask-Caching para Dash
cache = Cache(config={
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_URL': 'redis://localhost:6379/0',
    'CACHE_DEFAULT_TIMEOUT': 300,  # 5 minutos
})


def cache_dataframe(timeout: int = 300, key_prefix: str = "df"):
    """
    Decorador para cachear DataFrames.
    
    Args:
        timeout: Tiempo en segundos
        key_prefix: Prefijo para la clave
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave única
            key_data = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            key = f"{key_prefix}:{hashlib.md5(key_data.encode()).hexdigest()}"
            
            # Intentar obtener del caché
            try:
                cached = redis_client.get(key)
                if cached:
                    logger.info(f"✅ Cache HIT: {key}")
                    return pickle.loads(cached)
            except Exception as e:
                logger.warning(f"⚠️ Error leyendo cache: {e}")
            
            # Ejecutar función
            result = func(*args, **kwargs)
            
            # Guardar en caché
            try:
                redis_client.setex(
                    key,
                    timedelta(seconds=timeout),
                    pickle.dumps(result)
                )
                logger.info(f"💾 Cache SET: {key}")
            except Exception as e:
                logger.warning(f"⚠️ Error guardando cache: {e}")
            
            return result
        return wrapper
    return decorator


def invalidate_cache(pattern: str = "*"):
    """
    Invalida caché por patrón.
    
    Args:
        pattern: Patrón de claves a eliminar
    """
    try:
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info(f"🗑️ Cache invalidado: {len(keys)} claves")
    except Exception as e:
        logger.error(f"❌ Error invalidando cache: {e}")
```

### 3.2 Lazy Loading de Páginas (Día 3-4)

```python
# interface/pages/__init__.py

# Lazy import de páginas pesadas
def get_generacion_fuentes_layout():
    """Importa la página de generación solo cuando se necesita."""
    from .generacion_fuentes_unificado import layout
    return layout()


def get_hidrologia_layout():
    """Importa la página de hidrología solo cuando se necesita."""
    from .generacion_hidraulica_hidrologia import layout
    return layout()


# Mapeo de rutas a funciones de layout
LAZY_PAGES = {
    '/generacion/fuentes': get_generacion_fuentes_layout,
    '/generacion/hidrologia': get_hidrologia_layout,
    # ... más páginas
}
```

### 3.3 Optimización de Assets (Día 5-7)

**Script de build: `scripts/build_assets.py`**
```python
#!/usr/bin/env python3
"""
Script de build para optimizar assets.
"""
import subprocess
import os
from pathlib import Path

ASSETS_DIR = Path("assets")
DIST_DIR = Path("assets/dist")


def minify_css():
    """Minifica archivos CSS."""
    css_files = list(ASSETS_DIR.glob("css/*.css"))
    
    for css_file in css_files:
        output = DIST_DIR / f"{css_file.stem}.min.css"
        
        subprocess.run([
            "cleancss", "-o", str(output), str(css_file)
        ], check=True)
        
        original_size = css_file.stat().st_size
        minified_size = output.stat().st_size
        savings = (1 - minified_size / original_size) * 100
        
        print(f"✅ {css_file.name}: {original_size/1024:.1f}KB → {minified_size/1024:.1f}KB ({savings:.1f}%)")


def optimize_images():
    """Optimiza imágenes."""
    image_dirs = ["assets/images", "assets/icons"]
    
    for img_dir in image_dirs:
        for img in Path(img_dir).glob("*.{png,jpg,jpeg}"):
            subprocess.run([
                "imagemin", str(img), "--out-dir", str(img.parent), "--plugin=pngquant"
            ])


if __name__ == "__main__":
    DIST_DIR.mkdir(exist_ok=True)
    minify_css()
    optimize_images()
```

### 3.4 Compresión Gzip (Día 8)

```python
# En app_factory.py
from flask_compress import Compress

def create_app():
    app = dash.Dash(__name__)
    
    # Compresión Gzip
    Compress(app.server)
    
    return app
```

### ✅ CRITERIOS DE ÉXITO FASE 3
- [ ] Redis configurado y funcionando
- [ ] Tiempos de carga reducidos en 40%
- [ ] Scripts de build automatizados
- [ ] Score Lighthouse > 80

---

## 🎨 FASE 4: UX/UI AVANZADO
**Duración:** Semana 6  
**Objetivo:** Experiencia de usuario premium

### 4.1 Tema Oscuro/Claro (Día 1-3)

**`interface/components/theme_toggle.py`**
```python
"""
Toggle de tema oscuro/claro.
"""
from dash import html, callback, Output, Input, State
import dash_bootstrap_components as dbc


def theme_toggle():
    """Crea el toggle de tema."""
    return html.Div(
        className="theme-toggle",
        children=[
            html.I(className="fas fa-sun", id="theme-icon-sun"),
            dbc.Switch(
                id="theme-switch",
                value=False,
                className="theme-switch"
            ),
            html.I(className="fas fa-moon", id="theme-icon-moon"),
            dcc.Store(id="theme-store", data="light")
        ]
    )


# Callback para cambiar tema
@callback(
    Output("theme-store", "data"),
    Output("app-container", "className"),
    Input("theme-switch", "value"),
    State("theme-store", "data")
)
def toggle_theme(is_dark, current_theme):
    """Cambia entre tema claro y oscuro."""
    new_theme = "dark" if is_dark else "light"
    return new_theme, f"app-container theme-{new_theme}"
```

**CSS para temas:**
```css
/* Tema Claro (default) */
.app-container {
  --bg-primary: #ffffff;
  --bg-secondary: #f9fafb;
  --text-primary: #111827;
  --text-secondary: #6b7280;
  --border-color: #e5e7eb;
}

/* Tema Oscuro */
.app-container.theme-dark {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --border-color: #334155;
}
```

### 4.2 Toast Notifications (Día 4-5)

```python
# interface/components/feedback/toast.py

def toast_container():
    """Contenedor para toasts."""
    return html.Div(
        className="toast-container",
        children=[
            dbc.Toast(
                id="toast-success",
                header="Éxito",
                is_open=False,
                dismissable=True,
                duration=4000,
                icon="success",
                className="toast-success"
            ),
            dbc.Toast(
                id="toast-error",
                header="Error",
                is_open=False,
                dismissable=True,
                duration=4000,
                icon="danger",
                className="toast-error"
            ),
        ]
    )


def show_toast(message: str, type_: str = "success"):
    """Helper para mostrar toasts desde callbacks."""
    return True, message
```

### 4.3 Breadcrumbs y Navegación (Día 6-7)

```python
# interface/components/navigation/breadcrumbs.py

import dash
from dash import html
import dash_bootstrap_components as dbc


def breadcrumbs():
    """Genera breadcrumbs automáticamente basado en la URL actual."""
    
    # Mapeo de rutas a nombres
    ROUTES = {
        "/": ("Inicio", "/"),
        "/generacion": ("Generación", "/generacion"),
        "/generacion/fuentes": ("Por Fuente", "/generacion/fuentes"),
        "/transmision": ("Transmisión", "/transmision"),
        "/distribucion": ("Distribución", "/distribucion"),
    }
    
    current_path = dash.page_registry.get("path", "/")
    
    items = [{"label": "Inicio", "href": "/"}]
    
    # Construir jerarquía
    parts = current_path.strip("/").split("/")
    current = ""
    
    for part in parts:
        current += f"/{part}"
        if current in ROUTES:
            items.append({
                "label": ROUTES[current][0],
                "href": ROUTES[current][1],
                "active": current == current_path
            })
    
    return dbc.Breadcrumb(
        items=items,
        className="app-breadcrumbs"
    )
```

### 4.4 Tooltips y Ayuda Contextual (Día 8)

```python
# interface/components/feedback/tooltip.py

def help_tooltip(text: str, icon: str = "fas fa-question-circle"):
    """Crea un icono con tooltip de ayuda."""
    return html.Span(
        [
            html.I(className=icon, id="help-icon"),
            dbc.Tooltip(
                text,
                target="help-icon",
                placement="top",
                className="help-tooltip"
            )
        ],
        className="help-icon-wrapper"
    )
```

### ✅ CRITERIOS DE ÉXITO FASE 4
- [ ] Tema oscuro/claro funcionando
- [ ] Sistema de toasts implementado
- [ ] Breadcrumbs en todas las páginas
- [ ] Tooltips de ayuda en KPIs principales

---

## ♿ FASE 5: ACCESIBILIDAD Y RESPONSIVE
**Duración:** Semanas 7-8  
**Objetivo:** Cumplir WCAG 2.1 AA

### 5.1 Accesibilidad (Día 1-5)

**Checklist de Implementación:**

```python
# interface/components/a11y.py

"""
Componentes accesibles.
"""
from dash import html
import dash_bootstrap_components as dbc


def accessible_table(data, columns, id):
    """Tabla accesible con ARIA labels."""
    return dash_table.DataTable(
        id=id,
        data=data,
        columns=columns,
        # Accesibilidad
        aria_label="Tabla de datos",
        role="grid",
        # Navegación por teclado
        sort_action='native',
        filter_action='native',
        row_selectable='single',
        # Contraste alto
        style_header={
            'backgroundColor': '#1e3a8a',
            'color': 'white',
            'fontWeight': 'bold'
        },
        style_cell={
            'fontFamily': 'Inter, sans-serif',
            'fontSize': '12px'
        },
        # Focus visible
        css=[{
            'selector': '.dash-spreadsheet td:focus',
            'rule': 'outline: 2px solid #3b82f6; outline-offset: -2px;'
        }]
    )


def skip_link():
    """Link para saltar navegación (accesibilidad)."""
    return html.A(
        "Saltar al contenido principal",
        href="#main-content",
        className="skip-link"
    )
```

**CSS para accesibilidad:**
```css
/* Skip link para navegación por teclado */
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  background: var(--mme-primary);
  color: white;
  padding: 8px;
  text-decoration: none;
  z-index: 10000;
}

.skip-link:focus {
  top: 0;
}

/* Focus visible en todos los elementos interactivos */
button:focus,
a:focus,
input:focus,
select:focus {
  outline: 2px solid var(--mme-primary-light);
  outline-offset: 2px;
}

/* Contraste mínimo 4.5:1 */
.text-muted {
  color: #6b7280 !important;  /* Ratio 7:1 en fondo blanco */
}

/* No usar solo color para transmitir información */
.kpi-trend.up::before {
  content: "▲ ";
}

.kpi-trend.down::before {
  content: "▼ ";
}
```

### 5.2 Responsive Design (Día 6-10)

**Breakpoints:**
```css
/* Mobile First */

/* Default: Mobile (< 576px) */
.kpi-card {
  flex-direction: column;
  text-align: center;
}

/* Tablet (>= 576px) */
@media (min-width: 576px) {
  .kpi-card {
    flex-direction: row;
    text-align: left;
  }
}

/* Desktop (>= 992px) */
@media (min-width: 992px) {
  .chart-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 20px;
  }
}

/* Large Desktop (>= 1400px) */
@media (min-width: 1400px) {
  .chart-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
```

**Componente Responsive:**
```python
# interface/components/layout/responsive.py

def responsive_grid(children, breakpoints=None):
    """
    Crea una grid responsive.
    
    Args:
        children: Lista de componentes
        breakpoints: Dict con columnas por breakpoint
            default: {'xs': 12, 'sm': 6, 'md': 4, 'lg': 3}
    """
    if breakpoints is None:
        breakpoints = {'xs': 12, 'sm': 6, 'md': 4, 'lg': 3}
    
    return dbc.Row(
        [
            dbc.Col(child, **breakpoints, className="mb-3")
            for child in children
        ]
    )
```

### ✅ CRITERIOS DE ÉXITO FASE 5
- [ ] Score Lighthouse Accesibilidad > 90
- [ ] Navegación completa por teclado
- [ ] Contraste válido en todas las páginas
- [ ] Diseño responsive en 4 breakpoints

---

## 🧪 FASE 6: TESTING Y CI/CD
**Duración:** Continuo  
**Objetivo:** Calidad automatizada

### 6.1 Tests de Frontend

```python
# tests/test_components.py

import pytest
from dash.testing.application_runners import import_app


def test_kpi_card_rendering():
    """Test que el KPI card renderiza correctamente."""
    from interface.components.data_display.kpi_card import kpi_card
    
    component = kpi_card(
        title="Test",
        value="100",
        unit="GWh"
    )
    
    assert component is not None
    assert "kpi-card" in component.className


def test_theme_toggle():
    """Test del toggle de tema."""
    from interface.components.theme_toggle import theme_toggle
    
    component = theme_toggle()
    assert component is not None
```

### 6.2 CI/CD Pipeline

**.github/workflows/frontend.yml**
```yaml
name: Frontend CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest dash[testing]
    
    - name: Run tests
      run: pytest tests/
    
    - name: Build assets
      run: python scripts/build_assets.py
    
    - name: Lighthouse CI
      run: |
        npm install -g @lhci/cli
        lhci autorun
```

### ✅ CRITERIOS DE ÉXITO FASE 6
- [ ] Cobertura de tests > 70%
- [ ] Pipeline CI/CD funcionando
- [ ] Lighthouse CI integrado
- [ ] Deploy automático a staging

---

## 📈 MÉTRICAS DE ÉXITO

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| **Tiempo de carga inicial** | 4.2s | < 2.5s | **40%** |
| **First Contentful Paint** | 2.1s | < 1.2s | **43%** |
| **Lighthouse Performance** | 62 | > 85 | **37%** |
| **Lighthouse Accesibilidad** | 78 | > 90 | **15%** |
| **Tamaño CSS** | 45KB | < 20KB | **56%** |
| **Tamaño JS** | 180KB | < 120KB | **33%** |

---

## 🚀 CHECKLIST DE IMPLEMENTACIÓN

### Semana 1-2: Fundamentos
- [ ] Crear `assets/css/01-variables.css`
- [ ] Crear `assets/css/02-components.css`
- [ ] Crear `assets/css/03-utilities.css`
- [ ] Crear `assets/css/04-pages.css`
- [ ] Actualizar `app_factory.py`
- [ ] Eliminar CSS antiguos (backup primero)

### Semana 3-4: Componentes
- [ ] Crear estructura de carpetas en `components/`
- [ ] Implementar `kpi_card.py`
- [ ] Implementar `chart_card.py`
- [ ] Implementar `skeleton.py`
- [ ] Documentar uso de componentes
- [ ] Migrar páginas a nuevos componentes

### Semana 5: Performance
- [ ] Configurar Redis
- [ ] Implementar `cache_manager.py`
- [ ] Agregar caché a callbacks pesados
- [ ] Crear `scripts/build_assets.py`
- [ ] Configurar compresión Gzip
- [ ] Optimizar imágenes

### Semana 6: UX/UI
- [ ] Implementar tema oscuro/claro
- [ ] Crear sistema de toasts
- [ ] Agregar breadcrumbs
- [ ] Implementar tooltips de ayuda
- [ ] Skeleton loading en todas las páginas

### Semana 7-8: A11y + Responsive
- [ ] Agregar skip links
- [ ] Implementar focus visible
- [ ] Validar contraste de colores
- [ ] Agregar ARIA labels
- [ ] Implementar breakpoints responsive
- [ ] Testing en múltiples dispositivos

### Continuo
- [ ] Configurar CI/CD
- [ ] Escribir tests de componentes
- [ ] Integrar Lighthouse CI
- [ ] Documentar en README

---

## 📝 NOTAS IMPORTANTES

1. **Backup**: Siempre hacer backup antes de eliminar archivos CSS antiguos
2. **Testing**: Probar en múltiples navegadores (Chrome, Firefox, Safari, Edge)
3. **Rollback**: Mantener rama `legacy-css` por si hay que revertir
4. **Comunicación**: Informar al equipo sobre cambios en componentes
5. **Documentación**: Actualizar documentación tan pronto como se implemente

---

## 🆘 SOPORTE

Si encuentras problemas durante la implementación:

1. **Revisar logs**: `tail -f logs/app.log | grep ERROR`
2. **Limpiar caché**: Eliminar `__pycache__` y recargar
3. **Verificar imports**: Asegurar rutas correctas en `app_factory.py`
4. **Consultar documentación**: Ver `docs/` para ejemplos

---

**¿Listo para comenzar?** Recomiendo empezar con la **FASE 1** y avanzar gradualmente. Cada fase se puede desplegar independientemente.
