-- Migración 039 — Fase 41 (predicciones de embalses), continuación: persistir
-- el resultado de main_backtest() en una tabla real en vez de solo un JSON
-- en disco (logs/backtest_<año>.json), para que el portal pueda mostrar
-- SIEMPRE la validación out-of-sample rigurosa (no la del holdout de
-- entrenamiento de 180 días, que resultó ser optimista — 4.5% vs. 9.3% real
-- verificado en la corrida del 2026-08-26) sin depender de un archivo local
-- ni de un número hardcodeado en el frontend.

CREATE TABLE IF NOT EXISTS predictions_backtest_history (
    id                  SERIAL PRIMARY KEY,
    fuente              TEXT NOT NULL,
    modelo              TEXT NOT NULL,
    anio_corte          INTEGER NOT NULL,       -- entrenado hasta 31-dic de este año
    fecha_test_inicio   DATE NOT NULL,
    fecha_test_fin      DATE NOT NULL,
    n_dias_test         INTEGER NOT NULL,
    mape_train_holdout  DOUBLE PRECISION,       -- referencia: el MAPE optimista del holdout de 180d
    mape_expost         DOUBLE PRECISION NOT NULL,  -- el número riguroso real, out-of-sample genuino
    cobertura_ci_95     DOUBLE PRECISION,
    modelo_robusto      BOOLEAN,
    ejecutado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fuente, modelo, anio_corte)
);

COMMENT ON TABLE predictions_backtest_history IS
    'Fase 41: resultados de main_backtest() (validación out-of-sample real, '
    'entrena hasta 31-dic de un año y valida contra el período siguiente '
    'completo) — la fuente de verdad para la precisión que se comunica '
    'públicamente en el portal, en vez del MAPE optimista de un holdout '
    'de entrenamiento de 180 días.';
