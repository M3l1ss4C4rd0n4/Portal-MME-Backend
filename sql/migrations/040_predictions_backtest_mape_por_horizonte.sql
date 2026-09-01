-- Fase 41 (2026-08-30): el MAPE fuera de muestra que ya se calcula en
-- predictions_backtest_history mezcla en un solo número el error a 30 días
-- con el error a 730 días — un pronóstico a 2 años es intrínsecamente menos
-- confiable que uno a 1 mes, así que un promedio único puede transmitir más
-- (o menos) certeza de la que hay evidencia real para respaldar en cada
-- horizonte. Esta columna guarda el desglose real por horizonte
-- (30/90/180/365/730 días), calculado por main_backtest() en
-- scripts/train_predictions_sector_energetico.py.
ALTER TABLE predictions_backtest_history
    ADD COLUMN IF NOT EXISTS mape_por_horizonte JSONB;

COMMENT ON COLUMN predictions_backtest_history.mape_por_horizonte IS
    'Desglose del MAPE ex-post por horizonte de días desde el corte de entrenamiento (ej. {"30": {"mape": 0.05, "n_dias": 30}, "90": {...}, ...}). NULL para filas generadas antes de esta migración.';
