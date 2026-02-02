"""
Repositorio para líneas de transmisión
"""

from typing import Optional, List, Dict, Any
import pandas as pd
from infrastructure.database.repositories.base_repository import BaseRepository


class TransmissionRepository(BaseRepository):
    """Repositorio para tabla lineas_transmision"""
    
    def get_latest_date(self) -> Optional[str]:
        """Obtiene la fecha más reciente en la base de datos"""
        query = "SELECT MAX(fecha_registro) as max_date FROM lineas_transmision"
        row = self.execute_query_one(query)
        return row["max_date"] if row and row.get("max_date") else None
    
    def get_total_lines(self) -> int:
        """Cuenta el total de líneas únicas"""
        query = "SELECT COUNT(DISTINCT codigo_linea) as count FROM lineas_transmision"
        row = self.execute_query_one(query)
        return int(row["count"]) if row else 0
    
    def get_lines_by_date(self, fecha: str) -> pd.DataFrame:
        """
        Obtiene todas las líneas de una fecha específica
        """
        query = """
            SELECT 
                fecha_publicacion as FechaPublicacion,
                fecha_registro as Fecha,
                codigo_linea as CodigoLinea,
                nombre_linea as NombreLinea,
                codigo_operador as CodigoOperador,
                fpo as FPO,
                sistema as Sistema,
                tension as Tension,
                longitud as Longitud,
                participacion_linea_nivel_tension as ParticipacionLineaNivelTension,
                participacion_linea_total as ParticipacionLineaTotal,
                longitud_nivel_tension as LongitudNivelTension,
                longitud_total as LongitudTotal,
                codigo_subarea_operativa as CodigoSubAreaOperativa,
                codigo_area_operativa as CodigoAreaOperativa,
                codigo_subestacion_origen as CodigoSubestacionOrigen,
                codigo_area_operativa_origen as CodigoAreaOperativaOrigen,
                codigo_subarea_operativa_origen as CodigoSubAreaOperativaOrigen,
                codigo_subestacion_destino as CodigoSubestacionDestino,
                codigo_area_operativa_destino as CodigoAreaOperativaDestino,
                codigo_subarea_operativa_destino as CodigoSubAreaOperativaDestino
            FROM lineas_transmision
            WHERE fecha_registro = ?
            ORDER BY codigo_linea
        """
        return self.execute_dataframe(query, (fecha,))
    
    def get_latest_lines(self) -> pd.DataFrame:
        """
        Obtiene las líneas de la fecha más reciente
        """
        latest_date = self.get_latest_date()
        if not latest_date:
            return pd.DataFrame()
        return self.get_lines_by_date(latest_date)
    
    def bulk_insert_lines(self, df: pd.DataFrame) -> int:
        """
        Inserta múltiples líneas desde un DataFrame
        Retorna el número de registros insertados
        """
        if df.empty:
            return 0
            
        # Mapear columnas del API a columnas de la DB
        column_mapping = {
            'FechaPublicacion': 'fecha_publicacion',
            'Fecha': 'fecha_registro',
            'CodigoLinea': 'codigo_linea',
            'NombreLinea': 'nombre_linea',
            'CodigoOperador': 'codigo_operador',
            'FPO': 'fpo',
            'Sistema': 'sistema',
            'Tension': 'tension',
            'Longitud': 'longitud',
            'ParticipacionLineaNivelTension': 'participacion_linea_nivel_tension',
            'ParticipacionLineaTotal': 'participacion_linea_total',
            'LongitudNivelTension': 'longitud_nivel_tension',
            'LongitudTotal': 'longitud_total',
            'CodigoSubAreaOperativa': 'codigo_subarea_operativa',
            'CodigoAreaOperativa': 'codigo_area_operativa',
            'CodigoSubestacionOrigen': 'codigo_subestacion_origen',
            'CodigoAreaOperativaOrigen': 'codigo_area_operativa_origen',
            'CodigoSubAreaOperativaOrigen': 'codigo_subarea_operativa_origen',
            'CodigoSubestacionDestino': 'codigo_subestacion_destino',
            'CodigoAreaOperativaDestino': 'codigo_area_operativa_destino',
            'CodigoSubAreaOperativaDestino': 'codigo_subarea_operativa_destino'
        }
        
        # Renombrar columnas
        df_mapped = df.rename(columns=column_mapping)
        
        # Seleccionar solo las columnas que existen
        available_cols = [col for col in column_mapping.values() if col in df_mapped.columns]
        df_insert = df_mapped[available_cols].copy()
        
        # Convertir Timestamps a string para SQLite
        date_cols = ['fecha_publicacion', 'fecha_registro', 'fpo']
        for col in date_cols:
            if col in df_insert.columns:
                df_insert[col] = df_insert[col].astype(str).replace({'NaT': None, 'nan': None})
        
        # Insertar en SQLite usando INSERT OR IGNORE (evita duplicados)
        query = f"""
            INSERT OR IGNORE INTO lineas_transmision ({', '.join(available_cols)})
            VALUES ({', '.join(['?' for _ in available_cols])})
        """
        
        inserted = 0
        for _, row in df_insert.iterrows():
            try:
                params = tuple(row[col] for col in available_cols)
                self.execute_non_query(query, params)
                inserted += 1
            except Exception as e:
                print(f"Error insertando línea {row.get('codigo_linea', 'unknown')}: {e}")
                
        return inserted
    
    def delete_old_data(self, days_to_keep: int = 90) -> int:
        """
        Elimina datos antiguos, manteniendo solo los últimos N días
        """
        query = """
            DELETE FROM lineas_transmision 
            WHERE fecha_registro < date('now', '-' || ? || ' days')
        """
        result = self.execute_query(query, (days_to_keep,))
        return result if result else 0
