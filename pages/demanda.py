from dash import dcc, html, Input, Output, State, callback, register_page
import dash_bootstrap_components as dbc

# Imports locales para componentes uniformes
from utils.components import crear_navbar_horizontal, crear_boton_regresar
from utils.config import COLORS

register_page(
    __name__,
    path="/demanda",
    name="Demanda",
    title="Demanda Energética - Ministerio de Minas y Energía",
    order=8
)

# Definir las subsecciones de demanda
DEMANDA_SUBSECTIONS = [
    {"name": "Demanda Histórica", "path": "/demanda-historica", "icon": "fas fa-chart-line", "color": "#FF9800", "description": "Análisis de patrones históricos de demanda"},
    {"name": "Pronósticos", "path": "/demanda-pronosticos", "icon": "fas fa-crystal-ball", "color": "#FF8A65", "description": "Modelos predictivos de demanda futura"},
    {"name": "Patrones de Demanda", "path": "/demanda-patrones", "icon": "fas fa-wave-square", "color": "#FFAB40", "description": "Análisis de comportamientos y patrones"}
]

def create_subsection_card(subsection):
    """Crear tarjeta para cada subsección de demanda"""
    return dbc.Col([
        html.A([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(
                            className=subsection["icon"],
                            style={
                                "fontSize": "5rem",
                                "color": subsection["color"],
                                "marginBottom": "1.5rem"
                            }
                        ),
                        html.H4(subsection["name"], 
                               className="mb-2",
                               style={"color": COLORS['text_primary'], "fontWeight": "600"}),
                        html.P(subsection["description"],
                              className="text-muted small mb-0",
                              style={"fontSize": "0.9rem"})
                    ], className="text-center"),
                ], className="py-4")
            ], 
            className="h-100 shadow-sm subsection-card",
            style={
                "cursor": "pointer",
                "transition": "all 0.3s ease",
                "border": f"2px solid {subsection['color']}30"
            }
            )
        ], href=subsection["path"], style={"textDecoration": "none"})
    ], lg=4, md=6, sm=12, className="mb-4")

layout = html.Div([
    # Navbar horizontal
    crear_navbar_horizontal(),
    
    # Container principal
    dbc.Container([
        # Botón de regreso
        crear_boton_regresar(),        # Título de la sección
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.I(className="fas fa-chart-bar", 
                          style={"fontSize": "4rem", "color": "#FF9800", "marginRight": "1rem"}),
                    html.H1("DEMANDA ENERGÉTICA", 
                           style={"color": COLORS['text_primary'], "fontWeight": "700", "display": "inline-block"})
                ], className="text-center mb-2")
            ])
        ]),
        
        dbc.Row([
            dbc.Col([
                html.P("Análisis integral de la demanda energética nacional en Colombia",
                      className="text-center text-muted mb-5", 
                      style={"fontSize": "1.2rem"})
            ])
        ]),
        
        # Tarjetas de subsecciones
        dbc.Row([
            create_subsection_card(subsection) for subsection in DEMANDA_SUBSECTIONS
        ]),
        
    ], fluid=True, className="py-4")
])