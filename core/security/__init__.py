"""
Módulo de seguridad para el Portal Energético MME.

Proporciona:
- Validación de entradas SQL y protección contra inyección
- Gestión segura de secretos via Vault
"""

from .sql_validator import (
    validate_table_name,
    validate_column_name,
    safe_table_query,
    SQLValidationError,
    ALLOWED_TABLES,
    ALLOWED_COLUMNS
)

from .vault import (
    Vault,
    get_vault,
    init_vault
)

__all__ = [
    'validate_table_name',
    'validate_column_name', 
    'safe_table_query',
    'SQLValidationError',
    'ALLOWED_TABLES',
    'ALLOWED_COLUMNS',
    'Vault',
    'get_vault',
    'init_vault'
]
