"""
Hidrología - KPIs y Fichas Informativas
=========================================

Funciones para crear fichas KPI, paneles de control y resúmenes.
"""

import pandas as pd
from dash import dcc, html
import dash_bootstrap_components as dbc
from datetime import date, timedelta

from infrastructure.external.xm_service import obtener_datos_inteligente

from interface.components.layout import registrar_callback_filtro_fechas
from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import crear_filter_bar
from core.constants import UIColors as COLORS

from .utils import (
    logger, get_reservas_hidricas, get_aportes_hidricos,
    ensure_rio_region_loaded,
)
from .data_services import (
    get_aportes_hidricos_por_region,
    get_aportes_hidricos_por_rio,
    get_reservas_hidricas_por_region,
    get_porcapor_data,
)

def crear_fichas_sin_seguras(region=None, rio=None):
    """
    Versión segura de crear_fichas_sin para uso en layout inicial
    con soporte para filtros por región y río.
    """
    try:
        logger.debug("[DEBUG] crear_fichas_sin_seguras ejecutándose...")
        return crear_fichas_sin(region=region, rio=rio)
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        # Devolver fichas temporales con datos de prueba
        return crear_fichas_temporales()



def crear_fichas_temporales():
    """Crear fichas temporales con datos de prueba basados en valores reales de XM"""
    return crear_kpi_row([
        {"titulo": "Reservas Hídricas", "valor": "82.48", "unidad": "%", "icono": "fas fa-water", "color": "green", "subtexto": "SIN Completo • Datos de prueba"},
        {"titulo": "Aportes Hídricos", "valor": "101.2", "unidad": "%", "icono": "fas fa-tint", "color": "blue", "subtexto": "SIN Completo • Datos de prueba"},
    ], columnas=2)

# Función original con fallback mejorado (comentada temporalmente)
# Esta función será restaurada una vez que se resuelvan los problemas de API



def crear_fichas_sin(fecha=None, region=None, rio=None):
    """
    Crea las fichas KPI de Reservas Hídricas y Aportes Hídricos del SIN
    según los cálculos oficiales de XM.
    
    Nota: Si se especifica región o río, se muestran valores específicos para ese filtro.
    Si no se especifica filtro, se muestran valores del SIN completo.
    
    Args:
        fecha: Fecha para los cálculos (usar fecha de consulta)
        region: Región hidrológica específica (opcional)
        rio: Río específico (opcional)
    """
    # Usar solo la fecha final para los cálculos (ignorar fecha inicial)
    fecha_calculo = fecha if fecha else (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

    # Determinar el contexto de los cálculos SOLO usando la fecha final
    if rio and rio != "__ALL__":
        contexto = f"Río {rio}"
        reservas_pct, reservas_gwh = None, None
        aportes_pct, aportes_m3s = get_aportes_hidricos_por_rio(fecha_calculo, rio)
        reservas_pct_str = "N/A"
        reservas_gwh_str = "No aplica para río individual"
        aportes_pct_str = f"{aportes_pct:.2f}%" if aportes_pct is not None else "N/D"
        aportes_gwh_str = f"{aportes_m3s:,.1f} m³/s".replace(",", ".") if aportes_m3s is not None else "N/D"
    elif region and region != "__ALL_REGIONS__":
        contexto = f"Región {region}"
        reservas_pct, reservas_gwh = get_reservas_hidricas_por_region(fecha_calculo, region)
        aportes_pct, aportes_gwh = get_aportes_hidricos_por_region(fecha_calculo, region)
        reservas_pct_str = f"{reservas_pct:.2f}%" if reservas_pct is not None else "N/D"
        reservas_gwh_str = f"{reservas_gwh:,.0f} GWh".replace(",", ".") if reservas_gwh is not None else "N/D"
        aportes_pct_str = f"{aportes_pct:.2f}%" if aportes_pct is not None else "N/D"
        aportes_gwh_str = f"{aportes_gwh:,.0f} GWh".replace(",", ".") if aportes_gwh is not None else "N/D"
    else:
        contexto = "SIN Completo"
        reservas_pct, reservas_gwh, _ = get_reservas_hidricas(fecha_calculo)
        aportes_pct, aportes_gwh = get_aportes_hidricos(fecha_calculo)
        reservas_pct_str = f"{reservas_pct:.2f}%" if reservas_pct is not None else "N/D"
        reservas_gwh_str = f"{reservas_gwh:,.0f} GWh".replace(",", ".") if reservas_gwh is not None else "N/D"
        aportes_pct_str = f"{aportes_pct:.2f}%" if aportes_pct is not None else "N/D"
        aportes_gwh_str = f"{aportes_gwh:,.0f} GWh".replace(",", ".") if aportes_gwh is not None else "N/D"

    # Determinar colores según porcentajes
    color_reservas = COLORS['success'] if reservas_pct and reservas_pct >= 60 else (COLORS['warning'] if reservas_pct and reservas_pct >= 40 else COLORS['danger'])
    color_aportes = COLORS['success'] if aportes_pct and aportes_pct >= 80 else (COLORS['warning'] if aportes_pct and aportes_pct >= 60 else COLORS['info'])

    # Si no hay reservas por río, usar color neutro
    if reservas_pct is None and rio and rio != "__ALL__":
        color_reservas = COLORS['secondary']

    return dbc.Row([
        # Ficha Reservas Hídricas
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-water fa-2x mb-2", style={"color": color_reservas}),
                        html.H5("Reservas Hídricas", className="card-title text-center", 
                               style={"fontWeight": "600", "color": COLORS['text_primary']}),
                        html.H3(reservas_pct_str, className="text-center mb-1",
                               style={"fontWeight": "bold", "color": color_reservas, "fontSize": "2.5rem"}),
                        html.P(reservas_gwh_str, className="text-center text-muted mb-1",
                              style={"fontSize": "1.1rem", "fontWeight": "500"}),
                        html.Small(f"{contexto} • {fecha_calculo}", 
                                  className="text-muted d-block text-center",
                                  style={"fontSize": "0.8rem"})
                    ], className="text-center")
                ])
            ], className="h-100", style={
                "border": f"1px solid {COLORS['border']}",
                "boxShadow": f"0 2px 4px {COLORS['shadow_sm']}",
                "borderRadius": "8px"
            })
        ], md=6, className="mb-3"),

        # Ficha Aportes Hídricos
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-tint fa-2x mb-2", style={"color": color_aportes}),
                        html.H5("Aportes Hídricos", className="card-title text-center",
                               style={"fontWeight": "600", "color": COLORS['text_primary']}),
                        html.H3(aportes_pct_str, className="text-center mb-1",
                               style={"fontWeight": "bold", "color": color_aportes, "fontSize": "2.5rem"}),
                        html.P(aportes_gwh_str, className="text-center text-muted mb-1",
                              style={"fontSize": "1.1rem", "fontWeight": "500"}),
                        html.Small(f"{contexto} • {fecha_calculo}", 
                                  className="text-muted d-block text-center",
                                  style={"fontSize": "0.8rem"})
                    ], className="text-center")
                ])
            ], className="h-100", style={
                "border": f"1px solid {COLORS['border']}",
                "boxShadow": f"0 2px 4px {COLORS['shadow_sm']}",
                "borderRadius": "8px"
            })
        ], md=6, className="mb-3")
    ], className="mb-4")



def crear_panel_controles():
    return crear_filter_bar(
        html.Span("REGIÓN:", className="t-filter-label"),
        html.Div(
            dcc.Dropdown(
                id="region-dropdown",
                options=[{"label": "Todas las regiones", "value": "__ALL_REGIONS__"}],
                placeholder="Región...",
                style={"width": "160px", "fontSize": "0.8rem"}
            )
        ),
        html.Span("RÍO:", className="t-filter-label"),
        html.Div(
            dcc.Dropdown(
                id="rio-dropdown",
                options=[],
                placeholder="Río...",
                style={"width": "160px", "fontSize": "0.8rem"}
            )
        ),
        html.Span("RANGO:", className="t-filter-label"),
        html.Div(
            dcc.Dropdown(
                id='rango-fechas-hidrologia',
                options=[
                    {'label': 'Último mes', 'value': '1m'},
                    {'label': 'Últimos 6 meses', 'value': '6m'},
                    {'label': 'Último año', 'value': '1y'},
                    {'label': 'Últimos 2 años', 'value': '2y'},
                    {'label': 'Últimos 5 años', 'value': '5y'},
                    {'label': 'Personalizado', 'value': 'custom'}
                ],
                value='1y',
                clearable=False,
                style={"width": "150px", "fontSize": "0.8rem"}
            )
        ),
        html.Div(
            dcc.DatePickerSingle(
                id='fecha-inicio-hidrologia',
                date=(date.today() - timedelta(days=365)).strftime('%Y-%m-%d'),
                display_format='DD/MM/YYYY',
                style={'fontSize': '0.75rem'}
            ),
            id='container-fecha-inicio-hidrologia',
            style={'display': 'none'}
        ),
        html.Div(
            dcc.DatePickerSingle(
                id='fecha-fin-hidrologia',
                date=date.today().strftime('%Y-%m-%d'),
                display_format='DD/MM/YYYY',
                style={'fontSize': '0.75rem'}
            ),
            id='container-fecha-fin-hidrologia',
            style={'display': 'none'}
        ),
        html.Button(
            [html.I(className="fas fa-sync-alt me-1"), "Actualizar"],
            id="btn-actualizar-hidrologia",
            className="t-btn-filter"
        ),
    )

# Función para generar la ficha KPI


def crear_ficha_kpi_inicial():
    """Genera la ficha KPI con datos del último año"""
    try:
        logger.info("🚀 INICIANDO crear_ficha_kpi_inicial()")
        # Calcular fechas: último año
        fecha_fin = date.today()
        fecha_inicio = fecha_fin - timedelta(days=365)
        start_date_str = fecha_inicio.strftime('%Y-%m-%d')
        end_date_str = fecha_fin.strftime('%Y-%m-%d')
        logger.info(f"📅 Fechas: {start_date_str} a {end_date_str}")
        
        # Obtener datos
        data, _ = obtener_datos_inteligente('AporEner', 'Rio', start_date_str, end_date_str)
        if data is None or data.empty:
            logger.warning("⚠️ FICHA INICIAL: No hay datos de AporEner")
            return html.Div()
        
        total_real = data['Value'].sum()
        logger.info(f"📊 Total real: {total_real:.2f} GWh")
        
        # Obtener media histórica usando el mismo rango de fechas
        media_hist_data, _ = obtener_datos_inteligente('AporEnerMediHist', 'Rio', start_date_str, end_date_str)
        
        if media_hist_data is not None and not media_hist_data.empty:
            total_historico = media_hist_data['Value'].sum()
            porcentaje_vs_historico = (total_real / total_historico * 100) if total_historico > 0 else None
            logger.info(f"📊 Histórico: {total_historico:.2f} GWh, Porcentaje: {porcentaje_vs_historico:.1f}%")
        else:
            logger.warning("⚠️ FICHA INICIAL: No hay media histórica")
            return html.Div()
        
        if porcentaje_vs_historico is None:
            logger.warning("⚠️ FICHA INICIAL: porcentaje_vs_historico es None")
            return html.Div()
        
        logger.info(f"✅ FICHA INICIAL CREADA: {porcentaje_vs_historico - 100:+.1f}%")
        # Crear ficha
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
                        html.Span("Estado 2025", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.8rem', 'display': 'block'}),
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
        logger.error(f"❌ Error creando ficha KPI inicial: {e}")
        return html.Div()

# Registrar callback del filtro de fechas
registrar_callback_filtro_fechas('hidrologia')

# Callback para actualizar SOLO la ficha KPI (eficiente - no re-renderiza el panel)


def create_latest_value_kpi(data, metric_name):
    """Crear card KPI que muestra el valor más reciente de la serie temporal"""
    if data is None or data.empty:
        return dbc.Alert("No hay datos disponibles", color="warning", className="mb-3")
    
    # Verificar que tengamos las columnas necesarias
    if 'Date' not in data.columns or 'Value' not in data.columns:
        return dbc.Alert("Faltan columnas necesarias", color="warning", className="mb-3")
    
    # Agrupar por fecha y sumar todos los valores
    daily_totals = data.groupby('Date')['Value'].sum().reset_index()
    daily_totals = daily_totals.sort_values('Date')
    
    if daily_totals.empty:
        return dbc.Alert("No hay datos procesados", color="warning", className="mb-3")
    
    # Obtener el valor más reciente
    latest_date = daily_totals['Date'].iloc[-1]
    latest_value = daily_totals['Value'].iloc[-1]
    
    # Formatear fecha
    if hasattr(latest_date, 'strftime'):
        formatted_date = latest_date.strftime('%d/%m/%Y')
    else:
        formatted_date = str(latest_date)
    
    # Formatear valor
    formatted_value = f"{latest_value:,.0f}".replace(",", ".")
    
    # Calcular tendencia si hay datos suficientes
    trend_icon = ""
    trend_color = "#6c757d"
    trend_text = ""
    trend_bg = "#f8f9fa"
    
    if len(daily_totals) >= 2:
        previous_value = daily_totals['Value'].iloc[-2]
        if previous_value != 0:  # Evitar división por cero
            change = latest_value - previous_value
            change_pct = (change / abs(previous_value) * 100)  # Usar valor absoluto para evitar negativos extraños
            
            if change > 0:
                trend_icon = "bi bi-arrow-up-circle-fill"
                trend_color = "#28a745"
                trend_text = f"+{change_pct:.1f}%"
                trend_bg = "#d4edda"
            elif change < 0:
                trend_icon = "bi bi-arrow-down-circle-fill"
                trend_color = "#dc3545"
                trend_text = f"{change_pct:.1f}%"
                trend_bg = "#f8d7da"
            else:
                trend_icon = "bi bi-dash-circle-fill"
                trend_color = "#6c757d"
                trend_text = "0.0%"
                trend_bg = "#e2e3e5"
        else:
            trend_icon = "bi bi-info-circle-fill"
            trend_color = "#17a2b8"
            trend_text = "N/A"
            trend_bg = "#d1ecf1"
    
    return dbc.Card([
        dbc.CardBody([
            # Contenedor principal centrado
            html.Div([
                # Encabezado con ícono
                html.Div([
                    html.I(className="bi bi-lightning-charge-fill me-2", 
                           style={"fontSize": "1.8rem", "color": "#007bff"}),
                    html.H5("Último Registro", className="text-dark mb-0", 
                            style={"fontSize": "1.1rem", "fontWeight": "600"})
                ], className="d-flex align-items-center justify-content-center mb-4"),
                
                # Contenedor principal con valor y tendencia lado a lado
                dbc.Row([
                    dbc.Col([
                        # Valor principal y unidad
                        html.Div([
                            html.H1(f"{formatted_value}", 
                                    className="mb-1", 
                                    style={
                                        "fontWeight": "800", 
                                        "color": "#2d3748", 
                                        "fontSize": "3.5rem",
                                        "lineHeight": "1",
                                        "textAlign": "center"
                                    }),
                            
                            # Unidad centrada
                            html.P("GWh", 
                                   className="text-primary mb-0", 
                                   style={
                                       "fontSize": "1.3rem", 
                                       "fontWeight": "500",
                                       "textAlign": "center"
                                   }),
                        ], className="text-center")
                    ], md=8),
                    
                    dbc.Col([
                        # Indicador de tendencia al lado
                        html.Div([
                            html.Div([
                                html.I(className=trend_icon, 
                                       style={
                                           "fontSize": "2rem", 
                                           "color": trend_color,
                                           "marginBottom": "5px"
                                       }) if trend_icon else None,
                                html.H5(trend_text, 
                                        className="mb-1", 
                                        style={
                                            "color": trend_color, 
                                            "fontWeight": "700",
                                            "fontSize": "1.2rem"
                                        }) if trend_text else None,
                                html.Small("vs anterior",
                                         className="text-muted",
                                         style={"fontSize": "0.75rem"})
                            ], className="text-center p-2 rounded-3",
                               style={
                                   "backgroundColor": trend_bg,
                                   "border": f"2px solid {trend_color}20"
                               })
                        ], className="d-flex align-items-center justify-content-center h-100")
                    ], md=4)
                ], className="mb-3", align="center"),
                
                # Fecha centrada abajo
                html.Div([
                    html.I(className="bi bi-calendar-date me-2", 
                           style={"color": "#6c757d", "fontSize": "1.1rem"}),
                    html.Span(formatted_date, 
                             style={"fontSize": "1rem", "color": "#6c757d"})
                ], className="d-flex align-items-center justify-content-center")
                
            ], className="px-3")
        ], className="py-4 px-4")
    ], className="shadow border-0 mb-4 mx-auto", 
       style={
           "background": "linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%)",
           "borderRadius": "20px",
           "border": "1px solid #e9ecef",
           "maxWidth": "500px",
           "minHeight": "200px"
       })



def create_porcapor_kpi(fecha_inicio, fecha_fin, region=None, rio=None):
    """Crear tarjeta KPI específica para la métrica PorcApor (Aportes % por río)
    
    Args:
        fecha_inicio: Fecha de inicio del rango
        fecha_fin: Fecha de fin del rango  
        region: Región para filtrar (opcional)
        rio: Río para filtrar (opcional)
    """
    data = get_porcapor_data(fecha_inicio, fecha_fin)
    
    if data is None or data.empty:
        return dbc.Alert("No hay datos de PorcApor disponibles", color="warning", className="mb-3")
    
    # Verificar que tengamos las columnas necesarias
    if 'Date' not in data.columns or 'Value' not in data.columns:
        return dbc.Alert(f"Faltan columnas necesarias en PorcApor. Columnas disponibles: {list(data.columns)}", color="warning", className="mb-3")
    
    # Filtrar por río específico si se especifica
    if rio and rio != "__ALL__":
        data_filtered = data[data['Name'] == rio]
        if data_filtered.empty:
            return dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.H6("Aportes % por Sistema", className="text-center mb-2"),
                        html.Hr(),
                        html.P(f"No hay datos de participación porcentual para el río {rio} en este período.", 
                               className="text-center text-muted mb-2"),
                        html.P("Este río puede estar temporalmente fuera de operación o en mantenimiento.", 
                               className="text-center text-muted small mb-2"),
                        html.P("💡 Selecciona otro río con datos activos como DESV. BATATAS, DESV. CHIVOR, etc.", 
                               className="text-center text-info small")
                    ])
                ])
            ], className="text-center shadow-sm mb-3")
        title_suffix = f" - {rio}"
    else:
        # Filtrar por región si se especifica y no es "todas las regiones"
        if region and region != "__ALL_REGIONS__":
            # Agregar información de región usando el mapeo RIO_REGION
            # ✅ FIX ERROR #3: UPPER en lugar de title
            region_normalized = region.strip().upper()
            rio_region = ensure_rio_region_loaded()
            data['Region'] = data['Name'].map(rio_region) 
            data_filtered = data[data['Region'] == region_normalized]
            if data_filtered.empty:
                return dbc.Alert(f"No hay datos de PorcApor para la región {region_normalized}", color="warning", className="mb-3")
            title_suffix = f" - {region_normalized}"
        else:
            data_filtered = data
            title_suffix = ""
    
    # Agrupar por fecha y calcular promedio de los ríos filtrados
    daily_avg = data_filtered.groupby('Date')['Value'].mean().reset_index()
    daily_avg = daily_avg.sort_values('Date')
    
    if daily_avg.empty:
        return dbc.Alert("No hay datos procesados de PorcApor", color="warning", className="mb-3")
    
    # Obtener el valor más reciente
    latest_date = daily_avg['Date'].iloc[-1]
    latest_value = daily_avg['Value'].iloc[-1]
    formatted_date = pd.to_datetime(latest_date).strftime('%d/%m/%Y')
    
    # Formatear el valor como porcentaje
    formatted_value = f"{latest_value:.1f}"
    
    # Calcular tendencia si hay al menos 2 registros
    if len(daily_avg) >= 2:
        previous_value = daily_avg['Value'].iloc[-2]
        change_percent = ((latest_value - previous_value) / previous_value) * 100
        
        if change_percent > 0:
            trend_icon = "bi bi-arrow-up-circle-fill"
            trend_color = "#28a745"
            trend_text = f"+{change_percent:.1f}%"
            trend_bg = "#d4edda"
        elif change_percent < 0:
            trend_icon = "bi bi-arrow-down-circle-fill"
            trend_color = "#dc3545"
            trend_text = f"{change_percent:.1f}%"
            trend_bg = "#f8d7da"
        else:
            trend_icon = "bi bi-dash-circle-fill"
            trend_color = "#ffc107"
            trend_text = "0.0%"
            trend_bg = "#fff3cd"
    else:
        trend_icon = "bi bi-info-circle-fill"
        trend_color = "#17a2b8"
        trend_text = "N/A"
        trend_bg = "#d1ecf1"

    return dbc.Card([
        dbc.CardBody([
            # Contenedor principal centrado
            html.Div([
                # Encabezado con ícono
                html.Div([
                    html.I(className="bi bi-percent me-2", 
                           style={"fontSize": "1.8rem", "color": "#28a745"}),
                    html.H5(f"Aportes % por Sistema{title_suffix}", className="text-dark mb-0", 
                            style={"fontSize": "1.1rem", "fontWeight": "600"})
                ], className="d-flex align-items-center justify-content-center mb-4"),
                
                # Contenedor principal con valor y tendencia lado a lado
                dbc.Row([
                    dbc.Col([
                        # Valor principal y unidad
                        html.Div([
                            html.H1(f"{formatted_value}", 
                                    className="mb-1", 
                                    style={
                                        "fontWeight": "800", 
                                        "color": "#2d3748", 
                                        "fontSize": "3.5rem",
                                        "lineHeight": "1",
                                        "textAlign": "center"
                                    }),
                            
                            # Unidad centrada
                            html.P("%", 
                                   className="text-success mb-0", 
                                   style={
                                       "fontSize": "1.3rem", 
                                       "fontWeight": "500",
                                       "textAlign": "center"
                                   }),
                        ], className="text-center")
                    ], md=8),
                    
                    dbc.Col([
                        # Indicador de tendencia al lado
                        html.Div([
                            html.Div([
                                html.I(className=trend_icon, 
                                       style={
                                           "fontSize": "2rem", 
                                           "color": trend_color,
                                           "marginBottom": "5px"
                                       }) if trend_icon else None,
                                html.H5(trend_text, 
                                        className="mb-1", 
                                        style={
                                            "color": trend_color, 
                                            "fontWeight": "700",
                                            "fontSize": "1.2rem"
                                        }) if trend_text else None,
                                html.Small("vs anterior",
                                         className="text-muted",
                                         style={"fontSize": "0.75rem"})
                            ], className="text-center p-2 rounded-3",
                               style={
                                   "backgroundColor": trend_bg,
                                   "border": f"2px solid {trend_color}20"
                               })
                        ], className="d-flex align-items-center justify-content-center h-100")
                    ], md=4)
                ], className="mb-3", align="center"),
                
                # Fecha centrada abajo
                html.Div([
                    html.I(className="bi bi-calendar-date me-2", 
                           style={"color": "#6c757d", "fontSize": "1.1rem"}),
                    html.Span(formatted_date, 
                             style={"fontSize": "1rem", "color": "#6c757d"})
                ], className="d-flex align-items-center justify-content-center")
                
            ], className="px-3")
        ], className="py-4 px-4")
    ], className="shadow border-0 mb-4 mx-auto", 
       style={
           "background": "linear-gradient(135deg, #e8f5e8 0%, #f0f8f0 100%)",
           "borderRadius": "20px",
           "border": "1px solid #28a745",
           "maxWidth": "500px",
           "minHeight": "200px"
       })



