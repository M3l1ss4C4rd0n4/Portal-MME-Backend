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
from flask import jsonify

from shared.logging.logger import get_logger, configure_root_logger, reduce_noisy_loggers
from utils.health_check import verificar_salud_sistema
from componentes.chat_ia import crear_componente_chat


# Configurar salida estándar con UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def _preload_xm_api(logger):
    """Pre-carga la conexión a API XM"""
    logger.info("Inicializando conexión a API XM...")
    try:
        from utils._xm import get_objetoAPI
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
    import pages.index_simple_working  # Página de inicio/portada
    import pages.generacion
    import pages.generacion_fuentes_unificado
    import pages.generacion_hidraulica_hidrologia
    import pages.transmision
    import pages.distribucion
    import pages.distribucion_demanda_unificado
    # import pages.demanda  # Módulo no existe - deshabilitado temporalmente
    import pages.perdidas
    import pages.restricciones
    import pages.comercializacion
    import pages.metricas
    import pages.metricas_piloto


def _register_layout(app):
    """Registra el layout principal"""
    app.layout = html.Div([
        dcc.Location(id="url", refresh=False),
        # 🗄️ Store global para datos del chatbot (todas las páginas pueden actualizarlo)
        dcc.Store(id='store-datos-chatbot-generacion', data={}),
        page_container,
        crear_componente_chat()  # ✨ Chat IA flotante integrado
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
            'color': '#333',
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

    app = Dash(
        __name__,
        use_pages=True,
        pages_folder="",
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

    _register_pages()
    _register_layout(app)
    _register_callbacks(app)

    return app
