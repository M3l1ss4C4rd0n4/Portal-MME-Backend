"""
Script para completar datos faltantes en tablas incompletas

Ejecuta ETL específico para llenar:
- commercial_metrics (precios comerciales)
- loss_metrics (pérdidas energéticas)
- restriction_metrics (restricciones)
"""

import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.database.manager import db_manager
from infrastructure.external.xm_service import XMService
from infrastructure.logging.logger import get_logger
import pandas as pd

logger = get_logger(__name__)


def completar_commercial_metrics():
    """Completa la tabla commercial_metrics con precios comerciales"""
    logger.info("="*70)
    logger.info("📊 Completando commercial_metrics...")
    logger.info("="*70)
    
    xm = XMService()
    
    # Métricas comerciales a descargar
    metricas_comerciales = [
        'PrecBolsNaci',  # Precio bolsa nacional
        'PrecEscaSupe',  # Precio escasez superior
        'PrecEscaActi',  # Precio escasez activación
        'PrecEscaInfe',  # Precio escasez inferior
    ]
    
    fecha_inicio = '2020-01-01'
    fecha_fin = datetime.now().strftime('%Y-%m-%d')
    
    total_insertados = 0
    
    for metrica in metricas_comerciales:
        try:
            logger.info(f"   📥 Descargando {metrica} desde {fecha_inicio} hasta {fecha_fin}...")
            
            df = xm.fetch_metric_data(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                metrica=metrica
            )
            
            if df.empty:
                logger.warning(f"   ⚠️  No hay datos para {metrica}")
                continue
            
            # Insertar en commercial_metrics
            df['metrica'] = metrica
            df['fecha_actualizacion'] = datetime.now()
            
            # Usar INSERT ON CONFLICT para evitar duplicados
            query = """
                INSERT INTO commercial_metrics (fecha, metrica, valor, unidad, fecha_actualizacion)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (fecha, metrica) DO UPDATE
                SET valor = EXCLUDED.valor,
                    unidad = EXCLUDED.unidad,
                    fecha_actualizacion = EXCLUDED.fecha_actualizacion
            """
            
            registros = 0
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for _, row in df.iterrows():
                        cur.execute(query, (
                            row.get('fecha'),
                            metrica,
                            row.get('valor', row.get('value', 0)),
                            row.get('unidad', '$/kWh'),
                            datetime.now()
                        ))
                        registros += 1
                conn.commit()
            
            logger.info(f"   ✅ {metrica}: {registros} registros insertados")
            total_insertados += registros
            
        except Exception as e:
            logger.error(f"   ❌ Error con {metrica}: {e}")
            continue
    
    logger.info(f"\n✅ commercial_metrics completado: {total_insertados} registros insertados\n")
    return total_insertados


def completar_loss_metrics():
    """Completa la tabla loss_metrics con pérdidas energéticas"""
    logger.info("="*70)
    logger.info("📊 Completando loss_metrics...")
    logger.info("="*70)
    
    xm = XMService()
    
    # Métricas de pérdidas
    metricas_perdidas = [
        'PerdidasEner',     # Pérdidas totales
        'PerdEnerRegu',     # Pérdidas reguladas
        'PerdEnerNoRe',     # Pérdidas no reguladas
    ]
    
    fecha_inicio = '2020-01-01'
    fecha_fin = datetime.now().strftime('%Y-%m-%d')
    
    total_insertados = 0
    
    for metrica in metricas_perdidas:
        try:
            logger.info(f"   📥 Descargando {metrica} desde {fecha_inicio} hasta {fecha_fin}...")
            
            df = xm.fetch_metric_data(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                metrica=metrica
            )
            
            if df.empty:
                logger.warning(f"   ⚠️  No hay datos para {metrica}")
                continue
            
            # Insertar en loss_metrics
            query = """
                INSERT INTO loss_metrics (fecha, metrica, valor_gwh, fecha_actualizacion)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (fecha, metrica) DO UPDATE
                SET valor_gwh = EXCLUDED.valor_gwh,
                    fecha_actualizacion = EXCLUDED.fecha_actualizacion
            """
            
            registros = 0
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for _, row in df.iterrows():
                        cur.execute(query, (
                            row.get('fecha'),
                            metrica,
                            row.get('valor', row.get('value', 0)),
                            datetime.now()
                        ))
                        registros += 1
                conn.commit()
            
            logger.info(f"   ✅ {metrica}: {registros} registros insertados")
            total_insertados += registros
            
        except Exception as e:
            logger.error(f"   ❌ Error con {metrica}: {e}")
            continue
    
    logger.info(f"\n✅ loss_metrics completado: {total_insertados} registros insertados\n")
    return total_insertados


def completar_restriction_metrics():
    """Completa la tabla restriction_metrics con restricciones"""
    logger.info("="*70)
    logger.info("📊 Completando restriction_metrics...")
    logger.info("="*70)
    
    xm = XMService()
    
    # Métricas de restricciones
    metricas_restricciones = [
        'RestAliv',         # Restricciones aliviadas
        'RestSinAliv',      # Restricciones sin aliviar
        'RestAlivSald',     # Restricciones aliviadas saldo
        'RestSinAlivSald',  # Restricciones sin aliviar saldo
    ]
    
    fecha_inicio = '2020-01-01'
    fecha_fin = datetime.now().strftime('%Y-%m-%d')
    
    total_insertados = 0
    
    for metrica in metricas_restricciones:
        try:
            logger.info(f"   📥 Descargando {metrica} desde {fecha_inicio} hasta {fecha_fin}...")
            
            df = xm.fetch_metric_data(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                metrica=metrica
            )
            
            if df.empty:
                logger.warning(f"   ⚠️  No hay datos para {metrica}")
                continue
            
            # Insertar en restriction_metrics
            query = """
                INSERT INTO restriction_metrics (fecha, metrica, valor_cop_millones, fecha_actualizacion)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (fecha, metrica) DO UPDATE
                SET valor_cop_millones = EXCLUDED.valor_cop_millones,
                    fecha_actualizacion = EXCLUDED.fecha_actualizacion
            """
            
            registros = 0
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for _, row in df.iterrows():
                        # Convertir $/kWh a Millones COP si es necesario
                        valor = row.get('valor', row.get('value', 0))
                        
                        cur.execute(query, (
                            row.get('fecha'),
                            metrica,
                            valor,
                            datetime.now()
                        ))
                        registros += 1
                conn.commit()
            
            logger.info(f"   ✅ {metrica}: {registros} registros insertados")
            total_insertados += registros
            
        except Exception as e:
            logger.error(f"   ❌ Error con {metrica}: {e}")
            continue
    
    logger.info(f"\n✅ restriction_metrics completado: {total_insertados} registros insertados\n")
    return total_insertados


def verificar_tablas_antes():
    """Verifica el estado de las tablas antes de completar"""
    logger.info("🔍 Verificando estado actual de las tablas...")
    logger.info("="*70)
    
    tablas = ['commercial_metrics', 'loss_metrics', 'restriction_metrics']
    
    for tabla in tablas:
        try:
            query = f"SELECT COUNT(*) as count FROM {tabla}"
            df = db_manager.query_df(query)
            count = df.iloc[0]['count'] if not df.empty else 0
            logger.info(f"   📊 {tabla}: {count:,} registros")
        except Exception as e:
            logger.warning(f"   ⚠️  {tabla}: Error al consultar - {e}")
    
    logger.info("="*70 + "\n")


def verificar_tablas_despues():
    """Verifica el estado de las tablas después de completar"""
    logger.info("\n" + "="*70)
    logger.info("✅ Verificando estado final de las tablas...")
    logger.info("="*70)
    
    tablas = ['commercial_metrics', 'loss_metrics', 'restriction_metrics']
    
    for tabla in tablas:
        try:
            query = f"SELECT COUNT(*) as count FROM {tabla}"
            df = db_manager.query_df(query)
            count = df.iloc[0]['count'] if not df.empty else 0
            logger.info(f"   📊 {tabla}: {count:,} registros")
        except Exception as e:
            logger.warning(f"   ⚠️  {tabla}: Error al consultar - {e}")
    
    logger.info("="*70)


def main():
    """Función principal"""
    logger.info("\n" + "="*70)
    logger.info("🚀 SCRIPT PARA COMPLETAR TABLAS INCOMPLETAS")
    logger.info("="*70)
    logger.info(f"📅 Fecha de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*70 + "\n")
    
    try:
        # Verificar estado inicial
        verificar_tablas_antes()
        
        # Completar cada tabla
        total_commercial = completar_commercial_metrics()
        total_loss = completar_loss_metrics()
        total_restriction = completar_restriction_metrics()
        
        # Verificar estado final
        verificar_tablas_despues()
        
        # Resumen final
        logger.info("\n" + "="*70)
        logger.info("🎉 PROCESO COMPLETADO EXITOSAMENTE")
        logger.info("="*70)
        logger.info(f"   📊 commercial_metrics: {total_commercial:,} registros")
        logger.info(f"   📊 loss_metrics: {total_loss:,} registros")
        logger.info(f"   📊 restriction_metrics: {total_restriction:,} registros")
        logger.info(f"   📊 TOTAL: {total_commercial + total_loss + total_restriction:,} registros insertados")
        logger.info("="*70 + "\n")
        
    except Exception as e:
        logger.error(f"\n❌ ERROR CRÍTICO: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
