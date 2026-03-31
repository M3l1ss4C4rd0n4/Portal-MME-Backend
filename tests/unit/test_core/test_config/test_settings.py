"""
Tests unitarios para core.config.Settings
Fase 3 - Testing y Calidad
"""

import pytest
import os
from pathlib import Path


class TestSettingsBasic:
    """Tests básicos para Settings."""
    
    def test_settings_import(self):
        """Test que Settings se puede importar."""
        from core.config import Settings
        assert Settings is not None
    
    def test_settings_default_values(self):
        """Test que Settings tiene valores por defecto correctos."""
        from core.config import Settings
        
        # Limpiar variable de entorno para test
        import os
        original_env = os.environ.get('DASH_ENV')
        if 'DASH_ENV' in os.environ:
            del os.environ['DASH_ENV']
        
        try:
            settings = Settings()
            
            # Verificar valores por defecto
            assert settings.DASH_ENV == "production"
            assert settings.DASH_DEBUG is False
            assert settings.DASH_PORT == 8050
            assert settings.POSTGRES_PORT == 5432
            assert settings.REDIS_PORT == 6379
        finally:
            # Restaurar variable de entorno
            if original_env:
                os.environ['DASH_ENV'] = original_env
    
    def test_settings_database_url(self):
        """Test que DATABASE_URL se construye correctamente."""
        from core.config import Settings
        
        settings = Settings()
        
        # Verificar que DATABASE_URL contiene los componentes
        assert "postgresql://" in settings.DATABASE_URL
        assert settings.POSTGRES_HOST in settings.DATABASE_URL
        assert str(settings.POSTGRES_PORT) in settings.DATABASE_URL
        assert settings.POSTGRES_DB in settings.DATABASE_URL


class TestSettingsAPI:
    """Tests para configuración de API."""
    
    def test_api_key_enabled_default(self):
        """Test que API_KEY_ENABLED está habilitado por defecto."""
        from core.config import Settings
        
        settings = Settings()
        assert settings.API_KEY_ENABLED is True
    
    def test_api_rate_limit(self):
        """Test que API_RATE_LIMIT tiene formato correcto."""
        from core.config import Settings
        
        settings = Settings()
        assert "/" in settings.API_RATE_LIMIT
        assert "minute" in settings.API_RATE_LIMIT or "hour" in settings.API_RATE_LIMIT
    
    def test_cors_origins(self):
        """Test que CORS_ORIGINS es una lista."""
        from core.config import Settings
        
        settings = Settings()
        origins = settings.API_CORS_ORIGINS
        
        assert isinstance(origins, list)
        assert len(origins) > 0


class TestSettingsPaths:
    """Tests para rutas de Settings."""
    
    def test_base_dir_exists(self):
        """Test que BASE_DIR existe."""
        from core.config import Settings
        
        settings = Settings()
        
        assert settings.BASE_DIR.exists()
        assert settings.BASE_DIR.is_dir()
    
    def test_logs_dir(self):
        """Test que LOGS_DIR se construye correctamente."""
        from core.config import Settings
        
        settings = Settings()
        
        assert "logs" in str(settings.LOGS_DIR)
    
    def test_backup_dir(self):
        """Test que BACKUP_DIR se construye correctamente."""
        from core.config import Settings
        
        settings = Settings()
        
        assert "backup" in str(settings.BACKUP_DIR).lower()


class TestSettingsValidation:
    """Tests para validación de Settings."""
    
    def test_gunicorn_workers_count(self):
        """Test que gunicorn_workers_count retorna un entero positivo."""
        from core.config import Settings
        
        settings = Settings()
        workers = settings.gunicorn_workers_count
        
        assert isinstance(workers, int)
        assert workers > 0
    
    def test_api_keys_list(self):
        """Test que api_keys_list es una lista."""
        from core.config import Settings
        
        settings = Settings()
        keys = settings.api_keys_list
        
        assert isinstance(keys, list)
        assert len(keys) >= 1


class TestSettingsML:
    """Tests para configuración de ML."""
    
    def test_ml_prediction_days(self):
        """Test que ML_PREDICTION_DAYS es positivo."""
        from core.config import Settings
        
        settings = Settings()
        assert settings.ML_PREDICTION_DAYS > 0
    
    def test_ml_confidence_interval(self):
        """Test que ML_CONFIDENCE_INTERVAL está entre 0 y 1."""
        from core.config import Settings
        
        settings = Settings()
        assert 0 < settings.ML_CONFIDENCE_INTERVAL < 1


class TestSettingsEnvironment:
    """Tests para detección de ambiente."""
    
    def test_is_development(self):
        """Test función is_development."""
        from core.config import is_development, settings
        
        # En ambiente de test, debería ser False
        if settings.DASH_ENV == "development":
            assert is_development() is True
        else:
            assert is_development() is False
    
    def test_is_production(self):
        """Test función is_production."""
        from core.config import is_production, settings
        
        # En ambiente de test, depende de DASH_ENV
        if settings.DASH_ENV == "production":
            assert is_production() is True
        else:
            assert is_production() is False


class TestSettingsConstants:
    """Tests para constantes de settings."""
    
    def test_cargo_transmision_positive(self):
        """Test que CARGO_TRANSMISION_COP_KWH es positivo."""
        from core.config import Settings
        
        settings = Settings()
        assert settings.CARGO_TRANSMISION_COP_KWH > 0
    
    def test_cargo_distribucion_positive(self):
        """Test que CARGO_DISTRIBUCION_COP_KWH es positivo."""
        from core.config import Settings
        
        settings = Settings()
        assert settings.CARGO_DISTRIBUCION_COP_KWH > 0
    
    def test_trm_ref_positive(self):
        """Test que TRM_REF_COP_USD es positivo."""
        from core.config import Settings
        
        settings = Settings()
        assert settings.TRM_REF_COP_USD > 0
