"""
Servicio de Dominio para Comercialización de Energía
Gestiona precios de bolsa, contratos bilaterales y liquidaciones
"""

import pandas as pd
from datetime import datetime, date
from typing import Optional, List, Dict
import logging

from infrastructure.database.repositories.commercial_repository import CommercialRepository
from infrastructure.external.xm_service import XMService
from core.exceptions import DataNotFoundError

logger = logging.getLogger(__name__)


class CommercialService:
    """
    Servicio de dominio para gestión de datos de comercialización.
    """
    
    def __init__(self):
        self.repository = CommercialRepository()
        self.xm_service = XMService()
    
    def get_date_range(self) -> tuple:
        """Obtiene rango de fechas disponible para precios"""
        try:
            # Intentar repositorio commercial_metrics metrics
            min_date, max_date = self.repository.fetch_date_range('PrecEsca')
            if min_date and max_date:
                return pd.to_datetime(min_date).date(), pd.to_datetime(max_date).date()
            return date.today() - pd.Timedelta(days=365), date.today()
        except:
            return date.today() - pd.Timedelta(days=365), date.today()

    def get_stock_price(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Obtiene Precio Bolsa Nacional (Promedio) con detalle horario"""
        return self._get_price_metric('PrecBolsNaci', 'Precio Bolsa Nacional', start_date, end_date)

    def get_scarcity_price(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Obtiene Precio Escasez con detalle horario"""
        return self._get_price_metric('PrecEsca', 'Precio Escasez', start_date, end_date)

    def get_activation_scarcity_price(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Obtiene Precio Escasez Activación con detalle horario"""
        return self._get_price_metric('PrecEscaAct', 'Precio Escasez Activación', start_date, end_date)

    def get_superior_scarcity_price(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Obtiene Precio Escasez Superior"""
        return self._get_price_metric('PrecEscaSup', 'Precio Escasez Superior', start_date, end_date)

    def get_inferior_scarcity_price(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Obtiene Precio Escasez Inferior"""
        return self._get_price_metric('PrecEscaInf', 'Precio Escasez Inferior', start_date, end_date)

    def _get_price_metric(self, metric_code: str, metric_name: str, start: date, end: date) -> pd.DataFrame:
        try:
            # 1. Intentar DB
            df = self.repository.fetch_commercial_metrics(metric_code, start, end)
            
            # Si DB está vacío o faltan datos, ir a API (Fallback simple por ahora: si vacío todo, ir a API)
            if df.empty:
                logger.info(f"DB vacía para {metric_code}, consultando API...")
                df_api = self.xm_service.get_metric_data(metric_code, start, end)
                if df_api is None or df_api.empty:
                    return pd.DataFrame()
                
                # Procesar API raw a estructura final
                return self._process_price_data_from_api(df_api, metric_name)
            
            # Si viene de DB, procesar 'extra_data' a dict
            import json
            df['Datos_Horarios'] = df['extra_data'].apply(lambda x: json.loads(x) if x else None)
            df['Date'] = pd.to_datetime(df['fecha'])
            df['Value'] = df['valor']
            df['Metrica'] = metric_name
            
            return df[['Date', 'Value', 'Metrica', 'Datos_Horarios']]

        except Exception as e:
            logger.error(f"Error procesando precio {metric_code}: {e}")
            return pd.DataFrame()

    def _process_price_data_from_api(self, df: pd.DataFrame, metric_name: str) -> pd.DataFrame:
        """Procesa datos crudos de API (con columnas horarias) a formato UI"""
        # Eliminar duplicados
        df = df.drop_duplicates(subset=['Date'], keep='first')
        
        # Identificar cols horarias
        hour_cols = [c for c in df.columns if 'Values_Hour' in c]
        
        if not hour_cols and 'Value' not in df.columns:
            return pd.DataFrame()
            
        df['Date'] = pd.to_datetime(df['Date'])
        
        # Calcular valor diario (promedio)
        if hour_cols:
            df['Value'] = df[hour_cols].mean(axis=1)
            
            # Generar JSON horario
            datos_horarios = []
            for _, row in df.iterrows():
                datos_hora = {'Date': row['Date'].strftime('%Y-%m-%d')}
                for i, col in enumerate(hour_cols, 1):
                    datos_hora[f'Hora_{i:02d}'] = float(row[col]) if pd.notna(row[col]) else None
                datos_horarios.append(datos_hora)
            df['Datos_Horarios'] = datos_horarios
        else:
            # Caso sin horas
            df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
            df['Datos_Horarios'] = None
            
        df['Metrica'] = metric_name
        
        return df[['Date', 'Value', 'Metrica', 'Datos_Horarios']]

    def get_commercial_data(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente_comprador: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Obtiene datos de comercialización.
        """
        logger.info(f"Solicitando {metric_code} comercial desde {start_date} hasta {end_date}")
        
        try:
            # 1. DB First
            df = self.repository.fetch_commercial_metrics(
                metric_code=metric_code,
                start_date=start_date,
                end_date=end_date,
                agente_comprador=agente_comprador
            )
            
            if not df.empty:
                logger.info(f"✅ Datos en DB local: {len(df)} registros")
                return df
            
            # 2. API Fallback
            logger.warning(f"⚠️ DB vacío, intentando API externa para {metric_code}")
            df = self._fetch_from_external_api(metric_code, start_date, end_date, agente_comprador)
            
            if not df.empty:
                logger.info(f"✅ Datos API: {len(df)} registros")
                return df
            
            raise DataNotFoundError(f"Sin datos para {metric_code}")
        
        except Exception as e:
            logger.error(f"❌ Error commercial service: {str(e)}")
            raise

    def _fetch_from_external_api(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente_comprador: Optional[str]
    ) -> pd.DataFrame:
        try:
            raw_data = self.xm_service.get_metric_data(
                metric=metric_code,
                start_date=start_date,
                end_date=end_date
            )
            df = self._normalize_dataframe(raw_data, metric_code)
            
            if agente_comprador and 'agente_comprador' in df.columns:
                df = df[df['agente_comprador'] == agente_comprador]
            
            return df
        except Exception as e:
            logger.error(f"Error API: {e}")
            return pd.DataFrame()

    def _normalize_dataframe(self, raw_df: pd.DataFrame, metric_code: str) -> pd.DataFrame:
        if raw_df is None or raw_df.empty:
            return pd.DataFrame()
            
        column_mapping = {
            'Values': 'valor',
            'Date': 'fecha',
        }
        # Adaptar si devuelve Agente como comprador o vendedor no es directo en pydataxm genérico
        # Pydataxm suele devolver Agente o Sistema
        if 'Agente' in raw_df.columns:
            column_mapping['Agente'] = 'agente_comprador' # Asunción por defecto
        
        df = raw_df.rename(columns=column_mapping)
        
        if 'fecha' in df.columns:
             df['fecha'] = pd.to_datetime(df['fecha']).dt.date
        if 'valor' in df.columns:
             df['valor'] = pd.to_numeric(df['valor'], errors='coerce')
        
        df['unidad'] = self._get_metric_unit(metric_code)
        
        # Completar columnas
        for col in ['agente_comprador', 'agente_vendedor', 'tipo_contrato']:
            if col not in df.columns:
                df[col] = None
                
        return df[['fecha', 'valor', 'unidad', 'agente_comprador', 'agente_vendedor', 'tipo_contrato']]

    def _get_metric_unit(self, metric_code: str) -> str:
        units = {
            'PrecBolsNaci': 'COP/kWh',
            'PrecBolsCTG': 'COP/kWh',
            'CONTRATO': 'kWh',
        }
        return units.get(metric_code, 'N/A')
        
    def get_available_buyers(self):
        return self.repository.get_available_buyers()
