#!/usr/bin/env python3
"""
Script de inspección exhaustiva de la base de datos PostgreSQL del Portal MME.
Detecta irregularidades, bugs de datos, gaps y anomalías.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
import psycopg2
import psycopg2.extras
from datetime import datetime, date

conn = psycopg2.connect(settings.DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

ROJO   = "\033[91m"
VERDE  = "\033[92m"
AMARIL = "\033[93m"
RESET  = "\033[0m"

hallazgos = []

def titulo(texto):
    print(f"\n{'=' * 70}")
    print(f"  {texto}")
    print('=' * 70)

def ok(msg):    print(f"  {VERDE}✅{RESET} {msg}")
def warn(msg):  print(f"  {AMARIL}⚠️ {RESET} {msg}"); hallazgos.append(('WARN', msg))
def error(msg): print(f"  {ROJO}❌{RESET} {msg}"); hallazgos.append(('ERROR', msg))

# ──────────────────────────────────────────────────────────────────────────────
titulo("1. TAMAÑO Y COBERTURA TEMPORAL DE CADA TABLA")
tablas = [
    ('metrics', 'fecha'),
    ('metrics_hourly', 'fecha'),
    ('commercial_metrics', 'fecha'),
    ('lineas_transmision', 'fecha'),
    ('predictions', 'fecha_prediccion'),
    ('restriction_metrics', 'fecha'),
    ('loss_metrics', 'fecha'),
    ('cu_daily', 'fecha'),
    ('subsidios_pagos', 'fecha'),
    ('losses_detailed', 'fecha'),
    ('cu_tarifas_or', 'fecha_inicio'),
]
for tbl, col in tablas:
    try:
        cur.execute(f"SELECT COUNT(*), MIN({col}::date), MAX({col}::date), COUNT(DISTINCT {col}::date) FROM {tbl}")
        cnt, mn, mx, nd = cur.fetchone()
        print(f"  {tbl:32s}: {cnt:>12,} filas | {str(mn)[:10]} → {str(mx)[:10]} ({nd:,} días)")
        if mx and mx < date(2026, 3, 1):
            warn(f"  {tbl}: última fecha es {mx} — posible tabla desactualizada")
    except Exception as e:
        error(f"{tbl}: {e}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("2. metrics — FILAS/DÍA POR MÉTRICA+ENTIDAD (bug 1-fila/día detectado)")
cur.execute("""
SELECT metrica, entidad,
       COUNT(*) as total,
       COUNT(DISTINCT fecha::date) as dias,
       ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT fecha::date),0), 1) as fpd
FROM metrics
GROUP BY metrica, entidad
ORDER BY fpd, metrica, entidad
""")
rows = cur.fetchall()
bugs_bug = [r for r in rows if float(r[4] or 0) < 2.0]
ok_rows  = [r for r in rows if float(r[4] or 0) >= 2.0]

if bugs_bug:
    for r in bugs_bug:
        error(f"{r[0]:30s}/{r[1]:15s}: {r[2]:,} filas / {r[3]:,} días = {r[4]} f/d  ← BUG")
else:
    ok("Ninguna combinación métrica+entidad tiene ≤1 fila/día")

print(f"\n  Combinaciones saludables ({len(ok_rows)}):")
for r in ok_rows:
    print(f"    {r[0]:30s}/{r[1]:15s}: {r[2]:>10,} filas | {r[3]:,}d | {r[4]} f/d")

# ──────────────────────────────────────────────────────────────────────────────
titulo("3. GAPS TEMPORALES EN metrics (días faltantes por año por métrica clave)")
metricas_clave = ['Gene', 'AporEner', 'AporCaudal', 'DemaCome', 'DemaReal', 'VoluUtilDiarEner']
cur.execute("""
SELECT metrica, entidad, 
       EXTRACT(YEAR FROM fecha)::int as anio,
       COUNT(DISTINCT fecha::date) as dias_con_datos
FROM metrics
WHERE metrica = ANY(%s)
GROUP BY metrica, entidad, anio
ORDER BY metrica, entidad, anio
""", (metricas_clave,))

gap_rows = cur.fetchall()
for r in gap_rows:
    anio, dias = r[2], r[3]
    esperados = 366 if anio in (2020, 2024) else 365
    if anio == 2026:
        today = date.today()
        esperados = (today - date(2026, 1, 1)).days + 1
    faltantes = esperados - dias
    if faltantes > 5:
        warn(f"{r[0]:25s}/{r[1]:12s} {anio}: {dias}/{esperados} días ← FALTAN {faltantes}")
    else:
        print(f"    {r[0]:25s}/{r[1]:12s} {anio}: {dias}/{esperados} días ✓")

# ──────────────────────────────────────────────────────────────────────────────
titulo("4. VALORES ANÓMALOS EN metrics")
# 4a. Valores NULL
cur.execute("SELECT COUNT(*) FROM metrics WHERE valor_gwh IS NULL")
nulls = cur.fetchone()[0]
if nulls > 0:
    error(f"Valores NULL en valor_gwh: {nulls:,}")
else:
    ok("Sin NULLs en valor_gwh")

# 4b. Valores negativos por métrica (se esperan solo en algunas)
cur.execute("""
SELECT metrica, entidad, COUNT(*) as neg
FROM metrics
WHERE valor_gwh < 0
GROUP BY metrica, entidad
ORDER BY neg DESC
""")
neg_rows = cur.fetchall()
metricas_ok_negativo = {'BonoXpor', 'BonoXcant', 'CostoDesv'}
for r in neg_rows:
    if r[0] not in metricas_ok_negativo:
        warn(f"Valores negativos: {r[0]}/{r[1]} → {r[2]:,} filas")
    else:
        print(f"    Negativos esperados: {r[0]}/{r[1]} → {r[2]:,} filas ✓")
if not neg_rows:
    ok("Sin valores negativos inesperados")

# 4c. Valores cero masivos (posible error de conversión)
cur.execute("""
SELECT metrica, entidad,
       COUNT(*) FILTER (WHERE valor_gwh = 0) as ceros,
       COUNT(*) as total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE valor_gwh = 0) / COUNT(*), 1) as pct_cero
FROM metrics
GROUP BY metrica, entidad
HAVING COUNT(*) FILTER (WHERE valor_gwh = 0) > 100
ORDER BY pct_cero DESC
""")
zero_rows = cur.fetchall()
for r in zero_rows:
    if float(r[4]) > 20:
        warn(f"Muchos ceros: {r[0]}/{r[1]} → {r[2]:,}/{r[3]:,} ({r[4]}%) ceros")
    else:
        print(f"    Ceros ({r[4]}%): {r[0]}/{r[1]} → {r[2]:,}/{r[3]:,}")

# 4d. Outliers extremos (> 99.9 percentil muy alejado)
cur.execute("""
SELECT metrica, entidad,
       ROUND(MAX(valor_gwh)::numeric, 2) as max_val,
       ROUND(AVG(valor_gwh)::numeric, 4) as avg_val,
       ROUND(STDDEV(valor_gwh)::numeric, 4) as std_val
FROM metrics
GROUP BY metrica, entidad
ORDER BY (MAX(valor_gwh) / NULLIF(AVG(valor_gwh), 0)) DESC NULLS LAST
LIMIT 20
""")
outlier_rows = cur.fetchall()
print("\n  Top 20 mayor ratio max/avg (posibles outliers):")
for r in outlier_rows:
    ratio = float(r[2]) / float(r[3]) if r[3] and float(r[3]) != 0 else 0
    flag = f" {ROJO}← OUTLIER?{RESET}" if ratio > 100 else ""
    print(f"    {r[0]:25s}/{r[1]:12s}: max={r[2]:>12} avg={r[3]:>12} ratio={ratio:>8.1f}x{flag}")
    if ratio > 100:
        hallazgos.append(('WARN', f"Outlier extremo {r[0]}/{r[1]}: max={r[2]} vs avg={r[3]} ({ratio:.0f}x)"))

# ──────────────────────────────────────────────────────────────────────────────
titulo("5. DUPLICADOS REALES EN metrics (solo_debería haber 1 fila por fecha+metrica+entidad+recurso)")
cur.execute("""
SELECT COUNT(*) FROM (
    SELECT fecha, metrica, entidad, recurso, COUNT(*)
    FROM metrics
    GROUP BY fecha, metrica, entidad, recurso
    HAVING COUNT(*) > 1
) t
""")
dups = cur.fetchone()[0]
if dups > 0:
    error(f"Duplicados en metrics: {dups:,} combinaciones con >1 fila (violación UNIQUE teórica)")
else:
    ok("Sin duplicados en clave fecha+metrica+entidad+recurso")

# ──────────────────────────────────────────────────────────────────────────────
titulo("6. metrics_hourly — INTEGRIDAD")
# 6a. Horas por día (debe ser 24)
cur.execute("""
SELECT metrica, entidad, 
       ROUND(AVG(horas_por_dia)::numeric,1) as avg_h,
       MIN(horas_por_dia) as min_h,
       MAX(horas_por_dia) as max_h
FROM (
    SELECT metrica, entidad, fecha::date,
           COUNT(DISTINCT hora) as horas_por_dia
    FROM metrics_hourly
    GROUP BY metrica, entidad, fecha::date
) t
GROUP BY metrica, entidad
ORDER BY min_h, metrica
""")
hourly_rows = cur.fetchall()
print("\n  Horas/día por métrica (esperado: 24):")
for r in hourly_rows:
    flag = f" {ROJO}← INCOMPLETO{RESET}" if int(r[3]) < 20 else ""
    print(f"    {r[0]:25s}/{r[1]:10s}: avg={r[2]} min={r[3]} max={r[4]}{flag}")
    if int(r[3]) < 20:
        hallazgos.append(('WARN', f"metrics_hourly {r[0]}/{r[1]}: mínimo {r[3]} horas/día"))

# 6b. Cobertura temporal
cur.execute("SELECT metrica, entidad, MIN(fecha::date), MAX(fecha::date) FROM metrics_hourly GROUP BY metrica, entidad ORDER BY metrica, entidad")
print("\n  Cobertura temporal hourly:")
for r in cur.fetchall():
    print(f"    {r[0]:25s}/{r[1]:10s}: {str(r[2])[:10]} → {str(r[3])[:10]}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("7. commercial_metrics — ESTADO")
cur.execute("""
SELECT metrica, COUNT(*) as filas, 
       MIN(fecha::date) as desde, MAX(fecha::date) as hasta,
       COUNT(DISTINCT operador) as operadores
FROM commercial_metrics
GROUP BY metrica
ORDER BY metrica
""")
for r in cur.fetchall():
    print(f"  {r[0]:30s}: {r[1]:>8,} filas | {str(r[2])[:10]}→{str(r[3])[:10]} | {r[4]} operadores")
    if r[3] < date(2026, 1, 1):
        warn(f"commercial_metrics/{r[0]}: última fecha {r[3]} — parece desactualizada")

# ──────────────────────────────────────────────────────────────────────────────
titulo("8. predictions — ESTADO MODELO ML")
cur.execute("""
SELECT metrica, modelo, 
       COUNT(DISTINCT fecha_prediccion::date) as dias_pred,
       MIN(fecha_prediccion::date) as desde,
       MAX(fecha_prediccion::date) as hasta,
       ROUND(AVG(valor_gwh_predicho)::numeric, 2) as avg_pred
FROM predictions
GROUP BY metrica, modelo
ORDER BY metrica, modelo
""")
pred_rows_all = cur.fetchall()
today = date.today()
for r in pred_rows_all:
    print(f"  {r[0]:30s}/{r[1]:20s}: {r[2]:,}d | {str(r[3])[:10]}→{str(r[4])[:10]} | avg={r[5]}")
    if r[4] < today:
        warn(f"predictions/{r[0]}/{r[1]}: no hay predicciones futuras (última: {r[4]})")

# ──────────────────────────────────────────────────────────────────────────────
titulo("9. restriction_metrics + loss_metrics — ESTADO")
for tbl in ['restriction_metrics', 'loss_metrics']:
    try:
        cur.execute(f"SELECT COUNT(*), MIN(fecha::date), MAX(fecha::date), COUNT(DISTINCT COALESCE(metrica,'?')) FROM {tbl}")
        cnt, mn, mx, nm = cur.fetchone()
        print(f"  {tbl:30s}: {cnt:>10,} | {str(mn)[:10]}→{str(mx)[:10]} | {nm} métricas")
        if mx and mx < date(2026, 1, 1):
            warn(f"{tbl}: última fecha {mx}")
    except Exception as e:
        error(f"{tbl}: {e}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("10. lineas_transmision — ESTADO")
cur.execute("""
SELECT COUNT(*), MIN(fecha::date), MAX(fecha::date), 
       COUNT(DISTINCT linea) as lineas, COUNT(DISTINCT tipo_restriccion) as tipos
FROM lineas_transmision
""")
r = cur.fetchone()
print(f"  Total: {r[0]:,} filas | {str(r[1])[:10]}→{str(r[2])[:10]} | {r[3]} líneas | {r[4]} tipos")
if r[2] and r[2] < date(2026, 1, 1):
    warn(f"lineas_transmision: última fecha {r[2]}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("11. catalogos — INTEGRIDAD")
cur.execute("SELECT catalogo, COUNT(*) FROM catalogos GROUP BY catalogo ORDER BY catalogo")
for r in cur.fetchall():
    print(f"  {r[0]:35s}: {r[1]:>6,} entradas")

# ──────────────────────────────────────────────────────────────────────────────
titulo("12. alertas_historial — ESTADO")
cur.execute("""
SELECT tipo_alerta, COUNT(*) as total,
       MIN(fecha_deteccion::date) as desde, MAX(fecha_deteccion::date) as hasta
FROM alertas_historial
GROUP BY tipo_alerta
ORDER BY total DESC
LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]:35s}: {r[1]:>6,} alertas | {str(r[2])[:10]}→{str(r[3])[:10]}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("13. anomalies — ESTADO")
try:
    cur.execute("SELECT metrica, COUNT(*), MIN(fecha::date), MAX(fecha::date) FROM anomalies GROUP BY metrica ORDER BY metrica")
    for r in cur.fetchall():
        print(f"  {r[0]:30s}: {r[1]:,} anomalías | {str(r[2])[:10]}→{str(r[3])[:10]}")
except Exception as e:
    error(f"anomalies: {e}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("14. subsidios_pagos — ESTADO")
try:
    cur.execute("""
    SELECT COUNT(*), MIN(fecha::date), MAX(fecha::date),
           COUNT(DISTINCT empresa) as empresas,
           ROUND(SUM(valor_subsidio)::numeric/1e9, 2) as total_billones
    FROM subsidios_pagos
    """)
    r = cur.fetchone()
    print(f"  Registros: {r[0]:,} | {str(r[1])[:10]}→{str(r[2])[:10]} | {r[3]} empresas | ${r[4]} billones total")
except Exception as e:
    error(f"subsidios_pagos: {e}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("15. cu_daily — ESTADO CU (Costo Unitario)")
try:
    cur.execute("""
    SELECT COUNT(*), MIN(fecha::date), MAX(fecha::date),
           COUNT(DISTINCT operador) as operadores,
           ROUND(AVG(cu_valor)::numeric, 2) as avg_cu
    FROM cu_daily
    """)
    r = cur.fetchone()
    print(f"  Registros: {r[0]:,} | {str(r[1])[:10]}→{str(r[2])[:10]} | {r[3]} operadores | avg CU = {r[4]}")
    if r[2] < date(2026, 1, 1):
        warn(f"cu_daily: última fecha {r[2]} — desactualizado")
except Exception as e:
    error(f"cu_daily: {e}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("16. VERIFICACIÓN ESPECÍFICA backup vs actual (métricas críticas)")
metricas_check = [
    ('Gene', 'Recurso'),
    ('AporEner', 'Rio'),
    ('AporCaudal', 'Rio'),
    ('VoluUtilDiarEner', 'Embalse'),
    ('DemaCome', 'Sistema'),
    ('DemaReal', 'Sistema'),
]
print(f"\n  {'Métrica':25s} {'Entidad':15s} {'f/día 2020':>12} {'f/día 2025':>12} {'f/día 2026':>12}")
print("  " + "-" * 80)
for met, ent in metricas_check:
    vals = {}
    for yr in [2020, 2025, 2026]:
        cur.execute("""
        SELECT ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT fecha::date), 0), 1)
        FROM metrics
        WHERE metrica = %s AND entidad = %s
          AND EXTRACT(YEAR FROM fecha) = %s
        """, (met, ent, yr))
        v = cur.fetchone()[0]
        vals[yr] = float(v) if v else 0
    status = ""
    for yr, fpd in vals.items():
        if fpd > 0 and fpd < 2:
            status = f" {ROJO}← BUG AÚN PRESENTE en {yr}{RESET}"
            hallazgos.append(('ERROR', f"BUG aún presente: {met}/{ent} año {yr} = {fpd} f/d"))
    print(f"  {met:25s} {ent:15s} {vals[2020]:>12.1f} {vals[2025]:>12.1f} {vals[2026]:>12.1f}{status}")

# ──────────────────────────────────────────────────────────────────────────────
titulo("RESUMEN DE HALLAZGOS")
if not hallazgos:
    print(f"  {VERDE}✅ No se encontraron irregularidades graves.{RESET}")
else:
    errores = [h for h in hallazgos if h[0] == 'ERROR']
    warns   = [h for h in hallazgos if h[0] == 'WARN']
    if errores:
        print(f"\n  {ROJO}❌ ERRORES ({len(errores)}):{RESET}")
        for _, msg in errores:
            print(f"     • {msg}")
    if warns:
        print(f"\n  {AMARIL}⚠️  ADVERTENCIAS ({len(warns)}):{RESET}")
        for _, msg in warns:
            print(f"     • {msg}")

conn.close()
print("\nInspección completada:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
