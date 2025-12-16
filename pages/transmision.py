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

import dash
from dash import dcc, html, Input, Output, State, callback, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# Importar navbar y componentes de filtro
from utils.components import crear_navbar_horizontal, crear_filtro_fechas_compacto, registrar_callback_filtro_fechas

# ================================================================================
# FUNCIONES AUXILIARES
# ================================================================================

def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

# ================================================================================
# FUNCIONES DE CARGA DE DATOS
# ================================================================================

def cargar_datos_lineas():
    """Cargar datos de líneas de transmisión desde CSV"""
    try:
        df = pd.read_csv('/home/admonctrlxm/server/data/lineas_transmision_simen.csv')
        df['Fecha'] = pd.to_datetime(df['Fecha'])
        df['FechaPublicacion'] = pd.to_datetime(df['FechaPublicacion'])
        df['FPO'] = pd.to_datetime(df['FPO'])
        return df
    except Exception as e:
        print(f"❌ Error cargando datos de líneas: {e}")
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
    
    # Filtrar solo líneas importantes
    df_plot = df_reciente[df_reciente['Part_%'] >= 0.3].copy()
    
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

layout = html.Div([
    # Navbar horizontal
    crear_navbar_horizontal(),
    
    # Contenedor principal
    dbc.Container([
    # Filtro de fechas compacto
    crear_filtro_fechas_compacto('transmision'),
    
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
    [
        Output('kpis-transmision', 'children'),
        Output('grafica-criticidad-antiguedad', 'figure'),
        Output('grafica-participacion-voltaje', 'figure'),
        Output('grafica-antiguedad-decadas', 'figure'),
        Output('tabla-lineas-criticas', 'children')
    ],
    [Input('btn-actualizar-transmision', 'n_clicks'),
     Input('fecha-inicio-transmision', 'date'),
     Input('fecha-fin-transmision', 'date')],
    prevent_initial_call=False
)
def actualizar_tablero_transmision(n_clicks, fecha_inicio, fecha_fin):
    """Actualizar todo el tablero de transmisión"""
    
    try:
        # Cargar datos de líneas
        df_lineas = cargar_datos_lineas()
        
        if df_lineas.empty:
            print("⚠️ DataFrame vacío en transmision.py")
            mensaje_error = html.Div("No hay datos disponibles. Verifica que exista el archivo CSV.", className="alert alert-danger")
            return mensaje_error, go.Figure(), go.Figure(), go.Figure(), html.Div()
        
        # Filtrar por año de construcción (FPO) si se proporcionan fechas
        if fecha_inicio and fecha_fin:
            fecha_ini = pd.to_datetime(fecha_inicio)
            fecha_fin_dt = pd.to_datetime(fecha_fin)
            # Filtrar líneas cuya Fecha de Puesta en Operación esté en el rango
            df_lineas = df_lineas[(df_lineas['FPO'] >= fecha_ini) & (df_lineas['FPO'] <= fecha_fin_dt)]
            print(f"✅ Datos filtrados por año de construcción (FPO): {len(df_lineas)} líneas construidas entre {fecha_inicio} y {fecha_fin}")
        else:
            print(f"✅ Datos cargados en transmision.py: {len(df_lineas)} registros")
        
        # Generar componentes
        kpis = crear_kpis_transmision(df_lineas)
        print(f"✅ KPIs creados")
        
        fig_criticidad = crear_grafica_criticidad_vs_antiguedad(df_lineas)
        print(f"✅ Gráfica criticidad creada con {len(fig_criticidad.data)} traces")
        
        fig_participacion = crear_grafica_participacion_voltaje(df_lineas)
        print(f"✅ Gráfica participación creada")
        
        fig_decadas = crear_grafica_antiguedad_decadas(df_lineas)
        print(f"✅ Gráfica décadas creada")
        
        tabla = crear_tabla_lineas_criticas(df_lineas)
        print(f"✅ Tabla creada")
        
        return kpis, fig_criticidad, fig_participacion, fig_decadas, tabla
        
    except Exception as e:
        print(f"❌ ERROR en callback transmision: {e}")
        import traceback
        traceback.print_exc()
        mensaje_error = html.Div(f"Error: {str(e)}", className="alert alert-danger")
        return mensaje_error, go.Figure(), go.Figure(), go.Figure(), html.Div()

# Registro de página
dash.register_page(__name__, path='/transmision', name='Transmisión', icon='fa-bolt')
