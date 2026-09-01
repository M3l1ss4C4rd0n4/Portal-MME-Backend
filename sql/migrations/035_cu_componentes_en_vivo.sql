-- Migración 035 — Fase 40 (Costo Unitario): fuentes en vivo para T/D/C
--
-- Contexto: CUService (domain/services/cu_service.py) usa hoy 3 cargos
-- FIJOS hardcodeados en core/config.py (CARGO_TRANSMISION_COP_KWH=8.5,
-- CARGO_DISTRIBUCION_COP_KWH=35.0, CARGO_COMERCIALIZACION_COP_KWH=12.0),
-- sin fecha de verificación conocida ni mecanismo de actualización.
--
-- La Resolución CREG 119 de 2007 (art. 4, mod. Res. CREG 101-28/2023) define:
--   T: varía SOLO por mes, valor NACIONAL único → XM publica CargoUsoSTN.
--   D, Cv, PR: varían por comercializador/mercado → cu_tarifas_or (26 ORs
--   reales, fuente SSPD) ya tiene estos datos, pero nunca se cruzó con
--   XM (DemaCome por MercadoComercializacion) para ponderar un promedio
--   nacional defendible.
--
-- Estas 3 tablas nuevas NO reemplazan cu_daily ni el cálculo en vivo de
-- CUService todavía — son la capa de datos que permite calcular T/D/C con
-- fuente real y auditable, para comparar contra los valores hardcodeados
-- actuales antes de decidir si se conmuta el cálculo en producción.

CREATE TABLE IF NOT EXISTS cargo_stn_mensual (
    mes                     DATE PRIMARY KEY,  -- primer día del mes (XM publica mensual)
    cargo_stn_cop_total     NUMERIC NOT NULL,   -- CargoUsoSTN crudo de XM (COP, total del mes)
    demacome_kwh_mes        NUMERIC NOT NULL,   -- DemaCome (Sistema) sumado del mes, en kWh
    cargo_stn_cop_kwh       NUMERIC NOT NULL,   -- = cargo_stn_cop_total / demacome_kwh_mes
    fuente                  TEXT NOT NULL DEFAULT 'XM_CargoUsoSTN_pydataxm',
    actualizado_en          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE cargo_stn_mensual IS
    'Fase 40: componente T (transmisión STN) del Costo Unitario, calculado '
    'en vivo desde CargoUsoSTN de XM (mensual, valor nacional único por '
    'Art. 4 Res. CREG 119/2007) dividido entre la demanda comercial '
    'nacional del mismo mes. Alimenta scripts/cu/etl_cargo_stn.py.';

CREATE TABLE IF NOT EXISTS cu_mercado_or_alias (
    mercado         TEXT PRIMARY KEY,   -- valor real de sector_energetico.metrics.recurso
                                         -- (entidad='MercadoComercializacion', métrica='DemaCome')
    or_codigo       TEXT REFERENCES cu_tarifas_or(or_codigo),
    metodo          TEXT NOT NULL CHECK (metodo IN (
                        'match_exacto_departamento',
                        'match_dominante_departamento',
                        'sin_resolver'
                    )),
    nota            TEXT,               -- justificación de la curación / motivo de no-resolución
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE cu_mercado_or_alias IS
    'Fase 40: mapeo curado (mercado de comercialización XM) -> (operador '
    'de red cu_tarifas_or), usado para ponderar D/C/pérdidas nacional por '
    'demanda real. Nunca auto-generado por coincidencia difusa — cada fila '
    'con or_codigo no nulo fue verificada manualmente contra el texto real '
    'de "departamentos" de cu_tarifas_or. Mercados genuinamente ambiguos '
    '(más de un operador real superpuesto, o sin operador identificable) '
    'quedan con or_codigo NULL y metodo=''sin_resolver'', nunca adivinados.';

CREATE TABLE IF NOT EXISTS cu_componentes_nacionales_ponderados (
    mes                     DATE PRIMARY KEY,
    d_pond_cop_kwh          NUMERIC,
    c_pond_cop_kwh          NUMERIC,
    perdidas_pond_pct       NUMERIC,
    n_mercados_ponderados   INTEGER NOT NULL,
    n_mercados_sin_resolver INTEGER NOT NULL,
    pct_demanda_cubierta    NUMERIC,   -- % de la demanda nacional del mes cubierta por mercados resueltos
    fuente                  TEXT NOT NULL DEFAULT 'cu_tarifas_or_SSPD_ponderado_DemaCome_XM',
    actualizado_en          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE cu_componentes_nacionales_ponderados IS
    'Fase 40: promedio nacional REAL ponderado de D/C/pérdidas, calculado '
    'como suma(valor_operador * peso_demanda_mercado) / suma(pesos), usando '
    'solo los mercados con or_codigo resuelto en cu_mercado_or_alias — '
    'pct_demanda_cubierta deja explícito qué fracción de la demanda '
    'nacional real respalda el promedio (nunca se fuerza cobertura del '
    '100% inventando mapeos inciertos).';
