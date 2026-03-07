"""
Servicio de Dominio para Comercialización de Energía.
Gestiona precios de bolsa, contratos bilaterales y liquidaciones.
Implementa Inyección de Dependencias (Arquitectura Limpia - Fase 3)
"""

import pandas as pd
from datetime import date
from typing import Optional
import logging

from domain.interfaces.repositories import ICommercialRepository
from infrastructure.database.repositories.commercial_repository import CommercialRepository
from infrastructure.external.xm_service import XMService
from core.exceptions import DataNotFoundError

logger = logging.getLogger(__name__)


class CommercialService:
    """
    Servicio de dominio para gestión de datos de comercialización.
    Implementa Inyección de Dependencias - Depende de ICommercialRepository.
    """
    
    def __init__(self, repository: Optional[ICommercialRepository] = None, xm_service: Optional[XMService] = None):
        """
        Inicializa el servicio con inyección de dependencias opcional.
        
        Args:
            repository: Implementación de ICommercialRepository. Si es None, usa CommercialRepository() por defecto.
            xm_service: Servicio para API de XM. Si es None, usa XMService() por defecto.
        """
        self.repository = repository if repository is not None else CommercialRepository()
        self.xm_service = xm_service if xm_service is not None else XMService()
    
    def get_date_range(self) -> tuple:
        """Obtiene rango de fechas disponible para precios"""
        try:
            # Intentar repositorio commercial_metrics metrics
            min_date, max_date = self.repository.fetch_date_range('PrecEsca')
            if min_date and max_date:
                return pd.to_datetime(min_date).date(), pd.to_datetime(max_date).date()
            return date.today() - pd.Timedelta(days=365), date.today()
        except Exception as e:
            logger.warning("Error obteniendo rango de fechas: %s", e)
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

    def get_commercial_prices(self, start_date, end_date, agent: Optional[str] = None) -> pd.DataFrame:
        """
        Obtiene precios comerciales de energía.
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            agent: Agente específico (opcional)
        
        Returns:
            DataFrame con columnas: fecha, agente, precio ($/kWh)
        """
        try:
            from datetime import date as date_type
            
            # Convertir fechas
            if isinstance(start_date, date_type):
                start_date_obj = start_date
            else:
                start_date_obj = pd.to_datetime(start_date).date()
            
            if isinstance(end_date, date_type):
                end_date_obj = end_date
            else:
                end_date_obj = pd.to_datetime(end_date).date()
            
            # Usar método existente para obtener precios de bolsa
            df = self.get_stock_price(start_date_obj, end_date_obj)
            
            if df.empty:
                logger.warning("⚠️ No hay datos de precios comerciales")
                return pd.DataFrame()
            
            # Adaptar formato para API
            resultado = pd.DataFrame()
            resultado['fecha'] = df['fecha']
            resultado['precio'] = df['valor']
            
            if agent:
                resultado['agente'] = agent
            else:
                resultado['agente'] = 'Sistema'
            
            logger.info(f"✅ {len(resultado)} registros de precios obtenidos")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo precios comerciales: {e}")
            return pd.DataFrame()

    def get_usuarios_por_departamento(self) -> pd.DataFrame:
        """
        Estimación de usuarios del servicio eléctrico por departamento.
        Fuente: SUI (Sistema Único de Información) 2023.
        Total Colombia: ~16.8 millones de usuarios.
        """
        USUARIOS_SUI_2023 = {
            'Bogotá D.C.':        ('11', 3_100),
            'Antioquia':          ('05', 2_650),
            'Valle del Cauca':    ('76', 1_850),
            'Cundinamarca':       ('25',   900),
            'Atlántico':          ('08',   820),
            'Bolívar':            ('13',   650),
            'Santander':          ('68',   620),
            'Córdoba':            ('23',   450),
            'Nariño':             ('52',   410),
            'Tolima':             ('73',   370),
            'Norte de Santander': ('54',   355),
            'Huila':              ('41',   290),
            'Boyacá':             ('15',   285),
            'Meta':               ('50',   260),
            'Caldas':             ('17',   250),
            'Risaralda':          ('66',   230),
            'Cauca':              ('19',   220),
            'Cesar':              ('20',   210),
            'Magdalena':          ('47',   205),
            'Sucre':              ('70',   190),
            'La Guajira':         ('44',   175),
            'Quindío':            ('63',   145),
            'Casanare':           ('85',   120),
            'Chocó':              ('27',    95),
            'Caquetá':            ('18',    80),
            'Putumayo':           ('86',    65),
            'Arauca':             ('81',    60),
            'San Andrés':         ('88',    25),
            'Amazonas':           ('91',    20),
            'Guaviare':           ('95',    30),
            'Guainía':            ('94',    12),
            'Vaupés':             ('97',    10),
            'Vichada':            ('99',    15),
        }
        TOTAL = 16_800
        rows = []
        for dept, (codigo, usuarios) in USUARIOS_SUI_2023.items():
            rows.append({
                'departamento': dept,
                'codigo_dpto': codigo,
                'usuarios_miles': usuarios,
                'participacion_pct': round(usuarios / TOTAL * 100, 2),
                'cobertura_est': (
                    '> 95%' if usuarios > 500
                    else '80-95%' if usuarios > 100
                    else '< 80%'
                ),
            })
        return pd.DataFrame(rows).sort_values('usuarios_miles', ascending=False)
