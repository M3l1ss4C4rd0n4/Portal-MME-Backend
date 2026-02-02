#!/usr/bin/env python3
"""
ETL para Datos de Distribución Eléctrica
Descarga métricas de XM/SIMEM y las persiste en SQLite

Ejecución: Cron diario 06:45 AM
"""

import sys
import os
from datetime import datetime, timedelta, date
import logging
from pathlib import Path
import pandas as pd

# Añadir ruta del servidor al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.services.distribution_service import DistributionService
from infrastructure.database.repositories.distribution_repository import DistributionRepository
from infrastructure.external.xm_service import XMService
from etl.config_distribucion import DISTRIBUTION_METRICS

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/admonctrlxm/server/logs/etl/etl_distribucion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DistributionETL:
    """
    Pipeline ETL para datos de distribución.
    """
    
    def __init__(self):
        self.repository = DistributionRepository()
        self.xm_service = XMService()
        self.metrics = DISTRIBUTION_METRICS
    
    def run(self, start_date: date = None, end_date: date = None):
        """
        Ejecuta ETL completo para todas las métricas de distribución.
        
        Args:
            start_date: Fecha inicio (por defecto: ayer)
            end_date: Fecha fin (por defecto: ayer)
        """
        # Por defecto: descargar datos de ayer (disponibles en madrugada)
        if not start_date:
            start_date = (datetime.now() - timedelta(days=1)).date()
        if not end_date:
            end_date = start_date
        
        logger.info(f"🚀 Iniciando ETL Distribución: {start_date} a {end_date}")
        
        success_count = 0
        error_count = 0
        
        for metric_code in self.metrics:
            try:
                logger.info(f"📥 Procesando métrica: {metric_code}")
                
                # 1. Extraer de API XM
                raw_df = self.xm_service.get_metric_data(
                    metric=metric_code,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if raw_df is None or raw_df.empty:
                    logger.warning(f"⚠️ No hay datos para {metric_code}")
                    continue
                
                # 2. Transformar (normalizar estructura)
                transformed_df = self._transform_data(raw_df, metric_code)
                
                # 3. Cargar en SQLite
                rows_saved = self.repository.save_metrics(transformed_df, metric_code)
                
                logger.info(f"✅ {metric_code}: {rows_saved} registros guardados")
                success_count += 1
            
            except Exception as e:
                logger.error(f"❌ Error procesando {metric_code}: {str(e)}", exc_info=True)
                error_count += 1
        
        # Resumen final
        logger.info(f"""
        ╔════════════════════════════════════╗
        ║   ETL DISTRIBUCIÓN COMPLETADO     ║
        ╠════════════════════════════════════╣
        ║ ✅ Exitosos: {success_count:2d}                 ║
        ║ ❌ Errores:  {error_count:2d}                 ║
        ║ 📅 Período:  {start_date} - {end_date}  ║
        ╚════════════════════════════════════╝
        """)
    
    def _transform_data(self, raw_df, metric_code: str):
        """
        Normaliza DataFrame de API XM a estructura del sistema.
        Maneja columnas horarias sumando valores (Energía/Pérdidas).
        """
        import json

        # 1. Detectar si es formato horario (Values_Hour01...Values_Hour24)
        hour_cols = [c for c in raw_df.columns if 'Values_Hour' in c]
        
        df = raw_df.copy()
        
        if hour_cols:
            # Lógica para datos horarios (SUMA para Distribución/Pérdidas)
            # Calcular suma diaria
            df['valor'] = df[hour_cols].sum(axis=1)
            
            # Serializar detalle horario
            # Convertir todas las columnas horarias a dict
            # orient='records' devuelve un array de dicts, tomamos la fila correspondiente
            # Pero más eficiente: apply row-wise
            def extract_hourly(row):
                return json.dumps({k: row[k] for k in hour_cols})
            
            df['extra_data'] = df.apply(extract_hourly, axis=1)
            
        else:
            # Lógica estándar (columna única)
            column_mapping = {
                'Values': 'valor',
                'Value': 'valor',
                'values': 'valor'
            }
            df = df.rename(columns=column_mapping)
            df['extra_data'] = None

        # Normalizar nombres comunes
        meta_mapping = {
            'Date': 'fecha',
            'Agente': 'agente'
        }
        df = df.rename(columns=meta_mapping)
        
        # Asegurar tipos
        if 'fecha' in df.columns:
            df['fecha'] = pd.to_datetime(df['fecha']).dt.date
        
        if 'valor' in df.columns:
            df['valor'] = pd.to_numeric(df['valor'], errors='coerce')
        
        # Añadir unidad según métrica
        df['unidad'] = self._get_unit(metric_code)
        
        # Completar agente si no existe
        if 'agente' not in df.columns:
            df['agente'] = None

        # Asegurar columna extra_data si no existe
        if 'extra_data' not in df.columns:
            df['extra_data'] = None

        # Validaciones
        df = df.dropna(subset=['fecha', 'valor'])
        
        return df[['fecha', 'valor', 'unidad', 'agente']]
    
    def _get_unit(self, metric_code: str) -> str:
        """Mapeo código métrica → unidad"""
        units = {
            'TXR': 'kWh',
            'RestAliv': 'COP',
            'PERCOM': '%',
            'RespComerAGC': 'COP',
            'CONSUM': 'GWh',
            'DemaReal': 'kWh',
            'PERD': '%',
            'PerdidasEner': 'kWh'
        }
        return units.get(metric_code, 'N/A')


def main():
    """Punto de entrada para cron"""
    try:
        etl = DistributionETL()
        
        # Argumentos opcionales: python etl_distribucion.py 2026-01-01 2026-01-31
        if len(sys.argv) == 3:
            start = datetime.strptime(sys.argv[1], '%Y-%m-%d').date()
            end = datetime.strptime(sys.argv[2], '%Y-%m-%d').date()
            etl.run(start, end)
        else:
            etl.run()  # Por defecto: ayer
        
        sys.exit(0)
    
    except Exception as e:
        logger.critical(f"💥 ETL FALLÓ COMPLETAMENTE: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
