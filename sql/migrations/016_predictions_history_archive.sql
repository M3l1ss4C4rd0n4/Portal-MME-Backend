-- Migración 016: Archivar predictions eliminadas (retrains) en predictions_history
-- Resuelve: (1) el monitor de calidad ex-post no puede acumular MIN_DIAS_OVERLAP=3
--           antes de que el retrain siguiente borre el batch vigente;
--           (2) _adjust_weights_from_history() solo ve el batch vivo (1 fila),
--           nunca los últimos 5 runs como fue diseñado en 001_predictions_per_model_mape.sql.
-- No modifica la tabla predictions ni ningún script escritor: un trigger
-- BEFORE DELETE copia la fila saliente antes de que desaparezca.

CREATE TABLE IF NOT EXISTS predictions_history (
    id                  BIGSERIAL PRIMARY KEY,
    id_original         INTEGER,                 -- predictions.id original (sin FK: la fila ya fue borrada)
    fecha_prediccion    DATE NOT NULL,
    fecha_generacion    TIMESTAMP,
    fuente              VARCHAR(50) NOT NULL,
    valor_gwh_predicho  NUMERIC(10, 2) NOT NULL,
    intervalo_inferior  NUMERIC(10, 2),
    intervalo_superior  NUMERIC(10, 2),
    horizonte_dias      INTEGER,
    modelo              VARCHAR(50),
    confianza           NUMERIC(3, 2),
    mape                NUMERIC(5, 4),
    rmse                NUMERIC(10, 2),
    metodo_prediccion   VARCHAR(50),
    mape_prophet        NUMERIC(6, 4),
    mape_sarima         NUMERIC(6, 4),
    peso_prophet        NUMERIC(4, 3),
    peso_sarima         NUMERIC(4, 3),
    factor_calibracion  NUMERIC(5, 4),
    cobertura_ci        NUMERIC(5, 4),
    created_at          TIMESTAMP,                -- created_at original de predictions
    updated_at          TIMESTAMP,                -- updated_at original de predictions
    archived_at         TIMESTAMP NOT NULL DEFAULT NOW()   -- momento del DELETE/archivado
);

-- Consumidor 1: monitor_predictions_quality.py — necesita todos los batches
-- de una fuente ordenados por fecha_generacion, y por fecha_prediccion dentro de un batch.
CREATE INDEX IF NOT EXISTS idx_pred_hist_fuente_gen
    ON predictions_history(fuente, fecha_generacion DESC);
CREATE INDEX IF NOT EXISTS idx_pred_hist_fuente_fecha_pred
    ON predictions_history(fuente, fecha_prediccion);

-- Consumidor 2: _adjust_weights_from_history() — últimos N runs de una fuente
-- con MAPEs per-model no nulos (lo único que esa query filtra).
CREATE INDEX IF NOT EXISTS idx_pred_hist_fuente_gen_mapes
    ON predictions_history(fuente, fecha_generacion DESC)
    WHERE mape_prophet IS NOT NULL AND mape_sarima IS NOT NULL;

-- Evitar archivar dos veces la misma fila original (defensivo; no debería
-- ocurrir en operación normal ya que id_original solo se archiva una vez
-- por su propio DELETE, pero protege contra reintentos accidentales).
CREATE UNIQUE INDEX IF NOT EXISTS uq_pred_hist_id_original
    ON predictions_history(id_original) WHERE id_original IS NOT NULL;

COMMENT ON TABLE predictions_history IS
  'Archivo de filas borradas de predictions (retrains). Poblada automáticamente '
  'por el trigger trg_predictions_archive_on_delete. Permite evaluación ex-post '
  'de batches ya reemplazados y reweighting adaptativo con historial real.';
COMMENT ON COLUMN predictions_history.id_original IS
  'id original en predictions (no FK: la fila fuente ya fue eliminada)';
COMMENT ON COLUMN predictions_history.archived_at IS
  'Momento en que la fila fue archivada (= momento del DELETE en predictions)';

-- ── Función y trigger de archivado ──
CREATE OR REPLACE FUNCTION fn_predictions_archive_on_delete()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO predictions_history (
        id_original, fecha_prediccion, fecha_generacion, fuente,
        valor_gwh_predicho, intervalo_inferior, intervalo_superior,
        horizonte_dias, modelo, confianza, mape, rmse,
        metodo_prediccion, mape_prophet, mape_sarima,
        peso_prophet, peso_sarima, factor_calibracion, cobertura_ci,
        created_at, updated_at
    ) VALUES (
        OLD.id, OLD.fecha_prediccion, OLD.fecha_generacion, OLD.fuente,
        OLD.valor_gwh_predicho, OLD.intervalo_inferior, OLD.intervalo_superior,
        OLD.horizonte_dias, OLD.modelo, OLD.confianza, OLD.mape, OLD.rmse,
        OLD.metodo_prediccion, OLD.mape_prophet, OLD.mape_sarima,
        OLD.peso_prophet, OLD.peso_sarima, OLD.factor_calibracion, OLD.cobertura_ci,
        OLD.created_at, OLD.updated_at
    )
    ON CONFLICT (id_original) WHERE id_original IS NOT NULL DO NOTHING;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Salvaguarda: si por algún motivo hay una transacción de reentrenamiento en
-- vuelo justo al aplicar esta migración, fallar rápido en vez de bloquear
-- lecturas de la API en cola detrás del ACCESS EXCLUSIVE de CREATE TRIGGER.
SET LOCAL lock_timeout = '5s';

DROP TRIGGER IF EXISTS trg_predictions_archive_on_delete ON predictions;
CREATE TRIGGER trg_predictions_archive_on_delete
    BEFORE DELETE ON predictions
    FOR EACH ROW
    EXECUTE FUNCTION fn_predictions_archive_on_delete();

COMMENT ON TRIGGER trg_predictions_archive_on_delete ON predictions IS
  'Archiva cada fila en predictions_history antes de que un retrain la elimine. '
  'No requiere cambios en train_predictions_sector_energetico.py ni train_predictions_postgres.py.';

-- ── Trazabilidad de qué batch fue evaluado en cada fila de quality_history ──
ALTER TABLE predictions_quality_history
    ADD COLUMN IF NOT EXISTS fecha_generacion TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_pqh_fuente_gen
    ON predictions_quality_history(fuente, fecha_generacion DESC);

COMMENT ON COLUMN predictions_quality_history.fecha_generacion IS
  'fecha_generacion del batch de predictions/predictions_history evaluado; '
  'permite deduplicar evaluaciones repetidas del mismo batch.';
