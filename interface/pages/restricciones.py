
def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

from dash import dcc, html, Input, Output, State, callback, register_page
import logging
logger = logging.getLogger(__name__)
import dash
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta
import warnings
import time

# Imports locales para componentes uniformes
from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import crear_chart_card_custom, crear_page_header, crear_filter_bar
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
    hoy = date.today()
    hace_180_dias = hoy - timedelta(days=180)

    return html.Div([
        crear_page_header(
            titulo="Restricciones Operativas",
            icono="fas fa-exclamation-triangle",
            breadcrumb="Inicio / Restricciones",
            fecha=LAST_UPDATE,
        ),

        crear_filter_bar(
            html.Div([
                html.Label("Periodo", className="t-filter-label"),
                dcc.Dropdown(
                    id='dropdown-rango-restricciones',
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
                    id='fecha-filtro-restricciones',
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
            ], id='btn-actualizar-restricciones', color="primary", size="sm"),
            dbc.Button([
                html.I(className="fas fa-file-excel me-1"), "Excel"
            ], id='btn-excel-restricciones', color="success", size="sm", outline=True),
            dcc.Download(id='download-excel-restricciones'),
        ),

        dcc.Loading(
            id="loading-restricciones",
            type="dot",
            color="#3b82f6",
            children=html.Div(id='restricciones-container'),
        ),
    ], className="t-page")


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
            return f"${valor:,.0f}"

        kpis = crear_kpi_row([
            {"titulo": "Restricciones Totales", "valor": formato_millones_valor(rest_total), "unidad": "M COP", "icono": "fas fa-dollar-sign", "color": "orange"},
            {"titulo": "Restricciones Aliviadas", "valor": formato_millones_valor(rest_aliv_total), "unidad": "M COP", "icono": "fas fa-check-circle", "color": "green"},
            {"titulo": "Restricciones Sin Alivio", "valor": formato_millones_valor(rest_sin_aliv_total), "unidad": "M COP", "icono": "fas fa-exclamation-triangle", "color": "red"},
            {"titulo": "Responsabilidad AGC", "valor": formato_millones_valor(resp_agc_total), "unidad": "M COP", "icono": "fas fa-cogs", "color": "blue"},
        ], columnas=4)
        
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
            xaxis_title="Fecha",
            yaxis_title="Valor (Millones COP)",
            hovermode='x unified',
            template='plotly_white',
            font=dict(family='Inter, sans-serif'),
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=60, r=20, t=30, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(tickformat=",d", tickprefix="$")
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
                xaxis_title="Mes",
                yaxis_title="Valor ($ Millones COP)",
                barmode='stack',
                template='plotly_white',
                font=dict(family='Inter, sans-serif'),
                plot_bgcolor='white',
                paper_bgcolor='white',
                margin=dict(l=60, r=20, t=30, b=40),
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

            html.Div([
                crear_chart_card_custom(
                    "Evolución Temporal de Restricciones",
                    dcc.Graph(figure=fig_serie, config={'displayModeBar': True, 'displaylogo': False}),
                ),
            ], style={'marginBottom': '16px'}),

            html.Div([
                html.Div([
                    crear_chart_card_custom(
                        "Distribución Aliviadas vs Sin Alivio",
                        dcc.Graph(figure=fig_distribucion, config={'displayModeBar': False}),
                    ),
                ], style={'flex': '1'}),
                html.Div([
                    crear_chart_card_custom(
                        "Restricciones por Mes",
                        dcc.Graph(figure=fig_mensual, config={'displayModeBar': True, 'displaylogo': False}),
                    ),
                ], style={'flex': '2'}),
            ], className="t-grid t-grid-2"),
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

# Fase G — Excel export
@callback(
    Output('download-excel-restricciones', 'data'),
    Input('btn-excel-restricciones', 'n_clicks'),
    [State('fecha-filtro-restricciones', 'start_date'),
     State('fecha-filtro-restricciones', 'end_date')],
    prevent_initial_call=True,
)
def exportar_excel_restricciones(n_clicks, fecha_inicio, fecha_fin):
    import io
    try:
        if not fecha_inicio or not fecha_fin:
            return dash.no_update
        fi = pd.to_datetime(fecha_inicio).strftime('%Y-%m-%d')
        ff = pd.to_datetime(fecha_fin).strftime('%Y-%m-%d')
        data = restrictions_service.get_restrictions_analysis(fi, ff)

        def to_df(x):
            if x is None: return pd.DataFrame()
            if isinstance(x, list): return pd.DataFrame(x)
            return x if isinstance(x, pd.DataFrame) else pd.DataFrame()

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            sheets = {
                'Restricciones_Aliviadas': to_df(data.get('RestAliv') if isinstance(data, dict) else None),
                'Restricciones_Sin_Alivio': to_df(data.get('RestSinAliv') if isinstance(data, dict) else None),
                'Respuesta_Comercial_AGC': to_df(data.get('RespComerAGC') if isinstance(data, dict) else None),
            }
            for sheet, df in sheets.items():
                if not df.empty:
                    df.to_excel(writer, sheet_name=sheet, index=False)
        buf.seek(0)
        return dcc.send_bytes(buf.read(), f"restricciones_{fi}_al_{ff}.xlsx")
    except Exception as e:
        logger.error("Error Excel restricciones: %s", e)
        return dash.no_update
