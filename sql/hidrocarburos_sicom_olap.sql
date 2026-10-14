-- ═══════════════════════════════════════════════════════════════════════════════
-- Esquema hidrocarburos — bases SICOM extraídas DIRECTAMENTE de los cubos OLAP
--
-- Convive con las tablas sicom_* que vienen del Excel de OneDrive: estas llevan
-- sufijo _olap y permiten contrastar ambas rutas antes de cambiar la fuente de
-- los tableros. Las diferencias entre una y otra no son menores (ver la vista
-- v_sicom_contraste y docs/SICOM_HIDROCARBUROS.md).
--
-- Tres cosas que el Excel no tenía y aquí sí:
--   · el CÓDIGO SICOM del agente, que permite contar agentes sin duplicar
--   · los CÓDIGOS DANE de departamento y municipio, que eliminan la ambigüedad
--     de los 67 nombres de municipio homónimos
--   · la dimensión CICLO en capacidad, que el Excel colapsaba sumando 17 años
--
-- DDL idempotente, lo aplica etl/etl_sicom_olap.py en cada corrida.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS hidrocarburos;

-- ─── AGENTES ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_olap_agentes (
    id                                   BIGSERIAL PRIMARY KEY,
    codigo_sicom_agente                  TEXT,
    operador_nombre_comercial            TEXT,
    tipo_agente                          TEXT,
    subtipo_agente                       TEXT,
    nuevo_estado                         TEXT,
    anio_creacion                        INTEGER,
    bandera                              TEXT,
    nombre_comercial_proveedor           TEXT,
    departamento_instalacion             TEXT,
    codigo_dane_departamento_instalacion TEXT,
    municipio_instalacion                TEXT,
    codigo_dane_municipio_instalacion    TEXT,
    operada_por                          TEXT,
    producto_a_comercializar             TEXT,
    tipo_estacion                        TEXT,
    agente_cantidad                      NUMERIC,
    fecha_carga                          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── CAPACIDAD ────────────────────────────────────────────────────────────────
-- Con CICLO, que es lo que faltaba: la capacidad se declara por ciclo, así que
-- sumarla a lo largo de los años no da la capacidad instalada sino un acumulado
-- de declaraciones.
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_olap_capacidad (
    id                                   BIGSERIAL PRIMARY KEY,
    anio_ciclo                           INTEGER,
    mes_ciclo                            INTEGER,
    codigo_sicom_agente                  TEXT,
    nombre_comercial_agente              TEXT,
    tipo_agente                          TEXT,
    subtipo_agente                       TEXT,
    departamento_instalacion             TEXT,
    codigo_dane_departamento_instalacion TEXT,
    municipio_instalacion                TEXT,
    codigo_dane_municipio_instalacion    TEXT,
    producto                             TEXT,
    descripcion_producto                 TEXT,
    capacidad_operativa                  NUMERIC,
    fecha_carga                          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── COMPRAS ──────────────────────────────────────────────────────────────────
-- Una sola tabla de hechos. "Compras" y "Compras EDS" del tablero son dos
-- lecturas distintas de esta misma tabla (ver vistas abajo): el Excel las
-- trataba como bases separadas porque cada una era una tabla dinámica aparte.
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_olap_compras (
    id                                        BIGSERIAL PRIMARY KEY,
    anio_ciclo                                INTEGER,
    mes_ciclo                                 INTEGER,
    codigo_sicom_agente_comprador             TEXT,
    nombre_comercial_agente_comprador         TEXT,
    tipo_agente_comprador                     TEXT,
    subtipo_agente_comprador                  TEXT,
    departamento_agente_comprador             TEXT,
    codigo_dane_departamento_agente_comprador TEXT,
    municipio_agente_comprador                TEXT,
    codigo_dane_municipio_agente_comprador    TEXT,
    -- Identidad del proveedor por PLANTA, no por agente: el 30,8 % del volumen
    -- está registrado sin agente proveedor, y cruzar por esa dimensión descarta
    -- esas filas en silencio (es lo que hacía perder el 25 % al Excel).
    planta_agente_proveedor                   TEXT,
    departamento_planta_agente_proveedor      TEXT,
    codigo_dane_departamento_planta_proveedor TEXT,
    municipio_planta_agente_proveedor         TEXT,
    codigo_dane_municipio_planta_proveedor    TEXT,
    producto                                  TEXT,
    descripcion_producto                      TEXT,
    volumen_comprado                          NUMERIC,
    volumen_transito                          NUMERIC,
    fecha_carga                               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Control de carga y conciliación ──────────────────────────────────────────
-- A diferencia de la ruta de Excel, aquí el patrón de referencia es el TOTAL
-- GENERAL que el propio cubo declara al consultarlo sin dimensiones. Es una
-- conciliación mucho más fuerte que la fila "Total general" de una hoja.
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_olap_control (
    id                  BIGSERIAL PRIMARY KEY,
    base                TEXT NOT NULL,
    catalogo            TEXT NOT NULL,
    cubo                TEXT NOT NULL,
    medida              TEXT NOT NULL,
    filas_cargadas      BIGINT NOT NULL,
    suma_detalle        NUMERIC,
    total_cubo          NUMERIC,
    gap_abs             NUMERIC,
    gap_pct             NUMERIC,
    concilia            BOOLEAN,
    identidades         BIGINT,      -- COUNT(DISTINCT) de la clave de identidad
    segundos            NUMERIC,
    -- Las recargas incrementales (--desde) no cubren toda la historia, así que
    -- sus cifras no son comparables ni conciliables. Se marcan para excluirlas
    -- del contraste, donde si no aparecerían como desvíos del -100 %.
    parcial             BOOLEAN NOT NULL DEFAULT FALSE,
    -- Las corridas fallidas no dejan rastro en esta tabla si solo se
    -- insertara dentro de la transacción (el rollback la deshace), así que
    -- se registran aparte con el motivo.
    error               TEXT,
    fecha_carga         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE hidrocarburos.sicom_olap_control
    ADD COLUMN IF NOT EXISTS parcial BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS error   TEXT;

-- Columna que se definió pero nunca se llegó a poblar.
ALTER TABLE hidrocarburos.sicom_olap_control
    DROP COLUMN IF EXISTS total_cubo_conteo;

-- ─── Índices ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_olap_agentes_codigo   ON hidrocarburos.sicom_olap_agentes (codigo_sicom_agente);
CREATE INDEX IF NOT EXISTS idx_olap_agentes_tipo     ON hidrocarburos.sicom_olap_agentes (tipo_agente);
CREATE INDEX IF NOT EXISTS idx_olap_agentes_estado   ON hidrocarburos.sicom_olap_agentes (nuevo_estado);
CREATE INDEX IF NOT EXISTS idx_olap_agentes_depto    ON hidrocarburos.sicom_olap_agentes (codigo_dane_departamento_instalacion);

CREATE INDEX IF NOT EXISTS idx_olap_capacidad_ciclo  ON hidrocarburos.sicom_olap_capacidad (anio_ciclo, mes_ciclo);
CREATE INDEX IF NOT EXISTS idx_olap_capacidad_depto  ON hidrocarburos.sicom_olap_capacidad (codigo_dane_departamento_instalacion);
CREATE INDEX IF NOT EXISTS idx_olap_capacidad_tipo   ON hidrocarburos.sicom_olap_capacidad (tipo_agente);

CREATE INDEX IF NOT EXISTS idx_olap_compras_ciclo    ON hidrocarburos.sicom_olap_compras (anio_ciclo, mes_ciclo);
CREATE INDEX IF NOT EXISTS idx_olap_compras_subtipo  ON hidrocarburos.sicom_olap_compras (subtipo_agente_comprador);
CREATE INDEX IF NOT EXISTS idx_olap_compras_prov     ON hidrocarburos.sicom_olap_compras (codigo_dane_departamento_planta_proveedor);
CREATE INDEX IF NOT EXISTS idx_olap_compras_producto ON hidrocarburos.sicom_olap_compras (producto);

CREATE INDEX IF NOT EXISTS idx_olap_control_base     ON hidrocarburos.sicom_olap_control (base, fecha_carga DESC);

-- ─── Vistas de lectura para los tableros ──────────────────────────────────────

-- "Compras EDS" = compras cuyo comprador es una estación de servicio.
-- El criterio queda aquí, visible y auditable, en vez de escondido en el MDX.
CREATE OR REPLACE VIEW hidrocarburos.v_sicom_olap_compras_eds AS
SELECT *
FROM hidrocarburos.sicom_olap_compras
WHERE subtipo_agente_comprador ILIKE 'ESTACION DE SERVICIO%';

-- Contraste cubo vs Excel, por base y medida.
CREATE OR REPLACE VIEW hidrocarburos.v_sicom_contraste AS
WITH olap AS (
    -- Solo cargas completas: una incremental cubre dos años y compararla contra
    -- el Excel daría un desvío cercano al -100 % que no significa nada.
    SELECT DISTINCT ON (base) base, filas_cargadas, suma_detalle, total_cubo, identidades, fecha_carga
    FROM hidrocarburos.sicom_olap_control
    WHERE NOT parcial
    ORDER BY base, fecha_carga DESC
), excel AS (
    SELECT DISTINCT ON (tabla) tabla, filas_cargadas, suma_detalle, fecha_carga
    FROM hidrocarburos.sicom_carga_control ORDER BY tabla, fecha_carga DESC
)
SELECT o.base,
       o.filas_cargadas          AS filas_cubo,
       e.filas_cargadas          AS filas_excel,
       o.suma_detalle            AS suma_cubo,
       e.suma_detalle            AS suma_excel,
       o.total_cubo              AS total_declarado_cubo,
       o.identidades,
       round(100.0 * (o.suma_detalle - e.suma_detalle) / NULLIF(e.suma_detalle, 0), 2) AS dif_pct,
       o.fecha_carga             AS cargado_cubo,
       e.fecha_carga             AS cargado_excel
FROM olap o
LEFT JOIN excel e ON e.tabla = 'sicom_' || o.base;

-- ─── Grants ───────────────────────────────────────────────────────────────────
GRANT USAGE ON SCHEMA hidrocarburos TO mme_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hidrocarburos TO mme_user;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA hidrocarburos GRANT SELECT ON TABLES TO mme_user;
