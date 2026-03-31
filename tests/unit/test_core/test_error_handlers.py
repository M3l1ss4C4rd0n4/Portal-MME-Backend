"""
Tests unitarios para core.error_handlers
Fase 3 - Testing y Calidad
"""

import pytest
import psycopg2
import requests
from unittest.mock import Mock


class TestDatabaseExceptions:
    """Tests para excepciones de base de datos."""
    
    def test_database_connection_error(self):
        """Test DatabaseConnectionError se puede lanzar y capturar."""
        from core.error_handlers import DatabaseConnectionError
        
        with pytest.raises(DatabaseConnectionError) as exc_info:
            raise DatabaseConnectionError("Connection failed")
        
        assert "Connection failed" in str(exc_info.value)
    
    def test_database_query_error(self):
        """Test DatabaseQueryError se puede lanzar y capturar."""
        from core.error_handlers import DatabaseQueryError
        
        with pytest.raises(DatabaseQueryError) as exc_info:
            raise DatabaseQueryError("Query failed")
        
        assert "Query failed" in str(exc_info.value)
    
    def test_database_integrity_error(self):
        """Test DatabaseIntegrityError se puede lanzar y capturar."""
        from core.error_handlers import DatabaseIntegrityError
        
        with pytest.raises(DatabaseIntegrityError) as exc_info:
            raise DatabaseIntegrityError("Constraint violation")
        
        assert "Constraint violation" in str(exc_info.value)


class TestAPIExceptions:
    """Tests para excepciones de API."""
    
    def test_api_connection_error(self):
        """Test APIConnectionError se puede lanzar y capturar."""
        from core.error_handlers import APIConnectionError
        
        with pytest.raises(APIConnectionError) as exc_info:
            raise APIConnectionError("API unreachable")
        
        assert "API unreachable" in str(exc_info.value)
    
    def test_api_response_error_with_status(self):
        """Test APIResponseError con código de estado."""
        from core.error_handlers import APIResponseError
        
        error = APIResponseError("Not found", status_code=404, response_body="Body")
        
        assert error.status_code == 404
        assert error.response_body == "Body"
    
    def test_api_timeout_error(self):
        """Test APITimeoutError se puede lanzar y capturar."""
        from core.error_handlers import APITimeoutError
        
        with pytest.raises(APITimeoutError) as exc_info:
            raise APITimeoutError("Request timeout")
        
        assert "Request timeout" in str(exc_info.value)


class TestDecorators:
    """Tests para decoradores de error handlers."""
    
    def test_safe_db_operation_success(self):
        """Test que safe_db_operation permite función exitosa."""
        from core.error_handlers import safe_db_operation
        
        @safe_db_operation("test_operation")
        def successful_operation():
            return "success"
        
        result = successful_operation()
        assert result == "success"
    
    def test_safe_db_operation_with_exception(self):
        """Test que safe_db_operation maneja excepciones."""
        from core.error_handlers import safe_db_operation, DatabaseQueryError
        
        @safe_db_operation("test_operation")
        def failing_operation():
            raise psycopg2.Error("DB Error")
        
        with pytest.raises(DatabaseQueryError):
            failing_operation()
    
    def test_safe_api_call_success(self):
        """Test que safe_api_call permite función exitosa."""
        from core.error_handlers import safe_api_call
        
        @safe_api_call("Test API")
        def successful_api_call():
            return {"data": "test"}
        
        result = successful_api_call()
        assert result == {"data": "test"}
    
    def test_safe_api_call_with_timeout(self):
        """Test que safe_api_call maneja timeout."""
        from core.error_handlers import safe_api_call, APITimeoutError
        
        @safe_api_call("Test API")
        def failing_api_call():
            raise requests.Timeout("Connection timeout")
        
        with pytest.raises(APITimeoutError):
            failing_api_call()


class TestContextManagers:
    """Tests para context managers."""
    
    def test_safe_db_context_success(self):
        """Test SafeDBContext con operación exitosa."""
        from core.error_handlers import SafeDBContext
        
        mock_conn = Mock()
        
        with SafeDBContext("INSERT test", mock_conn) as ctx:
            # Simular operación exitosa
            ctx.success()
        
        # Verificar que se llamó commit
        mock_conn.commit.assert_called_once()
    
    def test_safe_db_context_with_error(self):
        """Test SafeDBContext maneja errores."""
        from core.error_handlers import SafeDBContext, DatabaseQueryError
        import psycopg2
        
        mock_conn = Mock()
        
        with pytest.raises(DatabaseQueryError):
            with SafeDBContext("INSERT test", mock_conn) as ctx:
                raise psycopg2.Error("DB Error")


class TestHandleDBError:
    """Tests para función handle_db_error."""
    
    def test_handle_operational_error(self):
        """Test handle_db_error con OperationalError."""
        from core.error_handlers import handle_db_error, DatabaseConnectionError
        
        error = psycopg2.OperationalError("Connection refused")
        
        with pytest.raises(DatabaseConnectionError):
            handle_db_error(error, operation="test_connection")
    
    def test_handle_integrity_error(self):
        """Test handle_db_error con IntegrityError."""
        from core.error_handlers import handle_db_error, DatabaseIntegrityError
        
        error = psycopg2.IntegrityError("Unique constraint")
        
        with pytest.raises(DatabaseIntegrityError):
            handle_db_error(error, operation="test_insert")
    
    def test_handle_programming_error(self):
        """Test handle_db_error con ProgrammingError."""
        from core.error_handlers import handle_db_error, DatabaseQueryError
        
        error = psycopg2.ProgrammingError("Syntax error")
        
        with pytest.raises(DatabaseQueryError):
            handle_db_error(error, operation="test_query")


class TestHandleAPIError:
    """Tests para función handle_api_error."""
    
    def test_handle_timeout(self):
        """Test handle_api_error con Timeout."""
        from core.error_handlers import handle_api_error, APITimeoutError
        
        error = requests.Timeout("Request timeout")
        
        with pytest.raises(APITimeoutError):
            handle_api_error(error, api_name="XM API")
    
    def test_handle_connection_error(self):
        """Test handle_api_error con ConnectionError."""
        from core.error_handlers import handle_api_error, APIConnectionError
        
        error = requests.ConnectionError("No route to host")
        
        with pytest.raises(APIConnectionError):
            handle_api_error(error, api_name="XM API")
    
    def test_handle_http_error(self):
        """Test handle_api_error con HTTPError."""
        from core.error_handlers import handle_api_error, APIResponseError
        
        mock_response = Mock()
        mock_response.status_code = 500
        
        error = requests.HTTPError("Server error")
        error.response = mock_response
        
        with pytest.raises(APIResponseError) as exc_info:
            handle_api_error(error, api_name="XM API")
        
        assert exc_info.value.status_code == 500


class TestUtilityFunctions:
    """Tests para funciones de utilidad."""
    
    def test_log_error_with_context(self, caplog):
        """Test log_error_with_context loguea correctamente."""
        from core.error_handlers import log_error_with_context
        import logging
        
        error = ValueError("Test error")
        
        with caplog.at_level(logging.ERROR):
            log_error_with_context(error, context="TEST_CONTEXT", extra_data={"key": "value"})
        
        assert "TEST_CONTEXT" in caplog.text
        assert "Test error" in caplog.text
    
    def test_safe_execute_success(self):
        """Test safe_execute con función exitosa."""
        from core.error_handlers import safe_execute
        
        def success_func():
            return "result"
        
        result = safe_execute(success_func, default="default")
        assert result == "result"
    
    def test_safe_execute_with_error(self):
        """Test safe_execute con función que falla."""
        from core.error_handlers import safe_execute
        
        def failing_func():
            raise ValueError("Error")
        
        result = safe_execute(failing_func, default="default_value")
        assert result == "default_value"
