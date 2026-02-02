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

from core.constants import UIColors as COLORS
from interface.components.layout import crear_navbar_horizontal, crear_boton_regresar, crear_filtro_fechas_compacto, registrar_callback_filtro_fechas
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
        height=500,
        hovermode='x unified',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='Arial', size=12),
        xaxis=dict(
            showgrid=True,
            gridcolor='lightgray',
            title_font=dict(size=14, color='black')
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='lightgray',
            title_font=dict(size=14, color='black')
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

def crear_tabla_horaria(datos_hora, fecha_seleccionada):
    """Crear tabla con datos horarios de un día específico"""
    if not datos_hora or not isinstance(datos_hora, dict):
        return html.Div("No hay datos horarios disponibles", 
                       className="alert alert-warning")
    
    # Extraer valores de cada hora
    horas = []
    valores = []
    
    for i in range(1, 25):
        col_name = f'Values_Hour{i:02d}'
        if col_name in datos_hora:
            horas.append(f"Hora {i:02d}")
            valores.append(f"${datos_hora[col_name]:.2f}")
    
    if not horas:
        return html.Div("No hay datos horarios disponibles", 
                       className="alert alert-warning")
    
    # Crear DataFrame para la tabla
    df_tabla = pd.DataFrame({
        'Hora': horas,
        'Precio ($/kWh)': valores
    })
    
    # Dividir en 3 columnas para mejor visualización
    n = len(horas)
    tercio = n // 3
    
    col1 = df_tabla.iloc[:tercio]
    col2 = df_tabla.iloc[tercio:tercio*2]
    col3 = df_tabla.iloc[tercio*2:]
    
    def crear_mini_tabla(df_mini):
        return html.Table([
            html.Thead(html.Tr([
                html.Th("Hora", style={'padding': '8px', 'borderBottom': '2px solid #dee2e6'}),
                html.Th("Precio", style={'padding': '8px', 'borderBottom': '2px solid #dee2e6', 'textAlign': 'right'})
            ])),
            html.Tbody([
                html.Tr([
                    html.Td(row['Hora'], style={'padding': '6px'}),
                    html.Td(row['Precio ($/kWh)'], style={'padding': '6px', 'textAlign': 'right', 'fontWeight': 'bold'})
                ]) for _, row in df_mini.iterrows()
            ])
        ], className="table table-sm table-hover", style={'marginBottom': '0'})
    
    return html.Div([
        dbc.Row([
            dbc.Col(crear_mini_tabla(col1), md=4),
            dbc.Col(crear_mini_tabla(col2), md=4),
            dbc.Col(crear_mini_tabla(col3), md=4)
        ])
    ])

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
        # crear_navbar_horizontal(),
        # crear_boton_regresar() - Eliminado por solicitud de usuario
        
        html.Div(style={'transformOrigin': 'top center'}, children=[
        dbc.Container([
            
            # Filtro de fechas compacto
            # crear_filtro_fechas_compacto('comercializacion'),
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        # Columna 1: Rango Predefinido
                        dbc.Col([
                            html.Label("PERIODO DE ANÁLISIS:", className="fw-bold small text-muted mb-1"),
                            dcc.Dropdown(
                                id='dropdown-rango-comercializacion',
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
                                id='fecha-filtro-comercializacion',
                                min_date_allowed=date(2000, 1, 1),
                                max_date_allowed=date.today(),
                                initial_visible_month=date.today(),
                                start_date=fecha_inicio,
                                end_date=fecha_fin,
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
                            ], id='btn-actualizar-comercializacion', color="primary", className="w-100")
                        ], lg=3, md=12, className="d-flex align-items-end mb-2")
                    ])
                ])
            ], className="mb-4 shadow-sm border-0"),

            html.Small(f"📅 Hasta: {fecha_max_disponible.strftime('%d/%m/%Y')}", className="text-muted d-block", style={'fontSize': '0.75rem', 'marginTop': '-8px', 'marginBottom': '8px'}),
            
            # Fichas KPI en diseño horizontal (estilo sobrio profesional)
            dbc.Row([
                # Ficha 1: Precio Promedio Bolsa
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-dollar-sign", style={'color': '#111827', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                                html.Span("Precio Promedio Bolsa", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                                html.Span(f"${precio_promedio_bolsa:.2f}", id='ficha-precio-promedio', style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#111827', 'marginRight': '4px'}),
                                html.Span("$/kWh", style={'color': '#666', 'fontSize': '0.65rem'})
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '4px'})
                        ], style={'padding': '0.4rem 0.8rem', 'background': '#ffffff', 'borderRadius': '6px'})
                    ], className="shadow-sm")
                ], lg=3, md=6, style={'marginBottom': '0'}),
                
                # Ficha 2: Precio Máximo Bolsa
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-chart-line", style={'color': '#000000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                                html.Span("Precio Máximo Bolsa", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                                html.Span(f"${precio_max_bolsa:.2f}", id='ficha-precio-max', style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                                html.Span("$/kWh", style={'color': '#666', 'fontSize': '0.65rem'})
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '4px'})
                        ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)', 'borderRadius': '6px'})
                    ], className="shadow-sm")
                ], lg=3, md=6, style={'marginBottom': '0'}),
                
                # Ficha 3: Precio Escasez Superior
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-exclamation-triangle", style={'color': '#000000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                                html.Span("Escasez Superior", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                                html.Span(f"${precio_escasez_actual:.2f}", id='ficha-precio-escasez', style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                                html.Span("$/kWh", style={'color': '#666', 'fontSize': '0.65rem'})
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '4px'})
                        ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #fee2e2 0%, #fecaca 100%)', 'borderRadius': '6px'})
                    ], className="shadow-sm")
                ], lg=3, md=6, style={'marginBottom': '0'}),
                
                # Ficha 4: Spread de Escasez (NUEVA - información relevante)
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-exchange-alt", style={'color': '#000000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                                html.Span("Spread Escasez", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                                html.Span(f"${spread_escasez:.2f}", id='ficha-spread-escasez', style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                                html.Span("$/kWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '6px'}),
                                html.Button(
                                    "ℹ",
                                    id="btn-info-spread",
                                    style={
                                        'background': '#F2C330',
                                        'border': '2px solid #2C3E50',
                                        'borderRadius': '50%',
                                        'width': '22px',
                                        'height': '22px',
                                        'fontSize': '12px',
                                        'fontWeight': 'bold',
                                        'color': '#2C3E50',
                                        'cursor': 'pointer',
                                        'animation': 'pulse 2s ease-in-out infinite',
                                        'padding': '0',
                                        'display': 'inline-flex',
                                        'alignItems': 'center',
                                        'justifyContent': 'center'
                                    },
                                    n_clicks=0
                                )
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '4px'})
                        ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)', 'borderRadius': '6px'})
                    ], className="shadow-sm")
                ], lg=3, md=6, style={'marginBottom': '0'})
            ], className="mb-2"),
            
            # Gráfica principal
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("📊 Evolución de Precios", className="mb-0")),
                        dbc.CardBody([
                            dcc.Loading(
                                dcc.Graph(
                                    id='grafica-precios-comercializacion',
                                    figure=fig_precios,
                                    config={'displayModeBar': True, 'displaylogo': False}
                                )
                            )
                        ])
                    ], className="shadow-sm mb-4")
                ])
            ]),
            
            # Store para datos
            dcc.Store(id='store-comercializacion', data=None),
            
            # Modal para detalle horario
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle(id='modal-titulo-comercializacion')),
                dbc.ModalBody(id='modal-contenido-comercializacion'),
                dbc.ModalFooter(
                    dbc.Button("Cerrar", id='modal-cerrar-comercializacion', className="ms-auto")
                )
            ], id='modal-detalle-comercializacion', size='xl', is_open=False),
            
            # Modal de información Spread
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("Spread de Escasez")),
                dbc.ModalBody([
                    html.P("El Spread de Escasez representa la diferencia entre el Precio de Escasez Superior y el Precio de Escasez Inferior. Se calcula mediante la resta de ambos valores:", 
                           style={'marginBottom': '10px', 'color': '#2c3e50'}),
                    html.P([html.Strong("Spread = Precio Escasez Superior - Precio Escasez Inferior")], 
                           style={'marginBottom': '20px', 'marginLeft': '20px', 'color': '#1f2937'}),
                    
                    html.H6("Interpretación de valores:", style={'fontWeight': 'bold', 'color': '#2c3e50'}),
                    html.Ul([
                        html.Li([html.Strong("Alto (> $500/kWh): "), "Gran diferencia entre bandas. Indica mayor riesgo de escasez severa y alta volatilidad en el mercado eléctrico."]),
                        html.Li([html.Strong("Medio ($300-$500/kWh): "), "Rango normal de operación del sistema. El mercado opera dentro de parámetros esperados."]),
                        html.Li([html.Strong("Bajo (< $300/kWh): "), "Poca diferencia entre bandas. Menor probabilidad de escasez y mayor estabilidad del sistema."])
                    ], style={'marginBottom': '15px'}),
                    
                    html.H6("Importancia:", style={'fontWeight': 'bold', 'color': '#2c3e50'}),
                    html.Ul([
                        html.Li("Mide el rango de incertidumbre en los precios de escasez del mercado eléctrico."),
                        html.Li("Un spread amplio sugiere condiciones críticas que requieren mayor atención operativa."),
                        html.Li("Ayuda a anticipar necesidades de generación de respaldo y costos asociados.")
                    ])
                ], style={'fontSize': '0.95rem', 'lineHeight': '1.6'}),
                dbc.ModalFooter(
                    dbc.Button("Cerrar", id='modal-cerrar-spread', className="ms-auto")
                )
            ], id='modal-info-spread', size='lg', is_open=False)
            
        ], fluid=True, className="p-4")
        ])
    ])

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
     Output('ficha-precio-promedio', 'children'),
     Output('ficha-precio-max', 'children'),
     Output('ficha-precio-escasez', 'children'),
     Output('ficha-spread-escasez', 'children')],  # NUEVA ficha spread
    [Input('btn-actualizar-comercializacion', 'n_clicks'),
     Input('fecha-filtro-comercializacion', 'start_date'),
     Input('fecha-filtro-comercializacion', 'end_date')],
    prevent_initial_call='initial_duplicate'
)
def actualizar_datos_comercializacion(n_clicks, fecha_inicio_str, fecha_fin_str):
    """Callback para actualizar la gráfica y fichas según las fechas seleccionadas"""
    
    px, go = get_plotly_modules()
    
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
            return fig_error, None, "$0.00", "$0.00", "$0.00", "$0.00"
        
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
        # Para bolsa, guardar también los datos horarios por separado
        bolsa_json = None
        datos_horarios = {}
        
        if not df_bolsa.empty:
            # Extraer y guardar datos horarios antes de serializar
            if 'Datos_Horarios' in df_bolsa.columns:
                for idx, row in df_bolsa.iterrows():
                    fecha_str = row['Date'].strftime('%Y-%m-%d')
                    datos_horarios[fecha_str] = row['Datos_Horarios']
                # Remover columna de objetos para poder serializar
                df_bolsa_sin_horarios = df_bolsa.drop(columns=['Datos_Horarios'])
                bolsa_json = df_bolsa_sin_horarios.to_json(date_format='iso', orient='split')
            else:
                bolsa_json = df_bolsa.to_json(date_format='iso', orient='split')
        
        store_data = {
            'bolsa': bolsa_json,
            'escasez': df_escasez.to_json(date_format='iso', orient='split') if not df_escasez.empty else None,
            'escasez_act': df_escasez_act.to_json(date_format='iso', orient='split') if not df_escasez_act.empty else None,
            'escasez_sup': df_escasez_sup.to_json(date_format='iso', orient='split') if not df_escasez_sup.empty else None,
            'escasez_inf': df_escasez_inf.to_json(date_format='iso', orient='split') if not df_escasez_inf.empty else None,
            'datos_horarios': datos_horarios  # Guardar datos horarios por separado
        }
        
        return (
            fig, 
            store_data,
            f"${precio_promedio:.2f}",
            f"${precio_max:.2f}",
            f"${precio_escasez:.2f}",
            f"${spread_escasez:.2f}"  # NUEVO: valor spread
        )
        
    except Exception as e:
        logger.error(f"Error en actualizar_datos_comercializacion: {e}")
        traceback.print_exc()
        
        fig_error = go.Figure().add_annotation(
            text=f"Error al cargar datos: {str(e)[:100]}",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="red")
        )
        
        return fig_error, None, "$0.00", "$0.00", "$0.00", "$0.00"

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
    
    if not ctx.triggered:
        return False, "", ""
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Cerrar modal
    if trigger_id == 'modal-cerrar-comercializacion':
        return False, "", ""
    
    # Abrir modal con datos
    if trigger_id == 'grafica-precios-comercializacion' and clickData:
        try:
            # Extraer información del click
            punto = clickData['points'][0]
            fecha_click = pd.to_datetime(punto['x']).date()
            metrica = punto['data']['name']
            
            # Solo mostrar detalle horario para Precio Bolsa Nacional
            if metrica != 'Precio Bolsa Nacional':
                return False, "", ""
            
            if not store_data or not store_data.get('datos_horarios'):
                return False, "", ""
            
            # Buscar datos horarios para esa fecha
            fecha_str = fecha_click.strftime('%Y-%m-%d')
            datos_horarios = store_data['datos_horarios'].get(fecha_str)
            
            if not datos_horarios:
                return True, f"Detalle del {fecha_click}", html.Div(
                    "No hay datos horarios disponibles para esta fecha",
                    className="alert alert-warning"
                )
            
            tabla = crear_tabla_horaria(datos_horarios, fecha_click)
            
            titulo = f"📊 Detalle Horario - Precio Bolsa Nacional - {fecha_click}"
            
            return True, titulo, tabla
            
        except Exception as e:
            logger.error(f"Error mostrando detalle: {e}")
            traceback.print_exc()
            return True, "Error", html.Div(
                f"Error al cargar datos: {str(e)}",
                className="alert alert-danger"
            )
    
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

