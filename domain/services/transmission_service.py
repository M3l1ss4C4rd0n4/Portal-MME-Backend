"""
Servicio de dominio para Transmisión.
Maneja la lógica de negocio relacionada con líneas de transmisión.
Implementa Inyección de Dependencias (Arquitectura Limpia - Fase 3)
"""

import logging
from typing import Optional, Dict, Any
import pandas as pd
from datetime import datetime, timedelta

from domain.interfaces.repositories import ITransmissionRepository
from infrastructure.database.repositories.transmission_repository import TransmissionRepository

logger = logging.getLogger(__name__)


class TransmissionService:
    """
    Servicio para el tablero de transmisión.
    Sigue el patrón: DB First → API Fallback.
    Implementa Inyección de Dependencias - Depende de ITransmissionRepository.
    """
    
    def __init__(self, repository: Optional[ITransmissionRepository] = None):
        """
        Inicializa el servicio con inyección de dependencias opcional.
        
        Args:
            repository: Implementación de ITransmissionRepository. Si es None, usa TransmissionRepository() por defecto.
        """
        self.repo = repository if repository is not None else TransmissionRepository()
        
    def get_transmission_lines(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Obtiene datos de líneas de transmisión
        
        Args:
            force_refresh: Si es True, fuerza actualización desde API
            
        Returns:
            DataFrame con columnas normalizadas
        """
        try:
            # 1. Intentar obtener de DB
            if not force_refresh:
                df = self.repo.get_latest_lines()
                
                if not df.empty:
                    # Verificar que los datos no sean muy antiguos (> 7 días)
                    latest_date = self.repo.get_latest_date()
                    if latest_date:
                        latest_dt = pd.to_datetime(latest_date)
                        days_old = (datetime.now() - latest_dt).days
                        
                        if days_old <= 7:
                            logger.info(f"✅ Datos de transmisión desde DB: {len(df)} líneas (antigüedad: {days_old} días)")
                            return self._normalize_dataframe(df)
                        else:
                            logger.info(f"⚠️ Datos en DB tienen {days_old} días. Se recomienda ejecutar ETL.")
            
            # 2. Si DB está vacía o datos antiguos, retornar vacío
            # (El ETL debe ejecutarse para poblar)
            logger.info("⚠️ No hay datos recientes en DB. Ejecute el ETL de transmisión.")
            return pd.DataFrame()
            
        except Exception as e:
            logger.info(f"❌ Error en TransmissionService: {e}")
            return pd.DataFrame()
    
    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza el DataFrame para uso consistente
        """
        if df.empty:
            return df
            
        # Convertir fechas
        date_columns = ['Fecha', 'FechaPublicacion', 'FPO']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Convertir numéricos
        numeric_columns = [
            'Tension', 'Longitud', 
            'ParticipacionLineaNivelTension', 'ParticipacionLineaTotal',
            'LongitudNivelTension', 'LongitudTotal'
        ]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas resumidas del sistema de transmisión
        """
        df = self.get_transmission_lines()
        
        if df.empty:
            return {
                'total_lines': 0,
                'total_length_km': 0,
                'operators_count': 0,
                'latest_date': None
            }
        
        return {
            'total_lines': df['CodigoLinea'].nunique(),
            'total_length_km': df['LongitudTotal'].iloc[0] if len(df) > 0 else 0,
            'operators_count': df['CodigoOperador'].nunique(),
            'latest_date': df['Fecha'].max().strftime('%Y-%m-%d') if not df['Fecha'].isna().all() else None,
            'voltage_levels': sorted(df['Tension'].dropna().unique().tolist()),
            'systems': df['Sistema'].unique().tolist()
        }

    def get_lineas_transmision(self) -> pd.DataFrame:
        """
        Obtiene catálogo de líneas de transmisión con información detallada.
        
        Returns:
            DataFrame con columnas: nombre, subestacion_origen, subestacion_destino,
                                   tension_kv, operador, longitud_km, capacidad_mw
        """
        try:
            df = self.get_transmission_lines()
            
            if df.empty:
                logger.warning("⚠️ No hay datos de líneas de transmisión")
                return pd.DataFrame()
            
            # Normalizar columnas para API
            resultado = pd.DataFrame()
            resultado['nombre'] = df.get('CodigoLinea', df.get('Linea', ''))
            resultado['subestacion_origen'] = df.get('SubestacionOrigen', '')
            resultado['subestacion_destino'] = df.get('SubestacionDestino', '')
            resultado['tension_kv'] = df.get('Tension', 0)
            resultado['operador'] = df.get('CodigoOperador', df.get('Operador', ''))
            resultado['longitud_km'] = df.get('Longitud', df.get('LongitudTotal', 0))
            resultado['capacidad_mw'] = df.get('Capacidad', None)  # Si existe
            
            logger.info(f"✅ {len(resultado)} líneas de transmisión obtenidas")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo líneas de transmisión: {e}")
            return pd.DataFrame()

    def get_intercambios_internacionales(self, start_date, end_date) -> pd.DataFrame:
        """
        Obtiene intercambios internacionales de energía.
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
        
        Returns:
            DataFrame con columnas: fecha, pais, importacion_gwh, exportacion_gwh, neto_gwh
        """
        try:
            from datetime import date as date_type
            from infrastructure.database.repositories.metrics_repository import MetricsRepository
            
            # Convertir fechas
            if isinstance(start_date, date_type):
                start_str = start_date.strftime('%Y-%m-%d')
            else:
                start_str = str(start_date)
            
            if isinstance(end_date, date_type):
                end_str = end_date.strftime('%Y-%m-%d')
            else:
                end_str = str(end_date)
            
            repo = MetricsRepository()
            
            # Consultar intercambios desde metrics (si existen)
            # Métricas típicas: InterEcua, InterVene, InterPana para intercambios
            query = """
                SELECT 
                    fecha,
                    recurso as pais,
                    SUM(CASE WHEN metrica LIKE 'Impo%' THEN valor_gwh ELSE 0 END) as importacion_gwh,
                    SUM(CASE WHEN metrica LIKE 'Expo%' THEN valor_gwh ELSE 0 END) as exportacion_gwh,
                    SUM(valor_gwh) as neto_gwh
                FROM metrics
                WHERE fecha BETWEEN %s AND %s
                AND (metrica LIKE 'Inter%' OR metrica LIKE 'Impo%' OR metrica LIKE 'Expo%')
                AND recurso IN ('Ecuador', 'Venezuela', 'Panama', 'Panamá')
                GROUP BY fecha, recurso
                ORDER BY fecha, recurso
            """
            
            df = repo.execute_dataframe(query, (start_str, end_str))
            
            if df is None or df.empty:
                logger.info("⚠️ No hay datos de intercambios internacionales")
                return pd.DataFrame()
            
            logger.info(f"✅ {len(df)} registros de intercambios obtenidos")
            return df
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo intercambios internacionales: {e}")
            return pd.DataFrame()
