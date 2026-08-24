-- Migración 017: ontologia.dim_metrica + ontologia.metrica_relacion — Fase 12
-- (Ontología de métricas y variables — Palantir-IA)
--
-- Hoy el portal tiene 148 códigos técnicos de XM en sector_energetico.metrics
-- (esquema largo/angosto), más docenas de columnas en Colombia Solar, contratos
-- OR, FENOGE, hidrocarburos, presupuesto y subsidios — sin ningún catálogo que
-- documente qué es cada variable ni cómo se relacionan entre sí. Las relaciones
-- de derivación SÍ existen, pero solo como lógica de código en
-- server/core/umbrales_oficiales.py (NE ← PorcVoluUtilDiar + senda_referencia;
-- HSIN ← AporEner/AporEnerMediHist; PBP ← PrecBolsNaci + PEI/PE/PES; Condición
-- del sistema ← NE+HSIN+PBP). Esta migración le da a "Métrica" el mismo
-- tratamiento de objeto de dominio que ya tienen geografía, empresa y proyecto.
--
-- Cobertura deliberadamente parcial al inicio (estado='pendiente_curacion' para
-- lo no sembrado todavía) — mismo principio de curación por relevancia que
-- geografia_alias/empresa_alias, no se inventa cobertura total del día uno.

CREATE TABLE IF NOT EXISTS ontologia.dim_metrica (
    metrica_id            SERIAL PRIMARY KEY,
    codigo_tecnico         TEXT NOT NULL,        -- 'PorcVoluUtilDiar', 'AporEner', 'NE', 'avance_fisico_pct'...
    nombre_display          TEXT NOT NULL,        -- 'Nivel de embalse del SIN (%)'
    dominio                TEXT NOT NULL,        -- 'sector_energetico' | 'colombia_solar' | 'contratos_or' | 'fenoge' | 'hidrocarburos' | 'presupuesto' | 'subsidios' | 'supervision'
    esquema_origen          TEXT,
    tabla_origen             TEXT,
    columna_origen           TEXT,
    unidad                  TEXT,                 -- '%', 'GWh', 'COP/kWh', 'MW'...
    fuente                  TEXT NOT NULL,        -- 'XM' | 'DANE' | 'IDEAM' | 'NASA' | 'calculo_interno' | 'SharePoint'
    descripcion              TEXT,
    es_indice_regulatorio    BOOLEAN NOT NULL DEFAULT FALSE,
    referencia_normativa     TEXT,                 -- 'Res. CREG 209/2020 art. 2.8.2.1.3' (solo si aplica)
    estado                  TEXT NOT NULL DEFAULT 'catalogado'
        CHECK (estado IN ('catalogado', 'pendiente_curacion')),
    creado_en                TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dominio, codigo_tecnico)
);

CREATE TABLE IF NOT EXISTS ontologia.metrica_relacion (
    relacion_id           SERIAL PRIMARY KEY,
    metrica_origen_id      INTEGER NOT NULL REFERENCES ontologia.dim_metrica(metrica_id),
    metrica_destino_id      INTEGER NOT NULL REFERENCES ontologia.dim_metrica(metrica_id),
    tipo_relacion            TEXT NOT NULL
        CHECK (tipo_relacion IN ('insumo_de', 'se_compara_con', 'compone_indice')),
    descripcion              TEXT NOT NULL,        -- ej. 'PorcVoluUtilDiar se compara contra senda_referencia para clasificar el Índice NE'
    referencia_normativa     TEXT,
    creado_en                TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (metrica_origen_id, metrica_destino_id, tipo_relacion)
);

CREATE INDEX IF NOT EXISTS idx_dim_metrica_dominio ON ontologia.dim_metrica (dominio);
CREATE INDEX IF NOT EXISTS idx_dim_metrica_estado ON ontologia.dim_metrica (estado);
CREATE INDEX IF NOT EXISTS idx_metrica_relacion_origen ON ontologia.metrica_relacion (metrica_origen_id);
CREATE INDEX IF NOT EXISTS idx_metrica_relacion_destino ON ontologia.metrica_relacion (metrica_destino_id);

GRANT SELECT ON ontologia.dim_metrica, ontologia.metrica_relacion TO mme_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ontologia GRANT SELECT ON TABLES TO mme_user;

COMMENT ON TABLE ontologia.dim_metrica IS
    'Catálogo de métricas/variables del portal (Métrica como objeto de primera '
    'clase). Sembrado inicialmente desde las variables activas de sector_snapshot '
    'y los índices regulatorios de core/umbrales_oficiales.py — cobertura parcial '
    'deliberada, ver columna estado.';

COMMENT ON TABLE ontologia.metrica_relacion IS
    'Grafo de derivación/dependencia entre métricas, transcrito manualmente desde '
    'la lógica ya verificada de core/umbrales_oficiales.py (nunca inferido '
    'automáticamente desde nombres de columnas).';
