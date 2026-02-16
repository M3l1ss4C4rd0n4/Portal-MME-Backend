#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  DIAGNÓSTICO DE CONVERSORES DE UNIDADES — Script no destructivo     ║
║                                                                      ║
║  Valida que las funciones de conversión del ETL producen resultados  ║
║  correctos usando datos sintéticos.                                  ║
║                                                                      ║
║  Prueba:                                                             ║
║   • Wh → GWh (÷1M)                                                  ║
║   • kWh horario → GWh (Σ24h ÷1M)                                    ║
║   • kW horario → MW (avg 24h ÷1K)                                   ║
║   • COP → Millones COP (÷1M)                                        ║
║   • Restricciones → MCOP (avg 24h ÷1M)                              ║
║   • sin_conversión (identidad)                                       ║
║   • Coherencia entre detectar_conversion() y etl_rules.py           ║
║                                                                      ║
║  Uso:                                                                ║
║    python3 scripts/diagnostico_conversores_unidades.py               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import traceback

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════════════
# Importar funciones del ETL actual y de las reglas centralizadas
# ═══════════════════════════════════════════════════════════════

from etl.etl_todas_metricas_xm import detectar_conversion, convertir_unidades
from etl.etl_rules import (
    get_all_rules,
    get_conversion_type,
    apply_conversion,
    ConversionType,
    MetricRule,
)

# ═══════════════════════════════════════════════════════════════
# DATOS SINTÉTICOS DE PRUEBA
# ═══════════════════════════════════════════════════════════════

def crear_df_con_value(valor: float) -> pd.DataFrame:
    """Crea un DataFrame con columna Value."""
    return pd.DataFrame({
        "Date": ["2025-01-15"],
        "Value": [valor],
    })


def crear_df_con_horas(valor_por_hora: float) -> pd.DataFrame:
    """Crea un DataFrame con 24 columnas horarias (Values_Hour01..24)."""
    data = {"Date": ["2025-01-15"]}
    for i in range(1, 25):
        data[f"Values_Hour{i:02d}"] = [valor_por_hora]
    return pd.DataFrame(data)


# ═══════════════════════════════════════════════════════════════
# TESTS DE CONVERSIÓN
# ═══════════════════════════════════════════════════════════════

PASSED = 0
FAILED = 0
WARNINGS = 0


def assert_close(actual, expected, label, tolerance=0.0001):
    """Verifica que dos valores sean iguales dentro de la tolerancia."""
    global PASSED, FAILED
    if abs(actual - expected) < tolerance:
        print(f"  ✅ {label}: {actual:.6f} ≈ {expected:.6f}")
        PASSED += 1
    else:
        print(f"  ❌ {label}: {actual:.6f} ≠ {expected:.6f} (FALLO)")
        FAILED += 1


def test_wh_a_gwh():
    """Wh → GWh: dividir por 1_000_000."""
    print("\n─── Test: Wh → GWh ───")
    df = crear_df_con_value(5_000_000_000.0)  # 5 mil millones Wh = 5000 GWh
    result = convertir_unidades(df, "AporEner", "Wh_a_GWh")
    assert_close(result["Value"].iloc[0], 5000.0, "AporEner 5G Wh → 5000 GWh")

    df2 = crear_df_con_value(120_000_000.0)  # 120M Wh = 120 GWh
    result2 = convertir_unidades(df2, "VoluUtilDiarEner", "Wh_a_GWh")
    assert_close(result2["Value"].iloc[0], 120.0, "VoluUtilDiarEner 120M Wh → 120 GWh")


def test_horas_a_gwh():
    """Sum(24h kWh) → GWh: sumar 24 horas ÷ 1_000_000."""
    print("\n─── Test: Horas → GWh (Σ24h ÷ 1M) ───")
    # Cada hora tiene 1000 kWh → total 24,000 kWh → 0.024 GWh
    df = crear_df_con_horas(1000.0)
    result = convertir_unidades(df, "Gene", "horas_a_GWh")
    assert_close(result["Value"].iloc[0], 0.024, "Gene 1000kWh×24h → 0.024 GWh")

    # 5M kWh por hora → 120M kWh → 120 GWh
    df2 = crear_df_con_horas(5_000_000.0)
    result2 = convertir_unidades(df2, "DemaReal", "horas_a_GWh")
    assert_close(result2["Value"].iloc[0], 120.0, "DemaReal 5M kWh×24h → 120 GWh")


def test_horas_a_mw():
    """Avg(24h kW) → MW: promedio 24 horas ÷ 1_000."""
    print("\n─── Test: Horas → MW (avg24h ÷ 1K) ───")
    # 15,000 kW por hora → promedio = 15,000 kW → 15 MW
    df = crear_df_con_horas(15000.0)
    result = convertir_unidades(df, "DispoReal", "horas_a_MW")
    assert_close(result["Value"].iloc[0], 15.0, "DispoReal 15000kW → 15 MW")


def test_cop_a_mcop():
    """COP → Millones COP: ÷ 1_000_000."""
    print("\n─── Test: COP → Millones COP ───")
    df = crear_df_con_value(2_500_000_000.0)  # 2.5 mil millones COP = 2500 MCOP
    result = convertir_unidades(df, "RespComerAGC", "COP_a_MCOP")
    assert_close(result["Value"].iloc[0], 2500.0, "RespComerAGC 2.5G COP → 2500 MCOP")


def test_restricciones_a_mcop():
    """Restricciones: Avg(24h) ÷ 1_000_000."""
    print("\n─── Test: Restricciones → MCOP (avg24h ÷ 1M) ───")
    # 500,000 por hora promedio → 500,000 / 1M = 0.5 MCOP
    df = crear_df_con_horas(500_000.0)
    result = convertir_unidades(df, "RestAliv", "restricciones_a_MCOP")
    assert_close(result["Value"].iloc[0], 0.5, "RestAliv 500K/h → 0.5 MCOP")


def test_sin_conversion():
    """Sin conversión: el valor no debe cambiar."""
    print("\n─── Test: Sin conversión (identidad) ───")
    df = crear_df_con_value(345.67)
    result = convertir_unidades(df, "PrecBolsNaci", "sin_conversion")
    assert_close(result["Value"].iloc[0], 345.67, "PrecBolsNaci 345.67 → 345.67")


# ═══════════════════════════════════════════════════════════════
# TEST: Coherencia detectar_conversion() ↔ etl_rules.py
# ═══════════════════════════════════════════════════════════════

# Mapeo de string de conversión antiguo → ConversionType enum
_CONV_MAP = {
    "Wh_a_GWh": ConversionType.WH_TO_GWH,
    "kWh_a_GWh": ConversionType.KWH_TO_GWH,
    "horas_a_GWh": ConversionType.HOURS_TO_GWH,
    "horas_a_MW": ConversionType.HOURS_TO_MW,
    "COP_a_MCOP": ConversionType.COP_TO_MCOP,
    "restricciones_a_MCOP": ConversionType.RESTR_TO_MCOP,
    "sin_conversion": ConversionType.NONE,
}


def test_coherencia_detectar_vs_rules():
    """
    Compara detectar_conversion() (ETL actual) con get_conversion_type() (reglas centralizadas).
    
    Diferencias = bugs potenciales que deben resolverse.
    """
    global WARNINGS
    print("\n─── Test: Coherencia detectar_conversion() ↔ etl_rules.py ───")
    
    rules = get_all_rules()
    mismatches = []
    matches = 0

    for metric_id, rule in sorted(rules.items()):
        # Tomar la primera entidad como referencia
        entity = rule.entities[0] if rule.entities else "Sistema"
        old_conv_str = detectar_conversion(metric_id, entity)
        new_conv_enum = rule.conversion

        # Mapear string antiguo a enum
        old_conv_enum = _CONV_MAP.get(old_conv_str)

        if old_conv_enum is None:
            mismatches.append(
                f"  ⚠️  {metric_id}: detectar_conversion()='{old_conv_str}' "
                f"(no reconocido en mapa), regla={new_conv_enum.value}"
            )
            WARNINGS += 1
        elif old_conv_enum != new_conv_enum:
            mismatches.append(
                f"  ❌ {metric_id}: detectar_conversion()='{old_conv_str}' "
                f"≠ regla='{new_conv_enum.value}'"
            )
            WARNINGS += 1
        else:
            matches += 1

    print(f"  ✅ Coincidencias: {matches}/{len(rules)}")
    if mismatches:
        print(f"  ⚠️  Discrepancias ({len(mismatches)}):")
        for m in mismatches:
            print(m)
    else:
        print("  ✅ No hay discrepancias — las reglas están sincronizadas con el ETL actual")


# ═══════════════════════════════════════════════════════════════
# TEST: apply_conversion() de etl_rules.py produce mismos resultados
# ═══════════════════════════════════════════════════════════════

def test_apply_conversion_rules():
    """Verifica que apply_conversion() de etl_rules.py produce resultados correctos."""
    print("\n─── Test: apply_conversion() de etl_rules.py ───")

    # Wh → GWh
    df1 = crear_df_con_value(5_000_000_000.0)
    r1 = apply_conversion(df1, "AporEner")
    assert_close(r1["Value"].iloc[0], 5000.0, "apply_conversion AporEner → 5000 GWh")

    # Horas → GWh  
    df2 = crear_df_con_horas(5_000_000.0)
    r2 = apply_conversion(df2, "Gene")
    assert_close(r2["Value"].iloc[0], 120.0, "apply_conversion Gene → 120 GWh")

    # Horas → MW
    df3 = crear_df_con_horas(15000.0)
    r3 = apply_conversion(df3, "DispoReal")
    assert_close(r3["Value"].iloc[0], 15.0, "apply_conversion DispoReal → 15 MW")

    # COP → MCOP
    df4 = crear_df_con_value(2_500_000_000.0)
    r4 = apply_conversion(df4, "RespComerAGC")
    assert_close(r4["Value"].iloc[0], 2500.0, "apply_conversion RespComerAGC → 2500 MCOP")

    # Restricciones → MCOP
    df5 = crear_df_con_horas(500_000.0)
    r5 = apply_conversion(df5, "RestAliv")
    assert_close(r5["Value"].iloc[0], 0.5, "apply_conversion RestAliv → 0.5 MCOP")

    # Sin conversión
    df6 = crear_df_con_value(345.67)
    r6 = apply_conversion(df6, "PrecBolsNaci")
    assert_close(r6["Value"].iloc[0], 345.67, "apply_conversion PrecBolsNaci → 345.67")


# ═══════════════════════════════════════════════════════════════
# TEST: Métricas huérfanas (en BD pero sin regla)
# ═══════════════════════════════════════════════════════════════

def test_metricas_huerfanas_bd():
    """
    Conecta a BD y lista métricas que están en la tabla metrics
    pero no tienen regla definida en etl_rules.py.
    
    Estas métricas no tendrán validación centralizada.
    """
    global WARNINGS
    print("\n─── Test: Métricas en BD sin regla en etl_rules.py ───")
    
    try:
        import psycopg2
        conn = psycopg2.connect(dbname="portal_energetico", user="postgres", host="localhost")
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT metrica FROM metrics ORDER BY metrica")
        metricas_bd = {r[0] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        print(f"  ⚠️  No se pudo conectar a BD: {e}")
        return

    rules = get_all_rules()
    metricas_con_regla = set(rules.keys())

    huerfanas = metricas_bd - metricas_con_regla
    sin_datos = metricas_con_regla - metricas_bd

    print(f"  ℹ️  Métricas en BD: {len(metricas_bd)}")
    print(f"  ℹ️  Reglas definidas: {len(metricas_con_regla)}")
    print(f"  ℹ️  En BD con regla: {len(metricas_bd & metricas_con_regla)}")

    if huerfanas:
        print(f"\n  ⚠️  Métricas en BD SIN regla ({len(huerfanas)}):")
        for m in sorted(huerfanas):
            print(f"       • {m}")
            WARNINGS += 1
    else:
        print("  ✅ Todas las métricas en BD tienen regla")

    if sin_datos:
        print(f"\n  ℹ️  Reglas definidas SIN datos en BD ({len(sin_datos)}):")
        for m in sorted(sin_datos):
            print(f"       • {m}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  DIAGNÓSTICO DE CONVERSORES DE UNIDADES — Portal Energético MME")
    print("=" * 80)

    try:
        test_wh_a_gwh()
        test_horas_a_gwh()
        test_horas_a_mw()
        test_cop_a_mcop()
        test_restricciones_a_mcop()
        test_sin_conversion()
        test_apply_conversion_rules()
        test_coherencia_detectar_vs_rules()
        test_metricas_huerfanas_bd()
    except Exception as e:
        print(f"\n💥 Error no capturado: {e}")
        traceback.print_exc()
        return 1

    # Resumen
    print("\n" + "=" * 80)
    print("  RESUMEN")
    print("=" * 80)
    print(f"  ✅ Pasaron:      {PASSED}")
    print(f"  ❌ Fallaron:     {FAILED}")
    print(f"  ⚠️  Advertencias: {WARNINGS}")

    if FAILED > 0:
        print("\n  🔴 HAY FALLOS — las conversiones no son correctas")
        return 1
    elif WARNINGS > 0:
        print("\n  🟡 Sin fallos pero con advertencias — revisar discrepancias")
        return 0
    else:
        print("\n  🟢 Todo OK — conversiones verificadas")
        return 0


if __name__ == "__main__":
    sys.exit(main())
