"""
Tablero de Transmisión - Sistema de Transmisión Nacional (STN)
Autor: Dashboard MME
Fecha: 2025-12-10

DATOS REALES DE TRANSMISIÓN:
- Dataset SIMEN 7538fd: Parámetros técnicos de líneas de transmisión
- 857 líneas únicas, 29 críticas (>0.5% del sistema)
- 34 operadores
- Niveles de tensión: 57.5, 66, 110, 115, 138, 220, 230, 500 kV
- Longitud total: 30,946 km
- Sistemas: STN (Nacional) y STR (Regional)
"""

def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

from dash import dcc, html, Input, Output, State, callback, dash_table, register_page
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import datetime, timedelta, date
import numpy as np

# Importar navbar y componentes de filtro
from interface.components.layout import crear_navbar_horizontal, crear_filtro_fechas_compacto, registrar_callback_filtro_fechas
from domain.services.transmission_service import TransmissionService

# Registrar página
register_page(
    __name__,
    path="/transmision",
    name="Transmisión",
    title="Transmisión - Ministerio de Minas y Energía de Colombia",
    order=20
)

# ================================================================================
# FUNCIONES AUXILIARES
# ================================================================================

# Instancia del servicio
transmission_service = TransmissionService()

def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

# ================================================================================
# FUNCIONES DE CARGA DE DATOS
# ================================================================================

def cargar_datos_lineas():
    """
    Carga datos desde la base de datos usando el servicio
    Sigue el patrón estándar: DB First
    """
    import logging
    _logger = logging.getLogger(__name__)
    
    try:
        _logger.info("⚡ Iniciando carga de datos de transmisión...")
        df = transmission_service.get_transmission_lines()
        
        if df.empty:
            _logger.warning("⚠️ Transmisión: El servicio retornó DataFrame vacío")
            return pd.DataFrame() # No data

        _logger.info(f"✅ Transmisión: Datos cargados. Filas: {len(df)}. Columnas: {df.columns.tolist()}")
        return df
        
    except Exception as e:
        _logger.error(f"❌ Error CRÍTICO cargando datos transmisión: {e}", exc_info=True)
        return pd.DataFrame()

# ================================================================================
# FUNCIONES DE VISUALIZACIÓN
# ================================================================================

def crear_kpis_transmision(df_lineas):
    """Crear KPIs principales incluyendo distribución de criticidad"""
    if df_lineas.empty:
        return html.Div("No hay datos disponibles", className="alert alert-warning")
    
    df_reciente = df_lineas[df_lineas['Fecha'] == df_lineas['Fecha'].max()].copy()
    
    # Calcular KPIs básicos
    total_lineas = df_reciente['CodigoLinea'].nunique()
    longitud_total = df_reciente['LongitudTotal'].iloc[0] if len(df_reciente) > 0 else 0
    
    # Contar por nivel de criticidad
    criticas = len(df_reciente[df_reciente['ParticipacionLineaTotal'] > 0.008])
    importantes = len(df_reciente[(df_reciente['ParticipacionLineaTotal'] > 0.005) & (df_reciente['ParticipacionLineaTotal'] <= 0.008)])
    normales = len(df_reciente[df_reciente['ParticipacionLineaTotal'] <= 0.005])
    
    # Antigüedad promedio
    df_reciente['Antiguedad'] = (pd.Timestamp.now() - df_reciente['FPO']).dt.days / 365.25
    antiguedad_promedio = df_reciente['Antiguedad'].mean()
    
    kpis = dbc.Row([
        # Total de líneas
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-project-diagram", style={'color': '#000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                        html.Span("Total Líneas", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                        html.Span(f"{total_lineas:,}", style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000', 'marginRight': '5px'}),
                        html.Span("activas", style={'color': '#666', 'fontSize': '0.65rem'})
                    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '2px'})
                ], style={'padding': '0.4rem 0.8rem'})
            ], className="shadow-sm")
        ], lg=2, md=6, style={'marginBottom': '0'}),
        
        # Longitud total
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-ruler-horizontal", style={'color': '#000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                        html.Span("Longitud Total", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                        html.Span(f"{longitud_total:,.0f}", style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000', 'marginRight': '5px'}),
                        html.Span("km", style={'color': '#666', 'fontSize': '0.65rem'})
                    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '2px'})
                ], style={'padding': '0.4rem 0.8rem'})
            ], className="shadow-sm")
        ], lg=2, md=6, style={'marginBottom': '0'}),
        
        # Críticas
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-exclamation-circle", style={'color': '#dc2626', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                        html.Span("Críticas", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                        html.Span(f"{criticas}", style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#dc2626', 'marginRight': '5px'}),
                        html.Span(">0.8%", style={'color': '#666', 'fontSize': '0.65rem'})
                    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '2px'})
                ], style={'padding': '0.4rem 0.8rem'})
            ], className="shadow-sm")
        ], lg=2, md=4, style={'marginBottom': '0'}),
        
        # Importantes
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-exclamation-triangle", style={'color': '#f59e0b', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                        html.Span("Importantes", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                        html.Span(f"{importantes}", style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#f59e0b', 'marginRight': '5px'}),
                        html.Span("0.5-0.8%", style={'color': '#666', 'fontSize': '0.65rem'})
                    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '2px'})
                ], style={'padding': '0.4rem 0.8rem'})
            ], className="shadow-sm")
        ], lg=2, md=4, style={'marginBottom': '0'}),
        
        # Normales
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-check-circle", style={'color': '#10b981', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                        html.Span("Normales", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                        html.Span(f"{normales}", style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#10b981', 'marginRight': '5px'}),
                        html.Span("<0.5%", style={'color': '#666', 'fontSize': '0.65rem'})
                    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '2px'})
                ], style={'padding': '0.4rem 0.8rem'})
            ], className="shadow-sm")
        ], lg=2, md=4, style={'marginBottom': '0'}),
        
        # Antigüedad promedio
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-clock", style={'color': '#000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                        html.Span("Antigüedad", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                        html.Span(f"{antiguedad_promedio:.0f}", style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000', 'marginRight': '5px'}),
                        html.Span("años", style={'color': '#666', 'fontSize': '0.65rem'})
                    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '2px'})
                ], style={'padding': '0.4rem 0.8rem'})
            ], className="shadow-sm")
        ], lg=2, md=12, style={'marginBottom': '0'}),
    ])
    
    return kpis

def crear_tabla_lineas_criticas(df_lineas):
    """Tabla con TODAS las líneas del sistema ordenadas por criticidad - Compacta"""
    if df_lineas.empty:
        return html.Div("No hay datos disponibles")
    
    df_reciente = df_lineas[df_lineas['Fecha'] == df_lineas['Fecha'].max()].copy()
    
    # TODAS las líneas ordenadas por participación total (de mayor a menor)
    top_criticas = df_reciente.sort_values('ParticipacionLineaTotal', ascending=False)[
        ['NombreLinea', 'Tension', 'Longitud', 'Sistema', 'ParticipacionLineaTotal', 'ParticipacionLineaNivelTension', 'FPO', 'CodigoOperador']
    ].copy()
    
    # Calcular antigüedad
    top_criticas['Antiguedad'] = ((pd.Timestamp.now() - top_criticas['FPO']).dt.days / 365.25).round(0).astype(int)
    top_criticas['Part_%'] = (top_criticas['ParticipacionLineaTotal'] * 100).round(3)
    top_criticas['PartNivel_%'] = (top_criticas['ParticipacionLineaNivelTension'] * 100).round(2)
    top_criticas['Longitud'] = top_criticas['Longitud'].round(1)
    top_criticas['Tension'] = top_criticas['Tension'].astype(str) + ' kV'
    
    # Clasificar criticidad
    top_criticas['Nivel'] = top_criticas['Part_%'].apply(
        lambda x: '🔴 Crítica' if x >= 0.8 else '🟡 Importante' if x >= 0.5 else '🟢 Normal'
    )
    
    # Seleccionar columnas finales
    tabla_data = top_criticas[['Nivel', 'NombreLinea', 'Tension', 'Longitud', 'Part_%', 'PartNivel_%', 'Antiguedad', 'Sistema', 'CodigoOperador']].copy()
    tabla_data.columns = ['Criticidad', 'Línea', 'Tensión', 'km', 'Sist.%', 'Nivel%', 'Años', 'Sistema', 'Operador']
    
    # AGREGAR FILA DE TOTALES CON TODOS LOS VALORES
    num_tensiones = tabla_data['Tensión'].nunique()
    num_sistemas = tabla_data['Sistema'].nunique()
    num_operadores = tabla_data['Operador'].nunique()
    
    total_row = {
        'Criticidad': '📊 TOTAL',
        'Línea': f'{len(tabla_data)} líneas',
        'Tensión': f'{num_tensiones} niveles',
        'km': tabla_data['km'].sum().round(1),
        'Sist.%': tabla_data['Sist.%'].sum().round(2),
        'Nivel%': tabla_data['Nivel%'].sum().round(2),
        'Años': int(tabla_data['Años'].mean()),
        'Sistema': f'{num_sistemas} tipos',
        'Operador': f'{num_operadores} oper.'
    }
    tabla_data = pd.concat([tabla_data, pd.DataFrame([total_row])], ignore_index=True)
    
    # Crear tabla compacta con estilos forzados
    tabla = dash_table.DataTable(
        data=tabla_data.to_dict('records'),
        columns=[{"name": i, "id": i} for i in tabla_data.columns],
        style_table={'overflowX': 'auto', 'overflowY': 'auto', 'maxHeight': '320px'},
        style_cell={
            'textAlign': 'left', 
            'fontFamily': 'Arial, sans-serif', 
            'whiteSpace': 'normal',
            'fontSize': '9px',
            'padding': '3px 4px',
            'lineHeight': '1.3',
            'maxWidth': '120px',
            'minWidth': '40px'
        },
        style_header={
            'backgroundColor': '#f8f9fa', 
            'position': 'sticky', 
            'top': 0, 
            'zIndex': 1,
            'fontSize': '7px',
            'padding': '2px 3px',
            'fontWeight': '600',
            'lineHeight': '1.3'
        },
        style_data={
            'fontSize': '9px',
            'padding': '3px 4px',
            'lineHeight': '1.3'
        },
        style_data_conditional=[
            {'if': {'filter_query': '{Criticidad} contains "🔴"'}, 
             'backgroundColor': '#fee2e215', 'borderLeft': '3px solid #dc2626'},
            {'if': {'filter_query': '{Criticidad} contains "🟡"'}, 
             'backgroundColor': '#fef3c715', 'borderLeft': '3px solid #f59e0b'},
            {'if': {'filter_query': '{Criticidad} contains "TOTAL"'}, 
             'backgroundColor': '#dbeafe', 'fontWeight': 'bold', 'borderTop': '2px solid #2563eb'},
            {'if': {'row_index': 'odd'}, 'backgroundColor': '#fafafa'}
        ],
        page_size=15,
        sort_action='native',
        style_as_list_view=True
    )
    
    return html.Div([
        html.H6(f"Todas las Líneas ({len(tabla_data)})", style={'marginBottom': '6px'}),
        tabla
    ])

def crear_grafica_criticidad_vs_antiguedad(df_lineas):
    """Scatter plot con hover - SIN zoom CSS para mapeo correcto"""
    # Obtener módulos plotly
    px, go = get_plotly_modules()
    
    if df_lineas.empty:
        return go.Figure()
    
    df_reciente = df_lineas[df_lineas['Fecha'] == df_lineas['Fecha'].max()].copy()
    
    # Calcular antigüedad
    df_reciente['Antiguedad'] = (pd.Timestamp.now() - df_reciente['FPO']).dt.days / 365.25
    df_reciente['Part_%'] = df_reciente['ParticipacionLineaTotal'] * 100
    df_reciente['PartNivel_%'] = df_reciente['ParticipacionLineaNivelTension'] * 100
    
    # Clasificar por criticidad
    df_reciente['Categoria'] = df_reciente['Part_%'].apply(
        lambda x: 'Crítica (>0.8%)' if x >= 0.8 else 'Importante (0.5-0.8%)' if x >= 0.5 else 'Normal (<0.5%)'
    )
    
    # Mostrar todas las líneas sin filtrar por participación mínima
    # Esto permite visualizar líneas nuevas que aun tienen baja carga
    df_plot = df_reciente.copy()
    
    # Crear figura
    fig = go.Figure()
    
    # Colores por categoría
    colores = {
        'Crítica (>0.8%)': '#dc2626',
        'Importante (0.5-0.8%)': '#f59e0b',
        'Normal (<0.5%)': '#10b981'
    }
    
    # Agregar scatter por categoría
    for categoria in ['Crítica (>0.8%)', 'Importante (0.5-0.8%)', 'Normal (<0.5%)']:
        df_cat = df_plot[df_plot['Categoria'] == categoria]
        
        if len(df_cat) > 0:
            fig.add_trace(go.Scatter(
                x=df_cat['Antiguedad'],
                y=df_cat['Part_%'],
                mode='markers',
                name=categoria,
                marker=dict(size=12, color=colores[categoria], opacity=0.7),
                text=df_cat['NombreLinea'],
                customdata=df_cat[['Tension', 'Longitud', 'Sistema', 'CodigoOperador', 'PartNivel_%']],
                hovertemplate=(
                    '<b>%{text}</b><br><br>'
                    'Tensión: %{customdata[0]:.0f} kV<br>'
                    'Longitud: %{customdata[1]:.1f} km<br>'
                    'Antigüedad: %{x:.0f} años<br>'
                    'Part. Total: %{y:.3f}%<br>'
                    'Part. Nivel: %{customdata[4]:.2f}%<br>'
                    'Sistema: %{customdata[2]}<br>'
                    'Operador: %{customdata[3]}<extra></extra>'
                )
            ))
    
    # Líneas de referencia
    fig.add_hline(y=0.8, line_dash="dash", line_color="#dc2626", 
                  annotation_text="Crítica", annotation_position="right")
    fig.add_hline(y=0.5, line_dash="dash", line_color="#f59e0b",
                  annotation_text="Importante", annotation_position="right")
    
    # Layout compacto
    fig.update_layout(
        height=320,
        xaxis_title='Antigüedad (años)',
        yaxis_title='% del Sistema Total',
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5, font=dict(size=9)),
        margin=dict(l=50, r=15, t=15, b=50),
        hovermode='closest',
        plot_bgcolor='white',
        paper_bgcolor='white'
    )
    
    return fig

def crear_grafica_participacion_voltaje(df_lineas):
    """Gráfica de participación promedio por voltaje"""
    # Obtener módulos plotly
    px, go = get_plotly_modules()

    if df_lineas.empty:
        return go.Figure()
    
    df_reciente = df_lineas[df_lineas['Fecha'] == df_lineas['Fecha'].max()].copy()
    
    # Promedio por voltaje
    participacion = df_reciente.groupby('Tension').agg({
        'ParticipacionLineaTotal': 'mean',
        'Longitud': 'mean',
        'CodigoLinea': 'count'
    }).reset_index()
    
    participacion['Part_%'] = (participacion['ParticipacionLineaTotal'] * 100).round(3)
    participacion['TensionStr'] = participacion['Tension'].astype(str) + ' kV'
    participacion = participacion.sort_values('Tension')
    
    fig = go.Figure(data=[
        go.Bar(
            x=participacion['TensionStr'],
            y=participacion['Part_%'],
            marker_color='#2563eb',
            text=participacion['Part_%'].round(2),
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>' +
                         'Participación promedio: %{y:.3f}%<br>' +
                         '<extra></extra>'
        )
    ])
    
    fig.update_layout(
        title='Participación Promedio por Nivel de Tensión',
        xaxis_title='Nivel de Tensión',
        yaxis_title='% Promedio del Sistema',
        height=280,
        showlegend=False,
        xaxis_tickangle=-45,
        margin=dict(l=50, r=20, t=40, b=60),
        font=dict(size=10)
    )
    
    return fig

def crear_grafica_antiguedad_decadas(df_lineas):
    """Gráfica de líneas por década de construcción"""
    # Obtener módulos plotly
    px, go = get_plotly_modules()

    if df_lineas.empty:
        return go.Figure()
    
    df_reciente = df_lineas[df_lineas['Fecha'] == df_lineas['Fecha'].max()].copy()
    
    # Agrupar por década
    df_reciente['Decada'] = (df_reciente['FPO'].dt.year // 10) * 10
    decadas = df_reciente.groupby('Decada').agg({
        'CodigoLinea': 'count',
        'Longitud': 'sum'
    }).reset_index()
    decadas.columns = ['Decada', 'Cantidad', 'Longitud_km']
    decadas = decadas.sort_values('Decada')
    decadas['DecadaStr'] = decadas['Decada'].astype(int).astype(str) + 's'
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name='Cantidad de Líneas',
        x=decadas['DecadaStr'],
        y=decadas['Cantidad'],
        yaxis='y',
        marker_color='#3b82f6',
        text=decadas['Cantidad'],
        textposition='outside'
    ))
    
    fig.add_trace(go.Scatter(
        name='Longitud Total (km)',
        x=decadas['DecadaStr'],
        y=decadas['Longitud_km'],
        yaxis='y2',
        mode='lines+markers',
        marker_color='#ef4444',
        line=dict(width=2)
    ))
    
    fig.update_layout(
        title='Evolución de Construcción de Líneas por Década',
        xaxis=dict(title='Década'),
        yaxis=dict(title='Cantidad de Líneas', side='left'),
        yaxis2=dict(title='Longitud Total (km)', overlaying='y', side='right'),
        height=280,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode='x unified'
    )
    
    return fig

# ================================================================================
# LAYOUT
# ================================================================================

def layout():
    """Layout de la página de Transmisión"""
    
    # Obtener módulos plotly
    px, go = get_plotly_modules()
    
    # Opciones de Tensión
    opciones_tension = [
        {'label': 'Todas las tensiones', 'value': 'TODAS'},
        {'label': '500 kV (Alta Potencia)', 'value': 500},
        {'label': '230 kV', 'value': 230},
        {'label': '220 kV', 'value': 220},
        {'label': '115 kV', 'value': 115},
        {'label': '110 kV', 'value': 110},
        {'label': '66 kV', 'value': 66},
        {'label': '57.5 kV', 'value': 57.5}
    ]

    return html.Div([
        # Navbar horizontal
        # crear_navbar_horizontal(),
        
        # Store para trigger automático de carga inicial
        dcc.Store(id='transmision-data-trigger', data={'initialized': False}),
        
        # Contenedor principal
        dbc.Container([
            
            # --- PANEL DE FILTROS AVANZADO ---
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        # Columna 1: Rango Predefinido (Estilo Hidrología)
                        dbc.Col([
                            html.Label("PERIODO DE CONSTRUCCIÓN:", className="fw-bold small text-muted mb-1"),
                            dcc.Dropdown(
                                id='dropdown-rango-transmision',
                                options=[
                                    {'label': 'Inventario Completo (Todo)', 'value': 'todo'},
                                    {'label': 'Último Año (Nuevas)', 'value': '1y'},
                                    {'label': 'Últimos 5 años (Expansión)', 'value': '5y'},
                                    {'label': 'Últimos 10 años', 'value': '10y'},
                                    {'label': 'Líneas Antiguas (>20 años)', 'value': 'old'},
                                    {'label': 'Personalizado', 'value': 'custom'}
                                ],
                                value='todo',
                                clearable=False,
                                className="mb-0",
                                style={'fontSize': '0.85rem'}
                            )
                        ], lg=3, md=6, className="mb-2"),
                        
                        # Columna 2: Selector de Fechas (DatePicker)
                        dbc.Col([
                            html.Label("RANGO DE FECHAS (FPO):", className="fw-bold small text-muted mb-1"),
                            html.Div([
                                dcc.DatePickerRange(
                                    id='fecha-filtro-transmision',
                                    display_format='YYYY-MM-DD',
                                    style={'fontSize': '0.8rem', 'width': '100%'}
                                )
                            ])
                        ], lg=3, md=6, className="mb-2"),
                        
                        # Columna 3: Filtro Técnico (Tensión)
                        dbc.Col([
                            html.Label("NIVEL DE TENSIÓN:", className="fw-bold small text-muted mb-1"),
                            dcc.Dropdown(
                                id='dropdown-tension-transmision',
                                options=opciones_tension,
                                value='TODAS',
                                clearable=False,
                                className="mb-0",
                                style={'fontSize': '0.85rem'}
                            )
                        ], lg=3, md=6, className="mb-2"),
                        
                        # Columna 4: Botón Consultar
                        dbc.Col([
                            html.Label("ACCIÓN:", className="fw-bold small text-muted mb-1"),
                            dbc.Button([
                                html.I(className="fas fa-search me-2"), 
                                "Consultar Datos"
                            ], 
                            id="btn-actualizar-transmision", 
                            color="primary", 
                            className="w-100 shadow-sm")
                        ], lg=3, md=6, className="d-flex align-items-end mb-2")
                    ])
                ], style={'padding': '0.8rem'})
            ], className="mb-4 shadow-sm border-0", style={'backgroundColor': '#ffffff'}),
        
            # KPIs
            html.Div(id="kpis-transmision", style={'marginBottom': '0'}),
        
            # Sección principal: Gráfica + Tabla lado a lado
            html.Div([
        html.H6([
            html.I(className="fas fa-chart-scatter me-2", style={'fontSize': '0.85rem'}),
            "Análisis de Criticidad por Antigüedad"
        ], className="mt-2 mb-2", style={'fontSize': '0.9rem'}),
        
        dbc.Row([
            # Columna 1: Gráfica criticidad vs antigüedad (izquierda ~40%)
            dbc.Col([
                dcc.Graph(id="grafica-criticidad-antiguedad")
            ], lg=5, md=12),
            
            # Columna 2: Tabla de líneas (centro ~30%)
            dbc.Col([
                html.Div(id="tabla-lineas-criticas")
            ], lg=3, md=12),
            
            # Columna 3: Gráficas apiladas verticalmente (derecha ~30%)
            dbc.Col([
                # Participación por voltaje (arriba)
                dcc.Graph(id="grafica-participacion-voltaje", style={'marginBottom': '10px'}),
                
                # Líneas por década (abajo)
                dcc.Graph(id="grafica-antiguedad-decadas")
            ], lg=4, md=12)
        ], className="mb-2")
            ], style={'marginTop': '0'})
        
        ], fluid=True, style={'maxWidth': '100%', 'padding': '5px'})
    ], style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh'})

# ================================================================================
# CALLBACKS
# ================================================================================

# Registrar callback del filtro de fechas
registrar_callback_filtro_fechas('transmision')

@callback(
    [Output('fecha-filtro-transmision', 'start_date'),
     Output('fecha-filtro-transmision', 'end_date')],
    Input('dropdown-rango-transmision', 'value')
)
def actualizar_fechas_filtro(rango):
    """Actualiza las fechas del datepicker según el rango seleccionado"""
    hoy = date.today()
    
    if rango == 'todo':
        return date(1950, 1, 1), hoy
    elif rango == '1y':
        return hoy - timedelta(days=365), hoy
    elif rango == '5y':
        return hoy - timedelta(days=365*5), hoy
    elif rango == '10y':
        return hoy - timedelta(days=365*10), hoy
    elif rango == 'old':
        return date(1900, 1, 1), hoy - timedelta(days=365*20)
    
    return dash.no_update, dash.no_update

@callback(
    Output('transmision-data-trigger', 'data'),
    Input('transmision-data-trigger', 'data')
)
def inicializar_transmision(data):
    """Callback de inicialización que se ejecuta automáticamente al cargar la página"""
    if data is None or not data.get('initialized', False):
        return {'initialized': True, 'timestamp': datetime.now().isoformat()}
    return data

@callback(
    [
        Output('kpis-transmision', 'children'),
        Output('grafica-criticidad-antiguedad', 'figure'),
        Output('grafica-participacion-voltaje', 'figure'),
        Output('grafica-antiguedad-decadas', 'figure'),
        Output('tabla-lineas-criticas', 'children'),
        Output('store-datos-chatbot-generacion', 'data', allow_duplicate=True)
    ],
    [Input('transmision-data-trigger', 'data'),
     Input('btn-actualizar-transmision', 'n_clicks')],
    [State('fecha-filtro-transmision', 'start_date'),
     State('fecha-filtro-transmision', 'end_date'),
     State('dropdown-tension-transmision', 'value')],
    prevent_initial_call='initial_duplicate'
)
def actualizar_tablero_transmision(trigger_data, n_clicks, fecha_inicio, fecha_fin, tension_filtro):
    """Actualizar todo el tablero de transmisión"""
    
    # Obtener módulos plotly
    px, go = get_plotly_modules()
    
    try:
        # Cargar datos de líneas
        df_raw = cargar_datos_lineas()

        # Validación robusta de tipos
        if df_raw is None:
            df_lineas = pd.DataFrame()
        elif isinstance(df_raw, list):
            df_lineas = pd.DataFrame(df_raw)
        elif isinstance(df_raw, pd.DataFrame):
            df_lineas = df_raw
        else:
            df_lineas = pd.DataFrame()
        
        if df_lineas.empty:
            mensaje_error = html.Div(
                "No hay datos de transmisión recientes en la base de datos. Por favor ejecute el ETL ('python3 etl/etl_transmision.py').", 
                className="alert alert-warning"
            )
            datos_error = {'pagina': 'transmision', 'error': 'Sin datos en BD'}
            return mensaje_error, go.Figure(), go.Figure(), go.Figure(), html.Div(), datos_error
        
        # --- CONVERSIÓN DE TIPOS CRÍTICA ---
        # SQLite devuelve fechas como strings, pandas no las convierte automáticamente en read_sql_query
        if 'Fecha' in df_lineas.columns:
            df_lineas['Fecha'] = pd.to_datetime(df_lineas['Fecha'])
        
        if 'FPO' in df_lineas.columns:
            df_lineas['FPO'] = pd.to_datetime(df_lineas['FPO'], errors='coerce')
        
        # Convertir columnas numéricas que podrían ser strings
        cols_num = ['ParticipacionLineaTotal', 'ParticipacionLineaNivelTension', 'Longitud', 'Tension']
        for col in cols_num:
            if col in df_lineas.columns:
                df_lineas[col] = pd.to_numeric(df_lineas[col], errors='coerce')
        # -----------------------------------
        
        # --- APLICAR FILTROS ---
        
        # 1. Filtro por Tensión
        if tension_filtro and tension_filtro != 'TODAS':
            try:
                tension_val = float(tension_filtro)
                df_lineas = df_lineas[df_lineas['Tension'] == tension_val]
            except ValueError:
                pass

        # 2. Filtro por Fecha (FPO)
        if fecha_inicio and fecha_fin:
            try:
                fecha_ini_dt = pd.to_datetime(fecha_inicio)
                fecha_fin_dt = pd.to_datetime(fecha_fin)
                
                # Para Transmisión, filtramos por FECHA DE PUBLICACIÓN OPERACIÓN (FPO)
                # Solo si el usuario NO seleccionó "todo" (que enviamos como 1950)
                # Pero en realidad, la lógica es simple: filtrar FPO entre las fechas dadas.
                
                if 'FPO' in df_lineas.columns:
                    mask = (df_lineas['FPO'] >= fecha_ini_dt) & (df_lineas['FPO'] <= fecha_fin_dt)
                    df_filtrado = df_lineas[mask]
                    
                    if not df_filtrado.empty:
                        df_lineas = df_filtrado
                    else:
                        pass
                        # Opcional: mostrar mensaje en UI
            except Exception as e:
                pass
        
        
        # Generar componentes

        kpis = crear_kpis_transmision(df_lineas)
        
        fig_criticidad = crear_grafica_criticidad_vs_antiguedad(df_lineas)
        
        fig_participacion = crear_grafica_participacion_voltaje(df_lineas)
        
        fig_decadas = crear_grafica_antiguedad_decadas(df_lineas)
        
        tabla = crear_tabla_lineas_criticas(df_lineas)
        
        # Preparar datos para chatbot
        datos_chatbot = {
            'pagina': 'transmision',
            'timestamp': pd.Timestamp.now().isoformat(),
            'total_lineas': len(df_lineas),
            'lineas_criticas': len(df_lineas[df_lineas['Criticidad'] == 'Crítica']) if 'Criticidad' in df_lineas.columns else 0,
            'antiguedad_promedio': df_lineas['Años_Operacion'].mean() if 'Años_Operacion' in df_lineas.columns else 0
        }
        
        return kpis, fig_criticidad, fig_participacion, fig_decadas, tabla, datos_chatbot
        
    except Exception as e:
        traceback.print_exc()
        mensaje_error = html.Div(f"Error: {str(e)}", className="alert alert-danger")
        datos_error = {'pagina': 'transmision', 'error': str(e)}
        return mensaje_error, go.Figure(), go.Figure(), go.Figure(), html.Div(), datos_error
