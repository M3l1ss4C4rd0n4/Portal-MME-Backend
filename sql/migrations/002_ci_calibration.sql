-- Migración 002: Calibración empírica de intervalos de confianza
-- Añade factor de calibración y cobertura CI medida sobre holdout
-- Campos opcionales (NULL para predicciones anteriores a esta migración)

ALTER TABLE predictions
  ADD COLUMN IF NOT EXISTS factor_calibracion DECIMAL(5,4),
  ADD COLUMN IF NOT EXISTS cobertura_ci       DECIMAL(5,4);
