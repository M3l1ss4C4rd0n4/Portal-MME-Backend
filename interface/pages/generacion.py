from dash import dcc, html, Input, Output, callback, register_page
from datetime import date, timedelta, datetime

# Imports locales para componentes uniformes
from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import crear_page_header
from core.constants import UIColors as COLORS
from domain.services.metrics_service import MetricsService
from domain.services.hydrology_service import HydrologyService

# Inicializar servicios
metrics_service = MetricsService()
hydrology_service = HydrologyService()

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
        DataFrame con columna 'valor_gwh' (API XM o PostgreSQL) o None
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
    
    UNIFICADO (2026-04-21):
    - Usa HydrologyService (misma fuente que Portal de Dirección)
    - Reservas: PorcVoluUtilDiar/Sistema (precalculado XM) → fallback manual
    - Aportes: AporEner/Rio suma acumulada mensual / AporEnerMediHist/Rio suma acumulada
    - Generación SIN: Suma de generación diaria
    """
    try:
        fecha_fin = date.today() - timedelta(days=1)
        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')
        reserva_pct, reserva_gwh, fecha_reserva = None, None, None
        aporte_pct, aporte_gwh, fecha_aporte = None, None, None
        gen_gwh, fecha_gen = None, None
        
        # === 1. RESERVAS HÍDRICAS ===
        # Usar HydrologyService (intenta PorcVoluUtilDiar/Sistema primero)
        _pct, _gwh, _fecha = hydrology_service.get_reservas_hidricas(fecha_fin_str)
        if _pct is not None:
            reserva_pct = round(_pct, 2)
            reserva_gwh = _gwh
            fecha_reserva = datetime.strptime(_fecha, '%Y-%m-%d').date() if _fecha else fecha_fin
            print(f"Reservas: {reserva_pct}% ({reserva_gwh:,.2f} GWh) — {_fecha} [HydrologyService]")
        
        # === 2. APORTES HÍDRICOS ===
        # Usar HydrologyService (fórmula oficial XM: suma Rio / suma Rio media hist)
        _aporte_pct, _aporte_gwh = hydrology_service.get_aportes_hidricos(fecha_fin_str)
        if _aporte_pct is not None:
            aporte_pct = round(_aporte_pct, 2)
            aporte_gwh = round(_aporte_gwh, 2)
            fecha_aporte = fecha_fin
            print(f"Aportes: {aporte_pct}% ({aporte_gwh:.2f} GWh) — {fecha_fin_str} [HydrologyService]")
        
        # === 3. GENERACIÓN SIN ===
        # Buscar última fecha con datos
        for dias_atras in range(6):
            fecha_busqueda = (fecha_fin - timedelta(days=dias_atras)).strftime('%Y-%m-%d')
            df_gen = obtener_datos_fichas_realtime('Gene', 'Sistema', fecha_busqueda, fecha_busqueda)
            
            if df_gen is not None and not df_gen.empty:
                # Valor en GWh (ya convertido por obtener_datos_fichas_realtime)
                gen_gwh = round(df_gen['valor_gwh'].iloc[0], 2)
                fecha_gen = datetime.strptime(fecha_busqueda, '%Y-%m-%d').date()
                print(f"Generación SIN: {gen_gwh:.2f} GWh - {fecha_busqueda} [API XM ↔ PostgreSQL]")
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
    
    return crear_kpi_row([
        {
            "titulo": "Reservas Hídricas",
            "valor": reserva_pct_texto,
            "unidad": "%",
            "icono": "fas fa-water",
            "color": "green",
            "subtexto": f"{reserva_gwh_texto} — {fecha_texto_reserva}",
        },
        {
            "titulo": "Aportes Hídricos",
            "valor": aporte_pct_texto,
            "unidad": "%",
            "icono": "fas fa-tint",
            "color": "blue",
            "subtexto": f"{aporte_gwh_texto} — {fecha_texto_aporte}",
        },
        {
            "titulo": "Generación SIN",
            "valor": gen_gwh_texto,
            "unidad": "GWh/día",
            "icono": "fas fa-bolt",
            "color": "orange",
            "subtexto": fecha_texto_gen,
        },
    ], columnas=3)

def crear_fichas_hidricas_fallback():
    """Crear fichas de Reservas, Aportes y Generación Total con datos de fallback"""
    return html.Div("No se pudieron obtener datos reales de XM. Intente más tarde.", style={"color": "red"})

def crear_fichas_generacion_xm(porcentaje_renovable, porcentaje_no_renovable, generacion_total_gwh, fecha):
    """Crear las 3 fichas de generación XM con datos reales"""
    fecha_texto = formatear_fecha_espanol(fecha)
    
    return crear_kpi_row([
        {
            "titulo": "Generación Renovable",
            "valor": f"{porcentaje_renovable:.2f}",
            "unidad": "%",
            "icono": "fas fa-leaf",
            "color": "green",
            "subtexto": fecha_texto,
        },
        {
            "titulo": "Generación No Renovable",
            "valor": f"{porcentaje_no_renovable:.2f}",
            "unidad": "%",
            "icono": "fas fa-industry",
            "color": "red",
            "subtexto": fecha_texto,
        },
        {
            "titulo": "Generación Total",
            "valor": f"{generacion_total_gwh:,.2f}",
            "unidad": "GWh",
            "icono": "fas fa-bolt",
            "color": "blue",
            "subtexto": fecha_texto,
        },
    ], columnas=3)

def crear_fichas_generacion_xm_fallback():
    # Eliminada función de fallback. Si no hay datos, mostrar mensaje de error.
    return html.Div("No se pudieron obtener datos reales de XM. Intente más tarde.", style={"color": "red"})

def create_technology_card(tech):
    """Crear tarjeta para cada tecnología de generación"""
    return html.A([
        html.Div([
            html.Div([
                html.I(
                    className=tech["icon"],
                    style={"fontSize": "2rem", "color": tech["color"]}
                ),
            ], className="t-kpi-icon", style={"background": f"{tech['color']}18", "width": "56px", "height": "56px", "borderRadius": "12px", "display": "flex", "alignItems": "center", "justifyContent": "center"}),
            html.Div([
                html.H4(tech["name"], style={"margin": "0", "fontSize": "1rem", "fontWeight": "600", "color": "#1e293b"}),
                html.P(tech["description"], style={"margin": "4px 0 0", "fontSize": "0.8rem", "color": "#64748b", "lineHeight": "1.3"}),
            ]),
        ], className="t-kpi t-fade-in", style={"cursor": "pointer"}),
    ], href=tech["path"], style={"textDecoration": "none"})

layout = html.Div([
    crear_page_header(
        titulo="Generación Eléctrica",
        icono="fas fa-bolt",
        breadcrumb="Inicio / Generación",
    ),

    # Grid: imagen + contenido
    html.Div([
        # Imagen
        html.Div([
            html.Img(
                src="/assets/images/Recurso 1.png",
                alt="Generación Eléctrica",
                style={"width": "100%", "maxHeight": "500px", "objectFit": "contain"},
            )
        ], style={"flex": "1", "minWidth": "280px"}),

        # KPIs + tecnologías
        html.Div([
            html.H3("Indicadores Clave del Sistema",
                    style={"fontSize": "1rem", "fontWeight": "600", "color": "#1e293b", "marginBottom": "12px"}),

            dcc.Loading(
                id="loading-fichas-hidricas",
                type="dot",
                color="#3b82f6",
                children=html.Div(id="fichas-hidricas-container"),
            ),

            html.H3("Explorar por Tecnología",
                    style={"fontSize": "1rem", "fontWeight": "600", "color": "#1e293b", "margin": "20px 0 12px"}),

            html.Div([
                create_technology_card(tech) for tech in GENERACION_TECHNOLOGIES
            ], className="t-grid t-grid-2"),
        ], style={"flex": "2", "minWidth": "400px"}),
    ], style={"display": "flex", "gap": "24px", "flexWrap": "wrap", "alignItems": "flex-start"}),
], className="t-page")

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
