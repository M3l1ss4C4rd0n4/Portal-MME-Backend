
def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

"""
Componentes del dashboard Dash
"""
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output, State, callback, register_page
import pandas as pd
from .config import COLORS, MAP_CONFIG

def crear_sidebar_universal():
    """Crear un sidebar universal que se puede mostrar/ocultar"""
    return html.Div([
        # Botón toggle para mostrar/ocultar sidebar
        html.Button([
            html.I(className="fas fa-bars")
        ], id="sidebar-toggle", className="btn btn-primary", style={
            'position': 'fixed',
            'top': '15px',
            'left': '15px',
            'zIndex': '1100',
            'borderRadius': '8px',
            'padding': '8px 10px',
            'fontSize': '0.9rem'
        }),
        
        # Overlay (respeta el header)
        html.Div(id="sidebar-overlay", className="sidebar-overlay", style={
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'width': '100vw',
            'height': '100vh',
            'background': 'rgba(0,0,0,0.3)',
            'zIndex': '1044',
            'display': 'none'
        }),
        
        # Sidebar principal
        html.Div([
            # Header del sidebar
            html.Div([
                html.Div([
                    html.H6("Portal Energético", className="mb-0", style={"color": "#3D3D3D", "fontWeight": "bold", "fontSize": "1.1rem"})
                ], className="d-flex align-items-center"),
                
                html.Button([
                    html.I(className="fas fa-times")
                ], id="sidebar-close", className="btn btn-link p-1", style={
                    'color': COLORS['text_secondary'],
                    'fontSize': '1rem',
                    'border': 'none',
                    'background': 'transparent',
                    'position': 'absolute',
                    'right': '15px',
                    'top': '15px'
                })
            ], style={'position': 'relative', 'padding': '20px', 'borderBottom': f'1px solid {COLORS["border"]}'}),
            
            # Contenido del sidebar
            html.Div([
                # Enlaces de navegación principales
                html.H6([
                    html.I(className="fas fa-compass me-2", style={"color": "#1e3a8a"}),
                    "Navegación Principal"
                ], className="mb-3", style={'color': '#1e3a8a', 'fontWeight': '600', 'fontSize': '0.95rem'}),
                
                # Inicio
                dbc.NavLink([
                    html.I(className="fas fa-home me-3", style={"color": "#1e3a8a"}),
                    "Inicio"
                ], href="/", active="exact", className="nav-link-sidebar mb-2"),
                
                # Métricas
                dbc.NavLink([
                    html.I(className="fas fa-chart-line me-3", style={"color": "#1e3a8a"}),
                    "Métricas"
                ], href="/metricas", active="exact", className="nav-link-sidebar mb-3"),
                
                html.Hr(),
                
                # Sectores del Sistema Energético
                html.H6([
                    html.I(className="fas fa-bolt me-2", style={"color": "#1e3a8a"}),
                    "Sectores Energéticos"
                ], className="mb-3", style={'color': '#1e3a8a', 'fontWeight': '600', 'fontSize': '0.95rem'}),
                
                # Acordeón de sectores
                dbc.Accordion([
                    # GENERACIÓN
                    dbc.AccordionItem([
                        dbc.NavLink([
                            html.I(className="fas fa-tint me-3", style={"color": "#1e3a8a"}),
                            "Hidrología"
                        ], href="/generacion/hidraulica/hidrologia", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-bolt me-3", style={"color": "#1e3a8a"}),
                            "Generación por Fuentes"
                        ], href="/generacion/fuentes", active="exact", className="nav-link-sidebar ms-2")
                    ], title="Generación", item_id="generacion"),
                    
                    # TRANSMISIÓN
                    dbc.AccordionItem([
                        dbc.NavLink([
                            html.I(className="fas fa-chart-network me-3", style={"color": "#1e3a8a"}),
                            "Disponibilidad STN"
                        ], href="/transmision", active="exact", className="nav-link-sidebar ms-2 mb-2 fw-bold"),
                        html.Hr(className="my-2 mx-3", style={"borderColor": "#e5e7eb"}),
                        dbc.NavLink([
                            html.I(className="fas fa-plug me-3", style={"color": "#1e3a8a"}),
                            "Líneas de Transmisión"
                        ], href="/transmision/lineas", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-building me-3", style={"color": "#1e3a8a"}),
                            "Subestaciones"
                        ], href="/transmision/subestaciones", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-tools me-3", style={"color": "#1e3a8a"}),
                            "Mantenimientos"
                        ], href="/transmision/mantenimientos", active="exact", className="nav-link-sidebar ms-2")
                    ], title="Transmisión", item_id="transmision"),
                    
                    # DEMANDA
                    dbc.AccordionItem([
                        dbc.NavLink([
                            html.I(className="fas fa-chart-area me-3", style={"color": "#1e3a8a"}),
                            "Demanda Nacional"
                        ], href="/demanda", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-chart-line me-3", style={"color": "#1e3a8a"}),
                            "Proyecciones"
                        ], href="/demanda/proyecciones", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-industry me-3", style={"color": "#1e3a8a"}),
                            "Sectores"
                        ], href="/demanda/sectores", active="exact", className="nav-link-sidebar ms-2")
                    ], title="Demanda", item_id="demanda"),
                    
                    # PÉRDIDAS
                    dbc.AccordionItem([
                        dbc.NavLink([
                            html.I(className="fas fa-chart-line me-3"),
                            "Pérdidas del Sistema"
                        ], href="/perdidas-sistema", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-cog me-3"),
                            "Pérdidas Técnicas"
                        ], href="/perdidas-tecnicas", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-exclamation me-3"),
                            "Pérdidas Comerciales"
                        ], href="/perdidas-comerciales", active="exact", className="nav-link-sidebar ms-2")
                    ], title="Pérdidas", item_id="perdidas"),
                    
                    # RESTRICCIONES
                    dbc.AccordionItem([
                        dbc.NavLink([
                            html.I(className="fas fa-stop-circle me-3"),
                            "Restricciones Operativas"
                        ], href="/restricciones-operativas", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-leaf me-3"),
                            "Restricciones Ambientales"
                        ], href="/restricciones-ambientales", active="exact", className="nav-link-sidebar ms-2 mb-1"),
                        dbc.NavLink([
                            html.I(className="fas fa-gavel me-3"),
                            "Restricciones Regulatorias"
                        ], href="/restricciones-regulatorias", active="exact", className="nav-link-sidebar ms-2")
                    ], title="Restricciones", item_id="restricciones")
                    
                ], id="accordion-sectores", className="mb-3", flush=True, always_open=False),
                
                # DISTRIBUCIÓN - Enlace directo sin acordeón
                dbc.NavLink([
                    html.I(className="fas fa-project-diagram me-3", style={"color": "#1e3a8a"}),
                    html.Span("Distribución", style={"fontWeight": "600", "color": "#1e3a8a"})
                ], href="/distribucion", active="exact", className="nav-link-sidebar mb-2", 
                   style={"backgroundColor": "rgba(30, 58, 138, 0.05)", "borderRadius": "8px", "padding": "10px 15px"}),
                
                # COMERCIALIZACIÓN - Enlace directo sin acordeón
                dbc.NavLink([
                    html.I(className="fas fa-dollar-sign me-3", style={"color": "#1e3a8a"}),
                    html.Span("Comercialización", style={"fontWeight": "600", "color": "#1e3a8a"})
                ], href="/comercializacion", active="exact", className="nav-link-sidebar mb-4", 
                   style={"backgroundColor": "rgba(30, 58, 138, 0.05)", "borderRadius": "8px", "padding": "10px 15px"}),
                
                html.Hr(style={"borderColor": "rgba(30, 58, 138, 0.2)", "margin": "20px 0"}),
                
                # Enlaces institucionales mejorados
                html.H6([
                    html.I(className="fas fa-external-link-alt me-2", style={"color": "#1e3a8a"}),
                    "Enlaces Externos"
                ], className="mb-3", style={'color': '#1e3a8a', 'fontWeight': '600', 'fontSize': '0.95rem'}),
                
                dbc.Card([
                    dbc.CardBody([
                        html.A([
                            html.Div([
                                html.I(className="fas fa-building me-2", style={"color": "#1e3a8a"}),
                                html.Span("Ministerio de Minas", style={"color": "#1e3a8a", "fontSize": "0.875rem", "fontWeight": "500"})
                            ], className="d-flex align-items-center")
                        ], href="https://www.minenergia.gov.co/", target="_blank", 
                          className="text-decoration-none d-block mb-2 p-2 rounded", 
                          style={"transition": "background-color 0.2s", ":hover": {"backgroundColor": "rgba(30, 58, 138, 0.05)"}}),
                        
                        html.A([
                            html.Div([
                                html.I(className="fas fa-chart-line me-2", style={"color": "#1e3a8a"}),
                                html.Span("XM S.A. E.S.P.", style={"color": "#1e3a8a", "fontSize": "0.875rem", "fontWeight": "500"})
                            ], className="d-flex align-items-center")
                        ], href="https://www.xm.com.co/", target="_blank", 
                          className="text-decoration-none d-block mb-2 p-2 rounded",
                          style={"transition": "background-color 0.2s"}),
                        
                        html.A([
                            html.Div([
                                html.I(className="fas fa-balance-scale me-2", style={"color": "#1e3a8a"}),
                                html.Span("CREG", style={"color": "#1e3a8a", "fontSize": "0.875rem", "fontWeight": "500"})
                            ], className="d-flex align-items-center")
                        ], href="https://www.creg.gov.co/", target="_blank", 
                          className="text-decoration-none d-block p-2 rounded",
                          style={"transition": "background-color 0.2s"})
                    ], className="p-2")
                ], className="border-0 shadow-sm", style={"backgroundColor": "rgba(30, 58, 138, 0.03)"}),
            ], style={
                'padding': '20px',
                'overflowY': 'auto',
                'height': 'calc(100vh - 150px)'
            })
        ], id="sidebar-content", style={
            'position': 'fixed',
            'top': '0',
            'paddingTop': '140px',
            'left': '-300px',
            'width': '300px',
            'height': '100vh',
            'background': COLORS['bg_card'],
            'borderRight': f'1px solid {COLORS["border"]}',
            'boxShadow': '2px 0 10px rgba(0,0,0,0.1)',
            'zIndex': '1045',
            'transition': 'left 0.3s ease-in-out'
        })
    ])


def crear_header(titulo_pagina=None, descripcion_pagina=None, icono_pagina=None, informacion_adicional=None, color_tema=None, breadcrumb_items=None, ruta_completa=None):
    """Crear un header minimalista y elegante específico para cada página con breadcrumb clickeable"""
    
    # Si no se proporcionan datos, crear un header muy sutil o ninguno
    if not titulo_pagina:
        return html.Div()  # Header vacío para páginas que no lo necesiten
    
    # Asegurar que color_tema tenga un valor por defecto
    if not color_tema:
        color_tema = COLORS['primary']
    
    # Construir breadcrumb automático basado en ruta_completa
    breadcrumb_elements = []
    
    # Siempre empezar con home
    breadcrumb_elements.append(dcc.Link("🏠 Inicio", href="/", className="breadcrumb-link"))
    
    if ruta_completa:
        # ruta_completa es una lista de tuplas: [(label, href), (label, href), ...]
        for i, (label, href) in enumerate(ruta_completa):
            breadcrumb_elements.append(html.Span(" / ", style={"color": "#D1D5DB", "padding": "0 0.5rem"}))
            if i == len(ruta_completa) - 1:  # Último elemento (página actual)
                breadcrumb_elements.append(html.Span(label, className="breadcrumb-active"))
            else:
                breadcrumb_elements.append(dcc.Link(label, href=href, className="breadcrumb-link"))
    else:
        # Si no hay ruta_completa, mostrar solo la página actual
        breadcrumb_elements.append(html.Span(" / ", style={"color": "#D1D5DB", "padding": "0 0.5rem"}))
        breadcrumb_elements.append(html.Span(titulo_pagina, className="breadcrumb-active"))
    
    return html.Div([
        # Header compacto y elegante con logo integrado
        html.Div([
            # Estructura flex: Logo izquierda + Contenido centro + Logo derecha
            html.Div([
                # Logo de Colombia en esquina izquierda
                html.Div([
                    html.Img(
                        src="/assets/Minminas_Colombia.svg.png",
                        style={
                            "height": "50px",
                            "width": "auto"
                        }
                    )
                ], style={"flexShrink": "0", "marginRight": "1.5rem"}),
                
                # Contenido central (breadcrumb + título + descripción)
                html.Div([
                    # Breadcrumb clickeable personalizado
                    html.Div([
                        html.Div(breadcrumb_elements, className="breadcrumb-container", style={
                            "marginBottom": "0.5rem",
                            "fontSize": "0.85rem",
                            "display": "flex",
                            "alignItems": "center",
                            "flexWrap": "wrap"
                        })
                    ]),
                    
                    html.H1([
                        html.I(className=f"{icono_pagina} me-2", style={"color": color_tema, "fontSize": "1.5rem"}),
                        titulo_pagina
                    ], style={"color": COLORS['text_primary'], "fontWeight": "600", "fontSize": "1.5rem", "marginBottom": "0.25rem"}),
                    html.P(descripcion_pagina, style={"color": COLORS['text_secondary'], "fontSize": "0.9rem", "marginBottom": "0"})
                ], style={"flex": "1", "minWidth": "0"}),
                
                # Logo del Ministerio en esquina derecha
                html.Div([
                    html.Img(
                        src="/assets/portada_Logo del ministerio.png",
                        style={
                            "width": "100px",
                            "height": "auto"
                        }
                    )
                ], style={"flexShrink": "0", "marginLeft": "1.5rem"})
                
            ], style={"display": "flex", "alignItems": "center", "gap": "1rem"})
        ], style={
            "background": COLORS['bg_header'], 
            "borderRadius": "0", 
            "boxShadow": f"0 1px 3px {COLORS['shadow_sm']}", 
            "padding": "0.75rem 1.5rem",
            "border": f"1px solid {COLORS['border']}",
            "borderBottom": f"2px solid {color_tema}",
            "position": "sticky",
            "top": "0",
            "zIndex": "1000",
            "marginTop": "0"
        })
    ], className="mb-3", style={"position": "relative", "zIndex": "1000"})

def crear_navbar_horizontal():
    """
    Crear navbar horizontal minimalista con logo MME
    Reemplaza el header y sidebar vertical
    """
    return html.Div([
        dcc.Location(id='url-navbar', refresh=False),
        html.Nav([
            html.Div([
                # Logo MME a la izquierda
                html.A([
                    html.Img(
                        src="/assets/images/logo-minenergia.png",
                        style={
                            "height": "45px",
                            "width": "auto",
                            "marginRight": "2rem"
                        }
                    )
                ], href="/", className="navbar-logo"),
                
                # Links de navegación
                html.Div([
                    dcc.Link([
                        html.I(className="fas fa-home", style={"marginRight": "8px"}),
                        "Inicio"
                    ], href="/", className="navbar-link", id="nav-link-inicio"),
                    
                    dcc.Link([
                        html.I(className="fas fa-bolt", style={"marginRight": "8px"}),
                        "Generación"
                    ], href="/generacion", className="navbar-link", id="nav-link-generacion"),
                    
                    dcc.Link([
                        html.I(className="fas fa-tower-broadcast", style={"marginRight": "8px"}),
                        "Transmisión"
                    ], href="/transmision", className="navbar-link", id="nav-link-transmision"),
                    
                    dcc.Link([
                        html.I(className="fas fa-network-wired", style={"marginRight": "8px"}),
                        "Distribución"
                    ], href="/distribucion", className="navbar-link", id="nav-link-distribucion"),
                    
                    dcc.Link([
                        html.I(className="fas fa-handshake", style={"marginRight": "8px"}),
                        "Comercialización"
                    ], href="/comercializacion", className="navbar-link", id="nav-link-comercializacion"),
                    
                    dcc.Link([
                        html.I(className="fas fa-exclamation-triangle", style={"marginRight": "8px"}),
                        "Pérdidas"
                    ], href="/perdidas", className="navbar-link", id="nav-link-perdidas"),
                    
                    dcc.Link([
                        html.I(className="fas fa-ban", style={"marginRight": "8px"}),
                        "Restricciones"
                    ], href="/restricciones", className="navbar-link", id="nav-link-restricciones"),
                    
                    dcc.Link([
                        html.I(className="fas fa-database", style={"marginRight": "8px"}),
                        "Base de Datos"
                    ], href="/metricas", className="navbar-link", id="nav-link-metricas"),
                    
                ], className="navbar-links", id="navbar-links-container")
                
            ], className="navbar-container")
        ], className="navbar-horizontal")
    ], style={"marginBottom": "0"})

def crear_navbar():
    """Barra de navegación eliminada (no se renderiza nada)"""
    return None

def crear_sidebar_metricas(granjas_count, comunidades_count, dist_promedio):
    """Crear sidebar moderno con métricas"""
    return html.Div([
        dbc.Card([
            dbc.CardHeader([
                html.I(className="fas fa-chart-pie me-2", style={"color": COLORS['accent']}),
                html.H5("Métricas del Sistema", className="mb-0 d-inline", style={"color": COLORS['primary']})
            ], style={
                'background': f'linear-gradient(135deg, {COLORS["primary"]} 0%, {COLORS["accent"]} 100%)',
                'color': COLORS['text_light'],
                'borderRadius': '20px 20px 0 0',
                'border': 'none'
            }),
            dbc.CardBody([
                crear_metrica_moderna("Granjas Solares", granjas_count, "fas fa-solar-panel", COLORS['primary']),
                html.Hr(style={'margin': '1.5rem 0', 'border': 'none', 'height': '1px', 'background': f'linear-gradient(90deg, transparent, {COLORS["border"]}, transparent)'}),
                crear_metrica_moderna("Comunidades", f"{comunidades_count:,}", "fas fa-users", COLORS['secondary']),
                html.Hr(style={'margin': '1.5rem 0', 'border': 'none', 'height': '1px', 'background': f'linear-gradient(90deg, transparent, {COLORS["border"]}, transparent)'}),
                crear_metrica_moderna("Dist. Promedio", f"{dist_promedio:.1f} km", "fas fa-route", COLORS['accent']),
                # Estado del sistema
                html.Div([
                    html.H6("Estado del Sistema", className="mb-3 mt-4", style={'color': COLORS['primary'], 'fontWeight': '600'}),
                    html.Div([
                        html.Span([
                            html.I(className="fas fa-circle me-2", style={"color": COLORS['success']}),
                            "Online"
                        ], className="d-block mb-2", style={"color": COLORS['success']}),
                        html.Span([
                            html.I(className="fas fa-clock me-2", style={"color": COLORS['info']}),
                            "Actualizado"
                        ], className="d-block mb-2", style={"color": COLORS['info']}),
                        html.Span([
                            html.I(className="fas fa-shield-check me-2", style={"color": COLORS['warning']}),
                            "Seguro"
                        ], className="d-block", style={"color": COLORS['warning']})
                    ])
                ])
            ], style={'padding': '2rem'})
        ], className="sidebar", style={
            'border': f'2px solid {COLORS["accent"]}',
            'borderRadius': '20px',
            'boxShadow': '0 10px 25px -3px rgba(0, 0, 0, 0.1)',
            'background': 'rgba(255, 255, 255, 0.97)',
            'backdropFilter': 'blur(20px)'
        })
    ])

def crear_sidebar_hidrologia(total_rios, total_regiones, caudal_promedio=None):
    """Crear sidebar específico para el contexto hidrológico"""
    return html.Div([
        dbc.Card([
            dbc.CardHeader([
                html.I(className="fas fa-water me-2"),
                html.H5("Sistema Hidrológico", className="mb-0 d-inline", style={"color": COLORS['primary']})
            ], style={
                'background': f'linear-gradient(135deg, {COLORS["primary"]} 0%, {COLORS["secondary"]} 100%)',
                'color': COLORS['text_light'],
                'borderRadius': '20px 20px 0 0',
                'border': 'none'
            }),
            dbc.CardBody([
                crear_metrica_moderna("Ríos Monitoreados", f"{total_rios:,}", "fas fa-water", COLORS['primary']),
                html.Hr(style={'margin': '1.5rem 0', 'border': 'none', 'height': '1px', 'background': f'linear-gradient(90deg, transparent, {COLORS["border"]}, transparent)'}),
                crear_metrica_moderna("Regiones Hídricas", f"{total_regiones:,}", "fas fa-map-marked-alt", COLORS['secondary']),
                html.Hr(style={'margin': '1.5rem 0', 'border': 'none', 'height': '1px', 'background': f'linear-gradient(90deg, transparent, {COLORS["border"]}, transparent)'}),
                crear_metrica_moderna("Fuente de Datos", "API XM", "fas fa-database", COLORS['accent']),
                
                # Estado del sistema hidrológico
                html.Div([
                    html.H6("Estado del Sistema", className="mb-3 mt-4", style={'color': COLORS['primary'], 'fontWeight': '600'}),
                    html.Div([
                        html.Span([
                            html.I(className="fas fa-satellite-dish me-2", style={"color": COLORS['success']}),
                            "API Conectada"
                        ], className="d-block mb-2", style={"color": COLORS['success']}),
                        html.Span([
                            html.I(className="fas fa-stream me-2", style={"color": COLORS['info']}),
                            "Datos en Tiempo Real"
                        ], className="d-block mb-2", style={"color": COLORS['info']}),
                        html.Span([
                            html.I(className="fas fa-chart-line me-2", style={"color": COLORS['warning']}),
                            "Monitoreo Activo"
                        ], className="d-block", style={"color": COLORS['warning']})
                    ])
                ])
            ], style={'padding': '2rem'})
        ], className="sidebar", style={
            'border': f'2px solid {COLORS["secondary"]}',
            'borderRadius': '20px',
            'boxShadow': '0 10px 25px -3px rgba(0, 0, 0, 0.1)',
            'background': 'rgba(255, 255, 255, 0.97)',
            'backdropFilter': 'blur(20px)'
        })
    ])

def crear_sidebar_metricas_energeticas(total_metricas, total_entidades, fuente_datos="XM"):
    """Crear sidebar específico para el contexto de métricas energéticas"""
    return html.Div([
        dbc.Card([
            dbc.CardHeader([
                html.I(className="fas fa-chart-line me-2"),
                html.H5("Sistema de Métricas", className="mb-0 d-inline", style={"color": COLORS['primary']})
            ], style={
                'background': f'linear-gradient(135deg, {COLORS["primary"]} 0%, {COLORS["accent"]} 100%)',
                'color': COLORS['text_light'],
                'borderRadius': '20px 20px 0 0',
                'border': 'none'
            }),
            dbc.CardBody([
                crear_metrica_moderna("Métricas Disponibles", f"{total_metricas:,}", "fas fa-chart-bar", COLORS['primary']),
                html.Hr(style={'margin': '1.5rem 0', 'border': 'none', 'height': '1px', 'background': f'linear-gradient(90deg, transparent, {COLORS["border"]}, transparent)'}),
                crear_metrica_moderna("Entidades Monitoreadas", f"{total_entidades:,}", "fas fa-building", COLORS['secondary']),
                html.Hr(style={'margin': '1.5rem 0', 'border': 'none', 'height': '1px', 'background': f'linear-gradient(90deg, transparent, {COLORS["border"]}, transparent)'}),
                crear_metrica_moderna("Fuente de Datos", fuente_datos, "fas fa-server", COLORS['accent']),
                
                # Estado del sistema de métricas
                html.Div([
                    html.H6("Estado del Sistema", className="mb-3 mt-4", style={'color': COLORS['primary'], 'fontWeight': '600'}),
                    html.Div([
                        html.Span([
                            html.I(className="fas fa-link me-2", style={"color": COLORS['success']}),
                            "API Activa"
                        ], className="d-block mb-2", style={"color": COLORS['success']}),
                        html.Span([
                            html.I(className="fas fa-sync-alt me-2", style={"color": COLORS['info']}),
                            "Datos Actualizados"
                        ], className="d-block mb-2", style={"color": COLORS['info']}),
                        html.Span([
                            html.I(className="fas fa-shield-alt me-2", style={"color": COLORS['warning']}),
                            "Sistema Estable"
                        ], className="d-block", style={"color": COLORS['warning']})
                    ])
                ])
            ], style={'padding': '2rem'})
        ], className="sidebar", style={
            'border': f'2px solid {COLORS["accent"]}',
            'borderRadius': '20px',
            'boxShadow': '0 10px 25px -3px rgba(0, 0, 0, 0.1)',
            'background': 'rgba(255, 255, 255, 0.97)',
            'backdropFilter': 'blur(20px)'
        })
    ])

def crear_metrica_moderna(titulo, valor, icono, color):
    """Crear una métrica moderna individual"""
    return html.Div([
        html.Div([
            html.I(className=f"{icono} fa-2x mb-3", style={'color': color}),
            html.H3(str(valor), className="metric-value"),
            html.P(titulo, className="metric-label")
        ], className="text-center")
    ], className="metric-card animate-fade-in")

def crear_metrica(titulo, valor, icono):
    """Crear una métrica individual"""
    return html.Div([
        html.P([html.Span(icono), f" {titulo}"], 
               className="mb-1", 
               style={'color': COLORS['text_secondary'], 'fontSize': '0.9rem'}),
        html.H4(str(valor), 
               className="mb-0", 
               style={'color': COLORS['text_primary'], 'fontWeight': 'bold'})
    ])

def crear_mapa_plotly(granjas_df, comunidades_df):
    """Crear mapa moderno con Plotly"""
    fig = go.Figure()
    
    # Granjas con estilo moderno
    if len(granjas_df) > 0:
        fig.add_trace(go.Scattermapbox(
            lat=granjas_df['Latitud'],
            lon=granjas_df['Longitud'],
            mode='markers',
            marker=dict(
                size=16, 
                color=COLORS['primary'], 
                opacity=0.9,
                symbol='circle'
            ),
            text=[f"🏗️ Granja {row['Item']}<br>📍 {row['Municipio']}, {row['Departamento']}<br>⚡ {row['Potencia  KW']} kW<br>👥 {row['Beneficiarios']} beneficiarios" 
                  for _, row in granjas_df.iterrows()],
            name='🏗️ Granjas Solares',
            hovertemplate='%{text}<extra></extra>',
            showlegend=True
        ))
    
    # Comunidades con estilo moderno
    if len(comunidades_df) > 0:
        fig.add_trace(go.Scattermapbox(
            lat=comunidades_df['y'],
            lon=comunidades_df['x'],
            mode='markers',
            marker=dict(
                size=10, 
                color=COLORS['success'], 
                opacity=0.7,
                symbol='circle'
            ),
            text=[f"⚡ CE {row['ID']}<br>📍 {row['Municipio']}<br>🏢 {str(row['Nombre de la comunidad'])[:30]}..." 
                  for _, row in comunidades_df.iterrows()],
            name='⚡ Comunidades Energéticas',
            hovertemplate='%{text}<extra></extra>',
            showlegend=True
        ))
    
    fig.update_layout(
        mapbox=dict(
            style='open-street-map',
            center=dict(lat=MAP_CONFIG['center_lat'], lon=MAP_CONFIG['center_lon']),
            zoom=MAP_CONFIG['zoom']
        ),
        height=600,
        margin=dict(l=0, r=0, t=40, b=0),
        title={
            'text': "🗺️ Ubicación de Granjas y Comunidades Energéticas",
            'x': 0.5,
            'font': {
                'size': 18,
                'family': 'Poppins, sans-serif',
                'color': COLORS['text_primary']
            }
        },
        title_font_color=COLORS['text_primary'],
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_family='Inter, sans-serif',
        legend=dict(
            bgcolor='rgba(255, 255, 255, 0.9)',
            bordercolor=COLORS['border'],
            borderwidth=1,
            font=dict(color=COLORS['text_primary'])
        )
    )
    
    return fig

def crear_grafico_distancias(estadisticas_df):
    """Crear gráfico moderno de barras con distancias"""
    fig = px.bar(
        estadisticas_df.sort_values('Distancia_Media'),
        x='Item', 
        y='Distancia_Media',
        color='Departamento',
        title='📏 Distancia Promedio a las 10 Comunidades Más Cercanas',
        labels={'Item': 'Granja', 'Distancia_Media': 'Distancia Promedio (km)'},
        height=500,
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color=COLORS['text_primary'],
        title_font_color=COLORS['text_primary'],
        title_font_size=18,
        title_font_family='Poppins, sans-serif',
        font_family='Inter, sans-serif',
        showlegend=True,
        legend=dict(
            bgcolor='rgba(255, 255, 255, 0.9)',
            bordercolor=COLORS['border'],
            borderwidth=1
        ),
        xaxis=dict(
            gridcolor='rgba(229, 231, 235, 0.5)',
            zerolinecolor='rgba(229, 231, 235, 0.5)'
        ),
        yaxis=dict(
            gridcolor='rgba(229, 231, 235, 0.5)',
            zerolinecolor='rgba(229, 231, 235, 0.5)'
        )
    )
    
    # Hover personalizado
    fig.update_traces(
        hovertemplate='<b>Granja %{x}</b><br>' +
                      'Distancia: %{y:.2f} km<br>' +
                      '<extra></extra>'
    )
    
    return fig

def crear_tabla_dash(df, table_id):
    """Crear tabla moderna con Dash DataTable"""
    return dash_table.DataTable(
        id=table_id,
        data=df.to_dict('records'),
        columns=[{"name": i, "id": i} for i in df.columns],
        style_table={
            'overflowX': 'auto',
            'borderRadius': '12px',
            'boxShadow': f'0 4px 6px -1px {COLORS["shadow"]}',
            'border': f'2px solid {COLORS["border"]}'
        },
        style_cell={
            'backgroundColor': COLORS['bg_card'],
            'color': COLORS['text_primary'],
            'border': f'1px solid {COLORS["border"]}',
            'textAlign': 'left',
            'padding': '12px 16px',
            'fontFamily': 'Inter, sans-serif',
            'fontSize': '14px'
        },
        style_header={
            'backgroundColor': COLORS['primary'],
            'color': COLORS['text_light'],
            'fontWeight': '600',
            'textTransform': 'uppercase',
            'letterSpacing': '0.5px',
            'fontSize': '12px',
            'border': f'2px solid {COLORS["primary"]}'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': COLORS['bg_main']
            },
            {
                'if': {'state': 'active'},
                'backgroundColor': f'{COLORS["primary"]}20',
                'border': f'1px solid {COLORS["primary"]}',
            }
        ],
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_filter={
            'backgroundColor': COLORS['bg_main'],
            'border': f'1px solid {COLORS["border"]}',
            'borderRadius': '6px'
        }
    )

def crear_cards_top_granjas(estadisticas_df):
    """Crear cards con top granjas"""
    top_5 = estadisticas_df.nsmallest(5, 'Distancia_Media')
    bottom_5 = estadisticas_df.nlargest(5, 'Distancia_Media')
    
    card_top = dbc.Card([
        dbc.CardHeader(html.H5("🏆 Top 5 Mejores Ubicaciones", className="mb-0")),
        dbc.CardBody([
            crear_tabla_dash(top_5[['Item', 'Municipio', 'Distancia_Media']], 'table-top-5')
        ])
    ], style={'backgroundColor': COLORS['bg_card'], 'border': f'1px solid {COLORS["border"]}'})
    
    card_bottom = dbc.Card([
        dbc.CardHeader(html.H5("⚠️ Top 5 Mayores Desafíos", className="mb-0")),
        dbc.CardBody([
            crear_tabla_dash(bottom_5[['Item', 'Municipio', 'Distancia_Media']], 'table-bottom-5')
        ])
    ], style={'backgroundColor': COLORS['bg_card'], 'border': f'1px solid {COLORS["border"]}'})
    
    return card_top, card_bottom

def crear_cards_metricas_principales(granjas_df, estadisticas_df):
    """Crear cards modernos con métricas principales"""
    mejor = estadisticas_df.loc[estadisticas_df['Distancia_Media'].idxmin()]
    peor = estadisticas_df.loc[estadisticas_df['Distancia_Media'].idxmax()]
    
    cards = [
        # Card 1: Granjas Analizadas
        html.Div([
            html.Div([
                html.I(className="fas fa-solar-panel fa-3x mb-3", style={'color': COLORS['primary']}),
                html.H2(len(granjas_df), className="metric-value"),
                html.P("Granjas Analizadas", className="metric-label"),
                html.Small("Instalaciones solares activas", style={'color': COLORS['text_secondary']})
            ], className="text-center p-4")
        ], className="metric-card animate-fade-in"),
        
        # Card 2: Distancia Promedio
        html.Div([
            html.Div([
                html.I(className="fas fa-route fa-3x mb-3", style={'color': COLORS['secondary']}),
                html.H2(f"{estadisticas_df['Distancia_Media'].mean():.1f}", className="metric-value"),
                html.P("Distancia Promedio (km)", className="metric-label"),
                html.Small("A comunidades cercanas", style={'color': COLORS['text_secondary']})
            ], className="text-center p-4")
        ], className="metric-card animate-fade-in"),
        
        # Card 3: Mejor Ubicación
        html.Div([
            html.Div([
                html.I(className="fas fa-trophy fa-3x mb-3", style={'color': COLORS['success']}),
                html.H2(f"#{mejor['Item']}", className="metric-value"),
                html.P("Mejor Ubicación", className="metric-label"),
                html.Small(f"{mejor['Municipio']}", style={'color': COLORS['text_secondary']})
            ], className="text-center p-4")
        ], className="metric-card animate-fade-in"),
        
        # Card 4: Mayor Desafío
        html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-triangle fa-3x mb-3", style={'color': COLORS['warning']}),
                html.H2(f"#{peor['Item']}", className="metric-value"),
                html.P("Mayor Desafío", className="metric-label"),
                html.Small(f"{peor['Municipio']}", style={'color': COLORS['text_secondary']})
            ], className="text-center p-4")
        ], className="metric-card animate-fade-in")
    ]
    
    return cards

# Sidebar ahora usa JavaScript inline para funcionar sin callbacks de Dash

# Función duplicada eliminada - se usa la primera definición con breadcrumb clickeable

def crear_boton_regresar():
    """Función deprecada - ahora se usa breadcrumb clickeable"""
    return html.Div()  # Retorna div vacío para no romper código existente


def crear_navbar():
    """Barra de navegación eliminada (no se renderiza nada)"""
    return None


def crear_filtro_fecha_compacto(
    id_prefix,
    fecha_inicial_default=None,
    fecha_final_default=None,
    show_actualizar_btn=True,
    rangos_personalizados=None
):
    """
    Crear filtro de fecha ultra-compacto con rangos predeterminados.
    
    Args:
        id_prefix: Prefijo para los IDs de los componentes (ej: 'perdidas', 'restricciones')
        fecha_inicial_default: Fecha inicial por defecto
        fecha_final_default: Fecha final por defecto
        show_actualizar_btn: Si mostrar botón Actualizar
        rangos_personalizados: Lista de rangos personalizados (opcional)
    
    Returns:
        html.Div con el filtro compacto
    """
    from datetime import datetime, timedelta
    
    if not fecha_inicial_default:
        fecha_inicial_default = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    if not fecha_final_default:
        fecha_final_default = datetime.now().strftime('%Y-%m-%d')
    
    rangos_default = [
        {'label': 'Último mes', 'value': 'ultimo_mes'},
        {'label': 'Últimos 6 meses', 'value': 'ultimos_6_meses'},
        {'label': 'Último año', 'value': 'ultimo_ano'},
        {'label': 'Últimos 2 años', 'value': 'ultimos_2_anos'},
        {'label': 'Últimos 5 años', 'value': 'ultimos_5_anos'},
        {'label': 'Últimos 10 años', 'value': 'ultimos_10_anos'},
        {'label': 'Personalizado', 'value': 'personalizado'}
    ]
    
    opciones_rangos = rangos_personalizados if rangos_personalizados else rangos_default
    
    componentes = [
        # Dropdown de rangos predeterminados
        html.Div([
            html.Label("RANGO:", style={
                'fontSize': '0.75rem',
                'fontWeight': '600',
                'color': '#666',
                'marginBottom': '4px',
                'textTransform': 'uppercase',
                'letterSpacing': '0.5px'
            }),
            dcc.Dropdown(
                id=f'{id_prefix}-rango-dropdown',
                options=opciones_rangos,
                value='ultimo_ano',
                clearable=False,
                style={
                    'fontSize': '0.85rem',
                    'minWidth': '180px'
                },
                className='compact-dropdown'
            )
        ], style={'marginRight': '20px'}),
        
        # Fecha Inicio (oculto por defecto)
        html.Div([
            html.Label("FECHA INICIO:", style={
                'fontSize': '0.75rem',
                'fontWeight': '600',
                'color': '#666',
                'marginBottom': '4px',
                'textTransform': 'uppercase',
                'letterSpacing': '0.5px'
            }),
            dcc.DatePickerSingle(
                id=f'{id_prefix}-start-date',
                date=fecha_inicial_default,
                display_format='DD/MM/YYYY',
                style={'fontSize': '0.85rem'},
                className='compact-datepicker'
            )
        ], id=f'{id_prefix}-fecha-inicio-container', style={'marginRight': '20px', 'display': 'none'}),
        
        # Fecha Fin (oculto por defecto)
        html.Div([
            html.Label("FECHA FIN:", style={
                'fontSize': '0.75rem',
                'fontWeight': '600',
                'color': '#666',
                'marginBottom': '4px',
                'textTransform': 'uppercase',
                'letterSpacing': '0.5px'
            }),
            dcc.DatePickerSingle(
                id=f'{id_prefix}-end-date',
                date=fecha_final_default,
                display_format='DD/MM/YYYY',
                style={'fontSize': '0.85rem'},
                className='compact-datepicker'
            )
        ], id=f'{id_prefix}-fecha-fin-container', style={'marginRight': '20px', 'display': 'none'})
    ]
    
    # Agregar botón Actualizar si se solicita
    if show_actualizar_btn:
        componentes.append(
            html.Div([
                html.Label("\u00A0", style={'fontSize': '0.75rem', 'marginBottom': '4px', 'display': 'block'}),  # Espaciador
                dbc.Button(
                    "Actualizar",
                    id=f'{id_prefix}-btn-actualizar',
                    color="primary",
                    className="btn-sm",
                    style={
                        'fontSize': '0.85rem',
                        'padding': '6px 20px',
                        'fontWeight': '500'
                    }
                )
            ])
        )
    
    return html.Div(
        componentes,
        style={
            'display': 'flex',
            'alignItems': 'flex-end',
            'gap': '0px',
            'padding': '15px 0',
            'borderBottom': '1px solid #e5e7eb',
            'marginBottom': '20px'
        }
    )


def crear_callback_filtro_fecha(app, id_prefix):
    """
    Crear callbacks automáticos para el filtro de fecha compacto.
    
    Args:
        app: Instancia de la app Dash
        id_prefix: Prefijo usado en crear_filtro_fecha_compacto
    """
    from datetime import datetime, timedelta
    from dash import Input, Output
    
    @app.callback(
        [
            Output(f'{id_prefix}-fecha-inicio-container', 'style'),
            Output(f'{id_prefix}-fecha-fin-container', 'style'),
            Output(f'{id_prefix}-start-date', 'date'),
            Output(f'{id_prefix}-end-date', 'date')
        ],
        [Input(f'{id_prefix}-rango-dropdown', 'value')]
    )
    def actualizar_rango_fecha(rango_seleccionado):
        """Actualizar fechas según el rango seleccionado"""
        fecha_fin = datetime.now()
        
        # Calcular fecha inicio según el rango
        if rango_seleccionado == 'ultimo_mes':
            fecha_inicio = fecha_fin - timedelta(days=30)
        elif rango_seleccionado == 'ultimos_6_meses':
            fecha_inicio = fecha_fin - timedelta(days=180)
        elif rango_seleccionado == 'ultimo_ano':
            fecha_inicio = fecha_fin - timedelta(days=365)
        elif rango_seleccionado == 'ultimos_2_anos':
            fecha_inicio = fecha_fin - timedelta(days=730)
        elif rango_seleccionado == 'ultimos_5_anos':
            fecha_inicio = fecha_fin - timedelta(days=1825)
        elif rango_seleccionado == 'ultimos_10_anos':
            fecha_inicio = fecha_fin - timedelta(days=3650)
        else:  # personalizado
            # Mostrar los date pickers
            return (
                {'marginRight': '20px', 'display': 'block'},  # Mostrar fecha inicio
                {'marginRight': '20px', 'display': 'block'},  # Mostrar fecha fin
                (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'),  # Fecha inicio default
                datetime.now().strftime('%Y-%m-%d')  # Fecha fin default
            )
        
        # Para rangos predeterminados, ocultar date pickers y actualizar fechas
        return (
            {'marginRight': '20px', 'display': 'none'},  # Ocultar fecha inicio
            {'marginRight': '20px', 'display': 'none'},  # Ocultar fecha fin
            fecha_inicio.strftime('%Y-%m-%d'),
            fecha_fin.strftime('%Y-%m-%d')
        )


def crear_filtro_fechas_compacto(page_id):
    """
    Crea un filtro de fechas compacto y uniforme para todas las páginas.
    
    Args:
        page_id: Identificador único de la página (ej: 'perdidas', 'generacion', etc.)
    
    Returns:
        html.Div con el filtro de fechas compacto
    """
    from datetime import datetime, timedelta
    
    fecha_fin_default = datetime.now()
    fecha_inicio_default = fecha_fin_default - timedelta(days=180)
    
    # Rangos específicos para transmisión (por años de construcción)
    if page_id == 'transmision':
        options = [
            {'label': 'Últimos 5 años', 'value': '5y'},
            {'label': 'Últimos 10 años', 'value': '10y'},
            {'label': 'Últimos 20 años', 'value': '20y'},
            {'label': 'Últimos 30 años', 'value': '30y'},
            {'label': 'Todas las líneas', 'value': '100y'},
            {'label': 'Personalizado', 'value': 'custom'}
        ]
        default_value = '100y'
    else:
        # Rangos normales para métricas temporales
        options = [
            {'label': 'Último mes', 'value': '1m'},
            {'label': 'Últimos 6 meses', 'value': '6m'},
            {'label': 'Último año', 'value': '1y'},
            {'label': 'Últimos 2 años', 'value': '2y'},
            {'label': 'Últimos 5 años', 'value': '5y'},
            {'label': 'Personalizado', 'value': 'custom'}
        ]
        default_value = '6m'
    
    return html.Div([
        # Fila con dropdown de rangos y botón actualizar
        html.Div([
            # Dropdown de rangos predeterminados
            html.Div([
                html.Label("RANGO:", style={
                    'fontSize': '0.75rem',
                    'fontWeight': '600',
                    'color': '#666',
                    'marginBottom': '4px',
                    'textTransform': 'uppercase',
                    'letterSpacing': '0.5px'
                }),
                dcc.Dropdown(
                    id=f'rango-fechas-{page_id}',
                    options=options,
                    value=default_value,
                    clearable=False,
                    style={'fontSize': '0.85rem', 'minHeight': '32px'},
                    className='compact-dropdown'
                )
            ], style={'flex': '1', 'minWidth': '180px', 'marginRight': '12px'}),
            
            # Fecha Inicio (oculta por defecto)
            html.Div([
                html.Label("FECHA INICIO:", style={
                    'fontSize': '0.75rem',
                    'fontWeight': '600',
                    'color': '#666',
                    'marginBottom': '4px',
                    'textTransform': 'uppercase',
                    'letterSpacing': '0.5px'
                }),
                dcc.DatePickerSingle(
                    id=f'fecha-inicio-{page_id}',
                    date=fecha_inicio_default.strftime('%Y-%m-%d'),
                    display_format='DD/MM/YYYY',
                    style={'fontSize': '0.85rem'},
                    className='compact-datepicker'
                )
            ], id=f'container-fecha-inicio-{page_id}', style={
                'flex': '1',
                'minWidth': '140px',
                'marginRight': '12px',
                'display': 'none'
            }),
            
            # Fecha Fin (oculta por defecto)
            html.Div([
                html.Label("FECHA FIN:", style={
                    'fontSize': '0.75rem',
                    'fontWeight': '600',
                    'color': '#666',
                    'marginBottom': '4px',
                    'textTransform': 'uppercase',
                    'letterSpacing': '0.5px'
                }),
                dcc.DatePickerSingle(
                    id=f'fecha-fin-{page_id}',
                    date=fecha_fin_default.strftime('%Y-%m-%d'),
                    display_format='DD/MM/YYYY',
                    style={'fontSize': '0.85rem'},
                    className='compact-datepicker'
                )
            ], id=f'container-fecha-fin-{page_id}', style={
                'flex': '1',
                'minWidth': '140px',
                'marginRight': '12px',
                'display': 'none'
            }),
            
            # Botón Actualizar
            html.Div([
                html.Button([
                    html.I(className="fas fa-sync-alt me-2"),
                    "Actualizar"
                ], id=f'btn-actualizar-{page_id}', className='btn btn-primary', style={
                    'fontSize': '0.85rem',
                    'padding': '6px 16px',
                    'height': '32px',
                    'marginTop': '20px',
                    'fontWeight': '600'
                })
            ], style={'flex': '0 0 auto'})
            
        ], style={
            'display': 'flex',
            'alignItems': 'flex-end',
            'gap': '0',
            'padding': '8px 0',
            'marginBottom': '12px'
        })
        
    ], style={
        'background': 'transparent',
        'padding': '0',
        'margin': '0'
    })


# ==================== CALLBACK UNIVERSAL PARA FILTROS DE FECHAS ====================
def registrar_callback_filtro_fechas(page_id):
    """
    Registra el callback para manejar el cambio de rango de fechas.
    Debe llamarse desde cada página después de definir el layout.
    
    Args:
        page_id: Identificador único de la página
    """
    from datetime import datetime, timedelta
    from dash import callback, Output, Input
    
    @callback(
        [Output(f'container-fecha-inicio-{page_id}', 'style'),
         Output(f'container-fecha-fin-{page_id}', 'style'),
         Output(f'fecha-inicio-{page_id}', 'date'),
         Output(f'fecha-fin-{page_id}', 'date')],
        Input(f'rango-fechas-{page_id}', 'value'),
        prevent_initial_call=False
    )
    def actualizar_rango_fechas(rango):
        """Actualizar fechas según el rango seleccionado"""
        fecha_fin = datetime.now()
        
        # Estilos base
        style_oculto = {
            'flex': '1',
            'minWidth': '140px',
            'marginRight': '12px',
            'display': 'none'
        }
        
        style_visible = {
            'flex': '1',
            'minWidth': '140px',
            'marginRight': '12px',
            'display': 'block'
        }
        
        if rango == '1m':
            fecha_inicio = fecha_fin - timedelta(days=30)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        elif rango == '6m':
            fecha_inicio = fecha_fin - timedelta(days=180)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        elif rango == '1y':
            fecha_inicio = fecha_fin - timedelta(days=365)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        elif rango == '2y':
            fecha_inicio = fecha_fin - timedelta(days=730)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        elif rango == '5y':
            fecha_inicio = fecha_fin - timedelta(days=1825)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        elif rango == '10y':
            fecha_inicio = fecha_fin - timedelta(days=3650)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        elif rango == '20y':
            fecha_inicio = fecha_fin - timedelta(days=7300)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        elif rango == '30y':
            fecha_inicio = fecha_fin - timedelta(days=10950)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        elif rango == '100y':
            fecha_inicio = fecha_fin - timedelta(days=36500)
            return (
                style_oculto,
                style_oculto,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
        else:  # 'custom'
            fecha_inicio = fecha_fin - timedelta(days=30)
            return (
                style_visible,
                style_visible,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d')
            )
