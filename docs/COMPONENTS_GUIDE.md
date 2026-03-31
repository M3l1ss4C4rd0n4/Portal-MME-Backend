# 📚 GUÍA DE COMPONENTES MME

Guía completa de uso de los componentes reutilizables del Portal Energético.

---

## 📁 Estructura de Componentes

```
interface/components/
├── __init__.py              # Exporta todos los componentes
├── data_display/            # Visualización de datos
│   ├── kpi_card.py
│   ├── chart_card.py
│   └── data_table.py
├── feedback/                # Estados y feedback
│   ├── skeleton.py
│   ├── toast.py
│   └── modal.py
├── inputs/                  # Controles de entrada
│   ├── date_range.py
│   └── multi_select.py
├── navigation/              # Navegación
│   └── breadcrumbs.py
└── layout/                  # Layout base
    └── page_wrapper.py
```

---

## 🎯 KPI Cards

### Uso Básico

```python
from interface.components import kpi_card, kpi_row

# KPI individual
kpi = kpi_card(
    title="Generación Total",
    value="7464.0",
    unit="GWh",
    icon="fas fa-bolt",
    color="blue",
    subtitle="16/02/2026 - 18/03/2026"
)

# KPI con tendencia
kpi_con_trend = kpi_card(
    title="Generación",
    value="7464.0",
    unit="GWh",
    trend="+5.2%",
    trend_direction="up",
    color="green"
)
```

### Fila de KPIs

```python
fichas = kpi_row([
    {
        "title": "Generación Total SIN",
        "value": "7464.0",
        "unit": "GWh",
        "icon": "fas fa-bolt",
        "color": "blue",
        "subtitle": "16/02/2026 - 18/03/2026"
    },
    {
        "title": "Renovable",
        "value": "6648.6",
        "unit": "GWh",
        "icon": "fas fa-leaf",
        "color": "green",
        "subtitle": "89.1% del total"
    },
    {
        "title": "No Renovable",
        "value": "815.4",
        "unit": "GWh",
        "icon": "fas fa-industry",
        "color": "red",
        "subtitle": "10.9% del total"
    },
    {
        "title": "Último Día Disponible",
        "value": "247.6",
        "unit": "GWh",
        "icon": "fas fa-calendar-day",
        "color": "purple",
        "subtitle": "18/03/2026"
    },
], columns=4)
```

### Estados de Carga y Error

```python
from interface.components import kpi_loading_card, kpi_error_card

# Durante carga
kpi_cargando = kpi_loading_card(id="kpi-total-loading")

# En caso de error
kpi_error = kpi_error_card(
    title="Error al cargar",
    message="No se pudieron obtener los datos"
)
```

---

## 📊 Chart Cards

### Uso Básico

```python
from interface.components import chart_card
import plotly.express as px

fig = px.line(df, x="fecha", y="generacion")

grafica = chart_card(
    title="Generación por Fuente",
    figure=fig,
    id="grafica-generacion",
    subtitle="Últimos 30 días",
    download_button=True,
    height=400
)
```

### Estados Especiales

```python
from interface.components import (
    chart_card_loading,
    chart_card_error,
    chart_card_empty
)

# Cargando
chart_loading = chart_card_loading(
    title="Cargando datos...",
    height=400
)

# Error
chart_error = chart_card_error(
    title="Error al cargar gráfica",
    message="No se pudieron obtener los datos.",
    on_retry="btn-retry"  # ID del botón para reintentar
)

# Sin datos
chart_empty = chart_card_empty(
    title="Sin datos disponibles",
    message="No hay datos para el período seleccionado."
)
```

---

## 📋 Data Tables

### Uso Básico

```python
from interface.components import data_table

tabla = data_table(
    id="tabla-plantas",
    data=df.to_dict('records'),
    columns=[
        {"name": "Planta", "id": "Planta"},
        {"name": "Fuente", "id": "Fuente"},
        {"name": "Generación (GWh)", "id": "Generacion_GWh", "type": "numeric"},
        {"name": "Participación (%)", "id": "Participacion_Pct", "type": "numeric"},
    ],
    title="Detalle por Planta",
    page_size=10,
    sortable=True,
    filterable=True
)
```

### Desde DataFrame

```python
from interface.components import data_table_from_dataframe

tabla = data_table_from_dataframe(
    id="tabla-datos",
    df=df,
    title="Datos de Generación",
    page_size=15,
    sortable=True,
    numeric_columns=["Generacion_GWh", "Participacion_Pct"]
)
```

### Estado de Carga

```python
from interface.components import data_table_loading

tabla_cargando = data_table_loading(
    title="Cargando datos...",
    rows=5
)
```

---

## 💀 Skeleton Loading

### Uso Básico

```python
from interface.components.feedback.skeleton import (
    skeleton_kpi,
    skeleton_chart,
    skeleton_table,
    skeleton_page
)

# KPI
skeleton_kpi()

# Chart
skeleton_chart(height=400, show_header=True)

# Table
skeleton_table(rows=5)

# Página completa
skeleton_page(kpi_count=4, chart_count=2, table_count=1)
```

### En Callbacks de Loading

```python
from dash import Input, Output, callback
from interface.components.feedback.skeleton import skeleton_chart

@callback(
    Output("contenedor-grafica", "children"),
    Input("btn-actualizar", "n_clicks"),
    background=True,  # Callback de larga duración
    running=[(Output("contenedor-grafica", "children"), skeleton_chart(), None)]
)
def actualizar_grafica(n_clicks):
    # ... código de carga
    return chart_card(title="Resultados", figure=fig, id="grafica-resultados")
```

---

## 🔔 Toast Notifications

### Setup Inicial

Agregar en el layout principal:

```python
from interface.components import toast_container

app.layout = html.Div([
    # ... otros componentes ...
    toast_container(position="top-right")
])
```

### Uso en Callbacks

```python
from dash import Input, Output, callback
from interface.components.feedback.toast import show_toast

@callback(
    Output("toast-success", "is_open"),
    Output("toast-success", "children"),
    Input("btn-guardar", "n_clicks"),
)
def guardar_datos(n_clicks):
    if not n_clicks:
        return False, ""
    
    try:
        # ... guardar datos ...
        return show_toast("Datos guardados correctamente", "success")
    except Exception as e:
        return show_toast(f"Error: {str(e)}", "error")
```

### Tipos de Toast

```python
from interface.components.feedback.toast import show_toast

# Éxito
show_toast("Operación completada", "success")

# Error
show_toast("Ocurrió un error", "error")

# Advertencia
show_toast("Verifique los datos", "warning")

# Información
show_toast("Proceso iniciado", "info")
```

---

## 🧭 Breadcrumbs

### Uso Básico

```python
from interface.components import breadcrumbs

layout = html.Div([
    breadcrumbs(),
    # ... contenido de la página
])
```

### Registro de Callbacks

En `app.py` o donde se crea la app:

```python
from interface.components.navigation.breadcrumbs import register_breadcrumb_callbacks

app = dash.Dash(__name__)
register_breadcrumb_callbacks(app)
```

### Items Personalizados

```python
from interface.components import breadcrumbs
from interface.components.navigation.breadcrumbs import breadcrumb_item

breadcrumbs_personalizado = breadcrumbs(
    custom_items=[
        breadcrumb_item("Inicio", "/", "fas fa-home"),
        breadcrumb_item("Generación", "/generacion"),
        breadcrumb_item("Por Fuente", active=True),
    ]
)
```

---

## 🎨 Personalización de Estilos

### CSS Variables Disponibles

```css
/* Colores */
var(--mme-primary);        /* Azul institucional */
var(--mme-primary-light);  /* Azul claro */
var(--success);            /* Verde éxito */
var(--warning);            /* Naranja advertencia */
var(--danger);             /* Rojo error */

/* Tipografía */
var(--text-xs);   /* 10px - Headers tabla */
var(--text-sm);   /* 11px - Celdas tabla */
var(--text-base); /* 12px - Body */
var(--text-md);   /* 13px - Subtítulos */
var(--text-lg);   /* 15px - Valores KPI */
var(--text-xl);   /* 18px - Títulos */

/* Espaciado */
var(--space-1);  /* 4px */
var(--space-2);  /* 8px */
var(--space-3);  /* 12px */
var(--space-4);  /* 16px */
var(--space-6);  /* 24px */
```

### Clases CSS Utilitarias

```python
# En cualquier componente Dash
html.Div(
    className="d-flex justify-content-between align-items-center",
    children=[...]
)

# Espaciado
html.Div(className="mb-4")      # margin-bottom: 16px
html.Div(className="p-3")       # padding: 12px
html.Div(className="mx-auto")   # margin horizontal auto

# Texto
html.Span(className="text-muted")      # Color gris
html.Span(className="font-bold")       # Negrita
html.Span(className="text-sm")         # Tamaño pequeño

# Flexbox
html.Div(className="d-flex gap-2")     # Flex con gap
html.Div(className="justify-center")   # Centrado horizontal
html.Div(className="align-center")     # Centrado vertical
```

---

## 📝 Ejemplo Completo: Página de Generación

```python
from dash import html, callback, Output, Input
import dash_bootstrap_components as dbc
from interface.components import (
    kpi_row,
    chart_card,
    data_table,
    skeleton_page,
    toast_container
)
from interface.components.feedback.toast import show_toast

# Layout
def layout():
    return html.Div([
        # Toast container global
        toast_container(),
        
        # Filtros
        dbc.Row([
            dbc.Col([
                html.Label("Período:", className="filter-label"),
                dcc.Dropdown(
                    id="filtro-periodo",
                    options=[
                        {"label": "Último mes", "value": "1m"},
                        {"label": "Últimos 3 meses", "value": "3m"},
                        {"label": "Último año", "value": "1y"},
                    ],
                    value="1m"
                )
            ], width=3),
            dbc.Col([
                html.Button(
                    [html.I(className="fas fa-sync mr-2"), "Actualizar"],
                    id="btn-actualizar",
                    className="btn btn-primary"
                )
            ], width=2),
        ], className="filter-bar mb-4"),
        
        # Contenedor de contenido (se actualiza vía callback)
        html.Div(id="contenido-generacion")
    ])

# Callback
@callback(
    Output("contenido-generacion", "children"),
    Output("toast-success", "is_open"),
    Output("toast-success", "children"),
    Input("btn-actualizar", "n_clicks"),
    Input("filtro-periodo", "value"),
    background=True,
    running=[(
        Output("contenido-generacion", "children"),
        skeleton_page(kpi_count=4, chart_count=2),
        None
    )]
)
def actualizar_contenido(n_clicks, periodo):
    # ... cargar datos
    
    fichas = kpi_row([
        {"title": "Total", "value": "7464.0", "unit": "GWh", "icon": "fas fa-bolt", "color": "blue"},
        {"title": "Renovable", "value": "6648.6", "unit": "GWh", "icon": "fas fa-leaf", "color": "green"},
        {"title": "No Renovable", "value": "815.4", "unit": "GWh", "icon": "fas fa-industry", "color": "red"},
        {"title": "Último Día", "value": "247.6", "unit": "GWh", "icon": "fas fa-calendar", "color": "purple"},
    ])
    
    grafica = chart_card(
        title="Generación por Fuente",
        figure=fig,
        id="grafica-temporal",
        download_button=True
    )
    
    tabla = data_table(
        id="tabla-plantas",
        data=df.to_dict('records'),
        columns=[...],
        title="Detalle por Planta"
    )
    
    return html.Div([fichas, grafica, tabla]), *show_toast("Datos actualizados")
```

---

## 🔧 Mejores Prácticas

### 1. Siempre usar IDs descriptivos

```python
# ✅ Bien
chart_card(id="grafica-generacion-mensual")

# ❌ Evitar
chart_card(id="graph-1")
```

### 2. Manejar estados de carga

```python
# ✅ Siempre mostrar skeleton durante carga
running=[(Output("container", "children"), skeleton_card(), None)]

# ✅ O usar dcc.Loading
 dcc.Loading(
    type="graph",
    children=chart_card(...)
)
```

### 3. Feedback al usuario

```python
# ✅ Informar acciones importantes
show_toast("Datos exportados correctamente", "success")

# ✅ Mostrar errores amigables
except Exception as e:
    logger.error(f"Error: {e}")
    return show_toast("Error al procesar la solicitud", "error")
```

### 4. Documentar callbacks complejos

```python
@callback(
    Output("grafica", "figure"),
    Input("filtro-fecha", "start_date"),
    Input("filtro-fecha", "end_date"),
    Input("filtro-fuente", "value"),
)
def actualizar_grafica(start_date, end_date, fuente):
    """
    Actualiza la gráfica según los filtros seleccionados.
    
    Args:
        start_date: Fecha inicial (YYYY-MM-DD)
        end_date: Fecha final (YYYY-MM-DD)
        fuente: Tipo de fuente energética
    
    Returns:
        plotly.graph_objects.Figure
    """
    # ... implementación
```

---

## 🐛 Troubleshooting

### Problema: Componentes no se ven correctamente

**Solución:** Verificar que los CSS estén cargados:
```python
# En app_factory.py
external_stylesheets=[
    "/assets/css/01-variables.css",
    "/assets/css/02-components.css",
    "/assets/css/03-utilities.css",
    "/assets/css/04-pages.css",
]
```

### Problema: Callbacks no funcionan

**Solución:** Verificar que `suppress_callback_exceptions=True`:
```python
app = dash.Dash(__name__, suppress_callback_exceptions=True)
```

### Problema: Toast no aparece

**Solución:** Asegurar que `toast_container()` esté en el layout:
```python
app.layout = html.Div([
    # ... contenido ...
    toast_container()  # <-- Requerido
])
```

---

## 📞 Soporte

Para dudas o problemas:
1. Revisar logs: `tail -f logs/app.log`
2. Verificar imports: `python -c "from interface.components import kpi_card"`
3. Consultar ejemplos en: `interface/pages/`
