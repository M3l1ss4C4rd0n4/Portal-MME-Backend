"""
Factory de aplicación Dash
Crea y configura la app con la nueva arquitectura
"""

import sys
import io
import os
from pathlib import Path
from dotenv import load_dotenv
from dash import Dash, html, dcc, page_container
import dash_bootstrap_components as dbc
from flask import jsonify, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry

from infrastructure.logging.logger import get_logger, configure_root_logger, reduce_noisy_loggers
from domain.services.system_service import verificar_salud_sistema
from interface.components.chat_widget import crear_componente_chat
from interface.components.header import crear_header_restaurado

# ==================== PROMETHEUS METRICS ====================
# Registry global para métricas
METRICS_REGISTRY = CollectorRegistry()

# Métricas del dashboard
dashboard_requests_total = Counter(
    'dashboard_requests_total',
    'Total de solicitudes al dashboard',
    ['page', 'method'],
    registry=METRICS_REGISTRY
)

dashboard_response_time = Histogram(
    'dashboard_response_time_seconds',
    'Tiempo de respuesta del dashboard',
    ['page'],
    registry=METRICS_REGISTRY
)

database_queries_total = Counter(
    'database_queries_total',
    'Total de consultas a la base de datos',
    ['table', 'status'],
    registry=METRICS_REGISTRY
)

database_query_duration = Histogram(
    'database_query_duration_seconds',
    'Duración de consultas a base de datos',
    ['table'],
    registry=METRICS_REGISTRY
)

xm_api_calls_total = Counter(
    'xm_api_calls_total',
    'Total de llamadas a la API XM',
    ['metric', 'status'],
    registry=METRICS_REGISTRY
)

redis_cache_operations = Counter(
    'redis_cache_operations_total',
    'Operaciones de caché Redis',
    ['result'],
    registry=METRICS_REGISTRY
)

active_connections = Gauge(
    'dashboard_active_connections',
    'Conexiones activas al dashboard',
    registry=METRICS_REGISTRY
)
# ============================================================

# Configurar salida estándar con UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def _preload_xm_api(logger):
    """Pre-carga la conexión a API XM"""
    logger.info("Inicializando conexión a API XM...")
    try:
        from infrastructure.external.xm_service import get_objetoAPI
        objetoAPI = get_objetoAPI()
        if objetoAPI:
            logger.info("API XM disponible")
        else:
            logger.warning("API XM no disponible")
        return objetoAPI
    except Exception as e:
        logger.warning(f"Error en inicialización API XM: {e}")
        return None


def _register_pages():
    """Registra páginas manualmente"""
    # Importar para forzar el registro de páginas en Dash
    # NOTA: Comentado para evitar duplicidad de callbacks con Dash Pages (auto-discovery)
    # import interface.pages.home # Página de inicio/portada
    # import interface.pages.generacion
    # import interface.pages.generacion_fuentes_unificado
    # import interface.pages.generacion_hidraulica_hidrologia
    # import interface.pages.transmision
    # import interface.pages.distribucion
    # import interface.pages.distribucion_demanda_unificado
    # import interface.pages.demanda  # Módulo no existe - deshabilitado temporalmente
    # import interface.pages.perdidas
    # import interface.pages.restricciones
    # import interface.pages.comercializacion
    # import interface.pages.metricas
    # import interface.pages.metricas_piloto
    pass


def _register_layout(app):
    """Registra el layout principal"""
    app.layout = html.Div([
        # ✅ ÚNICO ENCABEZADO CENTRALIZADO (Fixed Top)
        crear_header_restaurado(),
        
        # Elementos invisibles
        dcc.Location(id="url", refresh=False),
        dcc.Store(id='store-datos-chatbot-generacion', data={}),
        
        # Contenedor principal con padding superior para compensar el header fijo
        html.Div([
            page_container,
        ], style={"paddingTop": "85px"}),
        
        # ✨ Chat Widget
        crear_componente_chat()
    ])


def _register_callbacks(app):
    """Registra callbacks globales"""
    from dash import Input, Output

    @app.callback(
        [Output(f'nav-link-{name}', 'style') for name in ['inicio', 'generacion', 'transmision', 'distribucion', 'comercializacion', 'perdidas', 'restricciones', 'metricas']],
        Input('url-navbar', 'pathname')
    )
    def update_navbar_active(pathname):
        """Resalta el link activo en el navbar según la ruta actual"""
        if pathname is None:
            pathname = '/'

        active_style = {
            'backgroundColor': '#FFC107',
            'color': '#000',
            'padding': '10px 20px',
            'borderRadius': '4px',
            'textDecoration': 'none',
            'fontWeight': '500',
            'transition': 'all 0.3s ease'
        }

        inactive_style = {
            'backgroundColor': 'transparent',
            'color': 'white',  # RESTAURADO: Color blanco para contrastar con header azul corporativo
            'padding': '10px 20px',
            'borderRadius': '4px',
            'textDecoration': 'none',
            'fontWeight': '400',
            'transition': 'all 0.3s ease'
        }

        route_mapping = {
            'inicio': lambda p: p == '/',
            'generacion': lambda p: p.startswith('/generacion'),
            'transmision': lambda p: p.startswith('/transmision'),
            'distribucion': lambda p: p.startswith('/distribucion'),
            'comercializacion': lambda p: p.startswith('/comercializacion'),
            'perdidas': lambda p: p.startswith('/perdidas'),
            'restricciones': lambda p: p.startswith('/restricciones'),
            'metricas': lambda p: p.startswith('/metricas')
        }

        styles = []
        for name in ['inicio', 'generacion', 'transmision', 'distribucion', 'comercializacion', 'perdidas', 'restricciones', 'metricas']:
            if route_mapping[name](pathname):
                styles.append(active_style)
            else:
                styles.append(inactive_style)
        return styles


def create_app() -> Dash:
    """Crea y configura la aplicación Dash"""
    load_dotenv()

    # Logging
    configure_root_logger()
    logger = get_logger(__name__)
    reduce_noisy_loggers()

    logger.info("=" * 70)
    logger.info("INICIANDO PORTAL ENERGÉTICO MME")
    logger.info(f"Ambiente: {os.getenv('DASH_ENV', 'development')}")
    logger.info("=" * 70)

    _preload_xm_api(logger)

    # Calcular rutas absolutas para evitar errores de contexto
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pages_path = os.path.join(base_path, "interface", "pages")
    assets_path = os.path.join(base_path, "assets")

    app = Dash(
        __name__,
        use_pages=True,
        pages_folder=pages_path,
        assets_folder=assets_path,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
             "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
             "/assets/mme-corporate.css",
             "/assets/professional-style.css"
        ],
        suppress_callback_exceptions=True
    )

    # Health check
    server = app.server

    @server.route('/health')
    def health_check():
        """Endpoint para monitoreo de salud del sistema"""
        salud = verificar_salud_sistema()
        
        if salud['status'] == 'healthy':
            status_code = 200
        elif salud['status'] == 'degraded':
            status_code = 200
        else:
            status_code = 503

        return jsonify(salud), status_code
    
    @server.route('/metrics')
    def metrics():
        """Endpoint de métricas Prometheus"""
        logger.info("📊 Endpoint /metrics solicitado")
        return Response(generate_latest(METRICS_REGISTRY), mimetype=CONTENT_TYPE_LATEST)
    
    # _register_pages()
    _register_layout(app)
    _register_callbacks(app)

    return app
