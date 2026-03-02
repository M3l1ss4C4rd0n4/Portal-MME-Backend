#!/usr/bin/env python3
"""
FASE 5.B — EXPERIMENTO XGBOOST OFFLINE PARA PRECIO_BOLSA
=========================================================
Ministerio de Minas y Energía — República de Colombia

Objetivo:
  Comparar XGBoost multivariable vs ensemble Prophet+SARIMA actual
  para la predicción de Precio de Bolsa Nacional.

Features:
  - Target: PRECIO_BOLSA (PrecBolsNaci, $/kWh)
  - Regresores BD: embalses_pct, demanda_gwh, aportes_gwh
  - Lags: precio_lag_1 (t-1), precio_lag_7 (t-7)
  - Calendario: es_festivo, dow_lun..dow_sab (7 features)

Validación:
  Temporal holdout — últimos 30 días del dataset.
  NO se usa random split (data leak temporal).

Salidas:
  - experiments/resultados_xgboost_precio.csv   (predicciones vs reales)
  - experiments/feature_importance_xgboost.csv   (importancia de features)
  - experiments/comparacion_modelos.csv          (MAPE/RMSE resumen)
  - Log en stdout

⚠️  NO integrar a producción. Solo comparar y guardar resultados en CSV.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error
import warnings
warnings.filterwarnings('ignore')

# ─── Directorio de salida ───
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Parámetros del experimento ───
VENTANA_MESES = 15          # Misma ventana que ensemble actual
HOLDOUT_DIAS = 30           # Días de validación temporal
PISO_HISTORICO = 86.0       # Mínimo histórico $/kWh (consistente con producción)

# =============================================================================
# CARGA DE DATOS (reutiliza patrón de train_predictions_sector_energetico.py)
# =============================================================================

def get_postgres_connection():
    """Conexión a PostgreSQL usando infraestructura del sistema."""
    import psycopg2
    from infrastructure.database.connection import PostgreSQLConnectionManager
    manager = PostgreSQLConnectionManager()
    conn_params = {
        'host': manager.host,
        'port': manager.port,
        'database': manager.database,
        'user': manager.user
    }
    if manager.password:
        conn_params['password'] = manager.password
    return psycopg2.connect(**conn_params)


def cargar_precio_bolsa(fecha_inicio):
    """Carga serie diaria de Precio de Bolsa Nacional."""
    conn = get_postgres_connection()
    query = """
    SELECT fecha, AVG(valor_gwh) as valor
    FROM metrics
    WHERE metrica = 'PrecBolsNaci'
      AND fecha >= %s
      AND entidad = 'Sistema'
      AND valor_gwh > 0
    GROUP BY fecha
    ORDER BY fecha
    """
    df = pd.read_sql_query(query, conn, params=(fecha_inicio,))
    conn.close()
    df['fecha'] = pd.to_datetime(df['fecha'])
    df = df.sort_values('fecha').set_index('fecha')
    return df


def cargar_regresores_bd(fecha_inicio):
    """Carga regresores históricos: embalses_pct, demanda_gwh, aportes_gwh."""
    conn = get_postgres_connection()
    series = {}

    # embalses_pct (PorcVoluUtilDiar × 100, entidad=Sistema)
    q = """
    SELECT fecha, AVG(valor_gwh) * 100 as valor
    FROM metrics
    WHERE metrica = 'PorcVoluUtilDiar' AND fecha >= %s AND entidad = 'Sistema' AND valor_gwh > 0
    GROUP BY fecha ORDER BY fecha
    """
    df_e = pd.read_sql_query(q, conn, params=(fecha_inicio,))
    df_e['fecha'] = pd.to_datetime(df_e['fecha'])
    series['embalses_pct'] = df_e.set_index('fecha')['valor']

    # demanda_gwh (DemaReal, prefer Sistema)
    q = """
    SELECT fecha,
      CASE WHEN MAX(CASE WHEN entidad='Sistema' THEN 1 ELSE 0 END) = 1
           THEN SUM(CASE WHEN entidad='Sistema' THEN valor_gwh END)
           ELSE SUM(valor_gwh)
      END as valor
    FROM metrics
    WHERE metrica = 'DemaReal' AND fecha >= %s AND valor_gwh > 0
    GROUP BY fecha ORDER BY fecha
    """
    df_d = pd.read_sql_query(q, conn, params=(fecha_inicio,))
    df_d['fecha'] = pd.to_datetime(df_d['fecha'])
    series['demanda_gwh'] = df_d.set_index('fecha')['valor']

    # aportes_gwh (AporEner)
    q = """
    SELECT fecha, SUM(valor_gwh) as valor
    FROM metrics
    WHERE metrica = 'AporEner' AND fecha >= %s AND valor_gwh > 0
    GROUP BY fecha ORDER BY fecha
    """
    df_a = pd.read_sql_query(q, conn, params=(fecha_inicio,))
    df_a['fecha'] = pd.to_datetime(df_a['fecha'])
    series['aportes_gwh'] = df_a.set_index('fecha')['valor']

    conn.close()

    df_regs = pd.DataFrame(series).sort_index().ffill().bfill()
    return df_regs


def construir_features_calendario(fechas_index):
    """Construye features de calendario: festivos + DOW dummies."""
    # Reutilizar festivos colombianos de producción
    from scripts.train_predictions_sector_energetico import _FESTIVOS_CO

    dates = pd.to_datetime(fechas_index)
    dow = dates.dayofweek

    df_cal = pd.DataFrame(index=dates)
    df_cal['es_festivo'] = [1.0 if d.date() in _FESTIVOS_CO else 0.0 for d in dates]
    df_cal['dow_lun'] = (dow == 0).astype(float)
    df_cal['dow_mar'] = (dow == 1).astype(float)
    df_cal['dow_mie'] = (dow == 2).astype(float)
    df_cal['dow_jue'] = (dow == 3).astype(float)
    df_cal['dow_vie'] = (dow == 4).astype(float)
    df_cal['dow_sab'] = (dow == 5).astype(float)
    return df_cal


# =============================================================================
# CARGAR MÉTRICAS DEL ENSEMBLE ACTUAL (desde BD predictions)
# =============================================================================

def cargar_metricas_ensemble_actual():
    """
    Lee MAPE y RMSE del ensemble Prophet+SARIMA actual para PRECIO_BOLSA
    desde la tabla predictions (guardados por train_predictions_sector_energetico.py).
    """
    conn = get_postgres_connection()
    try:
        query = """
        SELECT mape_validacion, rmse_validacion
        FROM predictions
        WHERE fuente = 'PRECIO_BOLSA'
        LIMIT 1
        """
        df = pd.read_sql_query(query, conn)
        if len(df) > 0 and df['mape_validacion'].iloc[0] is not None:
            return {
                'mape': float(df['mape_validacion'].iloc[0]),
                'rmse': float(df['rmse_validacion'].iloc[0]) if df['rmse_validacion'].iloc[0] else None
            }
    except Exception:
        pass
    finally:
        conn.close()
    return {'mape': None, 'rmse': None}


# =============================================================================
# CONSTRUCCIÓN DEL DATASET MULTIVARIABLE
# =============================================================================

def construir_dataset():
    """
    Construye dataset multivariable para XGBoost:
    target + 3 regresores BD + 2 lags + 7 calendario = 12 features.
    """
    from dateutil.relativedelta import relativedelta
    fecha_inicio = (datetime.now() - relativedelta(months=VENTANA_MESES)).strftime('%Y-%m-%d')

    print(f"\n{'='*70}")
    print(f"  FASE 5.B — EXPERIMENTO XGBOOST PRECIO_BOLSA")
    print(f"{'='*70}")
    print(f"\n📊 Cargando datos desde {fecha_inicio}...")

    # 1. Target
    df_precio = cargar_precio_bolsa(fecha_inicio)
    print(f"   Precio de Bolsa: {len(df_precio)} registros "
          f"({df_precio.index.min().date()} → {df_precio.index.max().date()})")
    print(f"   μ={df_precio['valor'].mean():.2f} $/kWh, "
          f"σ={df_precio['valor'].std():.2f}")

    # 2. Regresores BD
    df_regs = cargar_regresores_bd(fecha_inicio)
    print(f"   Regresores BD: {len(df_regs)} registros, "
          f"columnas={list(df_regs.columns)}")

    # 3. Fusionar target + regresores
    df = df_precio.join(df_regs, how='inner')
    print(f"   Dataset fusionado: {len(df)} registros (inner join por fecha)")

    # 4. Lags del target
    df['precio_lag_1'] = df['valor'].shift(1)
    df['precio_lag_7'] = df['valor'].shift(7)

    # 5. Regresores calendario
    df_cal = construir_features_calendario(df.index)
    df = df.join(df_cal)

    # 6. Eliminar filas con NaN (por lags)
    n_antes = len(df)
    df = df.dropna()
    print(f"   Eliminadas {n_antes - len(df)} filas por NaN de lags")
    print(f"   Dataset final: {len(df)} registros × {len(df.columns)} columnas")

    return df


# =============================================================================
# ENTRENAMIENTO Y EVALUACIÓN XGBOOST
# =============================================================================

def entrenar_xgboost(df):
    """
    Entrena XGBoost con temporal holdout de HOLDOUT_DIAS días.
    NO usa random split (evitar data leak temporal).
    """
    try:
        from xgboost import XGBRegressor
    except ImportError:
        print("\n❌ xgboost no instalado. Ejecute: pip install xgboost")
        sys.exit(1)

    # ── Split temporal ──
    target_col = 'valor'
    feature_cols = [c for c in df.columns if c != target_col]

    df_train = df.iloc[:-HOLDOUT_DIAS]
    df_test = df.iloc[-HOLDOUT_DIAS:]

    X_train = df_train[feature_cols]
    y_train = df_train[target_col]
    X_test = df_test[feature_cols]
    y_test = df_test[target_col]

    print(f"\n📐 Split temporal:")
    print(f"   Train: {len(df_train)} días "
          f"({df_train.index.min().date()} → {df_train.index.max().date()})")
    print(f"   Test:  {len(df_test)} días "
          f"({df_test.index.min().date()} → {df_test.index.max().date()})")

    # ── Entrenar XGBoost ──
    print(f"\n🤖 Entrenando XGBoost...")

    modelo = XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
        early_stopping_rounds=50,
    )

    modelo.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # ── Predecir ──
    y_pred = modelo.predict(X_test)

    # Aplicar piso histórico (consistente con producción)
    y_pred = np.maximum(y_pred, PISO_HISTORICO)

    # ── Métricas ──
    mape = mean_absolute_percentage_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = np.mean(np.abs(y_test - y_pred))

    print(f"\n📊 Resultados XGBoost (holdout {HOLDOUT_DIAS} días):")
    print(f"   MAPE:  {mape*100:.2f}%")
    print(f"   RMSE:  {rmse:.2f} $/kWh")
    print(f"   MAE:   {mae:.2f} $/kWh")

    return modelo, y_test, y_pred, feature_cols, {
        'mape': mape,
        'rmse': rmse,
        'mae': mae
    }


# =============================================================================
# FEATURE IMPORTANCE
# =============================================================================

def generar_feature_importance(modelo, feature_cols):
    """Extrae y formatea importancia de features."""
    importances = modelo.feature_importances_
    df_imp = pd.DataFrame({
        'feature': feature_cols,
        'importance': importances
    }).sort_values('importance', ascending=False)

    df_imp['importance_pct'] = (df_imp['importance'] / df_imp['importance'].sum() * 100)

    print(f"\n🏆 Feature Importance (XGBoost):")
    print(f"   {'Feature':<20} {'Importancia':>12} {'%':>8}")
    print(f"   {'─'*42}")
    for _, row in df_imp.iterrows():
        bar = '█' * int(row['importance_pct'] / 2)
        print(f"   {row['feature']:<20} {row['importance']:.4f}       "
              f"{row['importance_pct']:5.1f}% {bar}")

    return df_imp


# =============================================================================
# COMPARACIÓN VS ENSEMBLE ACTUAL
# =============================================================================

def comparar_modelos(metricas_xgb, metricas_ensemble):
    """Genera tabla comparativa XGBoost vs Ensemble Prophet+SARIMA."""
    print(f"\n{'='*70}")
    print(f"  COMPARACIÓN: XGBoost vs Ensemble Prophet+SARIMA")
    print(f"{'='*70}")

    rows = []

    # XGBoost
    rows.append({
        'modelo': 'XGBoost (multivariable)',
        'mape_pct': metricas_xgb['mape'] * 100,
        'rmse': metricas_xgb['rmse'],
        'mae': metricas_xgb['mae'],
        'holdout_dias': HOLDOUT_DIAS,
        'status': 'EXPERIMENTO'
    })

    # Ensemble actual
    if metricas_ensemble['mape'] is not None:
        rows.append({
            'modelo': 'Ensemble Prophet+SARIMA',
            'mape_pct': metricas_ensemble['mape'] * 100,
            'rmse': metricas_ensemble['rmse'] if metricas_ensemble['rmse'] else None,
            'mae': None,  # No disponible para ensemble
            'holdout_dias': 30,
            'status': 'PRODUCCIÓN'
        })
    else:
        print("   ⚠️  No se encontraron métricas del ensemble actual en BD")
        rows.append({
            'modelo': 'Ensemble Prophet+SARIMA',
            'mape_pct': None,
            'rmse': None,
            'mae': None,
            'holdout_dias': 30,
            'status': 'PRODUCCIÓN (sin métricas)'
        })

    df_comp = pd.DataFrame(rows)

    # Imprimir tabla
    print(f"\n   {'Modelo':<30} {'MAPE':>8} {'RMSE':>10} {'Status':>15}")
    print(f"   {'─'*65}")
    for _, row in df_comp.iterrows():
        mape_str = f"{row['mape_pct']:.2f}%" if pd.notna(row['mape_pct']) else "N/A"
        rmse_str = f"{row['rmse']:.2f}" if pd.notna(row['rmse']) else "N/A"
        print(f"   {row['modelo']:<30} {mape_str:>8} {rmse_str:>10} {row['status']:>15}")

    # Delta
    if len(rows) >= 2 and pd.notna(rows[0].get('mape_pct')) and pd.notna(rows[1].get('mape_pct')):
        delta_mape = rows[0]['mape_pct'] - rows[1]['mape_pct']
        signo = '+' if delta_mape > 0 else ''
        emoji = '📈' if delta_mape < 0 else '📉' if delta_mape > 0 else '🔄'
        print(f"\n   {emoji} Delta MAPE (XGBoost - Ensemble): {signo}{delta_mape:.2f}pp")
        if delta_mape < 0:
            print(f"   ✅ XGBoost mejora en {abs(delta_mape):.2f}pp")
        elif delta_mape > 0:
            print(f"   ⚠️  Ensemble actual es mejor por {abs(delta_mape):.2f}pp")
        else:
            print(f"   🔄 Rendimiento equivalente")

    return df_comp


# =============================================================================
# GUARDAR RESULTADOS
# =============================================================================

def guardar_resultados(y_test, y_pred, df_importancia, df_comparacion):
    """Guarda todos los CSVs de resultados."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 1. Predicciones vs reales
    df_res = pd.DataFrame({
        'fecha': y_test.index,
        'real': y_test.values,
        'prediccion_xgboost': y_pred,
        'error_abs': np.abs(y_test.values - y_pred),
        'error_pct': np.abs(y_test.values - y_pred) / y_test.values * 100
    })
    path_res = os.path.join(OUTPUT_DIR, 'resultados_xgboost_precio.csv')
    df_res.to_csv(path_res, index=False)
    print(f"\n💾 Resultados guardados:")
    print(f"   → {path_res}")

    # 2. Feature importance
    path_imp = os.path.join(OUTPUT_DIR, 'feature_importance_xgboost.csv')
    df_importancia.to_csv(path_imp, index=False)
    print(f"   → {path_imp}")

    # 3. Comparación modelos
    path_comp = os.path.join(OUTPUT_DIR, 'comparacion_modelos.csv')
    df_comparacion.to_csv(path_comp, index=False)
    print(f"   → {path_comp}")

    # 4. Log completo
    path_log = os.path.join(OUTPUT_DIR, f'xgboost_experiment_{timestamp}.log')
    with open(path_log, 'w') as f:
        f.write(f"FASE 5.B — Experimento XGBoost PRECIO_BOLSA\n")
        f.write(f"Fecha ejecución: {datetime.now().isoformat()}\n")
        f.write(f"Ventana: {VENTANA_MESES} meses, Holdout: {HOLDOUT_DIAS} días\n\n")
        f.write(f"=== Comparación ===\n")
        f.write(df_comparacion.to_string(index=False))
        f.write(f"\n\n=== Feature Importance ===\n")
        f.write(df_importancia.to_string(index=False))
        f.write(f"\n\n=== Detalle predicciones holdout ===\n")
        f.write(df_res.to_string(index=False))
    print(f"   → {path_log}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print(f"\n{'#'*70}")
    print(f"# FASE 5.B — EXPERIMENTO XGBOOST OFFLINE (NO PRODUCCIÓN)")
    print(f"# Métrica: PRECIO_BOLSA (Precio de Bolsa Nacional)")
    print(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*70}")

    # 1. Construir dataset multivariable
    df = construir_dataset()

    # 2. Entrenar y evaluar XGBoost
    modelo, y_test, y_pred, feature_cols, metricas_xgb = entrenar_xgboost(df)

    # 3. Feature importance
    df_importancia = generar_feature_importance(modelo, feature_cols)

    # 4. Cargar métricas del ensemble actual de BD
    metricas_ensemble = cargar_metricas_ensemble_actual()

    # 5. Comparar modelos
    df_comparacion = comparar_modelos(metricas_xgb, metricas_ensemble)

    # 6. Guardar resultados CSV
    guardar_resultados(y_test, y_pred, df_importancia, df_comparacion)

    print(f"\n{'='*70}")
    print(f"  ✅ Experimento completado — resultados en experiments/")
    print(f"  ⚠️  NO integrar a producción sin validación adicional")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    main()
