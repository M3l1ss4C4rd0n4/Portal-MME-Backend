#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
  FASE 15 — MULTIVARIATE DISCOVERY: 78+ REGRESORES XM
  Portal Energético MME — Ministerio de Minas y Energía de Colombia
  Fecha: 2026-03-01
═══════════════════════════════════════════════════════════════════════

Objetivo: Descubrir variables explicativas ocultas para las 6 métricas
elite (DEMANDA, Térmica, Solar, Eólica, APORTES, PRECIO_BOLSA)
analizando ~119 métricas disponibles en PostgreSQL.

Análisis:
  1. Discovery dinámico de métricas en BD + catálogo XM
  2. Descarga y alineación de 40+ métricas (6 meses)
  3. Heatmap Pearson/Spearman (40×40)
  4. Partial Correlations (controlando DEMANDA + GENE)
  5. Granger Causality Matrix
  6. Lag Correlation (1-14 días)
  7. PCA + Biplot
  8. VIF Multicolinealidad
  9. Correlation Network (|r|>0.6)
  10. Tabla Final de Regresores Recomendados
"""

# %% [markdown]
# # 🔬 FASE 15 — Multivariate Discovery XM
# ## Descubrimiento de 78+ Regresores Ocultos para Métricas Elite
#
# **Objetivo**: Analizar correlaciones, causalidad y relaciones no lineales
# entre ~119 métricas del sistema eléctrico colombiano para encontrar
# variables predictoras que mejoren los modelos LGBM/RF de FASE 10-14.

# %% ── 1. SETUP & CONEXIÓN ──────────────────────────────────────────

import sys, os, warnings, time
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import psycopg2
from datetime import datetime, timedelta

# Plotly
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.io as pio
pio.templates.default = "plotly_white"

# Stats
from scipy import stats
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
import statsmodels.api as sm
from statsmodels.tsa.stattools import grangercausalitytests
from statsmodels.stats.outliers_influence import variance_inflation_factor

# ML
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# Partial correlations
import pingouin as pg

# Network
import networkx as nx

print("✅ Librerías cargadas")
import plotly
print(f"   Pandas {pd.__version__}, Plotly {plotly.__version__}")
print(f"   Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# Configuración (credenciales desde variables de entorno)
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', '5432')),
    'dbname': os.getenv('POSTGRES_DB', 'portal_energetico'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
}
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs', 'fase15_discovery')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_conn():
    return psycopg2.connect(**DB_CONFIG)

print(f"   Output: {os.path.abspath(OUTPUT_DIR)}")

# %% [markdown]
# ## 2. Discovery Dinámico de Métricas en BD
# Consultamos todas las métricas disponibles en PostgreSQL y las clasificamos
# por entidad, cobertura temporal y cantidad de registros.

# %% ── 2. DISCOVERY DINÁMICO ────────────────────────────────────────

conn = get_conn()

# 2a. Inventario completo de métricas en BD
df_inventario = pd.read_sql_query("""
    SELECT metrica, entidad,
           COUNT(*) as rows,
           MIN(fecha)::date as desde,
           MAX(fecha)::date as hasta,
           EXTRACT(DAY FROM MAX(fecha) - MIN(fecha))::int as dias_span
    FROM metrics
    GROUP BY metrica, entidad
    ORDER BY rows DESC
""", conn)

print(f"📊 INVENTARIO BD:")
print(f"   {len(df_inventario)} combinaciones métrica-entidad")
print(f"   {df_inventario['metrica'].nunique()} métricas únicas")
print(f"   {df_inventario['entidad'].nunique()} entidades únicas")

# 2b. Métricas Sistema (nivel agregado) con cobertura > 6 meses
df_sistema = df_inventario[
    (df_inventario['entidad'] == 'Sistema') &
    (df_inventario['rows'] >= 180)
].sort_values('rows', ascending=False)

print(f"\n📈 Métricas Sistema (≥180 obs): {len(df_sistema)}")
for _, r in df_sistema.iterrows():
    print(f"   {r['metrica']:<25} {r['rows']:>5} rows  {r['desde']} → {r['hasta']}")

# 2c. Métricas por recurso que podemos agregar a nivel sistema
df_recurso_agg = df_inventario[
    (df_inventario['entidad'].isin(['Recurso', 'Embalse', 'Rio'])) &
    (df_inventario['rows'] >= 500)
].sort_values('rows', ascending=False)

print(f"\n🔧 Métricas Recurso/Embalse/Rio agregables: {len(df_recurso_agg)}")

conn.close()

# %% [markdown]
# ## 3. Descarga y Alineación de Métricas
# Descargamos las métricas con suficiente cobertura temporal y las alineamos
# en un DataFrame diario unificado. Incluimos generación por tipo (JOIN catalogos).

# %% ── 3. DESCARGA MASIVA ───────────────────────────────────────────

conn = get_conn()

# ── 3a. Métricas Sistema directas (>= 365 días de datos) ──
METRICAS_SISTEMA = [
    'Gene', 'DemaCome', 'DemaReal', 'AporEner', 'PrecBolsNaci',
    'PrecEsca', 'PrecEscaAct', 'RestAliv', 'RestSinAliv',
    'PerdidasEner', 'PerdidasEnerReg', 'PerdidasEnerNoReg',
    'RespComerAGC', 'DemaRealReg', 'DemaRealNoReg',
    'VoluUtilDiarEner', 'CapaUtilDiarEner', 'PorcVoluUtilDiar',
    'AporEnerMediHist', 'PorcApor',
]

# Fecha de inicio: 6 meses atrás (pero usamos toda la data disponible para robustez)
FECHA_INICIO = '2020-02-06'  # Máximo historial disponible
FECHA_FIN = '2026-02-28'

dfs_sistema = {}
print("📥 Descargando métricas Sistema...")
for m in METRICAS_SISTEMA:
    query = """
    SELECT fecha::date as fecha, valor_gwh as valor
    FROM metrics
    WHERE metrica = %s AND entidad = 'Sistema'
      AND fecha >= %s AND fecha <= %s
    ORDER BY fecha
    """
    df = pd.read_sql_query(query, conn, params=(m, FECHA_INICIO, FECHA_FIN))
    if len(df) > 0:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.drop_duplicates(subset='fecha', keep='last').set_index('fecha')
        dfs_sistema[m] = df['valor']
        print(f"   ✅ {m:<25} {len(df):>5} obs ({df.index.min().date()} → {df.index.max().date()})")
    else:
        print(f"   ❌ {m:<25} sin datos")

# ── 3b. Generación por tipo (JOIN catalogos) ──
TIPOS_GENERACION = {
    'Gene_Termica': 'TERMICA',
    'Gene_Hidraulica': 'HIDRAULICA',
    'Gene_Solar': 'SOLAR',
    'Gene_Eolica': 'EOLICA',
    'Gene_Menores': 'PLANTAS MENORES',
    'Gene_Cogeneracion': 'COGENERACION',
}

print("\n📥 Descargando generación por tipo (JOIN catalogos)...")
for alias, tipo in TIPOS_GENERACION.items():
    query = """
    SELECT m.fecha::date as fecha, SUM(m.valor_gwh) as valor
    FROM metrics m
    INNER JOIN catalogos c ON m.recurso = c.codigo
    WHERE m.metrica = 'Gene'
      AND c.catalogo = 'ListadoRecursos'
      AND c.tipo = %s
      AND m.fecha >= %s AND m.fecha <= %s
      AND m.valor_gwh > 0
    GROUP BY m.fecha
    ORDER BY m.fecha
    """
    df = pd.read_sql_query(query, conn, params=(tipo, FECHA_INICIO, FECHA_FIN))
    if len(df) > 0:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.drop_duplicates(subset='fecha', keep='last').set_index('fecha')
        dfs_sistema[alias] = df['valor']
        print(f"   ✅ {alias:<25} {len(df):>5} obs")
    else:
        print(f"   ❌ {alias:<25} sin datos")

# ── 3c. Disponibilidad declarada por tipo ──
TIPOS_DISPO = {
    'Dispo_Termica': 'TERMICA',
    'Dispo_Hidraulica': 'HIDRAULICA',
    'Dispo_Solar': 'SOLAR',
    'Dispo_Eolica': 'EOLICA',
}

print("\n📥 Descargando disponibilidad declarada por tipo...")
for alias, tipo in TIPOS_DISPO.items():
    query = """
    SELECT m.fecha::date as fecha, SUM(m.valor_gwh) as valor
    FROM metrics m
    INNER JOIN catalogos c ON m.recurso = c.codigo
    WHERE m.metrica = 'DispoDeclarada'
      AND c.catalogo = 'ListadoRecursos'
      AND c.tipo = %s
      AND m.fecha >= %s AND m.fecha <= %s
    GROUP BY m.fecha
    ORDER BY m.fecha
    """
    df = pd.read_sql_query(query, conn, params=(tipo, FECHA_INICIO, FECHA_FIN))
    if len(df) > 0:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.drop_duplicates(subset='fecha', keep='last').set_index('fecha')
        dfs_sistema[alias] = df['valor']
        print(f"   ✅ {alias:<25} {len(df):>5} obs")
    else:
        print(f"   ❌ {alias:<25} sin datos")

# ── 3d. Embalses agregados ──
METRICAS_EMBALSE = {
    'Embalses_VolUtil': ('VoluUtilDiarEner', 'Embalse'),
    'Embalses_Capac': ('CapaUtilDiarEner', 'Embalse'),
    'Embalses_Vertim': ('VertEner', 'Embalse'),
    'Embalses_Turbinado': ('VolTurbMasa', 'Embalse'),
}

print("\n📥 Descargando métricas embalses (agregadas)...")
for alias, (metrica, entidad) in METRICAS_EMBALSE.items():
    query = """
    SELECT fecha::date as fecha, SUM(valor_gwh) as valor
    FROM metrics
    WHERE metrica = %s AND entidad = %s
      AND fecha >= %s AND fecha <= %s
    GROUP BY fecha
    ORDER BY fecha
    """
    df = pd.read_sql_query(query, conn, params=(metrica, entidad, FECHA_INICIO, FECHA_FIN))
    if len(df) > 180:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.drop_duplicates(subset='fecha', keep='last').set_index('fecha')
        dfs_sistema[alias] = df['valor']
        print(f"   ✅ {alias:<25} {len(df):>5} obs")
    else:
        print(f"   ⏭️  {alias:<25} solo {len(df)} obs (skip)")

# ── 3e. Irradiancia y temperatura solar ──
METRICAS_SOLAR = {
    'IrrGlobal_Avg': ('IrrGlobal', 'Recurso'),
    'IrrPanel_Avg': ('IrrPanel', 'Recurso'),
    'TempPanel_Avg': ('TempPanel', 'Recurso'),
    'TempAmbSolar_Avg': ('TempAmbSolar', 'Recurso'),
}

print("\n📥 Descargando métricas solares (promedios por recurso)...")
for alias, (metrica, entidad) in METRICAS_SOLAR.items():
    query = """
    SELECT fecha::date as fecha, AVG(valor_gwh) as valor
    FROM metrics
    WHERE metrica = %s AND entidad = %s
      AND fecha >= %s AND fecha <= %s
    GROUP BY fecha
    ORDER BY fecha
    """
    df = pd.read_sql_query(query, conn, params=(metrica, entidad, FECHA_INICIO, FECHA_FIN))
    if len(df) > 180:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.drop_duplicates(subset='fecha', keep='last').set_index('fecha')
        dfs_sistema[alias] = df['valor']
        print(f"   ✅ {alias:<25} {len(df):>5} obs")
    else:
        print(f"   ⏭️  {alias:<25} solo {len(df)} obs (skip)")

# ── 3f. Emisiones (proxy demanda fósil) ──
print("\n📥 Descargando emisiones (proxy demanda térmica)...")
for met in ['EmisionesCO2', 'EmisionesCO2Eq', 'ConsCombustibleMBTU']:
    query = """
    SELECT fecha::date as fecha, SUM(valor_gwh) as valor
    FROM metrics
    WHERE metrica = %s AND fecha >= %s AND fecha <= %s
    GROUP BY fecha
    ORDER BY fecha
    """
    df = pd.read_sql_query(query, conn, params=(met, FECHA_INICIO, FECHA_FIN))
    if len(df) > 180:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.drop_duplicates(subset='fecha', keep='last').set_index('fecha')
        dfs_sistema[met] = df['valor']
        print(f"   ✅ {met:<25} {len(df):>5} obs")
    else:
        print(f"   ⏭️  {met:<25} solo {len(df)} obs (skip)")

# ── 3g. Aportes por río (top ríos) ──
print("\n📥 Descargando aportes hidrológicos por río (top 5)...")
query_top_rios = """
SELECT recurso, AVG(valor_gwh) as avg_val
FROM metrics
WHERE metrica = 'AporEner' AND entidad = 'Rio'
  AND fecha >= '2025-01-01'
GROUP BY recurso
ORDER BY avg_val DESC
LIMIT 5
"""
top_rios = pd.read_sql_query(query_top_rios, conn)
for _, rio in top_rios.iterrows():
    alias = f"AporRio_{rio['recurso'][:15]}"
    query = """
    SELECT fecha::date as fecha, valor_gwh as valor
    FROM metrics
    WHERE metrica = 'AporEner' AND entidad = 'Rio'
      AND recurso = %s AND fecha >= %s AND fecha <= %s
    ORDER BY fecha
    """
    df = pd.read_sql_query(query, conn, params=(rio['recurso'], FECHA_INICIO, FECHA_FIN))
    if len(df) > 180:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.drop_duplicates(subset='fecha', keep='last').set_index('fecha')
        dfs_sistema[alias] = df['valor']
        print(f"   ✅ {alias:<25} {len(df):>5} obs (μ={rio['avg_val']:.2f})")

conn.close()

# ── 3h. Ensamblar DataFrame unificado ──
print(f"\n🔧 Ensamblando DataFrame unificado...")
df_all = pd.DataFrame(dfs_sistema)

# Rellenar NaN con interpolación lineal (máx 3 días)
df_all = df_all.interpolate(method='linear', limit=3)

# Derivadas calculadas
if 'VoluUtilDiarEner' in df_all.columns and 'CapaUtilDiarEner' in df_all.columns:
    df_all['Embalses_Pct'] = (df_all['VoluUtilDiarEner'] / df_all['CapaUtilDiarEner'] * 100).clip(0, 100)

if 'Gene' in df_all.columns and 'DemaCome' in df_all.columns:
    df_all['Excedente_Gene'] = df_all['Gene'] - df_all['DemaCome']

if 'AporEner' in df_all.columns and 'AporEnerMediHist' in df_all.columns:
    df_all['AporEner_vs_Hist'] = df_all['AporEner'] / df_all['AporEnerMediHist'].replace(0, np.nan)

if 'PrecBolsNaci' in df_all.columns:
    df_all['PrecBolsa_Log'] = np.log1p(df_all['PrecBolsNaci'].clip(lower=0))

# Features temporales
df_all['mes'] = df_all.index.month
df_all['dia_del_anio'] = df_all.index.dayofyear
df_all['dow'] = df_all.index.dayofweek
df_all['es_finde'] = (df_all['dow'] >= 5).astype(int)

print(f"\n📊 DATASET FINAL:")
print(f"   Shape: {df_all.shape[0]} días × {df_all.shape[1]} variables")
print(f"   Rango: {df_all.index.min().date()} → {df_all.index.max().date()}")
print(f"   NaN%: {df_all.isna().mean().mean():.2%}")

# Estadísticas descriptivas
print(f"\n📈 Variables descargadas ({df_all.shape[1]}):")
for col in sorted(df_all.columns):
    n_valid = df_all[col].notna().sum()
    if n_valid > 0:
        print(f"   {col:<30} {n_valid:>5} obs  μ={df_all[col].mean():>10.2f}  σ={df_all[col].std():>10.2f}")

# %% [markdown]
# ## 4. Heatmap de Correlación Pearson / Spearman
# Visualización de la matriz de correlación completa para identificar
# relaciones lineales (Pearson) y monótonas (Spearman).

# %% ── 4. HEATMAPS PEARSON / SPEARMAN ───────────────────────────────

# Eliminar columnas con >50% NaN
valid_cols = df_all.columns[df_all.notna().mean() > 0.5]
df_corr = df_all[valid_cols].dropna()
print(f"📊 Correlaciones: {len(valid_cols)} variables × {len(df_corr)} obs (sin NaN)")

corr_pearson = df_corr.corr(method='pearson')
corr_spearman = df_corr.corr(method='spearman')

# 4a. Heatmap Pearson
fig = make_subplots(rows=1, cols=2,
                    subplot_titles=['Correlación Pearson', 'Correlación Spearman'],
                    horizontal_spacing=0.08)

fig.add_trace(go.Heatmap(
    z=corr_pearson.values,
    x=corr_pearson.columns,
    y=corr_pearson.index,
    colorscale='RdBu_r', zmid=0, zmin=-1, zmax=1,
    text=np.round(corr_pearson.values, 2),
    texttemplate='%{text}',
    textfont={'size': 7},
    showscale=True,
    colorbar=dict(x=0.45, len=0.8),
), row=1, col=1)

fig.add_trace(go.Heatmap(
    z=corr_spearman.values,
    x=corr_spearman.columns,
    y=corr_spearman.index,
    colorscale='RdBu_r', zmid=0, zmin=-1, zmax=1,
    text=np.round(corr_spearman.values, 2),
    texttemplate='%{text}',
    textfont={'size': 7},
    showscale=True,
    colorbar=dict(x=1.02, len=0.8),
), row=1, col=2)

n_vars = len(valid_cols)
fig_h = max(800, n_vars * 22)
fig.update_layout(
    title='FASE 15 — Heatmap Correlación Pearson vs Spearman',
    height=fig_h, width=fig_h * 2 + 200,
    font=dict(size=9),
)

path_heatmap = os.path.join(OUTPUT_DIR, 'heatmap_pearson_spearman.html')
fig.write_html(path_heatmap)
print(f"✅ Heatmap guardado: {path_heatmap}")

# 4b. Top correlaciones con los 6 targets
TARGETS = ['DemaCome', 'Gene_Termica', 'Gene_Solar', 'Gene_Eolica',
           'AporEner', 'PrecBolsNaci']
TARGETS_PRESENT = [t for t in TARGETS if t in corr_pearson.columns]

print(f"\n🎯 TOP CORRELACIONES con los 6 targets élite:")
print(f"{'─'*80}")
for target in TARGETS_PRESENT:
    corrs = corr_pearson[target].drop(target, errors='ignore').abs().sort_values(ascending=False)
    top5 = corrs.head(8)
    print(f"\n  {target}:")
    for var, r in top5.items():
        sign = '+' if corr_pearson.loc[var, target] > 0 else '-'
        spearman_r = corr_spearman.loc[var, target] if var in corr_spearman.index else 0
        print(f"    {sign}{var:<30} Pearson={corr_pearson.loc[var, target]:>+.3f}  Spearman={spearman_r:>+.3f}")

# %% [markdown]
# ## 5. Partial Correlations
# Correlaciones parciales controlando por DEMANDA y GENERACIÓN total,
# revelando relaciones directas sin efectos confundentes del ciclo económico.

# %% ── 5. PARTIAL CORRELATIONS ──────────────────────────────────────

# Covariables a controlar
COVARIABLES = [c for c in ['DemaCome', 'Gene'] if c in df_corr.columns]
print(f"🔬 Partial Correlations controlando: {COVARIABLES}")

partial_results = []
for target in TARGETS_PRESENT:
    predictors = [c for c in df_corr.columns if c != target and c not in COVARIABLES]
    for pred in predictors:
        try:
            cols_needed = [target, pred] + COVARIABLES
            df_sub = df_corr[cols_needed].dropna()
            if len(df_sub) < 50:
                continue
            result = pg.partial_corr(data=df_sub, x=pred, y=target,
                                     covar=COVARIABLES, method='pearson')
            r_val = result['r'].values[0]
            p_val = result['p_val'].values[0]  # pingouin uses p_val (underscore)
            partial_results.append({
                'target': target,
                'predictor': pred,
                'partial_r': r_val,
                'p_value': p_val,
                'abs_partial_r': abs(r_val),
                'n': len(df_sub),
                'significant': p_val < 0.05,
            })
        except Exception:
            pass

df_partial = pd.DataFrame(partial_results)
if len(df_partial) > 0:
    df_partial = df_partial.sort_values('abs_partial_r', ascending=False)

    print(f"\n📊 {len(df_partial)} correlaciones parciales calculadas")
    print(f"   {(df_partial['significant']).sum()} significativas (p<0.05)")

    # Top partial correlations por target
    for target in TARGETS_PRESENT:
        sub = df_partial[df_partial['target'] == target].head(8)
        if len(sub) > 0:
            print(f"\n  🎯 {target} (top partial correlations):")
            for _, row in sub.iterrows():
                sig = '***' if row['p_value'] < 0.001 else '**' if row['p_value'] < 0.01 else '*' if row['p_value'] < 0.05 else ''
                print(f"     {row['predictor']:<30} r={row['partial_r']:>+.3f} {sig:>3} (p={row['p_value']:.4f}, n={row['n']})")

    # Heatmap de partial correlations (top variables)
    top_preds = df_partial.groupby('predictor')['abs_partial_r'].max().nlargest(20).index.tolist()
    pivot = df_partial[df_partial['predictor'].isin(top_preds)].pivot_table(
        index='predictor', columns='target', values='partial_r'
    ).reindex(columns=TARGETS_PRESENT)

    fig_partial = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=pivot.index,
        colorscale='RdBu_r', zmid=0, zmin=-1, zmax=1,
        text=np.round(pivot.values, 3),
        texttemplate='%{text}',
        textfont={'size': 10},
    ))
    fig_partial.update_layout(
        title='FASE 15 — Partial Correlations (controlando DemaCome + Gene)',
        height=max(500, len(top_preds) * 30),
        width=800,
        yaxis_title='Predictor',
        xaxis_title='Target',
    )
    path_partial = os.path.join(OUTPUT_DIR, 'partial_correlations.html')
    fig_partial.write_html(path_partial)
    print(f"\n✅ Partial correlations guardado: {path_partial}")

# %% [markdown]
# ## 6. Granger Causality Matrix
# Test de causalidad de Granger (lags 1-7 días) para detectar relaciones
# temporales predictivas. "X Granger-causa Y" si los lags de X mejoran
# la predicción de Y más allá de la autoregresión.

# %% ── 6. GRANGER CAUSALITY ─────────────────────────────────────────

MAX_LAG_GRANGER = 7
# Variables con suficientes datos para Granger (necesitan ser estacionarias)
granger_vars = [c for c in df_corr.columns
                if df_corr[c].notna().sum() > 365
                and c not in ['mes', 'dia_del_anio', 'dow', 'es_finde']
                and df_corr[c].std() > 0]

# Limitar a las más relevantes (targets + top correlacionadas)
if len(granger_vars) > 25:
    # Priorizar targets y sus top correlaciones
    priority = set(TARGETS_PRESENT)
    for t in TARGETS_PRESENT:
        if t in corr_pearson.columns:
            top_for_t = corr_pearson[t].drop(t, errors='ignore').abs().nlargest(5).index
            priority.update(top_for_t)
    granger_vars = [v for v in granger_vars if v in priority]
    # Añadir hasta 25
    remaining = [v for v in df_corr.columns if v not in granger_vars
                 and v in corr_pearson.columns
                 and v not in ['mes', 'dia_del_anio', 'dow', 'es_finde']
                 and df_corr[v].std() > 0
                 and df_corr[v].notna().sum() > 365]
    granger_vars.extend(remaining[:25 - len(granger_vars)])

print(f"🔬 Granger Causality: {len(granger_vars)} variables × lag 1-{MAX_LAG_GRANGER}")
print(f"   Variables: {granger_vars[:10]}{'...' if len(granger_vars) > 10 else ''}")

granger_matrix = pd.DataFrame(np.nan, index=granger_vars, columns=granger_vars)
granger_pvals = pd.DataFrame(np.nan, index=granger_vars, columns=granger_vars)
granger_best_lag = pd.DataFrame(0, index=granger_vars, columns=granger_vars)

t0_granger = time.time()
n_pairs = 0
n_significant = 0

for cause in granger_vars:
    for effect in granger_vars:
        if cause == effect:
            continue
        try:
            pair_data = df_corr[[effect, cause]].dropna()
            if len(pair_data) < 100:
                continue

            result = grangercausalitytests(pair_data, maxlag=MAX_LAG_GRANGER, verbose=False)

            # Mejor lag (mínimo p-value)
            best_pval = 1.0
            best_lag = 1
            for lag in range(1, MAX_LAG_GRANGER + 1):
                p = result[lag][0]['ssr_ftest'][1]
                if p < best_pval:
                    best_pval = p
                    best_lag = lag

            granger_pvals.loc[cause, effect] = best_pval
            granger_matrix.loc[cause, effect] = -np.log10(max(best_pval, 1e-20))
            granger_best_lag.loc[cause, effect] = best_lag
            n_pairs += 1
            if best_pval < 0.05:
                n_significant += 1

        except Exception:
            pass

elapsed_granger = time.time() - t0_granger
print(f"\n✅ Granger completado: {n_pairs} pares en {elapsed_granger:.1f}s")
print(f"   {n_significant} relaciones significativas (p<0.05)")

# Heatmap Granger
granger_display = granger_matrix.dropna(axis=0, how='all').dropna(axis=1, how='all')
if granger_display.shape[0] > 2:
    fig_granger = go.Figure(go.Heatmap(
        z=granger_display.values,
        x=granger_display.columns,
        y=granger_display.index,
        colorscale='YlOrRd',
        text=np.round(granger_display.values, 1),
        texttemplate='%{text}',
        textfont={'size': 8},
        colorbar=dict(title='-log10(p)'),
    ))
    fig_granger.update_layout(
        title='FASE 15 — Granger Causality Matrix (-log10 p-value, lag 1-7)',
        height=max(600, len(granger_display) * 25),
        width=max(700, len(granger_display) * 25),
        xaxis_title='Effect (Y)',
        yaxis_title='Cause (X → Y)',
        font=dict(size=9),
    )
    path_granger = os.path.join(OUTPUT_DIR, 'granger_causality.html')
    fig_granger.write_html(path_granger)
    print(f"✅ Granger heatmap guardado: {path_granger}")

# Top Granger causal pairs para cada target
print(f"\n🎯 TOP GRANGER CAUSAL PAIRS por target:")
for target in TARGETS_PRESENT:
    if target in granger_pvals.columns:
        col = granger_pvals[target].dropna().sort_values()
        sig = col[col < 0.05]
        if len(sig) > 0:
            print(f"\n  {target}:")
            for cause, pval in sig.head(8).items():
                lag = granger_best_lag.loc[cause, target]
                print(f"    {cause:<30} → {target:<20} p={pval:.6f} (best lag={lag}d)")
        else:
            print(f"\n  {target}: sin relaciones Granger significativas")

# %% [markdown]
# ## 7. Lag Correlation Analysis (1-14 días)
# Correlación cruzada con diferentes lags para encontrar variables con
# poder predictivo retardado. Esencial para modelos de forecasting.

# %% ── 7. LAG CORRELATION ───────────────────────────────────────────

LAG_RANGE = range(1, 15)  # 1-14 días
lag_results = []

# Variables numéricas con suficientes datos
lag_vars = [c for c in df_corr.columns
            if c not in ['mes', 'dia_del_anio', 'dow', 'es_finde']
            and df_corr[c].std() > 0
            and df_corr[c].notna().sum() > 200]

print(f"🔄 Lag Correlation: {len(lag_vars)} variables × {len(TARGETS_PRESENT)} targets × lags 1-14")
t0_lag = time.time()

for target in TARGETS_PRESENT:
    for var in lag_vars:
        if var == target:
            continue
        for lag in LAG_RANGE:
            try:
                shifted = df_corr[var].shift(lag)
                pair = pd.DataFrame({'target': df_corr[target], 'lagged': shifted}).dropna()
                if len(pair) < 50:
                    continue
                r, p = stats.pearsonr(pair['target'], pair['lagged'])
                if abs(r) > 0.1:  # Solo guardar correlaciones relevantes
                    lag_results.append({
                        'target': target,
                        'predictor': var,
                        'lag': lag,
                        'pearson_r': r,
                        'abs_r': abs(r),
                        'p_value': p,
                        'n': len(pair),
                    })
            except Exception:
                pass

df_lag = pd.DataFrame(lag_results)
elapsed_lag = time.time() - t0_lag
print(f"✅ Lag correlations: {len(df_lag)} registros en {elapsed_lag:.1f}s")

if len(df_lag) > 0:
    # Mejor lag por par target-predictor
    best_lags = df_lag.loc[df_lag.groupby(['target', 'predictor'])['abs_r'].idxmax()]
    best_lags = best_lags.sort_values('abs_r', ascending=False)

    # Plotly: subplots por target mostrando lag correlation curves
    fig_lag = make_subplots(
        rows=len(TARGETS_PRESENT), cols=1,
        subplot_titles=[f'Lag Correlations → {t}' for t in TARGETS_PRESENT],
        vertical_spacing=0.05,
    )

    for i, target in enumerate(TARGETS_PRESENT, 1):
        sub = best_lags[best_lags['target'] == target].head(8)
        for _, row in sub.iterrows():
            var = row['predictor']
            # Get all lags for this pair
            pair_lags = df_lag[(df_lag['target'] == target) & (df_lag['predictor'] == var)]
            pair_lags = pair_lags.sort_values('lag')

            fig_lag.add_trace(go.Scatter(
                x=pair_lags['lag'],
                y=pair_lags['pearson_r'],
                mode='lines+markers',
                name=f'{var}',
                text=[f'{var} lag={l}d r={r:.3f}' for l, r in zip(pair_lags['lag'], pair_lags['pearson_r'])],
                showlegend=(i == 1),
            ), row=i, col=1)

        fig_lag.update_yaxes(title_text='Pearson r', row=i, col=1)
        fig_lag.update_xaxes(title_text='Lag (días)', row=i, col=1)

    fig_lag.update_layout(
        title='FASE 15 — Lag Correlation Analysis (1-14 días)',
        height=350 * len(TARGETS_PRESENT),
        width=1200,
        font=dict(size=9),
    )
    path_lag = os.path.join(OUTPUT_DIR, 'lag_correlations.html')
    fig_lag.write_html(path_lag)
    print(f"✅ Lag correlations guardado: {path_lag}")

    # Print top lag correlations
    print(f"\n🎯 BEST LAG CORRELATIONS por target:")
    for target in TARGETS_PRESENT:
        sub = best_lags[best_lags['target'] == target].head(6)
        print(f"\n  {target}:")
        for _, row in sub.iterrows():
            sign = '+' if row['pearson_r'] > 0 else '-'
            print(f"    {sign}{row['predictor']:<30} lag={row['lag']:>2}d  r={row['pearson_r']:>+.3f} (n={row['n']})")

# %% [markdown]
# ## 8. PCA — Análisis de Componentes Principales + Biplot
# Reducción de dimensionalidad para entender la estructura latente del
# sistema eléctrico colombiano. Los loadings revelan qué variables
# contribuyen más a cada componente.

# %% ── 8. PCA + BIPLOT ──────────────────────────────────────────────

# Seleccionar variables numéricas sin temporales
pca_cols = [c for c in df_corr.columns
            if c not in ['mes', 'dia_del_anio', 'dow', 'es_finde']
            and df_corr[c].std() > 0]
df_pca_input = df_corr[pca_cols].dropna()

print(f"🧮 PCA: {df_pca_input.shape[0]} obs × {df_pca_input.shape[1]} variables")

# Standardize
scaler = StandardScaler()
X_scaled = scaler.fit_transform(df_pca_input)

# PCA con todos los componentes
pca = PCA()
X_pca = pca.fit_transform(X_scaled)

# Varianza explicada
var_exp = pca.explained_variance_ratio_
var_cum = np.cumsum(var_exp)

# Determinar n componentes para 90% varianza
n_comp_90 = np.argmax(var_cum >= 0.90) + 1
print(f"   {n_comp_90} componentes explican ≥90% varianza")
print(f"   Top 5 varianza: {', '.join(f'PC{i+1}={v:.1%}' for i, v in enumerate(var_exp[:5]))}")

# 8a. Scree plot
fig_scree = make_subplots(specs=[[{"secondary_y": True}]])
fig_scree.add_trace(go.Bar(
    x=[f'PC{i+1}' for i in range(min(20, len(var_exp)))],
    y=var_exp[:20] * 100,
    name='Varianza Individual (%)',
    marker_color='steelblue',
), secondary_y=False)
fig_scree.add_trace(go.Scatter(
    x=[f'PC{i+1}' for i in range(min(20, len(var_exp)))],
    y=var_cum[:20] * 100,
    name='Varianza Acumulada (%)',
    mode='lines+markers',
    marker_color='firebrick',
), secondary_y=True)
fig_scree.add_hline(y=90, line_dash='dash', line_color='red',
                     annotation_text='90% varianza', secondary_y=True)
fig_scree.update_layout(
    title='FASE 15 — PCA Scree Plot',
    height=500, width=900,
)
fig_scree.update_yaxes(title_text='Varianza Individual (%)', secondary_y=False)
fig_scree.update_yaxes(title_text='Varianza Acumulada (%)', secondary_y=True)

path_scree = os.path.join(OUTPUT_DIR, 'pca_scree.html')
fig_scree.write_html(path_scree)
print(f"✅ Scree plot guardado: {path_scree}")

# 8b. Loadings heatmap (top 5 PCs)
loadings = pd.DataFrame(
    pca.components_[:5].T,
    columns=[f'PC{i+1} ({var_exp[i]:.1%})' for i in range(5)],
    index=pca_cols,
)

# Ordenar por max loading
loadings['max_loading'] = loadings.abs().max(axis=1)
loadings = loadings.sort_values('max_loading', ascending=False)
loadings_display = loadings.drop('max_loading', axis=1)

fig_loadings = go.Figure(go.Heatmap(
    z=loadings_display.values,
    x=loadings_display.columns,
    y=loadings_display.index,
    colorscale='RdBu_r', zmid=0,
    text=np.round(loadings_display.values, 3),
    texttemplate='%{text}',
    textfont={'size': 9},
))
fig_loadings.update_layout(
    title='FASE 15 — PCA Loadings (Top 5 Componentes)',
    height=max(500, len(pca_cols) * 22),
    width=700,
    yaxis_title='Variable',
)
path_loadings = os.path.join(OUTPUT_DIR, 'pca_loadings.html')
fig_loadings.write_html(path_loadings)
print(f"✅ Loadings guardado: {path_loadings}")

# 8c. Biplot (PC1 vs PC2) con vectores de loading
fig_biplot = go.Figure()

# Scatter de observaciones coloreadas por mes
fig_biplot.add_trace(go.Scatter(
    x=X_pca[:, 0], y=X_pca[:, 1],
    mode='markers',
    marker=dict(
        color=df_pca_input.index.month,
        colorscale='Viridis',
        size=3, opacity=0.5,
        colorbar=dict(title='Mes'),
    ),
    name='Observaciones',
    text=[d.strftime('%Y-%m-%d') for d in df_pca_input.index],
))

# Vectores de loading (top 15)
scale = max(abs(X_pca[:, 0].max()), abs(X_pca[:, 1].max())) * 0.8
top_loading_vars = loadings.nlargest(15, 'max_loading' if 'max_loading' in loadings.columns else loadings.columns[0]).index
# reload loadings without max_loading
load_vals = pd.DataFrame(pca.components_[:2].T, columns=['PC1', 'PC2'], index=pca_cols)

for var in top_loading_vars:
    if var in load_vals.index:
        x_end = load_vals.loc[var, 'PC1'] * scale
        y_end = load_vals.loc[var, 'PC2'] * scale
        fig_biplot.add_annotation(
            x=x_end, y=y_end, text=var,
            showarrow=True, arrowhead=2,
            ax=0, ay=0,
            font=dict(size=8),
        )

fig_biplot.update_layout(
    title=f'FASE 15 — PCA Biplot (PC1={var_exp[0]:.1%} vs PC2={var_exp[1]:.1%})',
    xaxis_title=f'PC1 ({var_exp[0]:.1%})',
    yaxis_title=f'PC2 ({var_exp[1]:.1%})',
    height=700, width=900,
)
path_biplot = os.path.join(OUTPUT_DIR, 'pca_biplot.html')
fig_biplot.write_html(path_biplot)
print(f"✅ Biplot guardado: {path_biplot}")

# Print PC1-PC3 loadings
print(f"\n📊 TOP LOADINGS POR COMPONENTE:")
for i in range(min(3, len(pca.components_))):
    pc_load = pd.Series(pca.components_[i], index=pca_cols).abs().nlargest(5)
    print(f"  PC{i+1} ({var_exp[i]:.1%}): {', '.join(f'{v}({pc_load[v]:.3f})' for v in pc_load.index)}")

# %% [markdown]
# ## 9. VIF — Multicolinealidad
# Variance Inflation Factor para detectar predictores redundantes.
# VIF > 10 indica multicolinealidad severa (una variable es casi
# combinación lineal de otras).

# %% ── 9. VIF MULTICOLINEALIDAD ─────────────────────────────────────

# Variables numéricas sin temporales y sin NaN
vif_cols = [c for c in pca_cols if c in df_corr.columns and df_corr[c].std() > 0]
df_vif = df_corr[vif_cols].dropna()

# Si hay muchas variables, seleccionar las más relevantes
if len(vif_cols) > 30:
    # Priorizar targets + top correlacionadas
    vif_priority = set(TARGETS_PRESENT)
    for t in TARGETS_PRESENT:
        if t in corr_pearson.columns:
            vif_priority.update(corr_pearson[t].drop(t, errors='ignore').abs().nlargest(5).index)
    vif_cols = [c for c in vif_cols if c in vif_priority]
    df_vif = df_corr[vif_cols].dropna()

print(f"📊 VIF: {len(vif_cols)} variables × {len(df_vif)} obs")

X_vif = sm.add_constant(df_vif)
vif_data = []
for i, col in enumerate(X_vif.columns):
    if col == 'const':
        continue
    try:
        vif = variance_inflation_factor(X_vif.values, i)
        vif_data.append({'variable': col, 'VIF': vif})
    except Exception:
        vif_data.append({'variable': col, 'VIF': np.nan})

df_vif_result = pd.DataFrame(vif_data).sort_values('VIF', ascending=False)
df_vif_result['multicollinear'] = df_vif_result['VIF'] > 10

print(f"\n🔴 Variables con VIF > 10 (multicolinealidad severa):")
severe = df_vif_result[df_vif_result['VIF'] > 10]
for _, row in severe.iterrows():
    print(f"   {row['variable']:<30} VIF = {row['VIF']:>10.1f}")

print(f"\n🟡 Variables con 5 < VIF ≤ 10 (moderada):")
moderate = df_vif_result[(df_vif_result['VIF'] > 5) & (df_vif_result['VIF'] <= 10)]
for _, row in moderate.iterrows():
    print(f"   {row['variable']:<30} VIF = {row['VIF']:>10.1f}")

print(f"\n🟢 Variables con VIF ≤ 5 (OK):")
ok = df_vif_result[df_vif_result['VIF'] <= 5]
for _, row in ok.iterrows():
    print(f"   {row['variable']:<30} VIF = {row['VIF']:>10.1f}")

# VIF bar chart
fig_vif = go.Figure()
colors = ['red' if v > 10 else 'orange' if v > 5 else 'green'
          for v in df_vif_result['VIF'].fillna(0)]
fig_vif.add_trace(go.Bar(
    x=df_vif_result['variable'],
    y=df_vif_result['VIF'],
    marker_color=colors,
    text=df_vif_result['VIF'].round(1),
    textposition='auto',
))
fig_vif.add_hline(y=10, line_dash='dash', line_color='red',
                  annotation_text='VIF=10 (severa)')
fig_vif.add_hline(y=5, line_dash='dash', line_color='orange',
                  annotation_text='VIF=5 (moderada)')
fig_vif.update_layout(
    title='FASE 15 — Variance Inflation Factor (Multicolinealidad)',
    height=500, width=max(800, len(df_vif_result) * 35),
    yaxis_title='VIF',
    xaxis_tickangle=-45,
)
path_vif = os.path.join(OUTPUT_DIR, 'vif_multicollinearity.html')
fig_vif.write_html(path_vif)
print(f"\n✅ VIF chart guardado: {path_vif}")

# %% [markdown]
# ## 10. Correlation Network
# Red de correlaciones donde los nodos son variables y las aristas
# representan correlaciones fuertes (|r| > 0.6). Permite visualizar
# clusters de variables co-dependientes.

# %% ── 10. CORRELATION NETWORK ──────────────────────────────────────

CORR_THRESHOLD = 0.6

# Crear grafo
G = nx.Graph()
for i in range(len(corr_pearson.columns)):
    for j in range(i + 1, len(corr_pearson.columns)):
        r = corr_pearson.iloc[i, j]
        if abs(r) > CORR_THRESHOLD:
            G.add_edge(
                corr_pearson.columns[i],
                corr_pearson.columns[j],
                weight=abs(r),
                sign='+' if r > 0 else '-',
                r_value=r,
            )

# Solo nodos con aristas
if len(G.nodes) > 0:
    print(f"🕸️  Correlation Network (|r| > {CORR_THRESHOLD}):")
    print(f"   {len(G.nodes)} nodos, {len(G.edges)} aristas")

    # Layout
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    # Degree centrality
    centrality = nx.degree_centrality(G)
    top_central = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]
    print(f"\n   Top nodos centrales:")
    for node, cent in top_central:
        print(f"     {node:<30} centrality={cent:.3f} (grado={G.degree(node)})")

    # Community detection (via clustering coefficient)
    communities = list(nx.community.greedy_modularity_communities(G))
    print(f"\n   {len(communities)} comunidades detectadas:")
    for i, comm in enumerate(communities[:6]):
        print(f"     C{i+1}: {', '.join(sorted(comm)[:5])}{'...' if len(comm) > 5 else ''}")

    # Plotly network
    edge_x, edge_y = [], []
    edge_colors = []
    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        edge_colors.append('steelblue' if data['sign'] == '+' else 'firebrick')

    # Asignar colores por comunidad
    node_community = {}
    for i, comm in enumerate(communities):
        for node in comm:
            node_community[node] = i

    community_colors = px.colors.qualitative.Set3
    node_colors = [community_colors[node_community.get(n, 0) % len(community_colors)]
                   for n in G.nodes]

    fig_net = go.Figure()

    # Edges
    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        color = 'rgba(70,130,180,0.4)' if data['sign'] == '+' else 'rgba(178,34,34,0.4)'
        width = abs(data['r_value']) * 3
        fig_net.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1],
            mode='lines',
            line=dict(color=color, width=width),
            hoverinfo='text',
            text=f"{u} ↔ {v}: r={data['r_value']:.3f}",
            showlegend=False,
        ))

    # Nodes
    node_x = [pos[n][0] for n in G.nodes]
    node_y = [pos[n][1] for n in G.nodes]
    node_size = [max(15, G.degree(n) * 5) for n in G.nodes]
    node_text = [f"{n}\nGrado: {G.degree(n)}\nCentralidad: {centrality[n]:.3f}"
                 for n in G.nodes]

    fig_net.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        marker=dict(size=node_size, color=node_colors,
                    line=dict(width=1, color='gray')),
        text=list(G.nodes),
        textposition='top center',
        textfont=dict(size=8),
        hovertext=node_text,
        hoverinfo='text',
        showlegend=False,
    ))

    fig_net.update_layout(
        title=f'FASE 15 — Correlation Network (|r| > {CORR_THRESHOLD}, {len(G.edges)} edges)',
        height=800, width=1000,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        annotations=[
            dict(text='🔵 Correlación positiva  🔴 Correlación negativa',
                 x=0.5, y=-0.05, xref='paper', yref='paper',
                 showarrow=False, font=dict(size=11)),
        ],
    )

    path_network = os.path.join(OUTPUT_DIR, 'correlation_network.html')
    fig_net.write_html(path_network)
    print(f"\n✅ Network guardado: {path_network}")

else:
    print(f"⚠️  No hay correlaciones > {CORR_THRESHOLD}")

# %% [markdown]
# ## 11. Tabla Final — Regresores Recomendados
# Síntesis de todos los análisis para generar recomendaciones concretas
# de nuevos regresores para cada métrica elite.

# %% ── 11. TABLA RECOMENDACIONES ─────────────────────────────────────

print(f"\n{'='*90}")
print(f"📋 FASE 15 — TABLA FINAL DE REGRESORES RECOMENDADOS")
print(f"{'='*90}")

recommendations = []

for target in TARGETS_PRESENT:
    # Recopilar evidencia de cada análisis
    candidates = {}

    # 11a. Pearson correlation
    if target in corr_pearson.columns:
        for var in corr_pearson.columns:
            if var == target or var in ['mes', 'dia_del_anio', 'dow', 'es_finde']:
                continue
            r_val = corr_pearson.loc[var, target]
            if abs(r_val) > 0.3:
                if var not in candidates:
                    candidates[var] = {'pearson_r': 0, 'spearman_r': 0,
                                       'partial_r': 0, 'granger_p': 1.0,
                                       'best_lag': 0, 'lag_r': 0, 'vif': 0,
                                       'scores': 0}
                candidates[var]['pearson_r'] = r_val
                candidates[var]['scores'] += 1

    # 11b. Spearman
    if target in corr_spearman.columns:
        for var in corr_spearman.columns:
            if var == target:
                continue
            r_val = corr_spearman.loc[var, target]
            if abs(r_val) > 0.3 and var in candidates:
                candidates[var]['spearman_r'] = r_val
                candidates[var]['scores'] += 1

    # 11c. Partial correlations
    if len(df_partial) > 0:
        sub = df_partial[df_partial['target'] == target]
        for _, row in sub.iterrows():
            var = row['predictor']
            if abs(row['partial_r']) > 0.15 and row['significant']:
                if var not in candidates:
                    candidates[var] = {'pearson_r': 0, 'spearman_r': 0,
                                       'partial_r': 0, 'granger_p': 1.0,
                                       'best_lag': 0, 'lag_r': 0, 'vif': 0,
                                       'scores': 0}
                candidates[var]['partial_r'] = row['partial_r']
                candidates[var]['scores'] += 1

    # 11d. Granger causality
    if target in granger_pvals.columns:
        for cause in granger_pvals.index:
            pval = granger_pvals.loc[cause, target]
            if pd.notna(pval) and pval < 0.05:
                if cause in candidates:
                    candidates[cause]['granger_p'] = pval
                    candidates[cause]['scores'] += 1
                elif pval < 0.01:  # Very significant Granger even without linear corr
                    candidates[cause] = {'pearson_r': 0, 'spearman_r': 0,
                                         'partial_r': 0, 'granger_p': pval,
                                         'best_lag': granger_best_lag.loc[cause, target],
                                         'lag_r': 0, 'vif': 0, 'scores': 1}

    # 11e. Lag correlations
    if len(df_lag) > 0:
        sub_lag = df_lag[df_lag['target'] == target]
        best = sub_lag.loc[sub_lag.groupby('predictor')['abs_r'].idxmax()] if len(sub_lag) > 0 else pd.DataFrame()
        for _, row in best.iterrows():
            var = row['predictor']
            if abs(row['pearson_r']) > 0.3 and var in candidates:
                candidates[var]['best_lag'] = row['lag']
                candidates[var]['lag_r'] = row['pearson_r']
                candidates[var]['scores'] += 1

    # 11f. VIF
    for _, row in df_vif_result.iterrows():
        if row['variable'] in candidates:
            candidates[row['variable']]['vif'] = row['VIF']

    # Generar recomendación
    for var, info in candidates.items():
        score = info['scores']
        # Composite score (0-100)
        composite = (
            min(abs(info['pearson_r']) * 25, 25) +        # max 25
            min(abs(info['partial_r']) * 40, 25) +         # max 25
            (25 if info['granger_p'] < 0.01 else 15 if info['granger_p'] < 0.05 else 0) +  # max 25
            min(abs(info['lag_r']) * 25, 25)                # max 25
        )

        # Penalizar VIF alto
        if info['vif'] > 10:
            composite *= 0.7
        elif info['vif'] > 5:
            composite *= 0.85

        # Clasificar
        if composite >= 50:
            recom = '🟢 ALTO'
        elif composite >= 30:
            recom = '🟡 MEDIO'
        elif composite >= 15:
            recom = '🔵 BAJO'
        else:
            recom = '⚪ SKIP'

        recommendations.append({
            'target': target,
            'variable': var,
            'pearson_r': info['pearson_r'],
            'partial_r': info['partial_r'],
            'granger_p': info['granger_p'],
            'best_lag': info['best_lag'],
            'lag_r': info['lag_r'],
            'vif': info['vif'],
            'composite_score': composite,
            'evidences': score,
            'recommendation': recom,
        })

df_recom = pd.DataFrame(recommendations).sort_values(['target', 'composite_score'],
                                                       ascending=[True, False])

# Print por target
for target in TARGETS_PRESENT:
    sub = df_recom[df_recom['target'] == target]
    alto = sub[sub['recommendation'].str.contains('ALTO')]
    medio = sub[sub['recommendation'].str.contains('MEDIO')]
    bajo = sub[sub['recommendation'].str.contains('BAJO')]

    print(f"\n{'─'*90}")
    print(f"  🎯 TARGET: {target}")
    print(f"{'─'*90}")
    print(f"  {'Variable':<28} {'Pearson':>8} {'Partial':>8} {'Granger':>8} {'Lag':>5} {'LagR':>7} {'VIF':>6} {'Score':>6} {'Recom':>8}")
    print(f"  {'─'*28} {'─'*8} {'─'*8} {'─'*8} {'─'*5} {'─'*7} {'─'*6} {'─'*6} {'─'*8}")

    for _, row in sub.head(15).iterrows():
        granger_str = f"{row['granger_p']:.4f}" if row['granger_p'] < 1 else "  N/A"
        vif_str = f"{row['vif']:.1f}" if row['vif'] > 0 else "  N/A"
        lag_str = f"{int(row['best_lag'])}d" if row['best_lag'] > 0 else " N/A"
        print(f"  {row['variable']:<28} {row['pearson_r']:>+7.3f} {row['partial_r']:>+7.3f} "
              f"{granger_str:>8} {lag_str:>5} {row['lag_r']:>+6.3f} {vif_str:>6} "
              f"{row['composite_score']:>5.1f} {row['recommendation']:>8}")

    print(f"\n  Resumen: 🟢 {len(alto)} ALTO | 🟡 {len(medio)} MEDIO | 🔵 {len(bajo)} BAJO")

# %% ── 12. RESUMEN EJECUTIVO Y OUTPUTS ──────────────────────────────

# Guardar tabla completa como CSV
path_csv = os.path.join(OUTPUT_DIR, 'regresores_recomendados.csv')
df_recom.to_csv(path_csv, index=False)

# Heatmap resumen de composite scores
pivot_scores = df_recom.pivot_table(
    index='variable', columns='target', values='composite_score'
).fillna(0)

# Top 25 variables por score máximo
top_vars = pivot_scores.max(axis=1).nlargest(25).index
pivot_top = pivot_scores.loc[top_vars].reindex(columns=TARGETS_PRESENT)

fig_recom = go.Figure(go.Heatmap(
    z=pivot_top.values,
    x=pivot_top.columns,
    y=pivot_top.index,
    colorscale='YlGnBu',
    text=np.round(pivot_top.values, 1),
    texttemplate='%{text}',
    textfont={'size': 9},
    colorbar=dict(title='Score'),
))
fig_recom.update_layout(
    title='FASE 15 — Composite Regressor Scores (Top 25 Variables)',
    height=max(500, len(top_vars) * 25),
    width=800,
    yaxis_title='Variable Candidata',
    xaxis_title='Target Métrica',
)
path_recom = os.path.join(OUTPUT_DIR, 'regressor_scores_heatmap.html')
fig_recom.write_html(path_recom)

# Resumen final
print(f"\n{'='*90}")
print(f"📊 FASE 15 — RESUMEN EJECUTIVO")
print(f"{'='*90}")
print(f"\n  Variables analizadas: {df_all.shape[1]}")
print(f"  Correlaciones parciales: {len(df_partial)}")
print(f"  Pares Granger significativos: {n_significant}")
print(f"  Regresores recomendados:")

alto_total = df_recom[df_recom['recommendation'].str.contains('ALTO')]
medio_total = df_recom[df_recom['recommendation'].str.contains('MEDIO')]
print(f"    🟢 ALTO impacto: {len(alto_total)}")
print(f"    🟡 MEDIO impacto: {len(medio_total)}")
print(f"\n  NUEVOS REGRESORES DESCUBIERTOS (no usados actualmente):")

# Regresores ya usados en producción (de FASE 10-14)
REGRESORES_ACTUALES = {
    'DemaCome': {'embalses_pct', 'mes', 'dia_del_anio', 'es_festivo', 'dow'},
    'Gene_Termica': {'embalses_pct', 'demanda_gwh', 'aportes_gwh'},
    'Gene_Solar': {'embalses_pct', 'demanda_gwh', 'irradiancia_global', 'temp_ambiente_solar', 'dispo_declarada_solar'},
    'Gene_Eolica': {'embalses_pct', 'demanda_gwh', 'aportes_gwh', 'dispo_declarada_eolica'},
    'AporEner': {'embalses_pct', 'demanda_gwh'},
    'PrecBolsNaci': {'embalses_pct', 'demanda_gwh', 'aportes_gwh'},
}

for target in TARGETS_PRESENT:
    actuales = REGRESORES_ACTUALES.get(target, set())
    nuevos = alto_total[alto_total['target'] == target]
    nuevos = nuevos[~nuevos['variable'].str.lower().isin([a.lower() for a in actuales])]
    if len(nuevos) > 0:
        print(f"\n  {target}:")
        for _, row in nuevos.head(5).iterrows():
            print(f"    → {row['variable']:<28} score={row['composite_score']:.1f} "
                  f"(r={row['pearson_r']:+.3f}, partial={row['partial_r']:+.3f})")

# Outputs generados
print(f"\n📁 OUTPUTS GENERADOS (logs/fase15_discovery/):")
outputs = [
    'heatmap_pearson_spearman.html',
    'partial_correlations.html',
    'granger_causality.html',
    'lag_correlations.html',
    'pca_scree.html',
    'pca_loadings.html',
    'pca_biplot.html',
    'vif_multicollinearity.html',
    'correlation_network.html',
    'regressor_scores_heatmap.html',
    'regresores_recomendados.csv',
]
for o in outputs:
    path = os.path.join(OUTPUT_DIR, o)
    exists = '✅' if os.path.exists(path) else '❌'
    print(f"   {exists} {o}")

print(f"\n🏁 FASE 15 Discovery completada. Total: {len(df_recom)} regresores evaluados.")
