"""
Validador SQL para prevenir inyección de código.

Este módulo proporciona funciones para validar nombres de tablas y columnas
antes de usarlos en queries dinámicas, previniendo así ataques de SQL injection.
"""

import re
from typing import Set, Optional


class SQLValidationError(Exception):
    """Error de validación SQL."""
    pass


# Tablas permitidas en la base de datos
ALLOWED_TABLES: Set[str] = {
    # Tablas principales de métricas
    'metrics',
    'metrics_hourly',
    'metrics_daily',
    'metrics_monthly',
    
    # Tablas de predicciones
    'predictions',
    'prediction_models',
    'model_performance',
    
    # Tablas de entidades
    'entities',
    'entities_types',
    'departments',
    'municipalities',
    
    # Tablas de usuarios y permisos
    'users',
    'user_roles',
    'roles',
    'permissions',
    
    # Tablas de reportes
    'reports',
    'report_templates',
    'scheduled_reports',
    
    # Tablas de notificaciones
    'notifications',
    'notification_templates',
    'notification_logs',
    
    # Tablas de ETL
    'etl_jobs',
    'etl_logs',
    'data_sources',
    
    # Tablas de auditoría
    'audit_logs',
    'user_sessions',
    'login_attempts',
    
    # Tablas específicas del dominio energético
    'subsidies',
    'tariffs',
    'contracts',
    'commercial_agents',
    'injection_points',
    'meter_readings',
    'consumption_data',
    'generation_data',

    # Tablas de subsidios DDE (schema: subsidios)
    'subsidios_pagos',
    'subsidios_empresas',
    'subsidios_mapa',
    'subsidios_import_log',
    'subsidios_usuarios_autorizados',
    'subsidios_audit_log',
    'subsidios.subsidios_pagos',
    'subsidios.subsidios_empresas',
    'subsidios.subsidios_mapa',
    'subsidios.subsidios_import_log',
    'subsidios.subsidios_usuarios_autorizados',
    'subsidios.subsidios_audit_log',

    # Tablas de supervisión (schema: supervision)
    'supervision.contratos',
    'supervision.contratos_liquidacion',
    'supervision.contratos_ejecucion',

    # Tablas de comunidades energéticas (schema: comunidades)
    'comunidades.base',
    'comunidades.implementadas',

    # Tablas de presupuesto (schema: presupuesto)
    'presupuesto.resumen',
    'presupuesto.compromisos_mensual',

    # Tablas de contratos OR (schema: contratos_or)
    'contratos_or.seguimiento',

    # Tablas de configuración
    'system_config',
    'app_settings',
    'feature_flags',
}

# Columnas permitidas para ordenamiento/filtrado dinámico
ALLOWED_COLUMNS: Set[str] = {
    'id',
    'created_at',
    'updated_at',
    'deleted_at',
    'is_active',
    'status',
    'entity_id',
    'metric_id',
    'user_id',
    'date',
    'timestamp',
    'value',
    'type',
    'category',
    'name',
    'code',
    'description',
    'start_date',
    'end_date',
    'period',
    'department',
    'municipality',
    'region',
    'zone',
    'level',
    'parent_id',
    'external_id',
    'source',
}

# Patrón para validar identificadores SQL válidos
VALID_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def validate_table_name(table_name: str, allowed_tables: Optional[Set[str]] = None) -> bool:
    """
    Valida que el nombre de tabla esté en la whitelist.
    
    Args:
        table_name: Nombre de la tabla a validar
        allowed_tables: Set opcional de tablas permitidas (usa ALLOWED_TABLES por defecto)
        
    Returns:
        True si la tabla está permitida
        
    Raises:
        SQLValidationError: Si el nombre de tabla no es válido o no está permitido
    """
    if not table_name:
        raise SQLValidationError("El nombre de tabla no puede estar vacío")
    
    # Validar formato de identificador SQL
    if not VALID_IDENTIFIER_PATTERN.match(table_name):
        raise SQLValidationError(
            f"Nombre de tabla inválido: '{table_name}'. "
            "Debe comenzar con letra o underscore, seguido de letras, números o underscores."
        )
    
    # Validar contra whitelist
    tables = allowed_tables or ALLOWED_TABLES
    if table_name not in tables:
        raise SQLValidationError(
            f"Tabla no permitida: '{table_name}'. "
            f"Tablas permitidas: {sorted(tables)}"
        )
    
    return True


def validate_column_name(column_name: str, allowed_columns: Optional[Set[str]] = None) -> bool:
    """
    Valida que el nombre de columna esté en la whitelist.
    
    Args:
        column_name: Nombre de la columna a validar
        allowed_columns: Set opcional de columnas permitidas (usa ALLOWED_COLUMNS por defecto)
        
    Returns:
        True si la columna está permitida
        
    Raises:
        SQLValidationError: Si el nombre de columna no es válido o no está permitido
    """
    if not column_name:
        raise SQLValidationError("El nombre de columna no puede estar vacío")
    
    # Validar formato de identificador SQL
    if not VALID_IDENTIFIER_PATTERN.match(column_name):
        raise SQLValidationError(
            f"Nombre de columna inválido: '{column_name}'"
        )
    
    # Validar contra whitelist
    columns = allowed_columns or ALLOWED_COLUMNS
    if column_name not in columns:
        raise SQLValidationError(
            f"Columna no permitida: '{column_name}'"
        )
    
    return True


def safe_table_query(table_name: str, base_query: str, allowed_tables: Optional[Set[str]] = None) -> str:
    """
    Genera una query segura con el nombre de tabla validado.
    
    Args:
        table_name: Nombre de la tabla a usar en la query
        base_query: Query base con placeholder {table} (ej: "SELECT * FROM {table}")
        allowed_tables: Set opcional de tablas permitidas
        
    Returns:
        Query con el nombre de tabla insertado de forma segura
        
    Raises:
        SQLValidationError: Si el nombre de tabla no es válido
        
    Example:
        >>> query = safe_table_query("metrics", "SELECT * FROM {table} WHERE id = %s")
        >>> print(query)
        SELECT * FROM metrics WHERE id = %s
    """
    validate_table_name(table_name, allowed_tables)
    return base_query.format(table=table_name)


def sanitize_order_by(order_by: str, allowed_columns: Optional[Set[str]] = None) -> str:
    """
    Sanitiza una cláusula ORDER BY.
    
    Args:
        order_by: String con columna y opcionalmente dirección (ej: "created_at DESC")
        allowed_columns: Set de columnas permitidas
        
    Returns:
        String sanitizado seguro para usar en ORDER BY
        
    Raises:
        SQLValidationError: Si la cláusula no es válida
    """
    if not order_by:
        return ""
    
    parts = order_by.strip().split()
    column = parts[0]
    
    # Validar columna
    validate_column_name(column, allowed_columns)
    
    # Validar dirección si existe
    if len(parts) > 1:
        direction = parts[1].upper()
        if direction not in ('ASC', 'DESC'):
            raise SQLValidationError(f"Dirección de ordenamiento inválida: {direction}")
        return f"{column} {direction}"
    
    return column


def sanitize_limit(limit: any) -> int:
    """
    Valida y sanitiza un valor LIMIT.
    
    Args:
        limit: Valor a usar como LIMIT
        
    Returns:
        Entero válido para LIMIT
        
    Raises:
        SQLValidationError: Si el valor no es válido
    """
    try:
        limit_int = int(limit)
    except (ValueError, TypeError):
        raise SQLValidationError(f"Valor LIMIT inválido: {limit}")
    
    if limit_int < 0:
        raise SQLValidationError(f"LIMIT no puede ser negativo: {limit_int}")
    
    if limit_int > 100000:  # Máximo razonable
        raise SQLValidationError(f"LIMIT excede el máximo permitido: {limit_int}")
    
    return limit_int


def validate_where_conditions(conditions: dict, allowed_columns: Optional[Set[str]] = None) -> list:
    """
    Valida condiciones WHERE dinámicas.
    
    Args:
        conditions: Diccionario de condiciones {columna: valor}
        allowed_columns: Set de columnas permitidas
        
    Returns:
        Lista de tuplas (columna, placeholder) para construir WHERE seguro
        
    Example:
        >>> validate_where_conditions({"status": "active", "type": "metric"})
        [("status", "%s"), ("type", "%s")]
    """
    validated = []
    columns = allowed_columns or ALLOWED_COLUMNS
    
    for column in conditions.keys():
        if column not in columns:
            raise SQLValidationError(f"Columna no permitida en WHERE: {column}")
        validated.append((column, "%s"))
    
    return validated


# Decorador para validación automática
def validate_table_arg(arg_name: str = 'table_name'):
    """
    Decorador que valida automáticamente el argumento de nombre de tabla.
    
    Args:
        arg_name: Nombre del argumento a validar
        
    Example:
        >>> @validate_table_arg('table')
        ... def get_data(table: str, limit: int = 100):
        ...     query = f"SELECT * FROM {table} LIMIT %s"
        ...     return query
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            table = kwargs.get(arg_name)
            if table:
                validate_table_name(table)
            return func(*args, **kwargs)
        return wrapper
    return decorator
