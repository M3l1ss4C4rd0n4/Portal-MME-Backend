-- Migración 028: sincroniza los nombres de municipio de dim_geografia (fuente
-- 'DANE', sembrados en Fase 1 desde texto libre de supervision.contratos) con
-- la forma oficial DIVIPOLA (data/referencia/divipola_dane.csv) — mismo
-- principio ya aplicado 3 veces en este proyecto (San Andrés, Caquetá/
-- Guainía/Vaupés a nivel departamento): preferir siempre el nombre
-- DIVIPOLA-canónico cuando hay más de una grafía para el mismo código DANE.
--
-- Se encontraron 85 diferencias (no las ~29 estimadas al planear esta fase),
-- verificadas programáticamente contra el CSV, no a mano una por una:
--
-- 1. 59 son solo diferencia de tilde/diacrítico (ej. "Valparaiso" ->
--    "Valparaíso") — CERO impacto en resolución (ontologia.f_unaccent() ya
--    las trata como iguales al hacer match), es una mejora puramente de
--    presentación (mapas, mv_resumen_municipio).
-- 2. 26 son estructuralmente distintas (ej. "Cartagena" -> "Cartagena De
--    Indias", "Currillo" -> "Curillo", "Chibolo" -> "Chivolo") — SÍ podían
--    afectar resolución. Para evitar romper cualquier valor de texto libre
--    que hoy resuelva por el nombre corto/viejo (nunca romper lo que ya
--    funciona), cada una recibe también un alias retrocompatible en
--    ontologia.geografia_alias_curado apuntando al mismo geografia_id.
--    3 de las 26 (San Andrés/San Pedro/Manaure) NO reciben alias retro-
--    compatible sin departamento: se verificó que esos 3 nombres cortos son
--    genuinamente ambiguos a nivel nacional (San Andrés existe en Antioquia,
--    Santander Y el Archipiélago; San Pedro en Antioquia, Sucre Y Valle del
--    Cauca; Manaure en Cesar Y La Guajira) — un alias global habría elegido
--    uno de varios candidatos reales a ciegas, exactamente el riesgo que
--    este mecanismo existe para evitar.

-- Sincronizacion de acentos (59 filas, sin impacto en resolucion — f_unaccent ya las trata igual)
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Valparaíso' WHERE codigo_dane_municipio = '05856' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Repelón' WHERE codigo_dane_municipio = '08606' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Santa Lucía' WHERE codigo_dane_municipio = '08675' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Santo Tomás' WHERE codigo_dane_municipio = '08685' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Cristóbal' WHERE codigo_dane_municipio = '13620' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Martín De Loba' WHERE codigo_dane_municipio = '13667' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Turbaná' WHERE codigo_dane_municipio = '13838' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Úmbita' WHERE codigo_dane_municipio = '15842' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Belén De Los Andaquíes' WHERE codigo_dane_municipio = '18094' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Cartagena Del Chairá' WHERE codigo_dane_municipio = '18150' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'El Paujíl' WHERE codigo_dane_municipio = '18256' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Milán' WHERE codigo_dane_municipio = '18460' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San José Del Fragua' WHERE codigo_dane_municipio = '18610' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Valparaíso' WHERE codigo_dane_municipio = '18860' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Jambaló' WHERE codigo_dane_municipio = '19364' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'López De Micay' WHERE codigo_dane_municipio = '19418' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Páez' WHERE codigo_dane_municipio = '19517' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Patía' WHERE codigo_dane_municipio = '19532' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Puracé' WHERE codigo_dane_municipio = '19585' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Sebastián' WHERE codigo_dane_municipio = '19693' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Timbío' WHERE codigo_dane_municipio = '19807' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Timbiquí' WHERE codigo_dane_municipio = '19809' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Totoró' WHERE codigo_dane_municipio = '19824' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Chiriguaná' WHERE codigo_dane_municipio = '20178' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Bojayá' WHERE codigo_dane_municipio = '27099' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Cértegui' WHERE codigo_dane_municipio = '27160' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Unión Panamericana' WHERE codigo_dane_municipio = '27810' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Íquira' WHERE codigo_dane_municipio = '41357' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Distracción' WHERE codigo_dane_municipio = '44098' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'El Piñón' WHERE codigo_dane_municipio = '47258' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'El Retén' WHERE codigo_dane_municipio = '47268' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Fundación' WHERE codigo_dane_municipio = '47288' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Puebloviejo' WHERE codigo_dane_municipio = '47570' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Sabanas De San Ángel' WHERE codigo_dane_municipio = '47660' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Sebastián De Buenavista' WHERE codigo_dane_municipio = '47692' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Santa Bárbara De Pinto' WHERE codigo_dane_municipio = '47720' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Zapayán' WHERE codigo_dane_municipio = '47960' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Mapiripán' WHERE codigo_dane_municipio = '50325' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Puerto López' WHERE codigo_dane_municipio = '50573' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Vistahermosa' WHERE codigo_dane_municipio = '50711' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Gualmatán' WHERE codigo_dane_municipio = '52323' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Magüí' WHERE codigo_dane_municipio = '52427' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Roberto Payán' WHERE codigo_dane_municipio = '52621' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Santa Bárbara' WHERE codigo_dane_municipio = '52696' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Santacruz' WHERE codigo_dane_municipio = '52699' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Túquerres' WHERE codigo_dane_municipio = '52838' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Ábrego' WHERE codigo_dane_municipio = '54003' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Cáchira' WHERE codigo_dane_municipio = '54128' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Gámbita' WHERE codigo_dane_municipio = '68298' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Lebrija' WHERE codigo_dane_municipio = '68406' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Colosó' WHERE codigo_dane_municipio = '70204' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Ibagué' WHERE codigo_dane_municipio = '73001' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Lérida' WHERE codigo_dane_municipio = '73408' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Chámeza' WHERE codigo_dane_municipio = '85015' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Puerto Asís' WHERE codigo_dane_municipio = '86568' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Puerto Guzmán' WHERE codigo_dane_municipio = '86571' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Puerto Leguízamo' WHERE codigo_dane_municipio = '86573' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Mirití - Paraná' WHERE codigo_dane_municipio = '91460' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Carurú' WHERE codigo_dane_municipio = '97161' AND fuente = 'DANE';

-- Nombres estructuralmente distintos (26 filas) + alias retrocompatible del nombre corto/viejo
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Andrés De Cuerquía' WHERE codigo_dane_municipio = '05647' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Pedro De Los Milagros' WHERE codigo_dane_municipio = '05664' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Vicente Ferrer' WHERE codigo_dane_municipio = '05674' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Cartagena De Indias' WHERE codigo_dane_municipio = '13001' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'El Carmen De Bolívar' WHERE codigo_dane_municipio = '13244' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Santa Cruz De Mompox' WHERE codigo_dane_municipio = '13468' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Santa Rosa' WHERE codigo_dane_municipio = '13683' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Güicán De La Sierra' WHERE codigo_dane_municipio = '15332' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Pablo De Borbur' WHERE codigo_dane_municipio = '15681' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Curillo' WHERE codigo_dane_municipio = '18205' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Piendamó - Tunía' WHERE codigo_dane_municipio = '19548' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Sotará - Paispamba' WHERE codigo_dane_municipio = '19760' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Manaure Balcón Del Cesar' WHERE codigo_dane_municipio = '20443' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Istmina' WHERE codigo_dane_municipio = '27361' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Río Iró' WHERE codigo_dane_municipio = '27580' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Cerro De San Antonio' WHERE codigo_dane_municipio = '47161' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Chivolo' WHERE codigo_dane_municipio = '47170' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Cubarral' WHERE codigo_dane_municipio = '50223' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Carlos De Guaroa' WHERE codigo_dane_municipio = '50680' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Andrés De Tumaco' WHERE codigo_dane_municipio = '52835' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Salazar' WHERE codigo_dane_municipio = '54660' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Juan De Betulia' WHERE codigo_dane_municipio = '70702' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San Luis De Sincé' WHERE codigo_dane_municipio = '70742' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'San José De Toluviejo' WHERE codigo_dane_municipio = '70823' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Santiago De Cali' WHERE codigo_dane_municipio = '76001' AND fuente = 'DANE';
UPDATE ontologia.dim_geografia SET nombre_municipio = 'Monterrey' WHERE codigo_dane_municipio = '85162' AND fuente = 'DANE';

-- Alias retrocompatible (23 de las 26 estructurales — ver nota arriba sobre
-- las 3 excluidas por ambigüedad genuina).
INSERT INTO ontologia.geografia_alias_curado (patron_departamento, patron_municipio, geografia_id, nota)
SELECT NULL, 'SAN VICENTE', geografia_id, 'Nombre corto/anterior de San Vicente Ferrer (cod 05674), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '05674'
UNION ALL
SELECT NULL, 'CARTAGENA', geografia_id, 'Nombre corto/anterior de Cartagena De Indias (cod 13001), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '13001'
UNION ALL
SELECT NULL, 'CARMEN DE BOLIVAR', geografia_id, 'Nombre corto/anterior de El Carmen De Bolívar (cod 13244), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '13244'
UNION ALL
SELECT NULL, 'MOMPOS', geografia_id, 'Nombre corto/anterior de Santa Cruz De Mompox (cod 13468), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '13468'
UNION ALL
SELECT NULL, 'SANTA ROSA DE LIMA', geografia_id, 'Nombre corto/anterior de Santa Rosa (cod 13683), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '13683'
UNION ALL
SELECT NULL, 'GUICAN', geografia_id, 'Nombre corto/anterior de Güicán De La Sierra (cod 15332), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '15332'
UNION ALL
SELECT NULL, 'SAN PABLO BORBUR', geografia_id, 'Nombre corto/anterior de San Pablo De Borbur (cod 15681), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '15681'
UNION ALL
SELECT NULL, 'CURRILLO', geografia_id, 'Nombre corto/anterior de Curillo (cod 18205), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '18205'
UNION ALL
SELECT NULL, 'PIENDAMO', geografia_id, 'Nombre corto/anterior de Piendamó - Tunía (cod 19548), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '19548'
UNION ALL
SELECT NULL, 'SOTARA', geografia_id, 'Nombre corto/anterior de Sotará - Paispamba (cod 19760), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '19760'
UNION ALL
SELECT NULL, 'ITSMINA', geografia_id, 'Nombre corto/anterior de Istmina (cod 27361), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '27361'
UNION ALL
SELECT NULL, 'RIO FRIO', geografia_id, 'Nombre corto/anterior de Río Iró (cod 27580), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '27580'
UNION ALL
SELECT NULL, 'CERRO SAN ANTONIO', geografia_id, 'Nombre corto/anterior de Cerro De San Antonio (cod 47161), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '47161'
UNION ALL
SELECT NULL, 'CHIBOLO', geografia_id, 'Nombre corto/anterior de Chivolo (cod 47170), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '47170'
UNION ALL
SELECT NULL, 'SAN LUIS DE CUBARRAL', geografia_id, 'Nombre corto/anterior de Cubarral (cod 50223), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '50223'
UNION ALL
SELECT NULL, 'SAN CARLOS GUAROA', geografia_id, 'Nombre corto/anterior de San Carlos De Guaroa (cod 50680), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '50680'
UNION ALL
SELECT NULL, 'TUMACO', geografia_id, 'Nombre corto/anterior de San Andrés De Tumaco (cod 52835), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '52835'
UNION ALL
SELECT NULL, 'SALAZAR DE LAS PALMAS', geografia_id, 'Nombre corto/anterior de Salazar (cod 54660), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '54660'
UNION ALL
SELECT NULL, 'SAN JUAN BETULIA', geografia_id, 'Nombre corto/anterior de San Juan De Betulia (cod 70702), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '70702'
UNION ALL
SELECT NULL, 'SINCE', geografia_id, 'Nombre corto/anterior de San Luis De Sincé (cod 70742), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '70742'
UNION ALL
SELECT NULL, 'TOLU VIEJO', geografia_id, 'Nombre corto/anterior de San José De Toluviejo (cod 70823), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '70823'
UNION ALL
SELECT NULL, 'CALI', geografia_id, 'Nombre corto/anterior de Santiago De Cali (cod 76001), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '76001'
UNION ALL
SELECT NULL, 'MONTEREY', geografia_id, 'Nombre corto/anterior de Monterrey (cod 85162), antes de sincronizar con DIVIPOLA en migracion 028' FROM ontologia.dim_geografia WHERE codigo_dane_municipio = '85162'
ON CONFLICT DO NOTHING;

-- Refrescar las vistas para reflejar los nombres corregidos.
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_comunidades_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_contratos_or_fisico_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_contratos_or_documental_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_fenoge_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_colombia_solar_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_subsidios_mapa_geo;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_resumen_departamento;
REFRESH MATERIALIZED VIEW CONCURRENTLY ontologia.mv_resumen_municipio;
