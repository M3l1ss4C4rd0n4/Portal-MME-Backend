from dash import dcc, html, Input, Output, callback, register_page
import dash_bootstrap_components as dbc
from datetime import date, timedelta, datetime
import pandas as pd
import plotly.express as px

# Imports locales para componentes uniformes
from interface.components.layout import crear_navbar_horizontal, crear_boton_regresar
from core.constants import UIColors as COLORS
from domain.services.metrics_service import MetricsService

# Inicializar servicio
metrics_service = MetricsService()

register_page(
    __name__,
    path="/generacion",
    name="Generación",
    title="Generación Eléctrica - Ministerio de Minas y Energía",
    order=2
)

# Definir las tecnologías de generación - Hidrología y Generación por Fuente
GENERACION_TECHNOLOGIES = [
    {"name": "Hidrología", "path": "/generacion/hidraulica/hidrologia", "icon": "fas fa-tint", "color": COLORS['energia_hidraulica'], "description": "Análisis de caudales, aportes, niveles de embalses y mapa de riesgo hidrológico"},
    {"name": "Generación por Fuente", "path": "/generacion/fuentes", "icon": "fas fa-layer-group", "color": COLORS['primary'], "description": "Análisis unificado por tipo de fuente: Eólica, Solar, Térmica y Biomasa"}
]

def formatear_fecha_espanol(fecha_obj):
    """
    Convierte un objeto date a formato español con indicador de antigüedad.
    
    - Datos del año actual: '21 de octubre'
    - Datos de años anteriores: '21 de octubre de 2024'
    - Datos con más de 7 días: '21 de octubre (hace 10 días)'
    """
    meses = {
        1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
        5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
        9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
    }
    
    hoy = date.today()
    dias_antiguedad = (hoy - fecha_obj).days
    
    # Formato base
    fecha_texto = f"{fecha_obj.day} de {meses[fecha_obj.month]}"
    
    # Agregar año si es de un año diferente
    if fecha_obj.year != hoy.year:
        fecha_texto += f" de {fecha_obj.year}"
    
    # Agregar indicador de antigüedad si tiene más de 2 días
    if dias_antiguedad > 2:
        fecha_texto += f" (hace {dias_antiguedad} días)"
    elif dias_antiguedad == 1:
        fecha_texto += " (ayer)"
    elif dias_antiguedad == 2:
        fecha_texto += " (hace 2 días)"
    
    return fecha_texto

def obtener_datos_fichas_realtime(metrica, entidad, fecha_inicio, fecha_fin):
    """
    Obtener datos para fichas del tablero usando MetricsService (Domain Layer).
    
    Args:
        metrica: Métrica XM (ej: 'VoluUtilDiarEner', 'Gene')
        entidad: Entidad (ej: 'Embalse', 'Sistema')
        fecha_inicio: Fecha inicio (str 'YYYY-MM-DD' o date)
        fecha_fin: Fecha fin (str 'YYYY-MM-DD' o date)
    
    Returns:
        DataFrame con columna 'valor_gwh' (API XM o SQLite) o None
    """
    import logging
    logger = logging.getLogger('generacion_dashboard')
    
    # Convertir fechas a string si es necesario
    if isinstance(fecha_inicio, date):
        fecha_inicio = fecha_inicio.strftime('%Y-%m-%d')
    if isinstance(fecha_fin, date):
        fecha_fin = fecha_fin.strftime('%Y-%m-%d')
    
    try:
        # Usar el servicio de dominio (Hybrid: DB + API)
        df = metrics_service.get_metric_series_hybrid(
            metric_id=metrica, 
            entity=entidad, 
            start_date=fecha_inicio, 
            end_date=fecha_fin
        )
        
        if df is not None and not df.empty:
            # Estandarizar columna 'valor_gwh' para la UI
            if 'valor_gwh' in df.columns:
                logger.info(f"[MetricsService] {len(df)} registros obtenidos (GWh)")
                return df
                
            if 'Value' in df.columns:
                # Conversión estándar: kWh -> GWh (XM API por defecto)
                df['valor_gwh'] = df['Value'] / 1_000_000
                logger.info(f"[MetricsService] {len(df)} registros obtenidos (Convirtiendo kWh -> GWh)")
                return df
            
            logger.warning(f"[MetricsService] Datos obtenidos sin columna 'Value' ni 'valor_gwh'")
            return None
            
        logger.warning(f"[MetricsService] Sin datos disponibles para {metrica}/{entidad}")
        return None

    except Exception as e:
        logger.error(f"[MetricsService] Error consultando {metrica}: {e}")
        return None

def obtener_metricas_hidricas():
    """
    Obtener métricas de reservas, aportes hídricos y generación total.
    
    NUEVA ARQUITECTURA PARA FICHAS (2025-11-24):
    - API XM como fuente PRIMARIA (tiempo real, datos actualizados)
    - SQLite como FALLBACK (si API no disponible)
    - Conversión automática de unidades según fuente
    
    METODOLOGÍA OFICIAL XM:
    1. Reservas Hídricas = (Volumen Útil / Capacidad Útil) * 100
    2. Aportes Hídricos = (Promedio mensual Real / Promedio mensual Histórico) * 100
    3. Generación SIN = Suma de generación diaria
    """
    try:
        fecha_fin = date.today() - timedelta(days=1)
        reserva_pct, reserva_gwh, fecha_reserva = None, None, None
        aporte_pct, aporte_gwh, fecha_aporte = None, None, None
        gen_gwh, fecha_gen = None, None
        
        # === 1. RESERVAS HÍDRICAS ===
        # Buscar datos válidos (hasta 5 días atrás) - validar volumen > 10,000 GWh
        for dias_atras in range(6):
            fecha_busqueda = (fecha_fin - timedelta(days=dias_atras)).strftime('%Y-%m-%d')
            
            # Obtener volumen y capacidad desde API XM (primero) o SQLite (fallback)
            df_vol = obtener_datos_fichas_realtime('VoluUtilDiarEner', 'Embalse', fecha_busqueda, fecha_busqueda)
            df_cap = obtener_datos_fichas_realtime('CapaUtilDiarEner', 'Embalse', fecha_busqueda, fecha_busqueda)
            
            if df_vol is not None and not df_vol.empty and df_cap is not None and not df_cap.empty:
                # Valores en GWh (ya convertidos por obtener_datos_fichas_realtime)
                vol_total_gwh = df_vol['valor_gwh'].sum()
                cap_total_gwh = df_cap['valor_gwh'].sum()
                
                # VALIDACIÓN COMPLETITUD: contar embalses con volumen vs capacidad
                # Rechazar si menos del 80% de embalses reportaron volumen
                col_recurso_v = next((c for c in ['recurso', 'Embalse', 'Values_code'] if c in df_vol.columns), None)
                col_recurso_c = next((c for c in ['recurso', 'Embalse', 'Values_code'] if c in df_cap.columns), None)
                
                if col_recurso_v and col_recurso_c:
                    n_vol = df_vol[col_recurso_v].nunique()
                    n_cap = df_cap[col_recurso_c].nunique()
                    if n_cap > 0 and n_vol / n_cap < 0.80:
                        print(f"Datos incompletos {fecha_busqueda}: n_vol={n_vol}, n_cap={n_cap}, ratio={n_vol/n_cap:.2f}")
                        continue
                
                if cap_total_gwh > 0:
                    reserva_pct = round((vol_total_gwh / cap_total_gwh) * 100, 2)
                    reserva_gwh = round(vol_total_gwh, 2)
                    fecha_reserva = datetime.strptime(fecha_busqueda, '%Y-%m-%d').date()
                    print(f"Reservas: {reserva_pct}% ({reserva_gwh:,.2f} GWh) - {fecha_busqueda}{' (datos históricos)' if dias_atras > 0 else ''} [API XM ↔ SQLite]")
                    break
        
        # === 2. APORTES HÍDRICOS ===
        # Promedio del mes actual (día 1 hasta ayer)
        fecha_inicio_mes = fecha_fin.replace(day=1).strftime('%Y-%m-%d')
        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')
        
        df_aportes = obtener_datos_fichas_realtime('AporEner', 'Sistema', fecha_inicio_mes, fecha_fin_str)
        df_media = obtener_datos_fichas_realtime('AporEnerMediHist', 'Sistema', fecha_inicio_mes, fecha_fin_str)
        
        if df_aportes is not None and not df_aportes.empty and df_media is not None and not df_media.empty:
            # Valores en GWh (ya convertidos por obtener_datos_fichas_realtime)
            aportes_promedio = df_aportes['valor_gwh'].mean()
            media_promedio = df_media['valor_gwh'].mean()
            
            if media_promedio > 0:
                aporte_pct = round((aportes_promedio / media_promedio) * 100, 2)
                aporte_gwh = round(media_promedio, 2)  # Mostrar Media Histórica (como XM)
                fecha_aporte = fecha_fin
                print(f"Aportes: {aporte_pct}% (Real: {aportes_promedio:.2f} GWh, Hist: {media_promedio:.2f} GWh) [API XM ↔ SQLite]")
        
        # === 3. GENERACIÓN SIN ===
        # Buscar última fecha con datos
        for dias_atras in range(6):
            fecha_busqueda = (fecha_fin - timedelta(days=dias_atras)).strftime('%Y-%m-%d')
            df_gen = obtener_datos_fichas_realtime('Gene', 'Sistema', fecha_busqueda, fecha_busqueda)
            
            if df_gen is not None and not df_gen.empty:
                # Valor en GWh (ya convertido por obtener_datos_fichas_realtime)
                gen_gwh = round(df_gen['valor_gwh'].iloc[0], 2)
                fecha_gen = datetime.strptime(fecha_busqueda, '%Y-%m-%d').date()
                print(f"Generación SIN: {gen_gwh:.2f} GWh - {fecha_busqueda} [API XM ↔ SQLite]")
                break

        
        return crear_fichas_hidricas_con_datos(
            reserva_pct, reserva_gwh, fecha_reserva,
            aporte_pct, aporte_gwh, fecha_aporte,
            gen_gwh, fecha_gen
        )
        
    except Exception as e:
        print(f"Error obteniendo métricas hídricas: {e}")
        import traceback
        traceback.print_exc()
        return html.Div("No se pudieron obtener datos de XM. Intente más tarde.", 
                       style={"color": "red", "padding": "20px", "textAlign": "center"})

def crear_fichas_hidricas_con_datos(reserva_pct, reserva_gwh, fecha_reserva,
                                    aporte_pct, aporte_gwh, fecha_aporte,
                                    gen_gwh, fecha_gen):
    """Crear fichas usando datos reales calculados con metodología XM"""
    
    # Formatear fechas con indicador de antigüedad
    fecha_texto_reserva = formatear_fecha_espanol(fecha_reserva) if fecha_reserva else "Sin datos disponibles"
    fecha_texto_aporte = formatear_fecha_espanol(fecha_aporte) if fecha_aporte else "Sin datos disponibles"
    fecha_texto_gen = formatear_fecha_espanol(fecha_gen) if fecha_gen else "Sin datos disponibles"
    
    # Valores por defecto si no hay datos - mostrar "N/D" en lugar de 0
    if reserva_pct is None:
        reserva_pct_texto, reserva_gwh_texto = "N/D", "Sin datos"
    else:
        reserva_pct_texto, reserva_gwh_texto = f"{reserva_pct:.2f}", f"{reserva_gwh:,.2f} GWh"
    
    if aporte_pct is None:
        aporte_pct_texto, aporte_gwh_texto = "N/D", "Sin datos"
    else:
        aporte_pct_texto, aporte_gwh_texto = f"{aporte_pct:.2f}", f"{aporte_gwh:.2f} GWh"
    
    if gen_gwh is None:
        gen_gwh_texto = "N/D"
    else:
        gen_gwh_texto = f"{gen_gwh:.2f}"
    
    return dbc.Row([
        # Ficha 1: Reservas Hídricas
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-water fa-2x mb-3", 
                              style={'color': '#86D293'}),
                        html.H6("Reservas Hídricas [%]", 
                               className="text-muted mb-2",
                               style={'fontSize': '0.85rem'}),
                        html.H3(reserva_pct_texto, 
                               className="mb-1",
                               style={
                                   'color': '#86D293',
                                   'fontWeight': 'bold',
                                   'fontSize': '2rem'
                               }),
                        html.P(reserva_gwh_texto, 
                              className="text-muted mb-2",
                              style={'fontSize': '0.8rem'}),
                        html.P(fecha_texto_reserva, 
                              className="text-muted mb-0",
                              style={'fontSize': '0.75rem'})
                    ], style={'textAlign': 'center'})
                ], style={
                    'background': 'linear-gradient(135deg, #86D293 0%, #6BC47D 100%)',
                    'borderRadius': '12px',
                    'color': 'white',
                    'padding': '1.5rem'
                })
            ], className="xm-card h-100")
        ], lg=4, md=6, className="mb-4"),
        
        # Ficha 2: Aportes Hídricos
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-tint fa-2x mb-3", 
                              style={'color': '#4DA6FF'}),
                        html.H6("Aportes Hídricos [%]", 
                               className="text-muted mb-2",
                               style={'fontSize': '0.85rem'}),
                        html.H3(aporte_pct_texto, 
                               className="mb-1",
                               style={
                                   'color': '#4DA6FF',
                                   'fontWeight': 'bold',
                                   'fontSize': '2rem'
                               }),
                        html.P(aporte_gwh_texto, 
                              className="text-muted mb-2",
                              style={'fontSize': '0.8rem'}),
                        html.P(fecha_texto_aporte, 
                              className="text-muted mb-0",
                              style={'fontSize': '0.75rem'})
                    ], style={'textAlign': 'center'})
                ], style={
                    'background': 'linear-gradient(135deg, #4DA6FF 0%, #3D8FE8 100%)',
                    'borderRadius': '12px',
                    'color': 'white',
                    'padding': '1.5rem'
                })
            ], className="xm-card h-100")
        ], lg=4, md=6, className="mb-4"),
        
        # Ficha 3: Generación SIN
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-bolt fa-2x mb-3", 
                              style={'color': '#FFB84D'}),
                        html.H6("Generación SIN", 
                               className="text-muted mb-2",
                               style={'fontSize': '0.85rem'}),
                        html.H3(gen_gwh_texto, 
                               className="mb-1",
                               style={
                                   'color': '#FFB84D',
                                   'fontWeight': 'bold',
                                   'fontSize': '2rem'
                               }),
                        html.P("GWh/día", 
                              className="text-muted mb-2",
                              style={'fontSize': '0.8rem'}),
                        html.P(fecha_texto_gen, 
                              className="text-muted mb-0",
                              style={'fontSize': '0.75rem'})
                    ], style={'textAlign': 'center'})
                ], style={
                    'background': 'linear-gradient(135deg, #FFB84D 0%, #FFA726 100%)',
                    'borderRadius': '12px',
                    'color': 'white',
                    'padding': '1.5rem'
                })
            ], className="xm-card h-100")
        ], lg=4, md=6, className="mb-4")
    ])

def crear_fichas_hidricas_fallback():
    """Crear fichas de Reservas, Aportes y Generación Total con datos de fallback"""
    def crear_fichas_hidricas_fallback():
        # Eliminada función de fallback. Si no hay datos, mostrar mensaje de error.
        return html.Div("No se pudieron obtener datos reales de XM. Intente más tarde.", style={"color": "red"})
    
    # Código original comentado temporalmente
    """
    try:
        if not PYDATAXM_AVAILABLE:
            return crear_fichas_generacion_xm_fallback()
        
        objetoAPI = ReadDB()
        fecha_actual = date.today()
        fecha_disponible = None
        
        # Buscar fecha con datos disponibles (hasta 3 días atrás para ser más rápido)
        for i in range(3):
            fecha_prueba = fecha_actual - timedelta(days=i)
            print(f"Buscando datos de generación XM para {fecha_prueba.strftime('%Y-%m-%d')}")
            
            try:
                # Intentar obtener datos de generación por recurso con timeout
                df_gene = objetoAPI.request_data(
                    "Gene",
                    "Recurso",
                    fecha_prueba.strftime("%Y-%m-%d"),
                    fecha_prueba.strftime("%Y-%m-%d")
                )
                
                if df_gene is not None and not df_gene.empty:
                    fecha_disponible = fecha_prueba
                    print(f"Datos de generación encontrados para {fecha_disponible.strftime('%Y-%m-%d')}")
                    break
                else:
                    print(f"Sin datos para {fecha_prueba.strftime('%Y-%m-%d')}")
            except Exception as e:
                print(f"Error al consultar {fecha_prueba.strftime('%Y-%m-%d')}: {str(e)[:100]}")
                continue
        
        if fecha_disponible is None:
            print(f"No hay datos de generación disponibles en los últimos 3 días, usando fallback")
            return crear_fichas_generacion_xm_fallback()
        
        # Obtener datos de generación por recurso
        df_gene = objetoAPI.request_data(
            "Gene",
            "Recurso",
            fecha_disponible.strftime("%Y-%m-%d"),
            fecha_disponible.strftime("%Y-%m-%d")
        )
        
        # Definir recursos renovables y no renovables
        recursos_renovables = ['HIDRAULICA', 'EOLICA', 'SOLAR', 'BIOMASA']
        recursos_no_renovables = ['TERMICA', 'GAS', 'CARBON']
        
        # Calcular generación por tipo
        generacion_renovable_kwh = 0
        generacion_no_renovable_kwh = 0
        
        # Sumar las columnas de horas (Values_Hour_1 a Values_Hour_24)
        horas_cols = [col for col in df_gene.columns if col.startswith('Values_Hour')]
        
        for idx, row in df_gene.iterrows():
            recurso = row.get('Id', '').upper()
            gen_total = row[horas_cols].sum() if horas_cols else 0
            
            if any(r in recurso for r in recursos_renovables):
                generacion_renovable_kwh += gen_total
            elif any(r in recurso for r in recursos_no_renovables):
                generacion_no_renovable_kwh += gen_total
        
        # Convertir de kWh a GWh
        generacion_renovable_gwh = generacion_renovable_kwh / 1000000
        generacion_no_renovable_gwh = generacion_no_renovable_kwh / 1000000
        generacion_total_gwh = generacion_renovable_gwh + generacion_no_renovable_gwh
        
        # Calcular porcentajes
        porcentaje_renovable = (generacion_renovable_gwh / generacion_total_gwh * 100) if generacion_total_gwh > 0 else 0
        porcentaje_no_renovable = (generacion_no_renovable_gwh / generacion_total_gwh * 100) if generacion_total_gwh > 0 else 0
        
        print(f"Generación Renovable: {generacion_renovable_gwh:.2f} GWh ({porcentaje_renovable:.2f}%)")
        print(f"Generación No Renovable: {generacion_no_renovable_gwh:.2f} GWh ({porcentaje_no_renovable:.2f}%)")
        print(f"Generación Total: {generacion_total_gwh:.2f} GWh")
        
        return crear_fichas_generacion_xm(
            porcentaje_renovable,
            porcentaje_no_renovable,
            generacion_total_gwh,
            fecha_disponible
        )
        
    except Exception as e:
        print(f"Error obteniendo datos de generación XM: {str(e)[:200]}")
        return crear_fichas_generacion_xm_fallback()
    """

def crear_fichas_generacion_xm(porcentaje_renovable, porcentaje_no_renovable, generacion_total_gwh, fecha):
    """Crear las 3 fichas de generación XM con datos reales"""
    fecha_texto = formatear_fecha_espanol(fecha)
    
    return dbc.Row([
        # Ficha Generación Renovable %
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-leaf fa-2x mb-2", style={"color": "#86D293"}),
                        html.H6("Generación Renovable [%]", className="card-title text-center mb-2", 
                               style={"fontWeight": "700", "color": "#2C3E50", "fontSize": "0.85rem"}),
                        html.H3(f"{porcentaje_renovable:.2f}", className="text-center mb-1",
                               style={"fontWeight": "800", "color": "#86D293", "fontSize": "2.5rem", "letterSpacing": "-1px"}),
                        html.Small(f"{fecha_texto}", 
                                  className="text-muted d-block text-center",
                                  style={"fontSize": "0.7rem", "opacity": "0.7"})
                    ], className="text-center")
                ], className="py-2")
            ], className="h-100 xm-card", style={
                "border": "none",
                "borderRadius": "16px",
                "background": "linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%)",
                "--card-color": "#86D293"
            })
        ], width=12, lg=4, md=4, className="mb-3"),
        
        # Ficha Generación No Renovable %
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-industry fa-2x mb-2", style={"color": "#FF6B6B"}),
                        html.H6("Generación No Renovable [%]", className="card-title text-center mb-2",
                               style={"fontWeight": "700", "color": "#2C3E50", "fontSize": "0.85rem"}),
                        html.H3(f"{porcentaje_no_renovable:.2f}", className="text-center mb-1",
                               style={"fontWeight": "800", "color": "#FF6B6B", "fontSize": "2.5rem", "letterSpacing": "-1px"}),
                        html.Small(f"{fecha_texto}", 
                                  className="text-muted d-block text-center",
                                  style={"fontSize": "0.7rem", "opacity": "0.7"})
                    ], className="text-center")
                ], className="py-2")
            ], className="h-100 xm-card", style={
                "border": "none",
                "borderRadius": "16px",
                "background": "linear-gradient(135deg, #ffffff 0%, #fff1f0 100%)",
                "--card-color": "#FF6B6B"
            })
        ], width=12, lg=4, md=4, className="mb-3"),
        
        # Ficha Generación Total GWh
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-bolt fa-2x mb-2", style={"color": "#4285F4"}),
                        html.H6("Generación Total [GWh]", className="card-title text-center mb-2",
                               style={"fontWeight": "700", "color": "#2C3E50", "fontSize": "0.85rem"}),
                        html.H3(f"{generacion_total_gwh:,.2f}", className="text-center mb-1",
                               style={"fontWeight": "800", "color": "#4285F4", "fontSize": "2.5rem", "letterSpacing": "-1px"}),
                        html.Small(f"{fecha_texto}", 
                                  className="text-muted d-block text-center",
                                  style={"fontSize": "0.7rem", "opacity": "0.7"})
                    ], className="text-center")
                ], className="py-2")
            ], className="h-100 xm-card", style={
                "border": "none",
                "borderRadius": "16px",
                "background": "linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%)",
                "--card-color": "#4285F4"
            })
        ], width=12, lg=4, md=4, className="mb-3")
    ], className="mb-4")

def crear_fichas_generacion_xm_fallback():
    # Eliminada función de fallback. Si no hay datos, mostrar mensaje de error.
    return html.Div("No se pudieron obtener datos reales de XM. Intente más tarde.", style={"color": "red"})

def create_technology_card(tech):
    """Crear tarjeta para cada tecnología de generación"""
    return dbc.Col([
        html.A([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(
                            className=tech["icon"],
                            style={
                                "fontSize": "5rem",
                                "color": tech["color"],
                                "marginBottom": "1.5rem"
                            }
                        ),
                        html.H4(tech["name"], 
                               className="mb-2",
                               style={"color": COLORS['text_primary'], "fontWeight": "600"}),
                        html.P(tech["description"],
                              className="text-muted small mb-0",
                              style={"fontSize": "0.9rem"})
                    ], className="text-center"),
                ], className="py-4")
            ], 
            className="h-100 shadow-sm tech-card",
            style={
                "cursor": "pointer",
                "transition": "all 0.3s ease",
                "border": f"2px solid {tech['color']}30"
            }
            )
        ], href=tech["path"], style={"textDecoration": "none"})
    ], lg=6, md=6, sm=12, className="mb-4")  # Cambiado de lg=4 a lg=6 para 2 columnas

layout = html.Div([
    # Navbar horizontal
    # crear_navbar_horizontal(),
    
    # Container principal
    dbc.Container([
        # Botón de regreso eliminado
        
        # Sección con imagen y fichas lado a lado
        dbc.Row([
            # Columna izquierda: Imagen
            dbc.Col([
                html.Div([
                    html.Img(
                        src="/assets/images/Recurso 1.png",
                        alt="Generación Eléctrica",
                        style={
                            "width": "100%",
                            "height": "100%",
                            "objectFit": "contain",
                            "minHeight": "600px"
                        },
                        className="mb-3"
                    )
                ], style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "height": "100%"
                })
            ], lg=4, md=12, className="mb-4 d-flex align-items-start"),
            
            # Columna derecha: Fichas y botones
            dbc.Col([
                # Subtítulo para KPIs
                html.H5("Indicadores Clave del Sistema", 
                       className="text-center mb-3",
                       style={"color": COLORS['text_primary'], "fontWeight": "600"}),
                
                # Fichas de Reservas, Aportes y Generación - Se cargan dinámicamente
                dcc.Loading(
                    id="loading-fichas-hidricas",
                    type="default",
                    children=html.Div(id="fichas-hidricas-container", className="mb-3")
                ),
                
                # Subtítulo para tecnologías
                html.H5("Explorar por Tecnología", 
                       className="text-center mt-3 mb-3",
                       style={"color": COLORS['text_primary'], "fontWeight": "600"}),
                
                # Tarjetas de tecnologías
                dbc.Row([
                    create_technology_card(tech) for tech in GENERACION_TECHNOLOGIES
                ]),
            ], lg=8, md=12)
        ], className="mb-4"),
        
    ], fluid=True, className="py-4")
])

# Callback para cargar las fichas hídricas de forma asíncrona
@callback(
    Output("fichas-hidricas-container", "children"),
    Input("fichas-hidricas-container", "id")
)
def cargar_fichas_hidricas(_):
    """Cargar las fichas de reservas, aportes y generación de forma asíncrona"""
    try:
        return obtener_metricas_hidricas()
    except Exception as e:
        print(f"Error en callback de fichas hídricas: {e}")
        return html.Div("No se pudieron obtener datos reales de XM. Intente más tarde.", style={"color": "red"})
