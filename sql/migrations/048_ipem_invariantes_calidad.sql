-- 048 · IPEM — invariantes de calidad de datos
--
-- Auditoría de calidad del 2026-10-28 sobre las tablas creadas en la migración 047.
-- Lo que la 047 dejó sin expresar en el esquema y por tanto solo vivía en el script de
-- carga (o en ningún sitio):
--
--  1. La columna de quintil era TEXT libre. Si la entrega anual llegara con otra
--     nomenclatura («Quintil 1», «Muy bajo»), la carga la aceptaba, el frontend
--     convertía lo desconocido en «—» y el tablero quedaba sin clasificación en las
--     1.121 filas SIN que nadie viera un error. Ahora el vocabulario es una
--     restricción de la tabla, no una convención.
--
--  2. `cod_departamento` podía desincronizarse de `cod_municipio`. Es el código con el
--     que el tablero cruza contra el geojson, así que un desajuste pinta el mapa mal.
--     Es derivable del propio código municipal: se exige la identidad.
--
--  3. No había integridad referencial entre las dos tablas. Un municipio cuyo
--     departamento no exista en la tabla departamental se queda sin región y, en el
--     tablero, sin filtro: el script lo comprobaba, pero la base no. Se añade la
--     llave foránea, que es el lugar donde esa garantía no se puede olvidar.
--
-- Efecto en la carga: con la llave foránea, `scripts/cargar_ipem.py` trunca las dos
-- tablas en una sola sentencia e inserta primero los departamentos.

-- Vocabulario cerrado de los quintiles. Se permite NULL: es ausencia de clasificación,
-- distinta de una etiqueta inválida.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ipem_municipal_quintil_vocabulario'
    ) THEN
        ALTER TABLE sector_energetico.ipem_municipal
            ADD CONSTRAINT ipem_municipal_quintil_vocabulario CHECK (
                (quintil_2024 IS NULL OR quintil_2024 IN ('MUY BAJO', 'BAJO', 'MEDIO', 'ALTO', 'MUY ALTO'))
                AND
                (quintil_2025 IS NULL OR quintil_2025 IN ('MUY BAJO', 'BAJO', 'MEDIO', 'ALTO', 'MUY ALTO'))
            );
    END IF;
END $$;

-- El código de departamento son los dos primeros dígitos del DIVIPOLA municipal.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ipem_municipal_cod_depto_coherente'
    ) THEN
        ALTER TABLE sector_energetico.ipem_municipal
            ADD CONSTRAINT ipem_municipal_cod_depto_coherente
            CHECK (cod_departamento = left(cod_municipio, 2));
    END IF;
END $$;

-- Todo municipio pertenece a un departamento de la tabla departamental, que es de
-- donde el tablero saca la región.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ipem_municipal_depto_fk'
    ) THEN
        ALTER TABLE sector_energetico.ipem_municipal
            ADD CONSTRAINT ipem_municipal_depto_fk
            FOREIGN KEY (cod_departamento)
            REFERENCES sector_energetico.ipem_departamental (cod_departamento);
    END IF;
END $$;

-- La región es obligatoria: sin ella el municipio desaparece del filtro por región.
ALTER TABLE sector_energetico.ipem_departamental
    ALTER COLUMN region SET NOT NULL;

COMMENT ON CONSTRAINT ipem_municipal_quintil_vocabulario
    ON sector_energetico.ipem_municipal IS
    'Las cinco etiquetas del informe del MME. Sin esta restricción, una entrega con '
    'otra nomenclatura dejaba el tablero sin clasificación y sin error visible.';
