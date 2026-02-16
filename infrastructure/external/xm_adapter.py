"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                          XM DATA SOURCE ADAPTER                               ║
║                                                                               ║
║  Adaptador que implementa IXMDataSource para acceso a la API de XM           ║
║  Envuelve xm_service.py para cumplir con arquitectura limpia                 ║
║  Permite intercambiar implementaciones sin afectar el dominio                ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

from typing import Optional, Any
from datetime import date
import pandas as pd
import logging

from domain.interfaces.data_sources import IXMDataSource
from infrastructure.external.xm_service import (
    fetch_metric_data,
    get_objetoAPI,
    _PYDATAXM_AVAILABLE
)

logger = logging.getLogger(__name__)


class XMDataSourceAdapter(IXMDataSource):
    """
    Adaptador que implementa IXMDataSource para la API de XM.
    
    Envuelve las funciones de xm_service.py (fetch_metric_data, get_objetoAPI)
    para cumplir con el contrato de IXMDataSource definido en el dominio.
    
    Beneficios:
    - Domain no depende de implementación específica de xm_service
    - Permite intercambiar implementaciones (mock, caché, otra API)
    - Cumple con el Principio de Inversión de Dependencias (DIP)
    """
    
    def __init__(self):
        """Inicializa el adaptador."""
        self._api_object = None
    
    def fetch_metric_data(
        self,
        metric: str,
        entity: str,
        start_date: date,
        end_date: date
    ) -> Optional[pd.DataFrame]:
        """
        Consulta datos de una métrica específica desde la API de XM.
        
        Args:
            metric: Código de métrica (ej: 'Gene', 'PrecBolsNaci')
            entity: Entidad (ej: 'Sistema', 'Recurso', 'Embalse')
            start_date: Fecha inicial
            end_date: Fecha final
            
        Returns:
            DataFrame con los datos o None si no hay datos disponibles
        """
        try:
            logger.debug(f"Consultando API XM: {metric}/{entity} desde {start_date} hasta {end_date}")
            
            # Llamar a la función de xm_service
            df = fetch_metric_data(
                metric=metric,
                entity=entity,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is not None and not df.empty:
                logger.info(f"✅ API XM retornó {len(df)} registros para {metric}/{entity}")
                return df
            else:
                logger.warning(f"⚠️ API XM sin datos para {metric}/{entity}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error consultando API XM: {e}")
            return None
    
    def get_api_object(self) -> Optional[Any]:
        """
        Obtiene el objeto API subyacente (ReadDB de pydataxm).
        
        Útil para operaciones avanzadas que requieren acceso directo.
        
        Returns:
            Objeto ReadDB de pydataxm o None si no está disponible
        """
        if self._api_object is None:
            self._api_object = get_objetoAPI()
        
        return self._api_object
    
    def is_available(self) -> bool:
        """
        Verifica si la fuente de datos de XM está disponible.
        
        Returns:
            True si pydataxm está disponible y funcional
        """
        if not _PYDATAXM_AVAILABLE:
            logger.warning("pydataxm no está disponible")
            return False
        
        api_obj = self.get_api_object()
        return api_obj is not None
    
    def fetch_catalog(self, catalog_name: str) -> Optional[pd.DataFrame]:
        """
        Obtiene un catálogo de XM (ListadoRecursos, ListadoEmbalses, etc.).
        
        Args:
            catalog_name: Nombre del catálogo
            
        Returns:
            DataFrame con el catálogo o None si no está disponible
        """
        try:
            api_obj = self.get_api_object()
            
            if api_obj is None:
                logger.warning(f"API XM no disponible para catálogo {catalog_name}")
                return None
            
            logger.debug(f"Consultando catálogo XM: {catalog_name}")
            
            # Los catálogos no tienen rango de fechas, usar fecha actual
            from datetime import datetime
            fecha = datetime.now()
            
            df = api_obj.request_data(catalog_name, "Sistema", fecha, fecha)
            
            if df is not None and not df.empty:
                logger.info(f"✅ Catálogo {catalog_name}: {len(df)} registros")
                return df
            else:
                logger.warning(f"⚠️ Catálogo {catalog_name} sin datos")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo catálogo {catalog_name}: {e}")
            return None
