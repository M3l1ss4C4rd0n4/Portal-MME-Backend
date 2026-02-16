
def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

from dash import dcc, html, Input, Output, callback, register_page
import dash
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta, datetime
import warnings
import sys
import os
import time

# Imports locales para componentes uniformes
from interface.components.layout import crear_navbar_horizontal, crear_filtro_fechas_compacto, registrar_callback_filtro_fechas
from core.constants import UIColors as COLORS
from domain.services.restrictions_service import RestrictionsService

warnings.filterwarnings("ignore")

# Instancia del servicio
restrictions_service = RestrictionsService()

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
    
    # KPIs place holder
    kpis_header = dbc.Row(id='restricciones-kpis', className="mb-4")

    # Filtro Manual similar a Transmision
    filtro_card = dbc.Card([
        dbc.CardBody([
            dbc.Row([
                # Columna 1: Rango Predefinido
                dbc.Col([
                    html.Label("PERIODO DE ANÁLISIS:", className="fw-bold small text-muted mb-1"),
                    dcc.Dropdown(
                        id='dropdown-rango-restricciones',
                        options=[
                            {'label': 'Últimos 30 días', 'value': '30d'},
                            {'label': 'Último Trimestre', 'value': '90d'},
                            {'label': 'Últimos 6 Meses', 'value': '180d'},
                            {'label': 'Último Año', 'value': '365d'},
                            {'label': 'Últimos 2 Años', 'value': '730d'},
                            {'label': 'Últimos 5 Años', 'value': '1825d'},
                            {'label': 'Personalizado', 'value': 'custom'}
                        ],
                        value='180d',
                        clearable=False,
                        className="mb-0",
                        style={'fontSize': '0.85rem'}
                    )
                ], lg=3, md=6, className="mb-2"),

                # Columna 2: DatePicker
                dbc.Col([
                    html.Label("RANGO DE FECHAS:", className="fw-bold small text-muted mb-1"),
                    dcc.DatePickerRange(
                        id='fecha-filtro-restricciones',
                        min_date_allowed=date(2020, 1, 1),
                        max_date_allowed=hoy,
                        initial_visible_month=hoy,
                        start_date=hace_180_dias,
                        end_date=hoy,
                        display_format='YYYY-MM-DD',
                        className="w-100"
                    )
                ], lg=5, md=6, className="mb-2"),

                # Columna 3: Botón
                dbc.Col([
                    html.Label("ACCIÓN:", className="fw-bold small text-muted mb-1"),
                    dbc.Button([
                        html.I(className="fas fa-search me-2"),
                        "Actualizar"
                    ], id='btn-actualizar-restricciones', color="primary", className="w-100")
                ], lg=3, md=12, className="d-flex align-items-end mb-2")
            ])
        ])
    ], className="mb-4 shadow-sm border-0")

    return html.Div([
        # Navbar horizontal
        # crear_navbar_horizontal(),
        
        html.Div(style={'maxWidth': '100%', 'padding': '5px'}, children=[
        # Contenido principal
        dbc.Container([
            # Filtro manual
            filtro_card,
            
            # Contenedor principal de datos
            dcc.Loading(
                id="loading-restricciones",
                type="circle",
                children=html.Div(id='restricciones-container')
            ),
            
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
# registrar_callback_filtro_fechas('restricciones') # No longer needed with manual layout

@callback(
    [Output('fecha-filtro-restricciones', 'start_date'),
     Output('fecha-filtro-restricciones', 'end_date')],
    Input('dropdown-rango-restricciones', 'value'),
    prevent_initial_call=True
)
def actualizar_fechas_rango_restricciones(rango):
    """Actualiza las fechas del datepicker según el rango seleccionado"""
    hoy = date.today()
    if rango == '30d': return hoy - timedelta(days=30), hoy
    if rango == '90d': return hoy - timedelta(days=90), hoy
    if rango == '180d': return hoy - timedelta(days=180), hoy
    if rango == '365d': return hoy - timedelta(days=365), hoy
    if rango == '730d': return hoy - timedelta(days=730), hoy
    if rango == '1825d': return hoy - timedelta(days=1825), hoy
    return dash.no_update, dash.no_update

@callback(
    [Output('restricciones-container', 'children'),
     Output('store-datos-chatbot-generacion', 'data', allow_duplicate=True)],
    [Input('btn-actualizar-restricciones', 'n_clicks'),
     Input('fecha-filtro-restricciones', 'start_date'),
     Input('fecha-filtro-restricciones', 'end_date')],
    prevent_initial_call='initial_duplicate'
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
        
        # Obtener datos usando el servicio de dominio
        data = restrictions_service.get_restrictions_analysis(fecha_ini, fecha_fin)
        
        # Extracción segura de datos
        if isinstance(data, dict):
            rest_aliv = data.get('RestAliv')
            rest_sin_aliv = data.get('RestSinAliv')
            resp_agc = data.get('RespComerAGC')
        else:
            # Fallback si data no es un diccionario
            rest_aliv, rest_sin_aliv, resp_agc = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # Validación robusta de tipos (Fix: 'list' object has no attribute 'empty')
        def asegurar_dataframe(df_input):
            if df_input is None:
                return pd.DataFrame()
            if isinstance(df_input, list):
                return pd.DataFrame(df_input)
            if isinstance(df_input, pd.DataFrame):
                return df_input
            return pd.DataFrame()

        rest_aliv = asegurar_dataframe(rest_aliv)
        rest_sin_aliv = asegurar_dataframe(rest_sin_aliv)
        resp_agc = asegurar_dataframe(resp_agc)
        
        # Verificar que haya datos
        if rest_aliv.empty and rest_sin_aliv.empty:
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
        
        # Calcular estadísticas (usando columnas normalizadas 'Value' y 'Date')
        rest_aliv_total = rest_aliv['Value'].sum() if rest_aliv is not None and not rest_aliv.empty else 0
        rest_sin_aliv_total = rest_sin_aliv['Value'].sum() if rest_sin_aliv is not None and not rest_sin_aliv.empty else 0
        resp_agc_total = resp_agc['Value'].sum() if resp_agc is not None and not resp_agc.empty else 0
        
        rest_total = rest_aliv_total + rest_sin_aliv_total
        
        # Calcular promedios diarios
        dias = (pd.to_datetime(fecha_fin) - pd.to_datetime(fecha_ini)).days + 1
        
        # KPIs (Value YA está en Millones COP, NO dividir)
        def formato_millones_valor(valor):
            return f"${valor:,.0f}"  # ✅ YA está en Millones COP

        estilo_cifra_kpi = {'fontWeight': 'bold', 'fontSize': '1.4rem', 'marginRight': '6px'}
        estilo_unidad_kpi = {'color': '#666', 'fontSize': '0.75rem', 'fontWeight': '500'}

        kpis = dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-dollar-sign", style={'color': '#ffc107', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Div([
                                html.Span("Restricciones Totales", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'display': 'block'}),
                                html.Div([
                                    html.Span(formato_millones_valor(rest_total), style={**estilo_cifra_kpi, 'color': '#ffc107'}),
                                    html.Span("Millones COP", style=estilo_unidad_kpi)
                                ], style={'display': 'flex', 'alignItems': 'baseline'})
                            ])
                        ], style={'display': 'flex', 'alignItems': 'center'})
                    ], style={'padding': '0.5rem 1rem'})
                ], className="shadow-sm")
            ], md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-check-circle", style={'color': '#198754', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Div([
                                html.Span("Restriccies Aliviadas", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'display': 'block'}),
                                html.Div([
                                    html.Span(formato_millones_valor(rest_aliv_total), style={**estilo_cifra_kpi, 'color': '#198754'}),
                                    html.Span("Millones COP", style=estilo_unidad_kpi)
                                ], style={'display': 'flex', 'alignItems': 'baseline'})
                            ])
                        ], style={'display': 'flex', 'alignItems': 'center'})
                    ], style={'padding': '0.5rem 1rem'})
                ], className="shadow-sm")
            ], md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-exclamation-triangle", style={'color': '#dc3545', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Div([
                                html.Span("Restricciones Sin Alivio", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'display': 'block'}),
                                html.Div([
                                    html.Span(formato_millones_valor(rest_sin_aliv_total), style={**estilo_cifra_kpi, 'color': '#dc3545'}),
                                    html.Span("Millones COP", style=estilo_unidad_kpi)
                                ], style={'display': 'flex', 'alignItems': 'baseline'})
                            ])
                        ], style={'display': 'flex', 'alignItems': 'center'})
                    ], style={'padding': '0.5rem 1rem'})
                ], className="shadow-sm")
            ], md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-cogs", style={'color': '#0d6efd', 'fontSize': '1.2rem', 'marginRight': '10px'}),
                            html.Div([
                                html.Span("Responsabilidad AGC", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.85rem', 'display': 'block'}),
                                html.Div([
                                    html.Span(formato_millones_valor(resp_agc_total), style={**estilo_cifra_kpi, 'color': '#0d6efd'}),
                                    html.Span("Millones COP", style=estilo_unidad_kpi)
                                ], style={'display': 'flex', 'alignItems': 'baseline'})
                            ])
                        ], style={'display': 'flex', 'alignItems': 'center'})
                    ], style={'padding': '0.5rem 1rem'})
                ], className="shadow-sm")
            ], md=3)
        ], className="mb-4")
        
        # Gráfico 1: Serie temporal de restricciones (Re-escalado a Millones)
        fig_serie = go.Figure()
        
        if rest_aliv is not None and not rest_aliv.empty:
            fig_serie.add_trace(go.Scatter(
                x=rest_aliv['Date'],
                y=rest_aliv['Value'],  # ✅ YA está en Millones COP
                mode='lines+markers',
                name='Restricciones Aliviadas',
                line=dict(color='#28a745', width=2),
                marker=dict(size=4),
                hovertemplate='$%{y:,.0f} Millones<br>%{x}'
            ))
        
        if rest_sin_aliv is not None and not rest_sin_aliv.empty:
            fig_serie.add_trace(go.Scatter(
                x=rest_sin_aliv['Date'],
                y=rest_sin_aliv['Value'],  # ✅ YA está en Millones COP
                mode='lines+markers',
                name='Restricciones Sin Alivio',
                line=dict(color='#dc3545', width=2),
                marker=dict(size=4),
                hovertemplate='$%{y:,.0f} Millones<br>%{x}'
            ))
        
        if resp_agc is not None and not resp_agc.empty:
            fig_serie.add_trace(go.Scatter(
                x=resp_agc['Date'],
                y=resp_agc['Value'],  # ✅ YA está en Millones COP
                mode='lines',
                name='Responsabilidad AGC',
                line=dict(color='#007bff', width=1.5, dash='dot'),
                hovertemplate='$%{y:,.0f} Millones<br>%{x}'
            ))
        
        fig_serie.update_layout(
            title="Evolución Temporal de Restricciones Operativas",
            xaxis_title="Fecha",
            yaxis_title="Valor (Millones COP)", # Eje simplificado
            hovermode='x unified',
            template='plotly_white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(tickformat=",d", tickprefix="$") # Formato numérico simple
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
                    textinfo='percent',
                    hovertemplate='%{label}<br>$%{value:,.0f} COP<br>%{percent}'
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
                y=df_mensual['Aliviadas'],  # ✅ FIX: Ya está en Millones COP desde ETL, no dividir
                name='Aliviadas',
                marker_color='#28a745',
                hovertemplate='$%{y:,.0f} Millones<br>%{x}'
            ))
            fig_mensual.add_trace(go.Bar(
                x=df_mensual['Mes'],
                y=df_mensual['Sin Alivio'],  # ✅ FIX: Ya está en Millones COP desde ETL, no dividir
                name='Sin Alivio',
                marker_color='#dc3545',
                hovertemplate='$%{y:,.0f} Millones<br>%{x}'
            ))
            
            fig_mensual.update_layout(
                title="Restricciones por Mes",
                xaxis_title="Mes",
                yaxis_title="Valor ($ Millones COP)",
                barmode='stack',
                template='plotly_white',
                yaxis=dict(tickformat=",d", tickprefix="$")
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