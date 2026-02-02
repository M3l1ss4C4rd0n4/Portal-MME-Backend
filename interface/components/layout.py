from dash import html, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
from core.constants import UIColors as COLORS, MapConfig as MAP_CONFIG

def crear_navbar_horizontal():
    """Crea una barra de navegación horizontal"""
    return dbc.NavbarSimple(
        children=[
            dbc.NavItem(dbc.NavLink("Inicio", href="/", active="exact")),
            dbc.NavItem(dbc.NavLink("Generación", href="/generacion", active="exact")),
            dbc.NavItem(dbc.NavLink("Transmisión", href="/transmision", active="exact")),
            dbc.NavItem(dbc.NavLink("Distribución", href="/distribucion", active="exact")),
            dbc.NavItem(dbc.NavLink("Comercialización", href="/comercializacion", active="exact")),
            dbc.NavItem(dbc.NavLink("Pérdidas", href="/perdidas", active="exact")),
            dbc.NavItem(dbc.NavLink("Restricciones", href="/restricciones", active="exact")),
            dbc.NavItem(dbc.NavLink("Métricas", href="/metricas", active="exact")),
        ],
        brand="Portal Energético MME",
        brand_href="/",
        color="white",
        dark=False,
        fluid=True,
        className="mb-4 shadow-sm"
    )

def crear_sidebar_universal():
    """Sidebar vacío para compatibilidad"""
    return html.Div()

def crear_header(titulo_pagina=None, descripcion_pagina=None, icono_pagina=None, informacion_adicional=None, color_tema=None):
    """Crear un header minimalista y elegante específico para cada página"""
    if not titulo_pagina:
        return html.Div()
    
    if not color_tema:
        color_tema = COLORS.PRIMARY
    
    return html.Div([
        html.Div([
            html.Div([
                html.Span([
                    html.I(className="fas fa-home me-2", style={"color": COLORS.TEXT_MUTED, "fontSize": "0.9rem"}),
                    "Ministerio de Minas y Energía"
                ], style={"fontSize": "0.85rem", "color": COLORS.TEXT_MUTED, "fontWeight": "500"}),
                html.Span(" / ", style={"color": COLORS.TEXT_MUTED, "margin": "0 0.5rem"}),
                html.Span([
                    html.I(className=f"{icono_pagina} me-2", style={"color": color_tema, "fontSize": "0.9rem"}),
                    titulo_pagina
                ], style={"fontSize": "0.85rem", "color": color_tema, "fontWeight": "600"})
            ], style={"marginBottom": "1rem", "paddingBottom": "0.5rem", "borderBottom": f"1px solid {COLORS.BORDER if hasattr(COLORS, 'BORDER') else '#E2E8F0'}"}),
            
            html.H2([
                html.I(className=f"{icono_pagina} me-3", style={"color": color_tema}),
                titulo_pagina
            ], style={"color": COLORS.TEXT_PRIMARY, "fontWeight": "600", "fontSize": "1.75rem", "marginBottom": "0.5rem"}),
            
            html.P(descripcion_pagina, style={
                "color": COLORS.TEXT_SECONDARY, "fontSize": "1rem", "marginBottom": "0", "lineHeight": "1.4"
            }) if descripcion_pagina else None
            
        ], style={
            "background": "linear-gradient(135deg, rgba(255,255,255,0.9) 0%, rgba(248,249,250,0.9) 100%)",
            "borderRadius": "8px",
            "padding": "1.5rem",
            "marginBottom": "1.5rem",
            "border": f"1px solid {COLORS.BORDER if hasattr(COLORS, 'BORDER') else '#E2E8F0'}",
            "borderLeft": f"4px solid {color_tema}",
            "boxShadow": "0 2px 4px rgba(0,0,0,0.05)"
        })
    ])

def crear_boton_regresar():
    """Crear botón para regresar al inicio"""
    return dbc.Row([
        dbc.Col([
            dbc.Button([
                html.I(className="fas fa-arrow-left me-2"),
                "Volver al Inicio"
            ], 
            color="light", 
            className="mb-4",
            href="/",
            style={"border": "2px solid #dee2e6", "color": COLORS.TEXT_PRIMARY, "fontWeight": "500"})
        ], width="auto")
    ])

def crear_navbar():
    return None

# Helpers de UI que estaban en el archivo original
def crear_metrica_moderna(titulo, valor, icono, color):
    return html.Div([
        html.Div([
            html.I(className=f"{icono} fa-2x mb-3", style={'color': color}),
            html.H3(str(valor), className="metric-value"),
            html.P(titulo, className="metric-label")
        ], className="text-center")
    ], className="metric-card animate-fade-in")

from dash import dcc, callback, Input, Output
from datetime import date, timedelta

def crear_filtro_fechas_compacto(id_prefix="global"):
    """
    Crea un componente de filtro de fechas compacto.
    """
    today = date.today()
    start_date = today - timedelta(days=30)
    
    return html.Div([
        dcc.DatePickerRange(
            id=f'fecha-filtro-{id_prefix}',
            min_date_allowed=date(2000, 1, 1),
            max_date_allowed=today,
            initial_visible_month=today,
            start_date=start_date,
            end_date=today,
            display_format='YYYY-MM-DD',
            className="compact-date-picker"
        )
    ], className="d-inline-block bg-white p-1 rounded border")

def registrar_callback_filtro_fechas(page_name):
    """
    Registra callbacks para el filtro de fechas (función legacy/placeholder).
    """
    pass
