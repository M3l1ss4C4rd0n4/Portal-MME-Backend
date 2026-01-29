"""
Constantes del Portal Energético MME
Valores que no cambian durante la ejecución
"""
from typing import Dict, List

# ═══════════════════════════════════════════════════════════════
# INFORMACIÓN DE LA APLICACIÓN
# ═══════════════════════════════════════════════════════════════

APP_NAME = "Portal Energético MME"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = "Dashboard de análisis del sector energético colombiano"
APP_AUTHOR = "Ministerio de Minas y Energía"

# ═══════════════════════════════════════════════════════════════
# URLS Y ENDPOINTS
# ═══════════════════════════════════════════════════════════════

# URL del dashboard
DASHBOARD_URL = "http://localhost:8050"

# Health check endpoint
HEALTH_CHECK_ENDPOINT = "/health"

# ═══════════════════════════════════════════════════════════════
# BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

# Nombre del archivo de base de datos SQLite
DATABASE_FILENAME = "portal_energetico.db"

# Tablas principales
TABLES = {
    "METRICS": "metrics",
    "METRICS_HOURLY": "metrics_hourly",
    "CATALOGOS": "catalogos",
    "PREDICTIONS": "predictions",
    "APOR_MEDIA_HIST": "apor_mediahist",
}

# Índices de base de datos
DATABASE_INDEXES = [
    "idx_metrics_metric_date",
    "idx_metrics_metric_id",
    "idx_metrics_date",
    "idx_hourly_metric_datetime",
    "idx_hourly_metric_id",
    "idx_hourly_datetime",
    "idx_predictions_metric",
]

# ═══════════════════════════════════════════════════════════════
# MÉTRICAS XM
# ═══════════════════════════════════════════════════════════════

# IDs de métricas principales (según API XM)
METRIC_IDS = {
    # Generación por fuente
    "GEN_HIDRAULICA": "Gene_Hidra",
    "GEN_TERMICA": "Gene_Trmica",
    "GEN_EOLICA": "Gene_lica",
    "GEN_SOLAR": "Gene_Solar",
    "GEN_BIOMASA": "Gene_Biomasa",
    "GEN_COGENERACION": "Gene_Cogeneracin",
    
    # Demanda
    "DEMANDA_NACIONAL": "DemaReal",
    "DEMANDA_SIN": "DemaBRutiOficial",
    
    # Comercialización
    "PRECIO_BOLSA": "PrecBolsNaci",
    "PRECIO_ESCASEZ": "PreEscasez",
    
    # Hidrología
    "APORTES_NETOS": "AporNeto",
    "APORTES_CAUDAL_RIO": "AporCaudal_Rio",
}

# Grupos de métricas por categoría
METRIC_GROUPS = {
    "generacion": [
        "Gene_Hidra",
        "Gene_Trmica",
        "Gene_lica",
        "Gene_Solar",
        "Gene_Biomasa",
        "Gene_Cogeneracin",
    ],
    "demanda": [
        "DemaReal",
        "DemaBRutiOficial",
    ],
    "comercializacion": [
        "PrecBolsNaci",
        "PreEscasez",
    ],
    "hidrologia": [
        "AporNeto",
        "AporCaudal_Rio",
    ],
}

# ═══════════════════════════════════════════════════════════════
# FUENTES DE GENERACIÓN
# ═══════════════════════════════════════════════════════════════

FUENTES_GENERACION = {
    "HIDRAULICA": {
        "nombre": "Hidráulica",
        "color": "#0088FE",
        "icono": "droplet",
        "unidad": "GWh",
    },
    "TERMICA": {
        "nombre": "Térmica",
        "color": "#FF8042",
        "icono": "fire",
        "unidad": "GWh",
    },
    "EOLICA": {
        "nombre": "Eólica",
        "color": "#00C49F",
        "icono": "wind",
        "unidad": "GWh",
    },
    "SOLAR": {
        "nombre": "Solar",
        "color": "#FFBB28",
        "icono": "sun",
        "unidad": "GWh",
    },
    "BIOMASA": {
        "nombre": "Biomasa",
        "color": "#8B4513",
        "icono": "leaf",
        "unidad": "GWh",
    },
    "COGENERACION": {
        "nombre": "Cogeneración",
        "color": "#9C27B0",
        "icono": "zap",
        "unidad": "GWh",
    },
}

# Orden de fuentes para visualización
FUENTES_ORDEN = [
    "HIDRAULICA",
    "TERMICA",
    "EOLICA",
    "SOLAR",
    "BIOMASA",
    "COGENERACION",
]

# ═══════════════════════════════════════════════════════════════
# COLORES DEL DASHBOARD
# ═══════════════════════════════════════════════════════════════

COLORS = {
    # Colores principales
    "primary": "#1E3A8A",      # Azul oscuro
    "secondary": "#3B82F6",    # Azul medio
    "accent": "#10B981",       # Verde
    "warning": "#F59E0B",      # Amarillo
    "danger": "#EF4444",       # Rojo
    "success": "#10B981",      # Verde
    "info": "#3B82F6",         # Azul
    
    # Colores de fondo
    "background": "#F8FAFC",
    "card": "#FFFFFF",
    "hover": "#F1F5F9",
    
    # Colores de texto
    "text_primary": "#1E293B",
    "text_secondary": "#64748B",
    "text_muted": "#94A3B8",
    
    # Colores de gráficos
    "chart_1": "#0088FE",
    "chart_2": "#00C49F",
    "chart_3": "#FFBB28",
    "chart_4": "#FF8042",
    "chart_5": "#8B4513",
    "chart_6": "#9C27B0",
}

# Paleta de colores para gráficos
CHART_COLORS = [
    "#0088FE",
    "#00C49F",
    "#FFBB28",
    "#FF8042",
    "#8B4513",
    "#9C27B0",
    "#E91E63",
    "#9E9E9E",
]

# ═══════════════════════════════════════════════════════════════
# FORMATOS DE FECHA Y HORA
# ═══════════════════════════════════════════════════════════════

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT_DISPLAY = "%d/%m/%Y"
DATETIME_FORMAT_DISPLAY = "%d/%m/%Y %H:%M"

# Formato para nombres de archivos
DATE_FORMAT_FILENAME = "%Y%m%d"
DATETIME_FORMAT_FILENAME = "%Y%m%d_%H%M%S"

# ═══════════════════════════════════════════════════════════════
# UNIDADES DE MEDIDA
# ═══════════════════════════════════════════════════════════════

UNITS = {
    "ENERGIA": "GWh",
    "POTENCIA": "MW",
    "PRECIO": "COP/kWh",
    "CAUDAL": "m³/s",
    "PORCENTAJE": "%",
    "TEMPERATURA": "°C",
}

# ═══════════════════════════════════════════════════════════════
# LÍMITES Y UMBRALES
# ═══════════════════════════════════════════════════════════════

# Umbrales de alertas para datos antiguos
DATA_AGE_THRESHOLDS = {
    "OK": 2,        # Menos de 2 días: OK
    "WARNING": 7,   # 2-7 días: Advertencia
    "CRITICAL": 15, # Más de 7 días: Crítico
}

# Umbrales de uso de disco
DISK_USAGE_THRESHOLDS = {
    "WARNING": 70,   # 70% uso: Advertencia
    "CRITICAL": 90,  # 90% uso: Crítico
}

# Límites de queries
QUERY_LIMITS = {
    "DEFAULT": 1000,
    "MAX": 10000,
    "HOURLY": 24 * 365,  # 1 año de datos horarios
}

# ═══════════════════════════════════════════════════════════════
# TIMEOUTS Y REINTENTOS
# ═══════════════════════════════════════════════════════════════

TIMEOUTS = {
    "API_XM": 30,           # segundos
    "DATABASE": 10,         # segundos
    "AI_REQUEST": 30,       # segundos
    "HTTP_REQUEST": 15,     # segundos
}

RETRIES = {
    "API_XM": 3,
    "DATABASE": 2,
    "AI_REQUEST": 2,
}

# Delays entre reintentos (segundos)
RETRY_DELAYS = {
    "SHORT": 1,
    "MEDIUM": 5,
    "LONG": 10,
}

# ═══════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════

CACHE_TTL = {
    "SHORT": 60,          # 1 minuto
    "MEDIUM": 300,        # 5 minutos
    "LONG": 3600,         # 1 hora
    "VERY_LONG": 86400,   # 24 horas
}

# ═══════════════════════════════════════════════════════════════
# MENSAJES DE ESTADO
# ═══════════════════════════════════════════════════════════════

STATUS_MESSAGES = {
    "HEALTHY": "✅ Sistema funcionando correctamente",
    "DEGRADED": "⚠️ Sistema con advertencias",
    "UNHEALTHY": "❌ Sistema con problemas críticos",
}

STATUS_ICONS = {
    "HEALTHY": "✅",
    "DEGRADED": "⚠️",
    "UNHEALTHY": "❌",
}

# ═══════════════════════════════════════════════════════════════
# MACHINE LEARNING
# ═══════════════════════════════════════════════════════════════

ML_MODELS = {
    "PROPHET": "prophet",
    "SARIMA": "sarima",
    "ENSEMBLE": "ensemble",
}

ML_CONFIDENCE_LEVELS = {
    "LOW": 0.80,
    "MEDIUM": 0.90,
    "HIGH": 0.95,
}

# ═══════════════════════════════════════════════════════════════
# PÁGINAS DEL DASHBOARD
# ═══════════════════════════════════════════════════════════════

PAGES = {
    "HOME": "/",
    "GENERACION": "/generacion/general",
    "DEMANDA": "/demanda/general",
    "COMERCIALIZACION": "/comercializacion/general",
    "HIDROLOGIA": "/hidrologia/general",
    "METRICAS": "/metricas",
    "PREDICCIONES": "/predicciones",
    "CHAT_IA": "/chat-ia",
}

# ═══════════════════════════════════════════════════════════════
# EXPRESIONES REGULARES
# ═══════════════════════════════════════════════════════════════

REGEX_PATTERNS = {
    "METRIC_ID": r"^[A-Za-z_]+$",
    "DATE": r"^\d{4}-\d{2}-\d{2}$",
    "DATETIME": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",
}

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE EXPORTACIÓN
# ═══════════════════════════════════════════════════════════════

EXPORT_FORMATS = ["csv", "excel", "json"]
EXPORT_MAX_ROWS = 100000

# ═══════════════════════════════════════════════════════════════
# INFORMACIÓN DEL SISTEMA
# ═══════════════════════════════════════════════════════════════

SYSTEM_INFO = {
    "MIN_PYTHON_VERSION": "3.8",
    "RECOMMENDED_PYTHON_VERSION": "3.12",
    "MIN_RAM_GB": 4,
    "RECOMMENDED_RAM_GB": 8,
    "MIN_DISK_GB": 10,
}

# ═══════════════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════════════

def get_metric_name(metric_id: str) -> str:
    """Obtiene el nombre legible de una métrica"""
    metric_map = {v: k for k, v in METRIC_IDS.items()}
    return metric_map.get(metric_id, metric_id)


def get_fuente_config(fuente: str) -> Dict:
    """Obtiene configuración de una fuente de generación"""
    return FUENTES_GENERACION.get(fuente.upper(), {})


def get_color_by_index(index: int) -> str:
    """Obtiene un color de la paleta por índice"""
    return CHART_COLORS[index % len(CHART_COLORS)]
