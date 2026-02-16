"""
Repositorio para líneas de transmisión.
Implementa ITransmissionRepository (Arquitectura Limpia - Inversión de Dependencias)
"""

from typing import Optional, List, Dict, Any
import pandas as pd
from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import ITransmissionRepository


class TransmissionRepository(BaseRepository, ITransmissionRepository):
    """
    Repositorio para tabla lineas_transmision.
    Implementa ITransmissionRepository para cumplir con arquitectura limpia.
    """
    
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
                fecha_publicacion AS "FechaPublicacion",
                fecha_registro AS "Fecha",
                codigo_linea AS "CodigoLinea",
                nombre_linea AS "NombreLinea",
                codigo_operador AS "CodigoOperador",
                fpo AS "FPO",
                sistema AS "Sistema",
                tension AS "Tension",
                longitud AS "Longitud",
                participacion_linea_nivel_tension AS "ParticipacionLineaNivelTension",
                participacion_linea_total AS "ParticipacionLineaTotal",
                longitud_nivel_tension AS "LongitudNivelTension",
                longitud_total AS "LongitudTotal",
                codigo_subarea_operativa AS "CodigoSubAreaOperativa",
                codigo_area_operativa AS "CodigoAreaOperativa",
                codigo_subestacion_origen AS "CodigoSubestacionOrigen",
                codigo_area_operativa_origen AS "CodigoAreaOperativaOrigen",
                codigo_subarea_operativa_origen AS "CodigoSubAreaOperativaOrigen",
                codigo_subestacion_destino AS "CodigoSubestacionDestino",
                codigo_area_operativa_destino AS "CodigoAreaOperativaDestino",
                codigo_subarea_operativa_destino AS "CodigoSubAreaOperativaDestino"
            FROM lineas_transmision
            WHERE fecha_registro::date = %s::date
            ORDER BY codigo_linea
        """
        return self.execute_dataframe(query, (fecha,))
    
    def get_latest_lines(self) -> pd.DataFrame:
        """
        Obtiene las líneas de la fecha más reciente
        """
        # Obtener TODAS las líneas de la fecha más reciente (sin filtro de fecha)
        # porque los datos de transmisión son relativamente estáticos
        query = """
            SELECT 
                fecha_publicacion AS "FechaPublicacion",
                fecha_registro AS "Fecha",
                codigo_linea AS "CodigoLinea",
                nombre_linea AS "NombreLinea",
                codigo_operador AS "CodigoOperador",
                fpo AS "FPO",
                sistema AS "Sistema",
                tension AS "Tension",
                longitud AS "Longitud",
                participacion_linea_nivel_tension AS "ParticipacionLineaNivelTension",
                participacion_linea_total AS "ParticipacionLineaTotal",
                longitud_nivel_tension AS "LongitudNivelTension",
                longitud_total AS "LongitudTotal",
                codigo_subarea_operativa AS "CodigoSubAreaOperativa",
                codigo_area_operativa AS "CodigoAreaOperativa",
                codigo_subestacion_origen AS "CodigoSubestacionOrigen",
                codigo_area_operativa_origen AS "CodigoAreaOperativaOrigen",
                codigo_subarea_operativa_origen AS "CodigoSubAreaOperativaOrigen",
                codigo_subestacion_destino AS "CodigoSubestacionDestino",
                codigo_area_operativa_destino AS "CodigoAreaOperativaDestino",
                codigo_subarea_operativa_destino AS "CodigoSubAreaOperativaDestino"
            FROM lineas_transmision
            WHERE fecha_registro = (SELECT MAX(fecha_registro) FROM lineas_transmision)
            ORDER BY codigo_linea
        """
        return self.execute_dataframe(query)
    
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
        
        # Insertar en PostgreSQL usando ON CONFLICT DO NOTHING (evita duplicados)
        query = f"""
            INSERT INTO lineas_transmision ({', '.join(available_cols)})
            VALUES ({', '.join(['%s' for _ in available_cols])})
            ON CONFLICT DO NOTHING
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
            WHERE fecha_registro < NOW() - INTERVAL '%s days'
        """
        result = self.execute_query(query, (days_to_keep,))    
    # Métodos adicionales para cumplir con ITransmissionRepository
    
    def get_all_lines(self) -> pd.DataFrame:
        """
        Obtiene todas las líneas de transmisión.
        Implementa método requerido por ITransmissionRepository.
        """
        return self.get_latest_lines()
    
    def get_lines_by_region(self, region: str) -> pd.DataFrame:
        """
        Obtiene líneas de transmisión por región (área operativa).
        Implementa método requerido por ITransmissionRepository.
        """
        query = """
            SELECT 
                fecha_registro AS "Fecha",
                codigo_linea AS "CodigoLinea",
                nombre_linea AS "NombreLinea",
                tension AS "Tension",
                longitud AS "Longitud",
                codigo_area_operativa AS "CodigoAreaOperativa"
            FROM lineas_transmision
            WHERE fecha_registro = (SELECT MAX(fecha_registro) FROM lineas_transmision)
              AND codigo_area_operativa = %s
            ORDER BY codigo_linea
        """
        return self.execute_dataframe(query, (region,))
    
    def get_lines_by_voltage(self, voltage: str) -> pd.DataFrame:
        """
        Obtiene líneas de transmisión por nivel de tensión.
        Implementa método requerido por ITransmissionRepository.
        """
        query = """
            SELECT 
                fecha_registro AS "Fecha",
                codigo_linea AS "CodigoLinea",
                nombre_linea AS "NombreLinea",
                tension AS "Tension",
                longitud AS "Longitud"
            FROM lineas_transmision
            WHERE fecha_registro = (SELECT MAX(fecha_registro) FROM lineas_transmision)
              AND tension = %s
            ORDER BY codigo_linea
        """
        return self.execute_dataframe(query, (voltage,))
    
    def get_total_count(self) -> int:
        """
        Obtiene el número total de líneas.
        Implementa método requerido por ITransmissionRepository (alias de get_total_lines).
        """
        return self.get_total_lines()
    
    def get_latest_update(self) -> Optional[str]:
        """
        Obtiene la fecha de última actualización.
        Implementa método requerido por ITransmissionRepository (alias de get_latest_date).
        """
        return self.get_latest_date()
