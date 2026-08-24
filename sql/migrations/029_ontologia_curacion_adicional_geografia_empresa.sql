-- Migración 029: continuación de la curación manual de geografia_alias/
-- empresa_alias tras revisar el backlog restante fila por fila (17 valores
-- geográficos + colisión de NIT EMCALI/ENEL verificada contra fuentes
-- externas — Concejo de Cali, RUES/DataCrédito, documentación de fusión de
-- Enel — no adivinada).
--
-- Incluye la corrección de un bug real: 3 de los 59 "cambios de solo acento"
-- de la migración 028 en realidad cambiaban también el espaciado ("Pueblo
-- Viejo"->"Puebloviejo", "Vista Hermosa"->"Vistahermosa", "Santa Cruz"->
-- "Santacruz") — la clasificación se hizo con una normalización en Python que
-- (a diferencia de ontologia.f_unaccent(), que solo quita tildes) también
-- quitaba espacios, así que esos 3 casos no recibieron el alias
-- retrocompatible que sí necesitaban. Se agregan aquí.

INSERT INTO ontologia.geografia_alias_curado (patron_departamento, patron_municipio, geografia_id, nota)
SELECT NULL, 'LA URIBE', geografia_id, 'Uribe (Meta) — corrige omision de la migracion 027/028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '50370'
UNION ALL
SELECT NULL, 'PUEBLO VIEJO', geografia_id, 'Puebloviejo (Magdalena) — bug de clasificacion en migracion 028 (cambio de espacio mal marcado como solo-acento)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '47570'
UNION ALL
SELECT NULL, 'VISTA HERMOSA', geografia_id, 'Vistahermosa (Meta) — mismo bug de clasificacion que Pueblo Viejo' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '50711'
UNION ALL
SELECT NULL, 'VISTA HERMOSA (1.000 KWP)', geografia_id, 'Variante literal con sufijo de capacidad, colombia_solar.base' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '50711'
UNION ALL
SELECT NULL, 'VISTA HERMOSA (235 KWP)', geografia_id, 'Variante literal con sufijo de capacidad, colombia_solar.base' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '50711'
UNION ALL
SELECT NULL, 'SANTA CRUZ', geografia_id, 'Santacruz (Nariño) — mismo bug de clasificacion que Pueblo Viejo' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '52699'
UNION ALL
SELECT NULL, 'CUCUTA', geografia_id, 'San Jose De Cucuta (Norte de Santander)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '54001'
UNION ALL
SELECT NULL, 'BOGOTA', geografia_id, 'Bogota D.C. — forma corta sin D.C.' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '11001'
UNION ALL
SELECT NULL, 'BUGA', geografia_id, 'Guadalajara De Buga (Valle del Cauca)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '76111'
UNION ALL
SELECT NULL, 'EL AGRADO', geografia_id, 'Agrado (Huila)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '41013'
UNION ALL
SELECT NULL, 'CUASPUD', geografia_id, 'Cuaspud Carlosama (Nariño)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '52224'
UNION ALL
SELECT NULL, 'POLO NUEVO', geografia_id, 'Polonuevo (Atlantico)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '08558'
UNION ALL
SELECT NULL, 'MONTANITA', geografia_id, 'La Montañita (Caqueta)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '18410'
UNION ALL
SELECT NULL, 'CARMEN DE VIBORAL', geografia_id, 'El Carmen De Viboral (Antioquia)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '05148'
UNION ALL
SELECT NULL, 'CARTAGENA DEL CHAIIRA', geografia_id, 'Typo (doble i) de Cartagena Del Chaira' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '18150'
UNION ALL
SELECT NULL, 'JAGUA DE IBIRICO (2)', geografia_id, 'Variante literal con sufijo, La Jagua De Ibirico (Cesar)' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '20400'
UNION ALL
SELECT 'REGION 2 CAQUETA', 'FLORENCIA', geografia_id, 'Florencia (Caqueta) — depto ambiguo en origen ("Region 2 Caqueta"), municipio Florencia es ambiguo a nivel nacional (existe tambien en Cauca) por eso requiere el par' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '18001'
ON CONFLICT DO NOTHING;

-- Colisión de NIT EMCALI/ENEL (ver build_empresa_alias.py::
-- EJECUTORES_NIT_VERIFICADO_EXTERNAMENTE) — NITs reales verificados
-- externamente: ENEL COLOMBIA S.A. E.S.P. = 860063875-8 (RUES vía
-- larepublica.co, DataCrédito, documentación propia de fusión de Enel);
-- EMCALI E.I.C.E. E.S.P. = 890399003-4 (Concejo de Cali,
-- concejodecali.gov.co/descargar.php?idFile=16164). Ninguno de los dos
-- sobrevivió el saneamiento de ambigüedad de la Fase 17 (la limpieza fue
-- correcta en su momento: no había verificación externa todavía) — se
-- resiembran aquí ya verificados.
INSERT INTO ontologia.dim_empresa (nit, nombre_oficial)
SELECT '860063875', 'ENEL COLOMBIA S.A. E.S.P.'
WHERE NOT EXISTS (SELECT 1 FROM ontologia.dim_empresa WHERE nit_normalizado = '860063875');

INSERT INTO ontologia.dim_empresa (nit, nombre_oficial)
SELECT '890399003', 'EMCALI E.I.C.E. E.S.P.'
WHERE NOT EXISTS (SELECT 1 FROM ontologia.dim_empresa WHERE nit_normalizado = '890399003');

-- Refrescar las vistas para reflejar los nombres/alias nuevos.
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_comunidades_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_contratos_or_fisico_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_contratos_or_documental_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_fenoge_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_colombia_solar_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_subsidios_mapa_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_resumen_departamento;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_resumen_municipio;
