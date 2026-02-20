
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
from interface.components.kpi_card import crear_kpi, crear_kpi_row
from interface.components.chart_card import crear_chart_card_custom, crear_page_header, crear_filter_bar
from core.constants import UIColors as COLORS
from domain.services.losses_service import LossesService

warnings.filterwarnings("ignore")

# Instancia del servicio
losses_service = LossesService()

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
    hoy = date.today()
    hace_180_dias = hoy - timedelta(days=180)

    return html.Div([
        crear_page_header(
            titulo="Pérdidas del Sistema",
            icono="fas fa-plug-circle-exclamation",
            breadcrumb="Inicio / Pérdidas",
            fecha=LAST_UPDATE,
        ),

        crear_filter_bar(
            html.Div([
                html.Label("Periodo", className="t-filter-label"),
                dcc.Dropdown(
                    id='dropdown-rango-perdidas',
                    options=[
                        {'label': 'Últimos 30 días', 'value': '30d'},
                        {'label': 'Último Trimestre', 'value': '90d'},
                        {'label': 'Últimos 6 Meses', 'value': '180d'},
                        {'label': 'Último Año', 'value': '365d'},
                        {'label': 'Últimos 2 Años', 'value': '730d'},
                        {'label': 'Últimos 5 Años', 'value': '1825d'},
                        {'label': 'Personalizado', 'value': 'custom'},
                    ],
                    value='180d',
                    clearable=False,
                    style={'width': '180px', 'fontSize': '0.85rem'},
                ),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px'}),

            html.Div([
                html.Label("Fechas", className="t-filter-label"),
                dcc.DatePickerRange(
                    id='fecha-filtro-perdidas',
                    min_date_allowed=date(2020, 1, 1),
                    max_date_allowed=hoy,
                    initial_visible_month=hoy,
                    start_date=hace_180_dias,
                    end_date=hoy,
                    display_format='YYYY-MM-DD',
                ),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px'}),

            dbc.Button([
                html.I(className="fas fa-search me-1"), "Actualizar"
            ], id='btn-actualizar-perdidas', color="primary", size="sm"),
        ),

        dcc.Loading(
            id="loading-perdidas",
            type="dot",
            color="#3b82f6",
            children=html.Div(id='perdidas-container'),
        ),
    ], className="t-page")


# ==================== CALLBACKS ====================

# Registrar callback del filtro de fechas
# registrar_callback_filtro_fechas('perdidas')

@callback(
    [Output('fecha-filtro-perdidas', 'start_date'),
     Output('fecha-filtro-perdidas', 'end_date')],
    Input('dropdown-rango-perdidas', 'value'),
    prevent_initial_call=True
)
def actualizar_fechas_rango_perdidas(rango):
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
    [Output('perdidas-container', 'children'),
     Output('store-datos-chatbot-generacion', 'data', allow_duplicate=True)],
    [Input('btn-actualizar-perdidas', 'n_clicks'),
     Input('fecha-filtro-perdidas', 'start_date'),
     Input('fecha-filtro-perdidas', 'end_date')],
    prevent_initial_call='initial_duplicate'
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
        
        # Obtener datos usando el servicio de dominio
        data = losses_service.get_losses_analysis(fecha_ini, fecha_fin)
        
        # Extracción segura de datos
        if isinstance(data, dict):
            perdidas_totales = data.get('PerdidasEner')
            perdidas_reg = data.get('PerdidasEnerReg')
            perdidas_no_reg = data.get('PerdidasEnerNoReg')
            generacion = data.get('Gene')
        else:
            perdidas_totales, perdidas_reg, perdidas_no_reg, generacion = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
        # Validación robusta de tipos
        def asegurar_dataframe(df_input):
            if df_input is None: return pd.DataFrame()
            if isinstance(df_input, list): return pd.DataFrame(df_input)
            if isinstance(df_input, pd.DataFrame): return df_input
            return pd.DataFrame()

        perdidas_totales = asegurar_dataframe(perdidas_totales)
        perdidas_reg = asegurar_dataframe(perdidas_reg)
        perdidas_no_reg = asegurar_dataframe(perdidas_no_reg)
        generacion = asegurar_dataframe(generacion)

        # Verificar que haya datos
        if perdidas_totales.empty:
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
        
        # Calcular estadísticas (usando columnas normalizadas 'Value' y 'Date')
        perdidas_total_gwh = perdidas_totales['Value'].sum()
        perdidas_reg_gwh = perdidas_reg['Value'].sum() if perdidas_reg is not None and not perdidas_reg.empty else 0
        perdidas_no_reg_gwh = perdidas_no_reg['Value'].sum() if perdidas_no_reg is not None and not perdidas_no_reg.empty else 0
        generacion_total_gwh = generacion['Value'].sum() if generacion is not None and not generacion.empty else 1
        
        # Calcular % pérdidas
        pct_perdidas = (perdidas_total_gwh / generacion_total_gwh * 100) if generacion_total_gwh > 0 else 0
        pct_reg = (perdidas_reg_gwh / perdidas_total_gwh * 100) if perdidas_total_gwh > 0 else 0
        pct_no_reg = (perdidas_no_reg_gwh / perdidas_total_gwh * 100) if perdidas_total_gwh > 0 else 0
        
        # KPIs
        kpis = crear_kpi_row([
            {"titulo": "Pérdidas Totales", "valor": f"{perdidas_total_gwh:,.1f}", "unidad": "GWh", "icono": "fas fa-exclamation-circle", "color": "red"},
            {"titulo": "Pérdidas Reguladas", "valor": f"{perdidas_reg_gwh:,.1f}", "unidad": "GWh", "icono": "fas fa-home", "color": "blue", "subtexto": f"{pct_reg:.1f}% del total"},
            {"titulo": "Pérdidas No Reguladas", "valor": f"{perdidas_no_reg_gwh:,.1f}", "unidad": "GWh", "icono": "fas fa-industry", "color": "orange", "subtexto": f"{pct_no_reg:.1f}% del total"},
            {"titulo": "% sobre Generación", "valor": f"{pct_perdidas:.1f}", "unidad": "%", "icono": "fas fa-percentage", "color": "purple"},
        ], columnas=4)
        
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
            xaxis_title="Fecha",
            yaxis_title="Pérdidas (GWh)",
            hovermode='x unified',
            template='plotly_white',
            font=dict(family='Inter, sans-serif'),
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=50, r=20, t=30, b=40),
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
            font=dict(family='Inter, sans-serif'),
            plot_bgcolor='white',
            paper_bgcolor='white',
            showlegend=False,
            margin=dict(l=0, r=0, t=10, b=0),
            height=280
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
                xaxis_title="Fecha",
                yaxis_title="% Pérdidas",
                hovermode='x unified',
                template='plotly_white',
                font=dict(family='Inter, sans-serif'),
                plot_bgcolor='white',
                paper_bgcolor='white',
                margin=dict(l=50, r=20, t=30, b=40),
            )
        else:
            fig_porcentaje = go.Figure()
        
        # Layout final
        contenido = html.Div([
            kpis,

            html.Div([
                crear_chart_card_custom(
                    "Evolución Temporal de Pérdidas",
                    dcc.Graph(figure=fig_serie, config={'displayModeBar': True, 'displaylogo': False}),
                ),
            ], style={'marginBottom': '16px'}),

            html.Div([
                html.Div([
                    crear_chart_card_custom(
                        "Distribución Reguladas vs No Reguladas",
                        dcc.Graph(figure=fig_distribucion, config={'displayModeBar': False}),
                    ),
                ], style={'flex': '1'}),
                html.Div([
                    crear_chart_card_custom(
                        "% Pérdidas sobre Generación",
                        dcc.Graph(figure=fig_porcentaje, config={'displayModeBar': True, 'displaylogo': False}),
                    ),
                ], style={'flex': '2'}),
            ], className="t-grid t-grid-2"),
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