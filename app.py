# -*- coding: utf-8 -*-
"""Entry point simplificado usando app_factory"""

import os
from dash import page_registry

from core.app_factory import create_app
from shared.logging.logger import get_logger


app = create_app()
server = app.server
logger = get_logger(__name__)


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8050))

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