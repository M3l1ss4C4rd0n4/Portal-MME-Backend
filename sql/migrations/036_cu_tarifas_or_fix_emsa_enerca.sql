-- Migración 036 — Fase 40 (Costo Unitario): corrige etiquetado real de EMSA/ENERCA en cu_tarifas_or
--
-- Contexto: al revisar el Boletín Tarifario SSPD Q4-2025 (Tabla 26, "Operadores
-- de Red y mercados" — el LAC calcula cargos por uso para 26 ORs / 28 mercados)
-- se encontró que cu_tarifas_or.or_nombre/departamentos para EMSA y ENERCA
-- estaban intercambiados/equivocados desde antes de esta sesión:
--
--   EMSA    (BD, antes): "Empresa de Energía del Casanare ESP" / "Casanare"
--   EMSA    (real):      Electrificadora del Meta S.A. E.S.P. — sirve Meta.
--                         Confirmado: SSPD Tabla 26 ("EMSA↔Meta") +
--                         electrificadoradelmeta.com.co + BNamericas.
--
--   ENERCA  (BD, antes): "Empresa de Energía del Caquetá (ENERCA)" /
--                         "Amazonas, Vaupés, Guainía"
--   ENERCA  (real):      Empresa de Energía de Casanare S.A. E.S.P. — sirve
--                         Casanare, sede en Yopal. Confirmado: SSPD Tabla 26
--                         ("ENERCA↔Casanare") + BNamericas + Devex.
--
-- Sin este fix, cualquier cruce por departamento (ej. el mapeo mercado↔OR de
-- scripts/cu/build_mercado_or_alias.py) habría asignado Meta/Casanare a los
-- operadores equivocados. Los valores de d_cop_kwh/c_cop_kwh/perdidas_pct
-- de estas 2 filas NO se tocan aquí — son cargos reales de SSPD por operador,
-- el bug estaba solo en cómo se identificaba a qué operador/departamento
-- correspondía cada fila, no en los cargos numéricos en sí.

UPDATE cu_tarifas_or
SET or_nombre   = 'Electrificadora del Meta S.A. E.S.P.',
    departamentos = 'Meta',
    updated_at  = now()
WHERE or_codigo = 'EMSA';

UPDATE cu_tarifas_or
SET or_nombre   = 'Empresa de Energía de Casanare S.A. E.S.P. (ENERCA)',
    departamentos = 'Casanare',
    updated_at  = now()
WHERE or_codigo = 'ENERCA';
