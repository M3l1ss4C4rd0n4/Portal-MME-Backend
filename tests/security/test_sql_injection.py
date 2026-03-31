"""
Tests de seguridad contra SQL Injection.

Verifica que el sistema de validación SQL proteja contra:
- Inyección de comandos DROP/DELETE
- Inyección de UNION SELECT
- Inyección de comentarios
- Bypass de autenticación con OR 1=1
"""

import pytest
from core.security.sql_validator import (
    validate_table_name,
    validate_column_name,
    safe_table_query,
    sanitize_limit,
    sanitize_order_by,
    SQLValidationError,
    ALLOWED_TABLES,
    ALLOWED_COLUMNS
)


class TestSQLTableValidation:
    """Tests para validación de nombres de tabla."""
    
    def test_valid_table_name(self):
        """Nombres de tabla válidos deben ser aceptados."""
        valid_tables = ['metrics', 'users', 'predictions', 'audit_logs']
        for table in valid_tables:
            assert validate_table_name(table) is True
    
    def test_empty_table_name(self):
        """Nombre vacío debe rechazarse."""
        with pytest.raises(SQLValidationError, match="no puede estar vacío"):
            validate_table_name("")
    
    def test_none_table_name(self):
        """None debe rechazarse."""
        with pytest.raises(SQLValidationError):
            validate_table_name(None)
    
    def test_sql_injection_drop_table(self):
        """Inyección DROP TABLE debe ser bloqueada."""
        malicious = "users; DROP TABLE users; --"
        with pytest.raises(SQLValidationError, match="inválido"):
            validate_table_name(malicious)
    
    def test_sql_injection_union_select(self):
        """Inyección UNION SELECT debe ser bloqueada."""
        malicious = "metrics UNION SELECT * FROM passwords"
        with pytest.raises(SQLValidationError):
            validate_table_name(malicious)
    
    def test_sql_injection_comment(self):
        """Inyección con comentarios debe ser bloqueada."""
        malicious = "users--"
        with pytest.raises(SQLValidationError):
            validate_table_name(malicious)
    
    def test_sql_injection_or_true(self):
        """Inyección OR 1=1 debe ser bloqueada."""
        malicious = "users WHERE 1=1 OR 1=1"
        with pytest.raises(SQLValidationError):
            validate_table_name(malicious)
    
    def test_sql_injection_special_chars(self):
        """Caracteres especiales deben ser bloqueados."""
        malicious_inputs = [
            "table; DELETE FROM users",
            "table' OR '1'='1",
            "table\"",
            "table\n",
            "table\t",
            "table;",
            "table'",
        ]
        for malicious in malicious_inputs:
            with pytest.raises(SQLValidationError):
                validate_table_name(malicious)
    
    def test_sql_injection_subquery(self):
        """Subqueries maliciosas deben ser bloqueadas."""
        malicious = "metrics WHERE id IN (SELECT id FROM admin)"
        with pytest.raises(SQLValidationError):
            validate_table_name(malicious)
    
    def test_case_sensitivity(self):
        """Los nombres de tabla son case-sensitive (PostgreSQL)."""
        # En PostgreSQL, los nombres sin comillas son lower-case
        # pero validamos exactamente como se proporcionan
        with pytest.raises(SQLValidationError):
            validate_table_name("METRICS")  # No está en ALLOWED_TABLES
    
    def test_table_not_in_whitelist(self):
        """Tabla no en whitelist debe ser rechazada."""
        with pytest.raises(SQLValidationError, match="no permitida"):
            validate_table_name("malicious_table")
        
        with pytest.raises(SQLValidationError):
            validate_table_name("users_backup")


class TestSQLColumnValidation:
    """Tests para validación de nombres de columna."""
    
    def test_valid_column_name(self):
        """Nombres de columna válidos deben ser aceptados."""
        valid_columns = ['id', 'created_at', 'status', 'value']
        for col in valid_columns:
            assert validate_column_name(col) is True
    
    def test_invalid_column_name(self):
        """Nombres de columna inválidos deben ser rechazados."""
        with pytest.raises(SQLValidationError):
            validate_column_name("password_hash; DROP TABLE")
        
        with pytest.raises(SQLValidationError):
            validate_column_name("id OR 1=1")


class TestSafeTableQuery:
    """Tests para safe_table_query."""
    
    def test_safe_query_generation(self):
        """Query segura debe generarse correctamente."""
        query = safe_table_query("metrics", "SELECT * FROM {table} WHERE id = %s")
        assert query == "SELECT * FROM metrics WHERE id = %s"
        assert "{table}" not in query
    
    def test_malicious_table_in_safe_query(self):
        """Tabla maliciosa debe ser rechazada en safe_table_query."""
        with pytest.raises(SQLValidationError):
            safe_table_query("users; DROP TABLE users", "SELECT * FROM {table}")


class TestSanitizeLimit:
    """Tests para sanitización de LIMIT."""
    
    def test_valid_limit(self):
        """Límites válidos deben ser aceptados."""
        assert sanitize_limit(10) == 10
        assert sanitize_limit("100") == 100
        assert sanitize_limit(1000) == 1000
    
    def test_negative_limit(self):
        """Límites negativos deben ser rechazados."""
        with pytest.raises(SQLValidationError, match="no puede ser negativo"):
            sanitize_limit(-1)
    
    def test_excessive_limit(self):
        """Límites excesivos deben ser rechazados."""
        with pytest.raises(SQLValidationError, match="excede el máximo"):
            sanitize_limit(999999)
    
    def test_invalid_limit_type(self):
        """Tipos inválidos deben ser rechazados."""
        with pytest.raises(SQLValidationError, match="inválido"):
            sanitize_limit("ten")
        
        with pytest.raises(SQLValidationError):
            sanitize_limit(None)


class TestSanitizeOrderBy:
    """Tests para sanitización de ORDER BY."""
    
    def test_valid_order_by(self):
        """ORDER BY válido debe ser aceptado."""
        assert sanitize_order_by("created_at") == "created_at"
        assert sanitize_order_by("created_at DESC") == "created_at DESC"
        assert sanitize_order_by("value ASC") == "value ASC"
    
    def test_invalid_column_in_order_by(self):
        """Columna inválida debe ser rechazada."""
        with pytest.raises(SQLValidationError):
            sanitize_order_by("1; DROP TABLE users")
    
    def test_invalid_direction(self):
        """Dirección inválida debe ser rechazada."""
        with pytest.raises(SQLValidationError, match="Dirección"):
            sanitize_order_by("created_at DROP")


class TestSQLInjectionVectors:
    """Tests para vectores específicos de inyección SQL."""
    
    @pytest.mark.parametrize("payload", [
        "users; DROP TABLE users; --",
        "users; DELETE FROM users; --",
        "users; UPDATE users SET admin=1; --",
        "users UNION SELECT * FROM passwords",
        "users' UNION SELECT null,null,null--",
        "users\" OR \"1\"=\"1",
        "users' OR '1'='1",
        "users' OR 1=1--",
        "users') OR ('1'='1",
        "users; INSERT INTO users VALUES ('hacker')",
        "users; EXEC xp_cmdshell 'dir'",
        "users; COPY (SELECT * FROM users) TO '/tmp/data'",
    ])
    def test_common_injection_payloads(self, payload):
        """Payloads comunes de inyección SQL deben ser bloqueados."""
        with pytest.raises(SQLValidationError):
            validate_table_name(payload)


class TestAllowedTablesList:
    """Tests para la lista de tablas permitidas."""
    
    def test_core_tables_present(self):
        """Tablas core deben estar en la whitelist."""
        core_tables = {'metrics', 'users', 'predictions', 'entities'}
        for table in core_tables:
            assert table in ALLOWED_TABLES, f"Tabla {table} no está en ALLOWED_TABLES"
    
    def test_no_empty_tables(self):
        """No debe haber tablas vacías en la whitelist."""
        for table in ALLOWED_TABLES:
            assert table, "Tabla vacía encontrada en ALLOWED_TABLES"
            assert isinstance(table, str), f"Tipo inválido para tabla: {type(table)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
