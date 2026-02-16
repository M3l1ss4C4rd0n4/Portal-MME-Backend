"""
Configuración centralizada del WhatsApp Bot
"""
import os
from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración del WhatsApp Bot"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ═══════════════════════════════════════════════════════════
    # WhatsApp Provider
    # ═══════════════════════════════════════════════════════════
    WHATSAPP_PROVIDER: Literal["twilio", "meta", "whatsapp-web"] = Field(
        default="twilio",
        description="Proveedor de WhatsApp"
    )
    
    # ═══════════════════════════════════════════════════════════
    # Twilio Configuration
    # ═══════════════════════════════════════════════════════════
    TWILIO_ACCOUNT_SID: str = Field(default="", description="Twilio Account SID")
    TWILIO_AUTH_TOKEN: str = Field(default="", description="Twilio Auth Token")
    TWILIO_WHATSAPP_NUMBER: str = Field(default="+14155238886", description="Twilio WhatsApp Number")
    
    # ═══════════════════════════════════════════════════════════
    # Meta WhatsApp Business API
    # ═══════════════════════════════════════════════════════════
    META_ACCESS_TOKEN: str = Field(default="", description="Meta Access Token")
    META_PHONE_NUMBER_ID: str = Field(default="", description="Meta Phone Number ID")
    META_WHATSAPP_BUSINESS_ACCOUNT_ID: str = Field(default="", description="Meta Business Account ID")
    
    # ═══════════════════════════════════════════════════════════
    # WhatsApp Web (whatsapp-web.js) - GRATIS
    # ═══════════════════════════════════════════════════════════
    WHATSAPP_WEB_URL: str = Field(
        default="http://localhost:3000",
        description="URL del servicio whatsapp-web.js"
    )
    
    # ═══════════════════════════════════════════════════════════
    # Telegram Bot - 100% GRATIS
    # ═══════════════════════════════════════════════════════════
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram Bot Token")
    TELEGRAM_ENABLED: bool = Field(default=False, description="Habilitar Telegram Bot")
    
    # ═══════════════════════════════════════════════════════════
    # Database
    # ═══════════════════════════════════════════════════════════
    DATABASE_URL: str = Field(
        default="sqlite:///portal_energetico.db",
        description="Database connection URL"
    )
    
    # ═══════════════════════════════════════════════════════════
    # Redis
    # ═══════════════════════════════════════════════════════════
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_DB: int = Field(default=0, description="Redis database")
    REDIS_PASSWORD: str = Field(default="", description="Redis password")
    
    # ═══════════════════════════════════════════════════════════
    # AI Configuration
    # ═══════════════════════════════════════════════════════════
    GROQ_API_KEY: str = Field(default="", description="Groq API Key")
    GROQ_BASE_URL: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Groq API Base URL"
    )
    AI_MODEL: str = Field(
        default="llama-3.3-70b-versatile",
        description="AI Model"
    )
    
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API Key")
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API Base URL"
    )
    OPENROUTER_MODEL: str = Field(
        default="meta-llama/llama-3.3-70b-instruct",
        description="OpenRouter Model"
    )
    
    # ═══════════════════════════════════════════════════════════
    # S3/MinIO Configuration
    # ═══════════════════════════════════════════════════════════
    S3_ENDPOINT_URL: str = Field(default="http://localhost:9000", description="S3 Endpoint")
    S3_ACCESS_KEY: str = Field(default="minioadmin", description="S3 Access Key")
    S3_SECRET_KEY: str = Field(default="minioadmin", description="S3 Secret Key")
    S3_BUCKET_CHARTS: str = Field(default="whatsapp-charts", description="Charts bucket")
    S3_BUCKET_DASHBOARDS: str = Field(default="whatsapp-dashboards", description="Dashboards bucket")
    S3_REGION: str = Field(default="us-east-1", description="S3 Region")
    
    # ═══════════════════════════════════════════════════════════
    # Portal Energético URLs
    # ═══════════════════════════════════════════════════════════
    PORTAL_BASE_URL: str = Field(
        default="http://portalenergetico.minenergia.gov.co",
        description="Portal base URL"
    )
    PORTAL_API_URL: str = Field(
        default="http://portalenergetico.minenergia.gov.co/api",
        description="Portal API URL"
    )
    PORTAL_DASHBOARD_URL: str = Field(
        default="http://portalenergetico.minenergia.gov.co",
        description="Portal Dashboard URL"
    )
    
    # ═══════════════════════════════════════════════════════════
    # Application Settings
    # ═══════════════════════════════════════════════════════════
    APP_ENV: Literal["development", "production", "testing"] = Field(
        default="development",
        description="Environment"
    )
    APP_DEBUG: bool = Field(default=False, description="Debug mode")
    APP_PORT: int = Field(default=8001, description="Application port")
    APP_HOST: str = Field(default="0.0.0.0", description="Application host")
    
    # ═══════════════════════════════════════════════════════════
    # Security
    # ═══════════════════════════════════════════════════════════
    ENCRYPTION_KEY: str = Field(
        default="your-32-character-encryption-key",
        description="Encryption key"
    )
    SECRET_KEY: str = Field(
        default="your-secret-key-for-sessions",
        description="Secret key"
    )
    
    # ═══════════════════════════════════════════════════════════
    # Rate Limiting
    # ═══════════════════════════════════════════════════════════
    RATE_LIMIT_MESSAGES: int = Field(default=20, description="Max messages per window")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Rate limit window in seconds")
    
    # ═══════════════════════════════════════════════════════════
    # Monitoring
    # ═══════════════════════════════════════════════════════════
    SENTRY_DSN: str = Field(default="", description="Sentry DSN")
    ENABLE_MONITORING: bool = Field(default=False, description="Enable monitoring")
    
    # ═══════════════════════════════════════════════════════════
    # Logging
    # ═══════════════════════════════════════════════════════════
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    LOG_FILE: str = Field(default="logs/whatsapp_bot.log", description="Log file path")
    
    # ═══════════════════════════════════════════════════════════
    # Rutas
    # ═══════════════════════════════════════════════════════════
    @property
    def BASE_DIR(self) -> Path:
        """Directorio base del proyecto"""
        return Path(__file__).parent.parent
    
    @property
    def LOGS_DIR(self) -> Path:
        """Directorio de logs"""
        path = self.BASE_DIR / "logs"
        path.mkdir(exist_ok=True)
        return path
    
    @property
    def DATA_DIR(self) -> Path:
        """Directorio de datos"""
        path = self.BASE_DIR / "data"
        path.mkdir(exist_ok=True)
        return path


# Singleton de configuración
settings = Settings()
