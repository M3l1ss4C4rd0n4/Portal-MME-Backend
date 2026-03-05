#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║  BACKFILL losses_detailed — Pérdidas No Técnicas del SIN (2020–2026)        ║
║                                                                               ║
║  Ejecuta LossesNTService.backfill_losses() para todo el rango disponible.    ║
║  Usa ON CONFLICT DO NOTHING → seguro re-ejecutar sin duplicados.            ║
║                                                                               ║
║  Uso:                                                                         ║
║    cd /home/admonctrlxm/server                                               ║
║    source venv/bin/activate                                                   ║
║    python scripts/backfill_losses_detailed.py                                ║
║                                                                               ║
║  Fase 3 — Módulo de Pérdidas No Técnicas                                    ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import time

# Asegurar que el proyecto está en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta


def main():
    print("=" * 60)
    print("  BACKFILL losses_detailed — Pérdidas No Técnicas")
    print("=" * 60)

    # ── 1. Verificar rango de datos disponibles ──────────────
    import psycopg2
    from core.config import get_settings
    settings = get_settings()

    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )

    cur = conn.cursor()
    cur.execute("""
        SELECT MIN(fecha::date), MAX(fecha::date)
        FROM metrics
        WHERE metrica IN ('Gene', 'DemaCome')
          AND entidad = 'Sistema'
          AND valor_gwh > 0
    """)
    row = cur.fetchone()
    fecha_min = row[0]
    fecha_max = row[1]
    conn.close()

    # No incluir los últimos 2 días (lag DemaCome)
    fecha_fin = min(fecha_max, date.today() - timedelta(days=2))
    fecha_inicio = fecha_min

    print(f"\n  Rango metrics disponible: {fecha_min} → {fecha_max}")
    print(f"  Rango a procesar:         {fecha_inicio} → {fecha_fin}")
    total_dias = (fecha_fin - fecha_inicio).days + 1
    print(f"  Total días:               {total_dias}")
    print()

    # ── 2. Ejecutar backfill ─────────────────────────────────
    from domain.services.losses_nt_service import LossesNTService

    svc = LossesNTService()
    t0 = time.time()
    resumen = svc.backfill_losses(fecha_inicio, fecha_fin)
    elapsed = time.time() - t0

    print(f"\n  ✅ Backfill completado en {elapsed:.1f}s")
    print(f"     Total insertados:   {resumen['insertados']}")
    print(f"     Errores:            {resumen['errores']}")
    print(f"     Anomalías (total):  {resumen['anomalias']}")

    # ── 3. Estadísticas post-backfill ────────────────────────
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )
    cur = conn.cursor()

    # Conteos
    cur.execute("SELECT COUNT(*) FROM losses_detailed")
    total_filas = cur.fetchone()[0]

    # Anomalías desglosadas
    cur.execute("""
        SELECT
            SUM(CASE WHEN perdidas_no_tecnicas_pct < 0 THEN 1 ELSE 0 END) as neg,
            SUM(CASE WHEN perdidas_no_tecnicas_pct > 25 THEN 1 ELSE 0 END) as exc
        FROM losses_detailed
    """)
    anom = cur.fetchone()
    anom_neg = int(anom[0] or 0)
    anom_exc = int(anom[1] or 0)

    # Promedios
    cur.execute("""
        SELECT
            ROUND(AVG(perdidas_no_tecnicas_pct)::numeric, 4),
            ROUND(AVG(perdidas_tecnicas_pct)::numeric, 4),
            ROUND(AVG(perdidas_total_pct)::numeric, 4)
        FROM losses_detailed
    """)
    avg_row = cur.fetchone()

    # Últimos 365 días
    cur.execute("""
        SELECT
            ROUND(AVG(perdidas_no_tecnicas_pct)::numeric, 4),
            ROUND(SUM(COALESCE(costo_no_tecnicas_mcop, 0))::numeric, 2)
        FROM losses_detailed
        WHERE fecha >= CURRENT_DATE - INTERVAL '365 days'
    """)
    yr_row = cur.fetchone()

    conn.close()

    print(f"\n{'=' * 60}")
    print(f"  RESUMEN FINAL losses_detailed")
    print(f"{'=' * 60}")
    print(f"  Total filas:                      {total_filas}")
    print(f"  Días con anomalía PNT < 0%:       {anom_neg}")
    print(f"  Días con anomalía PNT > 25%:      {anom_exc}")
    print(f"  P_NT promedio histórico:           {avg_row[0]}%")
    print(f"  P_técnicas promedio histórico:     {avg_row[1]}%")
    print(f"  P_total promedio histórico:        {avg_row[2]}%")
    print(f"  P_NT promedio últimos 365 días:    {yr_row[0]}%")
    costo_12m = float(yr_row[1] or 0)
    if costo_12m > 1000:
        print(f"  Costo PNT estimado (12 meses):    ${costo_12m/1000:.1f} B COP")
    else:
        print(f"  Costo PNT estimado (12 meses):    ${costo_12m:.1f} M COP")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
