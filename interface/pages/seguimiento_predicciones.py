"""
PÁGINA: SEGUIMIENTO DE PREDICCIONES ML
=======================================
Análisis exhaustivo de todas las proyecciones del sistema predictivo:
- 13 métricas con modelos ML (Prophet, LightGBM, Ensemble, RandomForest, ARIMA)
- Comparación día a día: predicho vs real
- KPIs de error (MAPE, RMSE) por métrica y modelo
- Historial de calidad ex-post
- Gráficas de dispersión, series temporales y heatmaps de error

Tablas PostgreSQL consultadas:
  predictions               — pronósticos vigentes
  metrics / catalogos       — datos reales XM
  predictions_quality_history — evaluaciones ex-post semanales

Autor: Arquitectura Dashboard MME
Fecha: 1 de marzo de 2026
"""

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════

def get_plotly_modules():
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

from dash import dcc, html, Input, Output, State, callback, register_page, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

from interface.components.layout import crear_navbar_horizontal, crear_boton_regresar
from interface.components.chart_card import crear_page_header, crear_filter_bar
from infrastructure.database.repositories.predictions_repository import PredictionsRepository

logger = logging.getLogger("seguimiento_predicciones")

# ═══════════════════════════════════════════════════════════════════════════════
# REGISTER PAGE
# ═══════════════════════════════════════════════════════════════════════════════

register_page(
    __name__,
    path="/seguimiento-predicciones",
    name="Seguimiento Predicciones",
    title="Seguimiento de Predicciones ML — MME",
    order=10,
)

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES Y MAPEO
# ═══════════════════════════════════════════════════════════════════════════════

# Mapeo fuente (predictions) → query de datos reales (metrics)
FUENTES_MAPPING = {
    'GENE_TOTAL':       {'metrica': 'Gene',            'agg': 'SUM', 'entidad': 'Sistema', 'unidad': 'GWh',  'label': 'Generación Total'},
    'DEMANDA':          {'metrica': 'DemaReal',         'agg': 'SUM', 'prefer_sistema': True, 'unidad': 'GWh', 'label': 'Demanda Real'},
    'PRECIO_BOLSA':     {'metrica': 'PrecBolsNaci',     'agg': 'AVG', 'entidad': 'Sistema', 'unidad': '$/kWh', 'label': 'Precio de Bolsa'},
    'PRECIO_ESCASEZ':   {'metrica': 'PrecEsca',         'agg': 'AVG', 'unidad': '$/kWh', 'label': 'Precio de Escasez'},
    'APORTES_HIDRICOS': {'metrica': 'AporEner',          'agg': 'SUM', 'unidad': 'GWh', 'label': 'Aportes Hídricos'},
    'EMBALSES':         {'metrica': 'CapaUtilDiarEner',  'agg': 'SUM', 'entidad': 'Sistema', 'unidad': 'GWh', 'label': 'Embalses (Cap. Útil)'},
    'EMBALSES_PCT':     {'metrica': 'PorcVoluUtilDiar',  'agg': 'AVG', 'entidad': 'Sistema', 'escala': 100, 'unidad': '%', 'label': 'Embalses (%)'},
    'PERDIDAS':         {'metrica': 'PerdidasEner',      'agg': 'SUM', 'prefer_sistema': True, 'unidad': 'GWh', 'label': 'Pérdidas'},
    'Hidráulica':       {'tipo_catalogo': 'HIDRAULICA', 'unidad': 'GWh', 'label': 'Gen. Hidráulica'},
    'Térmica':          {'tipo_catalogo': 'TERMICA',    'unidad': 'GWh', 'label': 'Gen. Térmica'},
    'Eólica':           {'tipo_catalogo': 'EOLICA',     'unidad': 'GWh', 'label': 'Gen. Eólica'},
    'Solar':            {'tipo_catalogo': 'SOLAR',      'unidad': 'GWh', 'label': 'Gen. Solar'},
    'Biomasa':          {'tipo_catalogo': 'COGENERADOR','unidad': 'GWh', 'label': 'Gen. Biomasa'},
}

# Colores para métricas
COLORES_METRICAS = {
    'DEMANDA': '#e74c3c',       'GENE_TOTAL': '#2ecc71',    'PRECIO_BOLSA': '#f39c12',
    'PRECIO_ESCASEZ': '#e67e22', 'APORTES_HIDRICOS': '#3498db', 'EMBALSES': '#1abc9c',
    'EMBALSES_PCT': '#16a085',   'PERDIDAS': '#95a5a6',
    'Hidráulica': '#2980b9',     'Térmica': '#e74c3c',
    'Eólica': '#27ae60',         'Solar': '#f1c40f',         'Biomasa': '#8e44ad',
}

# Clasificación de calidad por MAPE
def clasificar_mape(mape):
    if mape is None:
        return "Sin datos", "secondary"
    m = float(mape) * 100
    if m <= 5:
        return "Excelente", "success"
    elif m <= 10:
        return "Bueno", "info"
    elif m <= 20:
        return "Aceptable", "warning"
    else:
        return "Deficiente", "danger"


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE ACCESO A DATOS (via PredictionsRepository — sin psycopg2 directo)
# ═══════════════════════════════════════════════════════════════════════════════

_predictions_repo = PredictionsRepository()


def cargar_resumen_predicciones():
    """Carga resumen de todas las predicciones en la BD."""
    try:
        return _predictions_repo.get_predictions_summary()
    except Exception as e:
        logger.error(f"Error cargando resumen: {e}")
        return pd.DataFrame()


def cargar_predicciones_metrica(fuente):
    """Carga todas las predicciones de una métrica."""
    try:
        return _predictions_repo.get_predictions_for_metric(fuente)
    except Exception as e:
        logger.error(f"Error cargando predicciones {fuente}: {e}")
        return pd.DataFrame()


def cargar_reales_metrica(fuente, fecha_desde, fecha_hasta):
    """Carga datos reales de una métrica desde la tabla metrics."""
    cfg = FUENTES_MAPPING.get(fuente)
    if not cfg:
        return pd.DataFrame()
    
    try:
        if 'tipo_catalogo' in cfg:
            df = _predictions_repo.get_real_generation_by_type(
                cfg['tipo_catalogo'], fecha_desde, fecha_hasta
            )
        else:
            metrica = cfg['metrica']
            agg_fn = cfg.get('agg', 'SUM')
            entidad = cfg.get('entidad')
            prefer_sistema = cfg.get('prefer_sistema', False)
            
            df = _predictions_repo.get_real_metric_data(
                metrica=metrica,
                agg_fn=agg_fn,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                entidad=entidad,
                prefer_sistema=prefer_sistema,
            )
        
        if not df.empty:
            escala = cfg.get('escala', 1)
            if escala != 1:
                df['valor'] = df['valor'] * escala
        return df
    except Exception as e:
        logger.error(f"Error cargando reales {fuente}: {e}")
        return pd.DataFrame()


def cargar_quality_history():
    """Carga historial de evaluaciones de calidad ex-post."""
    try:
        return _predictions_repo.get_quality_history()
    except Exception as e:
        logger.error(f"Error cargando quality history: {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ═══════════════════════════════════════════════════════════════════════════════

def layout():
    """Layout dinámico — se ejecuta cada vez que se accede a la página."""
    
    return html.Div([
        crear_navbar_horizontal(),
        
        # Container principal
        dbc.Container([
            # Header
            crear_page_header(
                titulo="Seguimiento de Predicciones ML",
                icono="fas fa-crosshairs",
                breadcrumb="Inicio / Seguimiento Predicciones",
                fecha=datetime.now().strftime("%d/%m/%Y %H:%M"),
            ),
            crear_boton_regresar(),
            
            # ── SECCIÓN 1: RESUMEN EJECUTIVO (KPIs globales) ──
            html.Div(id='seccion-resumen-ejecutivo'),
            
            # ── SECCIÓN 2: TABLA MAESTRA DE MÉTRICAS ──
            html.H4([
                html.I(className="fas fa-table me-2"),
                "Inventario de Predicciones Activas"
            ], className="mt-4 mb-3", style={'color': '#2c3e50', 'fontWeight': '600'}),
            dcc.Loading(
                html.Div(id='tabla-resumen-predicciones'),
                type="circle"
            ),
            
            # ── SECCIÓN 3: SELECTOR DE MÉTRICA PARA ANÁLISIS DETALLADO ──
            html.Hr(className="my-4"),
            html.H4([
                html.I(className="fas fa-search-plus me-2"),
                "Análisis Detallado por Métrica"
            ], className="mb-3", style={'color': '#2c3e50', 'fontWeight': '600'}),
            
            crear_filter_bar(
                html.Div([
                    html.Label("MÉTRICA:", style={'fontSize': '0.7rem', 'fontWeight': '600', 'marginBottom': '2px'}),
                    dcc.Dropdown(
                        id='dd-metrica-seguimiento',
                        options=[],  # Se llena en callback
                        placeholder="Seleccionar métrica...",
                        style={'width': '280px', 'fontSize': '0.85rem'}
                    ),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),
                html.Div([
                    html.Label("PERIODO:", style={'fontSize': '0.7rem', 'fontWeight': '600', 'marginBottom': '2px'}),
                    dcc.Dropdown(
                        id='dd-periodo-seguimiento',
                        options=[
                            {'label': 'Últimos 7 días', 'value': 7},
                            {'label': 'Últimos 15 días', 'value': 15},
                            {'label': 'Últimos 30 días', 'value': 30},
                            {'label': 'Últimos 60 días', 'value': 60},
                            {'label': 'Todo el horizonte', 'value': 0},
                        ],
                        value=30,
                        clearable=False,
                        style={'width': '200px', 'fontSize': '0.85rem'}
                    ),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),
                html.Div([
                    dbc.Button(
                        [html.I(className="fas fa-chart-line me-1"), "Analizar"],
                        id='btn-analizar-metrica',
                        color="primary",
                        size="sm",
                        className="mt-3"
                    ),
                ], style={'display': 'inline-block'}),
            ),
            
            # ── SECCIÓN 4: KPI CARDS DE LA MÉTRICA SELECCIONADA ──
            dcc.Loading(
                html.Div(id='kpis-metrica-detalle'),
                type="circle"
            ),
            
            # ── SECCIÓN 5: GRÁFICA PREDICHO VS REAL ──
            dcc.Loading(
                html.Div(id='grafica-predicho-vs-real'),
                type="circle"
            ),
            
            # ── SECCIÓN 6: TABLA DÍA A DÍA ──
            dcc.Loading(
                html.Div(id='tabla-dia-a-dia'),
                type="circle"
            ),
            
            # ── SECCIÓN 7: GRÁFICA DE ERROR DIARIO ──
            dcc.Loading(
                html.Div(id='grafica-error-diario'),
                type="circle"
            ),
            
            # ── SECCIÓN 8: HISTORIAL DE CALIDAD EX-POST ──
            html.Hr(className="my-4"),
            html.H4([
                html.I(className="fas fa-history me-2"),
                "Historial de Evaluaciones Ex-Post"
            ], className="mb-3", style={'color': '#2c3e50', 'fontWeight': '600'}),
            dcc.Loading(
                html.Div(id='tabla-quality-history'),
                type="circle"
            ),
            
            # Footer
            html.Div(
                html.Small(
                    "Datos procesados por el sistema predictivo ML del Portal Energético MME. "
                    "Predicciones actualizadas semanalmente (dom 2:00 AM).",
                    className="text-muted"
                ),
                className="text-center my-4"
            ),
            
        ], fluid=True, className="px-4 pb-5"),
        
        # Store para datos intermedios
        dcc.Store(id='store-resumen-predicciones'),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

# ── CALLBACK 1: Cargar resumen ejecutivo + tabla maestra al entrar ──
@callback(
    [Output('seccion-resumen-ejecutivo', 'children'),
     Output('tabla-resumen-predicciones', 'children'),
     Output('dd-metrica-seguimiento', 'options'),
     Output('store-resumen-predicciones', 'data')],
    Input('dd-metrica-seguimiento', 'id'),  # Trigger al cargar la página
)
def cargar_resumen_inicial(_):
    """Carga resumen ejecutivo y tabla maestra al abrir la página."""
    px, go = get_plotly_modules()
    
    df = cargar_resumen_predicciones()
    if df.empty:
        alerta = dbc.Alert("⚠️ No hay predicciones en la base de datos.", color="warning")
        return alerta, alerta, [], None
    
    # ── KPIs EJECUTIVOS ──
    total_metricas = df['fuente'].nunique()
    total_modelos = df['modelo'].nunique()
    total_predicciones = int(df['dias_predichos'].sum())
    mape_promedio = df['mape_entrenamiento'].mean()
    calidad_label, calidad_color = clasificar_mape(mape_promedio)
    
    # Métrica mejor y peor
    best_row = df.loc[df['mape_entrenamiento'].idxmin()]
    worst_row = df.loc[df['mape_entrenamiento'].idxmax()]
    
    resumen_kpis = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-layer-group", style={'fontSize': '1.5rem', 'color': '#3498db'}),
                html.Div([
                    html.Span("Métricas Activas", style={'fontSize': '0.7rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{total_metricas}", style={'fontSize': '2rem', 'fontWeight': '700', 'color': '#2c3e50'}),
                ], className="ms-3")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm h-100"), md=2),
        
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-brain", style={'fontSize': '1.5rem', 'color': '#9b59b6'}),
                html.Div([
                    html.Span("Modelos ML", style={'fontSize': '0.7rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{total_modelos}", style={'fontSize': '2rem', 'fontWeight': '700', 'color': '#2c3e50'}),
                ], className="ms-3")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm h-100"), md=2),
        
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-calendar-check", style={'fontSize': '1.5rem', 'color': '#2ecc71'}),
                html.Div([
                    html.Span("Predicciones Totales", style={'fontSize': '0.7rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{total_predicciones:,}", style={'fontSize': '2rem', 'fontWeight': '700', 'color': '#2c3e50'}),
                ], className="ms-3")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm h-100"), md=2),
        
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-bullseye", style={'fontSize': '1.5rem', 'color': '#e74c3c' if calidad_color == 'danger' else '#2ecc71'}),
                html.Div([
                    html.Span("MAPE Promedio", style={'fontSize': '0.7rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{mape_promedio*100:.1f}%", style={'fontSize': '2rem', 'fontWeight': '700', 'color': '#2c3e50'}),
                    dbc.Badge(calidad_label, color=calidad_color, className="ms-1", style={'fontSize': '0.6rem'}),
                ], className="ms-3")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm h-100"), md=2),
        
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-trophy", style={'fontSize': '1.5rem', 'color': '#f1c40f'}),
                html.Div([
                    html.Span("Mejor Métrica", style={'fontSize': '0.7rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{best_row['fuente']}", style={'fontSize': '1rem', 'fontWeight': '700', 'color': '#27ae60'}),
                    html.Small(f" MAPE {float(best_row['mape_entrenamiento'])*100:.1f}%", style={'color': '#888'}),
                ], className="ms-3")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm h-100"), md=2),
        
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-exclamation-triangle", style={'fontSize': '1.5rem', 'color': '#e74c3c'}),
                html.Div([
                    html.Span("Mayor Error", style={'fontSize': '0.7rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{worst_row['fuente']}", style={'fontSize': '1rem', 'fontWeight': '700', 'color': '#e74c3c'}),
                    html.Small(f" MAPE {float(worst_row['mape_entrenamiento'])*100:.1f}%", style={'color': '#888'}),
                ], className="ms-3")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm h-100"), md=2),
    ], className="mb-4 g-2")
    
    # ── TABLA MAESTRA ──
    # Preparar datos para la tabla
    tabla_data = []
    for _, row in df.iterrows():
        mape_val = float(row['mape_entrenamiento']) if pd.notna(row['mape_entrenamiento']) else None
        calidad, color = clasificar_mape(mape_val)
        cfg = FUENTES_MAPPING.get(row['fuente'], {})
        tabla_data.append({
            'Métrica': cfg.get('label', row['fuente']),
            'Código': row['fuente'],
            'Modelo': row['modelo'],
            'Horizonte': f"{row['dias_predichos']} días",
            'Desde': str(row['fecha_inicio']),
            'Hasta': str(row['fecha_fin']),
            'MAPE (%)': f"{mape_val*100:.2f}%" if mape_val else "N/A",
            'RMSE': f"{float(row['rmse_entrenamiento']):.2f}" if pd.notna(row['rmse_entrenamiento']) else "N/A",
            'Confianza': f"{float(row['confianza'])*100:.0f}%" if pd.notna(row['confianza']) else "95%",
            'Calidad': calidad,
            'Unidad': cfg.get('unidad', ''),
            'Últ. Actualización': str(row['ultima_generacion'])[:16] if pd.notna(row['ultima_generacion']) else "",
        })
    
    df_tabla = pd.DataFrame(tabla_data)
    
    tabla = dash_table.DataTable(
        data=df_tabla.to_dict('records'),
        columns=[{'name': c, 'id': c} for c in df_tabla.columns],
        style_table={'overflowX': 'auto'},
        style_header={
            'backgroundColor': '#2c3e50', 'color': 'white', 'fontWeight': '600',
            'fontSize': '0.75rem', 'textAlign': 'center', 'padding': '8px',
        },
        style_cell={
            'fontSize': '0.8rem', 'textAlign': 'center', 'padding': '6px 10px',
            'whiteSpace': 'normal', 'minWidth': '80px',
        },
        style_data_conditional=[
            {'if': {'filter_query': '{Calidad} = "Excelente"', 'column_id': 'Calidad'},
             'backgroundColor': '#d4edda', 'color': '#155724', 'fontWeight': '600'},
            {'if': {'filter_query': '{Calidad} = "Bueno"', 'column_id': 'Calidad'},
             'backgroundColor': '#d1ecf1', 'color': '#0c5460', 'fontWeight': '600'},
            {'if': {'filter_query': '{Calidad} = "Aceptable"', 'column_id': 'Calidad'},
             'backgroundColor': '#fff3cd', 'color': '#856404', 'fontWeight': '600'},
            {'if': {'filter_query': '{Calidad} = "Deficiente"', 'column_id': 'Calidad'},
             'backgroundColor': '#f8d7da', 'color': '#721c24', 'fontWeight': '600'},
            # Highlight MAPE column
            {'if': {'column_id': 'MAPE (%)'},
             'fontWeight': '700'},
        ],
        sort_action='native',
        filter_action='native',
        page_size=15,
        style_as_list_view=True,
    )
    
    # ── DROPDOWN OPTIONS ──
    options = [
        {'label': f"{FUENTES_MAPPING.get(row['fuente'], {}).get('label', row['fuente'])} ({row['modelo']})",
         'value': row['fuente']}
        for _, row in df.iterrows()
    ]
    
    return resumen_kpis, tabla, options, df.to_dict('records')


# ── CALLBACK 2: Análisis detallado de métrica seleccionada ──
@callback(
    [Output('kpis-metrica-detalle', 'children'),
     Output('grafica-predicho-vs-real', 'children'),
     Output('tabla-dia-a-dia', 'children'),
     Output('grafica-error-diario', 'children')],
    Input('btn-analizar-metrica', 'n_clicks'),
    [State('dd-metrica-seguimiento', 'value'),
     State('dd-periodo-seguimiento', 'value')],
    prevent_initial_call=True,
)
def analizar_metrica_detallada(n_clicks, fuente, periodo_dias):
    """Genera análisis completo: predicho vs real, error diario, tabla día a día."""
    px, go = get_plotly_modules()
    
    if not fuente:
        alerta = dbc.Alert("Selecciona una métrica del dropdown.", color="info")
        return alerta, "", "", ""
    
    cfg = FUENTES_MAPPING.get(fuente, {})
    label = cfg.get('label', fuente)
    unidad = cfg.get('unidad', '')
    color_metrica = COLORES_METRICAS.get(fuente, '#3498db')
    
    # 1. Cargar predicciones
    df_pred = cargar_predicciones_metrica(fuente)
    if df_pred.empty:
        alerta = dbc.Alert(f"No hay predicciones para {label}.", color="warning")
        return alerta, "", "", ""
    
    modelo = df_pred['modelo'].iloc[0]
    mape_train = df_pred['mape_train'].iloc[0]
    rmse_train = df_pred['rmse_train'].iloc[0]
    confianza = df_pred['confianza'].iloc[0]
    
    # 2. Cargar datos reales 
    fecha_min_pred = df_pred['fecha'].min()
    # Also load some days before to compare
    fecha_desde = (fecha_min_pred - timedelta(days=7)).strftime('%Y-%m-%d')
    fecha_hasta = df_pred['fecha'].max().strftime('%Y-%m-%d')
    
    df_real = cargar_reales_metrica(fuente, fecha_desde, fecha_hasta)
    
    # 3. Merge predicho vs real
    if df_real.empty:
        df_merged = df_pred.copy()
        df_merged['real'] = np.nan
        df_merged['error_abs'] = np.nan
        df_merged['error_pct'] = np.nan
        hay_comparacion = False
    else:
        df_merged = pd.merge(
            df_pred, df_real,
            on='fecha', how='left'
        ).rename(columns={'valor': 'real'})
        df_merged['error_abs'] = (df_merged['predicho'] - df_merged['real']).abs()
        df_merged['error_pct'] = np.where(
            df_merged['real'] > 0,
            (df_merged['error_abs'] / df_merged['real'] * 100),
            np.nan
        )
        hay_comparacion = df_merged['real'].notna().any()
    
    # Filtrar por periodo
    periodo_dias = int(periodo_dias) if periodo_dias else 0
    if periodo_dias > 0:
        fecha_corte = datetime.now() - timedelta(days=periodo_dias)
        df_merged = df_merged[df_merged['fecha'] >= fecha_corte]
    
    # ═══ KPIs DE LA MÉTRICA ═══
    dias_con_real = df_merged['real'].notna().sum()
    dias_total = len(df_merged)
    
    if hay_comparacion and dias_con_real > 0:
        df_comp = df_merged.dropna(subset=['real', 'predicho'])
        mape_expost = (df_comp['error_abs'] / df_comp['real'].abs()).mean()
        rmse_expost = np.sqrt(((df_comp['predicho'] - df_comp['real'])**2).mean())
        error_medio = df_comp['error_pct'].mean()
        bias = (df_comp['predicho'] - df_comp['real']).mean()
        calidad_ep, color_ep = clasificar_mape(mape_expost)
        
        # Porcentaje dentro de intervalo de confianza
        if 'intervalo_inferior' in df_comp.columns and 'intervalo_superior' in df_comp.columns:
            dentro_ic = ((df_comp['real'] >= df_comp['intervalo_inferior']) & 
                         (df_comp['real'] <= df_comp['intervalo_superior'])).mean() * 100
        else:
            dentro_ic = None
    else:
        mape_expost = rmse_expost = error_medio = bias = None
        calidad_ep, color_ep = "Sin datos reales aún", "secondary"
        dentro_ic = None
    
    kpis = dbc.Row([
        # Modelo
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-robot", style={'fontSize': '1.3rem', 'color': '#9b59b6'}),
                html.Div([
                    html.Span("Modelo", style={'fontSize': '0.65rem', 'color': '#888', 'display': 'block'}),
                    html.Span(modelo, style={'fontSize': '0.85rem', 'fontWeight': '700'}),
                ], className="ms-2")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm"), md=2),
        
        # MAPE Entrenamiento
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-graduation-cap", style={'fontSize': '1.3rem', 'color': '#3498db'}),
                html.Div([
                    html.Span("MAPE Train", style={'fontSize': '0.65rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{float(mape_train)*100:.2f}%" if mape_train else "N/A",
                             style={'fontSize': '1.4rem', 'fontWeight': '700'}),
                ], className="ms-2")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm"), md=2),
        
        # MAPE Ex-Post
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-check-double", style={'fontSize': '1.3rem', 
                        'color': '#27ae60' if color_ep == 'success' else '#e74c3c'}),
                html.Div([
                    html.Span("MAPE Ex-Post", style={'fontSize': '0.65rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{mape_expost*100:.2f}%" if mape_expost is not None else "—",
                             style={'fontSize': '1.4rem', 'fontWeight': '700'}),
                    dbc.Badge(calidad_ep, color=color_ep, className="ms-1", style={'fontSize': '0.55rem'}),
                ], className="ms-2")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm"), md=2),
        
        # RMSE Ex-Post
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-ruler", style={'fontSize': '1.3rem', 'color': '#e67e22'}),
                html.Div([
                    html.Span("RMSE Ex-Post", style={'fontSize': '0.65rem', 'color': '#888', 'display': 'block'}),
                    html.Span(f"{rmse_expost:.2f} {unidad}" if rmse_expost is not None else "—",
                             style={'fontSize': '1.2rem', 'fontWeight': '700'}),
                ], className="ms-2")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm"), md=2),
        
        # Bias (sesgo)
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-balance-scale", style={'fontSize': '1.3rem', 'color': '#1abc9c'}),
                html.Div([
                    html.Span("Sesgo (Bias)", style={'fontSize': '0.65rem', 'color': '#888', 'display': 'block'}),
                    html.Span(
                        f"{'+'if bias and bias > 0 else ''}{bias:.2f}" if bias is not None else "—",
                        style={'fontSize': '1.2rem', 'fontWeight': '700',
                               'color': '#e74c3c' if bias and abs(bias) > 5 else '#27ae60'}
                    ),
                ], className="ms-2")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm"), md=2),
        
        # Dentro del IC
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.I(className="fas fa-shield-alt", style={'fontSize': '1.3rem', 'color': '#2980b9'}),
                html.Div([
                    html.Span("Dentro IC 95%", style={'fontSize': '0.65rem', 'color': '#888', 'display': 'block'}),
                    html.Span(
                        f"{dentro_ic:.0f}%" if dentro_ic is not None else "—",
                        style={'fontSize': '1.4rem', 'fontWeight': '700',
                               'color': '#27ae60' if dentro_ic and dentro_ic >= 90 else '#e74c3c'}
                    ),
                ], className="ms-2")
            ], style={'display': 'flex', 'alignItems': 'center'})
        ]), className="shadow-sm"), md=2),
    ], className="mb-3 g-2")
    
    # ═══ GRÁFICA PREDICHO VS REAL ═══
    fig = go.Figure()
    
    # Banda de confianza
    if 'intervalo_inferior' in df_merged.columns and 'intervalo_superior' in df_merged.columns:
        df_ic = df_merged.dropna(subset=['intervalo_inferior', 'intervalo_superior'])
        if not df_ic.empty:
            fig.add_trace(go.Scatter(
                x=pd.concat([df_ic['fecha'], df_ic['fecha'][::-1]]),
                y=pd.concat([df_ic['intervalo_superior'], df_ic['intervalo_inferior'][::-1]]),
                fill='toself',
                fillcolor=f'rgba({int(color_metrica[1:3],16)},{int(color_metrica[3:5],16)},{int(color_metrica[5:7],16)},0.12)',
                line=dict(color='rgba(0,0,0,0)'),
                name='IC 95%',
                hoverinfo='skip',
                showlegend=True,
            ))
    
    # Línea predicha
    fig.add_trace(go.Scatter(
        x=df_merged['fecha'], y=df_merged['predicho'],
        mode='lines+markers',
        name=f'Predicho ({modelo})',
        line=dict(color=color_metrica, width=2),
        marker=dict(size=4),
        hovertemplate=f'<b>Predicho</b><br>Fecha: %{{x|%Y-%m-%d}}<br>Valor: %{{y:,.2f}} {unidad}<extra></extra>',
    ))
    
    # Línea real
    if hay_comparacion:
        df_r = df_merged.dropna(subset=['real'])
        fig.add_trace(go.Scatter(
            x=df_r['fecha'], y=df_r['real'],
            mode='lines+markers',
            name='Real (datos XM)',
            line=dict(color='#2c3e50', width=2, dash='dot'),
            marker=dict(size=5, symbol='diamond'),
            hovertemplate=f'<b>Real</b><br>Fecha: %{{x|%Y-%m-%d}}<br>Valor: %{{y:,.2f}} {unidad}<extra></extra>',
        ))
    
    # Línea vertical "hoy"
    hoy = datetime.now()
    fig.add_shape(
        type="line", x0=hoy, x1=hoy, y0=0, y1=1, yref="paper",
        line=dict(color="gray", width=1.5, dash="dash"),
    )
    fig.add_annotation(
        x=hoy, y=1, yref="paper", text="Hoy",
        showarrow=False, font=dict(size=10, color="gray"),
        xanchor="left", yanchor="bottom",
    )
    
    fig.update_layout(
        title=f'{label} — Predicción vs Realidad',
        xaxis_title='Fecha', yaxis_title=f'Valor ({unidad})',
        template='plotly_white', height=450, hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=30, t=60, b=40),
    )
    
    grafica_pred_vs_real = dbc.Card(
        dbc.CardBody(dcc.Graph(figure=fig, config={'displayModeBar': True})),
        className="shadow-sm mb-3"
    )
    
    # ═══ TABLA DÍA A DÍA ═══
    tabla_records = []
    for _, row in df_merged.iterrows():
        fecha_str = row['fecha'].strftime('%Y-%m-%d') if hasattr(row['fecha'], 'strftime') else str(row['fecha'])
        es_futuro = row['fecha'] > pd.Timestamp.now()
        
        pred_val = float(row['predicho']) if pd.notna(row.get('predicho')) else None
        real_val = float(row['real']) if pd.notna(row.get('real')) else None
        err_abs = float(row['error_abs']) if pd.notna(row.get('error_abs')) else None
        err_pct = float(row['error_pct']) if pd.notna(row.get('error_pct')) else None
        
        ic_inf = float(row['intervalo_inferior']) if pd.notna(row.get('intervalo_inferior')) else None
        ic_sup = float(row['intervalo_superior']) if pd.notna(row.get('intervalo_superior')) else None
        
        dentro = ""
        if real_val is not None and ic_inf is not None and ic_sup is not None:
            dentro = "SI" if ic_inf <= real_val <= ic_sup else "NO"
        
        tabla_records.append({
            'Fecha': fecha_str,
            'Estado': '🔮 Futuro' if es_futuro else ('✅ Verificado' if real_val else '⏳ Pendiente'),
            f'Predicho ({unidad})': f"{pred_val:,.2f}" if pred_val is not None else "",
            f'Real ({unidad})': f"{real_val:,.2f}" if real_val is not None else "—",
            'Error Abs': f"{err_abs:,.2f}" if err_abs is not None else "—",
            'Error %': f"{err_pct:.1f}%" if err_pct is not None else "—",
            'IC Inf': f"{ic_inf:,.2f}" if ic_inf is not None else "",
            'IC Sup': f"{ic_sup:,.2f}" if ic_sup is not None else "",
            'Dentro IC': dentro,
        })
    
    df_tabla_dia = pd.DataFrame(tabla_records)
    
    tabla_dia = dbc.Card(
        dbc.CardBody([
            html.H6([
                html.I(className="fas fa-list-ol me-2"),
                f"Detalle día a día — {label}",
                dbc.Badge(f"{dias_con_real}/{dias_total} días con dato real", color="info", className="ms-2"),
            ], className="mb-3"),
            dash_table.DataTable(
                data=df_tabla_dia.to_dict('records'),
                columns=[{'name': c, 'id': c} for c in df_tabla_dia.columns],
                style_table={'overflowX': 'auto', 'maxHeight': '400px', 'overflowY': 'auto'},
                style_header={
                    'backgroundColor': '#34495e', 'color': 'white', 'fontWeight': '600',
                    'fontSize': '0.7rem', 'textAlign': 'center', 'padding': '6px',
                },
                style_cell={
                    'fontSize': '0.75rem', 'textAlign': 'center', 'padding': '4px 8px',
                    'whiteSpace': 'nowrap',
                },
                style_data_conditional=[
                    {'if': {'filter_query': '{Dentro IC} = "NO"', 'column_id': 'Dentro IC'},
                     'backgroundColor': '#f8d7da', 'color': '#721c24', 'fontWeight': '700'},
                    {'if': {'filter_query': '{Dentro IC} = "SI"', 'column_id': 'Dentro IC'},
                     'backgroundColor': '#d4edda', 'color': '#155724', 'fontWeight': '700'},
                    {'if': {'filter_query': '{Estado} contains "Futuro"'},
                     'backgroundColor': '#f0f0f0', 'fontStyle': 'italic'},
                ],
                sort_action='native',
                filter_action='native',
                page_size=20,
                export_format='csv',
                export_headers='display',
            ),
        ]),
        className="shadow-sm mb-3"
    )
    
    # ═══ GRÁFICA ERROR DIARIO ═══
    if hay_comparacion and dias_con_real > 0:
        df_err = df_merged.dropna(subset=['error_pct'])
        
        fig_err = go.Figure()
        
        # Barras de error porcentual
        colores_err = ['#27ae60' if e <= 5 else '#f39c12' if e <= 15 else '#e74c3c' 
                       for e in df_err['error_pct']]
        
        fig_err.add_trace(go.Bar(
            x=df_err['fecha'], y=df_err['error_pct'],
            marker_color=colores_err,
            name='Error %',
            hovertemplate='Fecha: %{x|%Y-%m-%d}<br>Error: %{y:.1f}%<extra></extra>',
        ))
        
        # Línea de MAPE promedio
        if mape_expost is not None:
            fig_err.add_hline(y=mape_expost*100, line_dash="dash", line_color="#e74c3c",
                             annotation_text=f"MAPE={mape_expost*100:.1f}%", annotation_position="top right")
        
        # Umbrales
        fig_err.add_hline(y=5, line_dash="dot", line_color="#27ae60", 
                         annotation_text="5% Excelente", annotation_position="bottom right")
        fig_err.add_hline(y=15, line_dash="dot", line_color="#f39c12",
                         annotation_text="15% Aceptable", annotation_position="bottom right")
        
        fig_err.update_layout(
            title=f'Error Porcentual Diario — {label}',
            xaxis_title='Fecha', yaxis_title='Error (%)',
            template='plotly_white', height=350,
            margin=dict(l=60, r=30, t=60, b=40),
            showlegend=False,
        )
        
        grafica_err = dbc.Card(
            dbc.CardBody(dcc.Graph(figure=fig_err, config={'displayModeBar': True})),
            className="shadow-sm mb-3"
        )
    else:
        grafica_err = dbc.Alert(
            [html.I(className="fas fa-info-circle me-2"),
             "Gráfica de error disponible cuando haya datos reales para comparar."],
            color="info", className="mt-2"
        )
    
    return kpis, grafica_pred_vs_real, tabla_dia, grafica_err


# ── CALLBACK 3: Historial de calidad ex-post ──
@callback(
    Output('tabla-quality-history', 'children'),
    Input('dd-metrica-seguimiento', 'id'),  # Trigger al cargar
)
def cargar_historial_calidad(_):
    """Carga tabla con historial de evaluaciones de calidad."""
    df = cargar_quality_history()
    
    if df.empty:
        return dbc.Alert(
            [html.I(className="fas fa-info-circle me-2"),
             "No hay evaluaciones de calidad ex-post registradas. Se generan automáticamente cada domingo."],
            color="info"
        )
    
    # Formatear
    records = []
    for _, row in df.iterrows():
        mape_ep = float(row['mape_expost']) if pd.notna(row.get('mape_expost')) else None
        mape_tr = float(row['mape_train']) if pd.notna(row.get('mape_train')) else None
        calidad, color = clasificar_mape(mape_ep)
        
        # Drift: si MAPE ex-post > 2x MAPE train
        drift = ""
        if mape_ep is not None and mape_tr is not None and mape_tr > 0:
            ratio = mape_ep / mape_tr
            if ratio > 2:
                drift = f"⚠️ {ratio:.1f}x"
            elif ratio > 1.5:
                drift = f"↗ {ratio:.1f}x"
            else:
                drift = f"✅ {ratio:.1f}x"
        
        cfg = FUENTES_MAPPING.get(row['fuente'], {})
        records.append({
            'Métrica': cfg.get('label', row['fuente']),
            'Modelo': row.get('modelo', ''),
            'Evaluación': str(row['fecha_evaluacion'])[:16] if pd.notna(row.get('fecha_evaluacion')) else '',
            'Periodo': f"{row.get('fecha_desde', '')} → {row.get('fecha_hasta', '')}",
            'Días Overlap': row.get('dias_overlap', 0),
            'MAPE Ex-Post': f"{mape_ep*100:.2f}%" if mape_ep else "—",
            'MAPE Train': f"{mape_tr*100:.2f}%" if mape_tr else "—",
            'Drift': drift,
            'Calidad': calidad,
            'Notas': row.get('notas', '') or '',
        })
    
    df_hist = pd.DataFrame(records)
    
    return dash_table.DataTable(
        data=df_hist.to_dict('records'),
        columns=[{'name': c, 'id': c} for c in df_hist.columns],
        style_table={'overflowX': 'auto'},
        style_header={
            'backgroundColor': '#2c3e50', 'color': 'white', 'fontWeight': '600',
            'fontSize': '0.75rem', 'textAlign': 'center', 'padding': '8px',
        },
        style_cell={
            'fontSize': '0.78rem', 'textAlign': 'center', 'padding': '5px 10px',
            'whiteSpace': 'normal',
        },
        style_data_conditional=[
            {'if': {'filter_query': '{Calidad} = "Excelente"', 'column_id': 'Calidad'},
             'backgroundColor': '#d4edda', 'color': '#155724', 'fontWeight': '600'},
            {'if': {'filter_query': '{Calidad} = "Bueno"', 'column_id': 'Calidad'},
             'backgroundColor': '#d1ecf1', 'color': '#0c5460', 'fontWeight': '600'},
            {'if': {'filter_query': '{Calidad} = "Aceptable"', 'column_id': 'Calidad'},
             'backgroundColor': '#fff3cd', 'color': '#856404', 'fontWeight': '600'},
            {'if': {'filter_query': '{Calidad} = "Deficiente"', 'column_id': 'Calidad'},
             'backgroundColor': '#f8d7da', 'color': '#721c24', 'fontWeight': '600'},
            {'if': {'filter_query': '{Drift} contains "⚠️"', 'column_id': 'Drift'},
             'backgroundColor': '#f8d7da', 'color': '#721c24', 'fontWeight': '700'},
        ],
        sort_action='native',
        filter_action='native',
        page_size=20,
        export_format='csv',
        export_headers='display',
    )
