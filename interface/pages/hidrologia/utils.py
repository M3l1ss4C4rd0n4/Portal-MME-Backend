"""
Utils - Funciones auxiliares y formateo

Funciones de utilidad compartidas por todos los módulos de hidrología.
"""

import pandas as pd
from datetime import datetime, date, timedelta
from infrastructure.logging.logger import setup_logger

logger = setup_logger(__name__)


def format_number(value):
    """Formatear números con separadores de miles usando puntos"""
    if pd.isna(value) or not isinstance(value, (int, float)):
        return value
    return f"{value:,.2f}".replace(",", ".")


def format_date(date_value):
    """Formatear fechas para mostrar solo la fecha sin hora"""
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


def normalizar_codigo(texto):
    """Normaliza códigos/nombres de forma consistente.
    
    Args:
        texto: String a normalizar o pandas Series
        
    Returns:
        String normalizado en UPPERCASE sin espacios extra
    """
    if texto is None:
        return None
    if isinstance(texto, str):
        return texto.strip().upper()
    return texto.str.strip().str.upper()


def normalizar_region(texto):
    """Normaliza nombres de regiones de forma consistente.
    
    Args:
        texto: String a normalizar o pandas Series
        
    Returns:
        String normalizado en UPPER CASE
    """
    if texto is None:
        return None
    if isinstance(texto, str):
        return texto.strip().upper()
    return texto.str.strip().str.upper()


def validar_rango_fechas(start_date, end_date):
    """Valida que el rango de fechas sea lógicamente válido."""
    if not start_date or not end_date:
        return False, "Debe seleccionar fechas de inicio y fin."
    
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') if isinstance(start_date, str) else start_date
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') if isinstance(end_date, str) else end_date
        
        if start_dt > end_dt:
            return False, "La fecha de inicio debe ser anterior a la fecha final."
        
        FECHA_LIMITE_SQLITE = date(2020, 1, 1)
        if isinstance(start_dt, datetime):
            start_date_obj = start_dt.date()
        else:
            start_date_obj = start_dt
        
        if start_date_obj < FECHA_LIMITE_SQLITE:
            mensaje_info = "ℹ️ Consultando datos anteriores a 2020 desde API XM (puede demorar 30-90 segundos)."
            return True, mensaje_info
        
        return True, "Rango de fechas válido"
        
    except Exception as e:
        return False, f"Error validando fechas: {str(e)}"


def manejar_error_api(error, operacion="consulta"):
    """Maneja errores específicos de la API de XM y proporciona mensajes útiles."""
    error_str = str(error).lower()
    
    if "400" in error_str and "json" in error_str:
        message = f"🔄 La API de XM retornó un error para esta {operacion}.\n"
        message += "• Las fechas seleccionadas están fuera del rango disponible\n"
        message += "• Los datos para el período solicitado no están disponibles\n"
        message += "• Hay mantenimiento en los servidores de XM\n"
        return message
    
    elif "timeout" in error_str or "connection" in error_str:
        return "🌐 Error de conexión con la API de XM. Verifique su conexión a internet."
    
    elif "unauthorized" in error_str or "403" in error_str:
        return "🔐 Error de autorización con la API de XM. Contacte al administrador."
    
    else:
        return f"Error inesperado en la {operacion}: {str(error)[:200]}..."


def calcular_semaforo_embalse(participacion, volumen_pct):
    """
    Calcula el estado del embalse basado en participación y volumen.
    
    Retorna:
        tuple: (estado, color, icono)
        Estados: 'critico', 'alerta', 'normal', 'optimo'
    """
    try:
        part = float(participacion) if participacion else 0
        vol = float(volumen_pct) if volumen_pct else 0
        
        # Crítico: Volumen < 30% o Participación < 30%
        if vol < 30 or part < 30:
            return 'critico', '#dc3545', '🔴'
        
        # Alerta: Volumen < 50% o Participación < 50%
        elif vol < 50 or part < 50:
            return 'alerta', '#ffc107', '🟡'
        
        # Normal: Volumen < 80% o Participación < 80%
        elif vol < 80 or part < 80:
            return 'normal', '#17a2b8', '🟢'
        
        # Óptimo: Volumen >= 80% y Participación >= 80%
        else:
            return 'optimo', '#28a745', '🟢'
            
    except Exception as e:
        logger.error(f"Error calculando semáforo: {e}")
        return 'desconocido', '#6c757d', '⚪'


def clasificar_riesgo_embalse(participacion, volumen_util):
    """
    Clasifica el nivel de riesgo de un embalse.
    
    Retorna:
        str: 'Crítico', 'Alto', 'Medio', 'Bajo', 'Muy Bajo'
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
        'Desconocido': {'backgroundColor': '#6c757d', 'color': 'white'}
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
        'Desconocido': '⚪'
    }
    return pictogramas.get(nivel_riesgo, '⚪')
