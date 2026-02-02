#!/usr/bin/env python3
"""
Script de limpieza de datos corruptos en BD
Basado en análisis del dashboard oficial de XM Sinergox
"""

from infrastructure.database.manager import db_manager
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Rangos válidos basados en XM (del prompt)
VALID_RANGES = {
    'AporEner': (0, 500),          # GWh diario
    'RestAliv': (0, 1000),         # Millones COP
    'RestSinAliv': (0, 1000),
    'PrecBolsNaci': (0, 2000),     # TX1
    'DemaReal': (0, 500),          # GWh
    'Gene': (0, 500),              # GWh por recurso
    'VolUti': (0, 300),            # % puede superar 100%
    'EmisionesCO2': (0, 100000),   # Ton CO2e
}

def clean_invalid_ranges():
    """Elimina valores fuera de rangos válidos"""
    logger.info("🧹 Iniciando limpieza de datos corruptos...")
    
    total_deleted = 0
    
    for metric, (min_val, max_val) in VALID_RANGES.items():
        # Buscar métricas que coincidan con el patrón
        query_count = f"""
        SELECT COUNT(*) as count 
        FROM metrics 
        WHERE metrica LIKE '{metric}%' 
        AND (valor_gwh < {min_val} OR valor_gwh > {max_val})
        """
        
        result = db_manager.query_df(query_count)
        count = result['count'].iloc[0] if not result.empty else 0
        
        if count > 0:
            logger.info(f"   ⚠️ {metric}: {count} registros fuera de rango [{min_val}, {max_val}]")
            
            # Eliminar registros inválidos
            delete_query = f"""
            DELETE FROM metrics 
            WHERE metrica LIKE '{metric}%' 
            AND (valor_gwh < {min_val} OR valor_gwh > {max_val})
            """
            
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(delete_query)
                conn.commit()
                deleted = cursor.rowcount
                total_deleted += deleted
                logger.info(f"   ✅ Eliminados {deleted} registros de {metric}")
    
    logger.info(f"\n🎯 Total eliminados: {total_deleted} registros corruptos")
    return total_deleted

def clean_old_restrictions():
    """Elimina restricciones con unidad incorrecta (datos viejos en GWh)"""
    logger.info("\n🔧 Limpiando restricciones antiguas (formato incorrecto)...")
    
    # Mantener SOLO las que tienen unit='COP'
    query = """
    DELETE FROM metrics 
    WHERE metrica IN ('RestAliv', 'RestSinAliv')
    AND (unidad IS NULL OR unidad != 'COP')
    """
    
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        conn.commit()
        deleted = cursor.rowcount
        logger.info(f"   ✅ Eliminados {deleted} registros viejos de restricciones")
    
    return deleted

def vacuum_database():
    """Optimiza la BD después de eliminaciones masivas"""
    logger.info("\n💾 Optimizando base de datos...")
    
    with db_manager.get_connection() as conn:
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
    
    logger.info("   ✅ BD optimizada")

def main():
    logger.info("=" * 70)
    logger.info("LIMPIEZA DE DATOS CORRUPTOS - BASADO EN ESTÁNDARES XM")
    logger.info("=" * 70)
    
    # 1. Limpiar rangos inválidos
    deleted_ranges = clean_invalid_ranges()
    
    # 2. Limpiar restricciones viejas
    deleted_restrictions = clean_old_restrictions()
    
    # 3. Optimizar BD
    vacuum_database()
    
    # 4. Estadísticas finales
    logger.info("\n📊 ESTADÍSTICAS FINALES:")
    query = """
    SELECT metrica, COUNT(*) as registros, 
           ROUND(MIN(valor_gwh), 2) as min, 
           ROUND(MAX(valor_gwh), 2) as max,
           ROUND(AVG(valor_gwh), 2) as promedio
    FROM metrics
    WHERE metrica IN ('AporEner', 'RestAliv', 'RestSinAliv', 'DemaReal', 'PrecBolsNaci')
    GROUP BY metrica
    """
    df = db_manager.query_df(query)
    print(df.to_string(index=False))
    
    logger.info(f"\n✅ LIMPIEZA COMPLETADA: {deleted_ranges + deleted_restrictions} registros eliminados")

if __name__ == "__main__":
    main()
