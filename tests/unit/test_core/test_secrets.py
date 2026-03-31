"""
Tests unitarios para core.secrets
Fase 3 - Testing y Calidad
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
from cryptography.fernet import Fernet

# Clave de prueba válida para Fernet
TEST_FERNET_KEY = Fernet.generate_key().decode()


class TestSecretManagerInitialization:
    """Tests para inicialización de SecretManager."""
    
    def test_secret_manager_import(self):
        """Test que SecretManager se puede importar."""
        from core.secrets import SecretManager
        assert SecretManager is not None
    
    def test_secret_manager_init_with_temp_dir(self):
        """Test inicialización con directorio temporal."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            key_path = Path(tmpdir) / ".vault_key"
            
            # Crear con clave explícita
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            assert sm is not None
            assert sm.vault_path == vault_path
    
    def test_secret_manager_singleton(self):
        """Test que get_secret_manager retorna singleton."""
        from core.secrets import get_secret_manager
        
        sm1 = get_secret_manager()
        sm2 = get_secret_manager()
        
        assert sm1 is sm2


class TestSecretOperations:
    """Tests para operaciones de secrets."""
    
    def test_set_and_get_secret(self):
        """Test set_secret y get_secret."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            # Guardar secret
            sm.set_secret("TEST_KEY", "test_value")
            
            # Recuperar secret
            value = sm.get_secret("TEST_KEY")
            
            assert value == "test_value"
    
    def test_get_secret_not_found(self):
        """Test get_secret retorna default cuando no existe."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            # Recuperar secret que no existe
            value = sm.get_secret("NON_EXISTENT", default="default_value")
            
            assert value == "default_value"
    
    def test_get_secret_no_default(self):
        """Test get_secret retorna None cuando no existe y no hay default."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            value = sm.get_secret("NON_EXISTENT")
            
            assert value is None
    
    def test_list_secrets_empty(self):
        """Test list_secrets con vault vacío."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            secrets = sm.list_secrets()
            
            assert secrets == []
    
    def test_list_secrets_with_data(self):
        """Test list_secrets con datos."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            sm.set_secret("KEY1", "value1")
            sm.set_secret("KEY2", "value2")
            
            secrets = sm.list_secrets()
            
            assert "KEY1" in secrets
            assert "KEY2" in secrets
            assert len(secrets) == 2
    
    def test_delete_secret(self):
        """Test delete_secret."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            sm.set_secret("TO_DELETE", "value")
            assert sm.get_secret("TO_DELETE") == "value"
            
            result = sm.delete_secret("TO_DELETE")
            assert result is True
            
            assert sm.get_secret("TO_DELETE") is None
    
    def test_delete_secret_not_found(self):
        """Test delete_secret retorna False cuando no existe."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            result = sm.delete_secret("NON_EXISTENT")
            
            assert result is False


class TestGetSecretFunction:
    """Tests para función get_secret."""
    
    def test_get_secret_function(self):
        """Test función de conveniencia get_secret."""
        from core.secrets import get_secret, SecretManager, _secret_manager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Parchar el vault path
            with patch('core.secrets.VAULT_FILE', Path(tmpdir) / ".env.vault"):
                with patch('core.secrets.KEY_FILE', Path(tmpdir) / ".vault_key"):
                    # Limpiar singleton para forzar recreación
                    import core.secrets
                    original_sm = core.secrets._secret_manager
                    core.secrets._secret_manager = None
                    
                    try:
                        # Crear nuevo vault con SecretManager
                        sm = SecretManager()
                        sm.set_secret("TEST_KEY", "test_value")
                        
                        # Usar función global (debería usar el mismo sm)
                        core.secrets._secret_manager = sm
                        value = get_secret("TEST_KEY")
                        
                        assert value == "test_value"
                    finally:
                        # Restaurar singleton
                        core.secrets._secret_manager = original_sm


class TestSecretsCompat:
    """Tests para clase SecretsCompat."""
    
    def test_secrets_compat_reads_vault(self):
        """Test SecretsCompat lee desde vault."""
        from core.secrets import SecretsCompat, SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            sm.set_secret("COMPAT_KEY", "compat_value")
            
            compat = SecretsCompat()
            # Parchar el secret manager interno
            compat._sm = sm
            
            value = compat.get("COMPAT_KEY")
            
            assert value == "compat_value"
    
    def test_secrets_compat_fallback_env(self):
        """Test SecretsCompat hace fallback a variable de entorno."""
        from core.secrets import SecretsCompat
        
        compat = SecretsCompat()
        
        # Establecer variable de entorno
        with patch.dict(os.environ, {"ENV_TEST_KEY": "env_value"}):
            value = compat.get("ENV_TEST_KEY")
            
            assert value == "env_value"


class TestVaultFileOperations:
    """Tests para operaciones de archivo de vault."""
    
    def test_vault_file_created(self):
        """Test que el archivo vault se crea al guardar secret."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            sm.set_secret("TEST", "value")
            
            assert vault_path.exists()
    
    def test_vault_file_is_encrypted(self):
        """Test que el archivo vault está cifrado."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            sm.set_secret("TEST", "value")
            
            # Leer contenido crudo
            content = vault_path.read_bytes()
            
            # No debería ser texto plano
            assert b"TEST=value" not in content
            
            # Debería tener formato Fernet (gAAAA...)
            assert content.startswith(b"gAAAA")


class TestErrorHandling:
    """Tests para manejo de errores."""
    
    def test_get_secret_corrupted_vault(self):
        """Test get_secret maneja vault corrupto."""
        from core.secrets import SecretManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / ".env.vault"
            
            # Crear archivo corrupto
            vault_path.write_bytes(b"corrupted_data")
            
            sm = SecretManager(vault_path=vault_path, key=TEST_FERNET_KEY)
            
            # Debería retornar default, no lanzar excepción
            value = sm.get_secret("ANY_KEY", default="default")
            
            assert value == "default"
