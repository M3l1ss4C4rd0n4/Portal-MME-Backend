"""
Configuración centralizada del Portal Energético MME
Usa Pydantic Settings para validación y gestión de variables de entorno
"""
import multiprocessing
from pathlib import Path
from typing import Optional, Literal, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración centralizada de la aplicación"""
    
    # ═══════════════════════════════════════════════════════════
    # CONFIGURACIÓN GENERAL
    # ═══════════════════════════════════════════════════════════
    
    # Entorno de ejecución
    DASH_ENV: Literal["development", "production", "testing"] = Field(
        default="production",
        description="Entorno de ejecución"
    )
    
    DASH_DEBUG: bool = Field(
        default=False,
        description="Modo debug de Dash"
    )
    
    DASH_PORT: int = Field(
        default=8050,
        description="Puerto del servidor Dash"
    )
    
    # ═══════════════════════════════════════════════════════════
    # RUTAS DEL PROYECTO
    # ═══════════════════════════════════════════════════════════
    
    @property
    def BASE_DIR(self) -> Path:
        """Directorio base del proyecto"""
        return Path(__file__).parent.parent
    
    @property
    def LOGS_DIR(self) -> Path:
        """Directorio de logs"""
        return self.BASE_DIR / "logs"
    
    @property
    def DATABASE_PATH(self) -> Path:
        """Ruta a la base de datos legacy (no usada — PostgreSQL es el backend principal)"""
        return self.BASE_DIR / "portal_energetico.db"
    
    @property
    def BACKUP_DIR(self) -> Path:
        """Directorio de backups"""
        return self.BASE_DIR / "backups"
    
    # ═══════════════════════════════════════════════════════════
    # BASE DE DATOS - Parámetros legacy (solo ETL fallback)
    # ═══════════════════════════════════════════════════════════
    
    DB_CACHE_SIZE_MB: int = Field(
        default=64,
        description="Tamaño de cache para consultas locales (legacy)"
    )
    
    DB_WAL_MODE: bool = Field(
        default=True,
        description="Modo WAL para escrituras concurrentes (legacy)"
    )
    
    DB_JOURNAL_MODE: Literal["DELETE", "WAL", "MEMORY"] = Field(
        default="WAL",
        description="Modo de journal para operaciones locales (legacy)"
    )
    
    # ═══════════════════════════════════════════════════════════
    # BASE DE DATOS - PostgreSQL (backend principal)
    # ═══════════════════════════════════════════════════════════
    
    USE_POSTGRES: bool = Field(
        default=True,
        description="Usar PostgreSQL como backend principal"
    )
    
    POSTGRES_HOST: str = Field(
        default="localhost",
        description="Host de PostgreSQL"
    )
    
    POSTGRES_PORT: int = Field(
        default=5432,
        description="Puerto de PostgreSQL"
    )
    
    POSTGRES_DB: str = Field(
        default="portal_energetico",
        description="Nombre de base de datos PostgreSQL"
    )
    
    POSTGRES_USER: str = Field(
        default="postgres",
        description="Usuario de PostgreSQL"
    )
    
    POSTGRES_PASSWORD: str = Field(
        default="",
        description="Contraseña de PostgreSQL"
    )
    
    @property
    def DATABASE_URL(self) -> str:
        """URL de conexión PostgreSQL (para futuro)"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    # ═══════════════════════════════════════════════════════════
    # REDIS
    # ═══════════════════════════════════════════════════════════
    
    REDIS_HOST: str = Field(
        default="localhost",
        description="Host de Redis"
    )
    
    REDIS_PORT: int = Field(
        default=6379,
        description="Puerto de Redis"
    )
    
    REDIS_DB: int = Field(
        default=0,
        description="Base de datos Redis para cache general"
    )
    
    REDIS_PASSWORD: str = Field(
        default="",
        description="Contraseña de Redis (vacío si no tiene auth)"
    )
    
    @property
    def REDIS_URL(self) -> str:
        """URL de conexión Redis"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # ═══════════════════════════════════════════════════════════
    # MLFLOW
    # ═══════════════════════════════════════════════════════════
    
    MLFLOW_ADMIN_PASSWORD: str = Field(
        default="",
        description="Contraseña de Basic Auth para MLflow (guardada en .env)"
    )
    
    # ═══════════════════════════════════════════════════════════
    # CARGOS REGULADOS CREG (para cálculo de CU MAYORISTA)
    # ═══════════════════════════════════════════════════════════
    #
    # IMPORTANTE — CONTEXTO DE USO:
    # Estos cargos son los que XM liquida en el mercado MAYORISTA a través
    # del Boletín LAC (Liquidaciones y Asignación de Costos). NO son los
    # componentes de la tarifa al usuario final que publica la SSPD en el
    # Boletín Tarifario. Esos incluyen STR (sub-transmisión), DTUN y márgenes
    # minoristas que elevan los valores 3-10x.
    #
    # Fuente oficial para actualizar T, D, C:
    #   XM → https://www.xm.com.co/publicaciones/liquidaciones
    #   Boletín LAC mensual → sección "Costos unitarios por cargo" → COP/kWh
    #
    # Indexación: Los cargos se actualizan anualmente por IPC (Resolución CREG).
    # Si no se actualizan vía .env, revisar al menos una vez por año.
    # Riesgo de desactualización: ~2-3% anual por IPC.
    #
    # Para anular los defaults sin tocar código:
    #   CARGO_TRANSMISION_COP_KWH=9.8 en .env
    #   CARGO_DISTRIBUCION_COP_KWH=42.0 en .env
    #   CARGO_COMERCIALIZACION_COP_KWH=14.5 en .env
    # ═══════════════════════════════════════════════════════════

    CARGO_TRANSMISION_COP_KWH: float = Field(
        default=8.5,
        description=(
            "Cargo transmisión STN en el mercado MAYORISTA (COP/kWh). "
            "Valor del Boletín LAC de XM — componente de la bolsa/contratos mayoristas. "
            "NO es equivalente al T del recibo del usuario final (ver CARGO_T_STN_MINORISTA_COP_KWH). "
            "Actualizar desde: xm.com.co → Publicaciones → Liquidaciones → Boletín LAC."
        )
    )

    CARGO_T_STN_MINORISTA_COP_KWH: float = Field(
        default=50.87,
        description=(
            "Cargo transmisión STN en la tarifa MINORISTA al usuario final (COP/kWh). "
            "Valor derivado del Boletín Tarifario oficial Enel Colombia enero 2026: "
            "T_total=52.97 menos T_STR_Codensa=2.10 → T_STN=50.87 COP/kWh. "
            "Este valor es nacional (CREG Resolution misma para todos los OR) y "
            "se actualiza anualmente por IPC. "
            "DISTINTO del cargo mayorista CARGO_TRANSMISION_COP_KWH (que es ~8.5 COP/kWh). "
            "Fuente: superservicios.gov.co → Boletín Tarifario SSPD, columna T_STN. "
            "O puede sobreescribirse vía columna t_stn_cop_kwh en cu_tarifas_or."
        )
    )

    CARGO_DISTRIBUCION_COP_KWH: float = Field(
        default=35.0,
        description=(
            "Cargo distribución SDL (promedio nacional) en el mercado MAYORISTA (COP/kWh). "
            "Promedio nacional ponderado por energía del Boletín LAC de XM. "
            "NO equivale al DTUN por OR del Boletín Tarifario SSPD (que varía 125-300 COP/kWh "
            "por ADD e incluye niveles de tensión 1-4). "
            "Actualizar desde: xm.com.co → Publicaciones → Liquidaciones → Boletín LAC."
        )
    )

    CARGO_COMERCIALIZACION_COP_KWH: float = Field(
        default=12.0,
        description=(
            "Cargo comercialización mayorista (promedio nacional) (COP/kWh). "
            "Margen de comercialización en la frontera mayorista del Boletín LAC de XM. "
            "NO equivale al componente C del recibo del usuario final (que incluye "
            "contribuciones cruzadas, impuestos y márgenes minoristas totalizando ~80-120 COP/kWh). "
            "Actualizar desde: xm.com.co → Publicaciones → Liquidaciones → Boletín LAC."
        )
    )

    FACTOR_PERDIDAS_DISTRIBUCION: float = Field(
        default=0.085,
        description=(
            "Factor de pérdidas TÉCNICAS distribución SDL regulado CREG (~8.5%). "
            "Promedio nacional según CREG/UPME. Componente técnico solamente. "
            "Suma con pérdidas STN reales (medidas por XM, ~1.4-1.7%) "
            "para estimar pérdidas técnicas totales del sistema."
        )
    )

    FACTOR_PERDIDAS_SDL_TOTAL: float = Field(
        default=0.12,
        description=(
            "Factor de pérdidas TOTALES SDL (técnicas + no técnicas) (COP/kWh). "
            "Promedio nacional CREG/UPME (~12%): pérdidas técnicas distribución (~8.5%) "
            "+ pérdidas no técnicas estimadas (~3.5%). "
            "Se usa para proyectar energía a nivel usuario final desde DemaReal (frontera STN/SDL). "
            "En ORs con alta PNT (Caribe, zonas rurales) puede alcanzar 20-30%."
        )
    )

    TRM_REF_COP_USD: float = Field(
        default=4_200.0,
        description="TRM de referencia COP/USD para conversión de CAPEX en inversiones "
                    "renovables. Actualizar vía variable de entorno TRM_REF_COP_USD "
                    "o ajustar el default cuando cambie significativamente."
    )
    
    # ═══════════════════════════════════════════════════════════
    # APIS EXTERNAS - XM
    # ═══════════════════════════════════════════════════════════
    
    XM_API_TIMEOUT: int = Field(
        default=30,
        description="Timeout para API XM en segundos"
    )
    
    XM_API_RETRIES: int = Field(
        default=3,
        description="Número de reintentos para API XM"
    )
    
    # ═══════════════════════════════════════════════════════════
    # INTELIGENCIA ARTIFICIAL
    # ═══════════════════════════════════════════════════════════
    
    # Groq API (primaria)
    GROQ_API_KEY: str = Field(
        default="",
        description="API Key de Groq"
    )
    
    GROQ_BASE_URL: str = Field(
        default="https://api.groq.com/openai/v1",
        description="URL base de Groq API"
    )
    
    AI_MODEL: str = Field(
        default="llama-3.3-70b-versatile",
        description="Modelo de IA a usar"
    )
    
    # OpenRouter API (backup)
    OPENROUTER_API_KEY: str = Field(
        default="",
        description="API Key de OpenRouter (backup)"
    )
    
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="URL base de OpenRouter API"
    )
    
    OPENROUTER_BACKUP_MODEL: str = Field(
        default="tngtech/deepseek-r1t2-chimera:free",
        description="Modelo de backup en OpenRouter"
    )
    
    # GNews API (noticias del sector)
    GNEWS_API_KEY: str = Field(
        default="",
        description="API Key de GNews (gnews.io) para noticias del sector"
    )
    
    # Mediastack API (segunda fuente de noticias)
    MEDIASTACK_API_KEY: str = Field(
        default="",
        description="API Key de Mediastack (mediastack.com) para noticias — opcional"
    )
    
    # Configuración de IA
    AI_MAX_TOKENS: int = Field(
        default=2000,
        description="Máximo de tokens en respuestas IA"
    )
    
    AI_TEMPERATURE: float = Field(
        default=0.7,
        description="Temperatura para generación de respuestas"
    )
    
    AI_REQUEST_TIMEOUT: int = Field(
        default=30,
        description="Timeout para requests de IA en segundos"
    )
    
    # ═══════════════════════════════════════════════════════════
    # MACHINE LEARNING
    # ═══════════════════════════════════════════════════════════
    
    ML_PREDICTION_DAYS: int = Field(
        default=90,
        description="Días de predicción para modelos ML"
    )
    
    ML_MODEL_TYPE: Literal["prophet", "sarima", "ensemble"] = Field(
        default="ensemble",
        description="Tipo de modelo ML a usar"
    )
    
    ML_CONFIDENCE_INTERVAL: float = Field(
        default=0.95,
        description="Intervalo de confianza para predicciones"
    )
    
    # ═══════════════════════════════════════════════════════════
    # WEB SERVER - Gunicorn
    # ═══════════════════════════════════════════════════════════
    
    GUNICORN_BIND: str = Field(
        default="127.0.0.1:8050",
        description="Socket bind de Gunicorn"
    )
    
    GUNICORN_WORKERS: Optional[int] = Field(
        default=None,
        description="Número de workers Gunicorn (None = auto)"
    )
    
    @property
    def gunicorn_workers_count(self) -> int:
        """Calcula número óptimo de workers"""
        if self.GUNICORN_WORKERS:
            return self.GUNICORN_WORKERS
        return multiprocessing.cpu_count() * 2 + 1
    
    GUNICORN_THREADS: int = Field(
        default=4,
        description="Threads por worker"
    )
    
    GUNICORN_TIMEOUT: int = Field(
        default=120,
        description="Timeout de workers en segundos"
    )
    
    GUNICORN_MAX_REQUESTS: int = Field(
        default=1000,
        description="Máximo de requests antes de reiniciar worker"
    )
    
    GUNICORN_KEEPALIVE: int = Field(
        default=5,
        description="Keepalive en segundos"
    )
    
    # ═══════════════════════════════════════════════════════════
    # LOGGING
    # ═══════════════════════════════════════════════════════════
    
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Nivel de logging"
    )
    
    LOG_FORMAT: str = Field(
        default="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
        description="Formato de logs"
    )
    
    LOG_DATE_FORMAT: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="Formato de fecha en logs"
    )
    
    LOG_MAX_BYTES: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Tamaño máximo de archivo de log"
    )
    
    LOG_BACKUP_COUNT: int = Field(
        default=5,
        description="Número de archivos de log a mantener"
    )
    
    # ═══════════════════════════════════════════════════════════
    # PERFORMANCE Y CACHE
    # ═══════════════════════════════════════════════════════════
    
    CACHE_ENABLED: bool = Field(
        default=True,
        description="Habilitar cache de datos"
    )
    
    CACHE_TTL_SECONDS: int = Field(
        default=300,  # 5 minutos
        description="TTL del cache en segundos"
    )
    
    CHART_REFRESH_INTERVAL: int = Field(
        default=300000,  # 5 minutos en ms
        description="Intervalo de refresh de gráficos en ms"
    )
    
    # ═══════════════════════════════════════════════════════════
    # ETL Y DATOS
    # ═══════════════════════════════════════════════════════════
    
    ETL_MAX_DAYS_AGE: int = Field(
        default=7,
        description="Días máximos de antigüedad de datos antes de alertar"
    )
    
    ETL_BATCH_SIZE: int = Field(
        default=1000,
        description="Tamaño de lote para inserts en ETL"
    )
    
    ETL_VALIDATION_ENABLED: bool = Field(
        default=True,
        description="Habilitar validaciones en ETL"
    )
    
    # ═══════════════════════════════════════════════════════════
    # API REST - FastAPI
    # ═══════════════════════════════════════════════════════════
    
    API_ENABLED: bool = Field(
        default=True,
        description="Habilitar API REST (FastAPI)"
    )
    
    API_PORT: int = Field(
        default=8000,
        description="Puerto del API REST"
    )
    
    API_DOCS_ENABLED: bool = Field(
        default=True,
        description="Habilitar documentación Swagger/ReDoc"
    )
    
    # Seguridad de API
    API_KEY_ENABLED: bool = Field(
        default=True,
        description="Habilitar validación de API Key"
    )
    
    API_KEY: str = Field(
        default="mme-portal-energetico-2026-secret-key",
        description="API Key principal para autenticación"
    )
    
    API_KEYS_WHITELIST: str = Field(
        default="",
        description="Lista de API Keys válidas separadas por comas (adicionales a API_KEY)"
    )
    
    @property
    def api_keys_list(self) -> List[str]:
        """Lista de API Keys válidas"""
        keys = [self.API_KEY]  # Siempre incluir la API Key principal
        if self.API_KEYS_WHITELIST:
            keys.extend([key.strip() for key in self.API_KEYS_WHITELIST.split(",") if key.strip()])
        return keys
    
    API_RATE_LIMIT: str = Field(
        default="100/minute",
        description="Límite de requests por minuto (formato: 'N/period')"
    )
    
    API_CORS_ORIGINS_STR: str = Field(
        default="http://localhost:8050,http://127.0.0.1:8050,https://srvwebprdctrlxm.mme.gov.co",
        description="Orígenes CORS permitidos (separados por comas)",
        alias="API_CORS_ORIGINS"
    )
    
    @property
    def API_CORS_ORIGINS(self) -> List[str]:
        """Lista de orígenes CORS permitidos"""
        if self.API_CORS_ORIGINS_STR == "*":
            return ["*"]
        return [origin.strip() for origin in self.API_CORS_ORIGINS_STR.split(",") if origin.strip()]
    
    # ═══════════════════════════════════════════════════════════
    # CONFIGURACIÓN DE PYDANTIC
    # ═══════════════════════════════════════════════════════════
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignorar variables extras en .env
    )


# ═══════════════════════════════════════════════════════════════
# INSTANCIA GLOBAL DE CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Obtiene la instancia global de configuración (Singleton)
    
    Returns:
        Settings: Configuración de la aplicación
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    Recarga la configuración desde .env (útil para tests)
    
    Returns:
        Settings: Nueva configuración
    """
    global _settings
    _settings = Settings()
    return _settings


# Exportar configuración para importación directa
settings = get_settings()


# ═══════════════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════════════

def is_development() -> bool:
    """Verifica si está en modo desarrollo"""
    return settings.DASH_ENV == "development"


def is_production() -> bool:
    """Verifica si está en modo producción"""
    return settings.DASH_ENV == "production"


def is_debug_enabled() -> bool:
    """Verifica si debug está habilitado"""
    return settings.DASH_DEBUG


def get_database_path() -> Path:
    """Obtiene ruta de la base de datos legacy (PostgreSQL es el backend principal)"""
    return settings.DATABASE_PATH


def get_logs_dir() -> Path:
    """Obtiene directorio de logs (crea si no existe)"""
    logs_dir = settings.LOGS_DIR
    logs_dir.mkdir(exist_ok=True, parents=True)
    return logs_dir


# ═══════════════════════════════════════════════════════════════
# ACCESORES DE CARGOS CREG — Compatibilidad con DynamicConfig
# ═══════════════════════════════════════════════════════════════
#
# Estas funciones son los puntos de entrada recomendados para leer
# los cargos regulados en código nuevo.  Internamente delegan a
# get_settings() con posibilidad de integrar DynamicConfig en el futuro.
#
# CONTEXTO: valores del MERCADO MAYORISTA (Boletín LAC de XM).
# NO son los componentes de la factura al usuario final.


def get_T() -> float:
    """Cargo transmisión STN mayorista vigente (COP/kWh). Fuente: Boletín LAC XM."""
    return get_settings().CARGO_TRANSMISION_COP_KWH


def get_D() -> float:
    """Cargo distribución SDL promedio nacional mayorista (COP/kWh). Fuente: Boletín LAC XM."""
    return get_settings().CARGO_DISTRIBUCION_COP_KWH


def get_C() -> float:
    """Cargo comercialización mayorista (COP/kWh). Fuente: Boletín LAC XM."""
    return get_settings().CARGO_COMERCIALIZACION_COP_KWH


def get_TRM() -> float:
    """
    TRM vigente en COP/USD.

    Intenta obtener el valor actualizado desde DynamicConfig (API datos.gov.co).
    Cae back a ``settings.TRM_REF_COP_USD`` si la API no está disponible.
    No lanza excepción — siempre retorna un valor utilizable.
    """
    try:
        # Import tardío para evitar importación circular en arranque
        from domain.services.config_dynamic import get_dynamic_config  # noqa: PLC0415
        return get_dynamic_config().get_trm()
    except Exception:  # noqa: BLE001
        return get_settings().TRM_REF_COP_USD


# ═══════════════════════════════════════════════════════════════
# VALIDACIONES AL INICIALIZAR
# ═══════════════════════════════════════════════════════════════

def validate_configuration():
    """
    Valida configuración crítica al iniciar
    
    Raises:
        ValueError: Si falta configuración crítica
    """
    errors = []
    
    # Validar que existe al menos una API key de IA
    if not settings.GROQ_API_KEY and not settings.OPENROUTER_API_KEY:
        errors.append("❌ Falta GROQ_API_KEY o OPENROUTER_API_KEY en .env")
    
    # Validar que existe la base de datos
    if not settings.DATABASE_PATH.exists():
        errors.append(f"⚠️  Base de datos no encontrada: {settings.DATABASE_PATH}")
    
    # Validar directorio de logs
    try:
        settings.LOGS_DIR.mkdir(exist_ok=True, parents=True)
    except Exception as e:
        errors.append(f"❌ No se puede crear directorio de logs: {e}")
    
    if errors:
        error_msg = "\n".join(errors)
        raise ValueError(f"Errores en configuración:\n{error_msg}")


# ═══════════════════════════════════════════════════════════════
# INFORMACIÓN DE CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

def print_configuration_summary():
    """Imprime resumen de configuración (útil para debugging)"""
    print("=" * 70)
    print("CONFIGURACIÓN DEL PORTAL ENERGÉTICO MME")
    print("=" * 70)
    print(f"Entorno:             {settings.DASH_ENV}")
    print(f"Debug:               {settings.DASH_DEBUG}")
    print(f"Puerto:              {settings.DASH_PORT}")
    print(f"Base de datos:       {settings.DATABASE_PATH}")
    print(f"Logs:                {settings.LOGS_DIR}")
    print(f"Workers Gunicorn:    {settings.gunicorn_workers_count}")
    print(f"Threads por worker:  {settings.GUNICORN_THREADS}")
    print(f"IA Provider:         {'Groq' if settings.GROQ_API_KEY else 'OpenRouter'}")
    print(f"Modelo IA:           {settings.AI_MODEL}")
    print(f"Log Level:           {settings.LOG_LEVEL}")
    print(f"Cache habilitado:    {settings.CACHE_ENABLED}")
    print("=" * 70)


if __name__ == "__main__":
    # Test de configuración
    try:
        validate_configuration()
        print_configuration_summary()
        print("\n✅ Configuración válida")
    except Exception as e:
        print(f"\n❌ Error en configuración: {e}")
