#!/usr/bin/env python3
"""
Retención de predictions_history
=================================

Purga batches archivados (por el trigger trg_predictions_archive_on_delete,
ver sql/migrations/016_predictions_history_archive.sql) más antiguos que
RETENTION_DAYS. 120 días cubre ~10x la ventana que necesita el ensemble
adaptativo (_adjust_weights_from_history: últimos 5 runs ≈ 10-15 días) y
varios meses de evaluación ex-post incluso para fuentes de horizonte largo
(hasta 365 días, ej. EMBALSES_PCT).

Ejecución recomendada: semanal, domingo, fuera de horario de retrain
(cron sugerido: 0 4 * * 0, después del backup semanal de metrics a las 3:00).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from datetime import datetime

RETENTION_DAYS = 120


def get_postgres_connection():
    from core.config import settings
    conn_params = {
        'host': settings.POSTGRES_HOST,
        'port': settings.POSTGRES_PORT,
        'database': settings.POSTGRES_DB,
        'user': settings.POSTGRES_USER,
    }
    if settings.POSTGRES_PASSWORD:
        conn_params['password'] = settings.POSTGRES_PASSWORD
    return psycopg2.connect(**conn_params)


def main():
    print("=" * 70)
    print("🧹 LIMPIEZA DE predictions_history")
    print(f"   Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Retención: {RETENTION_DAYS} días")
    print("=" * 70)

    conn = get_postgres_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM predictions_history WHERE archived_at < NOW() - INTERVAL '1 day' * %s",
        (RETENTION_DAYS,)
    )
    borradas = cur.rowcount
    conn.commit()
    print(f"\n✅ {borradas} filas eliminadas (archived_at > {RETENTION_DAYS} días)")

    conn.autocommit = True
    cur.execute("VACUUM (ANALYZE) predictions_history")
    print("✅ VACUUM (ANALYZE) predictions_history completado")

    cur.close()
    conn.close()
    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    main()
