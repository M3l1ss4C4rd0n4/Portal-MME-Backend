#!/usr/bin/env python3
"""
BACKFILL: Descarga datos históricos (2020-2026) para métricas con entity='Sistema'
que solo tienen datos recientes (últimos 7-17 días).

Esto resuelve el problema de que el ETL cron solo trae --dias 7.

Uso:
    python3 scripts/backfill_sistema_metricas.py [--dias 2200] [--metrica Gene]
"""

import sys
import os
import time
import logging
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydataxm.pydataxm import ReadDB
from infrastructure.database.manager import db_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Métricas que necesitan backfill a nivel Sistema
# Estas son todas las que el dashboard usa con entity='Sistema'
# pero que el ETL con --dias 7 no les ha creado historia
METRICAS_BACKFILL = [
    # Métrica, Entity, notas
    ('AporEner', 'Sistema'),
    ('VoluUtilDiarEner', 'Sistema'),
    ('PorcApor', 'Sistema'),
    ('DemaCome', 'Sistema'),
    ('DemaReal', 'Sistema'),
    ('DemaRealReg', 'Sistema'),
    ('DemaRealNoReg', 'Sistema'),
    ('PerdidasEner', 'Sistema'),
    ('PerdidasEnerReg', 'Sistema'),
    ('PerdidasEnerNoReg', 'Sistema'),
    ('PrecEsca', 'Sistema'),
    ('PrecEscaSup', 'Sistema'),
    ('PrecEscaInf', 'Sistema'),
    ('RestAliv', 'Sistema'),
]


def check_current_depth(metrica, entidad):
    """Verificar profundidad actual de datos"""
    try:
        query = """
        SELECT COUNT(*) as n, MIN(fecha)::date as min_f, MAX(fecha)::date as max_f
        FROM metrics
        WHERE metrica = %s AND entidad = %s
        """
        df = db_manager.query_df(query, (metrica, entidad))
        if not df.empty and df['n'].iloc[0] > 0:
            return df['n'].iloc[0], str(df['min_f'].iloc[0]), str(df['max_f'].iloc[0])
        return 0, None, None
    except Exception as e:
        logger.error(f"Error checking depth: {e}")
        return 0, None, None


def descargar_e_insertar(api, metrica, entidad, dias):
    """Descarga datos de XM e inserta en BD"""
    from etl.etl_todas_metricas_xm import detectar_conversion, convertir_unidades, asegurar_columna_valor
    from etl.etl_rules import get_expected_unit
    import pandas as pd
    
    fecha_fin = datetime.now() - timedelta(days=1)
    fecha_inicio = fecha_fin - timedelta(days=dias)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📊 {metrica} | {entidad}")
    logger.info(f"📅 {fecha_inicio.date()} → {fecha_fin.date()} ({dias} días)")
    
    # Check current depth
    n, min_f, max_f = check_current_depth(metrica, entidad)
    logger.info(f"📈 Datos actuales: {n} registros ({min_f} → {max_f})")
    
    try:
        df = api.request_data(
            metrica, entidad,
            start_date=fecha_inicio.strftime('%Y-%m-%d'),
            end_date=fecha_fin.strftime('%Y-%m-%d')
        )
        
        if df is None or df.empty:
            logger.warning(f"  ⚠️ Sin datos para {metrica}/{entidad}")
            return 0
        
        logger.info(f"  ✅ Descargados {len(df)} registros de XM")
        
        # Conversión
        conversion = detectar_conversion(metrica, entidad)
        df = convertir_unidades(df, metrica, conversion)
        df = asegurar_columna_valor(df, conversion)
        
        if df.empty or 'Value' not in df.columns:
            logger.warning(f"  ⚠️ Sin datos después de conversión")
            return 0
        
        # Determinar unidad
        unidad = get_expected_unit(metrica)
        if unidad is None:
            if conversion in ['restricciones_a_MCOP', 'COP_a_MCOP']:
                unidad = 'Millones COP'
            elif conversion in ['Wh_a_GWh', 'horas_a_GWh', 'kWh_a_GWh']:
                unidad = 'GWh'
            elif conversion == 'horas_a_MW':
                unidad = 'MW'
            elif 'Prec' in metrica:
                unidad = '$/kWh'
        
        # Detectar columnas
        fecha_col = next((c for c in ['Date', 'date', 'Fecha'] if c in df.columns), None)
        valor_col = 'Value'
        id_cols = next((c for c in ['Values_code', 'Name', 'Code', 'Id'] if c in df.columns), None)
        
        if not fecha_col:
            logger.warning(f"  ⚠️ No se encontró columna de fecha")
            return 0
        
        # Preparar registros
        registros = []
        for _, row in df.iterrows():
            recurso = str(row[id_cols]) if id_cols and pd.notna(row[id_cols]) else None
            fecha = pd.to_datetime(row[fecha_col]).strftime('%Y-%m-%d')
            valor = float(row[valor_col]) if pd.notna(row[valor_col]) else None
            
            if valor is not None:
                registros.append((fecha, metrica, entidad, recurso, valor, unidad))
        
        if not registros:
            logger.warning(f"  ⚠️ No hay registros válidos")
            return 0
        
        # Insertar con ON CONFLICT
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO metrics 
                (fecha, metrica, entidad, recurso, valor_gwh, unidad, fecha_actualizacion)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (fecha, metrica, entidad, recurso) 
                DO UPDATE SET 
                    valor_gwh = EXCLUDED.valor_gwh,
                    unidad = EXCLUDED.unidad,
                    fecha_actualizacion = CURRENT_TIMESTAMP
            """, registros)
            conn.commit()
        
        logger.info(f"  💾 Insertados/actualizados {len(registros)} registros")
        
        # Verificar resultado
        n_new, min_f_new, max_f_new = check_current_depth(metrica, entidad)
        logger.info(f"  📈 Después: {n_new} registros ({min_f_new} → {max_f_new})")
        
        return len(registros)
        
    except Exception as e:
        logger.error(f"  ❌ Error: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description='Backfill métricas Sistema')
    parser.add_argument('--dias', type=int, default=2200, help='Días de historia (default: 2200)')
    parser.add_argument('--metrica', type=str, help='Solo una métrica específica')
    args = parser.parse_args()
    
    logger.info("╔══════════════════════════════════════════════════════════════╗")
    logger.info("║   BACKFILL HISTÓRICO: MÉTRICAS SISTEMA (DASHBOARD)          ║")
    logger.info("╚══════════════════════════════════════════════════════════════╝")
    logger.info(f"📅 Días de historia: {args.dias}")
    
    api = ReadDB()
    
    metricas = METRICAS_BACKFILL
    if args.metrica:
        metricas = [(args.metrica, 'Sistema')]
    
    total_registros = 0
    resultados = []
    
    for metrica, entidad in metricas:
        registros = descargar_e_insertar(api, metrica, entidad, args.dias)
        total_registros += registros
        resultados.append((metrica, entidad, registros))
        time.sleep(1)  # Rate limit
    
    logger.info("\n" + "="*70)
    logger.info("RESUMEN BACKFILL")
    logger.info("="*70)
    for metrica, entidad, n in resultados:
        status = "✅" if n > 0 else "⚠️"
        logger.info(f"  {status} {metrica}/{entidad}: {n} registros")
    logger.info(f"\n💾 Total registros: {total_registros:,}")
    logger.info(f"✅ Completado: {datetime.now()}")


if __name__ == "__main__":
    main()
