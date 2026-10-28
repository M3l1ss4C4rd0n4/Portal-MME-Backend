-- 047 · IPEM — Índice de Pobreza Energética Multidimensional (2024 y 2025)
--
-- Origen del dato: entrega manual del área (server/data/IPEM/IPEM.xlsx), junto con los
-- dos informes técnicos del MME — `Pobreza-energetica-MME-2024.pdf` (edición IPEM
-- 2022-2023) y `IPEM-MME-2025.pdf` (edición vigente). Son datos FIJOS: no hay ETL ni
-- cron. La actualización es anual y manual, cuando el área entregue el Excel del año
-- siguiente, repoblando con scripts/cargar_ipem.py.
--
-- Metodología (informe 2025, §5-1): método Alkire-Foster siguiendo a Nussbaumer et al.
-- (2011), sobre tres dimensiones — acceso a energía eléctrica y preparación de alimentos
-- (36 %), vivienda funcional (32 %) y aprender y comunicarse (32 %) — con el peso de cada
-- dimensión repartido proporcionalmente entre sus variables. Fuentes: DANE (ECV) y UPME
-- (ICEE). La dimensión "territorio equipado" del informe anterior se eliminó y los
-- valores del año previo se recalcularon con el método nuevo, así que las dos columnas
-- SÍ son comparables entre sí.
--
-- TRES ADVERTENCIAS QUE VIENEN DEL INFORME Y CONDICIONAN CÓMO SE LEE ESTA TABLA:
--
--  1. El índice NO tiene puntos de corte por variable ni umbral agregado. El informe es
--     explícito: "no se definieron estos puntos de corte, ya que se considera que la
--     ausencia o carencia ya representa una privación". Es un índice continuo de
--     privaciones ponderadas, NO una tasa de incidencia con umbral k. No se puede hablar
--     de "umbral de pobreza energética" a partir de estos valores.
--
--  2. El dato MUNICIPAL es una estimación. La ECV no tiene representatividad municipal;
--     los valores por municipio se obtienen aplicando el factor de expansión de la
--     encuesta. No es censo.
--
--  3. Los quintiles de las columnas quintil_2024 / quintil_2025 son RELATIVOS A CADA AÑO,
--     no bandas fijas: verificado contra el Excel, cada etiqueta agrupa ~224 de los 1.121
--     municipios en ambos años, con rangos distintos por año (2024: MUY BAJO 15,17-25,18 %;
--     2025: MUY BAJO 12,87-22,98 %). Consecuencia: un municipio puede SUBIR de quintil
--     aunque su IPEM BAJE — caso real, Abriaquí pasa de 27,30 % a 26,49 % (mejora) y su
--     etiqueta va de BAJO a MEDIO. Para comparar años hay que usar el valor del índice,
--     nunca el cambio de etiqueta. El tablero lo advierte en pantalla.
--
-- Las bandas publicadas en el informe 2025 coinciden exactamente con los min/max de la
-- columna 2025 (municipal 12,87-63,58 %, departamental 12,87-55,48 %), no con los de 2024,
-- aunque el texto las atribuye a "la estimación de 2024". Encaja si las columnas del Excel
-- están nombradas por edición del informe mientras el texto habla del año del dato
-- (ECV 2023 vs ECV 2024); pendiente de confirmar con el área.
--
-- No se almacenan quintiles departamentales: el Excel no los trae y derivarlos sería
-- fabricar una clasificación que el informe no publica a esa escala. El mapa colorea los
-- departamentos con las bandas departamentales publicadas, que sí son rastreables al
-- documento.

CREATE TABLE IF NOT EXISTS sector_energetico.ipem_municipal (
    cod_municipio    CHAR(5) PRIMARY KEY,
    cod_departamento CHAR(2) NOT NULL,
    departamento     TEXT    NOT NULL,
    municipio        TEXT    NOT NULL,
    -- NULL legítimo: Angelópolis (05036) llegó sin valor de 2024 en la fuente,
    -- aunque sí trae etiqueta de quintil. La variación 2024→2025 se calcula
    -- entonces sobre 1.120 municipios, no 1.121.
    ipem_2024        NUMERIC(10, 8),
    ipem_2025        NUMERIC(10, 8),
    quintil_2024     TEXT,
    quintil_2025     TEXT,
    actualizado_en   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ipem_municipal_rango_2024 CHECK (ipem_2024 IS NULL OR (ipem_2024 >= 0 AND ipem_2024 <= 1)),
    CONSTRAINT ipem_municipal_rango_2025 CHECK (ipem_2025 IS NULL OR (ipem_2025 >= 0 AND ipem_2025 <= 1))
);

CREATE INDEX IF NOT EXISTS ipem_municipal_depto_idx
    ON sector_energetico.ipem_municipal (cod_departamento);

CREATE TABLE IF NOT EXISTS sector_energetico.ipem_departamental (
    cod_departamento CHAR(2) PRIMARY KEY,
    departamento     TEXT    NOT NULL,
    region           TEXT    NOT NULL,
    ipem_2024        NUMERIC(10, 8),
    ipem_2025        NUMERIC(10, 8),
    actualizado_en   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ipem_departamental_rango_2024 CHECK (ipem_2024 IS NULL OR (ipem_2024 >= 0 AND ipem_2024 <= 1)),
    CONSTRAINT ipem_departamental_rango_2025 CHECK (ipem_2025 IS NULL OR (ipem_2025 >= 0 AND ipem_2025 <= 1))
);

COMMENT ON TABLE sector_energetico.ipem_municipal IS
    'IPEM por municipio (1.121 filas, DIVIPOLA de 5 dígitos). Dato fijo de entrega '
    'manual del área, repoblar con scripts/cargar_ipem.py. Los quintiles son relativos '
    'a cada año, no bandas fijas: comparar años por el valor del índice, no por la '
    'etiqueta. El valor municipal es estimación por factor de expansión de la ECV.';

COMMENT ON TABLE sector_energetico.ipem_departamental IS
    'IPEM por departamento (33 filas) y su región. Dato fijo de entrega manual del área, '
    'repoblar con scripts/cargar_ipem.py. Sin quintiles: el Excel no los trae a esta '
    'escala y el informe no los publica por departamento con etiqueta.';

COMMENT ON COLUMN sector_energetico.ipem_municipal.cod_departamento IS
    'Primeros 2 dígitos del DIVIPOLA. Es la clave con la que el tablero cruza contra '
    'public/departamentos_colombia.geojson (propiedad DPTO): el cruce por nombre falla '
    'porque el Excel trae "BOGOTÁ, D.C." y el geojson "SANTAFE DE BOGOTA D.C".';

-- El portal Next.js se conecta como mme_user (src/lib/db.ts). Las ALTER DEFAULT
-- PRIVILEGES de la migración 046 ya cubren las tablas nuevas que cree el rol postgres en
-- este esquema, pero se otorga explícito para no depender de quién ejecute la migración
-- (ya hubo un incidente de "permission denied" por tablas nacidas sin privilegios).
GRANT SELECT ON sector_energetico.ipem_municipal     TO mme_user;
GRANT SELECT ON sector_energetico.ipem_departamental TO mme_user;
