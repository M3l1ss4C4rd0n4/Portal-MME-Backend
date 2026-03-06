"""
Hidrología - Utilidades compartidas
====================================

Funciones auxiliares, constantes, caché GeoJSON y wrappers de servicio
compartidos por todos los submódulos del paquete de hidrología.

Extraído de ``generacion_hidraulica_hidrologia.py`` para mejorar la
mantenibilidad y permitir la reutilización entre páginas.
"""

import json
import os
import time
import traceback

import pandas as pd
from datetime import datetime, date, timedelta

from infrastructure.logging.logger import setup_logger
from infrastructure.external.xm_service import (
    get_objetoAPI,
    obtener_datos_inteligente,
)
from domain.services.hydrology_service import HydrologyService

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
__all__ = [
    # Plotly lazy loader
    "get_plotly_modules",
    # Module-level state
    "logger",
    "LAST_UPDATE",
    "API_STATUS",
    # Formatting helpers
    "format_number",
    "format_date",
    # GeoJSON cache
    "_GEOJSON_CACHE",
    "_cargar_geojson_cache",
    # Validation / error handling
    "validar_rango_fechas",
    "manejar_error_api",
    # Hydrology service wrappers
    "get_reservas_hidricas",
    "get_aportes_hidricos",
    "calcular_volumen_util_unificado",
    # Río ↔ Región mapping
    "get_rio_region_dict",
    "RIO_REGION",
    "ensure_rio_region_loaded",
    "get_region_options",
    # Normalisation
    "normalizar_codigo",
    "normalizar_region",
    # Data aggregation
    "agregar_datos_hidrologia_inteligente",
    # Risk / semaphore helpers (kept from previous version)
    "calcular_semaforo_embalse",
    "clasificar_riesgo_embalse",
    "obtener_estilo_riesgo",
    "obtener_pictograma_riesgo",
]

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Plotly lazy import
# ---------------------------------------------------------------------------

def get_plotly_modules():
    """Importar plotly solo cuando se necesite."""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

# ---------------------------------------------------------------------------
# Fecha/hora de última actualización del código
# ---------------------------------------------------------------------------
LAST_UPDATE = time.strftime('%Y-%m-%d %H:%M:%S')

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_number(value):
    """Formatear números con separadores de miles usando puntos (formato colombiano)."""
    if pd.isna(value) or not isinstance(value, (int, float)):
        return value
    return f"{value:,.2f}".replace(",", ".")


def format_date(date_value):
    """Formatear fechas para mostrar solo la fecha sin hora."""
    if pd.isna(date_value):
        return date_value

    if isinstance(date_value, str):
        try:
            dt_value = pd.to_datetime(date_value)
            return dt_value.strftime('%Y-%m-%d')
        except Exception:
            return date_value
    elif hasattr(date_value, 'strftime'):
        return date_value.strftime('%Y-%m-%d')
    else:
        return date_value

# ---------------------------------------------------------------------------
# API XM – inicialización perezosa
# ---------------------------------------------------------------------------
API_STATUS = None

_temp_api = get_objetoAPI()
if _temp_api is not None:
    logger.info("✅ API XM inicializada correctamente (lazy)")
    API_STATUS = {'status': 'online', 'message': 'API XM funcionando correctamente'}
else:
    API_STATUS = {'status': 'offline', 'message': 'pydataxm no está disponible'}
    logger.warning("⚠️ API XM no disponible (pydataxm no está disponible)")

# ---------------------------------------------------------------------------
# GeoJSON cache (archivos estáticos – se cargan una sola vez)
# ---------------------------------------------------------------------------
_GEOJSON_CACHE = {
    'colombia_geojson': None,
    'regiones_config': None,
    'departamentos_a_regiones': None,
    'loaded': False,
}


def _cargar_geojson_cache():
    """Carga los archivos GeoJSON UNA SOLA VEZ (son archivos estáticos que no cambian)."""
    if _GEOJSON_CACHE['loaded']:
        return _GEOJSON_CACHE

    try:
        logger.info("📂 Cargando archivos GeoJSON estáticos en cache...")

        # Valores por defecto seguros
        _GEOJSON_CACHE['colombia_geojson'] = {"type": "FeatureCollection", "features": []}
        _GEOJSON_CACHE['regiones_config'] = {"regiones": {}}

        # --- Mapa de departamentos ---
        try:
            geojson_path = os.path.join(
                os.path.dirname(__file__), '..', '..', '..', 'assets',
                'departamentos_colombia.geojson',
            )
            if os.path.exists(geojson_path):
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    _GEOJSON_CACHE['colombia_geojson'] = json.load(f)
                logger.info(f"✅ Mapa cargado correctamente desde {geojson_path}")
            else:
                logger.error(f"❌ Archivo GeoJSON no encontrado en: {geojson_path}")
        except Exception as e:
            logger.error(f"❌ Error cargando GeoJSON departamentos: {e}")

        # --- Configuración de regiones ---
        try:
            regiones_path = os.path.join(
                os.path.dirname(__file__), '..', '..', '..', 'assets',
                'regiones_naturales_colombia.json',
            )
            if os.path.exists(regiones_path):
                with open(regiones_path, 'r', encoding='utf-8') as f:
                    _GEOJSON_CACHE['regiones_config'] = json.load(f)
                logger.info(f"✅ Configuración regiones cargada desde {regiones_path}")
            else:
                logger.error(f"❌ Archivo regiones no encontrado en: {regiones_path}")
        except Exception as e:
            logger.error(f"❌ Error cargando config regiones: {e}")

        _GEOJSON_CACHE['loaded'] = True

        # Diccionario inverso: departamento → región
        departamentos_a_regiones = {}
        for region_key, region_data in _GEOJSON_CACHE['regiones_config']['regiones'].items():
            for depto in region_data['departamentos']:
                departamentos_a_regiones[depto] = {
                    'region': region_data['nombre'],
                    'color': region_data['color'],
                    'border': region_data['border'],
                }

        _GEOJSON_CACHE['departamentos_a_regiones'] = departamentos_a_regiones
        _GEOJSON_CACHE['loaded'] = True

        logger.info(
            f"✅ GeoJSON cargado en memoria: "
            f"{len(_GEOJSON_CACHE['regiones_config']['regiones'])} regiones, "
            f"{len(departamentos_a_regiones)} departamentos"
        )

        return _GEOJSON_CACHE

    except Exception as e:
        logger.error(f"❌ Error cargando GeoJSON en cache: {e}")
        traceback.print_exc()
        return None


# Cargar cache al importar el módulo (solo una vez)
_cargar_geojson_cache()

# ---------------------------------------------------------------------------
# Validación de fechas y manejo de errores
# ---------------------------------------------------------------------------

def validar_rango_fechas(start_date, end_date):
    """
    Valida que el rango de fechas sea lógicamente válido.

    Permite cualquier rango de fechas – los datos se consultarán desde PostgreSQL
    (>=2020, rápido) o desde API XM (<2020, lento pero funcional).
    """
    if not start_date or not end_date:
        return False, "Debe seleccionar fechas de inicio y fin."

    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') if isinstance(start_date, str) else start_date
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') if isinstance(end_date, str) else end_date

        if start_dt > end_dt:
            return False, "La fecha de inicio debe ser anterior a la fecha final."

        FECHA_LIMITE_BD = date(2020, 1, 1)
        start_date_obj = start_dt.date() if isinstance(start_dt, datetime) else start_dt

        if start_date_obj < FECHA_LIMITE_BD:
            mensaje_info = (
                "ℹ️ Consultando datos anteriores a 2020 desde API XM "
                "(puede demorar 30-90 segundos). Datos desde 2020 en adelante "
                "se cargarán rápidamente desde base de datos local."
            )
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
        message = f"🔄 La API de XM retornó un error para esta {operacion}. Esto suele ocurrir cuando:\n"
        message += "• Las fechas seleccionadas están fuera del rango disponible\n"
        message += "• Los datos para el período solicitado no están disponibles\n"
        message += "• Hay mantenimiento en los servidores de XM\n"
        message += "Recomendaciones:\n"
        message += "• Intente con fechas más recientes (últimos 6 meses)\n"
        message += "• Reduzca el rango de fechas\n"
        message += "• Verifique el estado de la API de XM en www.xm.com.co"
        return message

    elif "timeout" in error_str or "connection" in error_str:
        return "🌐 Error de conexión con la API de XM. Verifique su conexión a internet y vuelva a intentar."

    elif "unauthorized" in error_str or "403" in error_str:
        return "🔐 Error de autorización con la API de XM. Contacte al administrador del sistema."

    else:
        return f"Error inesperado en la {operacion}: {str(error)[:200]}..."

# ---------------------------------------------------------------------------
# Hydrology service – instancia global y wrappers
# ---------------------------------------------------------------------------
_hydrology_service = HydrologyService()


def get_reservas_hidricas(fecha):
    """Obtiene las reservas hídricas para una fecha dada."""
    return _hydrology_service.get_reservas_hidricas(fecha)


def get_aportes_hidricos(fecha):
    """Obtiene los aportes hídricos para una fecha dada."""
    return _hydrology_service.get_aportes_hidricos(fecha)


def calcular_volumen_util_unificado(fecha, region=None, embalse=None):
    """Calcula el volumen útil unificado, opcionalmente filtrado por región o embalse."""
    return _hydrology_service.calcular_volumen_util_unificado(fecha, region, embalse)

# ---------------------------------------------------------------------------
# Normalización unificada
# ---------------------------------------------------------------------------

def normalizar_codigo(texto):
    """Normaliza códigos/nombres de forma consistente en TODO el sistema.

    Args:
        texto: String a normalizar o pandas Series.

    Returns:
        String normalizado en UPPERCASE sin espacios extra.
    """
    if texto is None:
        return None
    if isinstance(texto, str):
        return texto.strip().upper()
    # pandas Series
    return texto.str.strip().str.upper()


def normalizar_region(texto):
    """Normaliza nombres de regiones de forma consistente.

    Args:
        texto: String a normalizar o pandas Series.

    Returns:
        String normalizado en UPPER CASE (para coincidir con REGIONES_COORDENADAS).
    """
    if texto is None:
        return None
    if isinstance(texto, str):
        return texto.strip().upper()
    # pandas Series
    return texto.str.strip().str.upper()

# ---------------------------------------------------------------------------
# Río ↔ Región mapping
# ---------------------------------------------------------------------------

def get_rio_region_dict():
    """Obtiene la relación río-región directamente desde la API XM / PostgreSQL."""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        df, warning = obtener_datos_inteligente('ListadoRios', 'Sistema', yesterday, today)
        if 'Values_Name' in df.columns and 'Values_HydroRegion' in df.columns:
            df['Values_Name'] = normalizar_codigo(df['Values_Name'])
            df['Values_HydroRegion'] = normalizar_region(df['Values_HydroRegion'])
            return dict(sorted(zip(df['Values_Name'], df['Values_HydroRegion'])))
        else:
            return {}
    except Exception as e:
        logger.error(f"Error obteniendo relación río-región desde la API: {e}", exc_info=True)
        return {}


# Inicializar como None – se cargará bajo demanda
RIO_REGION = None


def ensure_rio_region_loaded():
    """Carga ``RIO_REGION`` bajo demanda si aún no se ha cargado."""
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
        df, warning = obtener_datos_inteligente(
            'AporEner', 'Rio',
            (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'),
            date.today().strftime('%Y-%m-%d'),
        )
        if 'Name' in df.columns:
            rios_con_datos = set(df['Name'].unique())
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

# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------

def agregar_datos_hidrologia_inteligente(df_hidrologia, dias_periodo):
    """
    Agrupa los datos de hidrología según el período para optimizar rendimiento.

    Niveles de agregación:
        * ``<= 60 días`` : datos diarios (sin cambios, máxima granularidad)
        * ``61-180 días`` : datos semanales (reduce ~7× puntos)
        * ``> 180 días``  : datos mensuales (reduce ~30× puntos)

    IMPORTANTE: Mantiene el coloreado dinámico en todos los rangos;
    solo reduce la cantidad de puntos a renderizar.
    """
    if df_hidrologia.empty:
        return df_hidrologia

    # Asegurar que Date sea datetime
    df_hidrologia['Date'] = pd.to_datetime(df_hidrologia['Date'])

    # Determinar nivel de agregación
    if dias_periodo <= 60:
        logger.info(f"📊 Sin agregación: {dias_periodo} días (≤60) - Datos diarios")
        return df_hidrologia
    elif dias_periodo <= 180:
        df_hidrologia['Periodo'] = df_hidrologia['Date'].dt.to_period('W').dt.start_time
        periodo_label = 'Semana'
        logger.info(f"📊 Agrupación SEMANAL: {dias_periodo} días → ~{dias_periodo // 7} semanas")
    else:
        df_hidrologia['Periodo'] = df_hidrologia['Date'].dt.to_period('M').dt.start_time
        periodo_label = 'Mes'
        logger.info(f"📊 Agrupación MENSUAL: {dias_periodo} días → ~{dias_periodo // 30} meses")

    # Columnas de agrupación
    columnas_grupo = ['Periodo']
    if 'Name' in df_hidrologia.columns:
        columnas_grupo.append('Name')
    if 'Region' in df_hidrologia.columns:
        columnas_grupo.append('Region')

    # Agrupar y promediar valores
    df_agregado = df_hidrologia.groupby(columnas_grupo, as_index=False).agg({
        'Value': 'mean',
    })

    df_agregado.rename(columns={'Periodo': 'Date'}, inplace=True)

    logger.info(
        f"✅ Datos agregados: {len(df_hidrologia)} registros → "
        f"{len(df_agregado)} {periodo_label}s "
        f"(reducción {100 * (1 - len(df_agregado) / len(df_hidrologia)):.1f}%)"
    )

    return df_agregado

# ---------------------------------------------------------------------------
# Semáforo / riesgo de embalses (helpers conservados de la versión anterior)
# ---------------------------------------------------------------------------

def calcular_semaforo_embalse(participacion, volumen_pct):
    """
    Calcula el estado del embalse basado en participación y volumen.

    Returns:
        tuple: (estado, color, icono)
        Estados: ``'critico'``, ``'alerta'``, ``'normal'``, ``'optimo'``
    """
    try:
        part = float(participacion) if participacion else 0
        vol = float(volumen_pct) if volumen_pct else 0

        if vol < 30 or part < 30:
            return 'critico', '#dc3545', '🔴'
        elif vol < 50 or part < 50:
            return 'alerta', '#ffc107', '🟡'
        elif vol < 80 or part < 80:
            return 'normal', '#17a2b8', '🟢'
        else:
            return 'optimo', '#28a745', '🟢'
    except Exception as e:
        logger.error(f"Error calculando semáforo: {e}")
        return 'desconocido', '#6c757d', '⚪'


def clasificar_riesgo_embalse(participacion, volumen_util):
    """
    Clasifica el nivel de riesgo de un embalse.

    Returns:
        str: ``'Crítico'``, ``'Alto'``, ``'Medio'``, ``'Bajo'`` o ``'Muy Bajo'``
    """
    try:
        part = float(participacion) if participacion else 0
        vol = float(volumen_util) if volumen_util else 0

        if vol < 20 or part < 20:
            return 'Crítico'
        elif vol < 40 or part < 40:
            return 'Alto'
        elif vol < 60 or part < 60:
            return 'Medio'
        elif vol < 80 or part < 80:
            return 'Bajo'
        else:
            return 'Muy Bajo'
    except Exception as e:
        logger.error(f"Error clasificando riesgo: {e}")
        return 'Desconocido'


def obtener_estilo_riesgo(nivel_riesgo):
    """Retorna el estilo CSS para un nivel de riesgo."""
    estilos = {
        'Crítico': {'backgroundColor': '#dc3545', 'color': 'white', 'fontWeight': 'bold'},
        'Alto': {'backgroundColor': '#fd7e14', 'color': 'white', 'fontWeight': 'bold'},
        'Medio': {'backgroundColor': '#ffc107', 'color': 'black'},
        'Bajo': {'backgroundColor': '#20c997', 'color': 'white'},
        'Muy Bajo': {'backgroundColor': '#28a745', 'color': 'white'},
        'Desconocido': {'backgroundColor': '#6c757d', 'color': 'white'},
    }
    return estilos.get(nivel_riesgo, estilos['Desconocido'])


def obtener_pictograma_riesgo(nivel_riesgo):
    """Retorna el emoji para un nivel de riesgo."""
    pictogramas = {
        'Crítico': '🔴',
        'Alto': '🟠',
        'Medio': '🟡',
        'Bajo': '🟢',
        'Muy Bajo': '🟢',
        'Desconocido': '⚪',
    }
    return pictogramas.get(nivel_riesgo, '⚪')
