-- Migración: persistir MAPEs y pesos por modelo en la tabla predictions
-- Permite que _adjust_weights_from_history() use historial real de entrenamientos
-- Columnas NULL-able → retrocompatible, sin downtime, sin cambio en rows existentes

ALTER TABLE predictions
  ADD COLUMN IF NOT EXISTS mape_prophet DECIMAL(6,4),
  ADD COLUMN IF NOT EXISTS mape_sarima  DECIMAL(6,4),
  ADD COLUMN IF NOT EXISTS peso_prophet DECIMAL(4,3),
  ADD COLUMN IF NOT EXISTS peso_sarima  DECIMAL(4,3);

CREATE INDEX IF NOT EXISTS idx_predictions_fuente_gen
  ON predictions(fuente, fecha_generacion DESC);

COMMENT ON COLUMN predictions.mape_prophet IS 'MAPE del modelo Prophet solo en el holdout de entrenamiento';
COMMENT ON COLUMN predictions.mape_sarima  IS 'MAPE del modelo SARIMAX solo en el holdout de entrenamiento';
COMMENT ON COLUMN predictions.peso_prophet IS 'Peso asignado a Prophet en el ensemble final (0.0–1.0)';
COMMENT ON COLUMN predictions.peso_sarima  IS 'Peso asignado a SARIMAX en el ensemble final (0.0–1.0)';
