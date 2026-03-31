#!/usr/bin/env python3
"""
ETL incremental para losses_detailed (Pérdidas No Técnicas del SIN).

Calcula y persiste PNT para fechas aún no cubiertas, desde
(MAX fecha en losses_detailed + 1 día) hasta (hoy - 2 días).

Uso:
    # Modo automático (usa max_fecha de DB):
    python3 etl/etl_losses_detailed.py

    # Modo manual con rango explícito:
    python3 etl/etl_losses_detailed.py --desde 2026-02-28 --hasta 2026-03-20
"""

import sys
import os
import argparse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from core.config import get_settings
from domain.services.losses_nt_service import LossesNTService
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)
_LAG_DIAS = 2  # DemaCome tiene rezago de ~2 días


def _get_max_fecha_db() -> date:
    """Obtiene la última fecha registrada en losses_detailed."""
    s = get_settings()
    conn = psycopg2.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
        database=s.POSTGRES_DB, user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
    )
    cur = conn.cursor()
    cur.execute("SELECT MAX(fecha) FROM losses_detailed")
    row = cur.fetchone()
    conn.close()
    if row[0]:
        return row[0]
    # Si la tabla está vacía, arrancar desde el inicio del SIN
    return date(2020, 2, 6)


def main():
    parser = argparse.ArgumentParser(description="ETL incremental losses_detailed")
    parser.add_argument("--desde", type=lambda s: date.fromisoformat(s),
                        help="Fecha inicio (YYYY-MM-DD). Default: max en DB + 1 día")
    parser.add_argument("--hasta", type=lambda s: date.fromisoformat(s),
                        help="Fecha fin (YYYY-MM-DD). Default: hoy - 2 días")
    args = parser.parse_args()

    fecha_fin = args.hasta if args.hasta else date.today() - timedelta(days=_LAG_DIAS)

    if args.desde:
        fecha_inicio = args.desde
    else:
        max_fecha = _get_max_fecha_db()
        fecha_inicio = max_fecha + timedelta(days=1)

    if fecha_inicio > fecha_fin:
        logger.info("losses_detailed ya está al día (max=%s, límite=%s). Sin cambios.",
                    fecha_inicio - timedelta(days=1), fecha_fin)
        print(f"✅ losses_detailed ya al día (max={fecha_inicio - timedelta(days=1)}, límite={fecha_fin})")
        return

    dias = (fecha_fin - fecha_inicio).days + 1
    logger.info("Iniciando ETL losses_detailed: %s → %s (%d días)", fecha_inicio, fecha_fin, dias)
    print(f"\n{'='*60}")
    print(f"  ETL losses_detailed — Pérdidas No Técnicas")
    print(f"{'='*60}")
    print(f"  Rango: {fecha_inicio} → {fecha_fin} ({dias} días)")

    svc = LossesNTService()
    resumen = svc.backfill_losses(fecha_inicio, fecha_fin)

    print(f"\n  ✅ Completado")
    print(f"     Insertados: {resumen['insertados']}")
    print(f"     Errores:    {resumen['errores']}")
    print(f"     Anomalías:  {resumen['anomalias']}")
    print(f"     Total días: {resumen['total_dias']}")

    if resumen['errores'] > 0:
        logger.warning("ETL losses_detailed: %d errores en %d días procesados",
                       resumen['errores'], resumen['total_dias'])
        sys.exit(1)


if __name__ == "__main__":
    main()
