"""
Data Service - Acceso a datos del portal energético
"""
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

# Agregar el directorio padre al path para importar desde el proyecto principal
server_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(server_path))

logger = logging.getLogger(__name__)


class DataService:
    """
    Servicio de acceso a datos
    Conecta con la base de datos del portal energético
    """
    
    def __init__(self):
        """Inicializa el servicio de datos"""
        try:
            # Importar db_manager del proyecto principal
            from infrastructure.database.manager import db_manager
            self.db = db_manager
            logger.info("✅ DataService inicializado con db_manager del portal")
        except ImportError as e:
            logger.warning(f"⚠️ No se pudo importar db_manager: {e}")
            logger.warning("⚠️ DataService funcionará en modo mock")
            self.db = None
    
    async def get_latest_price(self) -> Optional[Dict]:
        """
        Obtiene el precio de bolsa más reciente
        """
        if not self.db:
            return self._mock_price_data()
        
        try:
            query = """
                SELECT 
                    fecha,
                    valor_gwh as precio
                FROM metrics
                WHERE metrica = 'PrecioBolsa'
                ORDER BY fecha DESC
                LIMIT 1
            """
            
            df = self.db.query_df(query)
            
            if df.empty:
                return None
            
            row = df.iloc[0]
            
            # Calcular promedio mensual
            query_avg = """
                SELECT AVG(valor_gwh) as promedio
                FROM metrics
                WHERE metrica = 'PrecioBolsa'
                AND fecha >= DATE('now', '-30 days')
            """
            df_avg = self.db.query_df(query_avg)
            promedio_mes = df_avg.iloc[0]['promedio'] if not df_avg.empty else 0
            
            return {
                "fecha": str(row['fecha']),
                "precio": float(row['precio']),
                "promedio_mes": float(promedio_mes)
            }
        
        except Exception as e:
            logger.error(f"Error obteniendo precio: {str(e)}")
            return None
    
    async def get_latest_generation(self) -> Optional[Dict]:
        """
        Obtiene generación más reciente por fuente
        """
        if not self.db:
            return self._mock_generation_data()
        
        try:
            # Obtener fecha más reciente
            query_latest_date = """
                SELECT MAX(fecha) as max_fecha
                FROM metrics
                WHERE metrica = 'Gene'
            """
            df_date = self.db.query_df(query_latest_date)
            
            if df_date.empty:
                return None
            
            latest_date = df_date.iloc[0]['max_fecha']
            
            # Obtener generación por fuente para esa fecha
            query = """
                SELECT 
                    recurso,
                    SUM(valor_gwh) as total_gwh
                FROM metrics
                WHERE metrica = 'Gene'
                AND DATE(fecha) = DATE(%s)
                GROUP BY recurso
                ORDER BY total_gwh DESC
            """
            
            df = self.db.query_df(query, params=(latest_date,))
            
            if df.empty:
                return None
            
            # Construir diccionario de fuentes
            sources = {}
            total = 0
            
            for _, row in df.iterrows():
                valor = float(row['total_gwh'])
                sources[row['recurso']] = valor
                total += valor
            
            return {
                "fecha": str(latest_date),
                "total_gwh": total,
                "sources": sources
            }
        
        except Exception as e:
            logger.error(f"Error obteniendo generación: {str(e)}")
            return None
    
    async def get_metric_data(
        self,
        metric_code: str,
        days: int = 7
    ) -> List[Dict]:
        """
        Obtiene datos históricos de una métrica
        
        Args:
            metric_code: Código de métrica (Gene, DemaReal, etc)
            days: Días hacia atrás
        """
        if not self.db:
            return []
        
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            query = """
                SELECT 
                    fecha,
                    valor_gwh,
                    recurso,
                    entidad
                FROM metrics
                WHERE metrica = %s
                AND fecha >= %s
                ORDER BY fecha DESC
            """
            
            df = self.db.query_df(query, params=(metric_code, start_date))
            
            if df.empty:
                return []
            
            return df.to_dict('records')
        
        except Exception as e:
            logger.error(f"Error obteniendo métrica {metric_code}: {str(e)}")
            return []
    
    # ═══════════════════════════════════════════════════════════
    # Mock Data (para cuando no hay DB disponible)
    # ═══════════════════════════════════════════════════════════
    
    def _mock_price_data(self) -> Dict:
        """Datos mock de precio"""
        return {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "precio": 285.50,
            "promedio_mes": 270.30
        }
    
    def _mock_generation_data(self) -> Dict:
        """Datos mock de generación"""
        return {
            "fecha": datetime.now().strftime("%Y-%m-%d"),
            "total_gwh": 185.5,
            "sources": {
                "HIDRAULICA": 125.3,
                "TERMICA": 45.2,
                "SOLAR": 10.5,
                "EOLICA": 4.5
            }
        }
