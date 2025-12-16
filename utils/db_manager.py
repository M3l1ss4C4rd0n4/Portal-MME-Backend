"""
Database Manager para Portal Energético MME
Base de datos: SQLite
Propósito: Gestión de conexiones y queries a base de datos de métricas energéticas
"""

import sqlite3
import pandas as pd
import logging
from pathlib import Path
from typing import Optional, List, Tuple
from contextlib import contextmanager
from datetime import datetime

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ruta a la base de datos
DB_PATH = Path(__file__).parent.parent / "portal_energetico.db"
SCHEMA_PATH = Path(__file__).parent.parent / "sql" / "schema.sql"


@contextmanager
def get_connection():
    """
    Context manager para conexión a SQLite
    Garantiza cierre automático de conexión
    
    Uso:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM metrics")
    """
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Error de conexión SQLite: {e}")
        raise
    finally:
        if conn:
            conn.close()


def init_database():
    """
    Inicializa la base de datos ejecutando schema.sql
    Solo debe ejecutarse la primera vez o para recrear la BD
    """
    try:
        # Leer schema.sql
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        # Ejecutar schema
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(schema_sql)
            conn.commit()
            logger.info(f"✅ Base de datos inicializada: {DB_PATH}")
            
        return True
    except Exception as e:
        logger.error(f"❌ Error inicializando base de datos: {e}")
        return False


def get_metric_data(
    metrica: str,
    entidad: str,
    fecha_inicio: str,
    fecha_fin: Optional[str] = None,
    recurso: Optional[str] = None,
    recurso_filter: Optional[list] = None
) -> pd.DataFrame:
    """
    Obtiene datos de métrica desde SQLite
    
    Args:
        metrica: Nombre de la métrica ('Gene', 'DemaCome', etc.)
        entidad: Entidad ('Sistema', 'Recurso', 'Embalse', etc.)
        fecha_inicio: Fecha inicio en formato 'YYYY-MM-DD'
        fecha_fin: Fecha fin (opcional, si no se proporciona usa fecha_inicio)
        recurso: Filtro por recurso único (opcional, ej: 'CARBON', 'HIDRAULICA')
        recurso_filter: Lista de recursos para filtrar (opcional, ej: ['2QBW', '2QRL', 'RCIO'])
    
    Returns:
        DataFrame con columnas: fecha, metrica, entidad, recurso, valor_gwh, unidad
    """
    try:
        if fecha_fin is None:
            fecha_fin = fecha_inicio
        
        # Query base
        query = """
            SELECT fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion
            FROM metrics
            WHERE metrica = ?
              AND entidad = ?
              AND fecha BETWEEN ? AND ?
        """
        params = [metrica, entidad, fecha_inicio, fecha_fin]
        
        # Agregar filtro por recurso único
        if recurso:
            query += " AND recurso = ?"
            params.append(recurso)
        
        # Agregar filtro por lista de recursos (usando IN)
        elif recurso_filter and len(recurso_filter) > 0:
            placeholders = ','.join(['?'] * len(recurso_filter))
            query += f" AND recurso IN ({placeholders})"
            params.extend(recurso_filter)
        
        query += " ORDER BY fecha, recurso"
        
        # Ejecutar query
        import time
        t_start = time.time()
        logger.info(f"🔄 Iniciando query SQLite: {metrica}/{entidad} ({len(params)-4 if recurso_filter else 0} recursos)")
        
        with get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        
        elapsed = time.time() - t_start
        logger.info(f"✅ Query completada en {elapsed:.2f}s: {len(df)} registros ({fecha_inicio} a {fecha_fin})")
        return df
        
    except Exception as e:
        logger.error(f"❌ Error consultando {metrica}/{entidad}: {e}")
        return pd.DataFrame()


def upsert_metric(
    fecha: str,
    metrica: str,
    entidad: str,
    valor_gwh: float,
    recurso: Optional[str] = None,
    unidad: str = 'GWh'
) -> bool:
    """
    Inserta o actualiza una métrica en SQLite (UPSERT)
    Si ya existe (fecha, metrica, entidad, recurso), actualiza el valor
    Si no existe, inserta nuevo registro
    
    Args:
        fecha: Fecha en formato 'YYYY-MM-DD'
        metrica: Nombre de la métrica
        entidad: Entidad
        valor_gwh: Valor en GWh
        recurso: Recurso (opcional)
        unidad: Unidad de medida (default: 'GWh')
    
    Returns:
        True si operación exitosa, False si error
    """
    try:
        query = """
            INSERT INTO metrics (fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(fecha, metrica, entidad, recurso)
            DO UPDATE SET
                valor_gwh = excluded.valor_gwh,
                unidad = excluded.unidad,
                fecha_actualizacion = CURRENT_TIMESTAMP
        """
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (fecha, metrica, entidad, recurso, valor_gwh, unidad))
            conn.commit()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error insertando {metrica}/{entidad} ({fecha}): {e}")
        return False


def upsert_metrics_bulk(metrics: List[Tuple]) -> int:
    """
    Inserta múltiples métricas en una sola transacción (más eficiente)
    
    Args:
        metrics: Lista de tuplas (fecha, metrica, entidad, recurso, valor_gwh, unidad)
    
    Returns:
        Número de registros insertados/actualizados
    """
    try:
        query = """
            INSERT INTO metrics (fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(fecha, metrica, entidad, recurso)
            DO UPDATE SET
                valor_gwh = excluded.valor_gwh,
                unidad = excluded.unidad,
                fecha_actualizacion = CURRENT_TIMESTAMP
        """
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, metrics)
            conn.commit()
            rows_affected = cursor.rowcount
        
        logger.info(f"✅ Bulk insert: {rows_affected} registros procesados")
        return rows_affected
        
    except Exception as e:
        logger.error(f"❌ Error en bulk insert: {e}")
        return 0


def get_latest_date(metrica: str, entidad: str, recurso: Optional[str] = None) -> Optional[str]:
    """
    Obtiene la fecha más reciente disponible para una métrica
    
    Args:
        metrica: Nombre de la métrica
        entidad: Entidad
        recurso: Recurso (opcional)
    
    Returns:
        Fecha más reciente en formato 'YYYY-MM-DD' o None si no hay datos
    """
    try:
        query = """
            SELECT MAX(fecha) as max_fecha
            FROM metrics
            WHERE metrica = ? AND entidad = ?
        """
        params = [metrica, entidad]
        
        if recurso:
            query += " AND recurso = ?"
            params.append(recurso)
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
        
        return result['max_fecha'] if result['max_fecha'] else None
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo última fecha para {metrica}/{entidad}: {e}")
        return None


def get_database_stats() -> dict:
    """
    Obtiene estadísticas de la base de datos
    
    Returns:
        Diccionario con estadísticas: total_registros, metricas, fechas, etc.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Total de registros
            cursor.execute("SELECT COUNT(*) as total FROM metrics")
            total = cursor.fetchone()['total']
            
            # Número de métricas únicas
            cursor.execute("SELECT COUNT(DISTINCT metrica) as count FROM metrics")
            metricas_count = cursor.fetchone()['count']
            
            # Rango de fechas
            cursor.execute("SELECT MIN(fecha) as min_fecha, MAX(fecha) as max_fecha FROM metrics")
            fechas = cursor.fetchone()
            
            # Tamaño del archivo de base de datos
            db_size_mb = DB_PATH.stat().st_size / (1024 * 1024) if DB_PATH.exists() else 0
            
        stats = {
            'total_registros': total,
            'metricas_unicas': metricas_count,
            'fecha_minima': fechas['min_fecha'],
            'fecha_maxima': fechas['max_fecha'],
            'tamano_db_mb': round(db_size_mb, 2),
            'ruta_db': str(DB_PATH)
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo estadísticas: {e}")
        return {}


def test_connection() -> bool:
    """
    Prueba la conexión a la base de datos
    
    Returns:
        True si conexión exitosa, False si error
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        
        logger.info("✅ Conexión a SQLite exitosa")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error de conexión: {e}")
        return False


# ============================================================================
# FUNCIONES PARA CATÁLOGOS (ListadoRecursos, ListadoEmbalses, etc.)
# ============================================================================

def upsert_catalogo_bulk(catalogo: str, registros: List[dict]) -> int:
    """
    Inserta o actualiza múltiples registros de catálogo (ListadoRecursos, etc.)
    
    Args:
        catalogo: Nombre del catálogo ('ListadoRecursos', 'ListadoEmbalses', etc.)
        registros: Lista de diccionarios con estructura:
            {
                'codigo': str (requerido),
                'nombre': str (opcional),
                'tipo': str (opcional),
                'region': str (opcional),
                'capacidad': float (opcional),
                'metadata': str (opcional, JSON)
            }
    
    Returns:
        Número de registros insertados/actualizados
    
    Ejemplo:
        registros = [
            {'codigo': '2QBW', 'nombre': 'GUAVIO', 'tipo': 'HIDRAULICA', 'capacidad': 1213.0},
            {'codigo': '2QRL', 'nombre': 'RIO NEGRO', 'tipo': 'HIDRAULICA', 'capacidad': 39.6}
        ]
        upsert_catalogo_bulk('ListadoRecursos', registros)
    """
    if not registros:
        return 0
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                INSERT INTO catalogos (catalogo, codigo, nombre, tipo, region, capacidad, metadata, fecha_actualizacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(catalogo, codigo) DO UPDATE SET
                    nombre = excluded.nombre,
                    tipo = excluded.tipo,
                    region = excluded.region,
                    capacidad = excluded.capacidad,
                    metadata = excluded.metadata,
                    fecha_actualizacion = CURRENT_TIMESTAMP
            """
            
            datos = [
                (
                    catalogo,
                    reg.get('codigo'),
                    reg.get('nombre'),
                    reg.get('tipo'),
                    reg.get('region'),
                    reg.get('capacidad'),
                    reg.get('metadata')
                )
                for reg in registros
            ]
            
            cursor.executemany(query, datos)
            conn.commit()
            
            registros_afectados = cursor.rowcount
            logger.info(f"✅ Catálogo {catalogo}: {registros_afectados} registros guardados")
            return registros_afectados
            
    except sqlite3.Error as e:
        logger.error(f"❌ Error guardando catálogo {catalogo}: {e}")
        return 0


def get_catalogo(catalogo: str, codigo: str = None) -> pd.DataFrame:
    """
    Obtiene registros de un catálogo
    
    Args:
        catalogo: Nombre del catálogo ('ListadoRecursos', 'ListadoEmbalses', etc.)
        codigo: Código específico a buscar (opcional, si None devuelve todos)
    
    Returns:
        DataFrame con columnas: codigo, nombre, tipo, region, capacidad, metadata
    
    Ejemplo:
        # Obtener todos los recursos
        df = get_catalogo('ListadoRecursos')
        
        # Obtener recurso específico
        df = get_catalogo('ListadoRecursos', '2QBW')
    """
    try:
        with get_connection() as conn:
            if codigo:
                query = """
                    SELECT codigo, nombre, tipo, region, capacidad, metadata, fecha_actualizacion
                    FROM catalogos
                    WHERE catalogo = ? AND codigo = ?
                """
                df = pd.read_sql_query(query, conn, params=(catalogo, codigo))
            else:
                query = """
                    SELECT codigo, nombre, tipo, region, capacidad, metadata, fecha_actualizacion
                    FROM catalogos
                    WHERE catalogo = ?
                    ORDER BY nombre
                """
                df = pd.read_sql_query(query, conn, params=(catalogo,))
            
            logger.info(f"✅ Catálogo {catalogo}: {len(df)} registros obtenidos")
            return df
            
    except sqlite3.Error as e:
        logger.error(f"❌ Error consultando catálogo {catalogo}: {e}")
        return pd.DataFrame()


def get_mapeo_codigos(catalogo: str) -> dict:
    """
    Obtiene diccionario de mapeo código → nombre desde un catálogo
    
    Args:
        catalogo: Nombre del catálogo ('ListadoRecursos', 'ListadoEmbalses', etc.)
    
    Returns:
        Diccionario {codigo: nombre}
    
    Ejemplo:
        mapeo = get_mapeo_codigos('ListadoRecursos')
        # {'2QBW': 'GUAVIO', '2QRL': 'RIO NEGRO', ...}
        
        nombre = mapeo.get('2QBW', '2QBW')  # Devuelve 'GUAVIO'
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT codigo, nombre
                FROM catalogos
                WHERE catalogo = ? AND nombre IS NOT NULL
            """, (catalogo,))
            
            mapeo = {row[0]: row[1] for row in cursor.fetchall()}
            logger.info(f"✅ Mapeo {catalogo}: {len(mapeo)} códigos")
            return mapeo
            
    except sqlite3.Error as e:
        logger.error(f"❌ Error obteniendo mapeo {catalogo}: {e}")
        return {}


def get_codigos_con_datos(metrica: str, entidad: str, fecha_inicio: str, fecha_fin: str) -> List[str]:
    """
    Obtiene lista de códigos de recurso que tienen datos en un rango de fechas.
    Útil para optimizar consultas evitando buscar códigos sin datos.
    
    Args:
        metrica: Nombre de la métrica (ej: 'Gene')
        entidad: Tipo de entidad (ej: 'Recurso')
        fecha_inicio: Fecha inicio en formato 'YYYY-MM-DD'
        fecha_fin: Fecha fin en formato 'YYYY-MM-DD'
    
    Returns:
        Lista de códigos de recurso que tienen al menos un dato en el rango
    
    Ejemplo:
        codigos = get_codigos_con_datos('Gene', 'Recurso', '2024-01-01', '2024-12-31')
        # ['2QBW', '2QEK', '2QRL', ...]
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT recurso
                FROM metrics
                WHERE metrica = ?
                    AND entidad = ?
                    AND fecha BETWEEN ? AND ?
                    AND recurso IS NOT NULL
                    AND recurso != '_SISTEMA_'
            """, (metrica, entidad, fecha_inicio, fecha_fin))
            
            codigos = [row[0] for row in cursor.fetchall()]
            logger.info(f"✅ {len(codigos)} códigos con datos en {fecha_inicio} → {fecha_fin}")
            return codigos
            
    except sqlite3.Error as e:
        logger.error(f"❌ Error obteniendo códigos con datos: {e}")
        return []


# ============================================================================
# FUNCIONES PARA DATOS HORARIOS
# ============================================================================

def upsert_hourly_metrics_bulk(metrics_data: List[Tuple]) -> int:
    """
    Insertar/actualizar múltiples métricas horarias de forma eficiente (bulk)
    
    Args:
        metrics_data: Lista de tuplas (fecha, metrica, entidad, recurso, hora, valor_mwh)
    
    Returns:
        Número de registros procesados
    """
    if not metrics_data:
        return 0
    
    query = """
        INSERT INTO metrics_hourly (fecha, metrica, entidad, recurso, hora, valor_mwh, unidad)
        VALUES (?, ?, ?, ?, ?, ?, 'MWh')
        ON CONFLICT(fecha, metrica, entidad, recurso, hora) 
        DO UPDATE SET 
            valor_mwh = excluded.valor_mwh,
            fecha_actualizacion = CURRENT_TIMESTAMP
    """
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, metrics_data)
            conn.commit()
            
            registros_afectados = cursor.rowcount
            logger.info(f"✅ Bulk insert horario: {registros_afectados} registros procesados")
            return registros_afectados
            
    except sqlite3.Error as e:
        logger.error(f"❌ Error en bulk insert horario: {e}")
        return 0


def get_hourly_data(metrica: str, entidad: str, fecha: str, recurso: str = None) -> pd.DataFrame:
    """
    Obtener datos horarios de una métrica para una fecha específica
    
    Args:
        metrica: Nombre de la métrica ('DemaCome', 'DemaReal', etc.)
        entidad: Tipo de entidad ('Sistema', 'Agente', 'Recurso')
        fecha: Fecha en formato 'YYYY-MM-DD'
        recurso: Código de recurso/agente (opcional, None para Sistema)
    
    Returns:
        DataFrame con columnas: hora, valor_mwh
    """
    query = """
        SELECT hora, valor_mwh, unidad
        FROM metrics_hourly
        WHERE metrica = ?
        AND entidad = ?
        AND fecha = ?
    """
    
    params = [metrica, entidad, fecha]
    
    if recurso is not None:
        query += " AND recurso = ?"
        params.append(recurso)
    else:
        query += " AND recurso IS NULL"
    
    query += " ORDER BY hora"
    
    try:
        with get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
            
            if not df.empty:
                logger.info(f"✅ Datos horarios: {len(df)} horas para {metrica}/{entidad} en {fecha}")
            else:
                logger.warning(f"⚠️ Sin datos horarios para {metrica}/{entidad} en {fecha}")
            
            return df
            
    except sqlite3.Error as e:
        logger.error(f"❌ Error obteniendo datos horarios: {e}")
        return pd.DataFrame()


def get_hourly_data_aggregated(metrica: str, entidad: str, fecha: str) -> pd.DataFrame:
    """
    Obtener datos horarios agregados (suma de todos los recursos/agentes) para una fecha
    
    Args:
        metrica: Nombre de la métrica
        entidad: Tipo de entidad
        fecha: Fecha en formato 'YYYY-MM-DD'
    
    Returns:
        DataFrame con columnas: hora, valor_mwh (suma de todos los recursos)
    """
    query = """
        SELECT hora, SUM(valor_mwh) as valor_mwh
        FROM metrics_hourly
        WHERE metrica = ?
        AND entidad = ?
        AND fecha = ?
        GROUP BY hora
        ORDER BY hora
    """
    
    try:
        with get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=[metrica, entidad, fecha])
            
            if not df.empty:
                logger.info(f"✅ Datos horarios agregados: {len(df)} horas para {metrica}/{entidad} en {fecha}")
            else:
                logger.warning(f"⚠️ Sin datos horarios agregados para {metrica}/{entidad} en {fecha}")
            
            return df
            
    except sqlite3.Error as e:
        logger.error(f"❌ Error obteniendo datos horarios agregados: {e}")
        return pd.DataFrame()


# ============================================================================
# INICIALIZACIÓN AUTOMÁTICA
# ============================================================================
# Si la base de datos no existe, inicializarla automáticamente
if not DB_PATH.exists():
    logger.info(f"⚠️ Base de datos no encontrada: {DB_PATH}")
    logger.info("🔧 Inicializando base de datos...")
    init_database()


# ============================================================================
# EJEMPLO DE USO
# ============================================================================
if __name__ == "__main__":
    # Probar conexión
    print("Probando conexión...")
    test_connection()
    
    # Mostrar estadísticas
    print("\nEstadísticas de la base de datos:")
    stats = get_database_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Ejemplo de inserción
    print("\nEjemplo de inserción...")
    upsert_metric(
        fecha='2025-11-19',
        metrica='Gene',
        entidad='Sistema',
        valor_gwh=250.5,
        recurso=None
    )
    
    # Ejemplo de consulta
    print("\nEjemplo de consulta...")
    df = get_metric_data(
        metrica='Gene',
        entidad='Sistema',
        fecha_inicio='2025-11-19',
        fecha_fin='2025-11-19'
    )
    print(df)
