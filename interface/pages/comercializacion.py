"""
Página de Comercialización - Portal Energético MME
Análisis de precios de bolsa y escasez del mercado eléctrico colombiano
"""

import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
from datetime import date, timedelta
import pandas as pd
import traceback
import logging

from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import crear_chart_card, crear_page_header, crear_filter_bar
from domain.services.commercial_service import CommercialService

def get_plotly_modules():
    """Importación diferida de Plotly para optimizar carga inicial"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

# Configurar logging
logger = logging.getLogger(__name__)

# Instanciar servicio
_service = CommercialService()

# Registrar la página
dash.register_page(__name__, path='/comercializacion', name='Comercialización', title='Comercialización - Portal MME')

# ==================== FUNCIONES DE DATOS ====================

def obtener_rango_fechas_disponibles():
    """Obtener el rango de fechas con datos disponibles"""
    return _service.get_date_range()

def obtener_precio_bolsa(fecha_inicio, fecha_fin):
    """Obtener datos de Precio Bolsa Nacional"""
    return _service.get_stock_price(fecha_inicio, fecha_fin)

def obtener_precio_escasez(fecha_inicio, fecha_fin):
    """Obtener datos de Precio Escasez"""
    return _service.get_scarcity_price(fecha_inicio, fecha_fin)

def obtener_precio_escasez_activacion(fecha_inicio, fecha_fin):
    """Obtener datos de Precio Escasez Activación"""
    return _service.get_activation_scarcity_price(fecha_inicio, fecha_fin)

def obtener_precio_escasez_superior(fecha_inicio, fecha_fin):
    """Obtener datos de Precio Escasez Superior"""
    return _service.get_superior_scarcity_price(fecha_inicio, fecha_fin)

def obtener_precio_escasez_inferior(fecha_inicio, fecha_fin):
    """Obtener datos de Precio Escasez Inferior"""
    return _service.get_inferior_scarcity_price(fecha_inicio, fecha_fin)



# ==================== FUNCIONES DE VISUALIZACIÓN ====================

def crear_grafica_precios(df_bolsa, df_escasez, df_escasez_act, df_escasez_sup=None, df_escasez_inf=None):
    """Crear gráfica de líneas con todos los precios disponibles"""
    px, go = get_plotly_modules()
    
    # Verificar si hay al menos algún dato
    dfs_disponibles = [df for df in [df_bolsa, df_escasez, df_escasez_act, df_escasez_sup, df_escasez_inf] 
                       if df is not None and not df.empty]
    
    if not dfs_disponibles:
        fig = go.Figure()
        fig.add_annotation(
            text="No hay datos disponibles para el rango de fechas seleccionado",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(height=500)
        return fig
    
    # Combinar datos de todas las métricas disponibles
    dfs_to_concat = []
    if not df_bolsa.empty:
        dfs_to_concat.append(df_bolsa[['Date', 'Value', 'Metrica']])
    if not df_escasez.empty:
        dfs_to_concat.append(df_escasez[['Date', 'Value', 'Metrica']])
    if not df_escasez_act.empty:
        dfs_to_concat.append(df_escasez_act[['Date', 'Value', 'Metrica']])
    if df_escasez_sup is not None and not df_escasez_sup.empty:
        dfs_to_concat.append(df_escasez_sup[['Date', 'Value', 'Metrica']])
    if df_escasez_inf is not None and not df_escasez_inf.empty:
        dfs_to_concat.append(df_escasez_inf[['Date', 'Value', 'Metrica']])
    
    df_combinado = pd.concat(dfs_to_concat, ignore_index=True)
    
    # Crear gráfica
    fig = px.line(
        df_combinado,
        x='Date',
        y='Value',
        color='Metrica',
        title='Evolución de Precios del Mercado Eléctrico',
        labels={'Date': 'Fecha', 'Value': 'Precio ($/kWh)', 'Metrica': 'Métrica'},
        color_discrete_map={
            'Precio Bolsa Nacional': '#FFB800',  # Amarillo/Naranja brillante
            'Precio Escasez': '#DC3545',  # Rojo
            'Precio Escasez Activación': '#28A745',  # Verde (histórico hasta feb 2025)
            'Precio Escasez Superior': '#FF6B6B',  # Rojo claro (desde mar 2025)
            'Precio Escasez Inferior': '#4ECDC4'   # Turquesa (desde mar 2025)
        }
    )
    
    fig.update_traces(mode='lines+markers', marker=dict(size=8), line=dict(width=2))
    
    fig.update_layout(
        height=480,
        hovermode='x unified',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='Inter, sans-serif', size=12),
        margin=dict(l=60, r=20, t=30, b=40),
        xaxis=dict(
            showgrid=True,
            gridcolor='#f0f0f0',
            title_font=dict(size=13, color='#475569')
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#f0f0f0',
            title_font=dict(size=13, color='#475569')
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

def crear_tabla_horaria_unificada(datos_metricas, valores_diarios, fecha_seleccionada):
    """Crear dos tablas: una con Precio Bolsa por hora, otra con métricas diarias
    
    Args:
        datos_metricas: Dict con claves 'bolsa', 'escasez_act', 'escasez_sup', 'escasez_inf'
                       Cada valor es un dict con datos horarios o None
        valores_diarios: Dict con valores diarios de cada métrica para la fecha seleccionada
    """
    
    # ========== TABLA 1: PRECIO BOLSA NACIONAL POR HORA ==========
    datos_bolsa = datos_metricas.get('bolsa')
    
    if datos_bolsa and isinstance(datos_bolsa, dict):
        # Extraer valores horarios
        valores_horarios_bolsa = []
        for i in range(1, 25):
            col_name = f'Hora_{i:02d}'
            col_name_alt = f'Values_Hour{i:02d}'
            
            valor = None
            if col_name in datos_bolsa:
                valor = datos_bolsa[col_name]
            elif col_name_alt in datos_bolsa:
                valor = datos_bolsa[col_name_alt]
            
            valores_horarios_bolsa.append({
                'hora': f"Hora {i:02d}",
                'valor': valor
            })
        
        # Calcular total y promedio Bolsa
        valores_bolsa = [v['valor'] for v in valores_horarios_bolsa if v['valor'] is not None]
        total_bolsa = sum(valores_bolsa) if valores_bolsa else None
        promedio_bolsa = total_bolsa / len(valores_bolsa) if valores_bolsa else None  # type: ignore[operator]
        
        # Crear filas para tabla Bolsa
        filas_bolsa = []
        for item in valores_horarios_bolsa:
            filas_bolsa.append(html.Tr([
                html.Td(item['hora'], style={'padding': '8px', 'fontWeight': '500', 'backgroundColor': '#fff8e1'}),
                html.Td(
                    f"${item['valor']:.2f}" if item['valor'] is not None else "-",
                    style={'padding': '8px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': 'bold'}
                )
            ]))
        
        tabla_bolsa = html.Div([
            html.H6("💰 Precio Bolsa Nacional", style={'color': '#FFB800', 'marginBottom': '10px', 'fontWeight': 'bold'}),
            html.Div([
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("HORA", style={'padding': '10px', 'backgroundColor': '#FFB800', 'color': 'white', 'position': 'sticky', 'top': 0}),
                        html.Th("PRECIO ($/kWh)", style={'padding': '10px', 'backgroundColor': '#FFB800', 'color': 'white', 'textAlign': 'right', 'position': 'sticky', 'top': 0})
                    ])),
                    html.Tbody(filas_bolsa + [
                        html.Tr([
                            html.Td("TOTAL (24h)", style={'padding': '10px', 'fontWeight': 'bold', 'fontSize': '15px', 'backgroundColor': '#0d6efd', 'color': 'white'}),
                            html.Td(
                                f"${total_bolsa:.2f}" if total_bolsa is not None else "-",
                                style={'padding': '10px', 'textAlign': 'right', 'fontWeight': 'bold', 'fontSize': '15px', 'backgroundColor': '#0d6efd', 'color': 'white', 'fontFamily': 'monospace'}
                            )
                        ]),
                        html.Tr([
                            html.Td("PROMEDIO", style={'padding': '10px', 'fontWeight': 'bold', 'fontSize': '15px', 'backgroundColor': '#28a745', 'color': 'white'}),
                            html.Td(
                                f"${promedio_bolsa:.2f}" if promedio_bolsa is not None else "-",
                                style={'padding': '10px', 'textAlign': 'right', 'fontWeight': 'bold', 'fontSize': '15px', 'backgroundColor': '#28a745', 'color': 'white', 'fontFamily': 'monospace'}
                            )
                        ])
                    ])
                ], className="table table-sm table-striped", style={'marginBottom': '0', 'fontSize': '14px'})
            ], style={'maxHeight': '600px', 'overflowY': 'auto'})
        ])
    else:
        tabla_bolsa = html.Div(
            "No hay datos horarios de Precio Bolsa disponibles",
            className="alert alert-warning"
        )
    
    # ========== TABLA 2: OTRAS MÉTRICAS (VALORES DIARIOS) ==========
    metricas_diarias = [
        ('escasez', 'Precio Escasez', '#DC3545'),
        ('escasez_act', 'Escasez Activación', '#28A745'),
        ('escasez_sup', 'Escasez Superior', '#FF6B6B'),
        ('escasez_inf', 'Escasez Inferior', '#4ECDC4')
    ]
    
    filas_metricas = []
    for key, nombre, color in metricas_diarias:
        # Obtener el valor diario directamente del parámetro
        valor_diario = valores_diarios.get(key)
        
        filas_metricas.append(html.Tr([
            html.Td(nombre, style={'padding': '12px', 'fontWeight': 'bold', 'backgroundColor': color, 'color': 'white'}),
            html.Td(
                f"${valor_diario:.2f}" if valor_diario is not None else "Sin datos",
                style={
                    'padding': '12px',
                    'textAlign': 'right',
                    'fontFamily': 'monospace',
                    'fontSize': '16px',
                    'fontWeight': 'bold',
                    'color': '#000' if valor_diario is not None else '#999'
                }
            )
        ]))
    
    tabla_metricas = html.Div([
        html.H6("📊 Otras Métricas (Valor Diario)", style={'color': '#495057', 'marginBottom': '10px', 'fontWeight': 'bold'}),
        html.Table([
            html.Thead(html.Tr([
                html.Th("MÉTRICA", style={'padding': '10px', 'backgroundColor': '#6c757d', 'color': 'white'}),
                html.Th("VALOR ($/kWh)", style={'padding': '10px', 'backgroundColor': '#6c757d', 'color': 'white', 'textAlign': 'right'})
            ])),
            html.Tbody(filas_metricas)
        ], className="table table-bordered", style={'marginBottom': '0', 'fontSize': '14px'}),
        html.Small(
            "ℹ️ Estas métricas no tienen desagregación horaria en XM",
            className="text-muted d-block mt-2",
            style={'fontSize': '12px'}
        )
    ])
    
    # ========== LAYOUT: DOS COLUMNAS ==========
    return dbc.Row([
        dbc.Col(tabla_bolsa, md=7),
        dbc.Col(tabla_metricas, md=5)
    ])

# ==================== MAPA DEPARTAMENTAL ====================

def _crear_mapa_comercializacion():
    """Choropleth de usuarios del servicio eléctrico por departamento. SUI 2023."""
    import json
    import os
    px, go = get_plotly_modules()
    try:
        df = _service.get_usuarios_por_departamento()
        geojson_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "assets",
            "departamentos_colombia.geojson",
        )
        with open(geojson_path, encoding="utf-8") as f:
            geojson = json.load(f)

        fig = px.choropleth(
            df,
            geojson=geojson,
            locations="codigo_dpto",
            featureidkey="properties.DPTO",
            color="usuarios_miles",
            color_continuous_scale="Greens",
            labels={"usuarios_miles": "Usuarios (miles)"},
            hover_name="departamento",
            hover_data={
                "participacion_pct": True,
                "cobertura_est": True,
                "codigo_dpto": False,
            },
            title="Usuarios del Servicio Eléctrico — Colombia",
        )
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(
            height=550,
            margin=dict(l=0, r=0, t=50, b=0),
            coloraxis_colorbar=dict(title="Miles", thickness=15),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", size=12),
        )

        top5 = df.head(5)[["departamento", "usuarios_miles", "cobertura_est"]]
        rows_top5 = [
            html.Tr([html.Td(r["departamento"]),
                     html.Td(f"{r['usuarios_miles']:,} mil"),
                     html.Td(r["cobertura_est"])])
            for _, r in top5.iterrows()
        ]

        return html.Div([
            dbc.Alert([
                html.I(className="fas fa-circle-info me-2"),
                "Fuente: SUI 2023. Total Colombia: ~16.8 millones de usuarios. "
                "Distribución estimada por departamento según datos administrativos SUI.",
            ], color="info", className="mb-3 small"),
            dbc.Row([
                dbc.Col(
                    dcc.Graph(figure=fig, config={"displayModeBar": False}),
                    md=8,
                ),
                dbc.Col([
                    html.H6("🟢 Top 5 Mayor Cobertura", className="mb-2 fw-bold"),
                    dbc.Table(
                        [html.Thead(html.Tr([
                            html.Th("Departamento"),
                            html.Th("Usuarios"),
                            html.Th("Cobertura"),
                        ])),
                         html.Tbody(rows_top5)],
                        bordered=True, hover=True, size="sm",
                    ),
                    html.Small(
                        "Fuente: SUI 2023. Total Colombia: ~16.8M usuarios.",
                        className="text-muted fst-italic d-block mt-2",
                        style={"fontSize": "0.75rem"},
                    ),
                ], md=4),
            ]),
        ])
    except Exception as e:
        logger.error("Error mapa departamental comercialización: %s", e, exc_info=True)
        return dbc.Alert(f"Error cargando mapa: {e}", color="danger")


# ==================== LAYOUT ====================

def layout(**kwargs):
    """Layout principal de la página de comercialización"""
    
    # Obtener rango de fechas disponibles en BD
    fecha_min_disponible, fecha_max_disponible = obtener_rango_fechas_disponibles()
    
    # Configurar valores por defecto (últimos 90 días disponibles)
    fecha_fin = fecha_max_disponible
    fecha_inicio = max(fecha_min_disponible, fecha_fin - timedelta(days=90))
    
    precio_promedio_bolsa = 0.0
    precio_max_bolsa = 0.0
    precio_escasez_actual = 0.0
    spread_escasez = 0.0  # Nueva métrica: diferencia Superior - Inferior
    
    # Obtener datos iniciales de TODAS las métricas
    try:
        df_bolsa = obtener_precio_bolsa(fecha_inicio, fecha_fin)
        df_escasez = obtener_precio_escasez(fecha_inicio, fecha_fin)
        df_escasez_act = obtener_precio_escasez_activacion(fecha_inicio, fecha_fin)
        df_escasez_sup = obtener_precio_escasez_superior(fecha_inicio, fecha_fin)
        df_escasez_inf = obtener_precio_escasez_inferior(fecha_inicio, fecha_fin)
        
        fig_precios = crear_grafica_precios(df_bolsa, df_escasez, df_escasez_act, df_escasez_sup, df_escasez_inf)
        
        # Calcular estadísticas para las fichas
        if not df_bolsa.empty:
            precio_promedio_bolsa = float(df_bolsa['Value'].mean())
            precio_max_bolsa = float(df_bolsa['Value'].max())
        
        # Priorizar métrica más reciente para ficha Escasez
        if not df_escasez_sup.empty:
            precio_escasez_actual = float(df_escasez_sup['Value'].iloc[-1])
        elif not df_escasez_act.empty:
            precio_escasez_actual = float(df_escasez_act['Value'].iloc[-1])
        elif not df_escasez.empty:
            precio_escasez_actual = float(df_escasez['Value'].iloc[-1])
        
        # Calcular spread (diferencia entre Superior e Inferior)
        if not df_escasez_sup.empty and not df_escasez_inf.empty:
            valor_sup = float(df_escasez_sup['Value'].iloc[-1])
            valor_inf = float(df_escasez_inf['Value'].iloc[-1])
            spread_escasez = valor_sup - valor_inf
        
    except Exception as e:
        logger.error(f"Error cargando datos iniciales: {e}")
        traceback.print_exc()
        px, go = get_plotly_modules()
        fig_precios = go.Figure()
        fig_precios.add_annotation(
            text="Error al cargar datos. Por favor, actualice la página.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="red")
        )
    
    return html.Div([
        crear_page_header(
            titulo="Comercialización",
            icono="fas fa-store",
            breadcrumb="Inicio / Comercialización",
            fecha=f"Hasta: {fecha_max_disponible.strftime('%d/%m/%Y')}",
        ),

        crear_filter_bar(
            html.Div([
                html.Label("Periodo", className="t-filter-label"),
                dcc.Dropdown(
                    id='dropdown-rango-comercializacion',
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
                    id='fecha-filtro-comercializacion',
                    min_date_allowed=date(2000, 1, 1),  # type: ignore[arg-type]
                    max_date_allowed=date.today(),  # type: ignore[arg-type]
                    initial_visible_month=date.today(),  # type: ignore[arg-type]
                    start_date=fecha_inicio,
                    end_date=fecha_fin,
                    display_format='YYYY-MM-DD',
                ),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px'}),

            dbc.Button([
                html.I(className="fas fa-search me-1"), "Actualizar"
            ], id='btn-actualizar-comercializacion', color="primary", size="sm"),
            dbc.Button([
                html.I(className="fas fa-file-excel me-1"), "Excel"
            ], id='btn-excel-comercializacion', color="success", size="sm", outline=True),
            dcc.Download(id='download-excel-comercializacion'),
        ),

        # KPIs container (updated by callback)
        html.Div(
            id='kpis-comercializacion',
            children=crear_kpi_row([
                {"titulo": "Precio Promedio Bolsa", "valor": f"${precio_promedio_bolsa:.2f}", "unidad": "$/kWh", "icono": "fas fa-dollar-sign", "color": "blue"},
                {"titulo": "Precio Máximo Bolsa", "valor": f"${precio_max_bolsa:.2f}", "unidad": "$/kWh", "icono": "fas fa-chart-line", "color": "orange"},
                {"titulo": "Escasez Superior", "valor": f"${precio_escasez_actual:.2f}", "unidad": "$/kWh", "icono": "fas fa-exclamation-triangle", "color": "red"},
                {"titulo": "Spread Escasez", "valor": f"${spread_escasez:.2f}", "unidad": "$/kWh", "icono": "fas fa-exchange-alt", "color": "cyan"},
            ], columnas=4),
        ),

        # Info button for Spread modal
        html.Div(
            html.Button("ℹ Qué es el Spread de Escasez?", id="btn-info-spread", n_clicks=0,
                        className="btn btn-sm btn-outline-secondary",
                        style={'fontSize': '0.75rem', 'marginTop': '-8px', 'marginBottom': '12px'}),
            style={'textAlign': 'right'},
        ),

        # Gráfica principal
        crear_chart_card(
            titulo="Evolución de Precios del Mercado Eléctrico",
            graph_id='grafica-precios-comercializacion',
            height=480,
        ),

        # Stores y modales
        dcc.Store(id='store-comercializacion', data=None),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(id='modal-titulo-comercializacion')),
            dbc.ModalBody(id='modal-contenido-comercializacion'),
            dbc.ModalFooter(
                dbc.Button("Cerrar", id='modal-cerrar-comercializacion', className="ms-auto")
            )
        ], id='modal-detalle-comercializacion', size='xl', is_open=False),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Spread de Escasez")),
            dbc.ModalBody([
                html.P("El Spread de Escasez representa la diferencia entre el Precio de Escasez Superior y el Precio de Escasez Inferior.",
                       style={'marginBottom': '10px', 'color': '#2c3e50'}),
                html.P([html.Strong("Spread = Precio Escasez Superior - Precio Escasez Inferior")],
                       style={'marginBottom': '20px', 'marginLeft': '20px', 'color': '#1f2937'}),
                html.H6("Interpretación:", style={'fontWeight': 'bold', 'color': '#2c3e50'}),
                html.Ul([
                    html.Li([html.Strong("> $500/kWh: "), "Alta volatilidad, riesgo de escasez severa."]),
                    html.Li([html.Strong("$300-$500/kWh: "), "Rango normal de operación."]),
                    html.Li([html.Strong("< $300/kWh: "), "Baja probabilidad de escasez."]),
                ]),
            ], style={'fontSize': '0.95rem', 'lineHeight': '1.6'}),
            dbc.ModalFooter(
                dbc.Button("Cerrar", id='modal-cerrar-spread', className="ms-auto")
            )
        ], id='modal-info-spread', size='lg', is_open=False),

        # Mapa departamental de usuarios
        html.Div([
            html.H5("🗺️ Usuarios del Servicio Eléctrico por Departamento",
                    className="mb-3 text-secondary fw-semibold mt-4"),
            _crear_mapa_comercializacion(),
        ]),
    ], className="t-page")

# ==================== CALLBACKS ====================

@callback(
    [Output('fecha-filtro-comercializacion', 'start_date'),
     Output('fecha-filtro-comercializacion', 'end_date')],
    Input('dropdown-rango-comercializacion', 'value'),
    prevent_initial_call=True
)
def actualizar_fechas_rango_comercializacion(rango):
    """Actualiza las fechas del datepicker según el rango seleccionado"""
    hoy = date.today()
    if rango == '30d': return hoy - timedelta(days=30), hoy
    if rango == '90d': return hoy - timedelta(days=90), hoy
    if rango == '180d': return hoy - timedelta(days=180), hoy
    if rango == '365d': return hoy - timedelta(days=365), hoy
    if rango == '730d': return hoy - timedelta(days=730), hoy
    if rango == '1825d': return hoy - timedelta(days=1825), hoy
    return dash.no_update, dash.no_update

# Registrar callback del filtro de fechas (ya no es necesario el genérico, usamos el específico)
# registrar_callback_filtro_fechas('comercializacion')

@callback(
    [Output('grafica-precios-comercializacion', 'figure'),
     Output('store-comercializacion', 'data'),
     Output('kpis-comercializacion', 'children')],
    [Input('btn-actualizar-comercializacion', 'n_clicks'),
     Input('fecha-filtro-comercializacion', 'start_date'),
     Input('fecha-filtro-comercializacion', 'end_date')],
    prevent_initial_call=False
)
def actualizar_datos_comercializacion(n_clicks, fecha_inicio_str, fecha_fin_str):
    """Callback para actualizar la gráfica y fichas según las fechas seleccionadas"""
    
    px, go = get_plotly_modules()

    # Fallback de fechas por defecto si llegan None en el initial call
    if not fecha_fin_str:
        fecha_fin_str = date.today().strftime('%Y-%m-%d')
    if not fecha_inicio_str:
        fecha_inicio_str = (date.today() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    try:
        # Convertir fechas
        fecha_inicio = pd.to_datetime(fecha_inicio_str).date()
        fecha_fin = pd.to_datetime(fecha_fin_str).date()
        
        # Validar rango
        if (fecha_fin - fecha_inicio).days > 365:
            fig_error = go.Figure().add_annotation(
                text="Por favor seleccione un rango menor a 365 días",
                xref="paper", yref="paper", x=0.5, y=0.5,
                showarrow=False, font=dict(size=16, color="red")
            )
            kpis_vacio = crear_kpi_row([
                {"titulo": "Precio Promedio Bolsa", "valor": "$0.00", "unidad": "$/kWh", "icono": "fas fa-dollar-sign", "color": "blue"},
                {"titulo": "Precio Máximo Bolsa", "valor": "$0.00", "unidad": "$/kWh", "icono": "fas fa-chart-line", "color": "orange"},
                {"titulo": "Escasez Superior", "valor": "$0.00", "unidad": "$/kWh", "icono": "fas fa-exclamation-triangle", "color": "red"},
                {"titulo": "Spread Escasez", "valor": "$0.00", "unidad": "$/kWh", "icono": "fas fa-exchange-alt", "color": "cyan"},
            ], columnas=4)
            return fig_error, None, kpis_vacio
        
        # Obtener datos de TODAS las métricas (incluyendo nuevas desde marzo 2025)
        df_bolsa = obtener_precio_bolsa(fecha_inicio, fecha_fin)
        df_escasez = obtener_precio_escasez(fecha_inicio, fecha_fin)
        df_escasez_act = obtener_precio_escasez_activacion(fecha_inicio, fecha_fin)
        df_escasez_sup = obtener_precio_escasez_superior(fecha_inicio, fecha_fin)
        df_escasez_inf = obtener_precio_escasez_inferior(fecha_inicio, fecha_fin)
        
        # Crear gráfica con TODAS las métricas disponibles
        fig = crear_grafica_precios(df_bolsa, df_escasez, df_escasez_act, df_escasez_sup, df_escasez_inf)
        
        # Calcular estadísticas
        precio_promedio = df_bolsa['Value'].mean() if not df_bolsa.empty else 0.0
        precio_max = df_bolsa['Value'].max() if not df_bolsa.empty else 0.0
        
        # Priorizar métrica más reciente para ficha Escasez
        if not df_escasez_sup.empty:
            precio_escasez = df_escasez_sup['Value'].iloc[-1]
        elif not df_escasez_act.empty:
            precio_escasez = df_escasez_act['Value'].iloc[-1]
        elif not df_escasez.empty:
            precio_escasez = df_escasez['Value'].iloc[-1]
        else:
            precio_escasez = 0.0
        
        # Calcular spread (Superior - Inferior)
        spread_escasez = 0.0
        if not df_escasez_sup.empty and not df_escasez_inf.empty:
            valor_sup = df_escasez_sup['Value'].iloc[-1]
            valor_inf = df_escasez_inf['Value'].iloc[-1]
            spread_escasez = valor_sup - valor_inf
        
        # Guardar datos en store (TODAS las métricas)
        # Extraer datos horarios de TODAS las métricas
        datos_horarios = {
            'bolsa': {},
            'escasez_act': {},
            'escasez_sup': {},
            'escasez_inf': {}
        }
        
        # Función auxiliar para extraer datos horarios
        def extraer_datos_horarios(df, key):
            if not df.empty and 'Datos_Horarios' in df.columns:
                for idx, row in df.iterrows():
                    fecha_str = row['Date'].strftime('%Y-%m-%d')
                    if row['Datos_Horarios']:  # Solo si tiene datos
                        datos_horarios[key][fecha_str] = row['Datos_Horarios']
        
        # Extraer de todas las métricas
        extraer_datos_horarios(df_bolsa, 'bolsa')
        extraer_datos_horarios(df_escasez_act, 'escasez_act')
        extraer_datos_horarios(df_escasez_sup, 'escasez_sup')
        extraer_datos_horarios(df_escasez_inf, 'escasez_inf')
        
        # Preparar DataFrames para serialización (sin columna Datos_Horarios)
        def preparar_df(df):
            if df.empty:
                return None
            if 'Datos_Horarios' in df.columns:
                return df.drop(columns=['Datos_Horarios']).to_json(date_format='iso', orient='split')
            return df.to_json(date_format='iso', orient='split')
        
        # Extraer valores diarios por fecha para cada métrica
        valores_diarios = {}
        for df, key in [(df_bolsa, 'bolsa'), (df_escasez, 'escasez'), (df_escasez_act, 'escasez_act'), 
                        (df_escasez_sup, 'escasez_sup'), (df_escasez_inf, 'escasez_inf')]:
            valores_diarios[key] = {}
            if not df.empty and 'Date' in df.columns and 'Value' in df.columns:
                for idx, row in df.iterrows():
                    fecha_str = row['Date'].strftime('%Y-%m-%d')
                    valores_diarios[key][fecha_str] = float(row['Value'])
        
        store_data = {
            'bolsa': preparar_df(df_bolsa),
            'escasez': preparar_df(df_escasez),
            'escasez_act': preparar_df(df_escasez_act),
            'escasez_sup': preparar_df(df_escasez_sup),
            'escasez_inf': preparar_df(df_escasez_inf),
            'datos_horarios': datos_horarios,  # Dict con 4 claves, cada una con datos por fecha
            'valores_diarios': valores_diarios  # Valores diarios por fecha para cada métrica
        }
        
        return (
            fig, 
            store_data,
            crear_kpi_row([
                {"titulo": "Precio Promedio Bolsa", "valor": f"${precio_promedio:.2f}", "unidad": "$/kWh", "icono": "fas fa-dollar-sign", "color": "blue"},
                {"titulo": "Precio Máximo Bolsa", "valor": f"${precio_max:.2f}", "unidad": "$/kWh", "icono": "fas fa-chart-line", "color": "orange"},
                {"titulo": "Escasez Superior", "valor": f"${precio_escasez:.2f}", "unidad": "$/kWh", "icono": "fas fa-exclamation-triangle", "color": "red"},
                {"titulo": "Spread Escasez", "valor": f"${spread_escasez:.2f}", "unidad": "$/kWh", "icono": "fas fa-exchange-alt", "color": "cyan"},
            ], columnas=4),
        )
        
    except Exception as e:
        logger.error(f"Error en actualizar_datos_comercializacion: {e}")
        traceback.print_exc()
        
        fig_error = go.Figure().add_annotation(
            text=f"Error al cargar datos: {str(e)[:100]}",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="red")
        )
        kpis_error = crear_kpi_row([
            {"titulo": "Precio Promedio Bolsa", "valor": "$0.00", "unidad": "$/kWh", "icono": "fas fa-dollar-sign", "color": "blue"},
            {"titulo": "Precio Máximo Bolsa", "valor": "$0.00", "unidad": "$/kWh", "icono": "fas fa-chart-line", "color": "orange"},
            {"titulo": "Escasez Superior", "valor": "$0.00", "unidad": "$/kWh", "icono": "fas fa-exclamation-triangle", "color": "red"},
            {"titulo": "Spread Escasez", "valor": "$0.00", "unidad": "$/kWh", "icono": "fas fa-exchange-alt", "color": "cyan"},
        ], columnas=4)
        
        return fig_error, None, kpis_error

@callback(
    [Output('modal-detalle-comercializacion', 'is_open'),
     Output('modal-titulo-comercializacion', 'children'),
     Output('modal-contenido-comercializacion', 'children')],
    [Input('grafica-precios-comercializacion', 'clickData'),
     Input('modal-cerrar-comercializacion', 'n_clicks')],
    [State('store-comercializacion', 'data'),
     State('modal-detalle-comercializacion', 'is_open')],
    prevent_initial_call=True
)
def toggle_modal_detalle(clickData, close_clicks, store_data, is_open):
    """Abrir/cerrar modal con detalle horario al hacer clic en la gráfica"""
    
    from dash import callback_context as ctx
    
    logger.info("="*80)
    logger.info("🔔 toggle_modal_detalle EJECUTADO")
    logger.info(f"clickData: {clickData}")
    logger.info(f"ctx.triggered: {ctx.triggered}")
    logger.info("="*80)
    
    if not ctx.triggered:
        logger.warning("No hay triggered context")
        return False, "", ""
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    logger.info(f"Trigger ID: {trigger_id}")
    
    # Cerrar modal
    if trigger_id == 'modal-cerrar-comercializacion':
        logger.info("Cerrando modal")
        return False, "", ""
    
    # Abrir modal con datos
    if trigger_id == 'grafica-precios-comercializacion' and clickData:
        try:
            # Logging para debug
            logger.info(f"clickData recibido: {clickData}")
            
            # Obtener el primer punto (Plotly devuelve múltiples puntos en el mismo X)
            if not clickData.get('points'):
                return False, "", ""
            
            punto = clickData['points'][0]
            
            # Extraer fecha del punto
            fecha_click = pd.to_datetime(punto['x']).date()
            
            logger.info(f"Fecha seleccionada: {fecha_click}, abriendo modal con todas las métricas")
            
            # Validar que store_data existe y tiene la estructura correcta
            if not store_data:
                logger.warning("store_data es None")
                return True, "Sin datos", html.Div(
                    "No hay datos disponibles. Por favor, haga click en 'Actualizar' primero.",
                    className="alert alert-warning"
                )
            
            if not isinstance(store_data, dict):
                logger.error(f"store_data no es dict: {type(store_data)}")
                return True, "Error de datos", html.Div(
                    f"Error en la estructura de datos (tipo: {type(store_data).__name__})",
                    className="alert alert-danger"
                )
            
            if 'datos_horarios' not in store_data:
                logger.warning(f"store_data keys: {store_data.keys()}")
                return True, "Datos no disponibles", html.Div(
                    "Los datos horarios no están disponibles para este rango de fechas.",
                    className="alert alert-info"
                )
            
            # Buscar datos horarios de TODAS las métricas para esa fecha
            fecha_str = fecha_click.strftime('%Y-%m-%d')
            datos_horarios_all = store_data['datos_horarios']
            valores_diarios_all = store_data.get('valores_diarios', {})
            
            # Recopilar datos de todas las métricas disponibles
            datos_metricas = {}
            valores_diarios = {}
            metricas_disponibles = []
            
            for metrica_key in ['bolsa', 'escasez', 'escasez_act', 'escasez_sup', 'escasez_inf']:
                # Datos horarios
                datos_metrica = datos_horarios_all.get(metrica_key, {}).get(fecha_str)
                datos_metricas[metrica_key] = datos_metrica
                
                # Valores diarios
                valor_diario = valores_diarios_all.get(metrica_key, {}).get(fecha_str)
                valores_diarios[metrica_key] = valor_diario
                
                if datos_metrica or valor_diario:
                    metricas_disponibles.append(metrica_key)
            
            logger.info(f"Métricas disponibles para {fecha_str}: {metricas_disponibles}")
            logger.info(f"Valores diarios: {valores_diarios}")
            
            # Verificar que al menos una métrica tenga datos
            if not metricas_disponibles:
                return True, f"Detalle del {fecha_click.strftime('%d/%m/%Y')}", html.Div(
                    f"No hay datos disponibles para {fecha_click.strftime('%d/%m/%Y')}",
                    className="alert alert-warning"
                )
            
            # Crear tabla unificada con todas las métricas
            tabla = crear_tabla_horaria_unificada(datos_metricas, valores_diarios, fecha_click)
            
            titulo = f"📊 Detalle Horario Completo - {fecha_click.strftime('%d/%m/%Y')}"
            
            return True, titulo, tabla
            
        except Exception as e:
            logger.error(f"Error mostrando detalle: {e}")
            logger.error(f"clickData completo: {clickData}")
            traceback.print_exc()
            return True, "Error", html.Div([
                html.P(f"Error al cargar datos: '{str(e)}'", className="text-danger"),
                html.P(f"Detalles técnicos: {str(clickData)[:200]}", className="text-muted small")
            ], className="alert alert-danger")
    
    return is_open, "", ""

@callback(
    Output('modal-info-spread', 'is_open'),
    [Input('btn-info-spread', 'n_clicks'),
     Input('modal-cerrar-spread', 'n_clicks')],
    [State('modal-info-spread', 'is_open')],
    prevent_initial_call=True
)
def toggle_modal_spread(btn_clicks, close_clicks, is_open):
    """Abrir/cerrar modal de información del Spread de Escasez"""
    return not is_open



# Fase G: Excel export para Comercializacion
@callback(
    Output('download-excel-comercializacion', 'data'),
    Input('btn-excel-comercializacion', 'n_clicks'),
    [State('fecha-filtro-comercializacion', 'start_date'),
     State('fecha-filtro-comercializacion', 'end_date')],
    prevent_initial_call=True,
)
def exportar_excel_comercializacion(n_clicks, fecha_inicio_str, fecha_fin_str):
    """Exporta precios de bolsa y escasez a Excel con múltiples hojas"""
    import io
    try:
        if not fecha_inicio_str or not fecha_fin_str:
            return dash.no_update
        fecha_inicio = pd.to_datetime(fecha_inicio_str).date()
        fecha_fin = pd.to_datetime(fecha_fin_str).date()

        df_bolsa = obtener_precio_bolsa(fecha_inicio, fecha_fin)
        df_escasez = obtener_precio_escasez(fecha_inicio, fecha_fin)
        df_escasez_act = obtener_precio_escasez_activacion(fecha_inicio, fecha_fin)
        df_escasez_sup = obtener_precio_escasez_superior(fecha_inicio, fecha_fin)
        df_escasez_inf = obtener_precio_escasez_inferior(fecha_inicio, fecha_fin)

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            sheets = {
                'Precio_Bolsa': df_bolsa,
                'Escasez': df_escasez,
                'Escasez_Activacion': df_escasez_act,
                'Escasez_Superior': df_escasez_sup,
                'Escasez_Inferior': df_escasez_inf,
            }
            for sheet, df in sheets.items():
                if df is not None and not (isinstance(df, pd.DataFrame) and df.empty):
                    pd.DataFrame(df).to_excel(writer, sheet_name=sheet, index=False)
        buf.seek(0)
        fi = str(fecha_inicio)
        ff = str(fecha_fin)
        nombre = f"comercializacion_{fi}_al_{ff}.xlsx"
        return dcc.send_bytes(buf.read(), nombre)
    except Exception as e:
        logger.error("Error exportando Excel comercializacion: %s", e)
        return dash.no_update
