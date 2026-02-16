#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║     DIAGNÓSTICO DE MÉTRICAS ETL — Script no destructivo (solo lee)  ║
║                                                                      ║
║  Verifica la salud de cada métrica en la BD:                         ║
║   • Existencia de datos                                              ║
║   • Huecos en la serie temporal                                      ║
║   • Unidad correcta según etl_rules.py                               ║
║   • Rango de valores dentro de lo esperado                           ║
║   • Frescura de datos (última fecha)                                 ║
║                                                                      ║
║  Uso:                                                                ║
║    python3 scripts/diagnostico_metricas_etl.py                       ║
║    python3 scripts/diagnostico_metricas_etl.py --dias 30             ║
║    python3 scripts/diagnostico_metricas_etl.py --csv reporte.csv     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import argparse
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
import psycopg2.extras

# Importar reglas centralizadas
from etl.etl_rules import get_all_rules, MetricRule


# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

DB_NAME = "portal_energetico"
DB_USER = "postgres"
DB_HOST = "localhost"

# Umbral: cuántos días sin datos son un "hueco" significativo
GAP_THRESHOLD_DAYS = 3

# Días máximos de antigüedad para datos recientes
FRESHNESS_MAX_DAYS = 5


def get_connection():
    """Conecta a PostgreSQL."""
    return psycopg2.connect(dbname=DB_NAME, user=DB_USER, host=DB_HOST)


def diagnosticar_metrica(
    conn, rule: MetricRule, dias_analisis: int
) -> Dict[str, Any]:
    """
    Diagnostica el estado de una métrica en BD.

    Retorna un diccionario con:
      metric_id, entity, status, issues[], stats{}
    """
    result = {
        "metric_id": rule.metric_id,
        "section": rule.section.value,
        "expected_unit": rule.expected_unit,
        "entities_checked": [],
        "status": "OK",
        "issues": [],
        "stats": {},
    }

    cur = conn.cursor()
    fecha_limite = (datetime.now() - timedelta(days=dias_analisis)).strftime("%Y-%m-%d")
    hoy = datetime.now().strftime("%Y-%m-%d")

    # Verificar cada entidad esperada
    for entity in rule.entities:
        entity_result = {
            "entity": entity,
            "count": 0,
            "unit_ok": True,
            "gaps": 0,
            "max_gap_days": 0,
            "latest_date": None,
            "freshness_days": None,
            "value_min": None,
            "value_max": None,
            "out_of_range": 0,
            "negative_count": 0,
        }

        # 1. Contar registros
        cur.execute(
            """
            SELECT COUNT(*), MIN(fecha), MAX(fecha), MIN(valor_gwh), MAX(valor_gwh)
            FROM metrics
            WHERE metrica = %s AND entidad = %s AND fecha >= %s
            """,
            (rule.metric_id, entity, fecha_limite),
        )
        row = cur.fetchone()
        count, fecha_min, fecha_max, val_min, val_max = row

        entity_result["count"] = count or 0

        if count == 0:
            entity_result["status"] = "SIN_DATOS"
            result["issues"].append(
                f"SIN_DATOS: {rule.metric_id}/{entity} — 0 registros en últimos {dias_analisis} días"
            )
            result["entities_checked"].append(entity_result)
            continue

        entity_result["value_min"] = float(val_min) if val_min is not None else None
        entity_result["value_max"] = float(val_max) if val_max is not None else None
        entity_result["latest_date"] = str(fecha_max) if fecha_max else None

        # 2. Frescura
        if fecha_max:
            days_old = (datetime.now() - fecha_max).days if hasattr(fecha_max, 'day') else None
            if days_old is None:
                try:
                    days_old = (datetime.now() - datetime.strptime(str(fecha_max)[:10], "%Y-%m-%d")).days
                except Exception:
                    days_old = 999
            entity_result["freshness_days"] = days_old
            if days_old > FRESHNESS_MAX_DAYS:
                result["issues"].append(
                    f"DATOS_ANTIGUOS: {rule.metric_id}/{entity} — última fecha: {fecha_max} "
                    f"({days_old} días de antigüedad)"
                )

        # 3. Unidades
        cur.execute(
            """
            SELECT DISTINCT unidad FROM metrics
            WHERE metrica = %s AND entidad = %s AND fecha >= %s
            """,
            (rule.metric_id, entity, fecha_limite),
        )
        units = [r[0] for r in cur.fetchall()]
        bad_units = [u for u in units if u != rule.expected_unit and u is not None]
        none_units = [u for u in units if u is None]

        if bad_units:
            entity_result["unit_ok"] = False
            result["issues"].append(
                f"UNIDAD_INCORRECTA: {rule.metric_id}/{entity} — "
                f"encontrada(s) {bad_units}, esperada '{rule.expected_unit}'"
            )
        if none_units:
            # Contar cuántos registros tienen unidad=None
            cur.execute(
                """
                SELECT COUNT(*) FROM metrics
                WHERE metrica = %s AND entidad = %s AND fecha >= %s AND unidad IS NULL
                """,
                (rule.metric_id, entity, fecha_limite),
            )
            none_count = cur.fetchone()[0]
            result["issues"].append(
                f"UNIDAD_NULL: {rule.metric_id}/{entity} — {none_count} registros con unidad=NULL"
            )

        # 4. Rango de valores
        vmin, vmax = rule.valid_range
        cur.execute(
            """
            SELECT COUNT(*) FROM metrics
            WHERE metrica = %s AND entidad = %s AND fecha >= %s
              AND (valor_gwh < %s OR valor_gwh > %s)
            """,
            (rule.metric_id, entity, fecha_limite, vmin, vmax),
        )
        entity_result["out_of_range"] = cur.fetchone()[0]
        if entity_result["out_of_range"] > 0:
            result["issues"].append(
                f"FUERA_DE_RANGO: {rule.metric_id}/{entity} — "
                f"{entity_result['out_of_range']} valores fuera de [{vmin}, {vmax}]"
            )

        # 5. Negativos (si no permitidos)
        if not rule.allow_negative:
            cur.execute(
                """
                SELECT COUNT(*) FROM metrics
                WHERE metrica = %s AND entidad = %s AND fecha >= %s AND valor_gwh < 0
                """,
                (rule.metric_id, entity, fecha_limite),
            )
            entity_result["negative_count"] = cur.fetchone()[0]
            if entity_result["negative_count"] > 0:
                result["issues"].append(
                    f"NEGATIVOS: {rule.metric_id}/{entity} — "
                    f"{entity_result['negative_count']} valores negativos no esperados"
                )

        # 6. Huecos en serie temporal (solo para métricas diarias con > 10 registros)
        if count > 10 and entity in ("Sistema", "Rio", "Embalse"):
            cur.execute(
                """
                SELECT fecha FROM metrics
                WHERE metrica = %s AND entidad = %s AND fecha >= %s
                GROUP BY fecha
                ORDER BY fecha
                """,
                (rule.metric_id, entity, fecha_limite),
            )
            fechas = [r[0] for r in cur.fetchall()]
            if len(fechas) > 1:
                max_gap = 0
                gaps = 0
                for i in range(1, len(fechas)):
                    try:
                        f1 = fechas[i - 1]
                        f2 = fechas[i]
                        if isinstance(f1, str):
                            f1 = datetime.strptime(f1[:10], "%Y-%m-%d")
                        if isinstance(f2, str):
                            f2 = datetime.strptime(f2[:10], "%Y-%m-%d")
                        delta = (f2 - f1).days
                    except Exception:
                        delta = 1
                    if delta > GAP_THRESHOLD_DAYS:
                        gaps += 1
                        max_gap = max(max_gap, delta)
                entity_result["gaps"] = gaps
                entity_result["max_gap_days"] = max_gap
                if gaps > 0:
                    result["issues"].append(
                        f"HUECOS_SERIE: {rule.metric_id}/{entity} — "
                        f"{gaps} huecos detectados (máx {max_gap} días)"
                    )

        result["entities_checked"].append(entity_result)

    # Definir status global
    if any("SIN_DATOS" in i for i in result["issues"]):
        result["status"] = "SIN_DATOS"
    elif any("ERROR" in i or "UNIDAD_INCORRECTA" in i for i in result["issues"]):
        result["status"] = "ERROR"
    elif result["issues"]:
        result["status"] = "ADVERTENCIA"

    return result


def run_diagnostico(dias: int = 365, csv_path: str = None):
    """Ejecuta el diagnóstico completo de todas las métricas con reglas definidas."""
    print("=" * 80)
    print("  DIAGNÓSTICO DE MÉTRICAS ETL — Portal Energético MME")
    print(f"  Rango analizado: últimos {dias} días")
    print(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    rules = get_all_rules()
    print(f"\n📋 Total reglas definidas: {len(rules)}")

    conn = get_connection()
    resultados: List[Dict] = []

    ok = 0
    warn = 0
    error = 0
    sin_datos = 0

    for metric_id, rule in sorted(rules.items()):
        r = diagnosticar_metrica(conn, rule, dias)
        resultados.append(r)

        icon = {"OK": "✅", "ADVERTENCIA": "⚠️", "ERROR": "❌", "SIN_DATOS": "🔴"}.get(
            r["status"], "❓"
        )

        if r["status"] == "OK":
            ok += 1
        elif r["status"] == "ADVERTENCIA":
            warn += 1
        elif r["status"] == "SIN_DATOS":
            sin_datos += 1
        else:
            error += 1

        ent_info = ", ".join(
            f"{e['entity']}({e['count']})" for e in r["entities_checked"]
        )
        print(f"  {icon} {metric_id:30s} [{r['section']:15s}] → {r['status']:12s}  {ent_info}")

        for issue in r["issues"]:
            print(f"       ↳ {issue}")

    conn.close()

    # Resumen
    total = ok + warn + error + sin_datos
    print("\n" + "=" * 80)
    print("  RESUMEN")
    print("=" * 80)
    print(f"  ✅ OK:          {ok}/{total}")
    print(f"  ⚠️  Advertencias: {warn}/{total}")
    print(f"  ❌ Errores:      {error}/{total}")
    print(f"  🔴 Sin datos:    {sin_datos}/{total}")

    # Exportar CSV si se pidió
    if csv_path:
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "metric_id", "section", "expected_unit", "status",
                "entity", "count", "unit_ok", "gaps", "max_gap_days",
                "latest_date", "freshness_days", "value_min", "value_max",
                "out_of_range", "negative_count", "issues",
            ])
            for r in resultados:
                for e in r["entities_checked"]:
                    writer.writerow([
                        r["metric_id"], r["section"], r["expected_unit"], r["status"],
                        e["entity"], e["count"], e.get("unit_ok", ""),
                        e.get("gaps", ""), e.get("max_gap_days", ""),
                        e.get("latest_date", ""), e.get("freshness_days", ""),
                        e.get("value_min", ""), e.get("value_max", ""),
                        e.get("out_of_range", ""), e.get("negative_count", ""),
                        " | ".join(r["issues"]),
                    ])
        print(f"\n📄 Reporte CSV exportado: {csv_path}")

    # Código de salida: 0 si no hay errores/sin_datos, 1 si los hay
    return 0 if error == 0 and sin_datos == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnóstico de métricas ETL")
    parser.add_argument("--dias", type=int, default=365, help="Días de análisis (default: 365)")
    parser.add_argument("--csv", type=str, default=None, help="Ruta para exportar CSV")
    args = parser.parse_args()

    exit_code = run_diagnostico(dias=args.dias, csv_path=args.csv)
    sys.exit(exit_code)
