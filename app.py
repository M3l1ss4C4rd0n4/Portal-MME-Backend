# -*- coding: utf-8 -*-
"""Entry point simplificado usando app_factory"""
import os
from dash import page_registry

from core.app_factory import create_app
from infrastructure.logging.logger import get_logger

app = create_app()
server = app.server
logger = get_logger(__name__)


if __name__ == "__main__":
    # Configuración robusta para ejecución directa
    port = int(os.environ.get('PORT', 8050))
    debug_mode = os.environ.get('DASH_DEBUG', 'False').lower() == 'true'
    
    # Información de páginas registradas
    try:
        logger.info(f"📄 Páginas registradas: {len(page_registry)}")
        for path, page_info in page_registry.items():
            logger.info(f"  - {path}: {page_info.get('name', 'Sin nombre')}")
    except Exception as e:
        logger.error(f"Error listando páginas: {e}")

    logger.info("=" * 70)
    logger.info(f"🚀 Iniciando servidor Dash en puerto {port}")
    logger.info("📍 La aplicación estará disponible en:")
    logger.info(f"   - http://localhost:{port}")
    logger.info("=" * 70)

    try:
        app.run_server(
            host='0.0.0.0', 
            port=port, 
            debug=debug_mode,
            dev_tools_ui=debug_mode,
            dev_tools_props_check=debug_mode
        )
    except Exception as e:
        logger.critical(f"🔥 Error fatal iniciando servidor: {e}", exc_info=True)
