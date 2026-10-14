-- ═══════════════════════════════════════════════════════════════════════════════
-- Esquema hidrocarburos — bases SICOM (Sistema de Información de Combustibles)
--
-- Fuente: cubos OLAP de SICOM, exportados a Excel por la Dirección de
-- Hidrocarburos y depositados en OneDrive (carpeta "Datos de hidrocarburos").
-- Metodología: "Informe de Consolidación y Análisis de Información de
-- Combustibles" §6-9 (estructura de las 4 bases) y §17 (controles de calidad).
--
-- DDL idempotente, auto-aplicado por etl/etl_hidrocarburos_sicom.py en cada
-- corrida — mismo patrón que sql/hidrocarburos_schema.sql.
--
-- Los cubos son SNAPSHOTS completos sin clave natural estable (un mismo agente
-- aparece en varias filas), por eso la carga es TRUNCATE + COPY, no UPSERT.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS hidrocarburos;

-- ─── Base AGENTES (metodología §6) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_agentes (
    id                          BIGSERIAL PRIMARY KEY,
    operador_nombre_comercial   TEXT,
    tipo_agente                 TEXT,
    subtipo_agente              TEXT,
    anio_creacion               INTEGER,
    bandera                     TEXT,
    nombre_comercial_proveedor  TEXT,
    departamento_instalacion    TEXT,
    operada_por                 TEXT,
    producto_a_comercializar    TEXT,
    tipo_estacion               TEXT,
    agente_cantidad             NUMERIC,
    fecha_carga                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Base CAPACIDAD (metodología §7) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_capacidad (
    id                        BIGSERIAL PRIMARY KEY,
    departamento_instalacion  TEXT,
    municipio_instalacion     TEXT,
    nombre_comercial_agente   TEXT,
    subtipo_agente            TEXT,
    tipo_agente               TEXT,
    producto                  TEXT,
    descripcion_producto      TEXT,
    capacidad_operativa       NUMERIC,
    fecha_carga               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Base COMPRAS (metodología §8) ────────────────────────────────────────────
-- Nota de control resuelta: la metodología §8 reportaba "Tipo agente comprador"
-- duplicado. El archivo real tiene TIPO AGENTE COMPRADOR y TIPO AGENTE PROVEEDOR
-- (campos distintos), más dos municipios de planta (comprador y proveedor).
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_compras (
    id                                BIGSERIAL PRIMARY KEY,
    nombre_comercial_agente_comprador TEXT,
    tipo_agente_comprador             TEXT,
    municipio_agente_proveedor        TEXT,
    tipo_agente_proveedor             TEXT,
    anio_ciclo                        INTEGER,
    municipio_planta_agente_comprador TEXT,
    municipio_planta_agente_proveedor TEXT,
    volumen_comprado                  NUMERIC,
    volumen_transito                  NUMERIC,
    fecha_carga                       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Base COMPRAS EDS (metodología §9) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_compras_eds (
    id                         BIGSERIAL PRIMARY KEY,
    nombre_comercial_comprador TEXT,
    nombre_comercial_proveedor TEXT,
    producto                   TEXT,
    anio_ciclo                 INTEGER,
    mes_ciclo                  INTEGER,
    volumen_compra_eds         NUMERIC,
    fecha_carga                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Control de carga / trazabilidad (metodología §17-18) ─────────────────────
-- Una fila por tabla y por corrida. Guarda la conciliación contra la fila
-- "Total general" del propio export y la detección de truncamiento de Excel,
-- que es lo que alimenta la franja de cobertura de los tableros.
CREATE TABLE IF NOT EXISTS hidrocarburos.sicom_carga_control (
    id                       BIGSERIAL PRIMARY KEY,
    tabla                    TEXT NOT NULL,
    archivo_fuente           TEXT NOT NULL,
    hoja                     TEXT NOT NULL,
    filas_cargadas           BIGINT NOT NULL,
    medida                   TEXT,
    suma_detalle             NUMERIC,
    total_general_declarado  NUMERIC,
    gap_abs                  NUMERIC,
    gap_pct                  NUMERIC,
    concilia                 BOOLEAN,
    truncado_excel           BOOLEAN NOT NULL DEFAULT FALSE,
    primer_valor_clave       TEXT,
    ultimo_valor_clave       TEXT,
    fecha_dato               TIMESTAMPTZ,
    fecha_carga              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Índices para las agregaciones de los tableros ────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sicom_agentes_tipo        ON hidrocarburos.sicom_agentes (tipo_agente);
CREATE INDEX IF NOT EXISTS idx_sicom_agentes_depto       ON hidrocarburos.sicom_agentes (departamento_instalacion);
CREATE INDEX IF NOT EXISTS idx_sicom_agentes_anio        ON hidrocarburos.sicom_agentes (anio_creacion);

CREATE INDEX IF NOT EXISTS idx_sicom_capacidad_depto     ON hidrocarburos.sicom_capacidad (departamento_instalacion);
CREATE INDEX IF NOT EXISTS idx_sicom_capacidad_tipo      ON hidrocarburos.sicom_capacidad (tipo_agente);
CREATE INDEX IF NOT EXISTS idx_sicom_capacidad_desc_prod ON hidrocarburos.sicom_capacidad (descripcion_producto);

CREATE INDEX IF NOT EXISTS idx_sicom_compras_anio        ON hidrocarburos.sicom_compras (anio_ciclo);
CREATE INDEX IF NOT EXISTS idx_sicom_compras_tipo_comp   ON hidrocarburos.sicom_compras (tipo_agente_comprador);
CREATE INDEX IF NOT EXISTS idx_sicom_compras_muni_prov   ON hidrocarburos.sicom_compras (municipio_planta_agente_proveedor);

CREATE INDEX IF NOT EXISTS idx_sicom_eds_anio_mes        ON hidrocarburos.sicom_compras_eds (anio_ciclo, mes_ciclo);
CREATE INDEX IF NOT EXISTS idx_sicom_eds_producto        ON hidrocarburos.sicom_compras_eds (producto);
CREATE INDEX IF NOT EXISTS idx_sicom_eds_proveedor       ON hidrocarburos.sicom_compras_eds (nombre_comercial_proveedor);

CREATE INDEX IF NOT EXISTS idx_sicom_control_tabla_fecha ON hidrocarburos.sicom_carga_control (tabla, fecha_carga DESC);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Resolución municipio → departamento (para los mapas)
--
-- El Power BI original usa Azure Maps sobre el nombre de municipio. Las bases
-- Compras/Compras EDS traen el municipio SIN departamento, y en Colombia hay 67
-- nombres de municipio repetidos entre departamentos (ARMENIA está en Quindío y
-- en Antioquia, RIONEGRO en Antioquia y Santander, …). Cruzar solo por nombre
-- multiplicaría el volumen de esos municipios por 2-3.
--
-- Regla aplicada: se resuelve únicamente lo inequívoco contra la dimensión DANE
-- de la ontología. Los nombres ambiguos quedan SIN departamento y los tableros
-- los agrupan visiblemente como "Sin asignar", en vez de adivinar.
-- Al corte actual eso deja 98,4 % del volumen de compras asignado y 1,6 % sin
-- asignar (10 municipios).
-- ═══════════════════════════════════════════════════════════════════════════════

-- Normaliza un municipio de SICOM a la clave de ontologia.dim_geografia.
-- El alias de Cali es la única discrepancia de nomenclatura detectada: SICOM
-- escribe "CALI", el DANE "Santiago De Cali".
CREATE OR REPLACE FUNCTION hidrocarburos.f_clave_municipio(txt TEXT)
RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE upper(ontologia.f_unaccent(btrim(txt)))
               WHEN 'CALI' THEN 'SANTIAGO DE CALI'
               ELSE upper(ontologia.f_unaccent(btrim(txt)))
           END
$$;

-- Solo los nombres de municipio que identifican un único departamento.
CREATE OR REPLACE VIEW hidrocarburos.v_dane_municipio_unico AS
SELECT nombre_municipio_normalizado AS clave,
       min(nombre_departamento)     AS departamento
FROM ontologia.dim_geografia
GROUP BY nombre_municipio_normalizado
HAVING count(*) = 1;

-- ─── Grants ───────────────────────────────────────────────────────────────────
-- El BFF de Next.js lee como mme_user (no como postgres) — mismo patrón que el
-- resto de schemas (ver sql/hidrocarburos_schema.sql).
GRANT USAGE ON SCHEMA hidrocarburos TO mme_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hidrocarburos TO mme_user;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA hidrocarburos GRANT SELECT ON TABLES TO mme_user;
GRANT EXECUTE ON FUNCTION hidrocarburos.f_clave_municipio(TEXT) TO mme_user;
GRANT SELECT ON hidrocarburos.v_dane_municipio_unico TO mme_user;
