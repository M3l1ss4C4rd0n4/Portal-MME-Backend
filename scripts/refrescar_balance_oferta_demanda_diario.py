#!/usr/bin/env python3
"""
Puebla/actualiza sector_energetico.balance_oferta_demanda_diario (migración
044) — el resumen diario precalculado que usa el tablero Balance
Oferta-Demanda en vez de agregar en vivo sobre sector_energetico.metrics
(49.6M filas tras el backfill de la migración 043).

Corre la MISMA agregación que antes hacía
BalanceOfertaDemandaRepository.get_serie_diaria_oferta_demanda() en cada
request HTTP, pero una sola vez aquí, y guarda el resultado.

Uso:
    venv/bin/python3 scripts/refrescar_balance_oferta_demanda_diario.py
    venv/bin/python3 scripts/refrescar_balance_oferta_demanda_diario.py --desde-ultima-fecha

Sugerido en cron diario (después del ETL de XM) con --desde-ultima-fecha
para incorporar solo los días nuevos sin re-agregar el histórico completo.
"""

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--desde-ultima-fecha", action="store_true",
        help="Solo recalcula desde 3 días antes de la última fecha ya presente en la tabla "
             "(margen de solapamiento por si el ETL de XM corrigió datos recientes con retraso).",
    )
    args = parser.parse_args()

    import psycopg2
    from core.config import settings

    params = dict(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB, user=settings.POSTGRES_USER,
    )
    if settings.POSTGRES_PASSWORD:
        params["password"] = settings.POSTGRES_PASSWORD
    conn = psycopg2.connect(**params)
    conn.autocommit = True
    cur = conn.cursor()

    filtro_fecha = ""
    query_params: dict = {}
    if args.desde_ultima_fecha:
        cur.execute("SELECT MAX(fecha) FROM sector_energetico.balance_oferta_demanda_diario")
        ultima = cur.fetchone()[0]
        if ultima is not None:
            from datetime import timedelta
            desde = ultima - timedelta(days=3)
            filtro_fecha = "AND fecha >= %(desde)s"
            query_params["desde"] = desde
            log.info(f"Recalculando solo desde {desde} (--desde-ultima-fecha)")

    log.info("Agregando sector_energetico.metrics (puede tardar unos segundos)...")
    t0 = time.time()
    cur.execute(f"""
        INSERT INTO sector_energetico.balance_oferta_demanda_diario (
            fecha, oferta_declarada_mw, demanda_real_gwh, generacion_real_gwh,
            enficc_gwh, oef_gwh, actualizado_en
        )
        SELECT fecha::date,
               SUM(CASE WHEN metrica = 'DispoDeclarada' AND entidad = 'Recurso'
                        THEN valor_gwh END) AS oferta_declarada_mw,
               MAX(CASE WHEN metrica = 'DemaReal' AND entidad = 'Sistema'
                        THEN valor_gwh END) AS demanda_real_gwh,
               MAX(CASE WHEN metrica = 'Gene' AND entidad = 'Sistema'
                        THEN valor_gwh END) AS generacion_real_gwh,
               SUM(CASE WHEN metrica = 'ENFICC' AND entidad = 'Recurso'
                        THEN valor_gwh END) AS enficc_gwh,
               SUM(CASE WHEN metrica = 'ObligEnerFirme' AND entidad = 'Recurso'
                        THEN valor_gwh END) AS oef_gwh,
               NOW()
        FROM sector_energetico.metrics
        WHERE (
                (metrica = 'DispoDeclarada' AND entidad = 'Recurso')
             OR (metrica = 'DemaReal' AND entidad = 'Sistema')
             OR (metrica = 'Gene' AND entidad = 'Sistema')
             OR (metrica IN ('ENFICC', 'ObligEnerFirme') AND entidad = 'Recurso')
          )
          {filtro_fecha}
        GROUP BY fecha::date
        ON CONFLICT (fecha) DO UPDATE SET
            oferta_declarada_mw = EXCLUDED.oferta_declarada_mw,
            demanda_real_gwh = EXCLUDED.demanda_real_gwh,
            generacion_real_gwh = EXCLUDED.generacion_real_gwh,
            enficc_gwh = EXCLUDED.enficc_gwh,
            oef_gwh = EXCLUDED.oef_gwh,
            actualizado_en = NOW()
    """, query_params)
    log.info(f"Listo en {time.time() - t0:.1f}s — {cur.rowcount} filas insertadas/actualizadas")

    cur.execute("SELECT MIN(fecha), MAX(fecha), COUNT(*) FROM sector_energetico.balance_oferta_demanda_diario")
    log.info(f"Cobertura final de balance_oferta_demanda_diario: {cur.fetchone()}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
