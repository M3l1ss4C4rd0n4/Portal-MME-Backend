"""
Calculadora de métricas y variaciones porcentuales
Basado en fórmulas oficiales de XM Sinergox
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def calculate_variation(current_value: float, previous_value: float) -> Dict[str, Any]:
    """
    Calcula variación porcentual según fórmula oficial de XM.
    
    Fórmula: ((valor_actual - valor_anterior) / |valor_anterior|) * 100
    
    Ejemplos reales de XM Sinergox:
    - Precio Bolsa: (242.87 - 254.69) / 254.69 * 100 = -4.64%
    - Aportes: (243.07 - 183.25) / 183.25 * 100 = +32.65%
    - Exportaciones: (0.028 - 0.025) / 0.025 * 100 = +13.73%
    - Emisiones CO2: (28544.92 - 26631.48) / 26631.48 * 100 = +7.18%
    
    Args:
        current_value: Valor actual
        previous_value: Valor anterior
        
    Returns:
        dict con:
        - variation_pct: Porcentaje de variación (float)
        - direction: 'up', 'down', o 'neutral'
        - arrow: '▲', '▼', o '—'
    """
    # Validar valores
    if pd.isna(current_value) or pd.isna(previous_value):
        return {
            'variation_pct': None,
            'direction': 'neutral',
            'arrow': '—'
        }
    
    # Evitar división por cero
    if previous_value == 0:
        if current_value == 0:
            return {'variation_pct': 0.0, 'direction': 'neutral', 'arrow': '—'}
        else:
            # Si antes era 0 y ahora no, es crecimiento infinito
            return {'variation_pct': None, 'direction': 'up', 'arrow': '▲'}
    
    # Calcular variación (fórmula oficial XM)
    variation = ((current_value - previous_value) / abs(previous_value)) * 100
    
    # Determinar dirección y flecha
    if variation > 0.1:  # Umbral de 0.1% para evitar ruido
        return {
            'variation_pct': round(variation, 2),
            'direction': 'up',
            'arrow': '▲'
        }
    elif variation < -0.1:
        return {
            'variation_pct': round(variation, 2),
            'direction': 'down',
            'arrow': '▼'
        }
    else:
        return {
            'variation_pct': round(variation, 2),
            'direction': 'neutral',
            'arrow': '—'
        }


def format_value(value: float, unit: str) -> str:
    """
    Formatea valores según unidad como en XM Sinergox.
    
    Ejemplos de XM:
    - 242.87 TX1
    - 12,907.74 GWh
    - 87.73 %
    - 28,544.92 Ton CO2e
    - 295.00 Millones COP
    
    Args:
        value: Valor numérico
        unit: Unidad de medida
        
    Returns:
        String formateado
    """
    if pd.isna(value):
        return "—"
    
    # Formateo según tipo de unidad
    if unit in ['TX1', 'GWh', 'MW', 'GWh-día', 'm3/s']:
        # 2 decimales con separador de miles
        return f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    elif unit == '%':
        # Porcentajes con 2 decimales
        return f"{value:.2f}%"
    
    elif unit in ['COP', 'Millones COP']:
        # Moneda con 2 decimales
        return f"${value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    elif unit == 'Ton CO2e':
        # Toneladas con 2 decimales
        return f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    else:
        # Default: 2 decimales
        return f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def calculate_percentage(value: float, total: float) -> float:
    """
    Calcula porcentaje evitando división por cero.
    
    Args:
        value: Valor parcial
        total: Valor total
        
    Returns:
        Porcentaje (0-100)
    """
    if total == 0 or pd.isna(total) or pd.isna(value):
        return 0.0
    
    return round((value / total) * 100, 2)


def validate_value_in_range(value: float, min_val: float, max_val: float, metric_name: str = "") -> bool:
    """
    Valida que un valor esté en el rango esperado.
    
    Args:
        value: Valor a validar
        min_val: Valor mínimo aceptable
        max_val: Valor máximo aceptable
        metric_name: Nombre de la métrica (para logging)
        
    Returns:
        True si está en rango, False si no
    """
    if pd.isna(value):
        return False
    
    if value < min_val or value > max_val:
        logger.warning(f"Valor fuera de rango para {metric_name}: {value:.2f} (esperado: {min_val}-{max_val})")
        return False
    
    return True


# Rangos válidos basados en análisis de XM Sinergox
VALID_RANGES = {
    'PrecBolsNaci': (0, 2000),           # TX1
    'DemaReal': (0, 500),                # GWh diario
    'DemaCome': (0, 500),                # GWh diario
    'Gene': (0, 500),                    # GWh por recurso
    'AporEner': (0, 500),                # GWh
    'VoluUtilDiarEner': (0, 20000),      # GWh total
    'CapaUtilDiarEner': (0, 100),        # % (puede superar)
    'RestAliv': (0, 500),                # Millones COP
    'RestSinAliv': (0, 500),             # Millones COP
    'RentasCongestRestr': (0, 1000),     # Millones COP
    'EmisionesCO2': (0, 100000),         # Ton CO2e
    'ImpoEner': (0, 50),                 # GWh
    'ExpoEner': (0, 50),                 # GWh
    'PerdidasEner': (0, 100),            # GWh
}


def get_valid_range(metric_id: str) -> Optional[tuple]:
    """
    Obtiene el rango válido para una métrica.
    
    Args:
        metric_id: ID de la métrica
        
    Returns:
        Tupla (min, max) o None si no tiene rango definido
    """
    # Buscar coincidencia exacta
    if metric_id in VALID_RANGES:
        return VALID_RANGES[metric_id]
    
    # Buscar por prefijo (ej: 'GeneIdea' → 'Gene')
    for key, range_val in VALID_RANGES.items():
        if metric_id.startswith(key):
            return range_val
    
    return None
