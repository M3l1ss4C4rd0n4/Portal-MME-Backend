-- Migración 038 — Fase 40 (Costo Unitario), Ronda 3: pesos de demanda real
-- por operador de red, para que el promedio nacional del CU Usuario Final
-- (CUMinoristaService.get_promedio_nacional_minorista(), usado en TODOS los
-- lugares que muestran ese KPI: home.py Dash, costo_usuario_final.py Dash,
-- y el portal Next.js vía /v1/cu/minorista/promedio-nacional) deje de ser
-- un promedio simple (igual peso entre 26 operadores) y pase a ser un
-- promedio ponderado por la demanda real de cada uno — más preciso,
-- reemplaza por completo el valor anterior en cada lugar donde se muestra.
--
-- A diferencia de cu_componentes_nacionales_ponderados (agrega D/C/pérdidas
-- a nivel nacional), esta tabla guarda el peso normalizado POR OPERADOR
-- (agregando todos los mercados que ese operador cubre, ej. CELSIA =
-- TOLIMA + VALLE DEL CAUCA), para poder ponderar directamente
-- cu_minorista_total (que ya incluye todos los componentes reales de cada
-- operador) sin reconstruir la fórmula del CU.

CREATE TABLE IF NOT EXISTS cu_pesos_demanda_or (
    mes                     DATE NOT NULL,
    or_codigo               TEXT NOT NULL REFERENCES cu_tarifas_or(or_codigo),
    peso_normalizado        NUMERIC NOT NULL,  -- suma 1.0 entre los OR resueltos ese mes
    demanda_kwh_mes         NUMERIC NOT NULL,
    pct_demanda_cubierta    NUMERIC NOT NULL,  -- mismo valor para todas las filas del mes
    actualizado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (mes, or_codigo)
);

COMMENT ON TABLE cu_pesos_demanda_or IS
    'Fase 40 Ronda 3: peso de demanda real por operador de red (agregado '
    'desde cu_mercado_or_alias x DemaCome por MercadoComercializacion), '
    'usado por CUMinoristaService para ponderar el promedio nacional del '
    'CU Usuario Final en vez de promediar con igual peso entre operadores.';
