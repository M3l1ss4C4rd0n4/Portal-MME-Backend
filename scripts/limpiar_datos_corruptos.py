#!/usr/bin/env python3
"""
Script de limpieza de datos corruptos en BD
Basado en análisis del dashboard oficial de XM Sinergox

⚠️ SCRIPT DESTRUCTIVO — Ejecuta DELETE FROM metrics
   Usar SIEMPRE con --dry-run primero para ver qué se borraría.
   Uso: python limpiar_datos_corruptos.py --dry-run
         python limpiar_datos_corruptos.py --confirmar
"""

from infrastructure.database.manager import db_manager
import logging
import argparse
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# MODO DE EJECUCIÓN (se configura con --dry-run o --confirmar)
# ──────────────────────────────────────────────────────────────────────
DRY_RUN = True  # por defecto NO borra nada

# Rangos válidos basados en XM (del prompt)
# ⚠️ PELIGRO: Estos rangos activan DELETE FROM metrics
# Solo valores claramente imposibles para evitar borrado accidental
VALID_RANGES = {
    'AporEner': (0, 5000),          # GWh diario (Sistema puede sumar alto)
    'RestAliv': (0, 100000),        # Millones COP
    'RestSinAliv': (0, 100000),
    'PrecBolsNaci': (0, 5000),      # $/kWh (puede haber picos extremos)
    'DemaReal': (0, 1000),          # GWh (Sistema puede ser alto)
    'Gene': (0, 1000),              # GWh (Sistema ~200 GWh/dia pero sumado puede ser más)
    'EmisionesCO2': (0, 1000000),   # Ton CO2e
}

def clean_invalid_ranges():
    """Elimina valores fuera de rangos válidos"""
    mode_label = "🔍 DRY-RUN (sin borrar)" if DRY_RUN else "🗑️  EJECUCIÓN REAL"
    logger.info(f"🧹 Iniciando limpieza de datos corruptos... [{mode_label}]")
    
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
            
            if DRY_RUN:
                logger.info(f"   🔍 DRY-RUN: Se borrarían {count} registros de {metric}")
                total_deleted += count
            else:
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
    
    logger.info(f"\n🎯 Total {'a eliminar' if DRY_RUN else 'eliminados'}: {total_deleted} registros corruptos")
    return total_deleted

def clean_old_restrictions():
    """Elimina restricciones con unidad incorrecta (datos viejos en GWh)
    
    NOTA: Las restricciones válidas tienen unidad='Millones COP' (no 'COP').
    Solo eliminar registros con unidad='GWh' que son claramente incorrectos.
    """
    logger.info("\n🔧 Limpiando restricciones antiguas (formato incorrecto)...")
    
    if DRY_RUN:
        # Solo contar
        count_query = """
        SELECT COUNT(*) as count FROM metrics 
        WHERE metrica IN ('RestAliv', 'RestSinAliv', 'RespComerAGC')
        AND unidad = 'GWh'
        """
        result = db_manager.query_df(count_query)
        count = result['count'].iloc[0] if not result.empty else 0
        logger.info(f"   🔍 DRY-RUN: Se borrarían {count} registros con unidad='GWh' de restricciones")
        return count
    
    # ✅ FIX: Solo borrar restricciones con unidad='GWh' (claramente erróneas)
    # Mantener las que tienen 'Millones COP', 'COP' o NULL
    query = """
    DELETE FROM metrics 
    WHERE metrica IN ('RestAliv', 'RestSinAliv', 'RespComerAGC')
    AND unidad = 'GWh'
    """
    
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        conn.commit()
        deleted = cursor.rowcount
        logger.info(f"   ✅ Eliminados {deleted} registros con unidad='GWh' de restricciones")
    
    return deleted

def vacuum_database():
    """Optimiza la BD después de eliminaciones masivas"""
    logger.info("\n💾 Optimizando base de datos...")
    
    with db_manager.get_connection() as conn:
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
    
    logger.info("   ✅ BD optimizada")

def main():
    global DRY_RUN
    
    parser = argparse.ArgumentParser(
        description="Limpieza de datos corruptos en la BD de métricas",
        epilog="⚠️  SIN argumentos = dry-run por seguridad"
    )
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Solo mostrar qué se borraría (por defecto)')
    parser.add_argument('--confirmar', action='store_true',
                        help='Ejecutar la limpieza REAL (borra datos)')
    args = parser.parse_args()
    
    if args.confirmar:
        DRY_RUN = False
        logger.warning("=" * 70)
        logger.warning("⚠️  MODO REAL: SE VAN A BORRAR DATOS DE LA BD")
        logger.warning("=" * 70)
        respuesta = input("¿Está seguro? Escriba 'SI BORRAR' para continuar: ")
        if respuesta != 'SI BORRAR':
            logger.info("❌ Cancelado por el usuario")
            sys.exit(0)
    else:
        DRY_RUN = True
        logger.info("=" * 70)
        logger.info("🔍 MODO DRY-RUN: No se borrará nada (use --confirmar para borrar)")
        logger.info("=" * 70)
    
    logger.info("LIMPIEZA DE DATOS CORRUPTOS - BASADO EN ESTÁNDARES XM")
    logger.info("=" * 70)
    
    # 1. Limpiar rangos inválidos
    deleted_ranges = clean_invalid_ranges()
    
    # 2. Limpiar restricciones viejas
    deleted_restrictions = clean_old_restrictions()
    
    # 3. Optimizar BD (solo si se borraron datos realmente)
    if not DRY_RUN:
        vacuum_database()
    
    # 4. Estadísticas finales
    logger.info("\n📊 ESTADÍSTICAS FINALES:")
    query = """
    SELECT metrica, COUNT(*) as registros, 
           ROUND(MIN(valor_gwh)::numeric, 2) as min, 
           ROUND(MAX(valor_gwh)::numeric, 2) as max,
           ROUND(AVG(valor_gwh)::numeric, 2) as promedio
    FROM metrics
    WHERE metrica IN ('AporEner', 'RestAliv', 'RestSinAliv', 'DemaReal', 'PrecBolsNaci')
    GROUP BY metrica
    """
    df = db_manager.query_df(query)
    print(df.to_string(index=False))
    
    action = "a eliminar" if DRY_RUN else "eliminados"
    logger.info(f"\n✅ LIMPIEZA {'SIMULADA' if DRY_RUN else 'COMPLETADA'}: {deleted_ranges + deleted_restrictions} registros {action}")

if __name__ == "__main__":
    main()
