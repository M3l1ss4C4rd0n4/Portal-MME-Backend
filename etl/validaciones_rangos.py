"""
Módulo de Validación de Rangos según XM Sinergox
Complementa validaciones.py con rangos oficiales de XM
"""

import pandas as pd
from typing import Tuple, Optional, Dict, Any, List
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


# ==========================================
# RANGOS VÁLIDOS SEGÚN XM SINERGOX
# ==========================================

VALID_RANGES = {
    # Precios y Costos (TX1 = Pesos Colombianos por MWh)
    'PrecBolsNaci': (0, 2000),      # Precio Bolsa Nacional (TX1)
    'PrecBolsFron': (0, 2000),      # Precio Bolsa Frontera (TX1)
    'PrecOfeComb': (0, 2000),       # Precio Oferta Combustible (TX1)
    'PrecCombGas': (0, 2000),       # Precio Combustible Gas (TX1)
    
    # Restricciones (Millones COP)
    'RestAliv': (0, 500),           # Restricciones Aliviadas (MCOP)
    'RestSinAliv': (0, 500),        # Restricciones Sin Alivio (MCOP)
    'RestAGC': (0, 500),            # Restricciones AGC (MCOP)
    
    # Energía (GWh)
    'AporEner': (0, 500),           # Aportes Hídricos (GWh)
    'GeneReal': (0, 500),           # Generación Real (GWh)
    'DemaEner': (0, 500),           # Demanda Energía (GWh)
    'GeneIdea': (0, 500),           # Generación Ideal (GWh)
    'DemaCome': (0, 100),           # Demanda Comercial (GWh)
    
    # Porcentajes (0-100%)
    'PorcAporEner': (0, 100),       # Porcentaje Aportes (%)
    'PorcCons': (0, 100),           # Porcentaje Consumo (%)
    'CapaUtilDiarEner': (0, 100),   # Capacidad Útil (%)
    
    # Capacidad y Caudales
    'CapEfecNeto': (0, 20000),      # Capacidad Efectiva Neta (MW)
    'CaudAfluente': (0, 10000),     # Caudal Afluente (m³/s)
    'VoluUtilDiarEner': (0, 20000), # Volumen Útil (GWh)
    
    # Comercialización (TX1)
    'CostMarg': (0, 2000),          # Costo Marginal (TX1)
    'PrecPromMerc': (0, 2000),      # Precio Promedio Mercado (TX1)
    'PreciEscaComer': (0, 2000),    # Precio Escasez Comercial (TX1)
}


def validar_rango_metrica(
    df: pd.DataFrame, 
    metrica: str, 
    columna_valor: str = 'valor_gwh',
    log_warnings: bool = True
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Valida que los valores de una métrica estén dentro del rango válido.
    Filtra registros inválidos y retorna estadísticas.
    
    Args:
        df: DataFrame con datos
        metrica: Nombre de la métrica
        columna_valor: Columna con los valores a validar
        log_warnings: Si True, loguea advertencias
        
    Returns:
        (df_limpio, estadisticas)
        
    Ejemplo:
        df_clean, stats = validar_rango_metrica(df, 'PrecBolsNaci')
        print(f"Registros eliminados: {stats['registros_eliminados']}")
    """
    if metrica not in VALID_RANGES:
        # Si no hay rango definido, retornar sin filtrar
        return df, {
            'metrica': metrica,
            'tiene_rango': False,
            'registros_originales': len(df),
            'registros_eliminados': 0,
            'registros_finales': len(df)
        }
    
    min_val, max_val = VALID_RANGES[metrica]
    registros_originales = len(df)
    
    # Filtrar valores fuera de rango
    df_limpio = df[
        (df[columna_valor] >= min_val) & 
        (df[columna_valor] <= max_val)
    ].copy()
    
    registros_eliminados = registros_originales - len(df_limpio)
    
    # Estadísticas
    stats = {
        'metrica': metrica,
        'tiene_rango': True,
        'rango_min': min_val,
        'rango_max': max_val,
        'registros_originales': registros_originales,
        'registros_eliminados': registros_eliminados,
        'registros_finales': len(df_limpio)
    }
    
    # Loguear si hubo eliminaciones
    if registros_eliminados > 0 and log_warnings:
        logger.warning(
            f"Métrica {metrica}: {registros_eliminados} registros fuera de rango "
            f"[{min_val}, {max_val}] eliminados. "
            f"Quedan {len(df_limpio)} registros válidos."
        )
    
    return df_limpio, stats


def validar_y_limpiar_batch(
    df: pd.DataFrame, 
    columna_metrica: str = 'metrica',
    columna_valor: str = 'valor_gwh'
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Valida y limpia un DataFrame con múltiples métricas.
    Aplica validación de rangos a cada métrica.
    
    Args:
        df: DataFrame con múltiples métricas
        columna_metrica: Columna que identifica la métrica
        columna_valor: Columna con los valores
        
    Returns:
        (df_limpio, lista_estadisticas)
        
    Ejemplo:
        df_clean, all_stats = validar_y_limpiar_batch(df)
        for stat in all_stats:
            if stat['registros_eliminados'] > 0:
                print(f"{stat['metrica']}: {stat['registros_eliminados']} eliminados")
    """
    df_limpio = pd.DataFrame()
    estadisticas = []
    
    # Procesar cada métrica
    for metrica in df[columna_metrica].unique():
        df_metrica = df[df[columna_metrica] == metrica].copy()
        
        # Validar rango
        df_metrica_limpio, stats = validar_rango_metrica(
            df_metrica, 
            metrica, 
            columna_valor
        )
        
        # Concatenar resultados
        df_limpio = pd.concat([df_limpio, df_metrica_limpio], ignore_index=True)
        estadisticas.append(stats)
    
    # Log resumen
    total_eliminados = sum(s['registros_eliminados'] for s in estadisticas)
    if total_eliminados > 0:
        logger.info(
            f"Validación de rangos completada: "
            f"{total_eliminados} registros inválidos eliminados. "
            f"Registros finales: {len(df_limpio)}"
        )
    
    return df_limpio, estadisticas


def get_valid_range(metrica: str) -> Optional[Tuple[float, float]]:
    """
    Obtiene el rango válido para una métrica.
    
    Args:
        metrica: Nombre de la métrica
        
    Returns:
        (min, max) o None si no hay rango definido
    """
    return VALID_RANGES.get(metrica)


def validate_value_in_range(value: float, metrica: str) -> bool:
    """
    Valida si un valor individual está dentro del rango válido.
    
    Args:
        value: Valor a validar
        metrica: Nombre de la métrica
        
    Returns:
        True si es válido o no hay rango, False si está fuera de rango
    """
    rango = get_valid_range(metrica)
    
    if not rango:
        return True  # Sin rango definido = válido
    
    min_val, max_val = rango
    return min_val <= value <= max_val
