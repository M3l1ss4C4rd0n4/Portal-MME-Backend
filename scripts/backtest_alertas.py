"""
Backtest histórico del modelo de alertas energéticas (estado diario SIN).

Calcula el estado diario del SIN (NORMAL/ALERTA/CRÍTICO) usando los mismos
umbrales de producción (alertas_energeticas.py), aplicando rolling-3d sobre
estrés térmico y ratio de precio, con la regla de 2+ alertas simultáneas o
1 alerta persistente ≥ 3 días.

Crea/actualiza la tabla sector_energetico.estado_sin_diario.

Uso:
    python -m scripts.backtest_alertas                      # 2025 completo
    python -m scripts.backtest_alertas --inicio 2023-01-01 --fin 2025-12-31
    python -m scripts.backtest_alertas --no-bd              # solo consola
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from typing import Optional

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Umbrales centralizados (fuente única de verdad) ────────────────────────────
from scripts.alertas_energeticas import (
    UMBRALES,
    _UMBRALES_APORTES_ESTACIONAL,
    _get_umbral_aportes,
)

# ── Período por defecto ────────────────────────────────────────────────────────
DEFAULT_INICIO = "2025-01-01"
DEFAULT_FIN = "2025-12-31"

# ── DDL tabla ──────────────────────────────────────────────────────────────────
_DDL = """
CREATE TABLE IF NOT EXISTS sector_energetico.estado_sin_diario (
    fecha                  DATE PRIMARY KEY,
    estado_global          TEXT NOT NULL
                               CHECK (estado_global IN ('NORMAL','ALERTA','CRÍTICO')),
    n_criticos             SMALLINT,
    n_alertas              SMALLINT,
    -- métricas base
    gene_gwh               NUMERIC(10, 3),   -- Gene Sistema (~demanda real)
    termica_gwh            NUMERIC(10, 3),
    aportes_gwh            NUMERIC(10, 3),
    embalse_pct            NUMERIC(6, 2),    -- PorcVoluUtilDiar × 100
    precio_bolsa           NUMERIC(10, 2),
    precio_escasez         NUMERIC(10, 2),
    -- métricas derivadas (suavizadas mv3)
    estres_termico_pct     NUMERIC(6, 2),    -- térmica/gene×100, rolling-3d
    price_ratio            NUMERIC(6, 4),    -- bolsa/escasez, rolling-3d
    -- flags individuales
    flag_embalse_critico   BOOLEAN,
    flag_embalse_alerta    BOOLEAN,
    flag_termico_critico   BOOLEAN,
    flag_termico_alerta    BOOLEAN,
    flag_precio_critico    BOOLEAN,
    flag_precio_alerta     BOOLEAN,
    flag_aportes_critico   BOOLEAN,
    flag_aportes_alerta    BOOLEAN,
    -- metadato
    created_at             TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE sector_energetico.estado_sin_diario IS
    'Estado global diario del SIN. Generado por backtest_alertas.py '
    'con datos reales XM (sector_energetico.metrics).';
"""


# ─────────────────────────────────────────────────────────────────────────────
# Conexión
# ─────────────────────────────────────────────────────────────────────────────

def _get_conn():
    from core.config import settings
    params: dict = dict(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
    )
    if settings.POSTGRES_PASSWORD:
        params["password"] = settings.POSTGRES_PASSWORD
    import psycopg2
    return psycopg2.connect(**params)


# ─────────────────────────────────────────────────────────────────────────────
# Carga de datos
# ─────────────────────────────────────────────────────────────────────────────

def _cargar_metricas_base(conn, inicio: str, fin: str) -> pd.DataFrame:
    """Carga métricas diarias del recurso 'Sistema' para el período dado."""
    q = """
        SELECT fecha::date AS fecha,
               metrica,
               AVG(valor_gwh) AS valor_gwh
        FROM sector_energetico.metrics
        WHERE recurso = 'Sistema'
          AND metrica IN ('Gene', 'AporEner',
                          'PorcVoluUtilDiar', 'PrecBolsNaci', 'PrecEsca')
          AND fecha::date BETWEEN %(inicio)s AND %(fin)s
        GROUP BY fecha::date, metrica
        ORDER BY fecha::date
    """
    df = pd.read_sql_query(q, conn, params={"inicio": inicio, "fin": fin})
    if df.empty:
        raise RuntimeError(f"Sin datos en sector_energetico.metrics para {inicio}–{fin}")

    pivot = df.pivot_table(
        index="fecha", columns="metrica", values="valor_gwh", aggfunc="mean"
    )
    pivot.columns.name = None
    pivot = pivot.rename(
        columns={
            "Gene": "gene_gwh",
            "AporEner": "aportes_gwh",
            "PorcVoluUtilDiar": "embalse_frac",
            "PrecBolsNaci": "precio_bolsa",
            "PrecEsca": "precio_escasez",
        }
    )
    pivot.index = pd.to_datetime(pivot.index)
    return pivot


def _cargar_termica(conn, inicio: str, fin: str) -> pd.Series:
    """Generación térmica diaria (SUM Gene de recursos tipo TERMICA)."""
    q = """
        SELECT m.fecha::date AS fecha,
               SUM(m.valor_gwh) AS termica_gwh
        FROM sector_energetico.metrics m
        JOIN sector_energetico.catalogos c
             ON m.recurso = c.codigo
            AND c.catalogo = 'ListadoRecursos'
        WHERE m.metrica = 'Gene'
          AND c.tipo = 'TERMICA'
          AND m.fecha::date BETWEEN %(inicio)s AND %(fin)s
        GROUP BY m.fecha::date
        ORDER BY m.fecha::date
    """
    df = pd.read_sql_query(q, conn, params={"inicio": inicio, "fin": fin})
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df.set_index("fecha")["termica_gwh"]


# ─────────────────────────────────────────────────────────────────────────────
# Métricas derivadas
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_derivadas(df: pd.DataFrame, termica: pd.Series) -> pd.DataFrame:
    """Añade métricas derivadas con rolling-3d (igual que producción)."""
    df = df.copy()
    df["termica_gwh"] = termica

    # Embalses en % (de fracción a porcentaje)
    df["embalse_pct"] = df["embalse_frac"] * 100.0

    # Estrés térmico crudo + rolling-3d
    df["_estres_raw"] = (df["termica_gwh"] / df["gene_gwh"].replace(0, np.nan)) * 100.0
    df["estres_termico_mv3"] = df["_estres_raw"].rolling(3, min_periods=1).mean()

    # Ratio precio + rolling-3d
    df["_ratio_raw"] = df["precio_bolsa"] / df["precio_escasez"].replace(0, np.nan)
    df["price_ratio_mv3"] = df["_ratio_raw"].rolling(3, min_periods=1).mean()

    df["mes"] = df.index.month
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Flags diarios (umbrales)
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_flags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Embalses
    emb_c = UMBRALES["EMBALSES_PCT"]["CRITICO"]   # 30 %
    emb_a = UMBRALES["EMBALSES_PCT"]["ALERTA"]    # 40 %
    df["flag_embalse_critico"] = df["embalse_pct"] < emb_c
    df["flag_embalse_alerta"] = (df["embalse_pct"] >= emb_c) & (df["embalse_pct"] < emb_a)

    # Estrés térmico (rolling-3d)
    ter_c = UMBRALES["ESTRES_TERMICO"]["CRITICO"]   # 35 %
    ter_a = UMBRALES["ESTRES_TERMICO"]["ALERTA"]    # 20 %
    df["flag_termico_critico"] = df["estres_termico_mv3"] > ter_c
    df["flag_termico_alerta"] = (df["estres_termico_mv3"] > ter_a) & ~df["flag_termico_critico"]

    # Precio bolsa (rolling-3d)
    pr_c = UMBRALES["PRECIO_BOLSA"]["CRITICO_RATIO"]   # 0.90
    pr_a = UMBRALES["PRECIO_BOLSA"]["ALERTA_RATIO"]    # 0.65
    df["flag_precio_critico"] = df["price_ratio_mv3"] >= pr_c
    df["flag_precio_alerta"] = (df["price_ratio_mv3"] >= pr_a) & ~df["flag_precio_critico"]

    # Aportes hídricos — regla de fracción rolling-30d (igual que producción)
    # producción: dias_criticos/horizonte >= DIAS_CRITICO_PCT (0.60) → CRÍTICO
    #             dias_alerta  /horizonte >= DIAS_ALERTA_PCT  (0.50) → ALERTA
    _umb_crit = df["mes"].map(
        lambda m: _UMBRALES_APORTES_ESTACIONAL.get(m, (300, 400))[0]
    )
    _umb_alrt = df["mes"].map(
        lambda m: _UMBRALES_APORTES_ESTACIONAL.get(m, (300, 400))[1]
    )
    _below_crit = (df["aportes_gwh"] < _umb_crit).astype(float)
    _below_alrt = (df["aportes_gwh"] < _umb_alrt).astype(float)  # includes < p5

    _dias_crit_pct = UMBRALES["APORTES_HIDRICOS"]["DIAS_CRITICO_PCT"]  # 0.60
    _dias_alrt_pct = UMBRALES["APORTES_HIDRICOS"]["DIAS_ALERTA_PCT"]   # 0.50

    # Rolling 30 días (min 7 para no descartrar el inicio de la serie)
    _frac_crit_30d = _below_crit.rolling(30, min_periods=7).mean()
    _frac_alrt_30d = _below_alrt.rolling(30, min_periods=7).mean()

    df["flag_aportes_critico"] = _frac_crit_30d >= _dias_crit_pct
    df["flag_aportes_alerta"] = (
        (_frac_alrt_30d >= _dias_alrt_pct) & ~df["flag_aportes_critico"]
    )

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Clasificación estado global
# ─────────────────────────────────────────────────────────────────────────────

def _clasificar_estado(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica las reglas CND/XM para determinar el estado global diario.

    Reglas (espejo exacto de _determinar_estado_general en producción):
      CRÍTICO : ≥ 2 señales críticas simultáneas.
                O bien 1 señal crítica sostenida ≥ 14 días consecutivos
                + ≥ 1 señal de alerta adicional (exige coincidencia).
      ALERTA  : ≥ 2 señales de alerta simultáneas.
                O bien 1 señal crítica aislada (sin señal de apoyo).
                O bien 1 alerta persistente ≥ 3 días.
      NORMAL  : en otro caso.
    """
    df = df.copy()

    df["n_criticos"] = (
        df["flag_embalse_critico"].astype(int)
        + df["flag_termico_critico"].astype(int)
        + df["flag_precio_critico"].astype(int)
        + df["flag_aportes_critico"].astype(int)
    )
    df["n_alertas"] = (
        df["flag_embalse_alerta"].astype(int)
        + df["flag_termico_alerta"].astype(int)
        + df["flag_precio_alerta"].astype(int)
        + df["flag_aportes_alerta"].astype(int)
    )

    # ── Guarda de embalse (proxy stock) ──────────────────────────────────────
    # Si embalse_pct ≥ 60%, el sistema tiene buffer operacional:
    # señales de flujo (aportes) + precio no constituyen CRÍTICO por sí solas.
    # XM no declararía riesgo estructural con tanques a >60 % de capacidad útil.
    _embalse_presion = df["embalse_pct"] < 60.0

    # ── Crisis operacional (independiente del stock, pero embalse no debe estar sano) ───
    # Térmica CRÍTICO + Precio CRÍTICO simultáneos = despacho forzado bajo
    # precio de escasez → riesgo real. Sin embargo, si embalse ≥ 70% los tanques
    # todavía tienen buffer suficiente → es vigilancia, no crisis.
    _crisis_operacional = (
        df["flag_termico_critico"] & df["flag_precio_critico"]
        & (df["embalse_pct"] < 70.0)
    )

    # ── Persistencia de ≥ 1 señal crítica sostenida 14 días ─────────────────
    _crit_sostenida_14d = (
        (df["n_criticos"] >= 1).astype(int)
        .rolling(14, min_periods=14).sum() >= 14
    )

    # ── Persistencia ALERTA: 1 alerta ≥ 3 días consecutivos ──────────────
    _any_alerta = (df["n_alertas"] >= 1).astype(int)
    _alerta_persistente = _any_alerta.rolling(3, min_periods=3).sum() >= 3

    # ── Clasificar (prioridad descendente) ────────────────────────────────
    condiciones = [
        # CRÍTICO A: múltiples señales críticas + embalse comprometido
        (df["n_criticos"] >= 2) & _embalse_presion,
        # CRÍTICO B: crisis operacional (térmica+precio) independiente de embalse
        _crisis_operacional,
        # CRÍTICO C: señal crítica sostenida ≥14d + alerta + embalse bajo
        _crit_sostenida_14d & (df["n_alertas"] >= 1) & _embalse_presion,
        # ALERTA: ≥ 1 señal crítica sin respaldo de embalse bajos
        df["n_criticos"] >= 1,
        # ALERTA: ≥ 2 señales de alerta simultáneas
        df["n_alertas"] >= 2,
        # ALERTA: 1 alerta persistente ≥ 3 días
        _alerta_persistente,
    ]
    valores = ["CRÍTICO", "CRÍTICO", "CRÍTICO", "ALERTA", "ALERTA", "ALERTA"]
    df["estado_global"] = np.select(condiciones, valores, default="NORMAL")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Persistencia en BD
# ─────────────────────────────────────────────────────────────────────────────

def _crear_tabla(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_DDL)
    conn.commit()
    print("  ✅ Tabla sector_energetico.estado_sin_diario verificada/creada")


def _insertar(conn, df: pd.DataFrame) -> None:
    """UPSERT vectorizado en estado_sin_diario."""
    bool_cols = [
        "flag_embalse_critico", "flag_embalse_alerta",
        "flag_termico_critico", "flag_termico_alerta",
        "flag_precio_critico",  "flag_precio_alerta",
        "flag_aportes_critico", "flag_aportes_alerta",
    ]

    def _safe(val, round_dec: Optional[int] = None):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return round(float(val), round_dec) if round_dec is not None else val

    rows = []
    for fecha, row in df.iterrows():
        rows.append((
            fecha.date(),
            row["estado_global"],
            int(row["n_criticos"]),
            int(row["n_alertas"]),
            _safe(row.get("gene_gwh"), 3),
            _safe(row.get("termica_gwh"), 3),
            _safe(row.get("aportes_gwh"), 3),
            _safe(row.get("embalse_pct"), 2),
            _safe(row.get("precio_bolsa"), 2),
            _safe(row.get("precio_escasez"), 2),
            _safe(row.get("estres_termico_mv3"), 2),
            _safe(row.get("price_ratio_mv3"), 4),
            *(bool(row.get(c, False)) for c in bool_cols),
        ))

    upsert_sql = """
        INSERT INTO sector_energetico.estado_sin_diario
            (fecha, estado_global, n_criticos, n_alertas,
             gene_gwh, termica_gwh, aportes_gwh,
             embalse_pct, precio_bolsa, precio_escasez,
             estres_termico_pct, price_ratio,
             flag_embalse_critico, flag_embalse_alerta,
             flag_termico_critico, flag_termico_alerta,
             flag_precio_critico,  flag_precio_alerta,
             flag_aportes_critico, flag_aportes_alerta)
        VALUES %s
        ON CONFLICT (fecha) DO UPDATE SET
            estado_global        = EXCLUDED.estado_global,
            n_criticos           = EXCLUDED.n_criticos,
            n_alertas            = EXCLUDED.n_alertas,
            gene_gwh             = EXCLUDED.gene_gwh,
            termica_gwh          = EXCLUDED.termica_gwh,
            aportes_gwh          = EXCLUDED.aportes_gwh,
            embalse_pct          = EXCLUDED.embalse_pct,
            precio_bolsa         = EXCLUDED.precio_bolsa,
            precio_escasez       = EXCLUDED.precio_escasez,
            estres_termico_pct   = EXCLUDED.estres_termico_pct,
            price_ratio          = EXCLUDED.price_ratio,
            flag_embalse_critico = EXCLUDED.flag_embalse_critico,
            flag_embalse_alerta  = EXCLUDED.flag_embalse_alerta,
            flag_termico_critico = EXCLUDED.flag_termico_critico,
            flag_termico_alerta  = EXCLUDED.flag_termico_alerta,
            flag_precio_critico  = EXCLUDED.flag_precio_critico,
            flag_precio_alerta   = EXCLUDED.flag_precio_alerta,
            flag_aportes_critico = EXCLUDED.flag_aportes_critico,
            flag_aportes_alerta  = EXCLUDED.flag_aportes_alerta,
            created_at           = NOW()
    """
    with conn.cursor() as cur:
        execute_values(cur, upsert_sql, rows)
    conn.commit()
    print(f"  ✅ {len(rows)} filas insertadas/actualizadas en estado_sin_diario")


# ─────────────────────────────────────────────────────────────────────────────
# Resumen consola
# ─────────────────────────────────────────────────────────────────────────────

_MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


def _imprimir_resumen(df: pd.DataFrame, inicio: str, fin: str) -> None:
    total = len(df)
    if total == 0:
        print("  ⚠️  Sin filas para mostrar resumen.")
        return

    n_normal  = (df["estado_global"] == "NORMAL").sum()
    n_alerta  = (df["estado_global"] == "ALERTA").sum()
    n_critico = (df["estado_global"] == "CRÍTICO").sum()

    sep = "─" * 80
    print(f"\n{'═'*80}")
    print(f"  📊  BACKTEST ALERTAS SIN — {inicio}  →  {fin}")
    print(f"{'═'*80}")
    print(f"  Total días evaluados : {total}")
    print(f"  🟢 NORMAL  : {n_normal:4d} días  ({n_normal/total*100:5.1f} %)")
    print(f"  🟡 ALERTA  : {n_alerta:4d} días  ({n_alerta/total*100:5.1f} %)")
    print(f"  🔴 CRÍTICO : {n_critico:4d} días  ({n_critico/total*100:5.1f} %)")

    print(f"\n{sep}")
    hdr = (f"  {'Mes':>4}  {'Días':>5}  "
           f"{'NORMAL':>12}  {'ALERTA':>12}  {'CRÍTICO':>12}  "
           f"{'Emb%':>6}  {'Térm%':>6}  {'Ratio':>7}")
    print(hdr)
    print(f"  {sep}")
    for m in range(1, 13):
        sub = df[df.index.month == m]
        if sub.empty:
            continue
        d  = len(sub)
        nn = (sub["estado_global"] == "NORMAL").sum()
        na = (sub["estado_global"] == "ALERTA").sum()
        nc = (sub["estado_global"] == "CRÍTICO").sum()
        emb = sub["embalse_pct"].mean()
        ter = sub["estres_termico_mv3"].mean() if "estres_termico_mv3" in sub else float("nan")
        pr  = sub["price_ratio_mv3"].mean()    if "price_ratio_mv3"    in sub else float("nan")
        print(
            f"  {_MESES[m-1]:>4}  {d:5d}  "
            f"{nn:5d} ({nn/d*100:4.0f}%)  "
            f"{na:5d} ({na/d*100:4.0f}%)  "
            f"{nc:5d} ({nc/d*100:4.0f}%)  "
            f"{emb:6.1f}  {ter:6.1f}  {pr:7.3f}"
        )

    print(f"\n{sep}")
    print("  Contribución de señales (días con flag activo):")
    flag_labels = [
        ("Embalse",  "flag_embalse_critico",  "flag_embalse_alerta"),
        ("Térmico",  "flag_termico_critico",  "flag_termico_alerta"),
        ("Precio",   "flag_precio_critico",   "flag_precio_alerta"),
        ("Aportes",  "flag_aportes_critico",  "flag_aportes_alerta"),
    ]
    for label, fc, fa in flag_labels:
        dc = int(df[fc].sum()) if fc in df.columns else 0
        da = int(df[fa].sum()) if fa in df.columns else 0
        bar_c = "█" * min(dc // 5, 20)
        bar_a = "█" * min(da // 5, 20)
        print(
            f"  {label:10s}  "
            f"CRÍTICO: {dc:3d}d ({dc/total*100:4.1f}%) {bar_c}   "
            f"ALERTA: {da:3d}d ({da/total*100:4.1f}%) {bar_a}"
        )
    print(f"{'═'*80}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline principal
# ─────────────────────────────────────────────────────────────────────────────

def run(
    inicio: str = DEFAULT_INICIO,
    fin: str = DEFAULT_FIN,
    guardar_bd: bool = True,
) -> pd.DataFrame:
    """Ejecuta el backtest completo y devuelve el DataFrame con resultados."""
    print(f"\n🔍  Backtest alertas energéticas: {inicio}  →  {fin}")
    conn = _get_conn()
    try:
        print("  Cargando métricas Sistema...")
        df = _cargar_metricas_base(conn, inicio, fin)
        print(f"  → {len(df)} días con datos")

        print("  Cargando generación térmica...")
        termica = _cargar_termica(conn, inicio, fin)

        print("  Calculando derivadas (rolling-3d)...")
        df = _calcular_derivadas(df, termica)

        print("  Aplicando umbrales y flags...")
        df = _calcular_flags(df)

        print("  Clasificando estado global diario...")
        df = _clasificar_estado(df)

        _imprimir_resumen(df, inicio, fin)

        if guardar_bd:
            print("💾  Persistiendo en estado_sin_diario...")
            _crear_tabla(conn)
            _insertar(conn, df)

        return df

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backtest histórico del modelo de alertas energéticas"
    )
    parser.add_argument(
        "--inicio", default=DEFAULT_INICIO, metavar="YYYY-MM-DD",
        help=f"Fecha de inicio (default: {DEFAULT_INICIO})"
    )
    parser.add_argument(
        "--fin", default=DEFAULT_FIN, metavar="YYYY-MM-DD",
        help=f"Fecha de fin (default: {DEFAULT_FIN})"
    )
    parser.add_argument(
        "--no-bd", action="store_true",
        help="Solo mostrar resultado en consola, no guardar en BD"
    )
    args = parser.parse_args()
    run(inicio=args.inicio, fin=args.fin, guardar_bd=not args.no_bd)
