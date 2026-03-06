
def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

from dash import dcc, html, Input, Output, callback, register_page
import dash
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta
import warnings
import time
import logging

# Imports locales para componentes uniformes
from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import crear_chart_card_custom, crear_page_header, crear_filter_bar
from domain.services.losses_service import LossesService

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

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


# ================================================================
# Helper: Semáforo PNT
# ================================================================
def _semaforo_pnt(pnt_pct: float) -> tuple:
    """Retorna (emoji, color, label) según nivel PNT."""
    if pnt_pct is None:
        return ("⚪", "secondary", "Sin datos")
    val = abs(pnt_pct)
    if pnt_pct < 0:
        return ("🔵", "info", "Negativo (anomalía datos)")
    if val < 5:
        return ("🟢", "success", "Bajo")
    if val < 10:
        return ("🟡", "warning", "Moderado")
    return ("🔴", "danger", "Alto")


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

        # ── Tabs: Técnicas (existente) + No Técnicas (FASE 3) ──
        dcc.Tabs(
            id='perdidas-tabs',
            value='tab-tecnicas',
            children=[
                dcc.Tab(
                    label='Pérdidas Técnicas',
                    value='tab-tecnicas',
                    className='custom-tab',
                    selected_className='custom-tab--selected',
                ),
                dcc.Tab(
                    label='Pérdidas No Técnicas (PNT)',
                    value='tab-nt',
                    className='custom-tab',
                    selected_className='custom-tab--selected',
                ),
            ],
            style={'marginBottom': '16px'},
        ),

        dcc.Loading(
            id="loading-perdidas",
            type="dot",
            color="#3b82f6",
            children=html.Div(id='perdidas-container'),
        ),

        # Container para PNT (Tab 2)
        dcc.Loading(
            id="loading-perdidas-nt",
            type="dot",
            color="#e74c3c",
            children=html.Div(id='perdidas-nt-container'),
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
     Input('fecha-filtro-perdidas', 'end_date'),
     Input('perdidas-tabs', 'value')],
    prevent_initial_call='initial_duplicate'
)
def actualizar_perdidas(n_clicks, fecha_inicio, fecha_fin, tab_activo):
    """Actualizar análisis de pérdidas de energía (Tab 1: Técnicas)"""
    # Si estamos en la pestaña NT, ocultar este contenedor
    if tab_activo == 'tab-nt':
        return html.Div(), dash.no_update

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


# ================================================================
# FASE 3: Callback Tab 2 — Pérdidas No Técnicas
# ================================================================

@callback(
    Output('perdidas-nt-container', 'children'),
    [Input('perdidas-tabs', 'value'),
     Input('btn-actualizar-perdidas', 'n_clicks'),
     Input('fecha-filtro-perdidas', 'start_date'),
     Input('fecha-filtro-perdidas', 'end_date')],
    prevent_initial_call=True
)
def actualizar_perdidas_nt(tab_activo, n_clicks, fecha_inicio, fecha_fin):
    """Renderiza Tab 2: Pérdidas No Técnicas (PNT) del SIN."""
    if tab_activo != 'tab-nt':
        return html.Div()

    px, go = get_plotly_modules()

    try:
        if not fecha_inicio or not fecha_fin:
            return dbc.Alert("Seleccione ambas fechas", color="warning")

        fecha_ini = pd.to_datetime(fecha_inicio).strftime('%Y-%m-%d')
        fecha_f = pd.to_datetime(fecha_fin).strftime('%Y-%m-%d')

        # ── Datos históricos ─────────────────────────────────
        df = losses_service.get_losses_detailed(fecha_ini, fecha_f)
        stats = losses_service.get_losses_nt_summary()

        if df.empty and "error" in stats:
            return dbc.Alert([
                html.H5("ℹ️ Sin datos de Pérdidas No Técnicas", className="alert-heading"),
                html.P("La tabla losses_detailed no tiene registros para el período seleccionado."),
                html.P("Ejecute el backfill o espere a que el cron diario complete la carga."),
            ], color="info")

        # ── KPIs ─────────────────────────────────────────────
        pnt_30d = stats.get('pct_promedio_nt_30d', 0) or 0
        pnt_12m = stats.get('pct_promedio_nt_12m', 0) or 0
        tendencia = stats.get('tendencia_nt', 'ESTABLE')
        dias_anom = stats.get('anomalias_30d', 0) or 0
        costo_12m = stats.get('costo_nt_12m_mcop', 0) or 0
        total_dias = stats.get('total_dias', 0) or 0

        # Semáforo
        emoji, sem_color, sem_label = _semaforo_pnt(pnt_30d)

        # Variación de tendencia
        tend_icon = "fas fa-arrow-down" if tendencia == "MEJORANDO" else (
            "fas fa-arrow-up" if tendencia == "EMPEORANDO" else "fas fa-minus"
        )
        tend_color = "green" if tendencia == "MEJORANDO" else (
            "red" if tendencia == "EMPEORANDO" else "blue"
        )

        kpis = crear_kpi_row([
            {
                "titulo": f"{emoji} PNT Promedio 30d",
                "valor": f"{pnt_30d:.2f}",
                "unidad": "%",
                "icono": "fas fa-chart-line",
                "color": "red" if pnt_30d < 0 else ("orange" if pnt_30d > 5 else "green"),
                "subtexto": f"Semáforo: {sem_label}",
            },
            {
                "titulo": "Tendencia PNT",
                "valor": tendencia,
                "unidad": "",
                "icono": tend_icon,
                "color": tend_color,
                "subtexto": f"PNT 12m: {pnt_12m:.2f}%",
            },
            {
                "titulo": "Costo PNT (12m)",
                "valor": f"{costo_12m:,.0f}",
                "unidad": "MCOP",
                "icono": "fas fa-money-bill-wave",
                "color": "purple",
                "subtexto": f"Total hist: {stats.get('costo_nt_historico_mcop', 0) or 0:,.0f} MCOP",
            },
            {
                "titulo": "Anomalías (30d)",
                "valor": str(dias_anom),
                "unidad": "días",
                "icono": "fas fa-exclamation-triangle",
                "color": "orange" if dias_anom > 0 else "green",
                "subtexto": f"Total serie: {stats.get('dias_anomalia', 0) or 0} / {total_dias}",
            },
        ], columnas=4)

        # ── Gráfico 1: Stacked area (Técnicas vs NT) ────────
        fig_stacked = go.Figure()
        if not df.empty and 'fecha' in df.columns:
            fig_stacked.add_trace(go.Scatter(
                x=df['fecha'],
                y=df.get('perdidas_tecnicas_pct', pd.Series(dtype=float)),
                mode='lines',
                name='Pérdidas Técnicas (%)',
                line=dict(color='#3498db', width=2),
                fill='tozeroy',
                fillcolor='rgba(52, 152, 219, 0.3)',
                stackgroup='one',
            ))
            fig_stacked.add_trace(go.Scatter(
                x=df['fecha'],
                y=df.get('perdidas_nt_pct', pd.Series(dtype=float)).clip(lower=0),
                mode='lines',
                name='Pérdidas No Técnicas (%)',
                line=dict(color='#e74c3c', width=2),
                fill='tonexty',
                fillcolor='rgba(231, 76, 60, 0.3)',
                stackgroup='one',
            ))
            # Línea total
            fig_stacked.add_trace(go.Scatter(
                x=df['fecha'],
                y=df.get('perdidas_total_pct', pd.Series(dtype=float)),
                mode='lines',
                name='Pérdidas Totales (%)',
                line=dict(color='#2c3e50', width=1.5, dash='dot'),
            ))

        fig_stacked.update_layout(
            xaxis_title="Fecha",
            yaxis_title="Pérdidas (%)",
            hovermode='x unified',
            template='plotly_white',
            font=dict(family='Inter, sans-serif'),
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=50, r=20, t=30, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )

        # ── Gráfico 2: PNT % con umbrales ───────────────────
        fig_nt = go.Figure()
        if not df.empty and 'fecha' in df.columns:
            nt_series = df.get('perdidas_nt_pct', pd.Series(dtype=float))
            colors = ['#e74c3c' if v < 0 or v > 25 else '#2ecc71' if v < 5 else '#f39c12'
                       for v in nt_series]
            fig_nt.add_trace(go.Bar(
                x=df['fecha'],
                y=nt_series,
                name='PNT (%)',
                marker_color=colors,
                opacity=0.8,
            ))
            # Líneas de umbral
            fig_nt.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="0%")
            fig_nt.add_hline(y=5, line_dash="dash", line_color="#f39c12", annotation_text="5% (moderado)")
            fig_nt.add_hline(y=10, line_dash="dash", line_color="#e74c3c", annotation_text="10% (alto)")

        fig_nt.update_layout(
            xaxis_title="Fecha",
            yaxis_title="PNT (%)",
            hovermode='x unified',
            template='plotly_white',
            font=dict(family='Inter, sans-serif'),
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=50, r=20, t=30, b=40),
            showlegend=False,
        )

        # ── Tarjeta de Interpretación ────────────────────────
        avg_nt = stats.get('pct_promedio_nt', 0) or 0
        avg_tec = stats.get('pct_promedio_tecnicas', 0) or 0
        avg_total = stats.get('pct_promedio_total', 0) or 0

        interpretacion = dbc.Card([
            dbc.CardHeader([
                html.I(className="fas fa-info-circle me-2"),
                "Interpretación del Análisis PNT"
            ], style={'fontWeight': '600', 'backgroundColor': '#f8f9fa'}),
            dbc.CardBody([
                html.P([
                    html.Strong("Método: "), "RESIDUO_HÍBRIDO_CREG — ",
                    "P_total = (Gene − DemaUsuario_est) / Gene, donde ",
                    "DemaUsuario_est = DemaReal × (1 − SDL_total)"
                ], style={'fontSize': '0.85rem', 'marginBottom': '8px'}),
                html.P([
                    html.Strong("Resultados promedio: "),
                    f"P_total = {avg_total:.2f}%, P_técnicas = {avg_tec:.2f}%, ",
                    html.Strong(f"P_NT = {avg_nt:.2f}%"),
                ], style={'fontSize': '0.85rem', 'marginBottom': '8px'}),
                html.Hr(),
                html.P([
                    html.Strong("Nota metodológica: "),
                    "Se usa DemaReal (demanda real medida en frontera STN/SDL) con factor "
                    "de pérdidas SDL total CREG (12%) para estimar energía a nivel de usuario "
                    "final. P_NT es el residuo entre pérdidas totales estimadas y técnicas "
                    "(STN medido + distribución CREG 8.5%). Método HOTFIX 4.0 — FASE 4."
                ], style={'fontSize': '0.8rem', 'color': '#666', 'marginBottom': '8px'}),
                html.Div([
                    html.Span(f"{emoji} ", style={'fontSize': '1.5rem'}),
                    html.Span(f"Nivel actual: {sem_label} — PNT 30d: {pnt_30d:.2f}%",
                              style={'fontWeight': '600'}),
                ], style={
                    'padding': '10px',
                    'borderRadius': '8px',
                    'backgroundColor': '#f0f0f0',
                    'textAlign': 'center',
                }),
            ]),
        ], style={'marginBottom': '16px'})

        # ── Layout final ─────────────────────────────────────
        contenido = html.Div([
            kpis,

            html.Div([
                crear_chart_card_custom(
                    "Evolución de Pérdidas: Técnicas vs No Técnicas",
                    dcc.Graph(figure=fig_stacked, config={'displayModeBar': True, 'displaylogo': False}),
                ),
            ], style={'marginBottom': '16px'}),

            html.Div([
                html.Div([
                    crear_chart_card_custom(
                        "Pérdidas No Técnicas (%) — Semáforo Diario",
                        dcc.Graph(figure=fig_nt, config={'displayModeBar': True, 'displaylogo': False}),
                    ),
                ], style={'flex': '2'}),
                html.Div([
                    interpretacion,
                ], style={'flex': '1'}),
            ], className="t-grid t-grid-2"),

            # Enlace a página detallada PNT (FASE 5)
            html.Div([
                dbc.Button([
                    html.I(className="fas fa-external-link-alt me-2"),
                    "Ver análisis detallado de Pérdidas NT"
                ], href="/perdidas-nt", color="outline-danger", className="mt-3",
                style={'fontWeight': '500'}),
            ], style={'textAlign': 'center', 'marginTop': '8px'}),
        ])

        return contenido

    except Exception as e:
        logger.error("Error en actualizar_perdidas_nt: %s", e)
        return dbc.Alert([
            html.H5("Error al cargar Pérdidas No Técnicas", className="alert-heading"),
            html.P(f"Detalle: {str(e)}"),
            html.Hr(),
            html.P("Por favor, intente nuevamente o contacte al administrador.", className="mb-0"),
        ], color="danger")