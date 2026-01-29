
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
    path="/perdidas",
    name="Pérdidas",
    title="Pérdidas - Ministerio de Minas y Energía de Colombia",
    order=15
)

LAST_UPDATE = time.strftime('%Y-%m-%d %H:%M:%S')

def layout():
    """Layout de la página de Pérdidas del Sistema"""
    # Fechas por defecto
    hoy = date.today()
    hace_30_dias = hoy - timedelta(days=180)
    
    return html.Div([
        # Navbar horizontal
        crear_navbar_horizontal(),
        
        html.Div(style={'maxWidth': '100%', 'padding': '5px'}, children=[
        # Contenido principal
        dbc.Container([
            # Filtros de fecha compactos
            crear_filtro_fechas_compacto('perdidas'),
            
            # Contenedor principal de datos
            html.Div(id='perdidas-container'),
            
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
registrar_callback_filtro_fechas('perdidas')

@callback(
    [Output('perdidas-container', 'children'),
     Output('store-datos-chatbot-generacion', 'data', allow_duplicate=True)],
    [Input('btn-actualizar-perdidas', 'n_clicks'),
     Input('fecha-inicio-perdidas', 'date'),
     Input('fecha-fin-perdidas', 'date')],
    prevent_initial_call=True
)
def actualizar_perdidas(n_clicks, fecha_inicio, fecha_fin):
    """Actualizar análisis de pérdidas de energía"""
    px, go = get_plotly_modules()
    
    try:
        # Validar fechas
        if not fecha_inicio or not fecha_fin:
            datos_error = {'pagina': 'perdidas', 'error': 'Fechas no seleccionadas'}
            return dbc.Alert("Por favor seleccione ambas fechas", color="warning", className="alert-professional warning"), datos_error
        
        # Convertir fechas
        fecha_ini = pd.to_datetime(fecha_inicio).strftime('%Y-%m-%d')
        fecha_fin = pd.to_datetime(fecha_fin).strftime('%Y-%m-%d')
        
        # Obtener datos de pérdidas desde SQLite/API
        perdidas_totales, _ = obtener_datos_inteligente('PerdidasEner', 'Sistema', fecha_ini, fecha_fin)
        perdidas_reg, _ = obtener_datos_inteligente('PerdidasEnerReg', 'Sistema', fecha_ini, fecha_fin)
        perdidas_no_reg, _ = obtener_datos_inteligente('PerdidasEnerNoReg', 'Sistema', fecha_ini, fecha_fin)
        generacion, _ = obtener_datos_inteligente('Gene', 'Sistema', fecha_ini, fecha_fin)
        
        # Verificar que haya datos
        if perdidas_totales is None or perdidas_totales.empty:
            datos_vacio = {'pagina': 'perdidas', 'error': 'Sin datos para el período'}
            return dbc.Alert([
                html.H5("ℹ️ Datos no disponibles", className="alert-heading"),
                html.P("No se encontraron datos de pérdidas para el período seleccionado."),
                html.Hr(),
                html.P("Esto puede deberse a:", className="mb-0"),
                html.Ul([
                    html.Li("El ETL aún no ha cargado datos históricos de pérdidas"),
                    html.Li("El rango de fechas seleccionado no tiene datos disponibles"),
                    html.Li("Error de conectividad con la base de datos")
                ])
            ], color="info"), datos_vacio
        
        # Calcular estadísticas
        perdidas_total_gwh = perdidas_totales['Value'].sum()
        perdidas_reg_gwh = perdidas_reg['Value'].sum() if perdidas_reg is not None and not perdidas_reg.empty else 0
        perdidas_no_reg_gwh = perdidas_no_reg['Value'].sum() if perdidas_no_reg is not None and not perdidas_no_reg.empty else 0
        generacion_total_gwh = generacion['Value'].sum() if generacion is not None and not generacion.empty else 1
        
        # Calcular % pérdidas
        pct_perdidas = (perdidas_total_gwh / generacion_total_gwh * 100) if generacion_total_gwh > 0 else 0
        pct_reg = (perdidas_reg_gwh / perdidas_total_gwh * 100) if perdidas_total_gwh > 0 else 0
        pct_no_reg = (perdidas_no_reg_gwh / perdidas_total_gwh * 100) if perdidas_total_gwh > 0 else 0
        
        # KPIs
        kpis = dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-exclamation-circle", style={'color': '#dc3545', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Span("Pérdidas Totales", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'marginRight': '12px'}),
                            html.Span(f"{perdidas_total_gwh:,.1f}", style={'fontWeight': 'bold', 'fontSize': '1.6rem', 'color': '#dc3545', 'marginRight': '6px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.85rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem'})
                ], className="shadow-sm")
            ], md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-home", style={'color': '#0d6efd', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Span("Pérdidas Reguladas", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'marginRight': '12px'}),
                            html.Span(f"{perdidas_reg_gwh:,.1f}", style={'fontWeight': 'bold', 'fontSize': '1.6rem', 'color': '#0d6efd', 'marginRight': '6px'}),
                            html.Span(f"GWh ({pct_reg:.1f}%)", style={'color': '#666', 'fontSize': '0.85rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem'})
                ], className="shadow-sm")
            ], md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-industry", style={'color': '#ffc107', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Span("Pérdidas No Reguladas", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'marginRight': '12px'}),
                            html.Span(f"{perdidas_no_reg_gwh:,.1f}", style={'fontWeight': 'bold', 'fontSize': '1.6rem', 'color': '#ffc107', 'marginRight': '6px'}),
                            html.Span(f"GWh ({pct_no_reg:.1f}%)", style={'color': '#666', 'fontSize': '0.85rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem'})
                ], className="shadow-sm")
            ], md=3)
        ], className="mb-4")
        
        # Gráfico 1: Serie temporal de pérdidas
        fig_serie = go.Figure()
        fig_serie.add_trace(go.Scatter(
            x=perdidas_totales['Date'],
            y=perdidas_totales['Value'],
            mode='lines+markers',
            name='Pérdidas Totales',
            line=dict(color='#e74c3c', width=2),
            marker=dict(size=4)
        ))
        if perdidas_reg is not None and not perdidas_reg.empty:
            fig_serie.add_trace(go.Scatter(
                x=perdidas_reg['Date'],
                y=perdidas_reg['Value'],
                mode='lines',
                name='Pérdidas Reguladas',
                line=dict(color='#3498db', width=1.5, dash='dot')
            ))
        if perdidas_no_reg is not None and not perdidas_no_reg.empty:
            fig_serie.add_trace(go.Scatter(
                x=perdidas_no_reg['Date'],
                y=perdidas_no_reg['Value'],
                mode='lines',
                name='Pérdidas No Reguladas',
                line=dict(color='#f39c12', width=1.5, dash='dot')
            ))
        
        fig_serie.update_layout(
            title="Evolución Temporal de Pérdidas de Energía",
            xaxis_title="Fecha",
            yaxis_title="Pérdidas (GWh)",
            hovermode='x unified',
            template='plotly_white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # Gráfico 2: Distribución Reguladas vs No Reguladas
        fig_distribucion = go.Figure(data=[
            go.Pie(
                labels=['Pérdidas Reguladas', 'Pérdidas No Reguladas'],
                values=[perdidas_reg_gwh, perdidas_no_reg_gwh],
                marker=dict(colors=['#3498db', '#f39c12']),
                hole=0.4,
                textposition='inside',
                textinfo='label+percent'
            )
        ])
        fig_distribucion.update_layout(
            template='plotly_white',
            showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            height=300
        )
        
        # Gráfico 3: % Pérdidas sobre generación
        if generacion is not None and not generacion.empty:
            # Calcular % diario
            df_pct = pd.merge(
                perdidas_totales[['Date', 'Value']].rename(columns={'Value': 'Perdidas'}),
                generacion[['Date', 'Value']].rename(columns={'Value': 'Generacion'}),
                on='Date'
            )
            df_pct['Porcentaje'] = (df_pct['Perdidas'] / df_pct['Generacion']) * 100
            
            fig_porcentaje = go.Figure()
            fig_porcentaje.add_trace(go.Scatter(
                x=df_pct['Date'],
                y=df_pct['Porcentaje'],
                mode='lines+markers',
                name='% Pérdidas',
                line=dict(color='#9b59b6', width=2),
                marker=dict(size=4),
                fill='tozeroy',
                fillcolor='rgba(155, 89, 182, 0.1)'
            ))
            fig_porcentaje.update_layout(
                title="Porcentaje de Pérdidas sobre Generación",
                xaxis_title="Fecha",
                yaxis_title="% Pérdidas",
                hovermode='x unified',
                template='plotly_white'
            )
        else:
            fig_porcentaje = go.Figure()
        
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
                            dcc.Graph(figure=fig_porcentaje)
                        ])
                    ], className="shadow-sm")
                ], md=4)
            ])
        ])
        
        # Preparar datos para chatbot
        datos_chatbot = {
            'pagina': 'perdidas',
            'timestamp': pd.Timestamp.now().isoformat(),
            'perdidas_totales_gwh': float(perdidas_total_gwh),
            'perdidas_reguladas_gwh': float(perdidas_reg_gwh),
            'perdidas_no_reguladas_gwh': float(perdidas_no_reg_gwh),
            'porcentaje_perdidas': float(pct_perdidas)
        }
        
        return contenido, datos_chatbot
        
    except Exception as e:
        datos_error = {'pagina': 'perdidas', 'error': str(e)}
        return dbc.Alert([
            html.H5("Error al cargar datos", className="alert-heading"),
            html.P(f"Detalle: {str(e)}"),
            html.Hr(),
            html.P("Por favor, intente nuevamente o contacte al administrador.", className="mb-0")
        ], color="danger"), datos_error