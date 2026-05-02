#!/usr/bin/env python3
"""
verify_table.py — Verificación de estado de tabla PostgreSQL

Uso:
    python scripts/agent-tools/verify_table.py TABLA [--method A|B|C|D] [--output /tmp/snapshot_X.md]
    python scripts/agent-tools/verify_table.py TABLA --post-check /tmp/snapshot_X.md

Selecciona automáticamente el método según pg_relation_size:
    < 100 MB   → Método A (checksum completo)
    100MB-1GB  → Método B (checksum completo, lento)
    1GB-10GB   → Método C (stat proxy + TABLESAMPLE con WHERE)
    > 10GB     → Método D (stat proxy exclusivo, ANALYZE si DML)

Autor: Agent Tools — Portal Dirección MME
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
PGHOST = os.environ.get("PGHOST", "localhost")
PGPORT = os.environ.get("PGPORT", "5432")
PGDATABASE = os.environ.get("PGDATABASE", "portal_energetico")
PGUSER = os.environ.get("PGUSER", "mme_user")
PGPASSWORD = os.environ.get("PGPASSWORD", "")

LIMITS = {
    "A": 100 * 1024 * 1024,       # 100 MB
    "B": 1 * 1024 * 1024 * 1024,  # 1 GB
    "C": 10 * 1024 * 1024 * 1024, # 10 GB
}


def psql(cmd: str, db: str = PGDATABASE) -> str:
    """Ejecuta comando psql y retorna stdout."""
    env = os.environ.copy()
    env["PGPASSWORD"] = PGPASSWORD
    result = subprocess.run(
        ["psql", "-h", PGHOST, "-p", PGPORT, "-U", PGUSER, "-d", db, "-t", "-A", "-c", cmd],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        print(f"[ERROR] psql falló: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_table_size(table: str) -> int:
    """Retorna tamaño en bytes."""
    out = psql(f"SELECT pg_relation_size('{table}');")
    return int(out)


def detect_method(table: str) -> str:
    """Detecta método automáticamente por tamaño."""
    size = get_table_size(table)
    if size < LIMITS["A"]:
        return "A"
    elif size < LIMITS["B"]:
        return "B"
    elif size < LIMITS["C"]:
        return "C"
    else:
        return "D"


def snapshot_method_a(table: str) -> str:
    """Método A: checksum completo."""
    count = psql(f"SELECT COUNT(*) FROM {table};")
    try:
        checksum = psql(f"SELECT md5(string_agg(t::text, '' ORDER BY id)) FROM {table} AS t;")
    except SystemExit:
        checksum = "[ERROR: tabla sin columna 'id' o tipo no ordenable]"
    return f"""### Method A: Full Checksum
| Métrica | Valor |
|---|---|
| COUNT | {count} |
| MD5 (string_agg) | {checksum} |
"""


def snapshot_method_b(table: str) -> str:
    """Método B: checksum completo con precaución (mismo que A pero anotado)."""
    return snapshot_method_a(table).replace("Method A", "Method B")


def snapshot_method_c(table: str) -> str:
    """Método C: stat proxy + TABLESAMPLE con WHERE."""
    estimated = psql(
        f"SELECT reltuples::bigint FROM pg_class WHERE relname = '{table}';"
    )
    stats = psql(
        f"SELECT attname, n_distinct, null_frac, avg_width "
        f"FROM pg_stats WHERE tablename = '{table}' ORDER BY attname;"
    )
    # TABLESAMPLE con WHERE primero (evita sesgo de muestreo)
    try:
        sample = psql(
            f"SELECT md5(string_agg(t::text, '' ORDER BY id)) "
            f"FROM {table} TABLESAMPLE SYSTEM(1.0) "
            f"WHERE fecha >= CURRENT_DATE - INTERVAL '30 days';"
        )
    except SystemExit:
        sample = "[ERROR: sin columna 'fecha' o 'id']"
    rango = psql(f"SELECT MIN(fecha), MAX(fecha) FROM {table};")

    return f"""### Method C: Stat Proxy + Sampling
| Métrica | Valor |
|---|---|
| estimated_count (pg_class.reltuples) | {estimated} |
| rango_temporal | {rango} |
| sample_checksum (WHERE fecha >= NOW()-30d, TABLESAMPLE 1%) | {sample} |

### pg_stats
{stats}
"""


def snapshot_method_d(table: str) -> str:
    """Método D: stat proxy exclusivo."""
    stats = psql(
        f"SELECT attname, n_distinct, null_frac, avg_width, correlation "
        f"FROM pg_stats WHERE tablename = '{table}' ORDER BY attname;"
    )
    rango = psql(f"SELECT MIN(fecha), MAX(fecha) FROM {table};")
    return f"""### Method D: Stat Proxy Only
| Métrica | Valor |
|---|---|
| rango_temporal | {rango} |

### pg_stats (PRE-ANALYZE — ver nota abajo)
{stats}

⚠️ **AUTOVACUUM WARNING**: Si hubo INSERT/UPDATE/DELETE masivo (>1% filas)
entre este snapshot y el post-check, ejecutar `ANALYZE {table};` ANTES
de leer pg_stats para el post-check.
"""


def postcheck(table: str, snapshot_file: str) -> str:
    """Ejecuta post-check comparando contra snapshot."""
    path = Path(snapshot_file)
    if not path.exists():
        print(f"[ERROR] Snapshot no encontrado: {snapshot_file}", file=sys.stderr)
        sys.exit(1)

    content = path.read_text()
    method = "D" if "Method D" in content else "C" if "Method C" in content else "A"

    lines = [f"## Post-check: {table}"]
    lines.append(f"### Timestamp: {datetime.now().isoformat()}")

    if method == "D":
        print(f"[INFO] Método D detectado. Ejecutando ANALYZE {table}...")
        psql(f"ANALYZE {table};")
        lines.append(f"### ANALYZE ejecutado: {datetime.now().isoformat()}")

        stats = psql(
            f"SELECT attname, n_distinct, null_frac, avg_width, correlation "
            f"FROM pg_stats WHERE tablename = '{table}' ORDER BY attname;"
        )
        lines.append("### pg_stats post-ANALYZE:")
        lines.append(stats)

    elif method in ("A", "B"):
        count = psql(f"SELECT COUNT(*) FROM {table};")
        try:
            checksum = psql(f"SELECT md5(string_agg(t::text, '' ORDER BY id)) FROM {table} AS t;")
        except SystemExit:
            checksum = "[ERROR]"
        lines.append(f"### Method {method} post-check:")
        lines.append(f"| COUNT | {count} |")
        lines.append(f"| MD5 | {checksum} |")

    elif method == "C":
        estimated = psql(f"SELECT reltuples::bigint FROM pg_class WHERE relname = '{table}';")
        try:
            sample = psql(
                f"SELECT md5(string_agg(t::text, '' ORDER BY id)) "
                f"FROM {table} TABLESAMPLE SYSTEM(1.0) "
                f"WHERE fecha >= CURRENT_DATE - INTERVAL '30 days';"
            )
        except SystemExit:
            sample = "[ERROR]"
        lines.append("### Method C post-check:")
        lines.append(f"| estimated_count | {estimated} |")
        lines.append(f"| sample_checksum | {sample} |")

    result = "\n".join(lines)
    path.write_text(content + "\n\n" + result)
    print(f"[OK] Post-check añadido a: {snapshot_file}")
    return result


def snapshot(table: str, method: str | None = None, output: str | None = None) -> str:
    """Ejecuta snapshot completo."""
    auto_method = detect_method(table)
    chosen = method or auto_method
    size = get_table_size(table)
    size_pretty = psql(f"SELECT pg_size_pretty({size}::bigint);")

    if method and method != auto_method:
        print(f"[WARN] Método manual ({method}) != método auto ({auto_method}). "
              f"Tamaño: {size_pretty}")

    timestamp = datetime.now().isoformat()
    out_path = output or f"/tmp/snapshot_{table}_{datetime.now():%Y%m%d_%H%M%S}.md"

    header = f"""# Snapshot: {table}
## Timestamp
{timestamp}
## Size
{size_pretty} ({size} bytes)
## Method
{chosen} (auto-detected: {auto_method})
"""

    if chosen == "A":
        body = snapshot_method_a(table)
    elif chosen == "B":
        body = snapshot_method_b(table)
    elif chosen == "C":
        body = snapshot_method_c(table)
    else:
        body = snapshot_method_d(table)

    full = header + "\n" + body
    Path(out_path).write_text(full)
    print(f"[OK] Snapshot guardado en: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Verificación de tabla PostgreSQL")
    parser.add_argument("table", help="Nombre de la tabla")
    parser.add_argument("--method", choices=["A", "B", "C", "D"], help="Forzar método")
    parser.add_argument("--output", help="Ruta de salida del snapshot")
    parser.add_argument("--post-check", dest="postcheck", help="Archivo snapshot para post-check")
    args = parser.parse_args()

    if args.postcheck:
        postcheck(args.table, args.postcheck)
    else:
        snapshot(args.table, args.method, args.output)


if __name__ == "__main__":
    main()
