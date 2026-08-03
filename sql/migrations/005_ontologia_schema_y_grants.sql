-- Migración 005: Esquema `ontologia` (capa semántica de solo lectura) + corrección de
-- permisos raíz de mme_user.
--
-- Contexto: mme_user (usuario de la app en producción) tiene 0 privilegios SELECT en
-- supervision/comunidades/contratos_or porque nunca se configuró ALTER DEFAULT
-- PRIVILEGES en esos esquemas — cada CREATE TABLE nuevo ejecutado como postgres nace
-- sin GRANT (mismo mecanismo del bug histórico "permission denied for table base").
-- Este archivo corrige la causa raíz y evita que el nuevo esquema ontologia la repita.

CREATE SCHEMA IF NOT EXISTS ontologia;

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Corrección retroactiva: privilegios en tablas ya existentes de los 3 esquemas semilla
GRANT USAGE ON SCHEMA supervision, comunidades, contratos_or TO mme_user;
GRANT SELECT ON ALL TABLES IN SCHEMA supervision TO mme_user;
GRANT SELECT ON ALL TABLES IN SCHEMA comunidades TO mme_user;
GRANT SELECT ON ALL TABLES IN SCHEMA contratos_or TO mme_user;

-- Prevención: cualquier tabla futura creada por postgres en estos esquemas (incluido
-- sector_energetico, que ya mostró el mismo síntoma con 4 tablas sin grant) hereda
-- SELECT automáticamente.
ALTER DEFAULT PRIVILEGES IN SCHEMA supervision, comunidades, contratos_or, sector_energetico
    GRANT SELECT ON TABLES TO mme_user;

-- Esquema ontologia: mismo mecanismo desde el día 1, para que 006/007/008 no lo repitan.
GRANT USAGE ON SCHEMA ontologia TO mme_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ontologia
    GRANT SELECT ON TABLES TO mme_user;

COMMENT ON SCHEMA ontologia IS
    'Capa semántica de solo lectura: dimensiones (geografía DANE, empresas) y vistas '
    'materializadas que cruzan los 9 esquemas de negocio existentes. No contiene FKs '
    'hacia tablas ETL originales — es aditiva, ningún ETL existente cambia.';
