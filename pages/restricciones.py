
def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

from dash import dcc, html, Input, Output, callback, register_page
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta, datetime
import warnings
import sys
import os
import time

# Imports locales para componentes uniformes
from utils.components import crear_navbar_horizontal, crear_filtro_fechas_compacto, registrar_callback_filtro_fechas
from utils.config import COLORS
from utils._xm import obtener_datos_inteligente

warnings.filterwarnings("ignore")

register_page(
    __name__,
    path="/restricciones",
    name="Restricciones",
    title="Restricciones - Ministerio de Minas y Energía de Colombia",
    order=50
)

LAST_UPDATE = time.strftime('%Y-%m-%d %H:%M:%S')

def layout():
    """Layout de la página de Restricciones Operativas"""
    # Fechas por defecto
    hoy = date.today()
    hace_180_dias = hoy - timedelta(days=180)
    
    return html.Div([
        # Navbar horizontal
        crear_navbar_horizontal(),
        
        html.Div(style={'maxWidth': '100%', 'padding': '5px'}, children=[
        # Contenido principal
        dbc.Container([
            # Filtros de fecha compactos
            crear_filtro_fechas_compacto('restricciones'),
            
            # Contenedor principal de datos
            html.Div(id='restricciones-container'),
            
            # Última actualización
            dbc.Row([
                dbc.Col([
                    html.P(f"Última actualización: {LAST_UPDATE}", 
                          className="text-center text-muted small mt-3"),
                ], width=12)
            ])
            
        ], fluid=True, className="py-4"),
        ])
    ])


# ==================== CALLBACKS ====================

# Registrar callback del filtro de fechas
registrar_callback_filtro_fechas('restricciones')

@callback(
    [Output('restricciones-container', 'children'),
     Output('store-datos-chatbot-generacion', 'data', allow_duplicate=True)],
    [Input('btn-actualizar-restricciones', 'n_clicks'),
     Input('fecha-inicio-restricciones', 'date'),
     Input('fecha-fin-restricciones', 'date')],
    prevent_initial_call=True
)
def actualizar_restricciones(n_clicks, fecha_inicio, fecha_fin):
    """Actualizar análisis de restricciones operativas"""
    px, go = get_plotly_modules()
    
    try:
        # Validar fechas
        if not fecha_inicio or not fecha_fin:
            datos_error = {'pagina': 'restricciones', 'error': 'Fechas no seleccionadas'}
            return dbc.Alert("Por favor seleccione ambas fechas", color="warning", className="alert-professional warning"), datos_error
        
        # Convertir fechas
        fecha_ini = pd.to_datetime(fecha_inicio).strftime('%Y-%m-%d')
        fecha_fin = pd.to_datetime(fecha_fin).strftime('%Y-%m-%d')
        
        # Obtener datos de restricciones desde SQLite/API
        rest_aliv, _ = obtener_datos_inteligente('RestAliv', 'Sistema', fecha_ini, fecha_fin)
        rest_sin_aliv, _ = obtener_datos_inteligente('RestSinAliv', 'Sistema', fecha_ini, fecha_fin)
        resp_agc, _ = obtener_datos_inteligente('RespComerAGC', 'Sistema', fecha_ini, fecha_fin)
        
        # Verificar que haya datos
        if (rest_aliv is None or rest_aliv.empty) and (rest_sin_aliv is None or rest_sin_aliv.empty):
            datos_vacio = {'pagina': 'restricciones', 'error': 'Sin datos para el período'}
            return dbc.Alert([
                html.H5("ℹ️ Datos no disponibles", className="alert-heading"),
                html.P("No se encontraron datos de restricciones para el período seleccionado."),
                html.Hr(),
                html.P("Esto puede deberse a:", className="mb-0"),
                html.Ul([
                    html.Li("El ETL aún no ha cargado datos históricos de restricciones"),
                    html.Li("El rango de fechas seleccionado no tiene datos disponibles"),
                    html.Li("Las restricciones son poco frecuentes en este período")
                ])
            ], color="info"), datos_vacio
        
        # Calcular estadísticas
        rest_aliv_total = rest_aliv['Value'].sum() if rest_aliv is not None and not rest_aliv.empty else 0
        rest_sin_aliv_total = rest_sin_aliv['Value'].sum() if rest_sin_aliv is not None and not rest_sin_aliv.empty else 0
        resp_agc_total = resp_agc['Value'].sum() if resp_agc is not None and not resp_agc.empty else 0
        
        rest_total = rest_aliv_total + rest_sin_aliv_total
        
        # Calcular promedios diarios
        dias = (pd.to_datetime(fecha_fin) - pd.to_datetime(fecha_ini)).days + 1
        rest_aliv_promedio = rest_aliv_total / dias if dias > 0 else 0
        rest_sin_aliv_promedio = rest_sin_aliv_total / dias if dias > 0 else 0
        
        # KPIs
        kpis = dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-dollar-sign", style={'color': '#ffc107', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Span("Restricciones Totales", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'marginRight': '12px'}),
                            html.Span(f"${rest_total:,.0f}", style={'fontWeight': 'bold', 'fontSize': '1.6rem', 'color': '#ffc107', 'marginRight': '6px'}),
                            html.Span(f"{dias}d", style={'color': '#666', 'fontSize': '0.85rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem'})
                ], className="shadow-sm")
            ], md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-check-circle", style={'color': '#198754', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Span("Restricciones Aliviadas", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'marginRight': '12px'}),
                            html.Span(f"${rest_aliv_total:,.0f}", style={'fontWeight': 'bold', 'fontSize': '1.6rem', 'color': '#198754', 'marginRight': '6px'}),
                            html.Span(f"{(rest_aliv_total/rest_total*100) if rest_total > 0 else 0:.1f}%", style={'color': '#666', 'fontSize': '0.85rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem'})
                ], className="shadow-sm")
            ], md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-exclamation-triangle", style={'color': '#dc3545', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Span("Restricciones Sin Alivio", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'marginRight': '12px'}),
                            html.Span(f"${rest_sin_aliv_total:,.0f}", style={'fontWeight': 'bold', 'fontSize': '1.6rem', 'color': '#dc3545', 'marginRight': '6px'}),
                            html.Span(f"{(rest_sin_aliv_total/rest_total*100) if rest_total > 0 else 0:.1f}%", style={'color': '#666', 'fontSize': '0.85rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem'})
                ], className="shadow-sm")
            ], md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-cogs", style={'color': '#0d6efd', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Span("Responsabilidad AGC", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'marginRight': '12px'}),
                            html.Span(f"${resp_agc_total:,.0f}", style={'fontWeight': 'bold', 'fontSize': '1.6rem', 'color': '#0d6efd', 'marginRight': '6px'}),
                            html.Span("AGC", style={'color': '#666', 'fontSize': '0.85rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem'})
                ], className="shadow-sm")
            ], md=3)
        ], className="mb-4")
        
        # Gráfico 1: Serie temporal de restricciones
        fig_serie = go.Figure()
        
        if rest_aliv is not None and not rest_aliv.empty:
            fig_serie.add_trace(go.Scatter(
                x=rest_aliv['Date'],
                y=rest_aliv['Value'],
                mode='lines+markers',
                name='Restricciones Aliviadas',
                line=dict(color='#28a745', width=2),
                marker=dict(size=4)
            ))
        
        if rest_sin_aliv is not None and not rest_sin_aliv.empty:
            fig_serie.add_trace(go.Scatter(
                x=rest_sin_aliv['Date'],
                y=rest_sin_aliv['Value'],
                mode='lines+markers',
                name='Restricciones Sin Alivio',
                line=dict(color='#dc3545', width=2),
                marker=dict(size=4)
            ))
        
        if resp_agc is not None and not resp_agc.empty:
            fig_serie.add_trace(go.Scatter(
                x=resp_agc['Date'],
                y=resp_agc['Value'],
                mode='lines',
                name='Responsabilidad AGC',
                line=dict(color='#007bff', width=1.5, dash='dot')
            ))
        
        fig_serie.update_layout(
            title="Evolución Temporal de Restricciones Operativas",
            xaxis_title="Fecha",
            yaxis_title="Valor ($ COP)",
            hovermode='x unified',
            template='plotly_white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # Gráfico 2: Distribución Aliviadas vs Sin Alivio
        if rest_aliv_total > 0 or rest_sin_aliv_total > 0:
            fig_distribucion = go.Figure(data=[
                go.Pie(
                    labels=['Restricciones Aliviadas', 'Restricciones Sin Alivio'],
                    values=[rest_aliv_total, rest_sin_aliv_total],
                    marker=dict(colors=['#28a745', '#dc3545']),
                    hole=0.4,
                    textposition='inside',
                    textinfo='label+percent+value'
                )
            ])
            fig_distribucion.update_layout(
                template='plotly_white',
                showlegend=False,
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
        else:
            fig_distribucion = go.Figure()
            fig_distribucion.add_annotation(
                text="Sin datos suficientes para este período",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16, color="gray")
            )
        
        # Gráfico 3: Comparación mensual (si hay suficientes datos)
        if rest_aliv is not None and not rest_aliv.empty and len(rest_aliv) > 30:
            # Agrupar por mes
            rest_aliv_copy = rest_aliv.copy()
            rest_aliv_copy['Mes'] = pd.to_datetime(rest_aliv_copy['Date']).dt.to_period('M').astype(str)
            
            rest_sin_aliv_copy = rest_sin_aliv.copy() if rest_sin_aliv is not None and not rest_sin_aliv.empty else pd.DataFrame()
            if not rest_sin_aliv_copy.empty:
                rest_sin_aliv_copy['Mes'] = pd.to_datetime(rest_sin_aliv_copy['Date']).dt.to_period('M').astype(str)
            
            df_mensual = pd.DataFrame()
            df_mensual['Aliviadas'] = rest_aliv_copy.groupby('Mes')['Value'].sum()
            if not rest_sin_aliv_copy.empty:
                df_mensual['Sin Alivio'] = rest_sin_aliv_copy.groupby('Mes')['Value'].sum()
            else:
                df_mensual['Sin Alivio'] = 0
            
            df_mensual = df_mensual.fillna(0).reset_index()
            
            fig_mensual = go.Figure()
            fig_mensual.add_trace(go.Bar(
                x=df_mensual['Mes'],
                y=df_mensual['Aliviadas'],
                name='Aliviadas',
                marker_color='#28a745'
            ))
            fig_mensual.add_trace(go.Bar(
                x=df_mensual['Mes'],
                y=df_mensual['Sin Alivio'],
                name='Sin Alivio',
                marker_color='#dc3545'
            ))
            
            fig_mensual.update_layout(
                title="Restricciones por Mes",
                xaxis_title="Mes",
                yaxis_title="Valor ($ COP)",
                barmode='stack',
                template='plotly_white'
            )
        else:
            fig_mensual = go.Figure()
            fig_mensual.add_annotation(
                text="Se requieren más de 30 días de datos para análisis mensual",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=14, color="gray")
            )
        
        # Layout final
        contenido = html.Div([
            kpis,
            
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            dcc.Graph(figure=fig_serie)
                        ])
                    ], className="shadow-sm")
                ], md=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            dcc.Graph(figure=fig_distribucion)
                        ])
                    ], className="shadow-sm")
                ], md=2),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            dcc.Graph(figure=fig_mensual)
                        ])
                    ], className="shadow-sm")
                ], md=4)
            ])
        ])
        
        # Preparar datos para chatbot
        datos_chatbot = {
            'pagina': 'restricciones',
            'timestamp': pd.Timestamp.now().isoformat(),
            'restricciones_aliviadas_gwh': float(rest_aliv_total),
            'restricciones_sin_aliviar_gwh': float(rest_sin_aliv_total),
            'respuesta_agc_gwh': float(resp_agc_total)
        }
        
        return contenido, datos_chatbot
        
    except Exception as e:
        datos_error = {'pagina': 'restricciones', 'error': str(e)}
        return dbc.Alert([
            html.H5("Error al cargar datos", className="alert-heading"),
            html.P(f"Detalle: {str(e)}"),
            html.Hr(),
            html.P("Por favor, intente nuevamente o contacte al administrador.", className="mb-0")
        ], color="danger"), datos_error