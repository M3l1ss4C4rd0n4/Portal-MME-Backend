"""
Servicio de Indicadores Completos
Retorna estructura completa: valor actual, anterior, variación, flecha
Basado en patrón de XM Sinergox
"""

from typing import Optional, Dict, Any
import pandas as pd
from infrastructure.database.manager import db_manager
from domain.services.metrics_calculator import calculate_variation, format_value
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class IndicatorsService:
    """
    Servicio para obtener indicadores con estructura completa.
    
    Estructura de salida (según XM Sinergox):
    {
        'metric_id': 'precio_bolsa',
        'valor_actual': 242.87,
        'unidad': 'TX1',
        'fecha_actual': '2026-01-29',
        'valor_anterior': 254.69,
        'fecha_anterior': '2026-01-28',
        'variacion_pct': -4.64,
        'direccion': 'down',
        'flecha': '▼',
        'valor_formateado': '242.87',
        'variacion_formateada': '-4.64%'
    }
    """
    
    def get_indicator_complete(self, metric_id: str, entity: str = 'Sistema') -> Optional[Dict[str, Any]]:
        """
        Obtiene indicador completo con comparación temporal.
        
        Args:
            metric_id: Identificador de la métrica
            entity: Entidad (default: 'Sistema')
            
        Returns:
            Dict con estructura completa o None si no hay datos
        """
        try:
            # Obtener últimos 2 registros
            query = """
                SELECT fecha, valor_gwh as valor, unidad
                FROM metrics
                WHERE metrica = %s AND entidad = %s
                ORDER BY fecha DESC
                LIMIT 2
            """
            df = db_manager.query_df(query, params=(metric_id, entity))
            
            if df.empty:
                logger.warning(f"No hay datos para {metric_id} (entidad: {entity})")
                return None
            
            # Si solo hay 1 registro, no se puede calcular variación
            if len(df) < 2:
                actual = df.iloc[0]
                return {
                    'metric_id': metric_id,
                    'valor_actual': actual['valor'],
                    'unidad': actual['unidad'] if pd.notna(actual['unidad']) else '',
                    'fecha_actual': actual['fecha'],
                    'valor_anterior': None,
                    'fecha_anterior': None,
                    'variacion_pct': None,
                    'direccion': 'neutral',
                    'flecha': '—',
                    'valor_formateado': format_value(actual['valor'], actual['unidad']),
                    'variacion_formateada': '—'
                }
            
            # Calcular variación con 2 registros
            actual = df.iloc[0]
            anterior = df.iloc[1]
            
            variation = calculate_variation(actual['valor'], anterior['valor'])
            
            # Formatear variación
            if variation['variation_pct'] is not None:
                var_formatted = f"{variation['arrow']} {variation['variation_pct']:+.2f}%"
            else:
                var_formatted = "—"
            
            return {
                'metric_id': metric_id,
                'valor_actual': actual['valor'],
                'unidad': actual['unidad'] if pd.notna(actual['unidad']) else '',
                'fecha_actual': actual['fecha'],
                'valor_anterior': anterior['valor'],
                'fecha_anterior': anterior['fecha'],
                **variation,
                'valor_formateado': format_value(actual['valor'], actual['unidad']),
                'variacion_formateada': var_formatted
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo indicador {metric_id}: {e}")
            return None
    
    def get_multiple_indicators(self, metric_ids: list, entity: str = 'Sistema') -> Dict[str, Dict]:
        """
        Obtiene múltiples indicadores en una sola llamada.
        
        Args:
            metric_ids: Lista de IDs de métricas
            entity: Entidad (default: 'Sistema')
            
        Returns:
            Dict con {metric_id: indicator_data}
        """
        result = {}
        
        for metric_id in metric_ids:
            indicator = self.get_indicator_complete(metric_id, entity)
            if indicator:
                result[metric_id] = indicator
        
        return result
    
    def get_indicator_with_history(
        self, 
        metric_id: str, 
        entity: str = 'Sistema',
        days: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene indicador con serie temporal histórica.
        
        Args:
            metric_id: Identificador de la métrica
            entity: Entidad
            days: Días de historia
            
        Returns:
            Dict con indicador + serie temporal
        """
        # Obtener indicador básico
        indicator = self.get_indicator_complete(metric_id, entity)
        
        if not indicator:
            return None
        
        # Obtener serie histórica
        query = """
            SELECT fecha, valor_gwh as valor
            FROM metrics
            WHERE metrica = %s AND entidad = %s
            ORDER BY fecha DESC
            LIMIT %s
        """
        df_history = db_manager.query_df(query, params=(metric_id, entity, days))
        
        if not df_history.empty:
            # Ordenar ascendente para gráficos
            df_history = df_history.sort_values('fecha')
            
            indicator['history'] = {
                'dates': df_history['fecha'].tolist(),
                'values': df_history['valor'].tolist()
            }
        
        return indicator


# Instancia global
indicators_service = IndicatorsService()
