"""
Repositorio de datos de distribución eléctrica.
Gestiona persistencia en SQLite.
"""

import sqlite3
import pandas as pd
from datetime import date
from typing import Optional, List, Dict
import logging

from infrastructure.database.manager import db_manager
from core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class DistributionRepository:
    """
    Repositorio para datos de distribución eléctrica.
    Acceso directo a tabla 'distribution_metrics' en SQLite.
    """
    
    def __init__(self):
        self.db_manager = db_manager
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """
        Crea tabla distribution_metrics si no existe (solo para SQLite).
        En PostgreSQL las tablas ya deben existir.
        """
        # Si usamos PostgreSQL, asumir que las tablas ya existen
        if self.db_manager.use_postgres:
            logger.info("✅ Usando PostgreSQL - tablas preexistentes")
            return
            
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS distribution_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_code TEXT NOT NULL,
            fecha DATE NOT NULL,
            valor REAL,
            unidad TEXT,
            agente TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(metric_code, fecha, agente)
        );
        
        CREATE INDEX IF NOT EXISTS idx_distribution_date 
        ON distribution_metrics(metric_code, fecha);
        
        CREATE INDEX IF NOT EXISTS idx_distribution_agent 
        ON distribution_metrics(agente);
        """
        
        try:
            with self.db_manager.get_connection() as conn:
                conn.executescript(create_table_sql)
                conn.commit()
                logger.info("✅ Tabla distribution_metrics verificada")
        except Exception as e:
            logger.error(f"❌ Error creando tabla: {str(e)}")
    
    def fetch_agent_statistics(self) -> pd.DataFrame:
        """
        Obtiene estadísticas de datos por agente para el tablero.
        Queries 'metrics' table (Unified).
        """
        query = """
        SELECT 
            recurso as code,
            COUNT(*) as total_registros,
            COUNT(DISTINCT fecha) as dias_unicos,
            COUNT(DISTINCT metrica) as metricas_distintas,
            MIN(fecha) as fecha_min,
            MAX(fecha) as fecha_max
        FROM metrics
        WHERE metrica IN ('DemaCome', 'DemaReal', 'DemaRealReg', 'DemaRealNoReg')
          AND entidad = 'Agente'
          AND recurso IS NOT NULL
        GROUP BY recurso
        ORDER BY total_registros DESC, dias_unicos DESC
        """
        
        try:
            with self.db_manager.get_connection() as conn:
                df = pd.read_sql_query(query, conn)
                logger.info(f"📊 Estadísticas de agentes: {len(df)} encontrados")
                return df
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas de agentes: {str(e)}")
            return pd.DataFrame()

    def fetch_distribution_metrics(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente: Optional[str] = None,
        entities: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Consulta métricas de distribución desde SQLite (Tabla Unified metrics).
        
        Args:
            metric_code: Código de la métrica
            start_date: Fecha inicio
            end_date: Fecha fin
            agente: Filtrar por recurso específico (opcional)
            entities: Lista de entidades a consultar (default: ['Agente'])
        
        Returns:
            DataFrame con datos o vacío si no hay registros
        """
        if entities is None:
            entities = ['Agente']
            
        entities_placeholder = ','.join(['?'] * len(entities))

        query = f"""
        SELECT 
            fecha,
            valor_gwh as valor,
            unidad,
            recurso as agente
        FROM metrics
        WHERE metrica = ?
          AND entidad IN ({entities_placeholder})
          AND fecha BETWEEN ? AND ?
        """
        
        params = [metric_code] + entities + [start_date, end_date]
        
        if agente:
            query += " AND recurso = ?"
            params.append(agente)
        
        query += " ORDER BY fecha ASC"
        
        try:
            with self.db_manager.get_connection() as conn:
                df = pd.read_sql_query(query, conn, params=params)
                
                if not df.empty:
                    df['fecha'] = pd.to_datetime(df['fecha']).dt.date
                
                logger.info(f"📊 Query retornó {len(df)} registros para {metric_code}")
                return df
        
        except Exception as e:
            logger.error(f"❌ Error ejecutando query: {str(e)}")
            return pd.DataFrame(columns=['fecha', 'valor', 'unidad', 'agente'])
    
    def save_metrics(self, df: pd.DataFrame, metric_code: str) -> int:
        """
        Inserta o actualiza métricas en batch.
        
        Args:
            df: DataFrame con columnas [fecha, valor, unidad, agente]
            metric_code: Código de la métrica
        
        Returns:
            Número de registros insertados
        """
        if df.empty:
            return 0
        
        insert_sql = """
        INSERT OR REPLACE INTO distribution_metrics 
        (metric_code, fecha, valor, unidad, agente, extra_data)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        
        try:
            records = [
                (metric_code, row['fecha'], row['valor'], row['unidad'], row['agente'], row.get('extra_data'))
                for _, row in df.iterrows()
            ]
            
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(insert_sql, records)
                conn.commit()
                
                rows_affected = cursor.rowcount
                logger.info(f"✅ Guardados {rows_affected} registros de {metric_code}")
                return rows_affected
        
        except sqlite3.Error as e:
            logger.error(f"❌ Error guardando datos: {str(e)}")
            # raise DatabaseError(f"Error persistiendo datos: {str(e)}")
            return 0
    
    def fetch_available_agents(self) -> List[Dict[str, str]]:
        """
        Retorna agentes distribuidores únicos en la base de datos.
        
        Returns:
            Lista [{'codigo': 'CODENSA', 'nombre': 'Codensa S.A.'}]
        """
        query = """
        SELECT DISTINCT agente as codigo
        FROM distribution_metrics
        WHERE agente IS NOT NULL
        ORDER BY agente
        """
        
        try:
            with self.db_manager.get_connection() as conn:
                df = pd.read_sql_query(query, conn)
                
                # Opcional: Mapear códigos a nombres completos (crear tabla lookup)
                agents = [{'codigo': row['codigo'], 'nombre': row['codigo']} 
                         for _, row in df.iterrows()]
                
                return agents
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo agentes: {str(e)}")
            return []
    
    def delete_old_data(self, days_to_keep: int = 365) -> int:
        """
        Limpia datos antiguos (opcional, para mantenimiento).
        
        Args:
            days_to_keep: Mantener últimos N días
        
        Returns:
            Registros eliminados
        """
        delete_sql = """
        DELETE FROM distribution_metrics
        WHERE fecha < date('now', '-' || ? || ' days')
        """
        
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(delete_sql, (days_to_keep,))
                conn.commit()
                
                deleted = cursor.rowcount
                logger.info(f"🗑️ Eliminados {deleted} registros antiguos")
                return deleted
        
        except sqlite3.Error as e:
            logger.error(f"❌ Error limpiando datos: {str(e)}")
            return 0
