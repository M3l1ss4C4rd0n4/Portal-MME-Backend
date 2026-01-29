"""
Utilidades para manejo y procesamiento de datos
Funciones comunes para trabajar con pandas, validación y transformación
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any, Union
from pathlib import Path


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Convierte un valor a float de forma segura
    
    Args:
        value: Valor a convertir
        default: Valor por defecto si la conversión falla
    
    Returns:
        float: Valor convertido o default
    
    Ejemplo:
        >>> safe_float("123.45")
        123.45
        >>> safe_float("invalid", 0.0)
        0.0
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Convierte un valor a int de forma segura
    
    Args:
        value: Valor a convertir
        default: Valor por defecto si la conversión falla
    
    Returns:
        int: Valor convertido o default
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def clean_column_name(name: str) -> str:
    """
    Limpia nombre de columna (quita espacios, caracteres especiales)
    
    Args:
        name: Nombre de columna original
    
    Returns:
        str: Nombre limpio
    
    Ejemplo:
        >>> clean_column_name("Valor Total (COP)")
        'valor_total_cop'
    """
    # Minúsculas
    name = name.lower()
    
    # Reemplazar espacios y guiones por underscore
    name = name.replace(' ', '_').replace('-', '_')
    
    # Quitar paréntesis y otros caracteres especiales
    name = name.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
    name = name.replace('á', 'a').replace('é', 'e').replace('í', 'i')
    name = name.replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    
    # Quitar caracteres no alfanuméricos
    name = ''.join(c for c in name if c.isalnum() or c == '_')
    
    # Quitar underscores múltiples
    while '__' in name:
        name = name.replace('__', '_')
    
    # Quitar underscores al inicio y final
    name = name.strip('_')
    
    return name


def clean_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia nombres de columnas de un DataFrame
    
    Args:
        df: DataFrame original
    
    Returns:
        pd.DataFrame: DataFrame con columnas limpias
    """
    df = df.copy()
    df.columns = [clean_column_name(col) for col in df.columns]
    return df


def remove_duplicates(
    df: pd.DataFrame,
    subset: Optional[List[str]] = None,
    keep: str = 'first'
) -> pd.DataFrame:
    """
    Elimina duplicados de un DataFrame
    
    Args:
        df: DataFrame original
        subset: Columnas a considerar para duplicados (None = todas)
        keep: Qué duplicado mantener ('first', 'last', False)
    
    Returns:
        pd.DataFrame: DataFrame sin duplicados
    """
    return df.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)


def fill_missing_dates(
    df: pd.DataFrame,
    date_column: str,
    freq: str = 'D',
    fill_method: Optional[str] = 'ffill'
) -> pd.DataFrame:
    """
    Rellena fechas faltantes en un DataFrame
    
    Args:
        df: DataFrame con columna de fechas
        date_column: Nombre de la columna de fecha
        freq: Frecuencia ('D' diaria, 'H' horaria, 'M' mensual)
        fill_method: Método de relleno ('ffill', 'bfill', None)
    
    Returns:
        pd.DataFrame: DataFrame con fechas completas
    """
    df = df.copy()
    
    # Asegurar que la columna es datetime
    df[date_column] = pd.to_datetime(df[date_column])
    
    # Crear rango completo de fechas
    date_range = pd.date_range(
        start=df[date_column].min(),
        end=df[date_column].max(),
        freq=freq
    )
    
    # Reindexar con fechas completas
    df = df.set_index(date_column).reindex(date_range)
    
    # Rellenar valores faltantes
    if fill_method:
        df = df.fillna(method=fill_method)
    
    # Resetear índice
    df = df.reset_index()
    df = df.rename(columns={'index': date_column})
    
    return df


def filter_outliers(
    df: pd.DataFrame,
    column: str,
    method: str = 'iqr',
    threshold: float = 1.5
) -> pd.DataFrame:
    """
    Filtra outliers de una columna
    
    Args:
        df: DataFrame original
        column: Columna a filtrar
        method: Método ('iqr', 'zscore')
        threshold: Umbral (1.5 para IQR, 3.0 para z-score)
    
    Returns:
        pd.DataFrame: DataFrame sin outliers
    """
    df = df.copy()
    
    if method == 'iqr':
        Q1 = df[column].quantile(0.25)
        Q3 = df[column].quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - threshold * IQR
        upper_bound = Q3 + threshold * IQR
        
        mask = (df[column] >= lower_bound) & (df[column] <= upper_bound)
        
    elif method == 'zscore':
        mean = df[column].mean()
        std = df[column].std()
        
        z_scores = np.abs((df[column] - mean) / std)
        mask = z_scores < threshold
    
    else:
        raise ValueError(f"Método no soportado: {method}")
    
    return df[mask].reset_index(drop=True)


def aggregate_by_period(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    period: str = 'D',
    agg_func: str = 'sum'
) -> pd.DataFrame:
    """
    Agrega datos por período
    
    Args:
        df: DataFrame original
        date_column: Columna de fecha
        value_column: Columna de valor a agregar
        period: Período ('D' diario, 'W' semanal, 'M' mensual, 'Y' anual)
        agg_func: Función de agregación ('sum', 'mean', 'max', 'min')
    
    Returns:
        pd.DataFrame: DataFrame agregado
    """
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column])
    
    # Agrupar por período
    df = df.set_index(date_column)
    
    if agg_func == 'sum':
        result = df[value_column].resample(period).sum()
    elif agg_func == 'mean':
        result = df[value_column].resample(period).mean()
    elif agg_func == 'max':
        result = df[value_column].resample(period).max()
    elif agg_func == 'min':
        result = df[value_column].resample(period).min()
    else:
        raise ValueError(f"Función de agregación no soportada: {agg_func}")
    
    return result.reset_index()


def calculate_percentage_change(
    df: pd.DataFrame,
    column: str,
    periods: int = 1
) -> pd.DataFrame:
    """
    Calcula cambio porcentual
    
    Args:
        df: DataFrame original
        column: Columna a calcular
        periods: Períodos hacia atrás
    
    Returns:
        pd.DataFrame: DataFrame con columna de cambio porcentual
    """
    df = df.copy()
    df[f'{column}_pct_change'] = df[column].pct_change(periods=periods) * 100
    return df


def normalize_column(
    df: pd.DataFrame,
    column: str,
    method: str = 'minmax'
) -> pd.DataFrame:
    """
    Normaliza una columna
    
    Args:
        df: DataFrame original
        column: Columna a normalizar
        method: Método ('minmax' o 'zscore')
    
    Returns:
        pd.DataFrame: DataFrame con columna normalizada
    """
    df = df.copy()
    
    if method == 'minmax':
        # Min-Max scaling [0, 1]
        min_val = df[column].min()
        max_val = df[column].max()
        df[f'{column}_normalized'] = (df[column] - min_val) / (max_val - min_val)
    
    elif method == 'zscore':
        # Z-score normalization
        mean = df[column].mean()
        std = df[column].std()
        df[f'{column}_normalized'] = (df[column] - mean) / std
    
    else:
        raise ValueError(f"Método no soportado: {method}")
    
    return df


def export_to_excel(
    df: pd.DataFrame,
    filename: Union[str, Path],
    sheet_name: str = 'Datos',
    **kwargs
) -> None:
    """
    Exporta DataFrame a Excel con formato
    
    Args:
        df: DataFrame a exportar
        filename: Nombre del archivo
        sheet_name: Nombre de la hoja
        **kwargs: Argumentos adicionales para to_excel()
    """
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False, **kwargs)


def get_dataframe_info(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Obtiene información resumida de un DataFrame
    
    Args:
        df: DataFrame a analizar
    
    Returns:
        Dict: Información del DataFrame
    """
    return {
        'rows': len(df),
        'columns': len(df.columns),
        'column_names': df.columns.tolist(),
        'dtypes': df.dtypes.to_dict(),
        'missing_values': df.isnull().sum().to_dict(),
        'memory_usage_mb': df.memory_usage(deep=True).sum() / (1024 * 1024),
    }


def validate_required_columns(
    df: pd.DataFrame,
    required_columns: List[str]
) -> bool:
    """
    Valida que un DataFrame tenga las columnas requeridas
    
    Args:
        df: DataFrame a validar
        required_columns: Lista de columnas requeridas
    
    Returns:
        bool: True si tiene todas las columnas
    
    Raises:
        ValueError: Si faltan columnas
    """
    missing = set(required_columns) - set(df.columns)
    
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}")
    
    return True


def chunk_dataframe(
    df: pd.DataFrame,
    chunk_size: int = 1000
) -> List[pd.DataFrame]:
    """
    Divide un DataFrame en chunks más pequeños
    
    Args:
        df: DataFrame a dividir
        chunk_size: Tamaño de cada chunk
    
    Returns:
        List[pd.DataFrame]: Lista de chunks
    """
    return [df[i:i + chunk_size] for i in range(0, len(df), chunk_size)]


if __name__ == "__main__":
    # Tests
    print("Testing data utilities...")
    
    # Test safe conversions
    assert safe_float("123.45") == 123.45
    assert safe_float("invalid", 0.0) == 0.0
    assert safe_int("42") == 42
    
    # Test clean column name
    assert clean_column_name("Valor Total (COP)") == "valor_total_cop"
    
    # Test DataFrame operations
    df = pd.DataFrame({
        'Fecha': ['2026-01-01', '2026-01-02'],
        'Valor Total (COP)': [100, 200]
    })
    
    df_clean = clean_dataframe_columns(df)
    assert 'valor_total_cop' in df_clean.columns
    
    print("✅ Data utilities test passed")
