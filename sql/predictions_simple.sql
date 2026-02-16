-- Tabla simple de predicciones
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    fecha_prediccion DATE NOT NULL,
    fecha_generacion TIMESTAMP DEFAULT NOW(),
    fuente VARCHAR(50) NOT NULL,
    valor_gwh_predicho DECIMAL(10, 2) NOT NULL,
    intervalo_inferior DECIMAL(10, 2),
    intervalo_superior DECIMAL(10, 2),
    horizonte_dias INTEGER DEFAULT 90,
    modelo VARCHAR(50) DEFAULT 'ENSEMBLE_v1.0',
    confianza DECIMAL(3, 2) DEFAULT 0.95,
    mape DECIMAL(5, 4),
    rmse DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_prediction UNIQUE(fuente, fecha_prediccion, modelo)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_predictions_fuente ON predictions(fuente);
CREATE INDEX IF NOT EXISTS idx_predictions_fecha ON predictions(fecha_prediccion);
CREATE INDEX IF NOT EXISTS idx_predictions_fuente_fecha ON predictions(fuente, fecha_prediccion);
CREATE INDEX IF NOT EXISTS idx_predictions_generacion ON predictions(fecha_generacion);
CREATE INDEX IF NOT EXISTS idx_predictions_modelo ON predictions(modelo);

-- Comentarios
COMMENT ON TABLE predictions IS 'Predicciones de generación eléctrica por fuente usando Machine Learning';
COMMENT ON COLUMN predictions.fuente IS 'Tipo de fuente: Hidráulica, Térmica, Eólica, Solar, Biomasa';
COMMENT ON COLUMN predictions.modelo IS 'Versión del modelo ML: ENSEMBLE_v1.0, Prophet_v1.0, SARIMA_v1.0';
COMMENT ON COLUMN predictions.mape IS 'Mean Absolute Percentage Error - Objetivo: < 0.05 (5%)';
