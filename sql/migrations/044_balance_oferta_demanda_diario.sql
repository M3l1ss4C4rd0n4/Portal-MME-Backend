-- Migración 044: sector_energetico.balance_oferta_demanda_diario — Fase 45b
--
-- Contexto (2026-09-23): tras el backfill histórico de la migración 043
-- (DemaReal/DispoDeclarada/CapEfecNeta desde 2000, ENFICC/ObligEnerFirme
-- desde 2007), sector_energetico.metrics pasó de ~10M a 49.6M filas. El
-- tablero de Balance Oferta-Demanda agregaba estas métricas EN VIVO sobre
-- la tabla cruda en cada request (GROUP BY fecha sobre ~40M filas
-- calificantes cuando no se pasan fechas explícitas) — verificado con
-- EXPLAIN ANALYZE: 4-9 segundos por consulta, suficiente para agotar el
-- timeout de 15s del BFF cuando el frontend dispara 3-4 consultas en
-- paralelo (Promise.all), dejando el tablero sin datos en el navegador.
--
-- Esta tabla es un resumen diario PRECALCULADO (mismo patrón ya usado en
-- este proyecto por sector_energetico.estado_sin_diario, ver
-- scripts/backtest_alertas.py) — reduce la consulta del tablero de "agregar
-- ~40M filas" a "leer ~9800 filas ya agregadas", sin cambiar ninguna
-- fórmula ni criterio de negocio (los valores son exactamente los mismos
-- que calculaba BalanceOfertaDemandaRepository.get_serie_diaria_oferta_demanda()
-- antes de esta migración).
--
-- Poblada por scripts/refrescar_balance_oferta_demanda_diario.py — correr
-- una vez para el histórico completo, y periódicamente (cron sugerido:
-- diario, después del ETL de XM) para incorporar los días nuevos.

CREATE TABLE IF NOT EXISTS sector_energetico.balance_oferta_demanda_diario (
    fecha                DATE PRIMARY KEY,
    oferta_declarada_mw  NUMERIC(12, 4),
    demanda_real_gwh     NUMERIC(12, 6),
    generacion_real_gwh  NUMERIC(12, 6),
    enficc_gwh           NUMERIC(12, 6),
    oef_gwh              NUMERIC(12, 6),
    actualizado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE sector_energetico.balance_oferta_demanda_diario IS
    'Resumen diario precalculado de oferta/demanda/margen regulatorio para '
    'el tablero Balance Oferta-Demanda — evita agregar en vivo sobre '
    'sector_energetico.metrics (49.6M filas). Repoblar con '
    'scripts/refrescar_balance_oferta_demanda_diario.py tras cada backfill '
    'o periódicamente vía cron para los días nuevos.';
