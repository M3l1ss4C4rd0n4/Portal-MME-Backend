from dash import dcc, html, Input, Output, dash_table, ALL, callback, register_page
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import datetime as dt
from datetime import date, timedelta, datetime
import warnings
import sys
import os
import time
import traceback

# Imports locales para componentes uniformes
from .components import crear_header, crear_navbar, crear_sidebar_universal
from .config import COLORS

warnings.filterwarnings("ignore")

register_page(
    __name__,
    path="/restricciones-operativas",
    name="Restricciones Operativas",
    title="Restricciones Operativas - Ministerio de Minas y Energía de Colombia",
    order=50
)

LAST_UPDATE = time.strftime('%Y-%m-%d %H:%M:%S')

def layout():
    """Layout de la página de Restricciones Operativas"""
    return html.Div([
        # Header y navegación
        crear_header(),
        crear_navbar(),
        
        # Contenido principal
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H1("Restricciones Operativas", 
                           className="text-center mb-4",
                           style={"color": COLORS['primary']}),
                    html.P("Análisis de restricciones operativas del sistema eléctrico nacional.",
                          className="text-center text-muted mb-4"),
                    
                    # Placeholder para contenido
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Restricciones del Sistema", className="mb-3"),
                            html.P("Esta sección contendrá el análisis de restricciones operativas.",
                                  className="text-muted"),
                            html.Hr(),
                            html.P(f"Última actualización: {LAST_UPDATE}", 
                                  className="small text-muted"),
                        ])
                    ], className="shadow-sm")
                    
                ], width=12)
            ])
        ], fluid=True, className="py-4"),
        
        # Sidebar universal
        crear_sidebar_universal()
    ])