"""
Factory de aplicación Dash
Crea y configura la app con la nueva arquitectura
"""

import sys
import io
import os
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


def _register_layout(app):
    """Registra el layout principal"""
    app.layout = html.Div([
        # ✅ ÚNICO ENCABEZADO CENTRALIZADO (Fixed Top)
        crear_header_restaurado(),
        
        # Elementos invisibles
        dcc.Location(id="url", refresh=False),
        dcc.Store(id='store-datos-chatbot-generacion', data={}),
        dcc.Store(id='error-log-store', data=None),
        dcc.Store(id='theme-store', storage_type='local', data='light'),
        
        # Contenedor principal — navbar sticky, sin paddingTop fijo
        html.Div([
            page_container,
        ]),
        
        # ✨ Chat Widget
        crear_componente_chat()
    ])


def _register_callbacks(app):
    """Registra callbacks globales"""
    from dash import Input, Output, clientside_callback

    # Fase F: toggle dark/light — aplica data-bs-theme al elemento raíz
    clientside_callback(
        """
        function(theme) {
            var t = theme || 'light';
            document.documentElement.setAttribute('data-bs-theme', t);
            document.documentElement.setAttribute('data-theme', t);
            return theme;
        }
        """,
        Output('theme-store', 'data'),
        Input('theme-store', 'data'),
    )

    # Fase F: Switch en header actualiza el Store
    clientside_callback(
        """
        function(checked) {
            var t = checked ? 'dark' : 'light';
            document.documentElement.setAttribute('data-bs-theme', t);
            document.documentElement.setAttribute('data-theme', t);
            return t;
        }
        """,
        Output('theme-store', 'data', allow_duplicate=True),
        Input('theme-switch', 'value'),
        prevent_initial_call=True,
    )

    # BUG 3: Toggler mobile para el nuevo dbc.Navbar
    @app.callback(
        Output('navbar-collapse', 'is_open'),
        Input('navbar-toggler', 'n_clicks'),
        prevent_initial_call=True,
    )
    def toggle_navbar(n_clicks):
        return bool(n_clicks % 2)

    NAV_NAMES = [
        'inicio', 'generacion', 'transmision', 'distribucion',
        'comercializacion', 'perdidas', 'costo-unitario', 'simulacion-creg',
        'perdidas-nt', 'restricciones', 'metricas', 'seguimiento-predicciones'
    ]

    @app.callback(
        [Output(f'nav-link-{name}', 'style') for name in NAV_NAMES],
        Input('url-navbar', 'pathname')
    )
    def update_navbar_active(pathname):
        """Resalta el link activo en el navbar según la ruta actual"""
        if pathname is None:
            pathname = '/'

        active_style = {
            'backgroundColor': 'rgba(245,158,11,0.9)',
            'color': '#000',
            'padding': '6px 14px',
            'borderRadius': '6px',
            'textDecoration': 'none',
            'fontWeight': '600',
            'fontSize': '13px',
            'transition': 'all 0.2s ease'
        }

        inactive_style = {
            'backgroundColor': 'transparent',
            'color': 'rgba(255,255,255,0.85)',
            'padding': '6px 14px',
            'borderRadius': '6px',
            'textDecoration': 'none',
            'fontWeight': '500',
            'fontSize': '13px',
            'transition': 'all 0.2s ease'
        }

        route_mapping = {
            'inicio': lambda p: p == '/',
            'generacion': lambda p: p.startswith('/generacion'),
            'transmision': lambda p: p.startswith('/transmision'),
            'distribucion': lambda p: p.startswith('/distribucion'),
            'comercializacion': lambda p: p.startswith('/comercializacion'),
            'perdidas': lambda p: p == '/perdidas' or p.startswith('/perdidas/'),
            'costo-unitario': lambda p: p.startswith('/costo-unitario'),
            'simulacion-creg': lambda p: p.startswith('/simulacion-creg'),
            'perdidas-nt': lambda p: p.startswith('/perdidas-nt'),
            'restricciones': lambda p: p.startswith('/restricciones'),
            'metricas': lambda p: p.startswith('/metricas'),
            'seguimiento-predicciones': lambda p: p.startswith('/seguimiento-predicciones'),
        }

        styles = []
        for name in NAV_NAMES:
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

    # ── Error boundary: captura errores 500 no manejados ──
    @server.errorhandler(500)
    def handle_500(e):
        logger.error(f"[DASHBOARD] Error 500: {e}", exc_info=True)
        return jsonify({
            "error": "Error interno del servidor",
            "message": "El equipo técnico ha sido notificado.",
        }), 500

    @server.errorhandler(404)
    def handle_404(e):
        return jsonify({"error": "Página no encontrada"}), 404

    # _register_pages() — ELIMINADO: Dash Pages usa auto-discovery
    _register_layout(app)
    _register_callbacks(app)

    return app


# Alias para compatibilidad con tests y código externo
create_dash_app = create_app
