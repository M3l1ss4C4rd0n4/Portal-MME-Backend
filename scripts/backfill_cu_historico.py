#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║        BACKFILL CU HISTÓRICO — Llena cu_daily con datos existentes          ║
║                                                                               ║
║  Ejecutar una sola vez después de crear CUService.                          ║
║  Calcula CU para todo el rango de datos disponibles en metrics.             ║
║                                                                               ║
║  Uso:                                                                        ║
║    cd /home/admonctrlxm/server                                               ║
║    source venv/bin/activate                                                   ║
║    python scripts/backfill_cu_historico.py                                   ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import logging
from datetime import date

# Asegurar que el directorio raíz del proyecto esté en el path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

from domain.services.cu_service import CUService
from infrastructure.database.connection import PostgreSQLConnectionManager
from core.config import get_settings


def backfill_batch_sql():
    """
    Backfill optimizado: una sola query SQL que calcula CU 
    para todos los días y los inserta en cu_daily de golpe.
    """
    settings = get_settings()
    cargo_t = settings.CARGO_TRANSMISION_COP_KWH
    cargo_d = settings.CARGO_DISTRIBUCION_COP_KWH
    cargo_c = settings.CARGO_COMERCIALIZACION_COP_KWH
    factor_dist = settings.FACTOR_PERDIDAS_DISTRIBUCION

    conn_mgr = PostgreSQLConnectionManager()

    # Query batch: pivotea métricas por fecha y calcula CU en SQL
    batch_sql = f"""
    WITH daily AS (
        SELECT
            fecha::date AS fecha,
            MAX(CASE WHEN metrica = 'Gene' THEN valor_gwh END) AS gene_gwh,
            MAX(CASE WHEN metrica = 'DemaCome' THEN valor_gwh END) AS dema_gwh,
            MAX(CASE WHEN metrica = 'PrecBolsNaci' THEN valor_gwh END) AS precio_bolsa,
            MAX(CASE WHEN metrica = 'RestAliv' THEN valor_gwh END) AS rest_aliv,
            MAX(CASE WHEN metrica = 'RestSinAliv' THEN valor_gwh END) AS rest_sin_aliv,
            MAX(CASE WHEN metrica = 'PerdidasEner' THEN valor_gwh END) AS perdidas_gwh
        FROM metrics
        WHERE entidad = 'Sistema'
          AND metrica IN ('Gene', 'DemaCome', 'PrecBolsNaci', 'RestAliv', 'RestSinAliv', 'PerdidasEner')
        GROUP BY fecha::date
    ),
    calc AS (
        SELECT
            fecha,
            precio_bolsa AS comp_g,
            {cargo_t} AS comp_t,
            {cargo_d} AS comp_d,
            {cargo_c} AS comp_c,
            -- comp_r = (RestAliv + RestSinAliv) / DemaCome  [Millones COP / GWh = COP/kWh]
            CASE 
                WHEN dema_gwh > 0 AND rest_aliv IS NOT NULL 
                THEN (COALESCE(rest_aliv, 0) + COALESCE(rest_sin_aliv, 0)) / dema_gwh
                ELSE NULL
            END AS comp_r,
            -- pérdidas STN como fracción
            CASE 
                WHEN gene_gwh > 0 AND perdidas_gwh IS NOT NULL 
                THEN perdidas_gwh / gene_gwh
                ELSE 0
            END AS perdidas_stn_frac,
            dema_gwh,
            gene_gwh,
            perdidas_gwh,
            -- Conteo de fuentes disponibles
            (CASE WHEN gene_gwh IS NOT NULL THEN 1 ELSE 0 END
             + CASE WHEN dema_gwh IS NOT NULL THEN 1 ELSE 0 END
             + CASE WHEN precio_bolsa IS NOT NULL THEN 1 ELSE 0 END
             + CASE WHEN rest_aliv IS NOT NULL THEN 1 ELSE 0 END
             + CASE WHEN perdidas_gwh IS NOT NULL THEN 1 ELSE 0 END) AS num_metricas
        FROM daily
    ),
    final AS (
        SELECT
            fecha,
            comp_g,
            comp_t,
            comp_d,
            comp_c,
            comp_r,
            -- factor total de pérdidas
            LEAST(perdidas_stn_frac + {factor_dist}, 0.95) AS factor_total,
            -- suma base
            COALESCE(comp_g, 0) + comp_t + comp_d + comp_c + COALESCE(comp_r, 0) AS suma_base,
            dema_gwh,
            gene_gwh,
            perdidas_gwh,
            -- pérdidas totales %
            CASE 
                WHEN perdidas_gwh IS NOT NULL AND gene_gwh > 0 
                THEN (perdidas_stn_frac + {factor_dist}) * 100
                ELSE NULL
            END AS perdidas_pct,
            -- fuentes OK (T, D, C siempre cuentan + G y R si disponibles)
            3 + (CASE WHEN comp_g IS NOT NULL THEN 1 ELSE 0 END)
              + (CASE WHEN comp_r IS NOT NULL THEN 1 ELSE 0 END) AS fuentes_ok,
            -- confianza
            CASE
                WHEN num_metricas >= 5 AND perdidas_gwh IS NOT NULL THEN 'alta'
                WHEN num_metricas >= 3 THEN 'media'
                ELSE 'baja'
            END AS confianza,
            -- notas
            CONCAT_WS('; ',
                CASE WHEN comp_g IS NULL THEN 'sin_precio_bolsa' END,
                CASE WHEN comp_r IS NULL THEN 'sin_restricciones' END,
                CASE WHEN perdidas_gwh IS NULL THEN 'sin_perdidas_stn' END
            ) AS notas,
            num_metricas
        FROM calc
        WHERE num_metricas >= 2
    )
    INSERT INTO cu_daily (
        fecha, componente_g, componente_t, componente_d,
        componente_c, componente_p, componente_r, cu_total,
        demanda_gwh, generacion_gwh, perdidas_gwh, perdidas_pct,
        fuentes_ok, confianza, notas
    )
    SELECT
        fecha,
        ROUND(comp_g::numeric, 4),
        ROUND(comp_t::numeric, 4),
        ROUND(comp_d::numeric, 4),
        ROUND(comp_c::numeric, 4),
        -- componente_p = (suma_base * factor_pérdidas) - suma_base
        ROUND((suma_base * (1.0 / (1.0 - factor_total)) - suma_base)::numeric, 4),
        ROUND(comp_r::numeric, 4),
        -- cu_total = suma_base * factor_pérdidas
        ROUND((suma_base * (1.0 / (1.0 - factor_total)))::numeric, 4),
        ROUND(dema_gwh::numeric, 6),
        ROUND(gene_gwh::numeric, 6),
        ROUND(perdidas_gwh::numeric, 6),
        ROUND(perdidas_pct::numeric, 4),
        fuentes_ok,
        confianza,
        NULLIF(notas, '')
    FROM final
    ORDER BY fecha
    ON CONFLICT (fecha) DO UPDATE SET
        componente_g = EXCLUDED.componente_g,
        componente_t = EXCLUDED.componente_t,
        componente_d = EXCLUDED.componente_d,
        componente_c = EXCLUDED.componente_c,
        componente_p = EXCLUDED.componente_p,
        componente_r = EXCLUDED.componente_r,
        cu_total = EXCLUDED.cu_total,
        demanda_gwh = EXCLUDED.demanda_gwh,
        generacion_gwh = EXCLUDED.generacion_gwh,
        perdidas_gwh = EXCLUDED.perdidas_gwh,
        perdidas_pct = EXCLUDED.perdidas_pct,
        fuentes_ok = EXCLUDED.fuentes_ok,
        confianza = EXCLUDED.confianza,
        notas = EXCLUDED.notas
    """

    logger.info("Ejecutando INSERT batch en cu_daily...")
    with conn_mgr.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(batch_sql)
        rowcount = cur.rowcount
        conn.commit()
        cur.close()

    logger.info(f"Insertados/actualizados: {rowcount} filas")
    return rowcount


def main():
    """Ejecuta el backfill de CU histórico."""
    logger.info("=" * 70)
    logger.info("BACKFILL CU HISTÓRICO — Inicio (modo batch SQL)")
    logger.info("=" * 70)

    # Detectar rango de datos disponibles
    conn_mgr = PostgreSQLConnectionManager()
    with conn_mgr.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT MIN(fecha::date), MAX(fecha::date), COUNT(DISTINCT fecha::date)
            FROM metrics
            WHERE entidad = 'Sistema'
              AND metrica IN ('Gene', 'DemaCome', 'PrecBolsNaci', 'RestAliv', 'PerdidasEner')
        """)
        row = cur.fetchone()
        cur.close()
        conn.commit()

    if not row or not row[0]:
        logger.error("No hay datos en metrics. Abortando.")
        return

    fecha_min, fecha_max, dias_con_dato = row[0], row[1], row[2]
    logger.info(f"Rango de datos en metrics: {fecha_min} → {fecha_max}")
    logger.info(f"Días con al menos 1 métrica: {dias_con_dato}")

    # Ejecutar backfill batch
    rowcount = backfill_batch_sql()

    # Verificar resultado
    logger.info("=" * 70)
    logger.info(f"RESULTADO BACKFILL: {rowcount} filas insertadas/actualizadas")
    logger.info("=" * 70)

    # Verificar tabla final
    with conn_mgr.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(fecha), MAX(fecha) FROM cu_daily")
        row_count = cur.fetchone()
        cur.execute("""
            SELECT 
                ROUND(AVG(cu_total)::numeric, 2) AS avg_cu,
                ROUND(MIN(cu_total)::numeric, 2) AS min_cu,
                ROUND(MAX(cu_total)::numeric, 2) AS max_cu,
                ROUND(AVG(componente_g)::numeric, 2) AS avg_g,
                ROUND(AVG(componente_r)::numeric, 2) AS avg_r
            FROM cu_daily
        """)
        stats_db = cur.fetchone()
        cur.execute("""
            SELECT confianza, COUNT(*)
            FROM cu_daily
            GROUP BY confianza
            ORDER BY COUNT(*) DESC
        """)
        confianza_dist = cur.fetchall()
        cur.close()
        conn.commit()

    logger.info(f"\nTABLA cu_daily:")
    logger.info(f"  Total filas: {row_count[0]}")
    logger.info(f"  Rango:       {row_count[1]} → {row_count[2]}")
    if stats_db:
        logger.info(f"  CU promedio: {stats_db[0]} COP/kWh")
        logger.info(f"  CU mínimo:   {stats_db[1]} COP/kWh")
        logger.info(f"  CU máximo:   {stats_db[2]} COP/kWh")
        logger.info(f"  G promedio:  {stats_db[3]} COP/kWh")
        logger.info(f"  R promedio:  {stats_db[4]} COP/kWh")
    if confianza_dist:
        logger.info(f"\n  Distribución de confianza:")
        for conf, cnt in confianza_dist:
            logger.info(f"    {conf}: {cnt}")

    logger.info("\n✅ Backfill completado.")


if __name__ == '__main__':
    main()
