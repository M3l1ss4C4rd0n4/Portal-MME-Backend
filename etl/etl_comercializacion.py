#!/usr/bin/env python3
"""
ETL para Datos de Comercialización Eléctrica
Descarga métricas de XM/SIMEM y las persiste en SQLite

Ejecución: Cron diario 07:00 AM
"""

import sys
from datetime import datetime, timedelta, date
import logging
from pathlib import Path
import pandas as pd

# Añadir ruta del servidor al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.services.commercial_service import CommercialService
from infrastructure.database.repositories.commercial_repository import CommercialRepository
from infrastructure.external.xm_service import XMService
from etl.config_comercializacion import COMMERCIAL_METRICS

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/admonctrlxm/server/logs/etl/etl_comercializacion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class CommercialETL:
    """
    Pipeline ETL para datos de comercialización.
    """
    
    def __init__(self):
        self.repository = CommercialRepository()
        self.xm_service = XMService()
        self.metrics = COMMERCIAL_METRICS
    
    def run(self, start_date: date = None, end_date: date = None):
        if not start_date:
            start_date = (datetime.now() - timedelta(days=1)).date()
        if not end_date:
            end_date = start_date
        
        logger.info(f"🚀 Iniciando ETL Comercialización: {start_date} a {end_date}")
        
        success_count = 0
        error_count = 0
        
        for metric_code in self.metrics:
            try:
                logger.info(f"📥 Procesando métrica: {metric_code}")
                
                raw_df = self.xm_service.get_metric_data(
                    metric=metric_code,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if raw_df is None or raw_df.empty:
                    logger.warning(f"⚠️ No hay datos para {metric_code}")
                    continue
                
                transformed_df = self._transform_data(raw_df, metric_code)
                rows_saved = self.repository.save_metrics(transformed_df, metric_code)
                
                logger.info(f"✅ {metric_code}: {rows_saved} registros guardados")
                success_count += 1
            
            except Exception as e:
                logger.error(f"❌ Error procesando {metric_code}: {str(e)}", exc_info=True)
                error_count += 1
        
        logger.info(f"Terminado. Success: {success_count}, Errors: {error_count}")
    
    def _transform_data(self, raw_df, metric_code: str):
        column_mapping = {
            'Values': 'valor',
            'Value': 'valor',
            'Date': 'fecha',
        }
        if 'Agente' in raw_df.columns:
            column_mapping['Agente'] = 'agente_comprador'

        df = raw_df.rename(columns=column_mapping)
        df = df.copy()
        
        # Manejo de datos horarios
        hour_cols = [c for c in df.columns if 'Values_Hour' in c]
        extra_data_list = []
        
        if hour_cols:
            import json
            # Calcular valor promedio (para precios) o suma (para energía, pendiente lógica)
            # Para Comercialización (Precios), usamos PROMEDIO
            if 'valor' not in df.columns:
                df['valor'] = df[hour_cols].mean(axis=1)
            
            # Serializar horario a JSON para extra_data
            for _, row in df.iterrows():
                try:
                    horas_dict = {
                        # "Hora_01": 123.45, etc
                        f"Hora_{c[-2:]}": row[c] for c in hour_cols
                    }
                    extra_data_list.append(json.dumps(horas_dict))
                except:
                    extra_data_list.append(None)
            
            df['extra_data'] = extra_data_list
        else:
            df['extra_data'] = None

        if 'fecha' in df.columns:
            df['fecha'] = pd.to_datetime(df['fecha']).dt.date
        if 'valor' in df.columns:
            df['valor'] = pd.to_numeric(df['valor'], errors='coerce')
        
        df['unidad'] = self._get_unit(metric_code)
        
        for col in ['agente_comprador', 'agente_vendedor', 'tipo_contrato', 'extra_data']:
            if col not in df.columns:
                df[col] = None
        
        df = df.dropna(subset=['fecha', 'valor'])
        return df[['fecha', 'valor', 'unidad', 'agente_comprador', 'agente_vendedor', 'tipo_contrato', 'extra_data']]
    
    def _get_unit(self, metric_code: str) -> str:
        units = {
            'PrecBolsNaci': 'COP_kWh',
            'CostMargDesp': 'COP_kWh',
            'PrecPromCont': 'COP_kWh',
            'PrecBolsCTG': 'COP_kWh',
        }
        return units.get(metric_code, 'N/A')


def main():
    try:
        etl = CommercialETL()
        if len(sys.argv) == 3:
            start = datetime.strptime(sys.argv[1], '%Y-%m-%d').date()
            end = datetime.strptime(sys.argv[2], '%Y-%m-%d').date()
            etl.run(start, end)
        else:
            etl.run()
        sys.exit(0)
    except Exception as e:
        logger.critical(f"💥 ETL FALLÓ: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
