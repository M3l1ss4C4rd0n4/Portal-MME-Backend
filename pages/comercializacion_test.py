"""
Prueba mínima de comercialización
"""

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

# Registrar la página
dash.register_page(__name__, path='/comercializacion-test', name='Test Comercialización')

def layout(**kwargs):
    """Layout mínimo de prueba"""
    return html.Div([
        html.H1("PÁGINA DE PRUEBA COMERCIALIZACIÓN"),
        html.P("Si ves este mensaje, el layout funciona correctamente"),
        dbc.Alert("Esta es una prueba", color="success")
    ])
