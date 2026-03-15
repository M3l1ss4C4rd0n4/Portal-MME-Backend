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

from dash import dcc, html, Input, Output, State, callback, register_page, dash_table, ALL, ctx
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

from interface.components.chart_card import crear_page_header, crear_filter_bar, crear_chart_card_custom
from interface.components.kpi_card import crear_kpi_row
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
    'PRECIO_BOLSA':     {'metrica': 'PrecBolsNaci',     'agg': 'AVG', 'entidad': 'Sistema', 'unidad': 'COP/kWh', 'label': 'Precio de Bolsa'},
    'PRECIO_ESCASEZ':   {'metrica': 'PrecEsca',         'agg': 'AVG', 'unidad': 'COP/kWh', 'label': 'Precio de Escasez'},
    'APORTES_HIDRICOS': {'metrica': 'AporEner',          'agg': 'SUM', 'unidad': 'GWh', 'label': 'Aportes Hídricos'},
    'EMBALSES':         {'metrica': 'CapaUtilDiarEner',  'agg': 'SUM', 'entidad': 'Sistema', 'unidad': 'GWh', 'label': 'Embalses (Cap. Útil)'},
    'EMBALSES_PCT':     {'metrica': 'PorcVoluUtilDiar',  'agg': 'AVG', 'entidad': 'Sistema', 'escala': 100, 'unidad': '%', 'label': 'Embalses (%)'},
    'PERDIDAS':         {'metrica': 'PerdidasEner',      'agg': 'SUM', 'prefer_sistema': True, 'unidad': 'GWh', 'label': 'Pérdidas'},
    'CU_DIARIO':        {'unidad': 'COP/kWh', 'label': 'Costo Unitario Diario'},
    'PERDIDAS_TOTALES': {'metrica': 'PerdidasEner',      'agg': 'SUM', 'unidad': 'GWh', 'label': 'Pérdidas Totales'},
    'Hidráulica':       {'tipo_catalogo': 'HIDRAULICA', 'unidad': 'GWh/día', 'label': 'Gen. Hidráulica'},
    'Térmica':          {'tipo_catalogo': 'TERMICA',    'unidad': 'GWh/día', 'label': 'Gen. Térmica'},
    'Eólica':           {'tipo_catalogo': 'EOLICA',     'unidad': 'GWh/día', 'label': 'Gen. Eólica'},
    'Solar':            {'tipo_catalogo': 'SOLAR',      'unidad': 'GWh/día', 'label': 'Gen. Solar'},
    'Biomasa':          {'tipo_catalogo': 'COGENERADOR','unidad': 'GWh/día', 'label': 'Gen. Biomasa'},
}

# Metadatos visuales por fuente (icono, color, nombre completo del modelo, features)
FUENTES_META = {
    'EMBALSES':         {'icono': '🏞️', 'color': '#1abc9c', 'modelo_real': 'Prophet 1.1.5 + SARIMA(2,1,2)(1,0,1)[7] — Ensemble', 'features': 'Serie histórica 2020-2026, estacionalidad anual/semanal'},
    'EMBALSES_PCT':     {'icono': '💧', 'color': '#16a085', 'modelo_real': 'Prophet 1.1.5 + SARIMA(2,1,2)(1,0,1)[7] — Ensemble', 'features': 'Serie histórica 2020-2026, estacionalidad anual/semanal'},
    'PRECIO_ESCASEZ':   {'icono': '⚡', 'color': '#e67e22', 'modelo_real': 'Prophet 1.1.5 + SARIMA(2,1,2)(1,0,1)[7] — Ensemble', 'features': 'Serie histórica 2020-2026, estacionalidad anual/semanal'},
    'GENE_TOTAL':       {'icono': '⚡', 'color': '#2ecc71', 'modelo_real': 'Prophet 1.1.5 + SARIMA(2,1,2)(1,0,1)[7] — Ensemble', 'features': 'Serie histórica 2020-2026, estacionalidad anual/semanal'},
    'DEMANDA':          {'icono': '📊', 'color': '#e74c3c', 'modelo_real': 'LightGBM 4.6.0 — Horizonte Dual (corto+largo)', 'features': 'Lags 1/7d, festivos Colombia (Ley 51+Emiliani), día semana'},
    'Hidráulica':       {'icono': '💧', 'color': '#2980b9', 'modelo_real': 'Prophet 1.1.5 + SARIMA(2,1,2)(1,0,1)[7] — Ensemble', 'features': 'Serie histórica 2020-2026, estacionalidad anual/semanal'},
    'Biomasa':          {'icono': '🌿', 'color': '#8e44ad', 'modelo_real': 'Prophet 1.1.5 + SARIMA(2,1,2)(1,0,1)[7] — Ensemble', 'features': 'Serie histórica 2020-2026, estacionalidad anual/semanal'},
    'PERDIDAS':         {'icono': '📉', 'color': '#95a5a6', 'modelo_real': 'Prophet 1.1.5 + SARIMA(2,1,2)(1,0,1)[7] — Ensemble', 'features': 'Serie histórica 2020-2026, estacionalidad anual/semanal'},
    'Térmica':          {'icono': '🔥', 'color': '#e74c3c', 'modelo_real': 'LightGBM 4.6.0 — Directo con lags', 'features': 'Lags 1/7/14d, temperatura, precio bolsa histórico'},
    'PRECIO_BOLSA':     {'icono': '💰', 'color': '#f39c12', 'modelo_real': 'RandomForest 300 árboles (sklearn 1.4)', 'features': 'Embalses %, Demanda GWh, Aportes hídricos, rolling mean 7d'},
    'Solar':            {'icono': '☀️', 'color': '#f1c40f', 'modelo_real': 'LightGBM 4.6.0 + NASA POWER CERES satélite', 'features': 'Irradiancia NASA POWER (Costa Caribe, La Guajira), lags 7/14d'},
    'APORTES_HIDRICOS': {'icono': '🌊', 'color': '#3498db', 'modelo_real': 'LightGBM 4.6.0 + NASA POWER precipitación', 'features': 'Precipitación NASA POWER 9 cuencas, embalses, lags 7d'},
    'Eólica':           {'icono': '💨', 'color': '#27ae60', 'modelo_real': 'LightGBM 4.6.0 + IDEAM velocidad viento', 'features': 'Vel. viento IDEAM La Guajira, lags 7/14d, calendario'},
    'CU_DIARIO':        {'icono': '🏷️', 'color': '#8e44ad', 'modelo_real': 'Serie histórica + regresores de precio', 'features': 'EMBALSES_PCT, PRECIO_BOLSA, DEMANDA'},
    'PERDIDAS_TOTALES': {'icono': '📉', 'color': '#7f8c8d', 'modelo_real': 'Prophet 1.1.5 + SARIMA', 'features': 'Serie histórica 2020-2026'},
}

# Colores para métricas
COLORES_METRICAS = {
    'DEMANDA': '#e74c3c',       'GENE_TOTAL': '#2ecc71',    'PRECIO_BOLSA': '#f39c12',
    'PRECIO_ESCASEZ': '#e67e22', 'APORTES_HIDRICOS': '#3498db', 'EMBALSES': '#1abc9c',
    'EMBALSES_PCT': '#16a085',   'PERDIDAS': '#95a5a6',
    'CU_DIARIO': '#8e44ad',      'PERDIDAS_TOTALES': '#7f8c8d',
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
            metrica = cfg.get('metrica')
            if not metrica:
                return pd.DataFrame()
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


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS DE COMPONENTES UI
# ══════════════════════════════════════════════════════════════════════════════

_BADGE_TO_KPI_COLOR = {
    'success': 'green', 'info': 'cyan', 'warning': 'orange',
    'danger': 'red', 'secondary': 'blue', 'primary': 'blue',
}

def layout():
    """Layout dinámico — panel izquierdo de métricas + panel derecho de detalle."""
    return html.Div([
        crear_page_header(
            titulo="Seguimiento de Predicciones ML",
            icono="fas fa-crosshairs",
            breadcrumb="Inicio / Seguimiento Predicciones",
            fecha=datetime.now().strftime("%d/%m/%Y %H:%M"),
        ),

        # KPIs ejecutivos globales
        dcc.Loading(html.Div(id='seccion-resumen-ejecutivo'), type='circle'),

        # ── Panel principal: lista izquierda + detalle derecha ──
        dbc.Row([
            # ── COLUMNA IZQ — Filtros + lista de métricas ──
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.I(className='fas fa-filter me-2'),
                            html.Span("Parámetros de análisis",
                                      className='fw-bold small'),
                        ], className='mb-3'),
                        html.Label("PERIODO DE COMPARACIÓN",
                                   className='text-muted fw-semibold mb-1',
                                   style={'fontSize': '0.68rem',
                                          'letterSpacing': '0.05em'}),
                        dcc.Dropdown(
                            id='dd-periodo-seguimiento',
                            options=[
                                {'label': 'Últimos 7 días',   'value': 7},
                                {'label': 'Últimos 15 días',  'value': 15},
                                {'label': 'Últimos 30 días',  'value': 30},
                                {'label': 'Últimos 60 días',  'value': 60},
                                {'label': 'Todo el horizonte', 'value': 0},
                            ],
                            value=30,
                            clearable=False,
                            className='mb-3',
                            style={'fontSize': '0.85rem'},
                        ),
                        html.Label("HORIZONTE DE PREDICCIÓN",
                                   className='text-muted fw-semibold mb-1',
                                   style={'fontSize': '0.68rem',
                                          'letterSpacing': '0.05em'}),
                        dcc.RadioItems(
                            id='horizonte-selector',
                            options=[
                                {'label': '30 días',      'value': 30},
                                {'label': '90 días',      'value': 90},
                                {'label': '365 días ⚗️', 'value': 365},
                            ],
                            value=90,
                            inline=True,
                            style={'fontSize': '0.82rem'},
                            inputStyle={'marginRight': '4px'},
                            labelStyle={'marginRight': '12px'},
                        ),
                        html.Small(
                            "⚠️ 365d = EXPERIMENTAL",
                            id='horizonte-aviso',
                            style={'color': '#e67e22', 'display': 'none',
                                   'fontWeight': '600'},
                        ),
                    ], style={'backgroundColor': '#f8f9fa',
                               'borderBottom': '1px solid #e9ecef'}),
                    dbc.CardBody(
                        dcc.Loading(
                            html.Div(id='lista-metricas-izq'),
                            type='dot',
                        ),
                        style={
                            'overflowY': 'auto',
                            'maxHeight': 'calc(100vh - 380px)',
                            'padding': '0.5rem',
                            'minHeight': '300px',
                        },
                    ),
                ], className='shadow-sm',
                   style={'position': 'sticky', 'top': '52px'}),
            ], md=4),

            # ── COLUMNA DER — Detalle de la métrica seleccionada ──
            dbc.Col([
                html.Div(
                    id='panel-detalle-derecha',
                    children=html.Div([
                        html.I(className='fas fa-hand-point-left fa-2x text-muted mb-3 d-block'),
                        html.P(
                            "Selecciona una métrica a la izquierda "
                            "para ver el análisis detallado.",
                            className='text-muted fst-italic',
                        ),
                    ], className='text-center mt-5 pt-4'),
                ),
            ], md=8),
        ], className='g-3 mt-2'),

        # ── Historial de evaluaciones Ex-Post ──
        html.Hr(className='mt-4 mb-3'),
        html.Div([
            html.I(className="fas fa-history me-2", style={'color': '#3498db'}),
            html.Span("Historial de Evaluaciones Ex-Post",
                      style={'fontWeight': '700', 'fontSize': '1.05rem',
                             'color': '#2c3e50'}),
        ], className="mb-3 pb-2", style={'borderBottom': '2px solid #e9ecef'}),
        dcc.Loading(html.Div(id='tabla-quality-history'), type="circle"),

        html.Div(
            html.Small([
                html.I(className="fas fa-brain me-1 text-muted"),
                "Predicciones actualizadas semanalmente (domingos 2:00 AM). "
                "Modelos: Prophet, LightGBM, RandomForest, SARIMA.",
            ], className="text-muted fst-italic"),
            className="text-center my-4"
        ),

        # Stores
        dcc.Store(id='store-resumen-predicciones'),
        dcc.Store(id='store-metrica-seleccionada'),
    ], className='container-fluid px-4 py-3')


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════
# ── CALLBACK 0: Mostrar/ocultar aviso EXPERIMENTAL según horizonte ──
@callback(
    Output('horizonte-aviso', 'style'),
    Input('horizonte-selector', 'value'),
)
def toggle_horizonte_aviso(horizonte):
    if horizonte and horizonte > 90:
        return {'color': '#e67e22', 'fontWeight': '600', 'display': 'block'}
    return {'display': 'none'}

# ── CALLBACK 1: Cargar lista de métricas y KPIs ejecutivos al entrar ──
@callback(
    [Output('seccion-resumen-ejecutivo', 'children'),
     Output('lista-metricas-izq', 'children'),
     Output('store-resumen-predicciones', 'data')],
    Input('dd-periodo-seguimiento', 'id'),  # Trigger al cargar la página
)
def cargar_resumen_inicial(_):
    """Carga KPIs ejecutivos y lista compacta de métricas al abrir la página."""
    px, go = get_plotly_modules()
    
    df = cargar_resumen_predicciones()
    if df.empty:
        alerta = dbc.Alert("⚠️ No hay predicciones en la base de datos.", color="warning")
        return alerta, alerta, None
    
    # ── KPIs EJECUTIVOS ──
    total_metricas = df['fuente'].nunique()
    total_modelos = df['modelo'].nunique()
    total_predicciones = int(df['dias_predichos'].sum())
    mape_promedio = df['mape_entrenamiento'].mean()
    calidad_label, calidad_color = clasificar_mape(mape_promedio)
    
    # Métrica mejor y peor
    best_row = df.loc[df['mape_entrenamiento'].idxmin()]
    worst_row = df.loc[df['mape_entrenamiento'].idxmax()]
    best_mape = float(best_row['mape_entrenamiento'])
    worst_mape = float(worst_row['mape_entrenamiento'])

    resumen_kpis = crear_kpi_row([
        {
            'titulo': 'Métricas Activas',
            'valor': str(total_metricas),
            'unidad': '',
            'icono': 'fas fa-database',
            'color': 'blue',
        },
        {
            'titulo': 'Modelos ML',
            'valor': str(total_modelos),
            'unidad': '',
            'icono': 'fas fa-brain',
            'color': 'cyan',
        },
        {
            'titulo': 'Predicciones',
            'valor': f'{total_predicciones:,}',
            'unidad': '',
            'icono': 'fas fa-chart-bar',
            'color': 'green',
        },
        {
            'titulo': 'MAPE Promedio',
            'valor': f'{mape_promedio*100:.1f}',
            'unidad': '%',
            'icono': 'fas fa-bullseye',
            'color': 'orange',
            'subtexto': calidad_label,
        },
        {
            'titulo': 'Mejor Métrica',
            'valor': best_row['fuente'],
            'unidad': '',
            'icono': 'fas fa-trophy',
            'color': 'green',
            'subtexto': f'MAPE {best_mape*100:.1f}%',
        },
        {
            'titulo': 'Mayor Error',
            'valor': worst_row['fuente'],
            'unidad': '',
            'icono': 'fas fa-triangle-exclamation',
            'color': 'red',
            'subtexto': f'MAPE {worst_mape*100:.1f}%',
        },
    ])

    # ── LISTA COMPACTA PARA PANEL IZQUIERDO ──
    # Deduplicar por fuente: preferir el horizonte 90d; si no existe, el menor MAPE
    df_izq = (
        df.sort_values('mape_entrenamiento', na_position='last')
          .drop_duplicates(subset=['fuente'], keep='first')
          .reset_index(drop=True)
    )
    tarjetas_izq = []
    for _, row in df_izq.iterrows():
        fuente = row['fuente']
        cfg_izq = FUENTES_MAPPING.get(fuente, {})
        meta_izq = FUENTES_META.get(fuente, {})
        mape_v = float(row['mape_entrenamiento']) if pd.notna(row['mape_entrenamiento']) else None
        calidad_izq, badge_izq = clasificar_mape(mape_v)
        color_borde_izq = meta_izq.get('color', '#3498db')
        icono_izq = meta_izq.get('icono', '📊')
        mape_txt_izq = f"{mape_v*100:.1f}%" if mape_v else "N/A"
        mape_color_izq = ('#e74c3c' if (mape_v or 0) > 0.1
                          else '#f39c12' if (mape_v or 0) > 0.05
                          else '#27ae60')
        tarjetas_izq.append(
            html.Div(
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Span(f"{icono_izq} ", style={'fontSize': '1rem'}),
                            html.Span(
                                cfg_izq.get('label', fuente),
                                className='fw-bold',
                                style={'fontSize': '0.88rem', 'color': '#2c3e50'},
                            ),
                            dbc.Badge(
                                calidad_izq, color=badge_izq,
                                style={'fontSize': '0.58rem', 'float': 'right'},
                            ),
                        ], className='d-flex align-items-center justify-content-between mb-1'),
                        html.Div([
                            html.Span("MAPE ", className='text-muted',
                                      style={'fontSize': '0.7rem'}),
                            html.Span(mape_txt_izq, className='fw-bold',
                                      style={'fontSize': '0.75rem',
                                             'color': mape_color_izq}),
                            html.Span(
                                f"  ·  {row['dias_predichos']}d"
                                f" · {cfg_izq.get('unidad', '')}",
                                className='text-muted',
                                style={'fontSize': '0.68rem'},
                            ),
                        ]),
                    ], style={'padding': '0.5rem 0.75rem'}),
                ], className='shadow-sm', style={
                    'borderLeft': f"4px solid {color_borde_izq}",
                    'borderRadius': '6px',
                }),
                id={'type': 'card-metrica', 'fuente': fuente},
                n_clicks=0,
                className='mb-2',
                style={'cursor': 'pointer'},
            )
        )
    lista_izq = (html.Div(tarjetas_izq) if tarjetas_izq
                 else dbc.Alert("Sin métricas disponibles.", color="warning"))

    return resumen_kpis, lista_izq, df.to_dict('records')


# ── CALLBACK: Seleccionar métrica desde tarjeta izquierda ──
@callback(
    Output('store-metrica-seleccionada', 'data'),
    Input({'type': 'card-metrica', 'fuente': ALL}, 'n_clicks'),
    prevent_initial_call=True,
)
def seleccionar_metrica(n_clicks_list):
    if not any(n or 0 for n in n_clicks_list):
        raise PreventUpdate
    triggered = ctx.triggered_id
    if triggered and isinstance(triggered, dict):
        return triggered.get('fuente')
    raise PreventUpdate


# ── CALLBACK 2: Mostrar detalle cuando se selecciona métrica o cambian filtros ──
@callback(
    Output('panel-detalle-derecha', 'children'),
    Input('store-metrica-seleccionada', 'data'),
    Input('dd-periodo-seguimiento', 'value'),
    Input('horizonte-selector', 'value'),
    prevent_initial_call=True,
)
def mostrar_detalle_metrica(fuente, periodo_dias, horizonte_dias):
    """Genera análisis completo: predicho vs real, error diario, tabla día a día."""
    px, go = get_plotly_modules()

    if not fuente:
        raise PreventUpdate

    cfg = FUENTES_MAPPING.get(fuente, {})
    label = cfg.get('label', fuente)
    unidad = cfg.get('unidad', '')
    color_metrica = COLORES_METRICAS.get(fuente, '#3498db')

    # 1. Cargar predicciones (filtrar por horizonte seleccionado)
    df_pred = cargar_predicciones_metrica(fuente)
    if not df_pred.empty and horizonte_dias and 'horizonte_dias' in df_pred.columns:
        mask = df_pred['horizonte_dias'] == horizonte_dias
        if mask.any():
            df_pred = df_pred[mask]
    if df_pred.empty:
        alerta = dbc.Alert(f"No hay predicciones para {label}.", color="warning")
        return html.Div(alerta)
    
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
    
    kpis = crear_kpi_row([
            {
                'titulo': 'Modelo ML',
                'valor': modelo,
                'unidad': '',
                'icono': 'fas fa-robot',
                'color': 'purple',
            },
            {
                'titulo': 'MAPE Entren.',
                'valor': f"{float(mape_train)*100:.2f}" if mape_train else "N/A",
                'unidad': '%',
                'icono': 'fas fa-graduation-cap',
                'color': 'blue',
            },
            {
                'titulo': 'MAPE Ex-Post',
                'valor': f"{mape_expost*100:.2f}" if mape_expost is not None else "—",
                'unidad': '%' if mape_expost is not None else '',
                'icono': 'fas fa-check-double',
                'color': _BADGE_TO_KPI_COLOR.get(color_ep, 'blue'),
                'subtexto': calidad_ep,
            },
            {
                'titulo': 'RMSE Ex-Post',
                'valor': f"{rmse_expost:.2f}" if rmse_expost is not None else "—",
                'unidad': unidad if rmse_expost is not None else '',
                'icono': 'fas fa-ruler',
                'color': 'orange',
            },
            {
                'titulo': 'Sesgo (Bias)',
                'valor': (f"{'+'if bias > 0 else ''}{bias:.2f}") if bias is not None else "—",
                'unidad': '',
                'icono': 'fas fa-balance-scale',
                'color': 'red' if bias is not None and abs(bias) > 5 else 'green',
            },
            {
                'titulo': 'Dentro IC 95%',
                'valor': f"{dentro_ic:.0f}" if dentro_ic is not None else "—",
                'unidad': '%' if dentro_ic is not None else '',
                'icono': 'fas fa-shield-alt',
                'color': 'green' if dentro_ic is not None and dentro_ic >= 90 else 'red',
            },
        ])
    
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
    
    grafica_pred_vs_real = crear_chart_card_custom(
        titulo=f"Predicción vs Realidad — {label}",
        subtitulo=f"Modelo: {modelo} · Horizonte {horizonte_dias} días",
        children=dcc.Graph(figure=fig, config={'displayModeBar': True}),
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
    
    tabla_dia = crear_chart_card_custom(
        titulo=f"Detalle día a día — {label}",
        subtitulo=f"{dias_con_real} de {dias_total} días con dato real disponible",
        children=dash_table.DataTable(
            data=df_tabla_dia.to_dict('records'),  # type: ignore[arg-type]
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
            style_data_conditional=[  # type: ignore[arg-type]
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
        
        grafica_err = crear_chart_card_custom(
            titulo=f'Error Porcentual Diario — {label}',
            subtitulo='Verde ≤5% Excelente · Naranja ≤15% Aceptable · Rojo >15% Deficiente',
            children=dcc.Graph(figure=fig_err, config={'displayModeBar': True}),
        )
    else:
        grafica_err = dbc.Alert(
            [html.I(className="fas fa-info-circle me-2"),
             "Gráfica de error disponible cuando haya datos reales para comparar."],
            color="info", className="mt-2"
        )
    
    return html.Div([kpis, grafica_pred_vs_real, tabla_dia, grafica_err])


# ── CALLBACK 3: Historial de calidad ex-post ──
@callback(
    Output('tabla-quality-history', 'children'),
    Input('tabla-quality-history', 'id'),  # Trigger al cargar
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
    
    # Rediseño ex-post: AG Grid con filtrado, orden y cellStyle condicional
    ag_theme = "ag-theme-alpine-dark"

    return dag.AgGrid(
        id="tabla-historial-expost",
        rowData=df_hist.to_dict("records"),
        columnDefs=[
            {"field": "Métrica", "headerName": "MÉTRICA", "width": 130, "pinned": "left"},
            {"field": "Modelo", "headerName": "MODELO", "width": 140},
            {"field": "Evaluación", "headerName": "EVALUACIÓN", "width": 130},
            {
                "field": "MAPE Ex-Post", "headerName": "MAPE EX-POST", "width": 120,
                "cellStyle": {
                    "function": (
                        "parseFloat(params.value) > 10 ? "
                        "{'color': 'var(--bs-danger)', 'fontWeight': '700'} : "
                        "{'color': 'var(--bs-success)', 'fontWeight': '700'}"
                    )
                },
            },
            {"field": "MAPE Train", "headerName": "MAPE TRAIN", "width": 110},
            {
                "field": "Drift", "headerName": "DRIFT", "width": 90,
                "cellStyle": {
                    "function": (
                        "params.value && params.value.includes('⚠️') ? "
                        "{'backgroundColor': 'rgba(255,193,7,0.15)', 'fontWeight': '700'} : {}"
                    )
                },
            },
            {"field": "Calidad", "headerName": "CALIDAD", "width": 100},
            {"field": "Notas", "headerName": "NOTAS", "flex": 1, "wrapText": True, "autoHeight": True},
        ],
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
            "cellStyle": {"fontSize": "11px"},
            "headerClass": "ag-header-compact",
        },
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 15,
            "rowHeight": 36,
            "headerHeight": 32,
            "animateRows": True,
            "suppressMovableColumns": True,
        },
        style={"height": "450px"},
        className=ag_theme,
    )
