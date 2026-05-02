"""
Script para completar datos faltantes en tablas incompletas

Ejecuta ETL específico para llenar:
- commercial_metrics (precios comerciales)
- loss_metrics (pérdidas energéticas)
- restriction_metrics (restricciones)
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.database.manager import db_manager
from infrastructure.external.xm_service import XMService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


# ───────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN POR TABLA (único lugar donde se definen las diferencias)
# ───────────────────────────────────────────────────────────────────────────────

_CONFIG_TABLAS: Dict[str, Dict[str, Any]] = {
    'commercial_metrics': {
        'nombre_log': 'commercial_metrics',
        'metricas': [
            'PrecBolsNaci',   # Precio bolsa nacional
            'PrecEscaSupe',   # Precio escasez superior
            'PrecEscaActi',   # Precio escasez activación
            'PrecEscaInfe',   # Precio escasez inferior
        ],
        'query': """
            INSERT INTO commercial_metrics (fecha, metrica, valor, unidad, fecha_actualizacion)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (fecha, metrica) DO UPDATE
            SET valor = EXCLUDED.valor,
                unidad = EXCLUDED.unidad,
                fecha_actualizacion = EXCLUDED.fecha_actualizacion
        """,
        'preparar_fila': lambda row, metrica, now: (
            row.get('fecha'),
            metrica,
            row.get('valor', row.get('value', 0)),
            row.get('unidad', '$/kWh'),
            now,
        ),
    },
    'loss_metrics': {
        'nombre_log': 'loss_metrics',
        'metricas': [
            'PerdidasEner',     # Pérdidas totales
            'PerdEnerRegu',     # Pérdidas reguladas
            'PerdEnerNoRe',     # Pérdidas no reguladas
        ],
        'query': """
            INSERT INTO loss_metrics (fecha, metrica, valor_gwh, fecha_actualizacion)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (fecha, metrica) DO UPDATE
            SET valor_gwh = EXCLUDED.valor_gwh,
                fecha_actualizacion = EXCLUDED.fecha_actualizacion
        """,
        'preparar_fila': lambda row, metrica, now: (
            row.get('fecha'),
            metrica,
            row.get('valor', row.get('value', 0)),
            now,
        ),
    },
    'restriction_metrics': {
        'nombre_log': 'restriction_metrics',
        'metricas': [
            'RestAliv',         # Restricciones aliviadas
            'RestSinAliv',      # Restricciones sin aliviar
            'RestAlivSald',     # Restricciones aliviadas saldo
            'RestSinAlivSald',  # Restricciones sin aliviar saldo
        ],
        'query': """
            INSERT INTO restriction_metrics (fecha, metrica, valor_cop_millones, fecha_actualizacion)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (fecha, metrica) DO UPDATE
            SET valor_cop_millones = EXCLUDED.valor_cop_millones,
                fecha_actualizacion = EXCLUDED.fecha_actualizacion
        """,
        'preparar_fila': lambda row, metrica, now: (
            row.get('fecha'),
            metrica,
            row.get('valor', row.get('value', 0)),
            now,
        ),
    },
}


# ───────────────────────────────────────────────────────────────────────────────
# FUNCIÓN GENÉRICA (el motor)
# ───────────────────────────────────────────────────────────────────────────────

def _completar_tabla_metricas(
    nombre_tabla: str,
    metricas: List[str],
    query_insert: str,
    preparar_fila: Callable[[Any, str, datetime], tuple],
    nombre_log: str,
    fecha_inicio: str = '2020-01-01',
) -> int:
    """
    Motor genérico para completar tablas de métricas desde XM.

    Args:
        nombre_tabla: Nombre de la tabla destino en PostgreSQL
        metricas: Lista de códigos de métricas XM a descargar
        query_insert: Query SQL INSERT ON CONFLICT
        preparar_fila: Callable que recibe (row, metrica, now) → tuple de valores
        nombre_log: Nombre para los logs
        fecha_inicio: Fecha inicial para la descarga (default: 2020-01-01)

    Returns:
        Total de registros insertados/actualizados
    """
    logger.info("=" * 70)
    logger.info(f"📊 Completando {nombre_log}...")
    logger.info("=" * 70)

    xm = XMService()
    fecha_fin = datetime.now().strftime('%Y-%m-%d')
    total_insertados = 0

    for metrica in metricas:
        try:
            logger.info(f"   📥 Descargando {metrica} desde {fecha_inicio} hasta {fecha_fin}...")

            df = xm.fetch_metric_data(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                metrica=metrica,
            )

            if df.empty:
                logger.warning(f"   ⚠️  No hay datos para {metrica}")
                continue

            registros = 0
            now = datetime.now()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for _, row in df.iterrows():
                        valores = preparar_fila(row, metrica, now)
                        cur.execute(query_insert, valores)
                        registros += 1
                conn.commit()

            logger.info(f"   ✅ {metrica}: {registros} registros insertados")
            total_insertados += registros

        except Exception as e:
            logger.error(f"   ❌ Error con {metrica}: {e}")
            continue

    logger.info(f"\n✅ {nombre_log} completado: {total_insertados} registros insertados\n")
    return total_insertados


# ───────────────────────────────────────────────────────────────────────────────
# WRAPPERS PÚBLICOS (compatibilidad 100% hacia atrás)
# ───────────────────────────────────────────────────────────────────────────────

def completar_commercial_metrics() -> int:
    """Completa la tabla commercial_metrics con precios comerciales"""
    cfg = _CONFIG_TABLAS['commercial_metrics']
    return _completar_tabla_metricas(
        nombre_tabla='commercial_metrics',
        metricas=cfg['metricas'],
        query_insert=cfg['query'],
        preparar_fila=cfg['preparar_fila'],
        nombre_log=cfg['nombre_log'],
    )


def completar_loss_metrics() -> int:
    """Completa la tabla loss_metrics con pérdidas energéticas"""
    cfg = _CONFIG_TABLAS['loss_metrics']
    return _completar_tabla_metricas(
        nombre_tabla='loss_metrics',
        metricas=cfg['metricas'],
        query_insert=cfg['query'],
        preparar_fila=cfg['preparar_fila'],
        nombre_log=cfg['nombre_log'],
    )


def completar_restriction_metrics() -> int:
    """Completa la tabla restriction_metrics con restricciones"""
    cfg = _CONFIG_TABLAS['restriction_metrics']
    return _completar_tabla_metricas(
        nombre_tabla='restriction_metrics',
        metricas=cfg['metricas'],
        query_insert=cfg['query'],
        preparar_fila=cfg['preparar_fila'],
        nombre_log=cfg['nombre_log'],
    )


# ───────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ───────────────────────────────────────────────────────────────────────────────

def verificar_tablas_antes():
    """Verifica el estado de las tablas antes de completar"""
    logger.info("🔍 Verificando estado actual de las tablas...")
    logger.info("=" * 70)

    tablas = list(_CONFIG_TABLAS.keys())

    for tabla in tablas:
        try:
            query = f"SELECT COUNT(*) as count FROM {tabla}"
            df = db_manager.query_df(query)
            count = df.iloc[0]['count'] if not df.empty else 0
            logger.info(f"   📊 {tabla}: {count:,} registros")
        except Exception as e:
            logger.warning(f"   ⚠️  {tabla}: Error al consultar - {e}")

    logger.info("=" * 70 + "\n")


def verificar_tablas_despues():
    """Verifica el estado de las tablas después de completar"""
    logger.info("\n" + "=" * 70)
    logger.info("✅ Verificando estado final de las tablas...")
    logger.info("=" * 70)

    tablas = list(_CONFIG_TABLAS.keys())

    for tabla in tablas:
        try:
            query = f"SELECT COUNT(*) as count FROM {tabla}"
            df = db_manager.query_df(query)
            count = df.iloc[0]['count'] if not df.empty else 0
            logger.info(f"   📊 {tabla}: {count:,} registros")
        except Exception as e:
            logger.warning(f"   ⚠️  {tabla}: Error al consultar - {e}")

    logger.info("=" * 70)


def main():
    """Función principal"""
    logger.info("\n" + "=" * 70)
    logger.info("🚀 SCRIPT PARA COMPLETAR TABLAS INCOMPLETAS")
    logger.info("=" * 70)
    logger.info(f"📅 Fecha de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70 + "\n")

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
        logger.info("\n" + "=" * 70)
        logger.info("🎉 PROCESO COMPLETADO EXITOSAMENTE")
        logger.info("=" * 70)
        logger.info(f"   📊 commercial_metrics: {total_commercial:,} registros")
        logger.info(f"   📊 loss_metrics: {total_loss:,} registros")
        logger.info(f"   📊 restriction_metrics: {total_restriction:,} registros")
        logger.info(f"   📊 TOTAL: {total_commercial + total_loss + total_restriction:,} registros insertados")
        logger.info("=" * 70 + "\n")

    except Exception as e:
        logger.error(f"\n❌ ERROR CRÍTICO: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
