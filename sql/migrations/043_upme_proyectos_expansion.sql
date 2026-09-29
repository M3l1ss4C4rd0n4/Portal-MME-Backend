-- Migración 043: sector_energetico.upme_proyectos_expansion — Fase 45
--
-- Contexto: tablero "Balance Oferta-Demanda del SIN" para evaluar con datos
-- la hipótesis de que la crisis de suministro actual fue causada por
-- retrasos en la ejecución de proyectos del Plan de Expansión de Referencia
-- Generación-Transmisión de la UPME. Hasta esta migración no existía en la
-- base de datos ninguna tabla estructurada de proyectos UPME (solo un
-- scraper de PDFs para el RAG documental en ontologia.informes_documentos)
-- — este es el primer modelo tabular para esos proyectos.
--
-- IMPORTANTE (gobernanza de datos, ver core/umbrales_oficiales.py y feedback
-- de proyecto sobre "solo datos oficiales"): esta tabla NO es una métrica
-- oficial de XM. Es información curada del Plan de Expansión de la UPME y
-- de seguimiento público, con `fuente` obligatoria y trazable por fila.
-- Nunca debe presentarse en el portal como si fuera un dato XM.

CREATE TABLE IF NOT EXISTS sector_energetico.upme_proyectos_expansion (
    id                              SERIAL PRIMARY KEY,
    nombre_proyecto                 TEXT NOT NULL,
    tipo                            TEXT NOT NULL
                                        CHECK (tipo IN ('GENERACION', 'TRANSMISION')),
    tecnologia                      TEXT NOT NULL,
        -- SOLAR | EOLICA | TERMICA | HIDRAULICA | COGENERADOR | LINEA | SUBESTACION | OTRO
    capacidad_mw                    NUMERIC(10, 2),
        -- MW para proyectos de generación. NULL permitido para líneas/subestaciones
        -- de transmisión donde la unidad relevante no es MW (se documenta en notas).
    departamento                    TEXT,
    area_operativa                  TEXT,
        -- Referencia informativa (Antioquia/Caribe/Nordeste/Oriental/Suroccidental/
        -- No definida) — NO se cruza automáticamente con sector_energetico.metrics
        -- porque hoy esa tabla no trae generación/capacidad desagregada por área
        -- operativa (catalogos.region y ontologia.dim_recurso.region están vacíos
        -- en toda la base — verificado en la Fase 0 de este trabajo).
    fecha_entrada_planeada_original DATE,
        -- Fecha de entrada en operación según la primera versión conocida del
        -- Plan de Expansión donde aparece el proyecto.
    fecha_entrada_planeada_vigente  DATE,
        -- Fecha de entrada según la versión más reciente del Plan de Expansión
        -- o el último informe de seguimiento UPME/XM consultado.
    fecha_entrada_real              DATE,
        -- NULL mientras el proyecto no haya entrado en operación comercial.
    estado                          TEXT NOT NULL DEFAULT 'PLANEADO'
                                        CHECK (estado IN (
                                            'PLANEADO', 'EN_CONSTRUCCION',
                                            'RETRASADO', 'OPERANDO', 'CANCELADO'
                                        )),
    dias_retraso                    INTEGER,
        -- GREATEST(0, COALESCE(fecha_entrada_real, CURRENT_DATE) - fecha_entrada_planeada_original)
        -- Se recalcula en la capa de servicio (domain/services/balance_oferta_demanda_service.py)
        -- al leer, para que quede siempre vigente sin depender de un job de refresco;
        -- se persiste aquí solo como último valor conocido para consultas directas/BI.
    fuente                          TEXT NOT NULL,
        -- Documento/informe específico (p. ej. "UPME Plan de Expansión de
        -- Referencia Generación-Transmisión 2023-2037, tabla X" o nota de prensa
        -- con fecha) — obligatorio para poder auditar cada fila.
    notas                           TEXT,
    creado_en                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Único por (nombre_proyecto, tipo) — permite que upsert_proyecto() haga
-- ON CONFLICT ... DO UPDATE real en vez de silenciosamente no hacer nada
-- (sin esta restricción, ON CONFLICT DO NOTHING nunca encuentra conflicto
-- y cada corrida del script de siembra duplicaría las filas).
CREATE UNIQUE INDEX IF NOT EXISTS uq_upme_proyectos_nombre_tipo
    ON sector_energetico.upme_proyectos_expansion (nombre_proyecto, tipo);

CREATE INDEX IF NOT EXISTS idx_upme_proyectos_estado
    ON sector_energetico.upme_proyectos_expansion (estado);
CREATE INDEX IF NOT EXISTS idx_upme_proyectos_tipo_tecnologia
    ON sector_energetico.upme_proyectos_expansion (tipo, tecnologia);
CREATE INDEX IF NOT EXISTS idx_upme_proyectos_fecha_planeada_original
    ON sector_energetico.upme_proyectos_expansion (fecha_entrada_planeada_original);

COMMENT ON TABLE sector_energetico.upme_proyectos_expansion IS
    'Proyectos de generación/transmisión del Plan de Expansión de la UPME, '
    'curados manualmente (no hay API estructurada de UPME). Usada por el '
    'tablero Balance Oferta-Demanda para evaluar la hipótesis de retrasos '
    'UPME como causa del déficit. NO es una métrica oficial XM — cada fila '
    'lleva su fuente documental.';
