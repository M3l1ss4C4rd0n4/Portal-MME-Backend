"""
Validador de unidades para prevenir conversiones duplicadas.

Este módulo previene errores comunes como:
- Conversiones duplicadas (kWh → GWh aplicadas dos veces)
- Uso incorrecto de .mean() vs .sum()
- Fechas sin datos disponibles
"""

import logging
from typing import Optional, Tuple
import pandas as pd
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Métricas que YA vienen convertidas a GWh por _xm.py
METRICAS_AUTO_CONVERTIDAS = {
    'AporEner',
    'AporEnerMediHist'
}

# Métricas que NO se convierten automáticamente
METRICAS_SIN_CONVERSION = {
    'VoluUtilDiarEner',  # Viene en Wh → necesita / 1e9 para GWh
    'CapaUtilDiarEner',  # Viene en Wh → necesita / 1e9 para GWh
    'AporCaudal',        # Viene en m³/s
    'Gene'               # Generación por planta
}


def validar_unidades_energia(metric_name: str, data: pd.DataFrame, expected_range: Tuple[float, float] = (0.01, 10000)) -> bool:
    """
    Valida que las unidades de energía sean correctas (en GWh).
    
    Args:
        metric_name: Nombre de la métrica
        data: DataFrame con columna 'Value'
        expected_range: Rango esperado de valores en GWh (min, max)
    
    Returns:
        True si las unidades parecen correctas, False si hay problemas
    """
    if data is None or data.empty or 'Value' not in data.columns:
        return True  # No hay datos para validar
    
    valor_promedio = data['Value'].mean()
    valor_total = data['Value'].sum()
    
    # Validar según el tipo de métrica
    if metric_name in METRICAS_AUTO_CONVERTIDAS:
        # Estas ya vienen en GWh
        if valor_promedio < 0.001:
            logger.error(
                f"⚠️ UNIDADES INCORRECTAS: {metric_name} tiene valores sospechosamente pequeños "
                f"(promedio={valor_promedio:.6f} GWh). "
                f"¿Se aplicó conversión duplicada?"
            )
            return False
        elif valor_promedio > 100000:
            logger.error(
                f"⚠️ UNIDADES INCORRECTAS: {metric_name} tiene valores muy grandes "
                f"(promedio={valor_promedio:.2f}). "
                f"¿Olvidó convertir de kWh a GWh?"
            )
            return False
    
    logger.debug(f"✅ Unidades validadas para {metric_name}: promedio={valor_promedio:.2f} GWh, total={valor_total:.2f} GWh")
    return True


def debe_convertir_unidades(metric_name: str) -> Tuple[bool, Optional[float]]:
    """
    Determina si una métrica necesita conversión de unidades.
    
    Returns:
        (necesita_conversion, factor_conversion)
    """
    if metric_name in METRICAS_AUTO_CONVERTIDAS:
        logger.debug(f"ℹ️ {metric_name} YA está convertido a GWh por _xm.py - NO aplicar conversión")
        return False, None
    
    if metric_name in ['VoluUtilDiarEner', 'CapaUtilDiarEner']:
        logger.debug(f"ℹ️ {metric_name} viene en Wh - convertir a GWh (÷ 1e9)")
        return True, 1e9
    
    # Por defecto, no convertir
    logger.debug(f"ℹ️ {metric_name} - sin conversión automática")
    return False, None


def buscar_ultima_fecha_disponible(
    fetch_function,
    metric_name: str,
    entity: str,
    fecha_inicio: date,
    max_dias_busqueda: int = 7
) -> Optional[date]:
    """
    Busca hacia atrás desde fecha_inicio hasta encontrar datos disponibles.
    
    Args:
        fetch_function: Función para consultar datos (ej: fetch_metric_data)
        metric_name: Nombre de la métrica
        entity: Entidad (Sistema, Rio, etc.)
        fecha_inicio: Fecha desde donde empezar a buscar
        max_dias_busqueda: Máximo de días a buscar hacia atrás
    
    Returns:
        Fecha con datos disponibles o None
    """
    logger.info(f"🔍 Buscando última fecha disponible para {metric_name}/{entity}")
    
    for dias_atras in range(max_dias_busqueda):
        fecha_prueba = fecha_inicio - timedelta(days=dias_atras)
        fecha_str = fecha_prueba.strftime('%Y-%m-%d')
        
        try:
            data = fetch_function(metric_name, entity, fecha_str, fecha_str)
            if data is not None and not data.empty:
                logger.info(f"✅ Datos disponibles hasta: {fecha_prueba.strftime('%Y-%m-%d')}")
                return fecha_prueba
        except Exception as e:
            logger.warning(f"⚠️ Error consultando {fecha_str}: {e}")
    
    logger.error(f"❌ No se encontraron datos para {metric_name}/{entity} en los últimos {max_dias_busqueda} días")
    return None


def validar_agregacion(
    data: pd.DataFrame,
    metodo: str,
    contexto: str
) -> bool:
    """
    Valida que se esté usando el método de agregación correcto.
    
    Args:
        data: DataFrame con datos
        metodo: 'sum' o 'mean'
        contexto: Descripción del cálculo (para logging)
    
    Returns:
        True si es correcto, False si hay advertencias
    """
    if data is None or data.empty:
        return True
    
    # Reglas de validación
    if 'acumulado' in contexto.lower() or 'total' in contexto.lower():
        if metodo != 'sum':
            logger.warning(
                f"⚠️ AGREGACIÓN INCORRECTA: '{contexto}' usa '{metodo}' pero debería usar 'sum' "
                f"para calcular totales acumulados"
            )
            return False
    
    if 'promedio' in contexto.lower() or 'media' in contexto.lower():
        if metodo != 'mean':
            logger.warning(
                f"⚠️ AGREGACIÓN INCORRECTA: '{contexto}' usa '{metodo}' pero debería usar 'mean' "
                f"para calcular promedios"
            )
            return False
    
    logger.debug(f"✅ Agregación validada: {metodo} para '{contexto}'")
    return True


def log_metricas_debug(
    nombre: str,
    data: pd.DataFrame,
    antes_conversion: bool = False
) -> None:
    """
    Log detallado de métricas para debugging.
    """
    if data is None or data.empty:
        logger.debug(f"📊 {nombre}: Sin datos")
        return
    
    col_value = 'Value' if 'Value' in data.columns else 'Values_code'
    if col_value not in data.columns:
        logger.debug(f"📊 {nombre}: Columna de valor no encontrada")
        return
    
    estado = "ANTES conversión" if antes_conversion else "DESPUÉS conversión"
    
    logger.info(f"📊 {nombre} ({estado}):")
    logger.info(f"   Registros: {len(data)}")
    logger.info(f"   Total: {data[col_value].sum():.2f}")
    logger.info(f"   Promedio: {data[col_value].mean():.2f}")
    logger.info(f"   Min: {data[col_value].min():.2f}, Max: {data[col_value].max():.2f}")
    
    if 'Date' in data.columns:
        logger.info(f"   Período: {data['Date'].min()} a {data['Date'].max()}")
