#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import settings
import psycopg2
from datetime import date

conn = psycopg2.connect(settings.DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()
today = date.today()

print("=== predictions ===")
cur.execute("SELECT fuente, modelo, COUNT(*), MIN(fecha_prediccion::date), MAX(fecha_prediccion::date), MIN(fecha_generacion::date), MAX(fecha_generacion::date) FROM predictions GROUP BY fuente, modelo ORDER BY fuente, modelo")
for r in cur.fetchall():
    fut = f" ({(r[4]-today).days}d futuro)" if r[4] >= today else " <- SIN FUTURO"
    print(f"  fuente={r[0]} modelo={r[1]}: {r[2]} rows | pred {r[3]}-->{r[4]}{fut} | gen {r[5]}-->{r[6]}")

print("\n=== commercial_metrics ===")
cur.execute("SELECT metrica, COUNT(*), MIN(fecha::date), MAX(fecha::date) FROM commercial_metrics GROUP BY metrica ORDER BY metrica")
for r in cur.fetchall():
    stale = " <- DESACT" if r[3] < date(2026,2,1) else ""
    print(f"  {r[0]:30s}: {r[1]:,} | {r[2]}->{r[3]}{stale}")

print("\n=== restriction_metrics ===")
cur.execute("SELECT COUNT(*), MIN(fecha::date), MAX(fecha::date), COUNT(DISTINCT metric_code) FROM restriction_metrics")
r = cur.fetchone()
stale = " <- DESACT" if r[2] < date(2026,3,1) else ""
print(f"  {r[0]:,} filas | {r[1]}->{r[2]} | {r[3]} metricas{stale}")

print("\n=== loss_metrics ===")
cur.execute("SELECT COUNT(*), MIN(fecha::date), MAX(fecha::date), COUNT(DISTINCT metric_code) FROM loss_metrics")
r = cur.fetchone()
stale = " <- DESACT" if r[2] < date(2026,3,1) else ""
print(f"  {r[0]:,} filas | {r[1]}->{r[2]} | {r[3]} metricas{stale}")

print("\n=== lineas_transmision ===")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='lineas_transmision' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print(f"  Columnas: {cols}")
date_col = [c for c in cols if 'fecha' in c.lower()]
if date_col:
    cur.execute(f"SELECT COUNT(*), MIN({date_col[0]}::date), MAX({date_col[0]}::date) FROM lineas_transmision")
    r = cur.fetchone()
    stale = " <- DESACT" if r[2] < date(2026,3,1) else ""
    print(f"  {r[0]:,} filas | {r[1]}->{r[2]}{stale}")

print("\n=== subsidios_pagos ===")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='subsidios_pagos' ORDER BY ordinal_position LIMIT 10")
cols = [r[0] for r in cur.fetchall()]
print(f"  Columnas: {cols}")
date_col = [c for c in cols if 'mes' in c.lower() or 'fecha' in c.lower()]
if date_col:
    cur.execute(f"SELECT COUNT(*), MIN({date_col[0]}), MAX({date_col[0]}) FROM subsidios_pagos")
    r = cur.fetchone()
    print(f"  {r[0]:,} filas | {r[1]}->{r[2]}")

print("\n=== catalogos ===")
cur.execute("SELECT catalogo, COUNT(*) FROM catalogos GROUP BY catalogo ORDER BY catalogo")
for r in cur.fetchall():
    print(f"  {r[0]:40s}: {r[1]:,}")

print("\n=== cu_daily ===")
cur.execute("SELECT COUNT(*), MIN(fecha::date), MAX(fecha::date), ROUND(AVG(cu_total)::numeric,2) FROM cu_daily")
r = cur.fetchone()
stale = " <- DESACT" if r[2] < date(2026,3,1) else ""
print(f"  {r[0]:,} filas | {r[1]}->{r[2]} | avg_cu_total={r[3]}{stale}")

print("\n=== metrics_hourly cobertura ===")
cur.execute("SELECT metrica, entidad, MIN(fecha::date), MAX(fecha::date), COUNT(DISTINCT fecha::date) FROM metrics_hourly GROUP BY metrica, entidad ORDER BY metrica, entidad")
for r in cur.fetchall():
    stale = " <- DESACT" if r[3] < date(2026,3,1) else ""
    print(f"  {r[0]:25s}/{r[1]:12s}: {r[2]}->{r[3]} ({r[4]}d){stale}")

print("\n=== Gene/Recurso y AporEner/Rio verificacion final ===")
for met, ent in [('Gene','Recurso'),('AporEner','Rio'),('VoluUtilDiarEner','Embalse'),('DemaCome','Sistema'),('PrecBolsNaci','Sistema'),('GeneSeguridad','Recurso')]:
    cur.execute("SELECT extract(year from fecha)::int, round(count(*)::numeric/nullif(count(distinct fecha::date),0),1) FROM metrics WHERE metrica=%s AND entidad=%s GROUP BY 1 ORDER BY 1", (met,ent))
    rows = cur.fetchall()
    vals = {int(r[0]): float(r[1]) for r in rows}
    bugs = [yr for yr,fpd in vals.items() if fpd < 2]
    status = f" BUG AÑOS {bugs}" if bugs else " OK"
    v2020 = vals.get(2020,0); v2025 = vals.get(2025,0); v2026 = vals.get(2026,0)
    print(f"  {met:25s}/{ent:12s}: 2020={v2020} 2025={v2025} 2026={v2026}{status}")

conn.close()
print("\nDone.")
