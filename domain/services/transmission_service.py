import logging
logger = logging.getLogger(__name__)
"""
Servicio de dominio para Transmisión
Maneja la lógica de negocio relacionada con líneas de transmisión
"""

from typing import Optional, Dict, Any
import pandas as pd
from datetime import datetime, timedelta
from infrastructure.database.repositories.transmission_repository import TransmissionRepository


class TransmissionService:
    """
    Servicio para el tablero de transmisión
    Sigue el patrón: DB First → API Fallback
    """
    
    def __init__(self, repo: Optional[TransmissionRepository] = None):
        self.repo = repo or TransmissionRepository()
        
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
