
def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

from dash import dcc, html, Input, Output, State, callback, register_page, dash_table
import dash
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from datetime import date, timedelta, datetime
import warnings
import sys
import os
import time
from flask import Flask, jsonify
# Use the installed pydataxm package instead of local module
try:
    from pydataxm.pydataxm import ReadDB
    PYDATAXM_AVAILABLE = True
except ImportError:
    PYDATAXM_AVAILABLE = False
    # logger no está disponible aún aquí, se loggea después

# NOTA IMPORTANTE SOBRE UNIDADES DE MEDIDA:
# La métrica 'AporEner' de XM representa aportes de energía por río
# Su unidad de medida es kWh (kilovatio-hora), convertida a GWh para visualización
# Los aportes energéticos representan la energía potencial de los caudales

# Imports locales para componentes uniformes
from interface.components.layout import crear_navbar_horizontal, crear_boton_regresar, crear_filtro_fechas_compacto, registrar_callback_filtro_fechas
from interface.components.kpi_card import crear_kpi, crear_kpi_row
from interface.components.chart_card import crear_chart_card, crear_chart_card_custom, crear_page_header, crear_filter_bar
from core.constants import UIColors as COLORS
from domain.services.geo_service import REGIONES_COORDENADAS, obtener_coordenadas_region
from infrastructure.logging.logger import setup_logger
from core.validators import validate_date_range, validate_string
from core.exceptions import DateRangeError, InvalidParameterError, DataNotFoundError
# from .api_fallback import create_fallback_data, create_api_status_message, save_api_status

warnings.filterwarnings("ignore")

# Configurar logger para este módulo
logger = setup_logger(__name__)

register_page(
    __name__,
    path="/generacion/hidraulica/hidrologia",
    name="Hidrología",
    title="Hidrología - Ministerio de Minas y Energía de Colombia",
    order=6
)

# --- NUEVO: Fecha/hora de última actualización del código ---
LAST_UPDATE = time.strftime('%Y-%m-%d %H:%M:%S')

# Funciones auxiliares para formateo de datos
def format_number(value):
    """Formatear números con separadores de miles usando puntos"""
    if pd.isna(value) or not isinstance(value, (int, float)):
        return value
    
    # Formatear con separador de miles usando puntos (formato colombiano)
    return f"{value:,.2f}".replace(",", ".")

def format_date(date_value):
    """Formatear fechas para mostrar solo la fecha sin hora"""
    if pd.isna(date_value):
        return date_value
    
    if isinstance(date_value, str):
        try:
            # Intentar convertir string a datetime
            dt_value = pd.to_datetime(date_value)
            return dt_value.strftime('%Y-%m-%d')
        except Exception:
            return date_value
    elif hasattr(date_value, 'strftime'):
        return date_value.strftime('%Y-%m-%d')
    else:
        return date_value


# Inicializar API XM de forma perezosa usando el helper
from infrastructure.external.xm_service import get_objetoAPI, obtener_datos_desde_bd, obtener_datos_inteligente
API_STATUS = None

# Verificar si la API está disponible al inicializar el módulo
_temp_api = get_objetoAPI()
if _temp_api is not None:
    logger.info("✅ API XM inicializada correctamente (lazy)")
    API_STATUS = {'status': 'online', 'message': 'API XM funcionando correctamente'}
else:
    API_STATUS = {'status': 'offline', 'message': 'pydataxm no está disponible'}
    logger.warning("⚠️ API XM no disponible (pydataxm no está disponible)")


# ============================================================================
# CACHE DE GEOJSON A NIVEL DE MÓDULO (Solo archivos estáticos)
# ============================================================================
_GEOJSON_CACHE = {
    'colombia_geojson': None,
    'regiones_config': None,
    'departamentos_a_regiones': None,
    'loaded': False
}

def _cargar_geojson_cache():
    """Carga los archivos GeoJSON UNA SOLA VEZ (son archivos estáticos que no cambian)."""
    if _GEOJSON_CACHE['loaded']:
        return _GEOJSON_CACHE
    
    try:
        import json
        
        logger.info("📂 Cargando archivos GeoJSON estáticos en cache...")
        
        # Inicializar con None para detectar fallos reales downstream si es necesario
        # o mantener estructura vacía pero logueando el error
        _GEOJSON_CACHE['colombia_geojson'] = {"type": "FeatureCollection", "features": []}
        _GEOJSON_CACHE['regiones_config'] = {"regiones": {}}

        try:
             # Ruta a assets/ (Restaurados desde git history)
             geojson_path = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'departamentos_colombia.geojson')
             
             if os.path.exists(geojson_path):
                 with open(geojson_path, 'r', encoding='utf-8') as f:
                     _GEOJSON_CACHE['colombia_geojson'] = json.load(f)
                 logger.info(f"✅ Mapa cargado correctamente desde {geojson_path}")
             else:
                 logger.error(f"❌ Archivo GeoJSON no encontrado en: {geojson_path}")
                 
        except Exception as e:
            logger.error(f"❌ Error cargando GeoJSON departamentos: {e}")

        try:
             regiones_path = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'regiones_naturales_colombia.json')
             
             if os.path.exists(regiones_path):
                 with open(regiones_path, 'r', encoding='utf-8') as f:
                     _GEOJSON_CACHE['regiones_config'] = json.load(f)
                 logger.info(f"✅ Configuración regiones cargada desde {regiones_path}")
             else:
                 logger.error(f"❌ Archivo regiones no encontrado en: {regiones_path}")

        except Exception as e:
            logger.error(f"❌ Error cargando config regiones: {e}")
            
        _GEOJSON_CACHE['loaded'] = True
        
        # Crear diccionario inverso: departamento -> región
        departamentos_a_regiones = {}
        for region_key, region_data in _GEOJSON_CACHE['regiones_config']['regiones'].items():
            for depto in region_data['departamentos']:
                departamentos_a_regiones[depto] = {
                    'region': region_data['nombre'],
                    'color': region_data['color'],
                    'border': region_data['border']
                }
        
        _GEOJSON_CACHE['departamentos_a_regiones'] = departamentos_a_regiones
        _GEOJSON_CACHE['loaded'] = True
        
        logger.info(f"✅ GeoJSON cargado en memoria: {len(_GEOJSON_CACHE['regiones_config']['regiones'])} regiones, "
                   f"{len(departamentos_a_regiones)} departamentos")
        
        return _GEOJSON_CACHE
        
    except Exception as e:
        logger.error(f"❌ Error cargando GeoJSON en cache: {e}")
        import traceback
        traceback.print_exc()
        return None

# Cargar cache al importar el módulo (solo una vez)
_cargar_geojson_cache()


# --- VALIDACIÓN DE FECHAS Y MANEJO DE ERRORES ---
def validar_rango_fechas(start_date, end_date):
    """
    Valida que el rango de fechas sea lógicamente válido.
    Permite cualquier rango de fechas - los datos se consultarán desde SQLite (>=2020, rápido)
    o desde API XM (<2020, lento pero funcional).
    """
    from datetime import datetime, date
    
    if not start_date or not end_date:
        return False, "Debe seleccionar fechas de inicio y fin."
    
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') if isinstance(start_date, str) else start_date
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') if isinstance(end_date, str) else end_date
        
        # Validación lógica básica
        if start_dt > end_dt:
            return False, "La fecha de inicio debe ser anterior a la fecha final."
        
        # Mensaje informativo (no bloqueante) si consulta datos antes de 2020
        FECHA_LIMITE_SQLITE = date(2020, 1, 1)
        if isinstance(start_dt, datetime):
            start_date_obj = start_dt.date()
        else:
            start_date_obj = start_dt
        
        if start_date_obj < FECHA_LIMITE_SQLITE:
            # ⚠️ Advertencia informativa, NO bloquea la consulta
            mensaje_info = f"ℹ️ Consultando datos anteriores a 2020 desde API XM (puede demorar 30-90 segundos). Datos desde 2020 en adelante se cargarán rápidamente desde base de datos local."
            return True, mensaje_info
        
        return True, "Rango de fechas válido"
        
    except Exception as e:
        return False, f"Error validando fechas: {str(e)}"

def manejar_error_api(error, operacion="consulta"):
    """
    Maneja errores específicos de la API de XM y proporciona mensajes útiles.
    """
    error_str = str(error).lower()
    
    if "400" in error_str and "json" in error_str and "text/plain" in error_str:
        message = f"🔄 La API de XM retornó un error para esta {operacion}. Esto suele ocurrir cuando:" + "\n"
        message += "• Las fechas seleccionadas están fuera del rango disponible\n"
        message += "• Los datos para el período solicitado no están disponibles\n"
        message += "• Hay mantenimiento en los servidores de XM\n"
        message += "Recomendaciones:\n"
        message += "• Intente con fechas más recientes (últimos 6 meses)\n"
        message += "• Reduzca el rango de fechas\n"
        message += "• Verifique el estado de la API de XM en www.xm.com.co"
        return message
    
    elif "timeout" in error_str or "connection" in error_str:
        return f"🌐 Error de conexión con la API de XM. Verifique su conexión a internet y vuelva a intentar."
    
    elif "unauthorized" in error_str or "403" in error_str:
        return f"🔐 Error de autorización con la API de XM. Contacte al administrador del sistema."
    
    else:
        return f"Error inesperado en la {operacion}: {str(error)[:200]}..."

from domain.services.hydrology_service import HydrologyService

# Instancia global del servicio
_hydrology_service = HydrologyService()

def get_reservas_hidricas(fecha):
    return _hydrology_service.get_reservas_hidricas(fecha)

def get_aportes_hidricos(fecha):
    return _hydrology_service.get_aportes_hidricos(fecha)

def calcular_volumen_util_unificado(fecha, region=None, embalse=None):
    return _hydrology_service.calcular_volumen_util_unificado(fecha, region, embalse)


    """
    Calcula las reservas hídricas filtradas por región específica.
    Usa la función unificada para garantizar consistencia con las tablas.
    
    Args:
        fecha: Fecha en formato 'YYYY-MM-DD'
        region: Nombre de la región hidrológica
        
    Returns:
ndef get_reservas_hidricas_por_region(fecha, region):
        tuple: (porcentaje, valor_GWh) o (None, None) si hay error
    """
    
    resultado = calcular_volumen_util_unificado(fecha, region=region)
    if resultado:
        return resultado['porcentaje'], resultado['volumen_gwh']
    else:
        return None, None


def get_aportes_hidricos_por_region(fecha, region):
    """
    Calcula los aportes hídricos filtrados por región específica.
    Replica el método de XM: promedio acumulado mensual de aportes energía por región
    
    Args:
        fecha: Fecha en formato 'YYYY-MM-DD'
        region: Nombre de la región hidrológica
        
    Returns:
        tuple: (porcentaje, valor_GWh) o (None, None) si hay error
    """
    
    try:
        # Calcular el rango desde el primer día del mes hasta la fecha final
        fecha_final = pd.to_datetime(fecha)
        fecha_inicio = fecha_final.replace(day=1)
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
        fecha_final_str = fecha_final.strftime('%Y-%m-%d')
        
        # Obtener aportes energía por río desde SQLite
        aportes_data, warning = obtener_datos_inteligente('AporEner', 'Rio', fecha_inicio_str, fecha_final_str)
        
        if aportes_data is not None and not aportes_data.empty:
            # Asignar región a cada río
            rio_region = ensure_rio_region_loaded()
            aportes_data['Region'] = aportes_data['Name'].map(rio_region)
            
            # Filtrar por región específica (normalizar región)
            # ✅ FIX ERROR #3: UPPER en lugar de title
            region_normalized = region.strip().upper()
            aportes_region = aportes_data[aportes_data['Region'] == region_normalized]
            
            if not aportes_region.empty:
                # CORRECCIÓN: Suma total del período (aportes acumulativos)
                aportes_total_region = aportes_region['Value'].sum()
                
                # Obtener media histórica para la región
                media_historica_data, warning = obtener_datos_inteligente('AporEnerMediHist', 'Rio', fecha_inicio_str, fecha_final_str)
                
                if media_historica_data is not None and not media_historica_data.empty:
                    media_historica_data['Region'] = media_historica_data['Name'].map(rio_region)
                    media_historica_region = media_historica_data[media_historica_data['Region'] == region_normalized]
                    
                    if not media_historica_region.empty:
                        # CORRECCIÓN: Suma total del período histórico
                        media_total_region = media_historica_region['Value'].sum()
                        
                        
                        if media_total_region > 0:
                            # Fórmula exacta de XM por región
                            porcentaje = round((aportes_total_region / media_total_region) * 100, 2)
                            return porcentaje, aportes_total_region
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error obteniendo aportes hídricos por región: {e}", exc_info=True)
        return None, None


def get_aportes_hidricos_por_rio(fecha, rio):
    """
    Calcula los aportes hídricos de un río específico.
    
    Args:
        fecha: Fecha en formato 'YYYY-MM-DD'
        rio: Nombre del río
        
    Returns:
        tuple: (porcentaje, valor_m3s) o (None, None) si hay error
    """
    
    try:
        # Obtener aportes del río específico desde SQLite
        aportes_data, warning = obtener_datos_inteligente('AporEner', 'Rio', fecha, fecha)
        
        if aportes_data is not None and not aportes_data.empty:
            # Buscar el río específico
            rio_data = aportes_data[aportes_data['Name'] == rio]
            
            if not rio_data.empty:
                aportes_rio = rio_data['Value'].iloc[0]
                
                # Para el porcentaje, comparar con la media de todos los ríos
                media_total_rios = aportes_data['Value'].mean()
                
                if media_total_rios > 0:
                    porcentaje = round((aportes_rio / media_total_rios) * 100, 2)
                    return porcentaje, aportes_rio
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error obteniendo aportes hídricos por río: {e}", exc_info=True)
        return None, None


# Obtener la relación río-región directamente desde la API XM
def get_rio_region_dict():
    try:
        # Usar fecha actual para obtener listado más reciente desde SQLite
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        df, warning = obtener_datos_inteligente('ListadoRios', 'Sistema', yesterday, today)
        if 'Values_Name' in df.columns and 'Values_HydroRegion' in df.columns:
            # ✅ USAR FUNCIONES DE NORMALIZACIÓN UNIFICADAS
            df['Values_Name'] = normalizar_codigo(df['Values_Name'])
            df['Values_HydroRegion'] = normalizar_region(df['Values_HydroRegion'])
            return dict(sorted(zip(df['Values_Name'], df['Values_HydroRegion'])))
        else:
            return {}
    except Exception as e:
        logger.error(f"Error obteniendo relación río-región desde la API: {e}", exc_info=True)
        return {}

# Inicializar como None, se cargará bajo demanda
RIO_REGION = None

# ============================================================================
# FUNCIÓN DE NORMALIZACIÓN UNIFICADA
# ============================================================================
def normalizar_codigo(texto):
    """Normaliza códigos/nombres de forma consistente en TODO el sistema.
    
    Args:
        texto: String a normalizar o pandas Series
        
    Returns:
        String normalizado en UPPERCASE sin espacios extra
    """
    if texto is None:
        return None
    if isinstance(texto, str):
        return texto.strip().upper()
    # Si es pandas Series
    return texto.str.strip().str.upper()

def normalizar_region(texto):
    """Normaliza nombres de regiones de forma consistente.
    
    Args:
        texto: String a normalizar o pandas Series
        
    Returns:
        String normalizado en UPPER CASE (para coincidir con REGIONES_COORDENADAS)
    """
    if texto is None:
        return None
    if isinstance(texto, str):
        return texto.strip().upper()
    # Si es pandas Series
    return texto.str.strip().str.upper()
# ============================================================================

def ensure_rio_region_loaded():
    """Carga RIO_REGION bajo demanda si aún no se ha cargado."""
    global RIO_REGION
    if RIO_REGION is None:
        RIO_REGION = get_rio_region_dict()
    return RIO_REGION

def get_region_options():
    """
    Obtiene las regiones que tienen ríos con datos de aportes energéticos activos.
    Filtra regiones que no tienen datos para evitar confusión al usuario.
    """
    rio_region = ensure_rio_region_loaded()
    try:
        # Obtener ríos con datos de energía recientes desde SQLite (30 días para cobertura completa)
        df, warning = obtener_datos_inteligente('AporEner', 'Rio', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'), date.today().strftime('%Y-%m-%d'))
        if 'Name' in df.columns:
            rios_con_datos = set(df['Name'].unique())
            # Filtrar solo regiones que tienen ríos con datos
            regiones_con_datos = set()
            for rio, region in rio_region.items():
                if rio in rios_con_datos:
                    regiones_con_datos.add(region)
            return sorted(regiones_con_datos)
        else:
            return sorted(set(rio_region.values()))
    except Exception as e:
        logger.error(f"Error filtrando regiones con datos: {e}", exc_info=True)
        return sorted(set(rio_region.values()))






# --- NUEVO: Función para obtener todos los ríos únicos desde la API ---
def get_all_rios_api():
    try:
        df, warning = obtener_datos_inteligente('AporEner', 'Rio', '2000-01-01', date.today().strftime('%Y-%m-%d'))
        if df is not None and 'Name' in df.columns:
            rios = sorted(df['Name'].dropna().unique())
            return rios
        else:
            return []
    except Exception:
        return []

def get_rio_options(region=None):
    try:
        df, warning = obtener_datos_inteligente('AporEner', 'Rio', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'), date.today().strftime('%Y-%m-%d'))
        if df is not None and 'Name' in df.columns:
            rios = sorted(df['Name'].dropna().unique())
            if region:
                rio_region = ensure_rio_region_loaded()
                rios = [r for r in rios if rio_region.get(r) == region]
            return rios
        else:
            return []
    except Exception as e:
        logger.error(f"Error obteniendo opciones de Río: {e}", exc_info=True)
        return []

regiones = []  # Se cargarán dinámicamente
rios = []      # Se cargarán dinámicamente

def crear_estilos_condicionales_para_tabla_estatica(start_date=None, end_date=None):
    """
    Crea estilos condicionales para la tabla estática basados en riesgo
    """
    try:
        # Obtener datos frescos para calcular estilos
        df_fresh = get_embalses_capacidad(None, start_date, end_date)
        if df_fresh.empty:
            return [
                {
                    "if": {"filter_query": "{Embalse} = \"TOTAL\""}, 
                    "backgroundColor": "#007bff",
                    "color": "white",
                    "fontWeight": "bold"
                }
            ]
        
        # Agregar riesgo y generar estilos
        df_con_riesgo = agregar_columna_riesgo_a_tabla(df_fresh)
        estilos = generar_estilos_condicionales_riesgo(df_con_riesgo)
        return estilos
        
    except Exception as e:
        logger.error(f"Error generando estilos condicionales: {e}", exc_info=True)
        return [
            {
                "if": {"filter_query": "{Embalse} = \"TOTAL\""}, 
                "backgroundColor": "#007bff",
                "color": "white",
                "fontWeight": "bold"
            }
        ]


# ============================================================================
# FUNCIONES PARA MAPA DE EMBALSES POR REGIÓN
# ============================================================================

def calcular_semaforo_embalse(participacion, volumen_pct):
    """
    Calcula el nivel de riesgo según la lógica del semáforo hidrológico de XM:
    
    Factor 1: Importancia Estratégica (participación > 10%)
    Factor 2: Disponibilidad Hídrica (% volumen útil)
    
    RIESGO ALTO (🔴): Embalses estratégicos (>10%) con volumen crítico (<30%)
    RIESGO MEDIO (🟡): Embalses estratégicos con volumen bajo (30-70%) o embalses pequeños con volumen crítico
    RIESGO BAJO (🟢): Embalses con volumen adecuado (≥70%) independientemente de su tamaño
    
    Args:
        participacion: % de participación en el sistema (0-100)
        volumen_pct: % de volumen útil disponible (0-100)
    
    Returns:
        tuple: (nivel_riesgo, color, mensaje)
    """
    es_estrategico = participacion >= 10
    
    if volumen_pct >= 70:
        return 'BAJO', '#28a745', '✓'
    elif volumen_pct >= 30:
        if es_estrategico:
            return 'MEDIO', '#ffc107', '!'
        else:
            return 'BAJO', '#28a745', '✓'
    else:  # volumen_pct < 30
        if es_estrategico:
            return 'ALTO', '#dc3545', '⚠'
        else:
            return 'MEDIO', '#ffc107', '!'

def obtener_datos_embalses_por_region():
    """
    Obtiene los datos de embalses agrupados por región hidrológica.
    Valida completitud: n_vol/n_cap >= 80% para evitar datos parciales.
    
    Returns:
        dict: {region: {embalses: [...], riesgo_max: str, color: str, lat: float, lon: float}}
    """
    try:
        # Obtener fecha actual y buscar últimos datos disponibles
        fecha_hoy = date.today()
        
        # Buscar la fecha más reciente con datos COMPLETOS en últimos 7 días
        fecha_valida = None
        df_vol = None
        df_cap = None
        df_listado = None
        
        for dias_atras in range(7):
            fecha_busqueda = fecha_hoy - timedelta(days=dias_atras)
            
            df_vol_tmp, fecha_vol = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_busqueda, dias_busqueda=1)
            df_cap_tmp, fecha_cap = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_busqueda, dias_busqueda=1)
            
            if df_vol_tmp is None or df_vol_tmp.empty or df_cap_tmp is None or df_cap_tmp.empty:
                continue
            if fecha_vol != fecha_cap:
                continue
            
            # Validar completitud: n_vol / n_cap >= 0.80
            # Contar embalses distintos en cada métrica
            col_embalse_vol = next((c for c in ['Embalse', 'recurso', 'Values_code', 'Values_Code'] if c in df_vol_tmp.columns), None)
            col_embalse_cap = next((c for c in ['Embalse', 'recurso', 'Values_code', 'Values_Code'] if c in df_cap_tmp.columns), None)
            
            if col_embalse_vol and col_embalse_cap:
                n_vol = df_vol_tmp[col_embalse_vol].nunique()
                n_cap = df_cap_tmp[col_embalse_cap].nunique()
                
                if n_cap > 0 and n_vol / n_cap < 0.80:
                    logger.warning(f"Embalses incompletos {fecha_busqueda}: n_vol={n_vol}, n_cap={n_cap}, ratio={n_vol/n_cap:.2f}")
                    continue
            
            # Datos completos encontrados
            df_vol = df_vol_tmp
            df_cap = df_cap_tmp
            fecha_valida = fecha_vol
            break
        
        if fecha_valida is None or df_vol is None or df_cap is None:
            logger.error("No se encontraron datos completos de embalses en últimos 7 días")
            return None
        
        # Obtener listado de embalses
        df_listado, fecha_listado = obtener_datos_desde_bd('ListadoEmbalses', 'Sistema', fecha_hoy)
        
        if df_listado is None:
            logger.error("No se pudo obtener ListadoEmbalses")
            return None
        
        fecha_str = fecha_valida.strftime('%Y-%m-%d')
        logger.info(f"Datos completos de embalses obtenidos para {fecha_str}")
        
        # Detectar nombre de columnas (mismo código que en las tablas)
        col_value_vol = None
        col_value_cap = None
        col_name_vol = None
        
        # Buscar columna de valores
        for col in ['Values_code', 'Value', 'Values_Code']:
            if col in df_vol.columns:
                col_value_vol = col
                break
        
        for col in ['Values_code', 'Value', 'Values_Code']:
            if col in df_cap.columns:
                col_value_cap = col
                break
        
        # Buscar columna de nombre/código
        for col in ['Values_code', 'Values_Code', 'Name']:
            if col in df_vol.columns:
                col_name_vol = col
                break
        
        if not col_value_vol or not col_value_cap or not col_name_vol:
            logger.error(f"Columnas no encontradas. df_vol: {df_vol.columns.tolist()}")
            return None
        
        logger.debug(f"Columnas detectadas - vol_value: {col_value_vol}, cap_value: {col_value_cap}, name: {col_name_vol}")
        
        # Crear diccionario de región por embalse
        embalse_region = {}
        col_name_listado = None
        for col in ['Values_Code', 'Values_code', 'Name']:
            if col in df_listado.columns:
                col_name_listado = col
                break
        
        if col_name_listado and 'Values_HydroRegion' in df_listado.columns:
            for _, row in df_listado.iterrows():
                codigo = row[col_name_listado]
                region = row['Values_HydroRegion']
                embalse_region[codigo] = region
        else:
            logger.error(f"Columnas del listado: {df_listado.columns.tolist()}")
            return None
        
        # Hacer copias antes de renombrar para evitar modificar los originales
        df_vol_copy = df_vol.copy()
        df_cap_copy = df_cap.copy()
        
        # Renombrar columnas en las copias
        df_vol_copy = df_vol_copy.rename(columns={col_value_vol: 'volumen_wh', col_name_vol: 'codigo'})
        df_cap_copy = df_cap_copy.rename(columns={col_value_cap: 'capacidad_wh'})
        
        # Buscar columna de nombre/código en df_cap
        col_name_cap = None
        for col in ['Values_code', 'Values_Code', 'Name']:
            if col in df_cap.columns:
                col_name_cap = col
                break
        
        df_cap_copy = df_cap_copy.rename(columns={col_name_cap: 'codigo'})
        
        logger.debug(f"Columnas df_vol_copy: {df_vol_copy.columns.tolist()}")
        logger.debug(f"Columnas df_cap_copy: {df_cap_copy.columns.tolist()}")
        
        # Verificar que las columnas existen
        if 'volumen_wh' not in df_vol_copy.columns or 'codigo' not in df_vol_copy.columns:
            logger.error("Error: columnas faltantes en df_vol_copy")
            return None
        
        if 'capacidad_wh' not in df_cap_copy.columns or 'codigo' not in df_cap_copy.columns:
            logger.error("Error: columnas faltantes en df_cap_copy")
            return None
        
        df_merged = pd.merge(
            df_vol_copy[['codigo', 'volumen_wh']],
            df_cap_copy[['codigo', 'capacidad_wh']],
            on='codigo',
            how='inner'
        )
        
        # Calcular porcentajes
        df_merged['volumen_pct'] = (df_merged['volumen_wh'] / df_merged['capacidad_wh']) * 100
        capacidad_total = df_merged['capacidad_wh'].sum()
        df_merged['participacion'] = (df_merged['capacidad_wh'] / capacidad_total) * 100
        
        # Agregar región
        df_merged['region'] = df_merged['codigo'].map(embalse_region)
        
        # Agrupar por región
        regiones_data = {}
        for region in df_merged['region'].unique():
            if pd.isna(region) or region not in REGIONES_COORDENADAS:
                continue
            
            df_region = df_merged[df_merged['region'] == region]
            
            # Crear lista de embalses de la región
            embalses_lista = []
            riesgo_max = 'BAJO'
            orden_riesgo = {'ALTO': 3, 'MEDIO': 2, 'BAJO': 1}
            
            for _, row in df_region.iterrows():
                riesgo, color, icono = calcular_semaforo_embalse(row['participacion'], row['volumen_pct'])
                
                embalses_lista.append({
                    'codigo': row['codigo'],
                    'volumen_pct': row['volumen_pct'],
                    'volumen_gwh': row['volumen_wh'] / 1e9,
                    'capacidad_gwh': row['capacidad_wh'] / 1e9,
                    'participacion': row['participacion'],
                    'riesgo': riesgo,
                    'color': color,
                    'icono': icono
                })
                
                # Actualizar riesgo máximo de la región
                if orden_riesgo[riesgo] > orden_riesgo[riesgo_max]:
                    riesgo_max = riesgo
            
            # Determinar color de la región según el riesgo máximo
            color_region = {'ALTO': '#dc3545', 'MEDIO': '#ffc107', 'BAJO': '#28a745'}[riesgo_max]
            
            coords = REGIONES_COORDENADAS[region]
            
            regiones_data[region] = {
                'embalses': embalses_lista,
                'riesgo_max': riesgo_max,
                'color': color_region,
                'lat': coords['lat'],
                'lon': coords['lon'],
                'nombre': coords['nombre'],
                'total_embalses': len(embalses_lista)
            }
        
        return regiones_data
    
    except Exception as e:
        logger.error(f"Error obteniendo datos para mapa por región: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return None

def crear_mapa_embalses_por_region():
    """
    Crea el mapa interactivo de Colombia con puntos por región hidrológica
    """
    import plotly.graph_objects as go
    
    regiones_data = obtener_datos_embalses_por_region()
    
    if regiones_data is None or len(regiones_data) == 0:
        return dbc.Alert([
            html.H5("⚠️ No hay datos disponibles", className="alert-heading"),
            html.P("No se pudieron cargar los datos de los embalses. Intente nuevamente más tarde.")
        ], color="warning")
    
    # Crear figura del mapa
    fig = go.Figure()
    
    # Agregar puntos por región
    for region, data in regiones_data.items():
        # Crear texto del tooltip con lista de embalses
        embalses_texto = "<br>".join([
            f"• {emb['codigo']}: {emb['volumen_pct']:.1f}% {emb['icono']}"
            for emb in sorted(data['embalses'], key=lambda x: x['volumen_pct'])[:10]  # Mostrar máximo 10
        ])
        
        if data['total_embalses'] > 10:
            embalses_texto += f"<br>... y {data['total_embalses'] - 10} más"
        
        hover_text = (
            f"<b>{data['nombre']}</b><br>" +
            f"Total embalses: {data['total_embalses']}<br>" +
            f"Riesgo máximo: <b>{data['riesgo_max']}</b><br><br>" +
            f"<b>Embalses:</b><br>{embalses_texto}"
        )
        
        # Tamaño según cantidad de embalses
        tamaño = min(15 + data['total_embalses'] * 3, 40)
        
        fig.add_trace(go.Scattergeo(
            lon=[data['lon']],
            lat=[data['lat']],
            text=[data['nombre']],
            mode='markers+text',
            marker=dict(
                size=tamaño,
                color=data['color'],
                line=dict(width=3, color='white'),
                symbol='circle'
            ),
            textposition='top center',
            textfont=dict(size=10, color='#2c3e50', family='Arial Black'),
            name=f"{data['nombre']} ({data['riesgo_max']})",
            hovertext=hover_text,
            hoverinfo='text',
            showlegend=True
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
            'text': '🗺️ Mapa de Embalses por Región Hidrológica',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18, 'color': COLORS['text_primary'], 'family': 'Arial Black'}
        },
        height=600,
        margin=dict(l=0, r=0, t=60, b=0),
        legend=dict(
            title=dict(text='Regiones', font=dict(size=12, family='Arial Black')),
            orientation='v',
            yanchor='top',
            y=0.98,
            xanchor='left',
            x=0.01,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='gray',
            borderwidth=1,
            font=dict(size=10)
        ),
        hoverlabel=dict(
            bgcolor='white',
            font_size=11,
            font_family='Arial'
        )
    )
    
    return dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False})

def crear_tabla_embalses_por_region():
    """
    Crea la tabla detallada de embalses agrupada por región
    """
    regiones_data = obtener_datos_embalses_por_region()
    
    if regiones_data is None or len(regiones_data) == 0:
        return dbc.Alert("No hay datos disponibles", color="warning")
    
    # Ordenar regiones por riesgo máximo
    orden_riesgo = {'ALTO': 0, 'MEDIO': 1, 'BAJO': 2}
    regiones_ordenadas = sorted(
        regiones_data.items(),
        key=lambda x: (orden_riesgo[x[1]['riesgo_max']], x[0])
    )
    
    # Crear acordeón con una sección por región
    acordeon_items = []
    
    for region, data in regiones_ordenadas:
        # Ordenar embalses por volumen (menor a mayor)
        embalses_ordenados = sorted(data['embalses'], key=lambda x: x['volumen_pct'])
        
        # Crear filas de tabla para esta región
        filas_region = []
        for emb in embalses_ordenados:
            filas_region.append(
                html.Tr([
                    html.Td(html.Span(emb['icono'], style={'fontSize': '1.2rem'}), className="text-center"),
                    html.Td(emb['codigo'], style={'fontWeight': '600'}),
                    html.Td(f"{emb['volumen_pct']:.1f}%", 
                           style={'color': emb['color'], 'fontWeight': '700'}),
                    html.Td(f"{emb['volumen_gwh']:.0f} GWh"),
                    html.Td(f"{emb['capacidad_gwh']:.0f} GWh"),
                    html.Td(f"{emb['participacion']:.1f}%"),
                    html.Td(emb['riesgo'], 
                           style={
                               'color': emb['color'],
                               'fontWeight': 'bold',
                               'backgroundColor': emb['color'] + '20',
                               'padding': '5px 10px',
                               'borderRadius': '4px'
                           })
                ])
            )
        
        tabla_region = dbc.Table([
            html.Thead([
                html.Tr([
                    html.Th("", className="text-center", style={'width': '50px'}),
                    html.Th("Embalse"),
                    html.Th("Volumen %"),
                    html.Th("Volumen"),
                    html.Th("Capacidad"),
                    html.Th("Participación %"),
                    html.Th("Riesgo")
                ], style={'backgroundColor': data['color'], 'color': 'white', 'fontSize': '0.9rem'})
            ]),
            html.Tbody(filas_region)
        ], bordered=True, hover=True, responsive=True, striped=True, size='sm')
        
        # Título del acordeón con color según riesgo
        titulo_acordeon = html.Div([
            html.Span(f"📍 {data['nombre']}", style={'fontWeight': '600', 'fontSize': '1.1rem'}),
            html.Span(
                f" ({data['total_embalses']} embalses - Riesgo {data['riesgo_max']})",
                style={'color': data['color'], 'fontWeight': 'bold', 'marginLeft': '10px'}
            )
        ])
        
        acordeon_items.append(
            dbc.AccordionItem(
                tabla_region,
                title=titulo_acordeon,
                item_id=f"region-{region}"
            )
        )
    
    return dbc.Accordion(acordeon_items, start_collapsed=True, always_open=True)

# ============================================================================
# NUEVAS TABLAS JERÁRQUICAS SIMPLIFICADAS (usando dbc.Table directamente)
# ============================================================================



def build_embalses_hierarchical_view(regiones_totales, df_completo_embalses, expanded_regions):
    """
    Construye vista jerárquica de la tabla pequeña de embalses con expansión/contracción.
    Similar a build_hierarchical_table_view() pero para la tabla de 4 columnas.
    """
    try:
        if regiones_totales is None or regiones_totales.empty or df_completo_embalses.empty:
            return dash_table.DataTable(
                data=[],
                columns=[
                    {"name": "Embalse", "id": "embalse"},
                    {"name": "Part.", "id": "participacion"},
                    {"name": "Vol.", "id": "volumen"},
                    {"name": "⚠️", "id": "riesgo"}
                ]
            )
        
        table_data = []
        style_data_conditional = []
        
        # Ordenar regiones por participación descendente
        regiones_sorted = regiones_totales.sort_values('Participación (%)', ascending=False)
        
        for _, row_region in regiones_sorted.iterrows():
            region_name = row_region['Región']
            participacion_region = row_region['Participación (%)']
            volumen_region = row_region['Volumen Útil (%)']
            
            is_expanded = region_name in expanded_regions
            button_icon = "⊟" if is_expanded else "⊞"
            
            # Clasificar riesgo de la región (usar el peor caso de sus embalses)
            embalses_region = df_completo_embalses[df_completo_embalses['Región'] == region_name]
            riesgos = []
            for _, emb in embalses_region.iterrows():
                riesgo = clasificar_riesgo_embalse(
                    emb.get('Participación (%)', 0),
                    emb.get('Volumen Útil (%)', 0)
                )
                riesgos.append(riesgo)
            
            # Determinar el peor riesgo de la región
            if 'high' in riesgos:
                riesgo_region = '🔴'
            elif 'medium' in riesgos:
                riesgo_region = '🟡'
            else:
                riesgo_region = '🟢'
            
            # Fila de región
            row_index = len(table_data)
            table_data.append({
                "embalse": f"{button_icon} {region_name}",
                "participacion": f"{participacion_region:.2f}%",
                "volumen": f"{volumen_region:.1f}%",
                "riesgo": riesgo_region
            })
            
            # Estilo para fila de región
            style_data_conditional.append({
                'if': {'row_index': row_index},
                'backgroundColor': '#e3f2fd',
                'fontWeight': 'bold',
                'cursor': 'pointer',
                'border': '2px solid #2196f3'
            })
            
            # Si está expandida, agregar embalses
            if is_expanded:
                embalses_sorted = embalses_region.sort_values('Participación (%)', ascending=False)
                
                for _, emb in embalses_sorted.iterrows():
                    embalse_name = emb['Embalse']
                    participacion_val = emb.get('Participación (%)', 0)
                    volumen_val = emb.get('Volumen Útil (%)', 0)
                    
                    # Clasificar riesgo
                    riesgo = clasificar_riesgo_embalse(participacion_val, volumen_val)
                    if riesgo == 'high':
                        riesgo_icon = '🔴'
                    elif riesgo == 'medium':
                        riesgo_icon = '🟡'
                    else:
                        riesgo_icon = '🟢'
                    
                    # Agregar fila de embalse
                    emb_row_index = len(table_data)
                    table_data.append({
                        "embalse": f"    └─ {embalse_name}",
                        "participacion": f"{participacion_val:.2f}%",
                        "volumen": f"{volumen_val:.1f}%" if pd.notna(volumen_val) else "N/D",
                        "riesgo": riesgo_icon
                    })
                    
                    # Estilo condicional por riesgo
                    if riesgo == 'high':
                        bg_color = '#ffe6e6'
                    elif riesgo == 'medium':
                        bg_color = '#fff9e6'
                    else:
                        bg_color = '#e6ffe6'
                    
                    style_data_conditional.append({
                        'if': {'row_index': emb_row_index},
                        'backgroundColor': bg_color
                    })
        
        # Agregar fila TOTAL
        total_participacion = regiones_totales['Participación (%)'].sum()
        
        # Calcular volumen total ponderado
        total_volumen_gwh = regiones_totales['Volumen Util (GWh)'].sum()
        total_capacidad_gwh = regiones_totales['Total (GWh)'].sum()
        promedio_volumen_general = (total_volumen_gwh / total_capacidad_gwh) * 100 if total_capacidad_gwh > 0 else 0
        
        total_row_index = len(table_data)
        table_data.append({
            "embalse": "TOTAL",
            "participacion": "100.00%",
            "volumen": f"{promedio_volumen_general:.1f}%",
            "riesgo": "⚡"
        })
        
        style_data_conditional.append({
            'if': {'row_index': total_row_index},
            'backgroundColor': '#e3f2fd',
            'fontWeight': 'bold'
        })
        
        # Crear DataTable
        return dash_table.DataTable(
            id="tabla-embalses-jerarquica",
            data=table_data,
            columns=[
                {"name": "Embalse", "id": "embalse"},
                {"name": "Part.", "id": "participacion"},
                {"name": "Vol.", "id": "volumen"},
                {"name": "⚠️", "id": "riesgo"}
            ],
            style_cell={'textAlign': 'left', 'padding': '4px', 'fontSize': '0.7rem'},
            style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold', 'fontSize': '0.7rem', 'padding': '4px'},
            style_data_conditional=style_data_conditional,
            page_action="none",
            style_table={'maxHeight': '480px', 'overflowY': 'auto'}
        )
        
    except Exception as e:
        logger.error(f"❌ Error en build_embalses_hierarchical_view: {e}", exc_info=True)
        return dash_table.DataTable(data=[], columns=[
            {"name": "Embalse", "id": "embalse"},
            {"name": "Part.", "id": "participacion"},
            {"name": "Vol.", "id": "volumen"},
            {"name": "⚠️", "id": "riesgo"}
        ])


def crear_tablas_jerarquicas_directas(regiones_totales):
    """
    Crea las tablas jerárquicas de Participación y Volumen Útil usando dbc.Table
    (mismo patrón que la tabla que SÍ funciona)
    
    Args:
        regiones_totales: DataFrame con datos de regiones (ya calculado)
    """
    try:
        if regiones_totales is None or regiones_totales.empty:
            return (
                dbc.Alert("No hay datos de regiones disponibles", color="warning"),
                dbc.Alert("No hay datos de regiones disponibles", color="warning")
            )
        
        # TABLA 1: Participación Porcentual
        filas_participacion = []
        
        # Ordenar regiones por participación descendente
        regiones_sorted = regiones_totales.sort_values('Participación (%)', ascending=False)
        
        for _, row_region in regiones_sorted.iterrows():
            region_name = row_region['Región']
            participacion_region = row_region['Participación (%)']
            
            # Fila de región (colapsada inicialmente)
            filas_participacion.append(
                html.Tr([
                    html.Td(
                        html.Span(f"⊞ {region_name}", style={'fontWeight': 'bold', 'cursor': 'pointer'}),
                        colSpan=2
                    ),
                    html.Td(f"{participacion_region:.2f}%", style={'fontWeight': 'bold', 'textAlign': 'right'})
                ], style={'backgroundColor': '#e3f2fd'})
            )
        
        # Fila TOTAL
        filas_participacion.append(
            html.Tr([
                html.Td("TOTAL SISTEMA", colSpan=2, style={'fontWeight': 'bold'}),
                html.Td("100.0%", style={'fontWeight': 'bold', 'textAlign': 'right'})
            ], style={'backgroundColor': '#007bff', 'color': 'white'})
        )
        
        tabla_participacion = dbc.Table([
            html.Thead([
                html.Tr([
                    html.Th("Región / Embalse", colSpan=2),
                    html.Th("Participación (%)", style={'textAlign': 'right'})
                ], style={'backgroundColor': '#667eea', 'color': 'white'})
            ]),
            html.Tbody(filas_participacion)
        ], bordered=True, hover=True, responsive=True, striped=True, size='sm', className="table-modern")
        
        # TABLA 2: Volumen Útil
        filas_volumen = []
        
        # Ordenar regiones por volumen útil descendente
        regiones_sorted_vol = regiones_totales.sort_values('Volumen Útil (%)', ascending=False)
        
        for _, row_region in regiones_sorted_vol.iterrows():
            region_name = row_region['Región']
            volumen_region = row_region['Volumen Útil (%)']
            
            # Fila de región
            filas_volumen.append(
                html.Tr([
                    html.Td(
                        html.Span(f"⊞ {region_name}", style={'fontWeight': 'bold', 'cursor': 'pointer'}),
                        colSpan=2
                    ),
                    html.Td(f"{volumen_region:.1f}%", style={'fontWeight': 'bold', 'textAlign': 'right'})
                ], style={'backgroundColor': '#e8f5e8'})
            )
        
        # Calcular volumen útil total
        total_volumen_gwh = regiones_totales['Volumen Util (GWh)'].sum()
        total_capacidad_gwh = regiones_totales['Total (GWh)'].sum()
        promedio_volumen_general = (total_volumen_gwh / total_capacidad_gwh) * 100 if total_capacidad_gwh > 0 else 0
        
        # Fila TOTAL
        filas_volumen.append(
            html.Tr([
                html.Td("TOTAL SISTEMA", colSpan=2, style={'fontWeight': 'bold'}),
                html.Td(f"{promedio_volumen_general:.1f}%", style={'fontWeight': 'bold', 'textAlign': 'right'})
            ], style={'backgroundColor': '#28a745', 'color': 'white'})
        )
        
        tabla_volumen = dbc.Table([
            html.Thead([
                html.Tr([
                    html.Th("Región / Embalse", colSpan=2),
                    html.Th("Volumen Útil (%)", style={'textAlign': 'right'})
                ], style={'backgroundColor': '#28a745', 'color': 'white'})
            ]),
            html.Tbody(filas_volumen)
        ], bordered=True, hover=True, responsive=True, striped=True, size='sm', className="table-modern")
        
        logger.info(f"✅ Tablas jerárquicas creadas exitosamente con {len(regiones_totales)} regiones")
        return tabla_participacion, tabla_volumen
        
    except Exception as e:
        logger.error(f"❌ Error creando tablas jerárquicas directas: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return (
            dbc.Alert(f"Error: {str(e)}", color="danger"),
            dbc.Alert(f"Error: {str(e)}", color="danger")
        )

# ============================================================================


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

layout = html.Div([
    html.Div(className="t-page", children=[
        crear_page_header(
            "Hidrología",
            "fas fa-water",
            "Inicio / Generación / Hidrología"
        ),
        # Panel de controles en tabs
        dbc.Tabs([
            dbc.Tab(label="⚡ Aportes de Energía", tab_id="tab-consulta"),
            dbc.Tab(label="📅 Comparación Anual", tab_id="tab-comparacion-anual"),
        ], id="hidro-tabs", active_tab="tab-consulta", className="mb-4"),
        # Contenido dinámico
        html.Div(id="hidrologia-tab-content")
    ])
])

# Modal global para tablas de datos
modal_rio_table = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle(id="modal-title-dynamic", children="Detalle de datos hidrológicos"), close_button=True),
    dbc.ModalBody([
        html.Div(id="modal-description", className="mb-3", style={"fontSize": "0.9rem", "color": "#666"}),
        html.Div(id="modal-table-content")
    ]),
], id="modal-rio-table", is_open=False, size="xl", backdrop=True, centered=True, style={"zIndex": 2000})

# Modal de información de la ficha KPI
modal_info_ficha_kpi = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Indicador de Aportes Energéticos"), close_button=True),
    dbc.ModalBody([
        html.H6("¿Qué mide?", className="fw-bold mb-2"),
        html.P("Compara los aportes energéticos actuales del año 2025 con el promedio histórico de los últimos 5 años."),
        
        html.H6("Cálculo:", className="fw-bold mb-2 mt-3"),
        html.Ul([
            html.Li("Período: Últimos 365 días"),
            html.Li("Datos reales: Suma de aportes energéticos (GWh) de todos los ríos del SIN"),
            html.Li("Media histórica: Promedio de los últimos 5 años (2020-2024) para el mismo período"),
            html.Li([
                "Fórmula: ",
                html.Code("[(Aportes Reales / Media Histórica) × 100] - 100")
            ])
        ]),
        
        html.H6("Interpretación:", className="fw-bold mb-2 mt-3"),
        html.Ul([
            html.Li([
                html.I(className="fas fa-arrow-up", style={'color': '#28a745'}),
                " Positivo (+): Más aportes que el promedio histórico (favorable)"
            ]),
            html.Li([
                html.I(className="fas fa-arrow-down", style={'color': '#dc3545'}),
                " Negativo (-): Menos aportes que el promedio histórico (crítico)"
            ])
        ]),
        
        html.H6("Colores:", className="fw-bold mb-2 mt-3"),
        html.Ul([
            html.Li([
                html.Span("●", style={'color': '#28a745', 'fontSize': '1.2rem'}),
                " Verde: ≥100% del histórico (excelente - abundancia hídrica)"
            ]),
            html.Li([
                html.Span("●", style={'color': '#17a2b8', 'fontSize': '1.2rem'}),
                " Azul: 90-100% del histórico (normal - cerca del promedio)"
            ]),
            html.Li([
                html.Span("●", style={'color': '#dc3545', 'fontSize': '1.2rem'}),
                " Rojo: <90% del histórico (crítico - déficit hídrico)"
            ])
        ])
    ])
], id="modal-info-ficha-kpi", is_open=False, size="lg", centered=True)

# Agregar modales al layout final
layout_with_modal = html.Div([layout, modal_rio_table, modal_info_ficha_kpi])
layout = layout_with_modal

# Layout del panel de controles (lo que antes estaba en el layout principal)
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
                    # ✅ OPTIMIZADO: Consulta inteligente SQLite (>=2020) vs API (<2020)
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
def crear_mapa_embalses_directo(regiones_totales, df_completo_embalses):
    """Crea el mapa mostrando CADA EMBALSE como un círculo/bolita individual de color sobre mapa real de Colombia."""
    try:
        import plotly.graph_objects as go
        import random
        from math import sin, cos, radians
        
        if regiones_totales is None or regiones_totales.empty:
            return dbc.Alert("No hay datos de regiones disponibles", color="warning")
        
        if df_completo_embalses is None or df_completo_embalses.empty:
            return dbc.Alert("No hay datos de embalses disponibles", color="warning")
        
        logger.info("Creando mapa con bolitas individuales por embalse sobre mapa real de Colombia...")
        logger.debug(f"Total embalses en df_completo_embalses: {len(df_completo_embalses)}")
        
        # Crear figura con mapa base de Colombia
        fig = go.Figure()
        
        # Usar cache de GeoJSON (archivos estáticos cargados UNA vez)
        try:
            cache = _cargar_geojson_cache()
            
            if cache is None or not cache['loaded']:
                logger.error("❌ Cache de GeoJSON no disponible")
                # Continuar sin mapa base
                colombia_geojson = None
                DEPARTAMENTOS_A_REGIONES = {}
            else:
                # Obtener datos del cache (ya cargados en memoria)
                colombia_geojson = cache['colombia_geojson']
                regiones_config = cache['regiones_config']
                DEPARTAMENTOS_A_REGIONES = cache['departamentos_a_regiones']
                
                logger.info(f"✅ Usando cache de GeoJSON: {len(regiones_config['regiones'])} regiones")
            
            # Solo dibujar mapa base si tenemos los datos
            if colombia_geojson and DEPARTAMENTOS_A_REGIONES:
                # Agregar el mapa de Colombia como fondo con colores por región natural
                departamentos_dibujados = 0
                for feature in colombia_geojson['features']:
                    # Obtener nombre del departamento y normalizarlo
                    nombre_dpto_original = feature['properties'].get('NOMBRE_DPT', '')
                    nombre_dpto = nombre_dpto_original.upper().strip()
                    
                    # Normalizar nombres especiales
                    if 'BOGOTA' in nombre_dpto or 'D.C' in nombre_dpto:
                        nombre_dpto = 'CUNDINAMARCA'
                    elif 'SAN ANDRES' in nombre_dpto:
                        nombre_dpto = 'SAN ANDRES Y PROVIDENCIA'
                    elif 'NARIÑO' in nombre_dpto_original:
                        nombre_dpto = 'NARIÑO'
                    elif 'BOYACÁ' in nombre_dpto_original:
                        nombre_dpto = 'BOYACA'
                    elif 'CÓRDOBA' in nombre_dpto_original:
                        nombre_dpto = 'CORDOBA'
                    
                    # Determinar color según región natural
                    if nombre_dpto in DEPARTAMENTOS_A_REGIONES:
                        info_region = DEPARTAMENTOS_A_REGIONES[nombre_dpto]
                        fillcolor = info_region['color']
                        bordercolor = info_region['border']
                        region_nombre = info_region['region']
                        hovertext = f"<b>{nombre_dpto_original}</b><br>{region_nombre}"
                    else:
                        fillcolor = 'rgba(220, 220, 220, 0.2)'
                        bordercolor = '#999999'
                        hovertext = f"<b>{nombre_dpto_original}</b>"
                    
                    # Manejar Polygon y MultiPolygon
                    geometry_type = feature['geometry']['type']
                    coords_list = []
                    
                    if geometry_type == 'Polygon':
                        coords_list = [feature['geometry']['coordinates'][0]]
                    elif geometry_type == 'MultiPolygon':
                        coords_list = [poly[0] for poly in feature['geometry']['coordinates']]
                    
                    # Dibujar cada polígono del departamento
                    for coords in coords_list:
                        lons = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        
                        fig.add_trace(go.Scattergeo(
                            lon=lons,
                            lat=lats,
                            mode='lines',
                            line=dict(width=1.5, color=bordercolor),
                            fill='toself',
                            fillcolor=fillcolor,
                            hoverinfo='text',
                            hovertext=hovertext,
                            showlegend=False
                        ))
                    
                    departamentos_dibujados += 1
                
                logger.info(f"Mapa de Colombia cargado: {departamentos_dibujados} departamentos")
                
        except Exception as e:
            logger.warning(f"Error al cargar mapa base: {e}")
        
        # Procesar embalses
        leyenda_mostrada = {'ALTO': False, 'MEDIO': False, 'BAJO': False}
        embalses_mapeados = 0
        
        for idx, row in df_completo_embalses.iterrows():
            nombre_embalse = str(row.get('Embalse', '')).strip()
            region_embalse = str(row.get('Región', '')).strip()
            
            if not nombre_embalse or not region_embalse:
                continue
            
            region_normalizada = region_embalse.upper()
            
            if region_normalizada not in REGIONES_COORDENADAS:
                continue
            
            participacion = float(row.get('Participación (%)', 0))
            volumen_pct = float(row.get('Volumen Útil (%)', 0))
            
            riesgo, color, icono = calcular_semaforo_embalse(participacion, volumen_pct)
            
            coords_region = REGIONES_COORDENADAS[region_normalizada]
            lat_centro = coords_region['lat']
            lon_centro = coords_region['lon']
            
            # Posición aleatoria pero consistente
            seed_value = hash(nombre_embalse + region_normalizada) % 100000
            random.seed(seed_value)
            
            radio_lat = 0.5
            radio_lon = 0.6
            
            angulo = random.uniform(0, 360)
            distancia = random.uniform(0.4, 1.0)
            
            offset_lat = distancia * radio_lat * sin(radians(angulo))
            offset_lon = distancia * radio_lon * cos(radians(angulo))
            
            lat_embalse = lat_centro + offset_lat
            lon_embalse = lon_centro + offset_lon
            
            hover_text = (
                f"<b>{nombre_embalse}</b><br>"
                f"Región: {coords_region['nombre']}<br>"
                f"Participación: {participacion:.2f}%<br>"
                f"Volumen Útil: {volumen_pct:.1f}%<br>"
                f"<b>Riesgo: {riesgo}</b> {icono}"
            )
            
            tamaño = max(12, min(10 + participacion * 0.8, 35))
            
            mostrar_leyenda = not leyenda_mostrada[riesgo]
            if mostrar_leyenda:
                leyenda_mostrada[riesgo] = True
                nombre_leyenda = f"{icono} Riesgo {riesgo}"
            else:
                nombre_leyenda = nombre_embalse
            
            fig.add_trace(go.Scattergeo(
                lon=[lon_embalse],
                lat=[lat_embalse],
                mode='markers',
                marker=dict(
                    size=tamaño,
                    color=color,
                    line=dict(width=2, color='white'),
                    symbol='circle',
                    opacity=0.9
                ),
                name=nombre_leyenda,
                hovertext=hover_text,
                hoverinfo='text',
                showlegend=mostrar_leyenda,
                legendgroup=riesgo
            ))
            
            embalses_mapeados += 1
        
        if embalses_mapeados == 0:
            return dbc.Alert("No se pudieron mapear los embalses", color="warning")
        
        # Configurar el mapa
        fig.update_geos(
            projection_type='mercator',
            scope='south america',
            center=dict(lon=-73.5, lat=4.5),
            showcoastlines=True,
            coastlinecolor='#333333',
            coastlinewidth=2,
            showland=True,
            landcolor='#f5f5f5',
            showcountries=True,
            countrycolor='#000000',
            countrywidth=2.5,
            showlakes=True,
            lakecolor='#b3d9ff',
            lonaxis_range=[-79.5, -66.5],
            lataxis_range=[-4.5, 13],
            bgcolor='#ffffff',
            resolution=50
        )
        
        fig.update_layout(
            height=455,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor='white',
            geo=dict(projection_scale=2.8),
            legend=dict(
                title=dict(text='Nivel de Riesgo', font=dict(size=10)),
                orientation='v',
                yanchor='top',
                y=0.98,
                xanchor='left',
                x=0.01,
                bgcolor='rgba(255,255,255,0.95)',
                bordercolor='#cccccc',
                borderwidth=2,
                font=dict(size=9)
            ),
            hoverlabel=dict(
                bgcolor='white',
                font_size=12,
                font_family='Arial',
                bordercolor='#666666'
            )
        )
        
        logger.info(f"Mapa creado exitosamente: {embalses_mapeados} embalses")
        return dcc.Graph(
            figure=fig, 
            config={
                'displayModeBar': True, 
                'displaylogo': False,
                'scrollZoom': True,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d']
            },
            style={'height': '100%', 'touchAction': 'auto'}
        )
        
    except Exception as e:
        logger.error(f"Error creando mapa: {e}", exc_info=True)
        return dbc.Alert(f"Error al crear el mapa: {str(e)}", color="danger")


# Callback principal para consultar y mostrar datos filtrando por río y fechas
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
            # ✅ OPTIMIZADO: Consulta inteligente SQLite (>=2020) vs API (<2020)
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
        # ✅ OPTIMIZADO: Consulta inteligente SQLite (>=2020) vs API (<2020)
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

def build_hierarchical_table_view(data_complete, expanded_regions, view_type="participacion"):
    """Construir vista de tabla jerárquica con botones integrados y sistema de semáforo CORREGIDO"""
    if not data_complete:
        return dash_table.DataTable(
            data=[],
            columns=[
                {"name": "Región / Embalse", "id": "nombre"},
                {"name": "Participación (%)" if view_type == "participacion" else "Volumen Útil (%)", "id": "valor"}
            ]
        )
    
    table_data = []
    processed_regions = set()
    style_data_conditional = []
    
    # Obtener todas las regiones únicas
    all_regions = set()
    for item in data_complete:
        if item.get('tipo') == 'region':
            region_name = item.get('region_name')
            if region_name:
                all_regions.add(region_name)
    
    # Crear lista de regiones con sus valores para ordenar de mayor a menor
    region_items = []
    for item in data_complete:
        if item.get('tipo') == 'region':
            region_name = item.get('region_name')
            if region_name and region_name not in processed_regions:
                # Obtener el valor para ordenar
                valor_str = item.get('participacion', item.get('capacidad', '0'))
                try:
                    # Extraer valor numérico del string (ej: "25.5%" -> 25.5)
                    if isinstance(valor_str, str):
                        valor_num = float(valor_str.replace('%', '').replace(',', '').strip())
                    else:
                        valor_num = float(valor_str) if valor_str else 0
                except (ValueError, AttributeError, TypeError) as e:
                    logger.debug(f"No se pudo convertir valor a numérico: {valor_str} - {e}")
                    valor_num = 0
                
                region_items.append({
                    'item': item,
                    'region_name': region_name,
                    'valor_num': valor_num
                })
                processed_regions.add(region_name)
    
    # Ordenar regiones por valor de mayor a menor
    region_items.sort(key=lambda x: x['valor_num'], reverse=True)
    
    # Procesar cada región en orden descendente
    for region_data in region_items:
        region_item = region_data['item']
        region_name = region_data['region_name']
        
        is_expanded = region_name in expanded_regions
        
        # Fila de región con botón integrado en el nombre
        button_icon = "⊟" if is_expanded else "⊞"  # Símbolos más elegantes
        table_data.append({
            "nombre": f"{button_icon} {region_name}",
            "valor": region_item.get('participacion', region_item.get('capacidad', ''))
        })
        
        # Si está expandida, agregar embalses ordenados de mayor a menor
        if is_expanded:
            # SOLUCIÓN DIRECTA: Crear diccionario unificado directamente desde data_complete
            embalses_unificados = {}
            
            for item in data_complete:
                if (item.get('tipo') == 'embalse' and 
                    item.get('region_name') == region_name):
                    embalse_name = item.get('nombre', '').replace('    └─ ', '').strip()
                    
                    if embalse_name not in embalses_unificados:
                        # CREAR ENTRADA COMPLETA con todos los datos necesarios
                        embalses_unificados[embalse_name] = {
                            'nombre': embalse_name,
                            'participacion_valor': item.get('participacion_valor', 0),
                            'volumen_valor': item.get('volumen_valor', 0),
                            'valor_display': item.get('participacion' if view_type == "participacion" else 'capacidad', ''),
                            'valor_num': 0
                        }
                        
                        # Calcular valor numérico para ordenar
                        valor_str = embalses_unificados[embalse_name]['valor_display']
                        try:
                            if isinstance(valor_str, str):
                                embalses_unificados[embalse_name]['valor_num'] = float(valor_str.replace('%', '').replace(',', '').strip())
                            else:
                                embalses_unificados[embalse_name]['valor_num'] = float(valor_str) if valor_str else 0
                        except (ValueError, AttributeError, TypeError) as e:
                            logger.debug(f"No se pudo convertir valor a numérico: {valor_str} - {e}")
                            embalses_unificados[embalse_name]['valor_num'] = 0
            
            # Convertir a lista y ordenar
            embalses_lista = list(embalses_unificados.values())
            embalses_lista.sort(key=lambda x: x.get('valor_num', 0), reverse=True)
            
            # 🔍 LOG: Verificar datos antes de construir tabla
            logger.info(f"🔍 [BUILD_TABLE] Región={region_name}, View={view_type}, Embalses={len(embalses_lista)}")
            
            # Procesar cada embalse con datos ya unificados
            for embalse_data in embalses_lista:
                embalse_name = embalse_data['nombre']
                valor_embalse = embalse_data['valor_display']
                participacion_val = embalse_data.get('participacion_valor', 0)
                volumen_val = embalse_data.get('volumen_valor', 0)
                
                # 🔍 LOG CRÍTICO: Valores que se mostrarán en la tabla
                logger.info(f"🔍 [TABLE_DISPLAY] {embalse_name} ({view_type}): Display={valor_embalse}, Part={participacion_val}%, Vol={volumen_val}%")
                
                
                # Clasificar riesgo con ambos valores CORRECTOS
                nivel_riesgo = clasificar_riesgo_embalse(participacion_val, volumen_val)
                
                # Agregar fila del embalse
                row_index = len(table_data)
                table_data.append({
                    "nombre": f"    └─ {embalse_name}",
                    "valor": valor_embalse
                })
                
                # Agregar estilo condicional para el semáforo solo en tabla de participación
                if view_type == "participacion":
                    estilo = obtener_estilo_riesgo(nivel_riesgo)
                    style_data_conditional.append({
                        'if': {'row_index': row_index},
                        **estilo
                    })
    
    # Agregar fila TOTAL
    total_item = None
    for item in data_complete:
        if item.get('tipo') == 'total':
            total_item = item
            break
    
    if total_item:
        table_data.append({
            "nombre": "TOTAL SISTEMA",
            "valor": total_item.get('participacion', total_item.get('capacidad', ''))
        })
    
    # Crear tabla con estructura de 2 columnas
    return dash_table.DataTable(
        id=f"tabla-{view_type}-jerarquica-display",
        data=table_data,
        columns=[
            {"name": "Región / Embalse", "id": "nombre"},
            {"name": "Participación (%)" if view_type == "participacion" else "Volumen Útil (%)", "id": "valor"}
        ],
        style_cell={
            'textAlign': 'left',
            'padding': '8px',
            'fontFamily': 'Inter, Arial, sans-serif',
            'fontSize': 13,
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #dee2e6'
        },
        style_header={
            'backgroundColor': '#667eea' if view_type == 'participacion' else '#28a745',
            'color': 'white',
            'fontWeight': 'bold',
            'fontSize': 14,
            'textAlign': 'center',
            'border': f'1px solid {"#5a6cf0" if view_type == "participacion" else "#218838"}'
        },
        style_data_conditional=style_data_conditional + [
            {
                'if': {'filter_query': '{nombre} contains "⊞" || {nombre} contains "⊟"'},
                'backgroundColor': '#e3f2fd' if view_type == 'participacion' else '#e8f5e8',
                'fontWeight': 'bold',
                'cursor': 'pointer',
                'border': f'2px solid {"#2196f3" if view_type == "participacion" else "#28a745"}'
            },
            {
                'if': {'filter_query': '{nombre} = "TOTAL SISTEMA"'},
                'backgroundColor': '#007bff',
                'color': 'white',
                'fontWeight': 'bold'
            }
        ],
        page_action="none"
    )

# Callback para inicializar las vistas HTML desde los stores (DEBE IR PRIMERO - sin allow_duplicate)
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
from dash import clientside_callback, ClientsideFunction

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
def get_participacion_embalses(df_embalses):
    """
    Calcula la participación porcentual de cada embalse respecto al total e incluye columna de riesgo.
    """
    if df_embalses.empty or 'Capacidad_GWh_Internal' not in df_embalses.columns:
        return pd.DataFrame(columns=['Embalse', 'Participación (%)', 'Riesgo'])
    
    df_participacion = df_embalses.copy()
    total = df_participacion['Capacidad_GWh_Internal'].sum()
    
    if total > 0:
        # Calcular porcentajes sin redondear primero
        porcentajes = (df_participacion['Capacidad_GWh_Internal'] / total * 100)
        
        # Ajustar el último valor para que la suma sea exactamente 100%
        porcentajes_redondeados = porcentajes.round(2)
        diferencia = 100 - porcentajes_redondeados.sum()
        
        # Si hay diferencia por redondeo, ajustar el valor más grande
        if abs(diferencia) > 0.001:
            idx_max = porcentajes_redondeados.idxmax()
            porcentajes_redondeados.loc[idx_max] += diferencia
            
        df_participacion['Participación (%)'] = porcentajes_redondeados.round(2)
    else:
        df_participacion['Participación (%)'] = 0
    
    # 🆕 Agregar columna de riesgo usando las funciones existentes
    df_con_riesgo = agregar_columna_riesgo_a_tabla(df_participacion)
    
    # Ordenar de mayor a menor por participación
    df_con_riesgo = df_con_riesgo.sort_values('Participación (%)', ascending=False)
    
    # Solo devolver las columnas necesarias (SIN capacidad, CON riesgo)
    df_final = df_con_riesgo[['Embalse', 'Participación (%)', 'Riesgo']].reset_index(drop=True)
    
    # Agregar fila TOTAL
    total_row = pd.DataFrame({
        'Embalse': ['TOTAL'],
        'Participación (%)': [100.0],
        'Riesgo': ['⚡']  # 🆕 Ícono especial para TOTAL
    })
    
    df_final = pd.concat([df_final, total_row], ignore_index=True)
    
    return df_final

def get_embalses_completa_para_tabla(region=None, start_date=None, end_date=None, embalses_df_preconsultado=None):
    """
    Función unificada que combina participación y volumen útil en UNA SOLA tabla.
    Retorna: Embalse, Participación (%), Volumen Útil (%), Riesgo
    USA LAS FUNCIONES QUE YA FUNCIONAN (get_tabla_regiones_embalses)
    
    Args:
        region: Región a filtrar (opcional)
        start_date: Fecha inicio (opcional)
        end_date: Fecha fin (opcional)
        embalses_df_preconsultado: DataFrame ya consultado de get_embalses_capacidad() para evitar consultas redundantes (opcional)
    """
# print(f"🔥🔥🔥 [INIT] get_embalses_completa_para_tabla LLAMADA: region={region}, dates={start_date} to {end_date}, preconsultado={'SÍ' if embalses_df_preconsultado is not None else 'NO'}")
    try:
        # ⚡ OPTIMIZACIÓN: Si ya se pasaron datos pre-consultados, usarlos directamente
        if embalses_df_preconsultado is not None and not embalses_df_preconsultado.empty:
# print(f"⚡ [OPTIMIZADO] Usando datos pre-consultados: {len(embalses_df_preconsultado)} embalses")
            df_embalses = embalses_df_preconsultado.copy()
            
            # El DataFrame pre-consultado ya tiene las columnas necesarias
            # Solo necesitamos filtrar por región si aplica
            if region and region != "__ALL_REGIONS__":
                region_normalized = region.strip().upper()
                if 'Región' in df_embalses.columns:
                    df_embalses = df_embalses[df_embalses['Región'] == region_normalized]
# print(f"🔥 [FILTER] Filtrado por región {region_normalized}: {len(df_embalses)} embalses")
        else:
            # Consultar datos si no se pasaron pre-consultados
# print(f"📊 [CONSULTA] Consultando datos de embalses...")
            regiones_totales, df_embalses = get_tabla_regiones_embalses(start_date, end_date)
            
# print(f"🔥 [AFTER_CALL] get_tabla_regiones_embalses retornó: {len(df_embalses)} embalses")
            
            # Filtrar por región si se especificó
            if region and region != "__ALL_REGIONS__":
                # ✅ FIX ERROR #3: UPPER en lugar de title
                region_normalized = region.strip().upper()
                df_embalses = df_embalses[df_embalses['Región'] == region_normalized]
# print(f"🔥 [FILTER] Filtrado por región {region_normalized}: {len(df_embalses)} embalses")
        
        if df_embalses.empty:
# print(f"⚠️ [RETURN_EMPTY] DataFrame vacío")
            return []
        
        if df_embalses.empty:
# print(f"⚠️ [RETURN_EMPTY] No hay embalses en región {region}")
            return []
        
        # Preparar datos para la tabla combinada
        table_data = []
        for _, row in df_embalses.iterrows():
            # Ya tiene Participación (%) calculado por get_tabla_regiones_embalses
            participacion_val = row.get('Participación (%)', 0)
            volumen_val = row.get('Volumen Útil (%)', None)
            
            # Formatear volumen útil
            if pd.notna(volumen_val):
                volumen_formatted = f"{float(volumen_val):.1f}%"
            else:
                volumen_formatted = "N/D"
            
            # Formatear participación
            participacion_formatted = f"{float(participacion_val):.2f}%"
            
            # Clasificar riesgo usando función existente
            riesgo = clasificar_riesgo_embalse(participacion_val, volumen_val if pd.notna(volumen_val) else 0)
            
            formatted_row = {
                'Embalse': row['Embalse'],
                'Participación (%)': participacion_formatted,
                'Volumen Útil (%)': volumen_formatted,
                'Riesgo': riesgo
            }
            table_data.append(formatted_row)
        
        # Ordenar por participación descendente
        table_data.sort(key=lambda x: float(x['Participación (%)'].replace('%', '')), reverse=True)
        
# print(f"✅ [SUCCESS] Tabla generada con {len(table_data)} filas")
        
        # Agregar fila TOTAL
        if table_data:
            # Calcular promedio de volumen útil
            volumenes = [float(row['Volumen Útil (%)'].replace('%', '')) for row in table_data if row['Volumen Útil (%)'] != 'N/D']
            avg_volume = sum(volumenes) / len(volumenes) if volumenes else None
            
            total_row = {
                'Embalse': 'TOTAL',
                'Participación (%)': '100.00%',
                'Volumen Útil (%)': f"{avg_volume:.1f}%" if avg_volume is not None else "N/D",
                'Riesgo': '⚡'
            }
            table_data.append(total_row)
        
# print(f"🎯 [FINAL] Total final: {len(table_data)} filas (incluye TOTAL)")
        return table_data
        
    except Exception as e:
# print(f"❌ [ERROR] Exception: {e}")
        logger.error(f"❌ Error en get_embalses_completa_para_tabla: {e}")
        import traceback
        traceback.print_exc()
        return []

# --- Función para clasificar riesgo según participación y volumen útil ---
def clasificar_riesgo_embalse(participacion, volumen_util):
    """
    Clasifica el riesgo de un embalse basado en participación y volumen útil
    
    Args:
        participacion (float): Participación porcentual en el sistema (0-100)
        volumen_util (float): Volumen útil disponible (0-100)
    
    Returns:
        str: '🟢' (bajo riesgo), '🟡' (riesgo medio), '🔴' (alto riesgo)
    """
    # MATRIZ DE RIESGO CORREGIDA: Combinar participación Y volumen
    
    # Caso 1: Embalses muy importantes (participación >= 15%)
    if participacion >= 15:
        if volumen_util < 30:
            return '🔴'  # Embalse importante con poco volumen = ALTO RIESGO
        elif volumen_util < 70:
            return '🟡'  # Embalse importante con volumen moderado = RIESGO MEDIO
        else:
            return '🟢'  # Embalse importante con buen volumen = BAJO RIESGO
    
    # Caso 2: Embalses importantes (participación >= 10%)
    elif participacion >= 10:
        if volumen_util < 20:
            return '🔴'  # Embalse importante con muy poco volumen = ALTO RIESGO
        elif volumen_util < 60:
            return '🟡'  # Embalse importante con volumen bajo-moderado = RIESGO MEDIO
        else:
            return '🟢'  # Embalse importante con buen volumen = BAJO RIESGO
    
    # Caso 3: Embalses moderadamente importantes (participación >= 5%)
    elif participacion >= 5:
        if volumen_util < 15:
            return '🔴'  # Embalse moderado con muy poco volumen = ALTO RIESGO
        elif volumen_util < 50:
            return '🟡'  # Embalse moderado con volumen bajo = RIESGO MEDIO
        else:
            return '🟢'  # Embalse moderado con volumen adecuado = BAJO RIESGO
    
    # Caso 4: Embalses menos importantes (participación < 5%)
    else:
        if volumen_util < 25:
            return '🟡'  # Embalse pequeño con poco volumen = RIESGO MEDIO
        else:
            return '🟢'  # Embalse pequeño con volumen adecuado = BAJO RIESGO

def obtener_estilo_riesgo(nivel_riesgo):
    """
    Obtiene el estilo CSS para el nivel de riesgo
    
    Args:
        nivel_riesgo (str): 'high', 'medium', 'low'
    
    Returns:
        dict: Estilo CSS para DataTable
    """
    estilos = {
        'high': {
            'backgroundColor': '#fee2e2',  # Rojo claro
            'color': '#991b1b',           # Rojo oscuro
            'fontWeight': 'bold'
        },
        'medium': {
            'backgroundColor': '#fef3c7',  # Amarillo claro
            'color': '#92400e',           # Amarillo oscuro
            'fontWeight': 'bold'
        },
        'low': {
            'backgroundColor': '#d1fae5',  # Verde claro
            'color': '#065f46'            # Verde oscuro
        }
    }
    return estilos.get(nivel_riesgo, estilos['low'])

def obtener_pictograma_riesgo(nivel_riesgo):
    """
    Obtiene el pictograma para el nivel de riesgo
    
    Args:
        nivel_riesgo (str): 'high', 'medium', 'low'
    
    Returns:
        str: Emoji o símbolo para el nivel de riesgo
    """
    pictogramas = {
        'high': '🔴',     # Círculo rojo
        'medium': '🟡',   # Círculo amarillo  
        'low': '🟢'       # Círculo verde
    }
    return pictogramas.get(nivel_riesgo, '🟢')

def agregar_columna_riesgo_a_tabla(df_embalses):
    """
    Agrega la columna de riesgo con pictogramas a una tabla de embalses
    
    Args:
        df_embalses (DataFrame): DataFrame con datos de embalses que debe incluir:
                                - 'Embalse': nombre del embalse
                                - 'Capacidad_GWh_Internal': para calcular participación
                                - 'Volumen Útil (%)': para evaluar riesgo
    
    Returns:
        DataFrame: DataFrame con columna 'Riesgo' agregada
    """
    if df_embalses.empty:
        return df_embalses
    
    # Crear una copia para no modificar el original
    df_con_riesgo = df_embalses.copy()
    
    # Calcular participación si no existe
    if 'Participación (%)' not in df_con_riesgo.columns and 'Capacidad_GWh_Internal' in df_con_riesgo.columns:
        # Filtrar filas que no sean TOTAL para calcular participación
        df_no_total = df_con_riesgo[df_con_riesgo['Embalse'] != 'TOTAL'].copy()
        if not df_no_total.empty:
            total_capacidad = df_no_total['Capacidad_GWh_Internal'].sum()
            if total_capacidad > 0:
                df_con_riesgo.loc[df_no_total.index, 'Participación (%)'] = (
                    df_no_total['Capacidad_GWh_Internal'] / total_capacidad * 100
                ).round(2)
            else:
                df_con_riesgo.loc[df_no_total.index, 'Participación (%)'] = 0
    
    # Inicializar columna de riesgo
    df_con_riesgo['Riesgo'] = ''
    
    # Calcular riesgo para cada embalse (excepto TOTAL)
    for idx, row in df_con_riesgo.iterrows():
        if row['Embalse'] != 'TOTAL':
            participacion = row.get('Participación (%)', 0)
            
            # Extraer valor numérico del volumen útil (puede estar como "45.2%", 45.2, o None)
            volumen_util = row.get('Volumen Útil (%)', 0)
            
            # Manejar diferentes tipos de datos
            if volumen_util is None or (isinstance(volumen_util, str) and volumen_util == 'N/D'):
                volumen_util = 0
            elif isinstance(volumen_util, str):
                # Si es string como "45.2%", extraer el número
                try:
                    volumen_util = float(volumen_util.replace('%', '').replace(',', '.').strip())
                except (ValueError, AttributeError):
                    volumen_util = 0
            elif pd.isna(volumen_util):
                volumen_util = 0
            else:
                # Ya es un número, asegurarse de que sea float
                volumen_util = float(volumen_util)
            
            # Clasificar riesgo
            nivel_riesgo = clasificar_riesgo_embalse(participacion, volumen_util)
            pictograma = obtener_pictograma_riesgo(nivel_riesgo)
            
            df_con_riesgo.at[idx, 'Riesgo'] = pictograma
        else:
            # Para la fila TOTAL, usar un ícono especial
            df_con_riesgo.at[idx, 'Riesgo'] = '⚡'
    
    return df_con_riesgo

def generar_estilos_condicionales_riesgo(df_con_riesgo):
    """
    Genera los estilos condicionales para colorear las filas según el nivel de riesgo
    
    Args:
        df_con_riesgo (DataFrame): DataFrame que incluye columnas de riesgo
    
    Returns:
        list: Lista de estilos condicionales para DataTable
    """
    estilos_condicionales = []
    
    # Recorrer cada fila para crear estilos específicos por embalse
    for idx, row in df_con_riesgo.iterrows():
        embalse = row['Embalse']
        
        if embalse != 'TOTAL':
            participacion = row.get('Participación (%)', 0)
            
            # Extraer valor numérico del volumen útil
            volumen_util = row.get('Volumen Útil (%)', 0)
            
            # Manejar diferentes tipos de datos
            if volumen_util is None or (isinstance(volumen_util, str) and volumen_util == 'N/D'):
                volumen_util = 0
            elif isinstance(volumen_util, str):
                try:
                    volumen_util = float(volumen_util.replace('%', '').replace(',', '.').strip())
                except (ValueError, AttributeError):
                    volumen_util = 0
            elif pd.isna(volumen_util):
                volumen_util = 0
            else:
                volumen_util = float(volumen_util)
            
            # Clasificar riesgo
            nivel_riesgo = clasificar_riesgo_embalse(participacion, volumen_util)
            estilo_riesgo = obtener_estilo_riesgo(nivel_riesgo)
            
            # Crear estilo condicional para este embalse específico
            estilo_embalse = {
                'if': {'filter_query': f'{{Embalse}} = "{embalse}"'},
                'backgroundColor': estilo_riesgo['backgroundColor'],
                'color': estilo_riesgo['color'],
                'fontWeight': estilo_riesgo.get('fontWeight', 'normal')
            }
            estilos_condicionales.append(estilo_embalse)
    
    # Estilo para la fila TOTAL
    estilo_total = {
        'if': {'filter_query': '{Embalse} = "TOTAL"'},
        'backgroundColor': '#007bff',
        'color': 'white',
        'fontWeight': 'bold'
    }
    estilos_condicionales.append(estilo_total)
    
    return estilos_condicionales

# Layout con almacenamiento local
layout = html.Div([
    dcc.Store(id="participacion-jerarquica-data"),
    dcc.Store(id="capacidad-jerarquica-data"),
    dcc.Store(id="ultima-fecha-con-datos"),
    layout_with_modal
])

# Funciones auxiliares heredadas
# --- Función para crear tabla con participación porcentual y semáforo ---
def get_tabla_con_participacion(df_embalses):
    """
    Crea una tabla que combina la capacidad útil con la participación porcentual.
    """
    if df_embalses.empty or 'Capacidad_GWh_Internal' not in df_embalses.columns:
        return pd.DataFrame(columns=['Embalse', 'Participación (%)'])
    
    df_resultado = df_embalses.copy()
    total = df_resultado['Capacidad_GWh_Internal'].sum()
    
    if total > 0:
        # Calcular porcentajes sin redondear primero
        porcentajes = (df_resultado['Capacidad_GWh_Internal'] / total * 100)
        
        # Ajustar el último valor para que la suma sea exactamente 100%
        porcentajes_redondeados = porcentajes.round(2)
        diferencia = 100 - porcentajes_redondeados.sum()
        
        # Si hay diferencia por redondeo, ajustar el valor más grande
        if abs(diferencia) > 0.001:
            idx_max = porcentajes_redondeados.idxmax()
            porcentajes_redondeados.loc[idx_max] += diferencia
            
        df_resultado['Participación (%)'] = porcentajes_redondeados.round(2)
    else:
        df_resultado['Participación (%)'] = 0
    
    # Ordenar de mayor a menor por participación
    df_resultado = df_resultado.sort_values('Participación (%)', ascending=False)
    
    return df_resultado[['Embalse', 'Participación (%)', 'Volumen Útil (%)']].reset_index(drop=True)

# --- Función para crear tabla jerárquica de regiones con embalses ---
def get_tabla_regiones_embalses(start_date=None, end_date=None):
    """
    Crea una tabla jerárquica que muestra primero las regiones y permite expandir para ver embalses.
    """
    try:
        objetoAPI = get_objetoAPI()
        
        # Obtener información de embalses desde API XM (fuente de verdad para regiones)
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        embalses_info, warning = obtener_datos_inteligente('ListadoEmbalses','Sistema', yesterday, today)
        
        # ✅ NORMALIZAR usando funciones unificadas
        embalses_info['Values_Name'] = normalizar_codigo(embalses_info['Values_Name'])
        embalses_info['Values_HydroRegion'] = normalizar_region(embalses_info['Values_HydroRegion'])
        
        # ✅ FIX: Limpiar duplicados y entradas sin región (causa de "inflated values" / duplicados visuales)
        # Priorizar entradas con región válida
        if not embalses_info.empty:
            # Eliminar registros con región vacía o nula
            embalses_info = embalses_info[embalses_info['Values_HydroRegion'].notna() & (embalses_info['Values_HydroRegion'] != '')]
            # Eliminar duplicados de nombre
            embalses_info = embalses_info.drop_duplicates(subset=['Values_Name'])
            logger.info(f"Listado embalses filtrado: {len(embalses_info)} registros únicos con región")

        # CREAR MAPEO CÓDIGO → REGIÓN (fuente única de verdad)
        embalse_region_map = dict(zip(embalses_info['Values_Name'], embalses_info['Values_HydroRegion']))
        logger.debug(f"Mapeo embalse-región creado: {len(embalse_region_map)} embalses")

        # Obtener fecha con datos COMPLETOS (n_vol/n_cap >= 80%)
        fecha_solicitada = end_date if end_date else start_date
        today = datetime.now().strftime('%Y-%m-%d')
        fecha_obj = datetime.strptime(fecha_solicitada if fecha_solicitada else today, '%Y-%m-%d').date()
        
        # Buscar fecha con datos completos en últimos 7 días
        fecha_encontrada = None
        df_vol_test = None
        df_cap_test = None
        
        for dias_atras in range(7):
            fecha_busq = fecha_obj - timedelta(days=dias_atras)
            df_vol_tmp, f_vol = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_busq, dias_busqueda=1)
            df_cap_tmp, f_cap = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_busq, dias_busqueda=1)
            
            if df_vol_tmp is None or df_vol_tmp.empty or df_cap_tmp is None or df_cap_tmp.empty:
                continue
            if f_vol != f_cap:
                continue
            
            # Validar completitud
            col_emb_v = next((c for c in ['Embalse', 'recurso', 'Values_code'] if c in df_vol_tmp.columns), None)
            col_emb_c = next((c for c in ['Embalse', 'recurso', 'Values_code'] if c in df_cap_tmp.columns), None)
            
            if col_emb_v and col_emb_c:
                n_v = df_vol_tmp[col_emb_v].nunique()
                n_c = df_cap_tmp[col_emb_c].nunique()
                if n_c > 0 and n_v / n_c < 0.80:
                    logger.warning(f"get_tabla_regiones: datos incompletos {fecha_busq}: n_vol={n_v}, n_cap={n_c}")
                    continue
            
            fecha_encontrada = f_vol
            df_vol_test = df_vol_tmp
            df_cap_test = df_cap_tmp
            break
        
        if fecha_encontrada is None or df_vol_test is None or df_cap_test is None:
            logger.warning("No se encontraron datos en ninguna fecha reciente")
            return pd.DataFrame(), pd.DataFrame()
        
        fecha = fecha_encontrada.strftime('%Y-%m-%d')
        logger.debug(f"[DEBUG] Usando fecha con datos disponibles para cálculo de embalses: {fecha} ({len(df_vol_test)} embalses con volumen)")

        if not fecha:
            logger.warning("No se encontraron datos en ninguna fecha reciente")
            return pd.DataFrame(), pd.DataFrame()

        # DataFrame detallado de embalses usando la fecha con datos
        logger.debug(f"Construyendo tabla de embalses para fecha: {fecha}")
        embalses_detalle = []

        # Consultar datos de volumen y capacidad para la fecha encontrada
        df_vol, _ = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_encontrada)
        df_cap, _ = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_encontrada)

        # ✅ NO CONVERTIR: obtener_datos_inteligente ya devuelve valores en GWh cuando viene de SQLite
        # Los datos de la API XM vienen en Wh, pero se convierten en obtener_datos_inteligente
        # Por lo tanto, 'Value' ya está en GWh aquí
        df_vol['Value_GWh'] = df_vol['Value']
        df_cap['Value_GWh'] = df_cap['Value']

        # ✅ SIEMPRE incluir TODOS los embalses del listado maestro (25 embalses)
        # Si no tienen datos, mostrar 0 o N/D
        for _, embalse_info in embalses_info.iterrows():
            embalse_name = embalse_info['Values_Name']
            region_name = embalse_info['Values_HydroRegion']

            # Buscar datos de este embalse
            # ✅ FIX ERROR #1: obtener_datos_desde_bd retorna columna 'Embalse', NO 'Name'
            vol_data = df_vol[df_vol['Embalse'] == embalse_name]
            cap_data = df_cap[df_cap['Embalse'] == embalse_name]

            # ✅ CAMBIO CRÍTICO: Incluir embalse aunque NO tenga datos
            if not vol_data.empty and not cap_data.empty:
                vol_gwh = vol_data['Value_GWh'].iloc[0]
                cap_gwh = cap_data['Value_GWh'].iloc[0]
                pct = (vol_gwh / cap_gwh * 100) if cap_gwh > 0 else 0
            else:
                # Si no tiene datos, usar 0 para permitir su visualización
                vol_gwh = 0.0
                cap_gwh = 0.0
                pct = 0.0
                logger.debug(f"⚠️ Embalse {embalse_name} sin datos - incluido con valores 0")

            embalses_detalle.append({
                'Embalse': embalse_name,
                'Región': region_name,
                'VoluUtilDiarEner (GWh)': vol_gwh,
                'CapaUtilDiarEner (GWh)': cap_gwh,
                'Volumen Útil (%)': pct
            })

        df_embalses = pd.DataFrame(embalses_detalle)
        
        # ✅ FIX #1B: Eliminar duplicados (API puede retornar mismo embalse múltiples veces)
        if not df_embalses.empty:
            registros_antes = len(df_embalses)
            df_embalses = df_embalses.drop_duplicates(subset=['Embalse'], keep='first')
            registros_despues = len(df_embalses)
            if registros_antes != registros_despues:
                logger.info(f"🔍 Eliminados {registros_antes - registros_despues} embalses duplicados (quedan {registros_despues} únicos)")
        
        logger.debug("Primeras filas df_embalses:")
        logger.debug(f"\n{df_embalses[['Región', 'VoluUtilDiarEner (GWh)', 'CapaUtilDiarEner (GWh)']].head(10)}")

        # Procesar datos si tenemos embalses
        if not df_embalses.empty:
            # ✅ FIX ERROR #1: Calcular participación a nivel NACIONAL (no por región)
            # Esto evita embalses duplicados y garantiza que la suma sea 100% a nivel nacional
            df_embalses['Capacidad_GWh_Internal'] = df_embalses['CapaUtilDiarEner (GWh)']

            # Calcular participación NACIONAL (todos los embalses suman 100%)
            total_cap_nacional = df_embalses['Capacidad_GWh_Internal'].sum()
            if total_cap_nacional > 0:
                df_embalses['Participación (%)'] = (
                    df_embalses['Capacidad_GWh_Internal'] / total_cap_nacional * 100
                ).round(2)
            else:
                df_embalses['Participación (%)'] = 0.0

            # Crear tabla resumen por región usando los datos YA OBTENIDOS (no llamar a función externa)
            regiones_resumen = []
            regiones_unicas = [r for r in df_embalses['Región'].unique() if r and r.strip() and r.strip().lower() not in ['sin nacional', 'rios estimados', '']]
            
            for region in regiones_unicas:
                # Filtrar embalses de esta región
                embalses_region = df_embalses[df_embalses['Región'] == region]
                
                if not embalses_region.empty:
                    # Calcular totales directamente de los datos que ya tenemos
                    total_capacidad = embalses_region['CapaUtilDiarEner (GWh)'].sum()
                    total_volumen = embalses_region['VoluUtilDiarEner (GWh)'].sum()
                    
                    # Calcular porcentaje
                    if total_capacidad > 0:
                        porcentaje_volumen = (total_volumen / total_capacidad) * 100
                    else:
                        porcentaje_volumen = 0.0
                    
                    regiones_resumen.append({
                        'Región': region,
                        'Total (GWh)': round(total_capacidad, 2),
                        'Volumen Util (GWh)': round(total_volumen, 2),
                        'Volumen Útil (%)': round(porcentaje_volumen, 1)
                    })
                else:
                    regiones_resumen.append({
                        'Región': region,
                        'Total (GWh)': 0.00,
                        'Volumen Util (GWh)': 0.00,
                        'Volumen Útil (%)': 0.00
                    })
            
            regiones_totales = pd.DataFrame(regiones_resumen)
            
            # 🆕 Calcular participación porcentual de cada región respecto al total nacional
            # La participación se basa en la capacidad útil total de cada región
            total_capacidad_nacional = regiones_totales['Total (GWh)'].sum()
            
            if total_capacidad_nacional > 0:
                regiones_totales['Participación (%)'] = (
                    regiones_totales['Total (GWh)'] / total_capacidad_nacional * 100
                ).round(2)
            else:
                regiones_totales['Participación (%)'] = 0.0
            
            logger.debug(f"Tabla de regiones creada con {len(regiones_totales)} regiones")
            logger.debug(f"Participación por región: {regiones_totales[['Región', 'Participación (%)']].to_dict('records')}")
        else:
            # Si no hay datos, crear DataFrame vacío con estructura correcta
            regiones_totales = pd.DataFrame(columns=['Región', 'Total (GWh)', 'Volumen Util (GWh)', 'Volumen Útil (%)', 'Participación (%)'])
            logger.warning("No se pudieron obtener datos de embalses para las fechas disponibles")

        # (No agregar fila TOTAL SISTEMA aquí, se agregará manualmente en la tabla de participación)
        return regiones_totales, df_embalses
    except Exception as e:
# print(f"[ERROR] get_tabla_regiones_embalses: {e}")
        return pd.DataFrame(), pd.DataFrame()

def create_collapsible_regions_table(start_date=None, end_date=None):
    """
    Crea una tabla expandible elegante con regiones que se pueden plegar/desplegar para ver embalses.
    """
    try:
        # Usar fecha actual si no se proporcionan parámetros
        if not end_date:
            end_date = date.today().strftime('%Y-%m-%d')
        
        regiones_totales, df_completo_embalses = get_tabla_regiones_embalses(start_date, end_date)
        
        if regiones_totales.empty:
            return dbc.Alert("No se encontraron datos de regiones.", color="warning", className="text-center")
        
        # Crear componentes colapsables elegantes para cada región
        region_components = []
        
        for idx, region_row in regiones_totales.iterrows():
            region_name = region_row['Región']
            total_gwh = region_row['Total (GWh)']
            participacion = region_row['Participación (%)']
            
            # Obtener embalses de la región
            embalses_region = get_embalses_by_region(region_name, df_completo_embalses)
            
            # Contar embalses para mostrar en el header
            num_embalses = len(embalses_region) if not embalses_region.empty else 0
            
            # Crear contenido de embalses con las dos tablas lado a lado
            if not embalses_region.empty:
                # Preparar datos para las tablas con formateo
                embalses_data_formatted = []
                embalses_data_raw = []  # Para cálculos
                for _, embalse_row in embalses_region.iterrows():
                    embalse_name = embalse_row['Región'].replace('    └─ ', '')
                    embalse_capacidad = embalse_row['Total (GWh)']
                    embalse_participacion = embalse_row['Participación (%)']
                    
                    # Para la tabla de capacidad ya no incluimos la columna de GWh
                    embalses_data_formatted.append({
                        'Embalse': embalse_name,
                        'Participación (%)': embalse_participacion
                    })
                    
                    embalses_data_raw.append({
                        'Embalse': embalse_name,
                        'Capacidad_GWh_Internal': embalse_capacidad,  # Sin formatear para cálculos
                        'Participación (%)': embalse_participacion
                    })
                
                # Calcular total para la tabla de capacidad
                total_capacidad = sum([row['Capacidad_GWh_Internal'] for row in embalses_data_raw])
                
                # Crear tabla de participación porcentual
                tabla_participacion = dash_table.DataTable(
                    data=[{
                        'Embalse': row['Embalse'],
                        'Participación (%)': row['Participación (%)']
                    } for row in embalses_data_formatted] + [{'Embalse': 'TOTAL', 'Participación (%)': '100.0%'}],
                    columns=[
                        {"name": "Embalse", "id": "Embalse"},
                        {"name": "Participación (%)", "id": "Participación (%)"}
                    ],
                    style_cell={
                        'textAlign': 'left',
                        'padding': '8px',
                        'fontFamily': 'Inter, Arial, sans-serif',
                        'fontSize': 13,
                        'backgroundColor': '#f8f9fa',
                        'border': '1px solid #dee2e6'
                    },
                    style_header={
                        'backgroundColor': '#667eea',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'fontSize': 14,
                        'textAlign': 'center',
                        'border': '1px solid #5a6cf0'
                    },
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{Embalse} = "TOTAL"'},
                            'backgroundColor': '#007bff',
                            'color': 'white',
                            'fontWeight': 'bold'
                        }
                    ],
                    page_action="none"
                )
                
                # Crear tabla de capacidad detallada
                # Crear DataFrame temporal para obtener las columnas correctas
                temp_df = pd.DataFrame([{
                    'Embalse': row['Embalse'],
                    'Participación (%)': row['Participación (%)']
                } for row in embalses_data_formatted])
                
                tabla_capacidad = dash_table.DataTable(
                    data=embalses_data_formatted + [{
                        'Embalse': 'TOTAL',
                        'Participación (%)': ''
                    }],
                    columns=create_embalse_table_columns(temp_df),
                    style_cell={
                        'textAlign': 'left',
                        'padding': '8px',
                        'fontFamily': 'Inter, Arial, sans-serif',
                        'fontSize': 13,
                        'backgroundColor': '#f8f9fa',
                        'border': '1px solid #dee2e6'
                    },
                    style_header={
                        'backgroundColor': '#28a745',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'fontSize': 14,
                        'textAlign': 'center',
                        'border': '1px solid #218838'
                    },
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{Embalse} = "TOTAL"'},
                            'backgroundColor': '#007bff',
                            'color': 'white',
                            'fontWeight': 'bold'
                        }
                    ],
                    page_action="none"
                )
                
                embalses_content = html.Div([
                    html.Div([
                        html.I(className="bi bi-building me-2", style={"color": "#28a745"}),
                        html.Strong(f"Análisis Detallado - {region_name}", 
                                  className="text-success", style={"fontSize": "1.1rem"})
                    ], className="mb-4 d-flex align-items-center"),
                    
                    # Las dos tablas lado a lado
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardHeader([
                                    html.I(className="bi bi-pie-chart me-2", style={"color": "#667eea"}),
                                    html.Strong("📊 Participación Porcentual por Embalse")
                                ], style={"background": "linear-gradient(135deg, #e3f2fd 0%, #f3f4f6 100%)",
                                         "border": "none", "borderRadius": "8px 8px 0 0"}),
                                dbc.CardBody([
                                    html.P("Distribución porcentual de la capacidad energética entre embalses. La tabla incluye una fila TOTAL que suma exactamente 100%.", 
                                          className="text-muted mb-3", style={"fontSize": "0.85rem"}),
                                    tabla_participacion
                                ], className="p-3")
                            ], className="card-modern h-100")
                        ], md=6),
                        
                        dbc.Col([
                            dbc.Card([
                                dbc.CardHeader([
                                    html.I(className="bi bi-battery-full me-2", style={"color": "#28a745"}),
                                    html.Strong("🏭 Capacidad Detallada por Embalse")
                                ], style={"background": "linear-gradient(135deg, #e8f5e8 0%, #f3f4f6 100%)",
                                         "border": "none", "borderRadius": "8px 8px 0 0"}),
                                dbc.CardBody([
                                    html.P(f"Valores específicos de capacidad útil diaria en GWh para los {num_embalses} embalses de la región.", 
                                          className="text-muted mb-3", style={"fontSize": "0.85rem"}),
                                    tabla_capacidad
                                ], className="p-3")
                            ], className="card-modern h-100")
                        ], md=6)
                    ], className="g-3")
                ])
            else:
                embalses_content = dbc.Alert([
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    f"No se encontraron embalses para la región {region_name}."
                ], color="light", className="text-center my-3 alert-modern")
            
            # Crear card principal elegante para la región
            region_card = dbc.Card([
                # Header clickeable de la región
                dbc.CardHeader([
                    dbc.Button([
                        html.Div([
                            html.Div([
                                html.I(className="bi bi-chevron-right me-3", 
                                       id={"type": "chevron-region", "index": idx},
                                       style={"fontSize": "1.1rem", "color": "#007bff", "transition": "transform 0.3s ease"}),
                                html.I(className="bi bi-geo-alt-fill me-2", style={"color": "#28a745"}),
                                html.Strong(region_name, style={"fontSize": "1.1rem", "color": "#2d3748"})
                            ], className="d-flex align-items-center"),
                            html.Div([
                                dbc.Badge(f"{format_number(total_gwh)} GWh", color="primary", className="me-2 px-2 py-1"),
                                dbc.Badge(f"{participacion}%", color="success", className="px-2 py-1"),
                                html.Small(f" • {num_embalses} embalse{'s' if num_embalses != 1 else ''}", 
                                         className="text-muted ms-2")
                            ], className="d-flex align-items-center mt-1")
                        ], className="d-flex justify-content-between align-items-start w-100")
                    ], 
                    id={"type": "toggle-region", "index": idx},
                    className="w-100 text-start border-0 bg-transparent p-0",
                    style={"background": "transparent !important"}
                    )
                ], className="border-0 bg-gradient", 
                style={
                    "background": f"linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)",
                    "borderRadius": "12px 12px 0 0",
                    "padding": "1rem"
                }),
                
                # Contenido colapsable
                dbc.Collapse([
                    dbc.CardBody([
                        html.Hr(className="mt-0 mb-3", style={"borderColor": "#dee2e6"}),
                        embalses_content
                    ], className="pt-0", style={"backgroundColor": "#fdfdfe"})
                ],
                id={"type": "collapse-region", "index": idx},
                is_open=False
                )
            ], className="mb-3 shadow-sm",
            style={
                "border": "1px solid #e3e6f0",
                "borderRadius": "12px",
                "transition": "all 0.3s ease",
                "overflow": "hidden"
            })
            
            region_components.append(region_card)
        
        return html.Div([
            # Header explicativo elegante
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Strong("Capacidad Útil Diaria de Energía por Región Hidrológica", style={"fontSize": "1.2rem"})
                    ], className="d-flex align-items-center mb-2"),
                    html.P([
                        "Haz clic en cualquier región para expandir y ver sus tablas detalladas. ",
                        html.Strong("Cada región muestra dos tablas lado a lado:", className="text-primary"),
                        " participación porcentual de embalses y capacidad energética detallada en GWh."
                    ], className="mb-0 text-dark", style={"fontSize": "0.95rem"})
                ], className="py-3")
            ], className="mb-4", 
            style={
                "background": "linear-gradient(135deg, #e3f2fd 0%, #f3f4f6 100%)",
                "border": "1px solid #bbdefb",
                "borderRadius": "12px"
            }),
            
            # Container de regiones
            html.Div(region_components, id="regions-container")
        ])
        
    except Exception as e:
# print(f"Error creando tabla colapsable: {e}")
        return dbc.Alert(f"Error al crear tabla: {str(e)}", color="danger")


# Callback elegante para manejar el pliegue/despliegue de regiones
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


def get_embalses_by_region(region, df_completo):
    """
    Obtiene los embalses de una región específica con participación dentro de esa región.
    """
    # Usar la columna correcta 'Región' en lugar de 'Values_HydroRegion'
    embalses_region = df_completo[df_completo['Región'] == region].copy()
    if embalses_region.empty:
        return pd.DataFrame()
    
    total_region = embalses_region['Capacidad_GWh_Internal'].sum()
    if total_region > 0:
        embalses_region['Participación (%)'] = (embalses_region['Capacidad_GWh_Internal'] / total_region * 100).round(2)
        # Ajustar para que sume exactamente 100%
        diferencia = 100 - embalses_region['Participación (%)'].sum()
        if abs(diferencia) > 0.001:
            idx_max = embalses_region['Participación (%)'].idxmax()
            embalses_region.loc[idx_max, 'Participación (%)'] += diferencia
            embalses_region['Participación (%)'] = embalses_region['Participación (%)'].round(2)
    else:
        embalses_region['Participación (%)'] = 0
    
    # Formatear para mostrar como sub-elementos - usar la columna correcta 'Embalse'
    if 'Embalse' in embalses_region.columns:
        # Agregar columna de volumen útil si está disponible
        columns_to_include = ['Embalse', 'Capacidad_GWh_Internal', 'Participación (%)']
        if 'Volumen Útil (%)' in embalses_region.columns:
            columns_to_include.append('Volumen Útil (%)')
        
        resultado = embalses_region[columns_to_include].copy()
        resultado = resultado.rename(columns={
            'Embalse': 'Región', 
            'Capacidad_GWh_Internal': 'Total (GWh)',
            'Volumen Útil (%)': 'Volumen Útil (%)'
        })
        resultado['Región'] = '    └─ ' + resultado['Región'].astype(str)  # Identar embalses
        resultado['Tipo'] = 'embalse'
        return resultado
    else:
        logger.warning(f"Columnas disponibles en df_completo: {embalses_region.columns.tolist()}")
        return pd.DataFrame()
def get_embalses_data_for_table(region=None, start_date=None, end_date=None):
    """
    Función simple que obtiene datos de embalses con columnas formateados para la tabla.
    Retorna Embalse, Volumen Útil (%) y Riesgo para visualización, manteniendo cálculos internos.
    """
    try:
        # Obtener datos frescos con todas las columnas para cálculos
        df_fresh = get_embalses_capacidad(region, start_date, end_date)
        
        # 🔍 LOG: Datos obtenidos
        logger.info(f"🔍 [get_embalses_data_for_table] Región={region}, Registros={len(df_fresh)}")
        
        if df_fresh.empty:
            return []
        
        # Agregar columna de riesgo usando los datos completos
        df_con_riesgo = agregar_columna_riesgo_a_tabla(df_fresh)
        
        # Crear datos formateados para la tabla (solo columnas visibles)
        table_data = []
        
        for _, row in df_con_riesgo.iterrows():
            if row['Embalse'] != 'TOTAL':  # Procesar solo embalses, no TOTAL
                volumen_val = row['Volumen Útil (%)']
                
                # 🔍 LOG CRÍTICO: Valor RAW de Volumen Útil
                logger.info(f"🔍 [TABLE_DATA] {row['Embalse']}: Volumen RAW={volumen_val} (tipo={type(volumen_val).__name__})")
                
                # Solo formatear si es numérico, no reformatear strings
                if isinstance(volumen_val, str):
                    volumen_formatted = volumen_val  # Ya está formateado
                elif pd.notna(volumen_val) and isinstance(volumen_val, (int, float)):
                    volumen_formatted = f"{float(volumen_val):.1f}%"
                else:
                    volumen_formatted = "N/D"
                
                # 🔍 LOG CRÍTICO: Valor formateado final
                logger.info(f"🔍 [TABLE_DATA] {row['Embalse']}: Volumen FORMATTED={volumen_formatted}")
                
                formatted_row = {
                    'Embalse': row['Embalse'],
                    'Volumen Útil (%)': volumen_formatted,
                    'Riesgo': row['Riesgo']
                }
                table_data.append(formatted_row)
        
        # Agregar fila TOTAL (mantener cálculo interno de capacidad pero no mostrarla)
        total_capacity = df_fresh['Capacidad_GWh_Internal'].sum()
        valid_volume_data = df_fresh[df_fresh['Volumen Útil (%)'].notna()]
        avg_volume = valid_volume_data['Volumen Útil (%)'].mean() if not valid_volume_data.empty else None
        
        total_row = {
            'Embalse': 'TOTAL',
            'Volumen Útil (%)': f"{avg_volume:.1f}%" if avg_volume is not None else "N/D",
            'Riesgo': '⚡'  # Ícono especial para TOTAL
        }
        table_data.append(total_row)
        
        return table_data
        
    except Exception as e:
        return []

def get_embalses_capacidad(region=None, start_date=None, end_date=None):
    """
    Obtiene la capacidad útil diaria de energía por embalse desde la API XM (CapaUtilDiarEner) 
    y calcula el porcentaje de volumen útil usando la función unificada.
    Si se pasa una región, filtra los embalses de esa región.
    Solo incluye embalses que tienen datos de capacidad activos.
    
    IMPORTANTE: Usa solo end_date (fecha final) para los cálculos de volumen útil.
    """
    try:
        objetoAPI = get_objetoAPI()
        
        # Si no se proporcionan fechas, usar fecha actual
        if not start_date or not end_date:
            today = datetime.now().strftime('%Y-%m-%d')
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            start_date, end_date = yesterday, today
        
        # USAR SOLO LA FECHA FINAL para los cálculos de volumen útil
        fecha_para_calculo = end_date
        
        # Consultar datos de capacidad
        df_capacidad, warning = obtener_datos_inteligente('CapaUtilDiarEner','Embalse', fecha_para_calculo, fecha_para_calculo)
# print(f"� DEBUG CAPACIDAD: Datos de capacidad obtenidos: {len(df_capacidad) if df_capacidad is not None else 0} registros")
        
        # Si no hay datos para la fecha exacta, buscar fecha anterior con datos (igual que la función unificada)
        if df_capacidad is None or df_capacidad.empty:
            logger.debug("DEBUG CAPACIDAD: Buscando fecha anterior con datos...")
            # Usar helper para buscar fecha con datos disponibles
            fecha_obj = datetime.strptime(fecha_para_calculo, '%Y-%m-%d').date()
            df_capacidad, fecha_encontrada = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_obj)
            
            if fecha_encontrada is None or df_capacidad is None:
# print("❌ DEBUG CAPACIDAD: No se encontraron datos en los últimos 7 días")
                return pd.DataFrame()
            
            fecha_para_calculo = fecha_encontrada.strftime('%Y-%m-%d')
            logger.debug(f"DEBUG CAPACIDAD: Usando fecha con datos: {fecha_para_calculo}")
        
        logger.debug(f"DEBUG CAPACIDAD: Datos finales obtenidos: {len(df_capacidad)} registros")
        
        if 'Name' in df_capacidad.columns and 'Value' in df_capacidad.columns:
            # Obtener información de embalses desde API XM (fuente de verdad)
            today = datetime.now().strftime('%Y-%m-%d')
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            embalses_info, warning = obtener_datos_inteligente('ListadoEmbalses','Sistema', yesterday, today)
            
            # ✅ NORMALIZAR usando funciones unificadas
            embalses_info['Values_Name'] = normalizar_codigo(embalses_info['Values_Name'])
            embalses_info['Values_HydroRegion'] = normalizar_region(embalses_info['Values_HydroRegion'])
            embalse_region_dict = dict(zip(embalses_info['Values_Name'], embalses_info['Values_HydroRegion']))
            
            # ✅ FIX: obtener_datos_desde_bd retorna 'Embalse', NO 'Name'
            # NORMALIZAR códigos en df_capacidad ANTES de mapear
            df_capacidad['Name_Upper'] = normalizar_codigo(df_capacidad['Embalse'])
            logger.debug(f"Códigos normalizados: {df_capacidad['Name_Upper'].unique()[:5].tolist()}")
            
            if region:
                embalses_en_region = [e for e, r in embalse_region_dict.items() if r == region]
            
            # ✅ FIX: Usar 'Embalse' en lugar de 'Name'
            # Solo incluir embalses que tienen datos de capacidad
            embalses_con_datos = set(df_capacidad['Embalse'].unique())
            embalse_region_dict_filtrado = {
                embalse: region_emb for embalse, region_emb in embalse_region_dict.items() 
                if embalse in embalses_con_datos
            }
            
            # Procesar datos de capacidad usando código normalizado
            df_capacidad['Region'] = df_capacidad['Name_Upper'].map(embalse_region_dict)
            logger.debug(f"Regiones mapeadas: {df_capacidad['Region'].value_counts().to_dict()}")
            
            if region:
                # ✅ FIX ERROR #3: UPPER en lugar de title
                region_normalized = region.strip().upper()
                antes_filtro = len(df_capacidad)
                df_capacidad = df_capacidad[df_capacidad['Region'] == region_normalized]
            
            # ✅ NO CONVERTIR: obtener_datos_inteligente ya devuelve valores en GWh cuando viene de SQLite
            # Los datos de la API XM vienen en Wh, pero obtener_datos_inteligente los convierte automáticamente
            df_capacidad['Value_GWh'] = df_capacidad['Value']
            
            df_capacidad_grouped = df_capacidad.groupby('Name')['Value_GWh'].sum().reset_index()
            df_capacidad_grouped = df_capacidad_grouped.rename(columns={'Name': 'Embalse', 'Value_GWh': 'Capacidad_GWh_Internal'})
            
            logger.debug(f"DEBUG CAPACIDAD CORREGIDA: Valores después de conversión a GWh:")
# print(df_capacidad_grouped.head().to_string())
            
            # Obtener datos de volumen útil
            df_volumen, warning_vol = obtener_datos_inteligente('VoluUtilDiarEner','Embalse', fecha_para_calculo, fecha_para_calculo)
            
            if df_volumen is None or df_volumen.empty:
                # Buscar fecha anterior con datos
                fecha_obj = datetime.strptime(fecha_para_calculo, '%Y-%m-%d').date()
                df_volumen, fecha_vol = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_obj)
                if fecha_vol:
                    fecha_para_calculo_vol = fecha_vol.strftime('%Y-%m-%d')
                    logger.debug(f"Usando fecha alternativa para volumen: {fecha_para_calculo_vol}")
            
            # Procesar datos de volumen
            df_final = df_capacidad_grouped.copy()
            
            if df_volumen is not None and not df_volumen.empty and 'Name' in df_volumen.columns and 'Value' in df_volumen.columns:
                # ✅ NO CONVERTIR: obtener_datos_inteligente ya devuelve valores en GWh
                df_volumen['Value_GWh'] = df_volumen['Value']
                df_volumen_grouped = df_volumen.groupby('Name')['Value_GWh'].sum().reset_index()
                df_volumen_grouped = df_volumen_grouped.rename(columns={'Name': 'Embalse'})
                
                # Merge con capacidad
                df_final = df_final.merge(df_volumen_grouped, on='Embalse', how='left')
                
                # Calcular porcentaje: (Volumen / Capacidad) * 100 - IGUAL que en get_tabla_regiones_embalses
                df_final['Volumen Útil (%)'] = df_final.apply(
                    lambda row: round((row['Value_GWh'] / row['Capacidad_GWh_Internal'] * 100), 1)
                    if pd.notna(row.get('Value_GWh')) and row['Capacidad_GWh_Internal'] > 0 
                    else None,
                    axis=1
                )
                
                # Limpiar columna temporal
                df_final = df_final.drop(columns=['Value_GWh'])
                
                logger.info(f"✅ Volumen útil calculado: {df_final['Volumen Útil (%)'].notna().sum()}/{len(df_final)} embalses")
            else:
                df_final['Volumen Útil (%)'] = None
                logger.warning("⚠️ No hay datos de volumen útil disponibles")

            # IMPORTANTE: NO formatear aquí, dejar valores numéricos (o None)
            # El formateo se hace solo una vez en las funciones que crean las tablas
            
# print(df_final.head())

            return df_final.sort_values('Embalse')
        else:
            # Si no hay datos de capacidad, mostrar DataFrame vacío pero con columnas correctas
            return pd.DataFrame(columns=['Embalse', 'Capacidad_GWh_Internal', 'Volumen Útil (%)'])
    except Exception as e:
        logger.error(f"Error obteniendo datos de embalses: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return pd.DataFrame(columns=['Embalse', 'Capacidad_GWh_Internal', 'Volumen Útil (%)'])

def create_embalse_table_columns(df):
    """Crea las columnas para la tabla de embalses dinámicamente según las columnas disponibles"""
    columns = []
    logger.debug(f"Creando columnas para tabla - DataFrame tiene: {list(df.columns) if not df.empty else 'VACÍO'}")
    if not df.empty:
        for col in df.columns:
            if col == "Embalse":
                columns.append({"name": "Embalse", "id": "Embalse"})
            elif col == "Volumen Útil (%)":
                columns.append({"name": "Volumen Útil (%)", "id": "Volumen Útil (%)"})
            elif col == "Participación (%)":
                columns.append({"name": "Participación (%)", "id": "Participación (%)"})
            elif col == "Riesgo":
                columns.append({"name": "🚨 Riesgo", "id": "Riesgo"})
            # Nota: La columna 'Capacidad_GWh_Internal' ha sido eliminada de las tablas jerárquicas
    logger.debug(f"Total de columnas creadas: {len(columns)}")
    return columns

def create_initial_embalse_table():
    """Crea la tabla inicial de embalses con la nueva columna"""
    try:
        logger.info("Creando tabla inicial de embalses...")
        
        # Obtener datos directamente usando fechas actuales
        df = get_embalses_capacidad()
        
        if df.empty:
            return dbc.Alert("No hay datos de embalses para mostrar.", color="warning")
        
        # Formatear datos (mantener la capacidad para cálculos internos)
        df_formatted = df.copy()
        
        if 'Volumen Útil (%)' in df.columns:
            # Solo formatear valores numéricos, no reformatear strings
            df_formatted['Volumen Útil (%)'] = df['Volumen Útil (%)'].apply(
                lambda x: x if isinstance(x, str) else (f"{x:.1f}%" if pd.notna(x) and isinstance(x, (int, float)) else "N/D")
            )
            logger.info("Columna 'Volumen Útil (%)' formateada en tabla inicial")
        
        # Calcular totales para la fila TOTAL (usando los datos originales)
        total_capacity = df['Capacidad_GWh_Internal'].sum() if 'Capacidad_GWh_Internal' in df.columns else 0
        total_row_data = {
            'Embalse': ['TOTAL']
        }
        
        if 'Volumen Útil (%)' in df.columns:
            valid_data = df[df['Volumen Útil (%)'].notna()]
            avg_volume_pct = valid_data['Volumen Útil (%)'].mean() if not valid_data.empty else None
            total_row_data['Volumen Útil (%)'] = [f"{avg_volume_pct:.1f}%" if avg_volume_pct is not None else "N/D"]
        
        total_row = pd.DataFrame(total_row_data)
        
        # Crear DataFrame para mostrar (sin columna de capacidad)
        display_columns = ['Embalse']
        if 'Volumen Útil (%)' in df_formatted.columns:
            display_columns.append('Volumen Útil (%)')
        
        df_display = df_formatted[display_columns].copy()
        df_display = pd.concat([df_display, total_row], ignore_index=True)
        
        # 🆕 AGREGAR COLUMNA DE RIESGO CON PICTOGRAMAS
        df_display_con_riesgo = agregar_columna_riesgo_a_tabla(df.copy())  # Usar df original con capacidad
        
        # Crear DataFrame final para mostrar solo con las columnas necesarias + riesgo
        final_columns = ['Embalse']
        if 'Volumen Útil (%)' in df_display_con_riesgo.columns:
            # Formatear volumen útil para mostrar
            df_display_con_riesgo['Volumen Útil (%)'] = df_display_con_riesgo['Volumen Útil (%)'].apply(
                lambda x: f"{x:.1f}%" if pd.notna(x) and x != 'N/D' and not isinstance(x, str) else (x if isinstance(x, str) else "N/D")
            )
            final_columns.append('Volumen Útil (%)')
        final_columns.append('Riesgo')
        
        # Agregar fila TOTAL con riesgo
        total_row_riesgo = {
            'Embalse': 'TOTAL',
            'Volumen Útil (%)': total_row_data['Volumen Útil (%)'][0] if 'Volumen Útil (%)' in total_row_data else 'N/D',
            'Riesgo': '⚡'
        }
        
        # Filtrar solo embalses (sin TOTAL) y agregar TOTAL al final
        df_embalses_only = df_display_con_riesgo[df_display_con_riesgo['Embalse'] != 'TOTAL'][final_columns].copy()
        df_total_row = pd.DataFrame([total_row_riesgo])
        df_final_display = pd.concat([df_embalses_only, df_total_row], ignore_index=True)
        
        
        return create_dynamic_embalse_table(df_final_display)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return dbc.Alert(f"Error: {str(e)}", color="danger")

def create_dynamic_embalse_table(df_formatted):
    """Crea una tabla de embalses dinámicamente con todas las columnas disponibles"""
    logger.debug(f"INICIO create_dynamic_embalse_table - DataFrame: {df_formatted.shape if not df_formatted.empty else 'VACÍO'}")
    
    if df_formatted.empty:
        logger.warning("DataFrame vacío - retornando alerta")
        return dbc.Alert("No hay datos de embalses para mostrar.", color="warning")
    
    logger.debug(f"Creando tabla dinámica de embalses con {len(df_formatted)} filas y columnas: {list(df_formatted.columns)}")
    
    # Crear columnas dinámicamente
    columns = create_embalse_table_columns(df_formatted)
    logger.debug(f"Columnas creadas: {len(columns)}")
    
    # 🆕 Generar estilos condicionales basados en riesgo
    estilos_condicionales = []
    if 'Riesgo' in df_formatted.columns:
        estilos_condicionales = generar_estilos_condicionales_riesgo(df_formatted)
        logger.debug(f"Estilos condicionales de riesgo generados: {len(estilos_condicionales)}")
    else:
        # Estilo básico para TOTAL si no hay columna de riesgo
        estilos_condicionales = [
            {
                'if': {'filter_query': '{Embalse} = "TOTAL"'},
                'backgroundColor': '#007bff',
                'color': 'white',
                'fontWeight': 'bold'
            }
        ]
    
    # Crear la tabla
    table = dash_table.DataTable(
        id="tabla-capacidad-embalse",
        data=df_formatted.to_dict('records'),
        columns=columns,
        style_cell={'textAlign': 'left', 'padding': '6px', 'fontFamily': 'Arial', 'fontSize': 14},
        style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold'},
        style_data={'backgroundColor': '#f8f8f8'},
        style_data_conditional=estilos_condicionales,
        page_action="none"
    )
    
    return table
    
def create_data_table(data):
    """Tabla paginada de datos de energía con participación porcentual y total integrado"""
    if data is None or data.empty:
        return dbc.Alert("No hay datos para mostrar en la tabla.", color="warning")
    
    # Crear una copia del dataframe para modificar
    df_with_participation = data.copy()
    
    # Formatear fechas si existe columna de fecha
    date_columns = [col for col in df_with_participation.columns if 'fecha' in col.lower() or 'date' in col.lower()]
    for col in date_columns:
        df_with_participation[col] = df_with_participation[col].apply(format_date)
    
    # Si tiene columna 'GWh', calcular participación
    total_value = 0
    num_registros = len(df_with_participation)
    if 'GWh' in df_with_participation.columns:
        # Filtrar filas que no sean TOTAL para calcular el porcentaje
        df_no_total = df_with_participation[df_with_participation['GWh'] != 'TOTAL'].copy()
        if not df_no_total.empty:
            # Asegurar que los valores son numéricos
            df_no_total['GWh'] = pd.to_numeric(df_no_total['GWh'], errors='coerce')
            total_value = df_no_total['GWh'].sum()
            
            if total_value > 0:
                # Calcular porcentajes
                porcentajes = (df_no_total['GWh'] / total_value * 100).round(2)
                
                # Ajustar para que sume exactamente 100%
                diferencia = 100 - porcentajes.sum()
                if abs(diferencia) > 0.001 and len(porcentajes) > 0:
                    idx_max = porcentajes.idxmax()
                    porcentajes.loc[idx_max] += diferencia
                
                # Agregar la columna de participación
                df_with_participation.loc[df_no_total.index, 'Participación (%)'] = porcentajes.round(2)
            else:
                df_with_participation['Participación (%)'] = 0
        else:
            df_with_participation['Participación (%)'] = 0
    
    # Formatear columnas numéricas (GWh, capacidades, etc.)
    numeric_columns = [col for col in df_with_participation.columns 
                      if any(keyword in col.lower() for keyword in ['gwh', 'capacidad', 'energia', 'valor', 'value'])]
    
    for col in numeric_columns:
        if col != 'Participación (%)':  # No formatear porcentajes
            df_with_participation[col] = df_with_participation[col].apply(
                lambda x: format_number(x) if pd.notnull(x) and x != 'TOTAL' else x
            )
    
    # Agregar fila de TOTAL al final del DataFrame
    total_row = {}
    for col in df_with_participation.columns:
        if 'fecha' in col.lower() or 'date' in col.lower():
            total_row[col] = f"📊 TOTAL ({num_registros} registros)"
        elif col == 'GWh':
            total_row[col] = format_number(total_value)
        elif col == 'Participación (%)':
            total_row[col] = '100.00'
        else:
            total_row[col] = ''
    
    df_with_participation = pd.concat([df_with_participation, pd.DataFrame([total_row])], ignore_index=True)
    
    # Crear tabla paginada con total integrado
    return dash_table.DataTable(
        data=df_with_participation.to_dict('records'),
        columns=[{"name": i, "id": i} for i in df_with_participation.columns],
        style_cell={
            'textAlign': 'left', 
            'padding': '4px 8px',  # Reducido verticalmente
            'fontFamily': 'Inter, Arial, sans-serif', 
            'fontSize': '12px',  # Reducido de 13px a 12px
            'whiteSpace': 'normal',
            'height': 'auto'
        },
        style_header={
            'backgroundColor': '#2c3e50', 
            'fontWeight': 'bold',
            'color': 'white',
            'border': '1px solid #34495e',
            'fontSize': '11px',  # Encabezado más pequeño
            'padding': '6px 8px'  # Padding reducido en header
        },
        style_data={
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #dee2e6'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#ffffff'
            },
            {
                # Estilo especial para la fila de TOTAL (última fila)
                'if': {'row_index': len(df_with_participation) - 1},
                'backgroundColor': '#e3f2fd',
                'fontWeight': 'bold',
                'borderTop': '3px solid #007bff',
                'borderBottom': '3px solid #007bff',
                'color': '#0056b3'
            }
        ],
        page_size=8,  # Mostrar 8 filas por página
        page_action='native',  # Paginación nativa
        page_current=0,
        style_table={
            'maxHeight': '400px',
            'overflowY': 'auto',
            'overflowX': 'auto'
        }
    )

def create_line_chart(data, rio_name=None, start_date=None, end_date=None):
    """Gráfico de líneas moderno de energía con media histórica"""
    if data is None or data.empty:
        return dbc.Alert("No se pueden crear gráficos con estos datos.", color="warning", className="alert-modern")
    
    # Buscar columnas de fecha y valor (pueden tener nombres diferentes)
    date_col = None
    value_col = None
    
    # Detectar columna de fecha
    for col in data.columns:
        if any(keyword in col.lower() for keyword in ['fecha', 'date']):
            date_col = col
            break
    
    # Detectar columna de valor
    for col in data.columns:
        if any(keyword in col.lower() for keyword in ['energia', 'value', 'gwh']):
            value_col = col
            break
    
    if date_col and value_col:
        # Determinar la etiqueta del eje Y basada en el nombre de la columna
        if 'gwh' in value_col.lower() or 'energia' in value_col.lower():
            y_label = "Energía (GWh)"
        else:
            y_label = value_col
        
        # Crear figura base con plotly graph objects
        px, go = get_plotly_modules()
        fig = go.Figure()
        
        # Agregar línea de valores reales (negra para consistencia)
        fig.add_trace(go.Scatter(
            x=data[date_col],
            y=data[value_col],
            mode='lines+markers',
            name='Aportes Reales',
            line=dict(width=1.5, color='black'),
            marker=dict(size=4, color='black', line=dict(width=0.8, color='white')),
            hovertemplate=f'<b>Fecha:</b> %{{x}}<br><b>{y_label}:</b> %{{y:.2f}}<extra></extra>'
        ))
        
        # Obtener media histórica si tenemos nombre de río y fechas
        tiene_media = False
        if rio_name and start_date and end_date:
            try:
                # Convertir fechas a string si es necesario
                if hasattr(start_date, 'strftime'):
                    fecha_inicio_str = start_date.strftime('%Y-%m-%d')
                else:
                    fecha_inicio_str = str(start_date)
                
                if hasattr(end_date, 'strftime'):
                    fecha_fin_str = end_date.strftime('%Y-%m-%d')
                else:
                    fecha_fin_str = str(end_date)
                
                # Obtener media histórica
                media_hist_data, _ = obtener_datos_inteligente('AporEnerMediHist', 'Rio', fecha_inicio_str, fecha_fin_str)
                
                if media_hist_data is not None and not media_hist_data.empty:
                    # Filtrar por el río específico
                    media_hist_rio = media_hist_data[media_hist_data['Name'] == rio_name]
                    
                    if not media_hist_rio.empty and 'Value' in media_hist_rio.columns:
                        # ⚠️ NO convertir - fetch_metric_data YA convierte a GWh automáticamente
                        
                        # Combinar datos reales e históricos para colorear según estado
                        # Necesitamos preparar los datos reales en formato adecuado
                        datos_reales = data[[date_col, value_col]].copy()
                        datos_reales.columns = ['Date', 'Value_real']
                        datos_reales['Date'] = pd.to_datetime(datos_reales['Date'])
                        
                        media_hist_rio['Date'] = pd.to_datetime(media_hist_rio['Date'])
                        
                        # Merge para comparación
                        merged_data = datos_reales.merge(
                            media_hist_rio[['Date', 'Value']], 
                            on='Date', 
                            how='inner'
                        )
                        merged_data.rename(columns={'Value': 'Value_hist'}, inplace=True)
                        
                        if not merged_data.empty:
                            # Calcular porcentaje
                            merged_data['porcentaje'] = (merged_data['Value_real'] / merged_data['Value_hist']) * 100
                            
                            # Agregar línea histórica con colores dinámicos
                            for i in range(len(merged_data) - 1):
                                # ✅ FIX: Convertir a float antes de usar en formato
                                porcentaje = float(merged_data.iloc[i]['porcentaje'])
                                
                                # Determinar color según porcentaje
                                if porcentaje >= 100:
                                    color = '#28a745'  # Verde - Húmedo
                                    estado = 'Húmedo'
                                elif porcentaje >= 90:
                                    color = '#17a2b8'  # Cyan - Normal
                                    estado = 'Normal'
                                elif porcentaje >= 70:
                                    color = '#ffc107'  # Amarillo - Moderadamente seco
                                    estado = 'Moderadamente seco'
                                else:
                                    color = '#dc3545'  # Rojo - Muy seco
                                    estado = 'Muy seco'
                                
                                # Agregar segmento de línea
                                fig.add_trace(go.Scatter(
                                    x=merged_data['Date'].iloc[i:i+2],
                                    y=merged_data['Value_hist'].iloc[i:i+2],
                                    mode='lines',
                                    name='Media Histórica' if i == 0 else None,
                                    showlegend=(i == 0),
                                    line=dict(width=3, color=color, dash='dash'),
                                    hovertemplate=f'<b>Fecha:</b> %{{x}}<br><b>Media Histórica:</b> %{{y:.2f}} GWh<br><b>Estado:</b> {estado} ({porcentaje:.1f}%)<extra></extra>',
                                    legendgroup='media_historica'
                                ))
                            tiene_media = True
                        else:
                            # Fallback: línea azul simple si no hay datos para comparar
                            fig.add_trace(go.Scatter(
                                x=media_hist_rio['Date'],
                                y=media_hist_rio['Value'],
                                mode='lines',
                                name='Media Histórica',
                                line=dict(width=3, color='#1e90ff', dash='dash'),
                                hovertemplate=f'<b>Fecha:</b> %{{x}}<br><b>Media Histórica:</b> %{{y:.2f}} GWh<extra></extra>'
                            ))
                            tiene_media = True
            except Exception as e:
                logger.warning(f"No se pudo obtener media histórica para río {rio_name}: {e}")
        
        # Aplicar tema moderno
        fig.update_layout(
            height=325,  # Reducido para compensar eliminación de zoom
            margin=dict(l=50, r=20, t=40, b=50),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Inter, Arial, sans-serif", size=12),
            title_font_size=16,
            xaxis=dict(
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128,128,128,0.2)',
                showline=True,
                linewidth=2,
                linecolor='rgba(128,128,128,0.3)',
                title="Fecha"
            ),
            yaxis=dict(
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128,128,128,0.2)',
                showline=True,
                linewidth=2,
                linecolor='rgba(128,128,128,0.3)',
                title=y_label
            ),
            showlegend=tiene_media,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        # ✅ Eliminar CardHeader - solo retornar el gráfico
        return dcc.Graph(figure=fig)
    else:
        return dbc.Alert("No se pueden crear gráficos con estos datos.", color="warning", className="alert-modern")

def create_bar_chart(data, metric_name):
    """Crear gráfico de líneas moderno por región o río"""
    # Detectar columnas categóricas y numéricas
    cat_cols = [col for col in data.columns if data[col].dtype == 'object']
    num_cols = [col for col in data.columns if data[col].dtype in ['float64', 'int64']]
    
    if not cat_cols or not num_cols:
        return dbc.Alert("No se pueden crear gráficos de líneas con estos datos.", 
                        color="warning", className="alert-modern")
    
    cat_col = cat_cols[0]
    num_col = num_cols[0]
    
    # Si los datos tienen información de región, crear líneas por región
    if 'Region' in data.columns:
        # Agrupar por región y fecha para crear series temporales por región
        if 'Date' in data.columns:
            # Datos diarios por región - series temporales
            fig = px.line(
                data,
                x='Date',
                y='Value', 
                color='Region',
                title="Aportes Energéticos por Región Hidrológica",
                labels={'Value': "Energía (GWh)", 'Date': "Fecha", 'Region': "Región"},
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            # Asegurar que cada línea tenga información de región para el click
            fig.for_each_trace(lambda t: t.update(legendgroup=t.name, customdata=[t.name] * len(t.x)))
        else:
            # Datos agregados por región - convertir a líneas también
            region_data = data.groupby('Region')[num_col].sum().reset_index()
            region_data = region_data.sort_values(by=num_col, ascending=False)
            
            fig = px.line(
                region_data,
                x='Region',
                y=num_col,
                title="Contribución Total por Región Hidrológica",
                labels={num_col: "Energía (GWh)", 'Region': "Región"},
                markers=True,
                color_discrete_sequence=['#667eea']
            )
    else:
        # Agrupar y ordenar datos de mayor a menor - usar líneas en lugar de barras
        grouped_data = data.groupby(cat_col)[num_col].sum().reset_index()
        grouped_data = grouped_data.sort_values(by=num_col, ascending=False)
        
        fig = px.line(
            grouped_data.head(15),  # Top 15 para mejor visualización
            x=cat_col,
            y=num_col,
            title="Aportes Energéticos por Río",
            labels={num_col: "Energía (GWh)", cat_col: "Río"},
            markers=True,
            color_discrete_sequence=['#667eea']
        )
    
    # Aplicar estilo moderno
    fig.update_layout(
        height=360,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter, Arial, sans-serif", size=12),
        title=dict(
            font_size=16,
            x=0.5,
            xanchor='center',
            font_color='#2d3748'
        ),
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.2)',
            showline=True,
            linewidth=2,
            linecolor='rgba(128,128,128,0.3)',
            tickangle=-45
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.2)',
            showline=True,
            linewidth=2,
            linecolor='rgba(128,128,128,0.3)'
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Mejorar el estilo para todos los gráficos de líneas
    fig.update_traces(
        marker=dict(size=10, line=dict(width=2, color='white')),
        line=dict(width=4),
        hovertemplate='<b>%{fullData.name}</b><br>Valor: %{y:.2f} GWh<extra></extra>'
    )
    
    chart_title = "Aportes de Energía por Región" if 'Region' in data.columns else "Aportes de Energía por Río"
    
    return dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="bi bi-graph-up me-2", style={"color": "#667eea"}),
                html.Strong(chart_title, style={"fontSize": "1.2rem"})
            ], className="d-flex align-items-center"),
            html.Small("Haz clic en cualquier punto para ver detalles", className="text-muted")
        ]),
        dbc.CardBody([
            dcc.Graph(id="rio-detail-graph", figure=fig, clear_on_unhover=True)
        ], className="p-2")
    ], className="card-modern chart-container shadow-lg")

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

def get_porcapor_data(fecha_inicio, fecha_fin):
    """Obtener datos de la métrica PorcApor - Aportes % por río"""
    try:
        objetoAPI = get_objetoAPI()
        data, warning = obtener_datos_inteligente('PorcApor', 'Rio', fecha_inicio, fecha_fin)
        if not data.empty:
            # Multiplicar por 100 para convertir a porcentaje
            if 'Value' in data.columns:
                data['Value'] = data['Value'] * 100
            return data
        else:
            logger.warning("No se encontraron datos de PorcApor")
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

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

def agregar_datos_hidrologia_inteligente(df_hidrologia, dias_periodo):
    """
    Agrupa los datos de hidrología según el período para optimizar rendimiento:
    - <= 60 días: datos diarios (sin cambios, máxima granularidad)
    - 61-180 días: datos semanales (reduce ~7x puntos)
    - > 180 días: datos mensuales (reduce ~30x puntos)
    
    IMPORTANTE: Mantiene el coloreado dinámico en todos los rangos,
    solo reduce la cantidad de puntos a renderizar.
    """
    if df_hidrologia.empty:
        return df_hidrologia
    
    # Asegurar que Date sea datetime
    df_hidrologia['Date'] = pd.to_datetime(df_hidrologia['Date'])
    
    # Determinar nivel de agregación
    if dias_periodo <= 60:
        # Datos diarios - no cambiar (máxima granularidad)
        logger.info(f"📊 Sin agregación: {dias_periodo} días (≤60) - Datos diarios")
        return df_hidrologia
    elif dias_periodo <= 180:
        # Agrupar por semana
        df_hidrologia['Periodo'] = df_hidrologia['Date'].dt.to_period('W').dt.start_time
        periodo_label = 'Semana'
        logger.info(f"📊 Agrupación SEMANAL: {dias_periodo} días → ~{dias_periodo//7} semanas")
    else:
        # Agrupar por mes
        df_hidrologia['Periodo'] = df_hidrologia['Date'].dt.to_period('M').dt.start_time
        periodo_label = 'Mes'
        logger.info(f"📊 Agrupación MENSUAL: {dias_periodo} días → ~{dias_periodo//30} meses")
    
    # Agregar datos (promediar Value)
    columnas_grupo = ['Periodo']
    
    # Detectar si hay columnas adicionales que mantener
    if 'Name' in df_hidrologia.columns:
        columnas_grupo.append('Name')
    if 'Region' in df_hidrologia.columns:
        columnas_grupo.append('Region')
    
    # Agrupar y promediar valores (para hidrología usamos promedio, no suma)
    df_agregado = df_hidrologia.groupby(columnas_grupo, as_index=False).agg({
        'Value': 'mean'  # Promedio de aportes en el período
    })
    
    # Renombrar Periodo a Date
    df_agregado.rename(columns={'Periodo': 'Date'}, inplace=True)
    
    logger.info(f"✅ Datos agregados: {len(df_hidrologia)} registros → {len(df_agregado)} {periodo_label}s (reducción {100*(1-len(df_agregado)/len(df_hidrologia)):.1f}%)")
    
    return df_agregado

def create_total_timeline_chart(data, metric_name, region_filter=None, rio_filter=None):
    """
    Crear gráfico de línea temporal con total nacional/regional/río por día incluyendo media histórica filtrada
    """
    if data is None or data.empty:
        return dbc.Alert("No se pueden crear gráficos con estos datos.", 
                        color="warning", className="alert-modern")
    
    # Verificar que tengamos las columnas necesarias
    if 'Date' not in data.columns or 'Value' not in data.columns:
        return dbc.Alert("No se encuentran las columnas necesarias (Date, Value).", 
                        color="warning", className="alert-modern")
    
    # LOGGING: Ver qué datos recibimos ANTES de agrupar
    try:
        logger.info(f"🔍 create_total_timeline_chart recibió {len(data)} registros")
        logger.info(f"🔍 Columnas: {list(data.columns)}")
        logger.info(f"🔍 Fechas únicas: {data['Date'].nunique()}")
        logger.info(f"🔍 Suma total de Value ANTES de agrupar: {data['Value'].sum():.2f} GWh")
    except Exception as log_error:
        logger.warning(f"⚠️ Error en logging: {log_error}")
    
    # Agrupar por fecha y sumar todos los valores
    daily_totals = data.groupby('Date')['Value'].sum().reset_index()
    daily_totals = daily_totals.sort_values('Date')
    
    logger.info(f"🔍 DESPUÉS de agrupar: {len(daily_totals)} fechas, Total: {daily_totals['Value'].sum():.2f} GWh")
    
    # Obtener media histórica y calcular indicador
    tiene_media = False  # ✅ Inicializar antes del try
    media_hist_totals = None  # ✅ Inicializar para evitar NameError fuera del try
    porcentaje_vs_historico = None
    promedio_real = None
    promedio_historico = None
    
    try:
        # ✅ FIX ERROR #2: Convertir a string de forma segura (puede ser datetime o string)
        fecha_min = daily_totals['Date'].min()
        fecha_max = daily_totals['Date'].max()
        
        if hasattr(fecha_min, 'strftime'):
            fecha_inicio = fecha_min.strftime('%Y-%m-%d')
        else:
            fecha_inicio = str(fecha_min)
            
        if hasattr(fecha_max, 'strftime'):
            fecha_fin = fecha_max.strftime('%Y-%m-%d')
        else:
            fecha_fin = str(fecha_max)  # ✅ FIX: usar fecha_max, NO fecha_fin
        
        # Obtener datos de media histórica de energía por río
        media_hist_data, warning_msg = obtener_datos_inteligente('AporEnerMediHist', 'Rio', fecha_inicio, fecha_fin)
        if warning_msg:
            logger.info(f"✅ Usando media_hist_data recibida como parámetro (sin query duplicado)")
        
        logger.debug(f"Datos recibidos de AporEnerMediHist: {len(media_hist_data) if media_hist_data is not None else 0} registros")
        if media_hist_data is not None and not media_hist_data.empty:
            logger.debug(f"Columnas disponibles: {media_hist_data.columns.tolist()}")
            logger.debug(f"Primeras 3 filas completas:")
# print(media_hist_data.head(3))
            logger.debug(f"Valores de muestra ANTES de conversión: {media_hist_data['Value'].head(3).tolist()}")
            logger.debug(f"Rango de valores: min={media_hist_data['Value'].min()}, max={media_hist_data['Value'].max()}")
            logger.debug(f"Nombres de ríos únicos: {media_hist_data['Name'].unique()[:5].tolist() if 'Name' in media_hist_data.columns else 'Sin columna Name'}")
        
        if media_hist_data is not None and not media_hist_data.empty and 'Value' in media_hist_data.columns:
            # ✅ La conversión kWh→GWh ahora se hace automáticamente en fetch_metric_data()
            # Los valores ya vienen en GWh desde el cache
            valor_promedio = media_hist_data['Value'].mean()
            logger.debug(f"AporEnerMediHist promedio: {valor_promedio:.2f} GWh")
            logger.debug(f"Valores de muestra: {media_hist_data['Value'].head(3).tolist()}")
            
            # ✅ FIX: Filtrar registros con Name NULL ANTES de intentar mapear regiones
            if 'Name' in media_hist_data.columns:
                registros_antes = len(media_hist_data)
                media_hist_data = media_hist_data[media_hist_data['Name'].notna()]
                registros_despues = len(media_hist_data)
                if registros_antes != registros_despues:
                    logger.info(f"🔍 Filtrados {registros_antes - registros_despues} registros con Name=NULL (quedan {registros_despues})")
            
            # FILTRAR por región o río si se especifica
            if region_filter:
                # Agregar mapeo de región
                rio_region = ensure_rio_region_loaded()
                # ✅ NORMALIZAR usando función unificada
                media_hist_data['Name_Upper'] = normalizar_codigo(media_hist_data['Name'])
                media_hist_data['Region'] = media_hist_data['Name_Upper'].map(rio_region)
                
                # ✅ FIX ERROR #3: UPPER para coincidir con normalizar_region()
                region_filter_normalized = region_filter.strip().upper() if isinstance(region_filter, str) else region_filter
                
                # Filtrar por región
                antes_filtro = len(media_hist_data)
                logger.info(f"🔍 ANTES filtro región '{region_filter}' (normalizado: '{region_filter_normalized}'): {antes_filtro} registros")
                logger.info(f"🔍 Regiones disponibles: {sorted(media_hist_data['Region'].dropna().unique())}")
                media_hist_data = media_hist_data[media_hist_data['Region'] == region_filter_normalized]
                logger.info(f"🔍 DESPUÉS filtro región '{region_filter_normalized}': {len(media_hist_data)} registros")
                if media_hist_data.empty:
                    logger.error(f"❌ ERROR: No hay datos históricos después del filtro para región '{region_filter_normalized}'")
                    logger.error(f"   Regiones disponibles eran: {sorted(media_hist_data['Region'].dropna().unique()) if 'Region' in media_hist_data.columns else 'N/A'}")
            elif rio_filter:
                # Filtrar por río específico
                antes_filtro = len(media_hist_data)
                media_hist_data = media_hist_data[media_hist_data['Name'] == rio_filter]
                logger.debug(f"Media histórica filtrada por río '{rio_filter}': {antes_filtro} → {len(media_hist_data)} registros")
            
            # Agrupar por fecha y sumar
            if not media_hist_data.empty:
                media_hist_totals = media_hist_data.groupby('Date')['Value'].sum().reset_index()
                media_hist_totals = media_hist_totals.sort_values('Date')
                tiene_media = True
                
                logger.info(f"✅ Media histórica agregada por fecha: {len(media_hist_totals)} días")
                logger.info(f"✅ tiene_media = {tiene_media} - LA LÍNEA DEBERÍA APARECER")
                logger.debug(f"Valores agregados de muestra: {media_hist_totals['Value'].head(3).tolist()}")
                logger.debug(f"Total agregado: min={media_hist_totals['Value'].min():.2f}, max={media_hist_totals['Value'].max():.2f}, suma={media_hist_totals['Value'].sum():.2f} GWh")
                
                # CORRECCIÓN: Calcular porcentaje con SUMA TOTAL del período (no promedio)
                total_real = daily_totals['Value'].sum()  # SUMA TOTAL
                total_historico = media_hist_totals['Value'].sum()  # SUMA TOTAL
                
                # ✅ FIX: Convertir a float explícitamente para evitar error de formato
                total_real = float(total_real)
                total_historico = float(total_historico)
                
                logger.info(f"📊 CÁLCULO PORCENTAJE: Real={total_real:.2f} GWh, Histórico={total_historico:.2f} GWh")
                
                if total_historico > 0:
                    # ✅ FIX CRÍTICO: Convertir a float Python nativo inmediatamente
                    porcentaje_vs_historico = float((total_real / total_historico) * 100)
                    logger.info(f"✅ Porcentaje calculado: {porcentaje_vs_historico:.1f}%")
                else:
                    logger.error(f"❌ ERROR: total_historico = 0, no se puede calcular porcentaje")
                    porcentaje_vs_historico = None
            else:
                tiene_media = False
                logger.warning(f"No hay datos después del filtrado")
        else:
            tiene_media = False
            logger.warning(f"No se recibieron datos válidos de AporEnerMediHist")
    except Exception as e:
        logger.error(f"❌ ERROR obteniendo media histórica: {e}")
        logger.error(f"   Tipo de error: {type(e).__name__}")
        logger.error(f"   Detalles: {str(e)}")
        import traceback
        traceback.print_exc()
        tiene_media = False
        # Mostrar mensaje más visible en consola
# print(f"\n⚠️ ADVERTENCIA: No se pudo cargar línea de media histórica")
# print(f"   Razón: {str(e)}")
# print(f"   La gráfica se mostrará solo con datos reales\n")
    
    # Crear figura base
    from plotly.subplots import make_subplots
    px, go = get_plotly_modules()
    
    fig = go.Figure()
    
    # Agregar línea de valores reales (negra) - optimizada para mejor visualización
    fig.add_trace(go.Scatter(
        x=daily_totals['Date'],
        y=daily_totals['Value'],
        mode='lines+markers',
        name='Aportes Reales',
        line=dict(width=1.5, color='black'),
        marker=dict(size=4, color='black', line=dict(width=0.8, color='white')),
        hovertemplate=(
            '<b>📅 Fecha:</b> %{x|%d/%m/%Y}<br>'
            '<b>⚡ Aportes Reales:</b> %{y:.2f} GWh<br>'
            '<b>━━━━━━━━━━━━━━━━</b><br>'
            '<i>Pasa el cursor sobre la línea histórica<br>para ver la comparación detallada</i>'
            '<extra></extra>'
        )
    ))
    
    # Agregar línea de media histórica con colores dinámicos según estado hidrológico
    logger.info(f"🎨 DIBUJANDO GRÁFICA: tiene_media={tiene_media}, media_hist_totals={'EXISTE' if media_hist_totals is not None else 'NULL'}")
    if tiene_media and media_hist_totals is not None:
        logger.info(f"✅ INICIANDO DIBUJO de línea de media histórica con {len(media_hist_totals)} puntos")
        # Combinar datos reales e históricos por fecha para comparación
        merged_data = daily_totals.merge(
            media_hist_totals, 
            on='Date', 
            how='inner', 
            suffixes=('_real', '_hist')
        )
        logger.info(f"🔗 Datos combinados: {len(merged_data)} fechas coincidentes")
        
        if not merged_data.empty:
            # Calcular porcentaje: (real / histórico) * 100
            merged_data['porcentaje'] = (merged_data['Value_real'] / merged_data['Value_hist']) * 100
            
            # ✅ COLOREADO DINÁMICO COMPLETO (restaurado)
            # Verde: > 100% (húmedo), Cyan: 90-100% (normal), Naranja: 70-90% (seco moderado), Rojo: < 70% (muy seco)
            logger.info(f"✅ Usando COLOREADO DINÁMICO para {len(merged_data)} puntos")
            
            for i in range(len(merged_data) - 1):
                    # ✅ FIX: Convertir a float explícitamente para evitar errores de formato
                    porcentaje = float(merged_data.iloc[i]['porcentaje'])
                    valor_real = float(merged_data.iloc[i]['Value_real'])
                    valor_hist = float(merged_data.iloc[i]['Value_hist'])
                    
                    # Calcular variación porcentual (formato estándar)
                    variacion = float(porcentaje - 100)
                    signo = '+' if variacion >= 0 else ''
                    
                    # Determinar color según porcentaje
                    if porcentaje >= 100:
                        color = '#28a745'  # Verde - Húmedo
                        estado = 'Húmedo'
                        emoji = '💧'
                    elif porcentaje >= 90:
                        color = '#17a2b8'  # Cyan - Normal
                        estado = 'Normal'
                        emoji = '✓'
                    elif porcentaje >= 70:
                        color = '#ffc107'  # Amarillo/Naranja - Moderadamente seco
                        estado = 'Moderadamente seco'
                        emoji = '⚠️'
                    else:
                        color = '#dc3545'  # Rojo - Muy seco
                        estado = 'Muy seco'
                        emoji = '🔴'
                    
                    # Tooltip mejorado con formato estándar de variación porcentual
                    hover_text = (
                        f'<b>📅 Fecha:</b> %{{x|%d/%m/%Y}}<br>'
                        f'<b>📊 Media Histórica:</b> %{{y:.2f}} GWh<br>'
                        f'<b>⚡ Aportes Reales:</b> {valor_real:.2f} GWh<br>'
                        f'<b>━━━━━━━━━━━━━━━━</b><br>'
                        f'<b>{emoji} Estado:</b> {estado}<br>'
                        f'<b>📈 Variación:</b> {signo}{variacion:.1f}% vs histórico<br>'
                        f'<b>📐 Fórmula:</b> ({valor_real:.1f} / {valor_hist:.1f}) × 100 = {porcentaje:.1f}%<br>'
                        f'<b>🧮 Diferencia:</b> {porcentaje:.1f}% - 100% = {signo}{variacion:.1f}%'
                        f'<extra></extra>'
                    )
                    
                    # Agregar segmento de línea
                    fig.add_trace(go.Scatter(
                        x=merged_data['Date'].iloc[i:i+2],
                        y=merged_data['Value_hist'].iloc[i:i+2],
                        mode='lines',
                        name='Media Histórica' if i == 0 else None,  # Solo mostrar leyenda una vez
                        showlegend=(i == 0),
                        line=dict(width=3, color=color, dash='dash'),
                        hovertemplate=hover_text,
                        legendgroup='media_historica'
                    ))
        else:
            # Fallback: línea azul simple si no hay datos para comparar
            fig.add_trace(go.Scatter(
                x=media_hist_totals['Date'],
                y=media_hist_totals['Value'],
                mode='lines',
                name='Media Histórica',
                line=dict(width=3, color='#1e90ff', dash='dash'),
                hovertemplate='<b>Fecha:</b> %{x}<br><b>Media Histórica:</b> %{y:.2f} GWh<extra></extra>'
            ))
    else:
        logger.warning(f"⚠️ NO SE DIBUJÓ línea de media histórica: tiene_media={tiene_media}, media_hist_totals={'None' if media_hist_totals is None else f'{len(media_hist_totals)} registros'}")
    
    # Determinar título dinámico según filtros
    if rio_filter:
        titulo_grafica = f"Aportes de Energía - Río {rio_filter}"
    elif region_filter:
        titulo_grafica = f"Aportes de Energía - Región {region_filter}"
    else:
        titulo_grafica = "Total Nacional de Aportes de Energía por Día"
    
    # Estilo moderno con márgenes optimizados
    fig.update_layout(
        height=500,
        margin=dict(l=50, r=20, t=60, b=50),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter, Arial, sans-serif", size=12),
        title=dict(
            text=titulo_grafica,
            font_size=16,
            x=0.5,
            xanchor='center',
            font_color='#2d3748'
        ),
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.2)',
            showline=True,
            linewidth=2,
            linecolor='rgba(128,128,128,0.3)',
            title="Fecha"
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.2)',
            showline=True,
            linewidth=2,
            linecolor='rgba(128,128,128,0.3)',
            title="Energía (GWh)"
        ),
        showlegend=tiene_media,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Crear indicador visual de comparación
    indicador_badge = None
    if porcentaje_vs_historico is not None:
        # ✅ FIX: Asegurar que porcentaje_vs_historico sea float
        try:
            porcentaje_vs_historico = float(porcentaje_vs_historico)
        except (ValueError, TypeError):
            logger.error(f"❌ No se pudo convertir porcentaje_vs_historico a float: {porcentaje_vs_historico}")
            porcentaje_vs_historico = None
    
    if porcentaje_vs_historico is not None:
        # Determinar color y emoji según el porcentaje
        if porcentaje_vs_historico >= 100:
            # Por encima del histórico (húmedo)
            color_badge = "success"
            icono = "💧"
            diferencia = float(porcentaje_vs_historico - 100)
            texto_badge = f"{icono} +{diferencia:.1f}% vs Histórico"
            texto_contexto = "Condiciones más húmedas que el promedio histórico"
        elif porcentaje_vs_historico >= 90:
            # Cerca del histórico (normal)
            color_badge = "info"
            icono = "✓"
            diferencia = float(100 - porcentaje_vs_historico)
            texto_badge = f"{icono} -{diferencia:.1f}% vs Histórico"
            texto_contexto = "Condiciones cercanas al promedio histórico"
        elif porcentaje_vs_historico >= 70:
            # Moderadamente bajo (alerta)
            color_badge = "warning"
            icono = "⚠️"
            diferencia = float(100 - porcentaje_vs_historico)
            texto_badge = f"{icono} -{diferencia:.1f}% vs Histórico"
            texto_contexto = "Condiciones más secas que el promedio histórico"
        else:
            # Muy bajo (crítico)
            color_badge = "danger"
            icono = "🔴"
            diferencia = float(100 - porcentaje_vs_historico)
            texto_badge = f"{icono} -{diferencia:.1f}% vs Histórico"
            texto_contexto = "Condiciones significativamente más secas que el histórico"
        
        indicador_badge = html.Div([
            dbc.Badge(
                texto_badge,
                color=color_badge,
                className="me-2",
                style={"fontSize": "0.9rem", "fontWeight": "600"}
            ),
            html.Small(texto_contexto, className="text-muted", style={"fontSize": "0.85rem"})
        ], className="d-flex align-items-center mt-2")
    
    # ✅ Header eliminado - solo retornar el gráfico sin card header
    return dcc.Graph(id="total-timeline-graph", figure=fig, clear_on_unhover=True)
# Callback para mostrar el modal con la tabla diaria al hacer click en un punto de la línea
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

def create_stats_summary(data):
    """Crear resumen estadístico"""
    numeric_data = data.select_dtypes(include=['float64', 'int64'])
    
    if numeric_data.empty:
        return dbc.Alert("No hay datos numéricos para análisis estadístico.", color="warning")
    
    stats = numeric_data.describe()
    
    return dbc.Card([
        dbc.CardHeader([
            html.H6([
                html.I(className="bi bi-calculator me-2"),
                "Resumen Estadístico"
            ], className="mb-0")
        ]),
        dbc.CardBody([
            dash_table.DataTable(
                data=stats.round(2).reset_index().to_dict('records'),
                columns=[{"name": i, "id": i} for i in stats.reset_index().columns],
                style_cell={
                    'textAlign': 'center',
                    'padding': '10px',
                    'fontFamily': 'Arial'
                },
                style_header={
                    'backgroundColor': '#3498db',
                    'color': 'white',
                    'fontWeight': 'bold'
                },
                style_data={'backgroundColor': '#f8f9fa'}
            )
        ])
    ], className="mt-3")

# === FUNCIONES PARA TABLAS FILTRADAS POR REGIÓN CON SEMÁFORO ===

def create_region_filtered_participacion_table(region, start_date, end_date):
    """
    Crea una tabla de participación porcentual filtrada por región específica,
    incluyendo el sistema de semáforo de riesgo.
    """
    try:
        
        # Obtener datos de embalses filtrados por región
        df_embalses = get_embalses_capacidad(region, start_date, end_date)
        
        if df_embalses.empty:
            return html.Div("No hay datos disponibles para esta región.", className="text-center text-muted")
        
        # Calcular participación porcentual
        df_participacion = get_participacion_embalses(df_embalses)
        
        # Crear datos para la tabla con semáforo
        table_data = []
        for _, row in df_participacion.iterrows():
            if row['Embalse'] == 'TOTAL':
                continue  # Saltamos el total para procesarlo al final
            
            embalse_name = row['Embalse']
            participacion_valor = row['Participación (%)']
            
            # Manejar tanto valores numéricos como strings con formato
            if isinstance(participacion_valor, str) and '%' in participacion_valor:
                participacion_num = float(participacion_valor.replace('%', ''))
                participacion_str = participacion_valor
            else:
                participacion_num = float(participacion_valor)
                participacion_str = f"{participacion_num:.2f}%"
            
            # Obtener volumen útil del embalse
            embalse_data = df_embalses[df_embalses['Embalse'] == embalse_name]
            volumen_util_raw = embalse_data['Volumen Útil (%)'].iloc[0] if not embalse_data.empty else 0
            
            # Convertir volumen_util a número (no reformatear si ya es string)
            if volumen_util_raw is None or (isinstance(volumen_util_raw, str) and volumen_util_raw == 'N/D'):
                volumen_util = 0
            elif isinstance(volumen_util_raw, str):
                # Si ya es string con %, extraer solo el número para cálculos de riesgo
                try:
                    volumen_util = float(volumen_util_raw.replace('%', '').replace(',', '.').strip())
                except (ValueError, AttributeError):
                    volumen_util = 0
            elif pd.isna(volumen_util_raw):
                volumen_util = 0
            else:
                volumen_util = float(volumen_util_raw)
            
            # Clasificar riesgo
            nivel_riesgo = clasificar_riesgo_embalse(participacion_num, volumen_util)
            estilo_riesgo = obtener_estilo_riesgo(nivel_riesgo)
            
            
            table_data.append({
                'Embalse': embalse_name,
                'Participación (%)': participacion_str,
                'Riesgo': "🔴" if nivel_riesgo == "high" else "🟡" if nivel_riesgo == "medium" else "🟢"
            })
        
        # Agregar fila TOTAL
        total_row = df_participacion[df_participacion['Embalse'] == 'TOTAL']
        if not total_row.empty:
            total_participacion = total_row['Participación (%)'].iloc[0]
            if isinstance(total_participacion, str) and '%' in total_participacion:
                total_str = total_participacion
            else:
                total_str = f"{float(total_participacion):.2f}%"
            
            table_data.append({
                'Embalse': 'TOTAL',
                'Participación (%)': total_str,
                'Riesgo': "⚡"  # Icono especial para el total
            })
        
        
        # Crear DataTable con semáforo
        return dash_table.DataTable(
            data=table_data,
            columns=[
                {"name": "Embalse", "id": "Embalse"},
                {"name": "Participación (%)", "id": "Participación (%)"},
                {"name": "🚦 Riesgo", "id": "Riesgo"}
            ],
            style_cell={'textAlign': 'left', 'padding': '8px', 'fontFamily': 'Inter, Arial', 'fontSize': 13},
            style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold'},
            style_data={'backgroundColor': '#f8f8f8'},
            style_data_conditional=[
                # Estilos de semáforo con pictogramas
                {
                    'if': {'filter_query': '{Riesgo} = 🔴'},
                    'backgroundColor': '#ffebee',
                    'color': '#c62828',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                {
                    'if': {'filter_query': '{Riesgo} = 🟡'},
                    'backgroundColor': '#fff8e1',
                    'color': '#f57c00',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                {
                    'if': {'filter_query': '{Riesgo} = 🟢'},
                    'backgroundColor': '#e8f5e8',
                    'color': '#2e7d32',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                # Estilo para fila TOTAL
                {
                    'if': {'filter_query': '{Embalse} = "TOTAL"'},
                    'backgroundColor': '#007bff',
                    'color': 'white',
                    'fontWeight': 'bold'
                }
            ],
            page_action="none",
            export_format="xlsx",
            export_headers="display"
        )
        
    except Exception as e:
        logger.error(f"❌ Error en create_region_filtered_participacion_table: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return html.Div(f"Error al cargar los datos: {str(e)}", className="text-center text-danger")

def create_region_filtered_capacidad_table(region, start_date, end_date):
    """
    Crea una tabla de capacidad útil filtrada por región específica,
    incluyendo el sistema de semáforo de riesgo.
    """
    try:
        # Obtener datos de embalses filtrados por región
        df_embalses = get_embalses_capacidad(region, start_date, end_date)
        
        if df_embalses.empty:
            return html.Div("No hay datos disponibles para esta región.", className="text-center text-muted")
        
        # Calcular participación para el semáforo
        df_participacion = get_participacion_embalses(df_embalses)
        
        # Crear datos para la tabla con semáforo
        table_data = []
        
        for _, row in df_embalses.iterrows():
            embalse_name = row['Embalse']
            capacidad = row['Capacidad_GWh_Internal']  # Solo para cálculos internos
            volumen_util_raw = row['Volumen Útil (%)']
            
            # Convertir volumen_util a número y preservar formato original si ya está formateado
            volumen_util_formatted = None
            if volumen_util_raw is None or (isinstance(volumen_util_raw, str) and volumen_util_raw == 'N/D'):
                volumen_util = 0
                volumen_util_formatted = "N/D"
            elif isinstance(volumen_util_raw, str):
                # Si ya es string, preservar formato original y extraer número
                try:
                    volumen_util = float(volumen_util_raw.replace('%', '').replace(',', '.').strip())
                    volumen_util_formatted = volumen_util_raw  # Usar formato original
                except (ValueError, AttributeError):
                    volumen_util = 0
                    volumen_util_formatted = "N/D"
            elif pd.isna(volumen_util_raw):
                volumen_util = 0
                volumen_util_formatted = "N/D"
            else:
                volumen_util = float(volumen_util_raw)
                volumen_util_formatted = None  # Formatear después
            
            # Obtener participación del embalse
            participacion_row = df_participacion[df_participacion['Embalse'] == embalse_name]
            participacion_num = 0
            if not participacion_row.empty:
                participacion_valor = participacion_row['Participación (%)'].iloc[0]
                # Manejar tanto valores numéricos como strings con formato
                if isinstance(participacion_valor, str) and '%' in participacion_valor:
                    participacion_num = float(participacion_valor.replace('%', ''))
                else:
                    participacion_num = float(participacion_valor)
            
            # Clasificar riesgo
            nivel_riesgo = clasificar_riesgo_embalse(participacion_num, volumen_util)
            
            
            # NO incluir la columna de capacidad GWh en la tabla
            table_data.append({
                'Embalse': embalse_name,
                'Volumen Útil (%)': volumen_util_formatted if volumen_util_formatted else (f"{volumen_util:.1f}%" if pd.notna(volumen_util) else "N/D"),
                'Riesgo': "🔴" if nivel_riesgo == "high" else "🟡" if nivel_riesgo == "medium" else "🟢"
            })
        
        # Agregar fila TOTAL (sin mostrar capacidad)
        total_capacity = df_embalses['Capacidad_GWh_Internal'].sum()  # Solo para cálculos
        valid_volume_data = df_embalses[df_embalses['Volumen Útil (%)'].notna()]
        avg_volume = valid_volume_data['Volumen Útil (%)'].mean() if not valid_volume_data.empty else None
        
        table_data.append({
            'Embalse': 'TOTAL',
            'Volumen Útil (%)': f"{avg_volume:.1f}%" if avg_volume is not None else "N/D",
            'Riesgo': "⚡"  # Icono especial para el total
        })
        
        # Crear DataTable con semáforo (SIN columna de GWh)
        return dash_table.DataTable(
            data=table_data,
            columns=[
                {"name": "Embalse", "id": "Embalse"},
                {"name": "Volumen Útil (%)", "id": "Volumen Útil (%)"},
                {"name": "🚦 Riesgo", "id": "Riesgo"}
            ],
            style_cell={'textAlign': 'left', 'padding': '8px', 'fontFamily': 'Inter, Arial', 'fontSize': 13},
            style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold'},
            style_data={'backgroundColor': '#f8f8f8'},
            style_data_conditional=[
                # Estilos de semáforo
                {
                    'if': {'filter_query': '{Riesgo} = 🔴'},
                    'backgroundColor': '#ffebee',
                    'color': '#c62828',
                    'textAlign': 'center',
                    'fontWeight': 'bold'
                },
                {
                    'if': {'filter_query': '{Riesgo} = 🟡'},
                    'backgroundColor': '#fff8e1',
                    'color': '#f57c00',
                    'textAlign': 'center',
                    'fontWeight': 'bold'
                },
                {
                    'if': {'filter_query': '{Riesgo} = 🟢'},
                    'backgroundColor': '#e8f5e8',
                    'color': '#2e7d32',
                    'textAlign': 'center',
                    'fontWeight': 'bold'
                },
                # Estilo para fila TOTAL
                {
                    'if': {'filter_query': '{Embalse} = "TOTAL"'},
                    'backgroundColor': '#007bff',
                    'color': 'white',
                    'fontWeight': 'bold'
                }
            ],
            page_action="none",
            export_format="xlsx",
            export_headers="display"
        )
        
    except Exception as e:
        logger.error(f"❌ Error en create_region_filtered_capacidad_table: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return html.Div(f"Error al cargar los datos: {str(e)}", className="text-center text-danger")

# NOTA: Los callbacks de tabla de embalses fueron eliminados para implementación directa en layout

# Callback para cargar opciones de regiones dinámicamente
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
            
            # Calcular riesgo con LA MISMA función del semáforo
            riesgo, color, icono = calcular_semaforo_embalse(participacion, volumen_pct)
            
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
