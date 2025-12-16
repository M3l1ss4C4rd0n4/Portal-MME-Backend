# -*- coding: utf-8 -*-
import sys
import io

# Configurar salida estándar con UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Cargar variables de entorno desde .env
from dotenv import load_dotenv
load_dotenv()  # ✨ Carga OPENROUTER_API_KEY y otras variables

from dash import Dash, html, dcc
import dash_bootstrap_components as dbc
import logging
import os
from datetime import date, timedelta

# Configurar logging ANTES de cualquier otra cosa
from utils.logger import setup_logger, configure_root_logger

# Configurar logger raíz
configure_root_logger()

# Logger para este módulo
logger = setup_logger(__name__)

# Reducir verbosidad de otros loggers
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('dash').setLevel(logging.INFO)

# Banner de inicio
logger.info("=" * 70)
logger.info("INICIANDO PORTAL ENERGÉTICO MME")
logger.info(f"Ambiente: {os.getenv('DASH_ENV', 'development')}")
logger.info("=" * 70)

# OPTIMIZACIÓN: Pre-cargar conexión a API XM
logger.info("Inicializando conexión a API XM...")
try:
    from utils._xm import get_objetoAPI
    
    objetoAPI = get_objetoAPI()
    if objetoAPI:
        logger.info("API XM disponible")
    else:
        logger.warning("API XM no disponible")
except Exception as e:
    logger.warning(f"Error en inicialización API XM: {e}")

# Crear la aplicación Dash con soporte multi-página
app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
        "/assets/mme-corporate.css",
        "/assets/professional-style.css"
    ],
    external_scripts=[
        "/assets/navbar-active.js"
    ],
    suppress_callback_exceptions=True
)

# El servidor para Gunicorn
server = app.server

# ✅ HEALTH CHECK ENDPOINT
from flask import jsonify
from utils.health_check import verificar_salud_sistema

@server.route('/health')
def health_check():
    """Endpoint para monitoreo de salud del sistema"""
    salud = verificar_salud_sistema()
    
    # Determinar código HTTP según status
    if salud['status'] == 'healthy':
        status_code = 200
    elif salud['status'] == 'degraded':
        status_code = 200  # Aún funcional, pero con warnings
    else:
        status_code = 503  # Service Unavailable
    
    return jsonify(salud), status_code

# AHORA importar y registrar las páginas manualmente
import pages.index_simple_working
import pages.generacion_fuentes_unificado
import pages.comercializacion

# Importar page_container DESPUÉS de registrar páginas
from dash import page_container, Input, Output, State, callback

# Importar componente de chat IA
from componentes.chat_ia import crear_componente_chat

# Layout principal con page_container y chat IA
app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    page_container,
    crear_componente_chat()  # ✨ Chat IA flotante integrado
])

# Callback para el sidebar universal
@app.callback(
    [Output("sidebar-content", "style"),
     Output("sidebar-overlay", "style"),
     Output("sidebar-toggle", "style")],
    [Input("sidebar-toggle", "n_clicks"),
     Input("sidebar-close", "n_clicks"),
     Input("sidebar-overlay", "n_clicks")],
    [State("sidebar-content", "style"),
     State("sidebar-overlay", "style")],
    prevent_initial_call=True
)
def toggle_sidebar(toggle_clicks, close_clicks, overlay_clicks, sidebar_style, overlay_style):
    """Controlar la apertura y cierre del sidebar"""
    from dash import callback_context as ctx
    from utils.config import COLORS
    
    if not ctx.triggered:
        return sidebar_style, overlay_style, {'position': 'fixed', 'top': '20px', 'left': '20px', 'zIndex': '1050', 'borderRadius': '8px', 'padding': '10px 12px'}
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Estilos base
    sidebar_hidden = {
        'position': 'fixed',
        'top': '0',
        'left': '-300px',
        'width': '300px',
        'height': '100vh',
        'background': COLORS['bg_card'],
        'borderRight': f'1px solid {COLORS["border"]}',
        'boxShadow': '2px 0 10px rgba(0,0,0,0.1)',
        'zIndex': '1040',
        'transition': 'left 0.3s ease-in-out'
    }
    
    sidebar_visible = sidebar_hidden.copy()
    sidebar_visible['left'] = '0px'
    
    overlay_hidden = {
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100vw',
        'height': '100vh',
        'background': 'rgba(0,0,0,0.3)',
        'zIndex': '1030',
        'display': 'none'
    }
    
    overlay_visible = overlay_hidden.copy()
    overlay_visible['display'] = 'block'
    
    # Estilos del botón toggle
    toggle_visible = {
        'position': 'fixed',
        'top': '20px',
        'left': '20px',
        'zIndex': '1050',
        'borderRadius': '8px',
        'padding': '10px 12px',
        'display': 'block'
    }
    
    toggle_hidden = toggle_visible.copy()
    toggle_hidden['display'] = 'none'
    
    if button_id == "sidebar-toggle":
        # Abrir sidebar y ocultar botón
        return sidebar_visible, overlay_visible, toggle_hidden
    elif button_id in ["sidebar-close", "sidebar-overlay"]:
        # Cerrar sidebar y mostrar botón
        return sidebar_hidden, overlay_hidden, toggle_visible
    
    return sidebar_style, overlay_style, toggle_visible

# Callback para actualizar el estado activo del navbar
@app.callback(
    [Output(f'nav-link-{name}', 'style') for name in ['inicio', 'generacion', 'transmision', 'distribucion', 'comercializacion', 'perdidas', 'restricciones', 'metricas']],
    Input('url-navbar', 'pathname')
)
def update_navbar_active(pathname):
    """Resalta el link activo en el navbar según la ruta actual"""
    if pathname is None:
        pathname = '/'
    
    # Estilos base
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
    
    # Mapeo de rutas a links (con pattern matching para sub-rutas)
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
    
    # Determinar qué link está activo
    styles = []
    for name in ['inicio', 'generacion', 'transmision', 'distribucion', 'comercializacion', 'perdidas', 'restricciones', 'metricas']:
        if route_mapping[name](pathname):
            styles.append(active_style)
        else:
            styles.append(inactive_style)
    
    return styles

if __name__ == "__main__":
    import os
    from dash import page_registry
    
    port = int(os.environ.get('PORT', 8050))
    
    # Inicializar ReadDB ANTES de arrancar el servidor
    logger.info("🔧 Inicializando conexión a API XM...")
    from utils._xm import get_objetoAPI
    api_xm = get_objetoAPI()
    if api_xm:
        logger.info("✅ API XM inicializada correctamente")
    else:
        logger.warning("⚠️ API XM no disponible - se usarán datos en caché")
    
    # Información de páginas registradas
    logger.info(f"📄 Páginas registradas: {len(page_registry)}")
    for path, page_info in page_registry.items():
        logger.debug(f"  - {path}: {page_info.get('name', 'Sin nombre')}")
    
    logger.info("=" * 70)
    logger.info(f"🚀 Iniciando servidor Dash en puerto {port}")
    logger.info("📍 La aplicación estará disponible en:")
    logger.info(f"   - http://localhost:{port}")
    logger.info(f"   - http://127.0.0.1:{port}")
    logger.info(f"   - http://192.168.1.34:{port}")
    logger.info("=" * 70)
    
    try:
        app.run(debug=False, host='0.0.0.0', port=port)
    except Exception as e:
        logger.critical(f"❌ Error al iniciar servidor: {e}", exc_info=True)

# Exponer el servidor WSGI para Gunicorn
server = app.server