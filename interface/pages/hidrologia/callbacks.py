"""
Hidrología - Callbacks de Interactividad
==========================================

Todos los callbacks de Dash para la página de hidrología.
Se registran automáticamente al importar este módulo.
"""

import json
import traceback
import pandas as pd
from datetime import date, datetime, timedelta

import dash
from dash import dcc, html, Input, Output, State, callback, dash_table, no_update
from dash import clientside_callback, ClientsideFunction
import dash_bootstrap_components as dbc
import plotly.express as px

from infrastructure.logging.logger import setup_logger
from infrastructure.external.xm_service import obtener_datos_inteligente, get_objetoAPI, obtener_datos_desde_bd
from domain.services.geo_service import REGIONES_COORDENADAS

from interface.components.layout import (
    crear_navbar_horizontal, crear_boton_regresar,
    crear_filtro_fechas_compacto, registrar_callback_filtro_fechas,
)
from interface.components.kpi_card import crear_kpi, crear_kpi_row
from interface.components.chart_card import (
    crear_chart_card, crear_chart_card_custom,
    crear_page_header, crear_filter_bar,
)
from core.constants import UIColors as COLORS
from core.validators import validate_date_range, validate_string
from core.exceptions import DateRangeError, InvalidParameterError, DataNotFoundError

from .utils import (
    logger, get_plotly_modules, format_number, format_date,
    LAST_UPDATE, API_STATUS,
    _GEOJSON_CACHE, _cargar_geojson_cache,
    validar_rango_fechas, manejar_error_api,
    get_reservas_hidricas, get_aportes_hidricos,
    calcular_volumen_util_unificado,
    normalizar_codigo, normalizar_region,
    get_rio_region_dict, ensure_rio_region_loaded,
    get_region_options, agregar_datos_hidrologia_inteligente,
    calcular_semaforo_embalse, clasificar_riesgo_embalse,
    obtener_estilo_riesgo, obtener_pictograma_riesgo,
)
from .data_services import (
    get_aportes_hidricos_por_region, get_aportes_hidricos_por_rio,
    get_all_rios_api, get_rio_options,
    obtener_datos_embalses_por_region, get_participacion_embalses,
    get_embalses_completa_para_tabla, get_embalses_data_for_table,
    get_embalses_capacidad, get_embalses_by_region,
    calcular_semaforo_embalse_local,
    clasificar_riesgo_embalse_local,
    obtener_estilo_riesgo_local,
    obtener_pictograma_riesgo_local,
    agregar_columna_riesgo_a_tabla,
    generar_estilos_condicionales_riesgo,
    get_tabla_con_participacion,
    get_porcapor_data,
)
from .tables import (
    crear_estilos_condicionales_para_tabla_estatica,
    crear_tabla_embalses_por_region,
    build_embalses_hierarchical_view,
    crear_tablas_jerarquicas_directas,
    build_hierarchical_table_view,
    get_tabla_regiones_embalses,
    create_collapsible_regions_table,
    create_embalse_table_columns,
    create_initial_embalse_table,
    create_dynamic_embalse_table,
    create_data_table,
    create_region_filtered_participacion_table,
    create_region_filtered_capacidad_table,
)
from .charts import (
    create_line_chart, create_bar_chart,
    create_total_timeline_chart, create_stats_summary,
)
from .maps import crear_mapa_embalses_por_region, crear_mapa_embalses_directo
from .kpis import (
    crear_fichas_sin_seguras, crear_fichas_temporales, crear_fichas_sin,
    crear_panel_controles, crear_ficha_kpi_inicial,
    create_latest_value_kpi, create_porcapor_kpi,
)

@callback(
    Output("ficha-kpi-container", "children"),
    Input("btn-actualizar-hidrologia", "n_clicks"),
    Input('rango-fechas-hidrologia', 'value'),
    State('fecha-inicio-hidrologia', 'date'),
    State('fecha-fin-hidrologia', 'date'),
    State("region-dropdown", "value"),
    State("rio-dropdown", "value"),
    prevent_initial_call=False
)
def update_ficha_kpi(n_clicks, rango, start_date, end_date, region, rio):
    """Actualiza solo la ficha KPI sin tocar el resto del layout - FILTRA POR REGIÓN/RÍO"""
    # Calcular fechas según el rango seleccionado
    fecha_fin = date.today()
    
    if rango == '1m':
        fecha_inicio = fecha_fin - timedelta(days=30)
    elif rango == '6m':
        fecha_inicio = fecha_fin - timedelta(days=180)
    elif rango == '1y':
        fecha_inicio = fecha_fin - timedelta(days=365)
    elif rango == '2y':
        fecha_inicio = fecha_fin - timedelta(days=730)
    elif rango == '5y':
        fecha_inicio = fecha_fin - timedelta(days=1825)
    elif rango == 'custom' and start_date and end_date:
        fecha_inicio = datetime.strptime(start_date, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        # Por defecto: último año
        fecha_inicio = fecha_fin - timedelta(days=365)
    
    start_date_str = fecha_inicio.strftime('%Y-%m-%d')
    end_date_str = fecha_fin.strftime('%Y-%m-%d')
    
    try:
        # Calcular porcentaje vs histórico
        data, _ = obtener_datos_inteligente('AporEner', 'Rio', start_date_str, end_date_str)
        if data is None or data.empty:
            logger.warning(f"⚠️ Ficha KPI: No hay datos para {start_date_str} a {end_date_str}")
            return html.Div()
        
        # ✅ FILTRAR POR REGIÓN O RÍO
        data_filtrada = data.copy()
        texto_filtro = "Nacional"
        
        if rio and rio != "":
            # Filtrar por río específico
            data_filtrada = data_filtrada[data_filtrada['Name'].str.upper() == rio.upper()]
            texto_filtro = rio.title()
            logger.info(f"📊 Ficha KPI: Filtrando por río {rio}")
        elif region and region != "__ALL_REGIONS__":
            # Filtrar por región
            rio_region = ensure_rio_region_loaded()
            data_filtrada['Region'] = data_filtrada['Name'].map(rio_region)
            region_normalizada = region.strip().upper()
            data_filtrada = data_filtrada[data_filtrada['Region'].str.upper() == region_normalizada]
            texto_filtro = region.title()
            logger.info(f"📊 Ficha KPI: Filtrando por región {region}")
        
        if data_filtrada.empty:
            logger.warning(f"⚠️ Ficha KPI: Sin datos después de filtrar")
            return html.Div()
        
        total_real = data_filtrada['Value'].sum()
        
        # Obtener media histórica usando el mismo rango de fechas Y APLICAR EL MISMO FILTRO
        media_hist_data, _ = obtener_datos_inteligente('AporEnerMediHist', 'Rio', start_date_str, end_date_str)
        
        if media_hist_data is not None and not media_hist_data.empty:
            # Aplicar el mismo filtro a la media histórica
            media_hist_filtrada = media_hist_data.copy()
            
            if rio and rio != "":
                media_hist_filtrada = media_hist_filtrada[media_hist_filtrada['Name'].str.upper() == rio.upper()]
            elif region and region != "__ALL_REGIONS__":
                rio_region = ensure_rio_region_loaded()
                media_hist_filtrada['Region'] = media_hist_filtrada['Name'].map(rio_region)
                region_normalizada = region.strip().upper()
                media_hist_filtrada = media_hist_filtrada[media_hist_filtrada['Region'].str.upper() == region_normalizada]
            
            total_historico = media_hist_filtrada['Value'].sum()
            porcentaje_vs_historico = (total_real / total_historico * 100) if total_historico > 0 else None
        else:
            logger.warning(f"⚠️ Ficha KPI: No hay media histórica")
            porcentaje_vs_historico = None
        
        if porcentaje_vs_historico is None:
            logger.warning(f"⚠️ Ficha KPI: porcentaje_vs_historico es None")
            return html.Div()
        
        logger.info(f"✅ Ficha KPI actualizada ({texto_filtro}): {porcentaje_vs_historico - 100:+.1f}%")
        # Crear ficha compacta CON BOTÓN DE INFORMACIÓN Y TEXTO DINÁMICO
        return dbc.Card([
            dbc.CardBody([
                # Botón de información en esquina superior derecha
                html.Button(
                    "ℹ",
                    id="btn-info-ficha-kpi",
                    style={
                        'width': '28px', 
                        'height': '28px', 
                        'borderRadius': '50%',
                        'backgroundColor': '#F2C330',
                        'color': '#2C3E50',
                        'fontSize': '16px',
                        'fontWeight': 'bold',
                        'border': '2px solid #2C3E50',
                        'cursor': 'pointer',
                        'position': 'absolute', 
                        'top': '6px', 
                        'right': '6px',
                        'zIndex': '10',
                        'boxShadow': '0 4px 12px rgba(0,0,0,0.4), 0 0 0 2px rgba(242,195,48,0.3)',
                        'transition': 'all 0.3s ease',
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'center',
                        'animation': 'pulse 2s ease-in-out infinite'
                    },
                    title="Información del indicador"
                ),
                
                html.Div([
                    html.I(className="fas fa-tint", style={'color': "#28a745" if porcentaje_vs_historico >= 100 
                                                       else "#dc3545" if porcentaje_vs_historico < 90
                                                       else "#17a2b8", 'fontSize': '1.2rem', 'marginRight': '8px'}),
                    html.Div([
                        html.Span(f"Estado 2025 - {texto_filtro}", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.75rem', 'display': 'block'}),
                        html.Span(
                            f"{porcentaje_vs_historico - 100:+.1f}%",
                            style={'fontWeight': 'bold', 'fontSize': '1.6rem', 
                                   'color': "#28a745" if porcentaje_vs_historico >= 100 
                                           else "#dc3545" if porcentaje_vs_historico < 90
                                           else "#17a2b8", 'display': 'block', 'lineHeight': '1.2'}),
                        html.Span("vs Histórico", style={'color': '#666', 'fontSize': '0.75rem', 'display': 'block'})
                    ], style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'flex-start'})
                ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'})
            ], style={'padding': '0.5rem', 'position': 'relative'})
        ], className="shadow-sm border-0", style={"borderLeft": "4px solid " + (
            "#28a745" if porcentaje_vs_historico >= 100 
            else "#dc3545" if porcentaje_vs_historico < 90
            else "#17a2b8"
        ), "height": "100%"})
        
    except Exception as e:
        logger.error(f"❌ Error actualizando ficha KPI: {e}")
        return html.Div()

# Callback para manejar tabs


@callback(
    Output("hidrologia-tab-content", "children"),
    Input("hidro-tabs", "active_tab")
)
def render_hidro_tab_content(active_tab):
    logger.info(f"🎯 render_hidro_tab_content ejecutándose: active_tab={active_tab}")
    if active_tab == "tab-consulta":
        # Mostrar por defecto la gráfica y tablas de embalse junto con las fichas KPI
        # Usar el rango por defecto: 1 año (365 días) para coincidir con dropdown
        fecha_final = date.today()
        fecha_inicio = fecha_final - timedelta(days=365)  # 1 año - coincide con dropdown value='1y'
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
        fecha_final_str = fecha_final.strftime('%Y-%m-%d')
        # Importante: show_default_view requiere start_date y end_date
        try:
            # Usar la función auxiliar definida en update_content
            # Debemos replicar la lógica aquí para obtener el contenido por defecto
            def show_default_view(start_date, end_date):
                objetoAPI = get_objetoAPI()
                es_valido, mensaje = validar_rango_fechas(start_date, end_date)
                
                # Mensaje informativo si hay advertencia (no bloquea)
                mensaje_info = None
                if mensaje and mensaje != "Rango de fechas válido":
                    mensaje_info = dbc.Alert(mensaje, color="info", className="mb-2")
                
                if not es_valido:
                    return dbc.Alert(mensaje, color="warning", className="text-start")
                try:
                    # ✅ OPTIMIZADO: Consulta inteligente PostgreSQL (>=2020) vs API (<2020)
                    # La conversión kWh→GWh se hace automáticamente
                    data, warning_msg = obtener_datos_inteligente('AporEner', 'Rio', start_date, end_date)
                    if warning_msg:
                        logger.info(f"⚠️ {warning_msg}")
                    
                    if data is None or data.empty:
                        return dbc.Alert([
                            html.H6("Sin datos", className="alert-heading"),
                            html.P(f"No hay datos disponibles para el período {start_date} a {end_date}."),
                            html.Hr(),
                            html.P("Intente con fechas más recientes.", className="mb-0")
                        ], color="warning", className="text-start")
                    rio_region = ensure_rio_region_loaded()
                    data['Region'] = data['Name'].map(rio_region)
                    if 'Name' in data.columns and 'Value' in data.columns:
                        region_df = data.groupby(['Region', 'Date'])['Value'].sum().reset_index()
                        region_df = region_df[region_df['Region'].notna()]
                        
                        # Obtener datos completos de embalses CON PARTICIPACIÓN para mapa y tabla
                        regiones_totales, df_completo_embalses = get_tabla_regiones_embalses(start_date, end_date)
                        
                        # CORRECCIÓN: Pasar datos originales (con columna Name) para que la función
                        # create_total_timeline_chart pueda obtener media histórica por río
                        
                        # LAYOUT HORIZONTAL OPTIMIZADO: 67%-33% (sin tabla visible)
                        return html.Div([
                            html.H5("🇨🇴 Evolución Temporal de Aportes de Energía", className="text-center mb-2"),
                            html.P("Vista general: Gráfica temporal y mapa. Haga clic en ℹ️ para ver tabla de embalses.", className="text-center text-muted mb-2", style={"fontSize": "0.85rem"}),
                            
                            dbc.Row([
                                # COLUMNA 1: Gráfica Temporal (67%)
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H6("📈 Evolución Temporal", className="text-center mb-1", style={'fontSize': '0.9rem'}),
                                            create_total_timeline_chart(
                                                agregar_datos_hidrologia_inteligente(
                                                    data.copy(), 
                                                    (pd.to_datetime(data['Date'].max()) - pd.to_datetime(data['Date'].min())).days
                                                ) if not data.empty else data,
                                                "Aportes nacionales"
                                            )
                                        ], className="p-1")
                                    ], className="h-100")
                                ], md=8),
                                
                                # COLUMNA 2: Mapa de Colombia con Popover de Embalses (33%)
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.Div([
                                                html.H6("🗺️ Mapa de Embalses", className="text-center mb-1 d-inline", style={'fontSize': '0.9rem'}),
                                                html.I(
                                                    id="btn-info-mapa-embalses",
                                                    className="fas fa-info-circle ms-2",
                                                    style={'color': '#17a2b8', 'cursor': 'pointer', 'fontSize': '1rem'}
                                                ),
                                                dbc.Popover(
                                                    [
                                                        dbc.PopoverHeader("📊 Tabla de Embalses"),
                                                        dbc.PopoverBody([
                                                            dash_table.DataTable(
                                                                id="tabla-embalses-inicial",
                                                                data=get_embalses_completa_para_tabla(None, start_date, end_date, embalses_df_preconsultado=df_completo_embalses),
                                                                columns=[
                                                                    {"name": "Embalse", "id": "Embalse"},
                                                                    {"name": "Part.", "id": "Participación (%)"},
                                                                    {"name": "Vol.", "id": "Volumen Útil (%)"},
                                                                    {"name": "⚠️", "id": "Riesgo"}
                                                                ],
                                                                style_cell={'textAlign': 'left', 'padding': '4px', 'fontSize': '0.7rem'},
                                                                style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold', 'fontSize': '0.7rem', 'padding': '4px'},
                                                                style_data_conditional=[
                                                                    {'if': {'filter_query': '{Riesgo} = "🔴"'}, 'backgroundColor': '#ffe6e6'},
                                                                    {'if': {'filter_query': '{Riesgo} = "🟡"'}, 'backgroundColor': '#fff9e6'},
                                                                    {'if': {'filter_query': '{Riesgo} = "🟢"'}, 'backgroundColor': '#e6ffe6'},
                                                                    {'if': {'filter_query': '{Embalse} = "TOTAL"'}, 'backgroundColor': '#e3f2fd', 'fontWeight': 'bold'}
                                                                ],
                                                                page_action="none",
                                                                style_table={'maxHeight': '400px', 'overflowY': 'auto', 'width': '100%'}
                                                            )
                                                        ], style={'padding': '10px'})
                                                    ],
                                                    id="popover-tabla-embalses",
                                                    target="btn-info-mapa-embalses",
                                                    trigger="click",
                                                    placement="left",
                                                    style={'maxWidth': '500px'}
                                                )
                                            ], className="text-center mb-1"),
                                            html.Div([
                                                crear_mapa_embalses_directo(
                                                    regiones_totales,
                                                    df_completo_embalses
                                                )
                                            ])
                                        ], className="p-1")
                                    ], className="h-100")
                                ], md=4)
                            ])
                        ])
                except Exception as e:
                    return dbc.Alert([
                        html.H6("Error cargando datos", className="alert-heading"),
                        html.P(str(e)),
                    ], color="danger", className="text-start")
            resultados_embalse = show_default_view(fecha_inicio_str, fecha_final_str)
        except Exception as e:
            resultados_embalse = dbc.Alert([
                html.H6("Error cargando datos", className="alert-heading"),
                html.P(str(e)),
            ], color="danger", className="text-start")
        return html.Div([
            # LAYOUT HORIZONTAL: Panel de controles (70%) + Ficha KPI dinámica (30%)
            dbc.Row([
                dbc.Col([crear_panel_controles()], md=9),
                dbc.Col([html.Div(id="ficha-kpi-container", children=[crear_ficha_kpi_inicial()])], md=3)
            ], className="g-2 mb-3 align-items-start"),
            
            # Contenido dinámico (gráficas, mapas, tablas)
            dcc.Loading(
                id="loading-hidro",
                type="circle",
                children=html.Div([
                    html.Div(id="hidro-results-content-dynamic", className="mt-2", children=resultados_embalse)
                ], id="hidro-results-content", className="mt-2"),
                color=COLORS['primary'],
                loading_state={'is_loading': False}
            )
        ])
    elif active_tab == "tab-analisis":
        return html.Div([
            dbc.Card([
                dbc.CardBody([
                    html.H4([
                        html.I(className="fas fa-chart-area me-2", style={"color": COLORS['primary']}),
                        "Análisis Hidrológico Avanzado"
                    ], className="mb-4"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("Análisis de Variabilidad", className="mb-3"),
                                    html.P("Análisis estadístico de variabilidad de aportes energéticos por región y temporada.", className="text-muted")
                                ])
                            ], className="h-100")
                        ], md=6),
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("Correlaciones Energéticas", className="mb-3"),
                                    html.P("Contribución energética de cada región a la generación hidroeléctrica del país.", className="text-muted")
                                ])
                            ], className="h-100")
                        ], md=6)
                    ])
                ])
            ], className="shadow-sm")
        ])
    elif active_tab == "tab-comparacion-anual":
        # Nueva sección de Comparación Anual - ESTRUCTURA IDÉNTICA A GENERACIÓN
        return html.Div([
            
            # FILTRO MULTISELECTOR DE AÑOS
            crear_filter_bar(
                html.Span("AÑOS:", className="t-filter-label"),
                html.Div(
                    dcc.Dropdown(
                        id='years-multiselector-hidro',
                        options=[{'label': str(y), 'value': y} for y in range(2021, 2026)],
                        value=[2024, 2025],
                        multi=True,
                        placeholder="Selecciona años...",
                        clearable=False,
                        style={"width": "300px", "fontSize": "0.8rem"}
                    )
                ),
                html.Button(
                    "Actualizar Comparación",
                    id='btn-actualizar-comparacion-hidro',
                    className="t-btn-filter"
                ),
            ),
            
            # LAYOUT HORIZONTAL: Gráfica de líneas (70%) + Fichas por año (30%)
            dbc.Row([
                # COLUMNA IZQUIERDA: Gráfica de líneas temporales
                dbc.Col([
                    dcc.Loading(
                        id="loading-grafica-lineas-hidro",
                        type="default",
                        children=html.Div([
                            html.H6("Evolución Temporal de Volúmenes de Embalses por Año", className="text-center mb-2",
                                   style={'fontWeight': '600', 'color': '#2c3e50', 'fontSize': '0.85rem'}),
                            dcc.Graph(id='grafica-lineas-temporal-hidro', config={'displayModeBar': False})
                        ])
                    )
                ], md=8, className="pe-2"),
                
                # COLUMNA DERECHA: Fichas por año (scroll vertical si hay muchos años)
                dbc.Col([
                    html.H6("Resumen por Año", className="text-center mb-2",
                           style={'fontWeight': '600', 'color': '#2c3e50', 'fontSize': '0.85rem'}),
                    dcc.Loading(
                        id="loading-embalses-anuales",
                        type="default",
                        children=html.Div(
                            id='contenedor-embalses-anuales',
                            style={'maxHeight': '500px', 'overflowY': 'auto'}
                        )
                    )
                ], md=4, className="ps-2")
            ], className="mb-4")
        ])
    elif active_tab == "tab-tendencias":
        return html.Div([
            dbc.Card([
                dbc.CardBody([
                    html.H4([
                        html.I(className="fas fa-trending-up me-2", style={"color": COLORS['primary']}),
                        "Tendencias Climáticas e Hidrológicas"
                    ], className="mb-4"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("Variabilidad Climática", className="mb-3"),
                                    html.P("Análisis de patrones climáticos y su impacto en los recursos hídricos.", className="text-muted")
                                ])
                            ], className="h-100")
                        ], md=6),
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("📈 Proyecciones Futuras", className="mb-3"),
                                    html.P("Modelos predictivos para planificación de recursos hídricos.", className="text-muted")
                                ])
                            ], className="h-100")
                        ], md=6)
                    ])
                ])
            ], className="shadow-sm")
        ])
    else:
        return html.Div([
            crear_panel_controles(),
            html.Div(id="hidro-results-content", className="mt-4")
        ])

# Callback para actualizar ríos según región seleccionada


@callback(
    Output("rio-dropdown", "options"),
    [Input("region-dropdown", "value")]
)
def update_rio_options(region):
    # Si se selecciona "Todas las regiones", mostrar todos los ríos disponibles
    if region == "__ALL_REGIONS__":
        rios_region = get_rio_options()  # Obtener todos los ríos sin filtro de región
    else:
        rios_region = get_rio_options(region)
    
    options = [{"label": "Todos los ríos", "value": "__ALL__"}]
    options += [{"label": r, "value": r} for r in rios_region]
    return options


# ===== CALLBACK ELIMINADO - Las fichas KPI ahora están en la página de Generación =====
# El callback update_fichas_kpi ha sido removido ya que las fichas de 
# Reservas Hídricas y Aportes Hídricos ahora se muestran en pages/generacion.py
# ===================================================================================


# ============================================================================
# FUNCIÓN PARA CREAR MAPA DE EMBALSES (Nivel de módulo - accesible globalmente)
# ============================================================================


@callback(
    Output("hidro-results-content-dynamic", "children"),
    [Input("btn-actualizar-hidrologia", "n_clicks")],
    [State("rio-dropdown", "value"),
     State("fecha-inicio-hidrologia", "date"),
     State("fecha-fin-hidrologia", "date"),
     State("region-dropdown", "value")]
)
def update_content(n_clicks, rio, start_date, end_date, region):
    # Debug básico del callback
    if n_clicks and n_clicks > 0:
        pass # print(f"📊 Consultando datos: región={region}, río={rio}, fechas={start_date} a {end_date}")

    # ✅ FIX CRÍTICO: Normalizar región con .upper() para coincidir con RIO_REGION
    region_normalized = region.strip().upper() if region and region != "__ALL_REGIONS__" else region
    
    # ===== FUNCIÓN MOVIDA A NIVEL DE MÓDULO (ver línea ~1918) =====
    # La función crear_mapa_embalses_directo ahora está definida a nivel de módulo
    # para que sea accesible desde múltiples callbacks (update_content y render_hidro_tab_content)
    # ===============================================================
    
    # Función auxiliar para mostrar la vista por defecto (panorámica nacional)
    def show_default_view(start_date, end_date):
        objetoAPI = get_objetoAPI()
        # Validar rango de fechas
        es_valido, mensaje = validar_rango_fechas(start_date, end_date)
        
        # Mensaje informativo si hay advertencia (no bloquea)
        mensaje_info = None
        if mensaje and mensaje != "Rango de fechas válido":
            mensaje_info = dbc.Alert(mensaje, color="info", className="mb-2")
        
        if not es_valido:
            return dbc.Alert(mensaje, color="warning", className="text-start")
        
        try:
            # ✅ OPTIMIZADO: Consulta inteligente PostgreSQL (>=2020) vs API (<2020)
            # La conversión kWh→GWh se hace automáticamente
            data, warning_msg = obtener_datos_inteligente('AporEner', 'Rio', start_date, end_date)
            if warning_msg:
                logger.info(f"⚠️ {warning_msg}")
            
            if data is None or data.empty:
                return dbc.Alert([
                    html.H6("Sin datos", className="alert-heading"),
                    html.P(f"No hay datos disponibles para el período {start_date} a {end_date}."),
                    html.Hr(),
                    html.P("Intente con fechas más recientes.", className="mb-0")
                ], color="warning", className="text-start")
            # Calcular porcentaje vs histórico para la ficha KPI
            porcentaje_vs_historico = None
            total_real = None
            total_historico = None
            try:
                # CORRECCIÓN: Sumar todos los aportes del período (acumulativo)
                daily_totals_real = data.groupby('Date')['Value'].sum().reset_index()
                total_real = daily_totals_real['Value'].sum()  # SUMA TOTAL, no promedio
                
                # Obtener media histórica y agrupar por fecha
                media_hist_data, _ = obtener_datos_inteligente('AporEnerMediHist', 'Rio', start_date, end_date)
                if media_hist_data is not None and not media_hist_data.empty:
                    # Agrupar media histórica por fecha y sumar
                    daily_totals_hist = media_hist_data.groupby('Date')['Value'].sum().reset_index()
                    total_historico = daily_totals_hist['Value'].sum()  # SUMA TOTAL, no promedio
                    if total_historico > 0:
                        # ✅ FIX CRÍTICO: Convertir a float Python nativo inmediatamente después del cálculo
                        # Esto previene que numpy.float64 cause problemas en f-strings
                        porcentaje_vs_historico = float((total_real / total_historico) * 100)
                        logger.debug(f"Ficha KPI - Comparación: Real total={float(total_real):.2f} GWh vs Histórico={float(total_historico):.2f} GWh ({porcentaje_vs_historico:.1f}%)")
            except Exception as e:
                logger.warning(f"No se pudo calcular porcentaje vs histórico: {e}")
            
            # Agregar información de región
            rio_region = ensure_rio_region_loaded()
            data['Region'] = data['Name'].map(rio_region)
            if 'Name' in data.columns and 'Value' in data.columns:
                # Agrupar por región y fecha para crear series temporales
                region_df = data.groupby(['Region', 'Date'])['Value'].sum().reset_index()
                region_df = region_df[region_df['Region'].notna()]
                
                # 🔍 Buscar la última fecha con datos reales de embalses (no usar end_date ciegamente)
                fecha_embalse_obj = None
                try:
                    # Intentar con la fecha solicitada primero
                    df_vol_test, fecha_encontrada = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', 
                                                                                datetime.strptime(end_date, '%Y-%m-%d').date())
                    if fecha_encontrada:
                        fecha_embalse_obj = fecha_encontrada
                        logger.info(f"✅ Fecha real con datos de embalses: {fecha_embalse_obj}")
                    else:
                        # Si no hay datos para end_date, buscar hacia atrás
                        fecha_embalse_obj = datetime.strptime(end_date, '%Y-%m-%d').date() - timedelta(days=1)
                        logger.warning(f"⚠️ No hay datos para {end_date}, usando fecha anterior: {fecha_embalse_obj}")
                except Exception as e:
                    logger.error(f"❌ Error buscando fecha con datos: {e}")
                    fecha_embalse_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                fecha_embalse = fecha_embalse_obj.strftime('%Y-%m-%d') if fecha_embalse_obj else end_date
                
                # Obtener datos completos con participación para mapa y tabla
                regiones_totales, df_completo_embalses = get_tabla_regiones_embalses(fecha_embalse, fecha_embalse)
                
                # CREAR FICHA KPI (para colocarla junto al panel de controles)
                ficha_kpi = dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-tint", style={'color': "#28a745" if porcentaje_vs_historico and porcentaje_vs_historico >= 100 
                                                                   else "#dc3545" if porcentaje_vs_historico and porcentaje_vs_historico < 90
                                                                   else "#17a2b8", 'fontSize': '1.2rem', 'marginRight': '8px'}),
                                html.Div([
                                    html.Span("Estado 2025", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.8rem', 'display': 'block'}),
                                    html.Span(
                                        porcentaje_vs_historico is not None and f"{porcentaje_vs_historico - 100:+.1f}%" or "...",
                                        style={'fontWeight': 'bold', 'fontSize': '1.6rem', 
                                               'color': "#28a745" if porcentaje_vs_historico and porcentaje_vs_historico >= 100 
                                                       else "#dc3545" if porcentaje_vs_historico and porcentaje_vs_historico < 90
                                                       else "#17a2b8", 'display': 'block', 'lineHeight': '1.2'}),
                                    html.Span("vs Histórico", style={'color': '#666', 'fontSize': '0.75rem', 'display': 'block'})
                                ], style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'flex-start'})
                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'})
                        ], style={'padding': '0.5rem'})
                    ], className="shadow-sm border-0", style={"borderLeft": "4px solid " + (
                        "#28a745" if porcentaje_vs_historico and porcentaje_vs_historico >= 100 
                        else "#dc3545" if porcentaje_vs_historico and porcentaje_vs_historico < 90
                        else "#17a2b8"
                    ), "height": "100%"})
                ], md=3) if porcentaje_vs_historico is not None else None
                
                return html.Div([
                    html.H5("🇨🇴 Contribución Energética por Región Hidrológica de Colombia", className="text-center mb-1", style={"fontSize": "1rem"}),
                    html.P("Vista general: Gráfica temporal y mapa. Haga clic en ℹ️ para ver tabla de embalses.", className="text-center text-muted mb-0", style={"fontSize": "0.75rem"}),
                    
                    # LAYOUT HORIZONTAL OPTIMIZADO: Gráfica (67%) + Mapa (33%)
                    dbc.Row([
                        # COLUMNA 1: Gráfica Temporal (67%) - ✅ CON LOADING INDICATOR
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    # Encabezado con botón de info
                                    html.Div([
                                        html.H6("📈 Evolución Temporal", className="text-center mb-1", style={'fontSize': '0.9rem', 'display': 'inline-block', 'marginRight': '8px'}),
                                        html.Button(
                                            "ℹ",
                                            id="btn-info-humedad",
                                            style={
                                                'width': '26px',
                                                'height': '26px',
                                                'borderRadius': '50%',
                                                'backgroundColor': '#F2C330',
                                                'color': '#2C3E50',
                                                'fontSize': '14px',
                                                'fontWeight': 'bold',
                                                'border': '2px solid #2C3E50',
                                                'cursor': 'pointer',
                                                'boxShadow': '0 4px 12px rgba(0,0,0,0.4), 0 0 0 2px rgba(242,195,48,0.3)',
                                                'transition': 'all 0.3s ease',
                                                'display': 'inline-flex',
                                                'alignItems': 'center',
                                                'justifyContent': 'center',
                                                'verticalAlign': 'middle',
                                                'animation': 'pulse 2s ease-in-out infinite'
                                            },
                                            title="Información del sistema de humedad"
                                        )
                                    ], style={'textAlign': 'center', 'marginBottom': '4px'}),
                                    create_total_timeline_chart(data, "Aportes nacionales")
                                ], className="p-1")
                            ], className="h-100")
                        ], md=8),
                        
                        # COLUMNA 2: Mapa de Colombia con Popover (33%)
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    # Encabezado compacto con fecha y botones de info
                                    html.Div([
                                        html.Div([
                                            html.Small([
                                                html.I(className="fas fa-calendar-alt me-1", style={'fontSize': '0.65rem'}),
                                                f"Datos: {fecha_embalse}",
                                                html.Span(" | ", style={'color': '#999'}),
                                                html.I(className="fas fa-water me-1", style={'fontSize': '0.65rem'}),
                                                "25 Embalses"
                                            ], style={'fontSize': '0.65rem', 'color': '#666', 'fontWeight': '500'})
                                        ], style={'flex': '1'}),
                                        html.Div([
                                            html.I(
                                                id="btn-info-mapa-embalses-callback",
                                                className="fas fa-info-circle me-2",
                                                style={'color': '#17a2b8', 'cursor': 'pointer', 'fontSize': '1rem'}
                                            ),
                                            html.Button(
                                                "ℹ",
                                                id="btn-info-semaforo",
                                                style={
                                                    'width': '28px',
                                                    'height': '28px',
                                                    'borderRadius': '50%',
                                                    'backgroundColor': '#F2C330',
                                                    'color': '#2C3E50',
                                                    'fontSize': '16px',
                                                    'fontWeight': 'bold',
                                                    'border': '2px solid #2C3E50',
                                                    'cursor': 'pointer',
                                                    'boxShadow': '0 4px 12px rgba(0,0,0,0.4), 0 0 0 2px rgba(242,195,48,0.3)',
                                                    'transition': 'all 0.3s ease',
                                                    'display': 'flex',
                                                    'alignItems': 'center',
                                                    'justifyContent': 'center',
                                                    'animation': 'pulse 2s ease-in-out infinite'
                                                },
                                                title="Información del semáforo de riesgo"
                                            ),
                                            dbc.Popover(
                                                [
                                                    dbc.PopoverHeader("📊 Tabla de Embalses"),
                                                    dbc.PopoverBody([
                                                        html.P("Haga clic en ⊞/⊟ para expandir/contraer regiones", 
                                                               className="text-muted text-center mb-1", 
                                                               style={'fontSize': '0.65rem'}),
                                                        html.Div(
                                                            id="tabla-embalses-jerarquica-container",
                                                            children=[build_embalses_hierarchical_view(regiones_totales, df_completo_embalses, [])],
                                                            style={'maxHeight': '500px', 'overflowY': 'auto'}
                                                        )
                                                    ], style={'padding': '10px'})
                                                ],
                                                id="popover-tabla-embalses-callback",
                                                target="btn-info-mapa-embalses-callback",
                                                trigger="click",
                                                placement="left",
                                                style={'maxWidth': '600px'}
                                            )
                                        ], style={'display': 'flex', 'alignItems': 'center'})
                                    ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '4px'}),
                                    # Mapa sin loading indicator
                                    html.Div([
                                        crear_mapa_embalses_directo(regiones_totales, df_completo_embalses)
                                    ])
                                ], className="p-1")
                            ], className="h-100")
                        ], md=4)
                    ]),
                    
                    dcc.Store(id="region-data-store", data=data.to_dict('records')),
                    dcc.Store(id="embalses-completo-data", data=df_completo_embalses.to_dict('records')),
                    dcc.Store(id="embalses-regiones-data", data=regiones_totales.to_dict('records')),
                    dcc.Store(id="embalses-expandidos-store", data=[]),
                    
                    # Modal con información del Sistema Semáforo
                    dbc.Modal([
                        dbc.ModalHeader(dbc.ModalTitle("Sistema Semáforo de Riesgo Hidrológico"), close_button=True),
                        dbc.ModalBody([
                            html.P("Sistema que analiza cada embalse combinando dos factores críticos:"),
                            
                            html.H6("Factores de Análisis:", className="fw-bold mb-2 mt-3"),
                            html.Ul([
                                html.Li([
                                    html.Strong("Importancia Estratégica: "),
                                    "Participación en el sistema energético nacional. Embalses >10% son estratégicos."
                                ]),
                                html.Li([
                                    html.Strong("Disponibilidad Hídrica: "),
                                    "Volumen útil disponible por encima del nivel mínimo técnico."
                                ])
                            ]),
                            
                            html.H6("Clasificación:", className="fw-bold mb-2 mt-3"),
                            html.Ul([
                                html.Li([
                                    html.Span("●", style={'color': '#dc3545', 'fontSize': '1.2rem'}),
                                    " Riesgo Alto: Embalses estratégicos con volumen crítico (<30%)"
                                ]),
                                html.Li([
                                    html.Span("●", style={'color': '#ffc107', 'fontSize': '1.2rem'}),
                                    " Riesgo Medio: Embalses estratégicos con volumen bajo (30-70%)"
                                ]),
                                html.Li([
                                    html.Span("●", style={'color': '#198754', 'fontSize': '1.2rem'}),
                                    " Riesgo Bajo: Embalses con volumen adecuado (≥70%)"
                                ])
                            ])
                        ])
                    ], id="modal-semaforo", is_open=False, size="lg"),
                    
                    # Modal con información del Sistema de Humedad
                    dbc.Modal([
                        dbc.ModalHeader(dbc.ModalTitle("Sistema de Humedad vs Media Histórica"), close_button=True),
                        dbc.ModalBody([
                            html.P("La línea punteada de colores compara los aportes energéticos actuales con el promedio histórico del mismo período."),
                            
                            html.H6("Código de Colores:", className="fw-bold mb-2 mt-3"),
                            html.Ul([
                                html.Li([
                                    html.Span("●", style={'color': '#28a745', 'fontSize': '1.2rem'}),
                                    " Verde: ≥100% del histórico (condiciones húmedas)"
                                ]),
                                html.Li([
                                    html.Span("●", style={'color': '#17a2b8', 'fontSize': '1.2rem'}),
                                    " Cyan: 90-100% del histórico (condiciones normales)"
                                ]),
                                html.Li([
                                    html.Span("●", style={'color': '#ffc107', 'fontSize': '1.2rem'}),
                                    " Amarillo: 70-90% del histórico (moderadamente seco)"
                                ]),
                                html.Li([
                                    html.Span("●", style={'color': '#dc3545', 'fontSize': '1.2rem'}),
                                    " Rojo: <70% del histórico (muy seco)"
                                ])
                            ]),
                            
                            html.H6("Cómo Interpretar:", className="fw-bold mb-2 mt-3"),
                            html.Ul([
                                html.Li("La línea negra con puntos muestra los aportes reales de energía."),
                                html.Li("La línea punteada de colores es la media histórica del mismo período."),
                                html.Li("El color indica si estamos por encima (verde/cyan) o por debajo (amarillo/rojo) de lo normal."),
                                html.Li("Pasa el cursor sobre la línea para ver detalles de la comparación.")
                            ])
                        ])
                    ], id="modal-humedad", is_open=False, size="lg"),
                    
                    html.Hr(),

                ])
            else:
                return dbc.Alert("No se pueden procesar los datos obtenidos.", color="warning")
        except Exception as e:
            error_message = manejar_error_api(e, "consulta de vista general")
            return dbc.Alert([
                html.H6("Error en vista general", className="alert-heading"),
                html.Pre(error_message, style={"white-space": "pre-wrap", "font-family": "inherit"}),
                html.Hr(),
                html.P("Intente con un rango de fechas más reciente.", className="mb-0")
            ], color="danger", className="text-start")
    
    # Verificar si los filtros están vacíos o en valores por defecto
    filtros_vacios = (
        (region is None or region == "__ALL_REGIONS__") and 
        (rio is None or rio == "__ALL__")
    )
    
    # Si no se ha hecho clic, o faltan fechas, o todos los filtros están vacíos pero hay fechas
    if not n_clicks or not start_date or not end_date:
        # Mostrar datos por defecto de todas las regiones al cargar la página
        if start_date and end_date and not n_clicks:
            return show_default_view(start_date, end_date)
        else:
            return dbc.Alert("Selecciona una región, fechas y/o río, luego haz clic en Consultar.", color="info", className="text-center")
    
    # Si se hizo clic pero todos los filtros están vacíos, mostrar vista por defecto
    if filtros_vacios:
        return show_default_view(start_date, end_date)
    
    objetoAPI = get_objetoAPI()
    # Validar fechas antes de proceder
    es_valido, mensaje = validar_rango_fechas(start_date, end_date)
    
    # Mensaje informativo si hay advertencia (no bloquea)
    mensaje_info = None
    if mensaje and mensaje != "Rango de fechas válido":
        mensaje_info = dbc.Alert(mensaje, color="info", className="mb-2")
    
    if not es_valido:
        return dbc.Alert(mensaje, color="warning", className="text-start")

    try:
        # ✅ OPTIMIZADO: Consulta inteligente PostgreSQL (>=2020) vs API (<2020)
        # La conversión a GWh se hace automáticamente
        data, warning_msg = obtener_datos_inteligente('AporEner', 'Rio', start_date, end_date)
        if warning_msg:
            logger.info(f"⚠️ {warning_msg}")
        
        # LOGGING: Verificar que datos ya vienen en GWh
        if data is not None and not data.empty:
            logger.info(f"🔍 AporEner recibido: {len(data)} registros, Total: {data['Value'].sum():.2f} GWh")
        
        if data is None or data.empty:
            return dbc.Alert([
                html.H6("Sin datos disponibles", className="alert-heading"),
                html.P(f"No hay datos para el período {start_date} a {end_date} con los filtros seleccionados."),
                html.Hr(),
                html.P("Intente con fechas más recientes o diferentes filtros.", className="mb-0")
            ], color="warning", className="text-start")

        # Si hay un río específico seleccionado (y no es 'Todos los ríos'), mostrar la serie temporal diaria de ese río
        if rio and rio != "__ALL__":
            data_rio = data[data['Name'] == rio]
            if data_rio.empty:
                return dbc.Alert("No se encontraron datos para el río seleccionado.", color="warning")
            plot_df = data_rio.copy()
            if 'Date' in plot_df.columns and 'Value' in plot_df.columns:
                plot_df = plot_df[['Date', 'Value']].rename(columns={'Date': 'Fecha', 'Value': 'GWh'})
            return html.Div([
                html.H5(f"Río {rio} - Análisis de Aportes de Energía", className="text-center mb-2"),
                html.P(f"Río {rio}: Gráfica temporal y datos detallados.", className="text-center text-muted mb-2", style={"fontSize": "0.85rem"}),
                
                # LAYOUT HORIZONTAL COMPACTO
                dbc.Row([
                    # Gráfica Temporal (70%)
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6("📈 Evolución Temporal", className="text-center mb-1", style={'fontSize': '0.9rem'}),
                                create_line_chart(plot_df, rio_name=rio, start_date=start_date, end_date=end_date)
                            ], className="p-1")
                        ], className="h-100")
                    ], md=8),
                    
                    # Tabla de Datos (30%)
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6("📋 Datos Detallados", className="text-center mb-1", style={'fontSize': '0.9rem'}),
                                html.Div([
                                    create_data_table(plot_df)
                                ], style={'maxHeight': '500px', 'overflowY': 'auto'})
                            ], className="p-1")
                        ], className="h-100")
                    ], md=4)
                ])
            ])

        # Si no hay río seleccionado o es 'Todos los ríos', mostrar barra de contribución total por río
        # Si hay región seleccionada, filtrar por región, si no, mostrar todas las regiones
        rio_region = ensure_rio_region_loaded()
        data['Region'] = data['Name'].map(rio_region)
        
        # LOGGING: Ver datos ANTES de filtrar por región
        logger.info(f"🔍 ANTES filtro - Total data: {len(data)} registros, Suma: {data['Value'].sum():.2f} GWh")
        
        if region and region != "__ALL_REGIONS__":
            logger.info(f"🔍 [FILTRO REGIÓN] Filtrando región '{region_normalized}'")
            logger.info(f"🔍 Regiones únicas en data: {sorted(data['Region'].dropna().unique().tolist())}")
            data_filtered = data[data['Region'] == region_normalized]
            logger.info(f"🔍 DESPUÉS filtro - data_filtered: {len(data_filtered)} registros, Suma: {data_filtered['Value'].sum():.2f} GWh")
            title_suffix = f"en la región {region_normalized}"
            # Obtener datos frescos de embalses con la nueva columna
            embalses_df_fresh = get_embalses_capacidad(region_normalized, start_date, end_date)
            logger.debug(f"[DEBUG FILTRO] Embalses encontrados para región: {len(embalses_df_fresh) if not embalses_df_fresh.empty else 0}")
            
            # Guardar datos SIN formatear - las tablas harán el formateo
            embalses_df_formatted = embalses_df_fresh.copy() if not embalses_df_fresh.empty else pd.DataFrame()
                
            # Obtener embalses de la región específica
            try:
                objetoAPI = get_objetoAPI()
                # Usar fecha actual para obtener listado más reciente
                today = datetime.now().strftime('%Y-%m-%d')
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                embalses_info, warning = obtener_datos_inteligente('ListadoEmbalses','Sistema', yesterday, today)
                embalses_info['Values_Name'] = embalses_info['Values_Name'].str.strip().str.upper()
                embalses_info['Values_HydroRegion'] = embalses_info['Values_HydroRegion'].str.strip().str.upper()  # ✅ FIX: .upper() en lugar de .title()
                embalses_region = embalses_info[embalses_info['Values_HydroRegion'] == region_normalized]['Values_Name'].sort_values().unique()
            except Exception as e:
                logger.error(f"Error obteniendo embalses para el filtro: {e}", exc_info=True)
                embalses_region = []
        else:
            # Si no hay región específica o es "Todas las regiones", mostrar vista nacional
            if region == "__ALL_REGIONS__":
                # Mostrar la vista panorámica nacional igual que al cargar la página
                region_df = data.groupby(['Region', 'Date'])['Value'].sum().reset_index()
                region_df = region_df[region_df['Region'].notna()]  # Filtrar regiones válidas
                
                # Obtener datos completos de embalses con participación para vista nacional
                regiones_totales_nacional, embalses_df_nacional = get_tabla_regiones_embalses(start_date, end_date)
                
                return html.Div([
                    # LAYOUT HORIZONTAL: Panel de controles (70%) + Ficha KPI (30%)
                    dbc.Row([
                        dbc.Col([crear_panel_controles()], md=9),
                        dbc.Col([html.Div(id="ficha-kpi-container")], md=3)
                    ], className="g-2 mb-3 align-items-start"),
                    
                    html.H5("🇨🇴 Contribución Energética por Región Hidrológica de Colombia", className="text-center mb-2"),
                    html.P("Vista nacional: Gráfica temporal y mapa. Haga clic en ℹ️ para ver resumen.", className="text-center text-muted mb-2", style={"fontSize": "0.85rem"}),
                    
                    # LAYOUT HORIZONTAL OPTIMIZADO: Gráfica (67%) + Mapa (33%)
                    dbc.Row([
                        # COLUMNA 1: Gráfica Temporal (67%)
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("📈 Evolución Temporal Nacional", className="text-center mb-1", style={'fontSize': '0.9rem'}),
                                    create_total_timeline_chart(data, "Aportes totales nacionales")
                                ], className="p-1")
                            ], className="h-100")
                        ], md=8),
                        
                        # COLUMNA 2: Mapa de Colombia con Popover (33%)
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.H6("🗺️ Mapa Nacional", className="text-center mb-1 d-inline", style={'fontSize': '0.9rem'}),
                                        html.I(
                                            id="btn-info-mapa-nacional",
                                            className="fas fa-info-circle ms-2",
                                            style={'color': '#17a2b8', 'cursor': 'pointer', 'fontSize': '1rem'}
                                        ),
                                        dbc.Popover(
                                            [
                                                dbc.PopoverHeader("📊 Resumen Nacional"),
                                                dbc.PopoverBody([
                                                    html.Small(f"Total Regiones: {len(region_df['Region'].unique())}", className="d-block text-muted mb-1", style={'fontSize': '0.75rem'}),
                                                    html.Small(f"Total Embalses: {len(embalses_df_nacional) if not embalses_df_nacional.empty else 0}", className="d-block text-muted mb-1", style={'fontSize': '0.75rem'}),
                                                    html.Hr(className="my-1"),
                                                    html.Small("Haga clic en la gráfica para ver detalles por región", className="text-muted", style={'fontSize': '0.7rem'})
                                                ])
                                            ],
                                            id="popover-resumen-nacional",
                                            target="btn-info-mapa-nacional",
                                            trigger="click",
                                            placement="left"
                                        )
                                    ], className="text-center mb-1"),
                                    html.Div(id="mapa-embalses-nacional", children=[
                                        crear_mapa_embalses_directo(
                                            regiones_totales_nacional,
                                            embalses_df_nacional
                                        )
                                    ])
                                ], className="p-1")
                            ], className="h-100")
                        ], md=4)
                    ]),
                    
                    dcc.Store(id="region-data-store", data=data.to_dict('records'))
                ])
            
            data_filtered = data
            title_suffix = "- Todas las regiones"
            # Obtener datos frescos de embalses con la nueva columna  
            embalses_df_fresh = get_embalses_capacidad(None, start_date, end_date)
            # Guardar datos SIN formatear - las tablas harán el formateo
            embalses_df_formatted = embalses_df_fresh.copy() if not embalses_df_fresh.empty else pd.DataFrame()
                
            embalses_region = embalses_df_fresh['Embalse'].unique() if not embalses_df_fresh.empty else []

        if data_filtered.empty:
            return dbc.Alert("No se encontraron datos para la región seleccionada." if region else "No se encontraron datos.", color="warning")
        
        # Asegurar que embalses_df_formatted esté definido - SIN formatear
        if 'embalses_df_formatted' not in locals():
            embalses_df_formatted = embalses_df_fresh.copy() if not embalses_df_fresh.empty else pd.DataFrame()
            
        if 'Name' in data_filtered.columns and 'Value' in data_filtered.columns:
            # Para región específica, crear gráfica temporal de esa región
            if region and region != "__ALL_REGIONS__":
                # Para región específica, pasar datos SIN agregar para que create_total_timeline_chart
                # pueda hacer el filtrado correcto de la media histórica
                region_temporal_data = data_filtered[['Date', 'Name', 'Value']].copy()
                
                return html.Div([
                    html.H5(f"Aportes de Energía - Región {region_normalized}", className="text-center mb-2"),
                    html.P(f"Región {region_normalized}: Evolución temporal de generación hidroeléctrica.", className="text-center text-muted mb-2", style={"fontSize": "0.85rem"}),
                    
                    # LAYOUT HORIZONTAL OPTIMIZADO: Gráfica (75%) + Tabla (25%)
                    dbc.Row([
                        # COLUMNA 1: Gráfica Temporal (75% - expandida)
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("📈 Evolución Temporal", className="text-center mb-2", style={'fontSize': '0.9rem'}),
                                    create_total_timeline_chart(region_temporal_data, f"Aportes región {region_normalized}", region_filter=region_normalized)
                                ], className="p-2")
                            ], className="h-100")
                        ], md=9),
                        
                        # COLUMNA 2: Tabla Combinada de Embalses (25%)
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("📊 Embalses", className="text-center mb-2", style={'fontSize': '0.9rem'}),
                                    html.Div([
                                        dash_table.DataTable(
                                            id="tabla-embalses-region",
                                            data=get_embalses_completa_para_tabla(region, start_date, end_date, embalses_df_preconsultado=embalses_df_fresh),
                                            columns=[
                                                {"name": "Embalse", "id": "Embalse"},
                                                {"name": "Part.", "id": "Participación (%)"},
                                                {"name": "Vol.", "id": "Volumen Útil (%)"},
                                                {"name": "⚠️", "id": "Riesgo"}
                                            ],
                                            style_cell={'textAlign': 'left', 'padding': '4px', 'fontSize': '0.7rem'},
                                            style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold', 'fontSize': '0.7rem', 'padding': '4px'},
                                            style_data_conditional=[
                                                {'if': {'filter_query': '{Riesgo} = "🔴"'}, 'backgroundColor': '#ffe6e6'},
                                                {'if': {'filter_query': '{Riesgo} = "🟡"'}, 'backgroundColor': '#fff9e6'},
                                                {'if': {'filter_query': '{Riesgo} = "🟢"'}, 'backgroundColor': '#e6ffe6'},
                                                {'if': {'filter_query': '{Embalse} = "TOTAL"'}, 'backgroundColor': '#e3f2fd', 'fontWeight': 'bold'}
                                            ],
                                            page_action="none",
                                            style_table={'maxHeight': '480px', 'overflowY': 'auto'}
                                        )
                                    ])
                                ], className="p-2")
                            ], className="h-100")
                        ], md=3)
                    ], className="mb-3"),
                    
                    dcc.Store(id="region-data-store", data=data_filtered.to_dict('records')),
                    dcc.Store(id="embalse-cap-data", data=embalses_df_formatted.to_dict('records')),
                    dcc.Store(id="participacion-data", data=get_participacion_embalses(embalses_df_fresh).to_dict('records')),
                    
                    # ✅ Desplegable del semáforo eliminado (ya no es necesario)
                    dbc.Collapse(
                        dbc.Row([
                            dbc.Col([
                                dbc.Card([
                                    dbc.CardHeader([
                                        html.I(className="fas fa-traffic-light me-2", style={"color": "#28a745"}),
                                        html.Strong("🚦 Sistema Inteligente de Semáforo de Riesgo Hidrológico")
                                    ], style={"background": "linear-gradient(135deg, #e8f5e8 0%, #f3f4f6 100%)",
                                             "border": "none", "borderRadius": "8px 8px 0 0"}),
                                    dbc.CardBody([
                                        html.P("Este sistema evalúa automáticamente el riesgo operativo de cada embalse mediante un análisis inteligente que combina:", 
                                              className="mb-3", style={"fontSize": "0.9rem"}),
                                        
                                        dbc.Row([
                                            dbc.Col([
                                                html.Div([
                                                    html.H6("� Importancia Estratégica", className="text-primary mb-2"),
                                                    html.P("¿Qué tan crítico es este embalse para el sistema energético nacional?", 
                                                          className="text-muted", style={"fontSize": "0.85rem"}),
                                                    html.Ul([
                                                        html.Li("Embalses grandes (≥10% participación): Estratégicos", style={"fontSize": "0.8rem"}),
                                                        html.Li("Embalses pequeños (<10% participación): Locales", style={"fontSize": "0.8rem"})
                                                    ])
                                                ])
                                            ], md=6),
                                            dbc.Col([
                                                html.Div([
                                                    html.H6("� Estado del Recurso Hídrico", className="text-info mb-2"),
                                                    html.P("¿Cuánta agua útil tiene disponible para generar energía?", 
                                                          className="text-muted", style={"fontSize": "0.85rem"}),
                                                    html.Ul([
                                                        html.Li("Crítico: <30% del volumen útil", style={"fontSize": "0.8rem"}),
                                                        html.Li("Precaución: 30-70% del volumen útil", style={"fontSize": "0.8rem"}),
                                                        html.Li("Óptimo: ≥70% del volumen útil", style={"fontSize": "0.8rem"})
                                                    ])
                                                ])
                                            ], md=6)
                                        ], className="mb-3"),
                                        
                                        html.Hr(),
                                        html.H6("🎯 Resultados del Análisis:", className="mb-2"),
                                        dbc.Row([
                                            dbc.Col([
                                                html.Div([
                                                    html.Span("�", style={"fontSize": "1.5rem"}),
                                                    html.Strong(" ALTO RIESGO", className="ms-2", style={"color": "#dc3545"}),
                                                    html.Br(),
                                                    html.Small("Embalse estratégico + Agua crítica", className="text-danger fw-bold")
                                                ], className="text-center p-2 border border-danger rounded")
                                            ], md=4),
                                            dbc.Col([
                                                html.Div([
                                                    html.Span("🟡", style={"fontSize": "1.5rem"}),
                                                    html.Strong(" RIESGO MEDIO", className="ms-2", style={"color": "#ffc107"}),
                                                    html.Br(),
                                                    html.Small("Situaciones intermedias", className="text-warning fw-bold")
                                                ], className="text-center p-2 border border-warning rounded")
                                            ], md=4),
                                            dbc.Col([
                                                html.Div([
                                                    html.Span("🟢", style={"fontSize": "1.5rem"}),
                                                    html.Strong(" BAJO RIESGO", className="ms-2", style={"color": "#198754"}),
                                                    html.Br(),
                                                    html.Small("Agua suficiente disponible", className="text-success fw-bold")
                                                ], className="text-center p-2 border border-success rounded")
                                            ], md=4)
                                        ])
                                    ], className="p-3")
                                ], className="card-modern mb-4")
                            ], md=12)
                        ]),
                        id="collapse-semaforo-region-info",
                        is_open=False
                    )
                ])
            else:
                # Para caso sin región específica o vista general, mostrar también gráfica temporal
                # ✅ FIX: NO agrupar aquí - pasar datos originales con columna 'Name' para que create_total_timeline_chart
                # pueda obtener la media histórica por río correctamente
                national_temporal_data = data_filtered.groupby('Date')['Value'].sum().reset_index()
                national_temporal_data['Region'] = 'Nacional'
                
                # ✅ FIX CRÍTICO: Obtener datos CORRECTOS de embalses para el mapa
                # El mapa necesita: regiones_totales (totales por región) y df_completo_embalses (lista de embalses)
                fecha_para_mapa = end_date if end_date else datetime.now().strftime('%Y-%m-%d')
                regiones_totales_mapa, df_completo_embalses_mapa = get_tabla_regiones_embalses(fecha_para_mapa, fecha_para_mapa)
                
                return html.Div([
                    html.H5(f"🇨🇴 Evolución Temporal de Aportes de Energía", className="text-center mb-2"),
                    html.P(f"Vista general: Gráfica temporal y mapa. Haga clic en ℹ️ para ver tabla de embalses.", className="text-center text-muted mb-2", style={"fontSize": "0.85rem"}),
                    
                    # LAYOUT HORIZONTAL OPTIMIZADO: Gráfica (67%) + Mapa (33%)
                    dbc.Row([
                        # COLUMNA 1: Gráfica Temporal (67%)
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("📈 Evolución Temporal", className="text-center mb-1", style={'fontSize': '0.9rem'}),
                                    create_total_timeline_chart(data_filtered, "Aportes nacionales")
                                ], className="p-1")
                            ], className="h-100")
                        ], md=8),
                        
                        # COLUMNA 2: Mapa de Colombia con Popover (33%)
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.H6("🗺️ Mapa de Embalses", className="text-center mb-1 d-inline", style={'fontSize': '0.9rem'}),
                                        html.I(
                                            id="btn-info-mapa-embalses-general",
                                            className="fas fa-info-circle ms-2",
                                            style={'color': '#17a2b8', 'cursor': 'pointer', 'fontSize': '1rem'}
                                        ),
                                        dbc.Popover(
                                            [
                                                dbc.PopoverHeader("📊 Tabla de Embalses"),
                                                dbc.PopoverBody([
                                                    dash_table.DataTable(
                                                        id="tabla-embalses-general",
                                                        data=get_embalses_completa_para_tabla(None, start_date, end_date, embalses_df_preconsultado=df_completo_embalses_mapa),
                                                        columns=[
                                                            {"name": "Embalse", "id": "Embalse"},
                                                            {"name": "Part.", "id": "Participación (%)"},
                                                            {"name": "Vol.", "id": "Volumen Útil (%)"},
                                                            {"name": "⚠️", "id": "Riesgo"}
                                                        ],
                                                        style_cell={'textAlign': 'left', 'padding': '4px', 'fontSize': '0.7rem'},
                                                        style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold', 'fontSize': '0.7rem', 'padding': '4px'},
                                                        style_data_conditional=[
                                                            {'if': {'filter_query': '{Riesgo} = "🔴"'}, 'backgroundColor': '#ffe6e6'},
                                                            {'if': {'filter_query': '{Riesgo} = "🟡"'}, 'backgroundColor': '#fff9e6'},
                                                            {'if': {'filter_query': '{Riesgo} = "🟢"'}, 'backgroundColor': '#e6ffe6'},
                                                            {'if': {'filter_query': '{Embalse} = "TOTAL"'}, 'backgroundColor': '#e3f2fd', 'fontWeight': 'bold'}
                                                        ],
                                                        page_action="none",
                                                        style_table={'maxHeight': '400px', 'overflowY': 'auto', 'width': '100%'}
                                                    )
                                                ], style={'padding': '10px'})
                                            ],
                                            id="popover-tabla-embalses-general",
                                            target="btn-info-mapa-embalses-general",
                                            trigger="click",
                                            placement="left",
                                            style={'maxWidth': '500px'}
                                        )
                                    ], className="text-center mb-1"),
                                    html.Div(id="mapa-embalses-general", children=[
                                        crear_mapa_embalses_directo(
                                            regiones_totales_mapa,
                                            df_completo_embalses_mapa
                                        )
                                    ])
                                ], className="p-1")
                            ], className="h-100")
                        ], md=4)
                    ]),
                    
                    dcc.Store(id="region-data-store", data=data_filtered.to_dict('records')),
                    dcc.Store(id="embalse-cap-data", data=embalses_df_formatted.to_dict('records')),
                    dcc.Store(id="participacion-data", data=get_participacion_embalses(embalses_df_fresh).to_dict('records'))
                ])
        else:
            return dbc.Alert("No se pueden graficar los datos de la región." if region else "No se pueden graficar los datos.", color="warning")
    except Exception as e:
        # ✅ FIX: Log completo del error con traceback
        import traceback
        logger.error(f"❌ ERROR EN UPDATE_CONTENT: {str(e)}")
        logger.error(f"❌ TRACEBACK COMPLETO:\n{traceback.format_exc()}")
        error_message = manejar_error_api(e, "consulta de datos hidrológicos")
        return dbc.Alert([
            html.H6("Error en consulta", className="alert-heading"),
            html.Pre(error_message, style={"white-space": "pre-wrap", "font-family": "inherit"}),
            html.Hr(),
            html.P("Revise los parámetros de consulta e intente nuevamente.", className="mb-0")
        ], color="danger", className="text-start")

# Callback para inicializar las tablas jerárquicas al cargar la página


@callback(
    [Output("participacion-jerarquica-data", "data"),
     Output("capacidad-jerarquica-data", "data"),
     Output("ultima-fecha-con-datos", "data")],
    [Input("fecha-inicio-hidrologia", "date"), Input("fecha-fin-hidrologia", "date")],
    prevent_initial_call=False
)
def initialize_hierarchical_tables(start_date, end_date):
    """Inicializar las tablas jerárquicas con datos de regiones al cargar la página"""
    try:
        objetoAPI = get_objetoAPI()
        logger.debug(f"DEBUG INIT: Inicializando tablas jerárquicas con fechas {start_date} - {end_date}")
        
        # 🔍 Buscar la última fecha con datos disponibles (no asumir que hoy tiene datos)
        from datetime import date, timedelta
        fecha_busqueda = date.today()
        fecha_obj = None
        intentos = 0
        max_intentos = 7  # Buscar hasta 7 días atrás
        
        while intentos < max_intentos and fecha_obj is None:
            df_vol_test, fecha_obj = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_busqueda)
            if fecha_obj is None:
                logger.debug(f"🔍 No hay datos para {fecha_busqueda}, intentando día anterior...")
                fecha_busqueda = fecha_busqueda - timedelta(days=1)
                intentos += 1
        
        if fecha_obj is None:
            logger.error(f"❌ DEBUG INIT: No se encontraron fechas con datos en los últimos {max_intentos} días")
            return [], []
        
        fecha_con_datos = fecha_obj.strftime('%Y-%m-%d')
        logger.info(f"✅ DEBUG INIT: Última fecha con datos disponibles: {fecha_con_datos}")
        
        regiones_totales, df_completo_embalses = get_tabla_regiones_embalses(None, fecha_con_datos)
        logger.debug(f"DEBUG INIT: Regiones obtenidas: {len(regiones_totales) if not regiones_totales.empty else 0}")
        
        if regiones_totales.empty:
            logger.warning("DEBUG INIT: No hay regiones, retornando listas vacías")
            return [], []
        
        # Crear datos para tabla de participación (solo regiones inicialmente)
        participacion_data = []
        capacidad_data = []
        
        logger.debug(f"DEBUG INIT: Procesando {len(regiones_totales)} regiones")
        
        for _, row in regiones_totales.iterrows():
            # ✅ CORREGIDO: Usar directamente la columna 'Participación (%)' calculada en get_tabla_regiones_embalses
            participacion_pct = row.get('Participación (%)', 0)
            participacion_data.append({
                'nombre': f"▶️ {row['Región']}",
                'participacion': f"{participacion_pct:.2f}%",
                'tipo': 'region',
                'region_name': row['Región'],
                'expandida': False,
                'id': f"region_{row['Región']}"
            })
            # Volumen útil (%) para la tabla de capacidad
            volumen_util_valor = row.get('Volumen Útil (%)', 0)
            capacidad_data.append({
                'nombre': f"▶️ {row['Región']}",
                'capacidad': f"{volumen_util_valor:.1f}%",
                'tipo': 'region',
                'region_name': row['Región'],
                'expandida': False,
                'id': f"region_{row['Región']}"
            })
        
        # Agregar fila TOTAL al final
        participacion_data.append({
            'nombre': 'TOTAL SISTEMA',
            'participacion': '100.0%',
            'tipo': 'total',
            'region_name': '',
            'expandida': False,
            'id': 'total'
        })
        
        # ✅ CORREGIDO: Calcular volumen útil nacional directamente desde regiones_totales
        # Esto garantiza consistencia total con los datos mostrados en las regiones
        total_volumen_gwh = regiones_totales['Volumen Util (GWh)'].sum()
        total_capacidad_gwh = regiones_totales['Total (GWh)'].sum()
        
        if total_capacidad_gwh > 0:
            promedio_volumen_general = round((total_volumen_gwh / total_capacidad_gwh) * 100, 1)
        else:
            promedio_volumen_general = 0.0
        
        logger.debug(f"Volumen útil nacional: Vol={total_volumen_gwh:.2f} GWh, Cap={total_capacidad_gwh:.2f} GWh, %={promedio_volumen_general:.1f}%")
        
        capacidad_data.append({
            'nombre': 'TOTAL SISTEMA',
            'capacidad': f"{promedio_volumen_general:.1f}%",
            'tipo': 'total',
            'region_name': '',
            'expandida': False,
            'id': 'total'
        })
        
        # Datos completos para los stores (incluye embalses)
        participacion_completa = participacion_data.copy()
        capacidad_completa = capacidad_data.copy()
        
        # Agregar datos de embalses a los stores completos COMBINANDO ambos valores
        for region_name in regiones_totales['Región'].unique():
            embalses_region = get_embalses_by_region(region_name, df_completo_embalses)
            
            if not embalses_region.empty:
                logger.info(f"🔍 [INIT_TABLES] Procesando región: {region_name}, {len(embalses_region)} embalses")
                for _, embalse_row in embalses_region.iterrows():
                    embalse_name = embalse_row['Región'].replace('    └─ ', '')
                    volumen_embalse = embalse_row.get('Volumen Útil (%)', 0)
                    participacion_embalse = embalse_row.get('Participación (%)', 0)
                    
                    # 🔍 LOG CRÍTICO: Valores RAW antes de formatear
                    logger.info(f"🔍 [RAW] {embalse_name}: Volumen={volumen_embalse} (tipo={type(volumen_embalse).__name__}), Participación={participacion_embalse} (tipo={type(participacion_embalse).__name__})")
                    
                    # 🔍 Convertir a float para evitar corrupción
                    try:
                        participacion_float = float(embalse_row['Participación (%)'])
                        volumen_float = float(volumen_embalse) if volumen_embalse is not None else 0.0
                    except (ValueError, TypeError) as e:
                        logger.error(f"❌ Error convirtiendo valores a float para {embalse_name}: {e}")
                        participacion_float = 0.0
                        volumen_float = 0.0
                    
                    # 🔍 LOG CRÍTICO: Valores después de conversión a float
                    logger.info(f"🔍 [FLOAT] {embalse_name}: Volumen={volumen_float:.2f}%, Participación={participacion_float:.2f}%")
                    
                    # 🔍 Formatear CONSISTENTEMENTE
                    participacion_formatted = f"{participacion_float:.2f}%"
                    volumen_formatted = f"{volumen_float:.1f}%"
                    
                    # 🔍 LOG CRÍTICO: Valores formateados
                    logger.info(f"🔍 [FORMATTED] {embalse_name}: Volumen={volumen_formatted}, Participación={participacion_formatted}")
                    
                    # ESTRUCTURA UNIFICADA: Agregar AMBOS valores a la misma entrada
                    # Para participación_completa
                    participacion_completa.append({
                        'nombre': f"    └─ {embalse_name}",
                        'participacion': participacion_formatted,
                        'capacidad': volumen_formatted,
                        'participacion_valor': participacion_float,
                        'volumen_valor': volumen_float,
                        'tipo': 'embalse',
                        'region_name': region_name,
                        'expandida': False,
                        'id': f"embalse_{region_name}_{embalse_name}"
                    })
                    
                    # Para capacidad_completa - MISMOS VALORES pero estructura diferente
                    capacidad_completa.append({
                        'nombre': f"    └─ {embalse_name}",
                        'capacidad': volumen_formatted,
                        'participacion': participacion_formatted,
                        'participacion_valor': participacion_float,
                        'volumen_valor': volumen_float,
                        'tipo': 'embalse',
                        'region_name': region_name,
                        'expandida': False,
                        'id': f"embalse_{region_name}_{embalse_name}"
                    })
                    
                    # 🔍 LOG CRÍTICO: Verificar que ambos stores tienen EXACTAMENTE los mismos valores
                    logger.info(f"🔍 [STORE_VERIFICATION] {embalse_name} - PARTICIPACION_STORE: vol={participacion_completa[-1]['capacidad']}, part={participacion_completa[-1]['participacion']}")
                    logger.info(f"🔍 [STORE_VERIFICATION] {embalse_name} - CAPACIDAD_STORE: vol={capacidad_completa[-1]['capacidad']}, part={capacidad_completa[-1]['participacion']}")
        
        # Retornar: datos completos para stores + última fecha con datos
        return participacion_completa, capacidad_completa, fecha_con_datos
        
    except Exception as e:
        logger.error(f"Error inicializando tablas jerárquicas: {e}", exc_info=True)
        return [], [], None



@callback(
    [Output("tabla-participacion-jerarquica-container", "children"),
     Output("tabla-capacidad-jerarquica-container", "children")],
    [Input("participacion-jerarquica-data", "data"),
     Input("capacidad-jerarquica-data", "data")],
    [State("regiones-expandidas", "data")],
    prevent_initial_call=False
)
def update_html_tables_from_stores(participacion_complete, capacidad_complete, regiones_expandidas):
    """Actualizar las vistas HTML basándose en los stores"""
    try:
        logger.info(f"✅ [UPDATE_TABLES_FROM_STORES] Ejecutándose...")
        logger.info(f"✅ Participación: {len(participacion_complete) if participacion_complete else 0} items")
        logger.info(f"✅ Capacidad: {len(capacidad_complete) if capacidad_complete else 0} items")
        logger.info(f"✅ Regiones expandidas: {regiones_expandidas}")
        
        if not participacion_complete or not capacidad_complete:
            logger.warning("DEBUG STORES: Datos incompletos, retornando mensajes de error")
            return (
                html.Div("No hay datos de participación disponibles", className="text-center text-muted p-3"),
                html.Div("No hay datos de capacidad disponibles", className="text-center text-muted p-3")
            )
        
        if not regiones_expandidas:
            regiones_expandidas = []
        
        # Construir vistas de tabla iniciales (todas las regiones colapsadas)
        logger.debug(f"DEBUG STORES: Construyendo vista de participación")
        participacion_view = build_hierarchical_table_view(participacion_complete, regiones_expandidas, "participacion")
        logger.debug(f"DEBUG STORES: Construyendo vista de capacidad")
        capacidad_view = build_hierarchical_table_view(capacidad_complete, regiones_expandidas, "capacidad")
        
        return participacion_view, capacidad_view
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return (
            html.Div("Error al cargar datos de participación", className="text-center text-danger p-3"),
            html.Div("Error al cargar datos de capacidad", className="text-center text-danger p-3")
        )

# Callback para manejar clics en las regiones y expandir/colapsar embalses (CON allow_duplicate)


@callback(
    [Output("tabla-participacion-jerarquica-container", "children", allow_duplicate=True),
     Output("tabla-capacidad-jerarquica-container", "children", allow_duplicate=True),
     Output("regiones-expandidas", "data")],
    [Input("tabla-participacion-jerarquica-display", "active_cell"),
     Input("tabla-capacidad-jerarquica-display", "active_cell")],
    [State("participacion-jerarquica-data", "data"),
     State("capacidad-jerarquica-data", "data"),
     State("regiones-expandidas", "data")],
    prevent_initial_call=True
)
def toggle_region_from_table(active_cell_part, active_cell_cap, participacion_complete, capacidad_complete, regiones_expandidas):
    """Manejar clics en los nombres de región con botones integrados"""
    try:
        if not participacion_complete or not capacidad_complete:
            return dash.no_update, dash.no_update, regiones_expandidas or []
        
        if regiones_expandidas is None:
            regiones_expandidas = []
        
        # Obtener el clic activo
        active_cell = active_cell_part or active_cell_cap
        if not active_cell:
            return dash.no_update, dash.no_update, regiones_expandidas
        
        # Solo responder a clics en la columna "nombre"
        if active_cell.get('column_id') != 'nombre':
            return dash.no_update, dash.no_update, regiones_expandidas
        
        # Obtener el nombre de la celda clicada directamente de la tabla correcta
        # Determinar qué tabla fue clicada y usar esa para obtener los datos
        if active_cell_part:
            # Clic en tabla de participación
            current_table = build_hierarchical_table_view(participacion_complete, regiones_expandidas, "participacion")
            table_source = "participacion"
        else:
            # Clic en tabla de capacidad
            current_table = build_hierarchical_table_view(capacidad_complete, regiones_expandidas, "capacidad")
            table_source = "capacidad"
        
        # Obtener los datos de la tabla actual
        table_data = current_table.data if hasattr(current_table, 'data') else []
        
        # Verificar qué fila se clicó
        row_id = active_cell['row']
        if row_id < len(table_data):
            clicked_row = table_data[row_id]
            clicked_name = clicked_row.get('nombre', '')
            
            # Determinar el tipo de fila basándose en el formato del nombre
            is_region = (clicked_name.startswith('⊞ ') or clicked_name.startswith('⊟ ')) and not clicked_name.startswith('    └─ ')
            
            # Solo procesar si es una región
            if is_region:
                # Extraer el nombre de la región del texto (remover símbolos ⊞/⊟)
                region_name = clicked_name.replace('⊞ ', '').replace('⊟ ', '').strip()
                
                # Toggle la región
                if region_name in regiones_expandidas:
                    regiones_expandidas.remove(region_name)
                else:
                    regiones_expandidas.append(region_name)
        
        # Reconstruir las vistas con sistema de semáforo
        participacion_view = build_hierarchical_table_view(participacion_complete, regiones_expandidas, "participacion")
        capacidad_view = build_hierarchical_table_view(capacidad_complete, regiones_expandidas, "capacidad")
        
        return participacion_view, capacidad_view, regiones_expandidas
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return dash.no_update, dash.no_update, regiones_expandidas or []


# ============================================================================
# CALLBACK PARA TABLA PEQUEÑA DE EMBALSES JERÁRQUICA
# ============================================================================



@callback(
    [Output("tabla-embalses-jerarquica-container", "children"),
     Output("embalses-expandidos-store", "data")],
    [Input("tabla-embalses-jerarquica", "active_cell")],
    [State("embalses-regiones-data", "data"),
     State("embalses-completo-data", "data"),
     State("embalses-expandidos-store", "data")],
    prevent_initial_call=True
)
def toggle_embalse_region(active_cell, regiones_data, embalses_data, expanded_regions):
    """Manejar clics en las regiones de la tabla pequeña para expandir/contraer"""
    try:
        if not active_cell or not regiones_data or not embalses_data:
            return dash.no_update, expanded_regions or []
        
        if expanded_regions is None:
            expanded_regions = []
        
        # Solo responder a clics en la columna "embalse"
        if active_cell.get('column_id') != 'embalse':
            return dash.no_update, expanded_regions
        
        # Convertir datos de vuelta a DataFrames
        import pandas as pd
        regiones_totales = pd.DataFrame(regiones_data)
        df_completo_embalses = pd.DataFrame(embalses_data)
        
        # Reconstruir la tabla para obtener los datos actuales
        current_table = build_embalses_hierarchical_view(regiones_totales, df_completo_embalses, expanded_regions)
        table_data = current_table.data if hasattr(current_table, 'data') else []
        
        # Verificar qué fila se clicó
        row_id = active_cell['row']
        if row_id < len(table_data):
            clicked_row = table_data[row_id]
            clicked_name = clicked_row.get('embalse', '')
            
            # Determinar si es una región (tiene ⊞ o ⊟ al inicio)
            is_region = (clicked_name.startswith('⊞ ') or clicked_name.startswith('⊟ ')) and not clicked_name.startswith('    └─ ')
            
            # Solo procesar si es una región
            if is_region:
                # Extraer el nombre de la región
                region_name = clicked_name.replace('⊞ ', '').replace('⊟ ', '').strip()
                
                # Toggle la región
                if region_name in expanded_regions:
                    expanded_regions.remove(region_name)
                else:
                    expanded_regions.append(region_name)
        
        # Reconstruir la vista con las regiones actualizadas
        new_table = build_embalses_hierarchical_view(regiones_totales, df_completo_embalses, expanded_regions)
        
        return new_table, expanded_regions
        
    except Exception as e:
        logger.error(f"❌ Error en toggle_embalse_region: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return dash.no_update, expanded_regions or []


# Clientside callback para toggle del Sistema Semáforo (más confiable para contenido dinámico)
import dash
# clientside_callback already imported at top

# JavaScript para manejar el toggle
dash.clientside_callback(
    """
    function(n_clicks, is_open) {
        if (!n_clicks) {
            return window.dash_clientside.no_update;
        }
        const new_state = !is_open;
        const button_text = new_state ? "Ocultar información del Sistema Semáforo" : "Ver información detallada del Sistema Semáforo de Riesgo Hidrológico";
        const chevron_class = new_state ? "fas fa-chevron-up ms-2" : "fas fa-chevron-down ms-2";
        return [new_state, button_text, chevron_class];
    }
    """,
    [Output("collapse-semaforo-info", "is_open"),
     Output("semaforo-button-text", "children"),
     Output("semaforo-chevron", "className")],
    [Input("toggle-semaforo-info", "n_clicks")],
    [State("collapse-semaforo-info", "is_open")]
)

# Clientside callback para la vista de región
dash.clientside_callback(
    """
    function(n_clicks, is_open) {
        if (!n_clicks) {
            return window.dash_clientside.no_update;
        }
        const new_state = !is_open;
        const button_text = new_state ? "Ocultar información del Sistema Semáforo" : "Ver información detallada del Sistema Semáforo de Riesgo Hidrológico";
        const chevron_class = new_state ? "fas fa-chevron-up ms-2" : "fas fa-chevron-down ms-2";
        return [new_state, button_text, chevron_class];
    }
    """,
    [Output("collapse-semaforo-region-info", "is_open"),
     Output("semaforo-region-button-text", "children"),
     Output("semaforo-region-chevron", "className")],
    [Input("toggle-semaforo-region-info", "n_clicks")],
    [State("collapse-semaforo-region-info", "is_open")]
)

# Clientside callback para la guía de lectura de la gráfica
dash.clientside_callback(
    """
    function(n_clicks, is_open) {
        if (!n_clicks) {
            return window.dash_clientside.no_update;
        }
        const new_state = !is_open;
        const button_text = new_state ? "Ocultar guía de lectura" : "Ver guía de lectura de la gráfica";
        const chevron_class = new_state ? "fas fa-chevron-up ms-2" : "fas fa-chevron-down ms-2";
        return [new_state, button_text, chevron_class];
    }
    """,
    [Output("collapse-guia-grafica", "is_open"),
     Output("guia-grafica-button-text", "children"),
     Output("guia-grafica-chevron", "className")],
    [Input("toggle-guia-grafica", "n_clicks")],
    [State("collapse-guia-grafica", "is_open")]
)

# Callback para abrir/cerrar modal del semáforo


@callback(
    Output("modal-semaforo", "is_open"),
    [Input("btn-info-semaforo", "n_clicks")],
    [State("modal-semaforo", "is_open")],
    prevent_initial_call=True
)
def toggle_modal_semaforo(n_clicks, is_open):
    """Toggle del modal de información del semáforo"""
    if n_clicks:
        return not is_open
    return is_open

# Callback para abrir/cerrar modal del sistema de humedad
@callback(
    Output("modal-humedad", "is_open"),
    [Input("btn-info-humedad", "n_clicks")],
    [State("modal-humedad", "is_open")],
    prevent_initial_call=True
)
def toggle_modal_humedad(n_clicks, is_open):
    """Toggle del modal de información del sistema de humedad"""
    if n_clicks:
        return not is_open
    return is_open

# Callback para abrir/cerrar modal de información de la ficha KPI
@callback(
    Output("modal-info-ficha-kpi", "is_open"),
    [Input("btn-info-ficha-kpi", "n_clicks")],
    [State("modal-info-ficha-kpi", "is_open")],
    prevent_initial_call=True
)
def toggle_modal_info_ficha_kpi(n_clicks, is_open):
    """Toggle del modal de información de la ficha KPI"""
    if n_clicks:
        return not is_open
    return is_open

# Callback adicional para cargar datos por defecto al iniciar la página
# TEMPORALMENTE DESHABILITADO PARA EVITAR CONFLICTOS
# @callback(
#     Output("hidro-results-content", "children", allow_duplicate=True),
#     [Input("start-date", "date"), Input("end-date", "date")],
#     prevent_initial_call='initial_duplicate'
# )
# def load_default_data(start_date, end_date):
#     """Cargar datos por defecto al inicializar la página"""
#     # FUNCIÓN TEMPORALMENTE DESHABILITADA PARA EVITAR CONFLICTOS DE CALLBACK
#     pass

# --- Función para calcular participación porcentual de embalses ---


@callback(
    [Output({"type": "collapse-region", "index": dash.dependencies.MATCH}, "is_open"),
     Output({"type": "chevron-region", "index": dash.dependencies.MATCH}, "className")],
    [Input({"type": "toggle-region", "index": dash.dependencies.MATCH}, "n_clicks")],
    [State({"type": "collapse-region", "index": dash.dependencies.MATCH}, "is_open")]
)
def toggle_region_collapse(n_clicks, is_open):
    """
    Callback elegante para manejar el toggle de una región específica usando pattern-matching
    """
    if not n_clicks:
        return False, "bi bi-chevron-right me-3"
    
    new_state = not is_open
    if new_state:
        # Expandido - rotar chevron hacia abajo
        return True, "bi bi-chevron-down me-3"
    else:
        # Contraído - chevron hacia la derecha
        return False, "bi bi-chevron-right me-3"




@callback(
    [Output("modal-rio-table", "is_open"), Output("modal-table-content", "children"), 
     Output("modal-title-dynamic", "children"), Output("modal-description", "children")],
    [Input("total-timeline-graph", "clickData"), Input("modal-rio-table", "is_open")],
    [State("region-data-store", "data")],
    prevent_initial_call=True
)
def show_modal_table(timeline_clickData, is_open, region_data):
    ctx = dash.callback_context
    
    logger.debug(f"CALLBACK EJECUTADO! Triggered: {[prop['prop_id'] for prop in ctx.triggered]}")
    logger.debug(f"Timeline click data: {timeline_clickData}")
    
    # Determinar qué fue clicado
    clickData = None
    graph_type = None
    
    if ctx.triggered:
        trigger_id = ctx.triggered[0]["prop_id"]
        
        if trigger_id.startswith("total-timeline-graph") and timeline_clickData:
            clickData = timeline_clickData
            graph_type = "timeline"
            logger.debug(f"Click detected! clickData: {clickData}")
        elif trigger_id.startswith("modal-rio-table"):
            return False, None, "", ""
    
    # Si se hace click en un punto del timeline, mostrar el modal con la tabla
    if clickData and graph_type == "timeline":
        point_data = clickData["points"][0]
        
        # Detectar en qué línea/curva se hizo clic
        curve_number = point_data.get('curveNumber', 0)
        trace_name = point_data.get('fullData', {}).get('name', 'Aportes Reales')
        
        logger.debug(f"Curva clickeada: {curve_number}, Nombre: {trace_name}")
        
        # Si se hizo clic en la Media Histórica (curva 1)
        if curve_number == 1 or 'Media Histórica' in str(trace_name):
            logger.debug("Click en MEDIA HISTÓRICA detectado")
            
            # Obtener la fecha clicada
            selected_date = point_data['x']
            total_value = point_data['y']
            
            # Obtener datos de media histórica
            try:
                # Necesitamos obtener la media histórica del backend
                objetoAPI = get_objetoAPI()
                
                # Obtener el rango de fechas del store de datos
                df_store = pd.DataFrame(region_data) if region_data else pd.DataFrame()
                if not df_store.empty:
                    fecha_inicio = df_store['Date'].min()
                    fecha_fin = df_store['Date'].max()
                    
                    if isinstance(fecha_inicio, str):
                        fecha_inicio_str = fecha_inicio
                    else:
                        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
                    
                    if isinstance(fecha_fin, str):
                        fecha_fin_str = fecha_fin
                    else:
                        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')
                    
                    # Obtener media histórica
                    media_hist_data, _ = obtener_datos_inteligente('AporEnerMediHist', 'Rio', fecha_inicio_str, fecha_fin_str)
                    
                    if media_hist_data is not None and not media_hist_data.empty:
                        # ⚠️ NO convertir - fetch_metric_data YA convierte a GWh automáticamente en _xm.py
                        
                        # Agregar información de región
                        rio_region = ensure_rio_region_loaded()
                        media_hist_data['Region'] = media_hist_data['Name'].map(rio_region)
                        
                        # Filtrar por la fecha seleccionada
                        selected_date_dt = pd.to_datetime(selected_date)
                        media_hist_data['Date'] = pd.to_datetime(media_hist_data['Date'])
                        df_date = media_hist_data[media_hist_data['Date'] == selected_date_dt].copy()
                        
                        if not df_date.empty:
                            # Agrupar por región
                            region_summary = df_date.groupby('Region')['Value'].sum().reset_index()
                            region_summary = region_summary.sort_values('Value', ascending=False)
                            region_summary = region_summary.rename(columns={'Region': 'Región', 'Value': 'Energía (GWh)'})
                            
                            # Calcular participación porcentual
                            total = region_summary['Energía (GWh)'].sum()
                            
                            if total > 0:
                                region_summary['Participación (%)'] = (region_summary['Energía (GWh)'] / total * 100).round(2)
                                diferencia = 100 - region_summary['Participación (%)'].sum()
                                if abs(diferencia) > 0.001:
                                    idx_max = region_summary['Participación (%)'].idxmax()
                                    region_summary.loc[idx_max, 'Participación (%)'] += diferencia
                                    region_summary['Participación (%)'] = region_summary['Participación (%)'].round(2)
                            else:
                                region_summary['Participación (%)'] = 0
                            
                            # Formatear números
                            region_summary['Energía (GWh)'] = region_summary['Energía (GWh)'].apply(format_number)
                            
                            # Agregar fila total
                            total_row = {
                                'Región': 'TOTAL',
                                'Energía (GWh)': format_number(total),
                                'Participación (%)': '100.0%'
                            }
                            
                            data_with_total = region_summary.to_dict('records') + [total_row]
                            
                            # Crear tabla
                            table = dash_table.DataTable(
                                data=data_with_total,
                                columns=[
                                    {"name": "Región", "id": "Región"},
                                    {"name": "Energía (GWh)", "id": "Energía (GWh)"},
                                    {"name": "Participación (%)", "id": "Participación (%)"}
                                ],
                                style_cell={'textAlign': 'left', 'padding': '8px', 'fontFamily': 'Inter, Arial', 'fontSize': 14},
                                style_header={'backgroundColor': '#1e90ff', 'color': 'white', 'fontWeight': 'bold'},
                                style_data={'backgroundColor': '#f0f8ff'},
                                style_data_conditional=[
                                    {
                                        'if': {'filter_query': '{Región} = "TOTAL"'},
                                        'backgroundColor': '#1e90ff',
                                        'color': 'white',
                                        'fontWeight': 'bold'
                                    }
                                ],
                                page_action="none",
                                export_format="xlsx",
                                export_headers="display"
                            )
                            
                            formatted_date = format_date(selected_date)
                            total_regions = len(region_summary)
                            title = f"📘 Media Histórica del {formatted_date} - Total Nacional: {format_number(total_value)} GWh"
                            description = f"Detalle de media histórica por región hidrológica para el día {formatted_date}. Se muestran los aportes energéticos históricos promedio de {total_regions} regiones, con su respectiva participación porcentual sobre el total nacional de {format_number(total_value)} GWh."
                            
                            return True, table, title, description
                        
            except Exception as e:
# print(f"❌ Error obteniendo media histórica: {e}")
                import traceback
                traceback.print_exc()
            
            return False, None, "Error", "No se pudieron obtener los datos de media histórica."
        
        # Si se hizo clic en Aportes Reales (curva 0) - código original
        df = pd.DataFrame(region_data) if region_data else pd.DataFrame()
        logger.debug(f"DataFrame creado - shape: {df.shape}, columns: {df.columns.tolist() if not df.empty else 'DataFrame vacío'}")
        
        if df.empty:
            return False, None, "Sin datos", "No hay información disponible para mostrar."
        
        # Obtener la fecha clicada
        selected_date = point_data['x']
        total_value = point_data['y']
        logger.debug(f"DEBUG: Fecha seleccionada: {selected_date}, Total: {total_value}")
        logger.debug(f"DEBUG: Tipo de fecha seleccionada: {type(selected_date)}")
        
        # Ver qué fechas están disponibles en el DataFrame
        unique_dates = df['Date'].unique()[:10]  # Primeras 10 fechas únicas
        logger.debug(f"Primeras fechas disponibles en DataFrame: {unique_dates}")
        logger.debug(f"Tipo de fechas en DataFrame: {type(df['Date'].iloc[0]) if not df.empty else 'N/A'}")
        
        # Filtrar datos de esa fecha específica
        df_date = df[df['Date'] == selected_date].copy()
        logger.debug(f"Datos filtrados por fecha - shape: {df_date.shape}")
        
        # Si no hay datos, intentar convertir la fecha a diferentes formatos
        if df_date.empty:
            logger.debug(f" Intentando conversiones de fecha...")
            # Intentar convertir la fecha seleccionada a datetime
            try:
                from datetime import datetime
                if isinstance(selected_date, str):
                    selected_date_dt = pd.to_datetime(selected_date)
                    logger.debug(f" Fecha convertida a datetime: {selected_date_dt}")
                    # Intentar filtrar con la fecha convertida
                    df_date = df[df['Date'] == selected_date_dt].copy()
                    logger.debug(f" Datos filtrados con fecha convertida - shape: {df_date.shape}")
                
                # Si aún no hay datos, intentar convertir las fechas del DataFrame
                if df_date.empty:
                    logger.debug(f" Convirtiendo fechas del DataFrame...")
                    df['Date'] = pd.to_datetime(df['Date'])
                    df_date = df[df['Date'] == selected_date_dt].copy()
                    logger.debug(f" Datos filtrados después de conversión DF - shape: {df_date.shape}")
                    
            except Exception as e:
                logger.error(f"Error en conversión de fechas: {e}")
                pass
        
        
        if df_date.empty:
            return False, None, f"Sin datos para {selected_date}", f"No se encontraron datos para la fecha {selected_date}."
        
        # Agrupar por región para esa fecha
        region_summary = df_date.groupby('Region')['Value'].sum().reset_index()
        region_summary = region_summary.sort_values('Value', ascending=False)
        region_summary = region_summary.rename(columns={'Region': 'Región', 'Value': 'Energía (GWh)'})
        logger.debug(f"region_summary contenido: {region_summary.to_dict() if not region_summary.empty else 'Vacío'}")
        
        # Calcular participación porcentual
        total = region_summary['Energía (GWh)'].sum()
        logger.debug(f"Total calculado: {total}")
        
        if total > 0:
            region_summary['Participación (%)'] = (region_summary['Energía (GWh)'] / total * 100).round(2)
            # Ajustar para que sume exactamente 100%
            diferencia = 100 - region_summary['Participación (%)'].sum()
            if abs(diferencia) > 0.001:
                idx_max = region_summary['Participación (%)'].idxmax()
                region_summary.loc[idx_max, 'Participación (%)'] += diferencia
                region_summary['Participación (%)'] = region_summary['Participación (%)'].round(2)
        else:
            region_summary['Participación (%)'] = 0
        
        # Formatear números
        region_summary['Energía (GWh)'] = region_summary['Energía (GWh)'].apply(format_number)
        
        # Agregar fila total
        total_row = {
            'Región': 'TOTAL',
            'Energía (GWh)': format_number(total),
            'Participación (%)': '100.0%'
        }
        
        data_with_total = region_summary.to_dict('records') + [total_row]
        
        # Crear tabla
        table = dash_table.DataTable(
            data=data_with_total,
            columns=[
                {"name": "Región", "id": "Región"},
                {"name": "Energía (GWh)", "id": "Energía (GWh)"},
                {"name": "Participación (%)", "id": "Participación (%)"}
            ],
            style_cell={'textAlign': 'left', 'padding': '8px', 'fontFamily': 'Inter, Arial', 'fontSize': 14},
            style_header={'backgroundColor': '#1e40af', 'color': 'white', 'fontWeight': 'bold'},
            style_data={'backgroundColor': '#f8f9fa'},
            style_data_conditional=[
                {
                    'if': {'filter_query': '{Región} = "TOTAL"'},
                    'backgroundColor': '#2563eb',
                    'color': 'white',
                    'fontWeight': 'bold'
                }
            ],
            page_action="none",
            export_format="xlsx",
            export_headers="display"
        )
        
        # Crear título y descripción
        formatted_date = format_date(selected_date)
        total_regions = len(region_summary) - 1 if len(region_summary) > 0 else 0
        title = f"⚡ Detalles del {formatted_date} - Total Nacional: {format_number(total_value)} GWh"
        description = f"Detalle por región hidrológica para el día {formatted_date}. Se muestran los aportes de energía de {total_regions} regiones que registraron actividad en esta fecha, con su respectiva participación porcentual sobre el total nacional de {format_number(total_value)} GWh."
        
        
        return True, table, title, description
    
    # Si se cierra el modal
    elif ctx.triggered and ctx.triggered[0]["prop_id"].startswith("modal-rio-table"):
        return False, None, "", ""
    
    # Por defecto, modal cerrado
    return False, None, "", ""



@callback(
    Output('region-dropdown', 'options'),
    Input('region-dropdown', 'id')  # Se ejecuta al cargar la página
)
def load_region_options(_):
    """Carga las opciones de regiones dinámicamente para evitar bloqueos durante la importación."""
    try:
        regiones_disponibles = get_region_options()
        options = [{"label": "Todas las regiones", "value": "__ALL_REGIONS__"}]
        options += [{"label": r, "value": r} for r in regiones_disponibles]
        return options
    except Exception as e:
        logger.error(f"Error cargando opciones de regiones: {e}", exc_info=True)
        return [{"label": "Todas las regiones", "value": "__ALL_REGIONS__"}]

# Callback para cargar el mapa de embalses por región
@callback(
    Output('mapa-embalses-container', 'children'),
    Input('participacion-jerarquica-data', 'data')  # Se ejecuta cuando se cargan los datos de las tablas
)
def cargar_mapa_embalses(data):
    """Genera el mapa mostrando CADA EMBALSE como un punto individual dentro de su región."""
    try:
        logger.info("Generando mapa con puntos por embalse...")
        
        if not data or len(data) == 0:
            return dbc.Alert([
                html.H5("No hay datos disponibles", className="alert-heading"),
                html.P("Esperando datos de embalses...")
            ], color="info")
        
        # Filtrar solo embalses (no regiones ni total)
        embalses_data = [d for d in data if d.get('tipo') == 'embalse']
        
        if len(embalses_data) == 0:
            return dbc.Alert([
                html.H5("No hay datos de embalses", className="alert-heading"),
                html.P("No se encontraron datos de embalses en las tablas.")
            ], color="warning")
        
        logger.info(f"Procesando {len(embalses_data)} embalses individuales...")
        
        # Agrupar embalses por región
        import random
        from math import cos, radians
        
        regiones_embalses = {}
        for emb in embalses_data:
            region = emb.get('region_name')
            if not region or region not in REGIONES_COORDENADAS:
                continue
            
            if region not in regiones_embalses:
                regiones_embalses[region] = []
            
            # Obtener valores
            participacion = emb.get('participacion_valor', 0)
            volumen_pct = emb.get('volumen_valor', 0)
            nombre_embalse = emb.get('nombre', '').replace('    └─ ', '')
            
            # Calcular riesgo con función que retorna ALTO/MEDIO/BAJO
            riesgo, color, icono = calcular_semaforo_embalse_local(participacion, volumen_pct)
            
            regiones_embalses[region].append({
                'nombre': nombre_embalse,
                'participacion': participacion,
                'volumen_pct': volumen_pct,
                'riesgo': riesgo,
                'color': color,
                'icono': icono
            })
        
        # Crear el mapa con Plotly
        import plotly.graph_objects as go
        
        fig = go.Figure()
        
        # Contador para leyenda (solo mostrar una vez cada color)
        leyenda_mostrada = {'ALTO': False, 'MEDIO': False, 'BAJO': False}
        
        # Para cada región, distribuir los embalses en un área alrededor del centro de la región
        for region, embalses in regiones_embalses.items():
            coords = REGIONES_COORDENADAS[region]
            lat_centro = coords['lat']
            lon_centro = coords['lon']
            
            # Calcular un radio de dispersión proporcional al número de embalses
            # Más embalses = mayor área de dispersión
            num_embalses = len(embalses)
            radio_lat = 0.3 + (num_embalses * 0.05)  # Radio en grados de latitud
            radio_lon = 0.4 + (num_embalses * 0.06)  # Radio en grados de longitud
            
            logger.debug(f"{region}: {num_embalses} embalses")
            
            # Distribuir cada embalse en posiciones aleatorias dentro del área de la región
            for i, emb in enumerate(embalses):
                # Generar posición aleatoria dentro de un círculo alrededor del centro
                # Usar semilla basada en el nombre para que sea consistente entre recargas
                seed_value = hash(emb['nombre']) % 10000
                random.seed(seed_value)
                
                # Ángulo aleatorio y distancia aleatoria desde el centro
                angulo = random.uniform(0, 360)
                distancia = random.uniform(0.2, 1.0)  # 20% a 100% del radio
                
                # Calcular offset
                from math import sin, cos, radians
                offset_lat = distancia * radio_lat * sin(radians(angulo))
                offset_lon = distancia * radio_lon * cos(radians(angulo))
                
                lat_embalse = lat_centro + offset_lat
                lon_embalse = lon_centro + offset_lon
                
                # Crear tooltip con información del embalse
                hover_text = (
                    f"<b>{emb['nombre']}</b><br>" +
                    f"Región: {coords['nombre']}<br>" +
                    f"Participación: {emb['participacion']:.2f}%<br>" +
                    f"Volumen Útil: {emb['volumen_pct']:.1f}%<br>" +
                    f"<b>Riesgo: {emb['riesgo']}</b> {emb['icono']}"
                )
                
                # Tamaño según participación (más grande = más importante)
                tamaño = min(8 + emb['participacion'] * 0.5, 25)
                
                # Mostrar en leyenda solo la primera vez que aparece cada nivel de riesgo
                mostrar_leyenda = not leyenda_mostrada[emb['riesgo']]
                if mostrar_leyenda:
                    leyenda_mostrada[emb['riesgo']] = True
                    nombre_leyenda = f"{emb['icono']} Riesgo {emb['riesgo']}"
                else:
                    nombre_leyenda = f"{emb['nombre']}"
                
                # Agregar punto al mapa
                fig.add_trace(go.Scattergeo(
                    lon=[lon_embalse],
                    lat=[lat_embalse],
                    mode='markers',
                    marker=dict(
                        size=tamaño,
                        color=emb['color'],
                        line=dict(width=1, color='white'),
                        symbol='circle',
                        opacity=0.85
                    ),
                    name=nombre_leyenda,
                    hovertext=hover_text,
                    hoverinfo='text',
                    showlegend=mostrar_leyenda,
                    legendgroup=emb['riesgo']  # Agrupar por nivel de riesgo
                ))
        
        # Configurar el mapa centrado en Colombia
        fig.update_geos(
            center=dict(lon=-74, lat=4.5),
            projection_type='mercator',
            showcountries=True,
            countrycolor='lightgray',
            showcoastlines=True,
            coastlinecolor='gray',
            showland=True,
            landcolor='#f5f5f5',
            showlakes=True,
            lakecolor='lightblue',
            showrivers=True,
            rivercolor='lightblue',
            lonaxis_range=[-79, -66],
            lataxis_range=[-4.5, 13],
            bgcolor='#e8f4f8'
        )
        
        fig.update_layout(
            title={
                'text': f'🗺️ Mapa de {len(embalses_data)} Embalses - Semáforo de Riesgo Hidrológico',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 16, 'color': COLORS['text_primary'], 'family': 'Arial Black'}
            },
            height=390,
            margin=dict(l=0, r=0, t=60, b=0),
            legend=dict(
                title=dict(text='Nivel de Riesgo', font=dict(size=12, family='Arial Black')),
                orientation='v',
                yanchor='top',
                y=0.98,
                xanchor='left',
                x=0.01,
                bgcolor='rgba(255,255,255,0.9)',
                bordercolor='gray',
                borderwidth=1,
                font=dict(size=11)
            ),
            hoverlabel=dict(
                bgcolor='white',
                font_size=12,
                font_family='Arial'
            )
        )
        
        total_embalses = len(embalses_data)
        total_regiones = len(regiones_embalses)
        logger.info(f"Mapa generado: {total_embalses} embalses en {total_regiones} regiones")
        
        return dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False})
        
    except Exception as e:
# print(f"❌ Error generando mapa de embalses: {e}")
        import traceback
        traceback.print_exc()
        return html.Div([
            html.I(className="fas fa-exclamation-triangle me-2"),
            f"Error al generar el mapa: {str(e)}"
        ], className="alert alert-danger")


# ============================================================================
# CALLBACK: COMPARACIÓN ANUAL DE HIDROLOGÍA (EMBALSES)
# ============================================================================



@callback(
    [Output('grafica-lineas-temporal-hidro', 'figure'),
     Output('contenedor-embalses-anuales', 'children')],
    [Input('btn-actualizar-comparacion-hidro', 'n_clicks'),
     Input('years-multiselector-hidro', 'value'),
     Input('hidro-tabs', 'active_tab')],
    prevent_initial_call=False
)
def actualizar_comparacion_anual_hidro(n_clicks, years_selected, active_tab):
    """
    Callback para actualizar:
    1. Gráfica de líneas temporales (volumen útil por año)
    2. Gráficas de barras (volumen promedio por embalse y año)
    """
    px, go = get_plotly_modules()
    
    # Solo ejecutar si estamos en la pestaña de comparación anual
    if active_tab != "tab-comparacion-anual":
        raise PreventUpdate
    
    if not years_selected or len(years_selected) == 0:
        return (
            go.Figure().add_annotation(text="Selecciona al menos un año", xref="paper", yref="paper", x=0.5, y=0.5),
            dbc.Alert("Por favor selecciona al menos un año para comparar", color="warning")
        )
    
    try:
        # Colores únicos para cada año
        colores_años = {
            2020: '#1f77b4',
            2021: '#ff7f0e',
            2022: '#2ca02c',
            2023: '#d62728',
            2024: '#9467bd',
            2025: '#8c564b'
        }
        
        # ============================================================
        # 1. OBTENER DATOS DE VOLÚMENES PARA CADA AÑO SELECCIONADO
        # ============================================================
        datos_todos_años = []
        
        for year in sorted(years_selected):
            logger.info(f"📅 Obteniendo datos hidrológicos para año {year}...")
            
            # Definir fechas del año completo
            fecha_inicio = date(year, 1, 1)
            fecha_fin = date(year, 12, 31)
            
            # Si es el año actual, usar solo hasta ayer
            if year == date.today().year:
                fecha_fin = date.today() - timedelta(days=1)
            
            # Obtener datos de volumen útil de embalses (VoluUtilDiarEner)
            try:
                df_year, warning_msg = obtener_datos_inteligente(
                    'VoluUtilDiarEner', 
                    'Embalse',
                    fecha_inicio.strftime('%Y-%m-%d'),
                    fecha_fin.strftime('%Y-%m-%d')
                )
                
                if warning_msg:
                    logger.info(f"⚠️ {warning_msg}")
                
                if df_year is not None and not df_year.empty:
                    # Renombrar columnas para consistencia
                    if 'Date' in df_year.columns:
                        df_year.rename(columns={'Date': 'Fecha'}, inplace=True)
                    if 'Value' in df_year.columns:
                        df_year.rename(columns={'Value': 'Volumen_GWh'}, inplace=True)
                    
                    # La columna 'Embalse' ya existe gracias a obtener_datos_inteligente
                    # Solo verificar que exista
                    if 'Embalse' not in df_year.columns and 'Name' in df_year.columns:
                        df_year['Embalse'] = df_year['Name']
                    
                    df_year['Año'] = year
                    datos_todos_años.append(df_year)
                else:
                    logger.warning(f"⚠️ Sin datos para año {year}")
                    
            except Exception as e:
                logger.error(f"❌ Error obteniendo datos para {year}: {e}")
                continue
        
        if not datos_todos_años:
            return (
                go.Figure().add_annotation(text="No hay datos disponibles para los años seleccionados", 
                                         xref="paper", yref="paper", x=0.5, y=0.5),
                dbc.Alert("No se encontraron datos para los años seleccionados", color="warning")
            )
        
        # Combinar todos los años
        df_completo = pd.concat(datos_todos_años, ignore_index=True)
        df_completo['Fecha'] = pd.to_datetime(df_completo['Fecha'])
        
        # ============================================================
        # NOTA: Se muestran TODOS los embalses de cada año (sin filtrar)
        # Esto asegura que los datos sean reales y completos
        # ============================================================
        
        # Logging para verificar totales por año
        for year in sorted(years_selected):
            embalses_año = df_completo[df_completo['Año'] == year]['Embalse'].nunique()
            logger.info(f"📊 {year}: {embalses_año} embalses")
        
        # ============================================================
        # 2. CREAR GRÁFICA DE LÍNEAS TEMPORALES SUPERPUESTAS
        # ============================================================
        
        # Agregar por fecha y año (suma total de embalses comunes por día)
        df_por_dia_año = df_completo.groupby(['Año', 'Fecha'], as_index=False)['Volumen_GWh'].sum()
        
        # Crear fecha normalizada (mismo año base 2024 para superposición)
        df_por_dia_año['MesDia'] = df_por_dia_año['Fecha'].dt.strftime('%m-%d')
        df_por_dia_año['FechaNormalizada'] = pd.to_datetime('2024-' + df_por_dia_año['MesDia'])
        
        # Crear gráfica de líneas superpuestas
        fig_lineas = go.Figure()
        
        for year in sorted(years_selected):
            df_year = df_por_dia_año[df_por_dia_año['Año'] == year].sort_values('FechaNormalizada')
            
            # Crear texto customizado para hover con fecha real
            hover_text = [
                f"<b>{year}</b><br>{fecha.strftime('%d de %B de %Y')}<br>Volumen: {vol:.2f} GWh"
                for fecha, vol in zip(df_year['Fecha'], df_year['Volumen_GWh'])
            ]
            
            fig_lineas.add_trace(
                go.Scatter(
                    x=df_year['FechaNormalizada'],
                    y=df_year['Volumen_GWh'],
                    mode='lines',
                    name=str(year),
                    line=dict(color=colores_años.get(year, '#666'), width=2),
                    hovertext=hover_text,
                    hoverinfo='text'
                )
            )
        
        fig_lineas.update_layout(
            title="Volumen Útil Total de Embalses (GWh)",
            xaxis_title="Fecha",
            yaxis_title="Volumen (GWh)",
            hovermode='x unified',
            template='plotly_white',
            height=325,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            xaxis=dict(
                tickformat='%d %b',
                dtick='M1',
                tickangle=-45
            )
        )
        
        # ============================================================
        # 3. CREAR GRÁFICAS DE TORTA CON FICHAS (una por año) - ESTRUCTURA IDÉNTICA A GENERACIÓN
        # ============================================================
        
        # Calcular altura dinámica según cantidad de años
        num_years = len(years_selected)
        if num_years <= 2:
            torta_height = 200  # Más grande para 1-2 años
        elif num_years == 3:
            torta_height = 120  # Media para 3 años
        else:
            torta_height = 80   # Pequeña para 4+ años
        
        embalses_anuales = []
        
        for year in sorted(years_selected):
            # Definir fechas del año específico
            fecha_inicio_year = date(year, 1, 1)
            fecha_fin_year = date(year, 12, 31)
            
            if year == date.today().year:
                fecha_fin_year = date.today() - timedelta(days=1)
            
            # Filtrar datos del año
            df_year = df_completo[df_completo['Año'] == year].copy()
            
            # Calcular totales para KPIs
            volumen_promedio_total = df_por_dia_año[df_por_dia_año['Año'] == year]['Volumen_GWh'].mean()
            volumen_minimo = df_por_dia_año[df_por_dia_año['Año'] == year]['Volumen_GWh'].min()
            volumen_maximo = df_por_dia_año[df_por_dia_año['Año'] == year]['Volumen_GWh'].max()
            
            # Calcular promedios por embalse para la gráfica
            df_por_embalse = df_year.groupby('Embalse')['Volumen_GWh'].mean().reset_index()
            df_por_embalse.columns = ['Embalse', 'Promedio']
            
            # Ordenar y tomar top 10 embalses
            df_por_embalse = df_por_embalse.sort_values('Promedio', ascending=False).head(10)
            
            # Crear gráfica de BARRAS (más clara que torta para volúmenes)
            fig_barras = go.Figure()
            fig_barras.add_trace(
                go.Bar(
                    x=df_por_embalse['Embalse'],
                    y=df_por_embalse['Promedio'],
                    marker=dict(
                        color='#1f77b4'  # Color uniforme azul para todas las barras
                    ),
                    hovertemplate='<b>%{x}</b><br>Volumen Promedio: %{y:.1f} GWh<extra></extra>'
                )
            )
            
            fig_barras.update_layout(
                template='plotly_white',
                height=torta_height,
                showlegend=False,
                margin=dict(t=5, b=25, l=5, r=5),
                xaxis=dict(
                    tickangle=-45,
                    tickfont=dict(size=7)
                ),
                yaxis=dict(
                    title="GWh",
                    titlefont=dict(size=8),
                    tickfont=dict(size=7)
                )
            )
            
            # Agregar tarjeta con fichas compactas DENTRO (estructura idéntica a Generación)
            embalses_anuales.append(
                dbc.Card([
                    dbc.CardBody([
                        html.Small(f"{year}", style={'fontSize': '0.6rem', 'color': '#666', 'fontWeight': '600', 'display': 'block', 'textAlign': 'center', 'marginBottom': '4px'}),
                        
                        # Fichas horizontales compactas (3 en fila)
                        html.Div([
                            # Ficha Promedio
                            html.Div([
                                html.I(className="fas fa-water", style={'color': '#1f77b4', 'fontSize': '0.6rem', 'marginRight': '2px'}),
                                html.Span("Prom", style={'fontSize': '0.45rem', 'marginRight': '2px', 'color': '#666'}),
                                html.Span(f"{volumen_promedio_total:,.0f}", style={'fontSize': '0.7rem', 'fontWeight': '700', 'color': '#1f77b4'})
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'gap': '1px',
                                'padding': '2px 4px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '3px',
                                'flex': '1',
                                'justifyContent': 'center'
                            }),
                            
                            # Ficha Mínimo
                            html.Div([
                                html.I(className="fas fa-arrow-down", style={'color': '#dc3545', 'fontSize': '0.6rem', 'marginRight': '2px'}),
                                html.Span("Min", style={'fontSize': '0.45rem', 'marginRight': '2px', 'color': '#666'}),
                                html.Span(f"{volumen_minimo:,.0f}", style={'fontSize': '0.7rem', 'fontWeight': '700', 'color': '#dc3545'})
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'gap': '1px',
                                'padding': '2px 4px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '3px',
                                'flex': '1',
                                'justifyContent': 'center'
                            }),
                            
                            # Ficha Máximo
                            html.Div([
                                html.I(className="fas fa-arrow-up", style={'color': '#28a745', 'fontSize': '0.6rem', 'marginRight': '2px'}),
                                html.Span("Max", style={'fontSize': '0.45rem', 'marginRight': '2px', 'color': '#666'}),
                                html.Span(f"{volumen_maximo:,.0f}", style={'fontSize': '0.7rem', 'fontWeight': '700', 'color': '#28a745'})
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'gap': '1px',
                                'padding': '2px 4px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '3px',
                                'flex': '1',
                                'justifyContent': 'center'
                            }),
                        ], style={'display': 'flex', 'gap': '3px', 'marginBottom': '4px'}),
                        
                        # Gráfica de barras
                        dcc.Graph(figure=fig_barras, config={'displayModeBar': False}),
                        
                        # Fecha del período
                        html.Small(f"{fecha_inicio_year.strftime('%d/%m/%Y')} - {fecha_fin_year.strftime('%d/%m/%Y')}",
                                 className="text-center d-block text-muted",
                                 style={'fontSize': '0.5rem', 'marginTop': '2px'})
                    ], className="p-1")
                ], className="shadow-sm")
            )
        
        # Organizar fichas de 2 en 2 horizontalmente
        filas = []
        for i in range(0, len(embalses_anuales), 2):
            cols = []
            # Primera columna (50% del ancho de la columna = 15% del total)
            cols.append(dbc.Col(embalses_anuales[i], md=6, className="mb-2"))
            # Segunda columna (si existe)
            if i + 1 < len(embalses_anuales):
                cols.append(dbc.Col(embalses_anuales[i + 1], md=6, className="mb-2"))
            filas.append(dbc.Row(cols, className="g-2"))
        
        contenedor_embalses = html.Div(filas)
        
        return fig_lineas, contenedor_embalses
        
    except Exception as e:
        logger.error(f"❌ Error en comparación anual hidrología: {e}")
        import traceback
        traceback.print_exc()
        return (
            go.Figure().add_annotation(text=f"Error: {str(e)}", xref="paper", yref="paper", x=0.5, y=0.5),
            dbc.Alert(f"Error procesando datos: {str(e)}", color="danger")
        )


