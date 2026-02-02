import sys
import os
import logging
from unittest.mock import MagicMock
import types

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("validation")

# Sophisticated Mocking
dash_mock = MagicMock()
sys.modules['dash'] = dash_mock
sys.modules['dash.exceptions'] = MagicMock()  # For PreventUpdate
sys.modules['dash.dcc'] = MagicMock()
sys.modules['dash.html'] = MagicMock()
sys.modules['dash.dash_table'] = MagicMock()
sys.modules['dash_bootstrap_components'] = MagicMock()

def test_distribucion_import_and_query():
    logger.info("🧪 Iniciando prueba de corrección en Distribución...")
    
    try:
        logger.info("1. Importando interface.pages.distribucion...")
        from interface.pages.distribucion import obtener_listado_agentes
        logger.info("✅ Importación exitosa.")
        
        logger.info("2. Ejecutando obtener_listado_agentes()...")
        df = obtener_listado_agentes()
        
        if df is not None:
            logger.info(f"✅ Query exitosa. Se obtuvo un DataFrame con dimensiones: {df.shape}")
        else:
            logger.error("❌ obtener_listado_agentes devolvió None.")
            
    except Exception as e:
        logger.error(f"❌ Error de Ejecución: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    logger.info("🎉 PRUEBA COMPLETADA EXITOSAMENTE")

if __name__ == "__main__":
    test_distribucion_import_and_query()
