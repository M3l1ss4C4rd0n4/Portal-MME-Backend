"""
Validadores para Portal Energético MME

Este módulo proporciona funciones de validación para datos de entrada,
parámetros de usuario, y estructuras de datos.

Validadores disponibles:
    - validate_date_range: Validar rango de fechas
    - validate_metric: Validar que una métrica sea válida
    - validate_entity: Validar que una entidad sea válida
    - validate_dataframe: Validar estructura de DataFrame
    - validate_numeric: Validar valores numéricos

Uso:
    from utils.validators import validate_date_range
    
    start, end = validate_date_range('2024-01-01', '2024-12-31', max_days=365)
"""

from datetime import datetime, timedelta
from typing import Optional, List, Any, Union
import pandas as pd

from utils.exceptions import (
    DateRangeError,
    InvalidParameterError,
    DataValidationError,
    DataFormatError
)


# ============================================================================
# VALIDACIÓN DE FECHAS
# ============================================================================

def validate_date_range(
    start_date: str,
    end_date: str,
    max_days: Optional[int] = None,
    format: str = '%Y-%m-%d'
) -> tuple:
    """
    Valida y normaliza un rango de fechas.
    
    Args:
        start_date: Fecha de inicio como string
        end_date: Fecha de fin como string
        max_days: Número máximo de días permitidos en el rango (opcional)
        format: Formato de fecha esperado (default: YYYY-MM-DD)
    
    Returns:
        tuple: (start_date_str, end_date_str) normalizadas
    
    Raises:
        DateRangeError: Si las fechas son inválidas
    
    Ejemplo:
        start, end = validate_date_range('2024-01-01', '2024-12-31', max_days=365)
    """
    # Validar formato
    try:
        start_dt = datetime.strptime(start_date, format)
        end_dt = datetime.strptime(end_date, format)
    except ValueError as e:
        raise DateRangeError(
            f"Formato de fecha inválido. Use {format}",
            details={'start': start_date, 'end': end_date, 'error': str(e)}
        )
    
    # Validar orden
    if end_dt < start_dt:
        raise DateRangeError(
            "Fecha de fin anterior a fecha de inicio",
            details={'inicio': start_date, 'fin': end_date}
        )
    
    # Validar rango máximo
    if max_days is not None:
        days_diff = (end_dt - start_dt).days
        if days_diff > max_days:
            raise DateRangeError(
                f"Rango de fechas excede el máximo permitido de {max_days} días",
                details={
                    'inicio': start_date,
                    'fin': end_date,
                    'dias_solicitados': days_diff,
                    'dias_maximo': max_days
                }
            )
    
    # Retornar fechas normalizadas
    return start_dt.strftime(format), end_dt.strftime(format)


def validate_date(
    date_str: str,
    format: str = '%Y-%m-%d',
    min_date: Optional[str] = None,
    max_date: Optional[str] = None
) -> str:
    """
    Valida una fecha individual.
    
    Args:
        date_str: Fecha como string
        format: Formato esperado
        min_date: Fecha mínima permitida (opcional)
        max_date: Fecha máxima permitida (opcional)
    
    Returns:
        str: Fecha normalizada
    
    Raises:
        DateRangeError: Si la fecha es inválida
    
    Ejemplo:
        date = validate_date('2024-01-01', min_date='2020-01-01')
    """
    try:
        dt = datetime.strptime(date_str, format)
    except ValueError as e:
        raise DateRangeError(
            f"Formato de fecha inválido. Use {format}",
            details={'fecha': date_str, 'error': str(e)}
        )
    
    # Validar rango
    if min_date:
        min_dt = datetime.strptime(min_date, format)
        if dt < min_dt:
            raise DateRangeError(
                f"Fecha anterior a la mínima permitida ({min_date})",
                details={'fecha': date_str, 'minima': min_date}
            )
    
    if max_date:
        max_dt = datetime.strptime(max_date, format)
        if dt > max_dt:
            raise DateRangeError(
                f"Fecha posterior a la máxima permitida ({max_date})",
                details={'fecha': date_str, 'maxima': max_date}
            )
    
    return dt.strftime(format)


# ============================================================================
# VALIDACIÓN DE MÉTRICAS Y ENTIDADES
# ============================================================================

def validate_metric(
    metric: str,
    valid_metrics: Optional[List[str]] = None
) -> str:
    """
    Valida que una métrica sea válida.
    
    Args:
        metric: Nombre de la métrica
        valid_metrics: Lista de métricas válidas (opcional)
    
    Returns:
        str: Métrica normalizada
    
    Raises:
        InvalidParameterError: Si la métrica no es válida
    
    Ejemplo:
        metric = validate_metric('DemaEner', valid_metrics=['DemaEner', 'GeneReal'])
    """
    if not metric or not isinstance(metric, str):
        raise InvalidParameterError(
            "Métrica debe ser un string no vacío",
            details={'metrica': metric, 'tipo': type(metric).__name__}
        )
    
    metric = metric.strip()
    
    if valid_metrics is not None and metric not in valid_metrics:
        raise InvalidParameterError(
            f"Métrica '{metric}' no es válida",
            details={
                'metrica': metric,
                'metricas_validas': valid_metrics[:10]  # Primeras 10 para no saturar
            }
        )
    
    return metric


def validate_entity(
    entity: str,
    valid_entities: Optional[List[str]] = None
) -> str:
    """
    Valida que una entidad sea válida.
    
    Args:
        entity: Nombre de la entidad
        valid_entities: Lista de entidades válidas (opcional)
    
    Returns:
        str: Entidad normalizada
    
    Raises:
        InvalidParameterError: Si la entidad no es válida
    
    Ejemplo:
        entity = validate_entity('Sistema', valid_entities=['Sistema', 'Recurso'])
    """
    if not entity or not isinstance(entity, str):
        raise InvalidParameterError(
            "Entidad debe ser un string no vacío",
            details={'entidad': entity, 'tipo': type(entity).__name__}
        )
    
    entity = entity.strip()
    
    if valid_entities is not None and entity not in valid_entities:
        raise InvalidParameterError(
            f"Entidad '{entity}' no es válida",
            details={
                'entidad': entity,
                'entidades_validas': valid_entities[:10]
            }
        )
    
    return entity


# ============================================================================
# VALIDACIÓN DE DATAFRAMES
# ============================================================================

def validate_dataframe(
    df: pd.DataFrame,
    required_columns: Optional[List[str]] = None,
    min_rows: int = 0,
    allow_nulls: bool = True,
    name: str = "DataFrame"
) -> pd.DataFrame:
    """
    Valida la estructura y contenido de un DataFrame.
    
    Args:
        df: DataFrame a validar
        required_columns: Columnas requeridas (opcional)
        min_rows: Número mínimo de filas requeridas
        allow_nulls: Si False, valida que no haya valores nulos
        name: Nombre descriptivo del DataFrame para mensajes de error
    
    Returns:
        pd.DataFrame: El mismo DataFrame si es válido
    
    Raises:
        DataFormatError: Si la estructura no es válida
        DataValidationError: Si los datos no son válidos
    
    Ejemplo:
        df = validate_dataframe(
            df,
            required_columns=['Date', 'Value'],
            min_rows=1,
            allow_nulls=False
        )
    """
    # Validar tipo
    if not isinstance(df, pd.DataFrame):
        raise DataFormatError(
            f"{name} debe ser un pandas DataFrame",
            details={'tipo_recibido': type(df).__name__}
        )
    
    # Validar que no esté vacío
    if df.empty and min_rows > 0:
        raise DataValidationError(
            f"{name} está vacío",
            details={'filas_requeridas': min_rows}
        )
    
    # Validar número mínimo de filas
    if len(df) < min_rows:
        raise DataValidationError(
            f"{name} tiene menos filas que las requeridas",
            details={'filas_actuales': len(df), 'filas_requeridas': min_rows}
        )
    
    # Validar columnas requeridas
    if required_columns:
        missing_cols = set(required_columns) - set(df.columns)
        if missing_cols:
            raise DataFormatError(
                f"{name} no tiene las columnas requeridas",
                details={
                    'columnas_faltantes': list(missing_cols),
                    'columnas_requeridas': required_columns,
                    'columnas_actuales': list(df.columns)
                }
            )
    
    # Validar valores nulos
    if not allow_nulls and df.isnull().any().any():
        null_counts = df.isnull().sum()
        null_cols = null_counts[null_counts > 0].to_dict()
        raise DataValidationError(
            f"{name} contiene valores nulos",
            details={'columnas_con_nulos': null_cols}
        )
    
    return df


# ============================================================================
# VALIDACIÓN NUMÉRICA
# ============================================================================

def validate_numeric(
    value: Union[int, float, str],
    min_value: Optional[Union[int, float]] = None,
    max_value: Optional[Union[int, float]] = None,
    allow_negative: bool = True,
    name: str = "valor"
) -> Union[int, float]:
    """
    Valida y convierte un valor numérico.
    
    Args:
        value: Valor a validar
        min_value: Valor mínimo permitido (opcional)
        max_value: Valor máximo permitido (opcional)
        allow_negative: Si False, no permite valores negativos
        name: Nombre descriptivo del valor para mensajes de error
    
    Returns:
        Union[int, float]: Valor numérico validado
    
    Raises:
        InvalidParameterError: Si el valor no es válido
    
    Ejemplo:
        days = validate_numeric(days_input, min_value=1, max_value=365, name='días')
    """
    # Convertir a numérico si es string
    try:
        if isinstance(value, str):
            value = float(value) if '.' in value else int(value)
        elif not isinstance(value, (int, float)):
            raise ValueError(f"Tipo no soportado: {type(value)}")
    except (ValueError, TypeError) as e:
        raise InvalidParameterError(
            f"{name} debe ser un valor numérico",
            details={'valor': value, 'tipo': type(value).__name__, 'error': str(e)}
        )
    
    # Validar negativos
    if not allow_negative and value < 0:
        raise InvalidParameterError(
            f"{name} no puede ser negativo",
            details={'valor': value}
        )
    
    # Validar rango
    if min_value is not None and value < min_value:
        raise InvalidParameterError(
            f"{name} es menor que el mínimo permitido",
            details={'valor': value, 'minimo': min_value}
        )
    
    if max_value is not None and value > max_value:
        raise InvalidParameterError(
            f"{name} es mayor que el máximo permitido",
            details={'valor': value, 'maximo': max_value}
        )
    
    return value


# ============================================================================
# VALIDACIÓN DE STRINGS
# ============================================================================

def validate_string(
    value: str,
    min_length: int = 1,
    max_length: Optional[int] = None,
    allowed_chars: Optional[str] = None,
    pattern: Optional[str] = None,
    name: str = "valor"
) -> str:
    """
    Valida un string según criterios especificados.
    
    Args:
        value: String a validar
        min_length: Longitud mínima
        max_length: Longitud máxima (opcional)
        allowed_chars: Caracteres permitidos (opcional)
        pattern: Patrón regex que debe cumplir (opcional)
        name: Nombre descriptivo para mensajes de error
    
    Returns:
        str: String validado y stripped
    
    Raises:
        InvalidParameterError: Si el string no es válido
    
    Ejemplo:
        region = validate_string(region_input, min_length=2, max_length=50, name='región')
    """
    if not isinstance(value, str):
        raise InvalidParameterError(
            f"{name} debe ser un string",
            details={'tipo_recibido': type(value).__name__}
        )
    
    value = value.strip()
    
    # Validar longitud
    if len(value) < min_length:
        raise InvalidParameterError(
            f"{name} es demasiado corto",
            details={'longitud': len(value), 'minimo': min_length}
        )
    
    if max_length and len(value) > max_length:
        raise InvalidParameterError(
            f"{name} es demasiado largo",
            details={'longitud': len(value), 'maximo': max_length}
        )
    
    # Validar caracteres permitidos
    if allowed_chars:
        invalid_chars = set(value) - set(allowed_chars)
        if invalid_chars:
            raise InvalidParameterError(
                f"{name} contiene caracteres no permitidos",
                details={'caracteres_invalidos': list(invalid_chars)}
            )
    
    # Validar patrón regex
    if pattern:
        import re
        if not re.match(pattern, value):
            raise InvalidParameterError(
                f"{name} no cumple con el patrón requerido",
                details={'valor': value, 'patron': pattern}
            )
    
    return value


# ============================================================================
# VALIDADORES COMPUESTOS
# ============================================================================

def validate_query_params(
    metric: str,
    entity: str,
    start_date: str,
    end_date: str,
    valid_metrics: Optional[List[str]] = None,
    valid_entities: Optional[List[str]] = None,
    max_days: int = 365
) -> dict:
    """
    Valida todos los parámetros de una consulta a XM.
    
    Args:
        metric: Métrica a consultar
        entity: Entidad a consultar
        start_date: Fecha de inicio
        end_date: Fecha de fin
        valid_metrics: Lista de métricas válidas (opcional)
        valid_entities: Lista de entidades válidas (opcional)
        max_days: Número máximo de días en el rango
    
    Returns:
        dict: Diccionario con parámetros validados
    
    Raises:
        InvalidParameterError, DateRangeError: Si algún parámetro no es válido
    
    Ejemplo:
        params = validate_query_params(
            metric='DemaEner',
            entity='Sistema',
            start_date='2024-01-01',
            end_date='2024-12-31',
            max_days=365
        )
    """
    validated = {}
    
    validated['metric'] = validate_metric(metric, valid_metrics)
    validated['entity'] = validate_entity(entity, valid_entities)
    validated['start_date'], validated['end_date'] = validate_date_range(
        start_date, end_date, max_days=max_days
    )
    
    return validated


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("Testing validadores...\n")
    
    # Test 1: validate_date_range
    try:
        start, end = validate_date_range('2024-01-01', '2024-12-31', max_days=365)
        print(f"✓ validate_date_range: {start} - {end}")
    except Exception as e:
        print(f"✗ validate_date_range: {e}")
    
    # Test 2: validate_metric
    try:
        metric = validate_metric('DemaEner', valid_metrics=['DemaEner', 'GeneReal'])
        print(f"✓ validate_metric: {metric}")
    except Exception as e:
        print(f"✗ validate_metric: {e}")
    
    # Test 3: validate_dataframe
    try:
        df = pd.DataFrame({'Date': ['2024-01-01'], 'Value': [100]})
        validated_df = validate_dataframe(df, required_columns=['Date', 'Value'], min_rows=1)
        print(f"✓ validate_dataframe: {len(validated_df)} filas")
    except Exception as e:
        print(f"✗ validate_dataframe: {e}")
    
    # Test 4: validate_numeric
    try:
        days = validate_numeric(30, min_value=1, max_value=365, name='días')
        print(f"✓ validate_numeric: {days}")
    except Exception as e:
        print(f"✗ validate_numeric: {e}")
    
    # Test 5: Validación que debe fallar
    try:
        validate_date_range('2024-12-31', '2024-01-01')  # Orden invertido
        print("✗ validate_date_range: Debería haber fallado")
    except DateRangeError:
        print("✓ validate_date_range: Error detectado correctamente")
    
    print("\n✅ Todos los validadores funcionan correctamente")
