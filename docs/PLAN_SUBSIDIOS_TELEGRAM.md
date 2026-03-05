# Plan Integral: Subsidios en Telegram — Base_Subsidios_DDE.xlsx → PostgreSQL → Chatbot

> **Autor**: Copilot (análisis automatizado)  
> **Fecha**: Julio 2025  
> **Archivo fuente**: `data/onedrive/Base_Subsidios_DDE.xlsx` (3.8 MB)  
> **SharePoint**: `https://minenergiacol.sharepoint.com/sites/msteams_c07b9d_609752` (enlace privado, requiere auth)  
> **Requisito crítico**: El chatbot de Telegram NO usa IA para responder. Solo consultas SQL directas a PostgreSQL.

---

## PARTE 1: ENTENDIMIENTO PROFUNDO DE LOS DATOS

### 1.1 Estructura del archivo Excel (6 hojas)

| Hoja | Filas | Columnas útiles | Propósito |
|------|-------|-----------------|-----------|
| **Pagos** | 13,014 (12,920 tras dedup) | 26 | **PRINCIPAL** — Cada fila es un ítem de pago de subsidio |
| **Validación** | 14,219 | 15 | Estado de validación por empresa/trimestre |
| **Conciliación** | 7,979 | 18 | Radicados ARGO y estado de conciliación |
| **Mapa** | 1,205 | 6 | Cobertura geográfica: departamento, municipio, empresa, usuarios |
| **Inicio** | 219 | 12 | Catálogo de empresas prestadoras (código SUI, NIT, tipo, departamento) |
| **KPI'S Subsidios** | 17 | 0 útiles | Solo tiene columnas "Unnamed" — hoja decorativa/dashboard |

### 1.2 Hoja PAGOS — Modelo de datos detallado

#### Columnas (26 útiles)

| # | Columna | Tipo | Completitud | Descripción |
|---|---------|------|-------------|-------------|
| 0 | Fecha actualización | datetime | 100% | Última fecha de actualización del registro |
| 1 | Persona Actualiza | text | 100% | Quién actualizó (ej: "Diana G") |
| 2 | **Fondo** | text | 100% | `FSSRI` (10,579 filas) o `FOES` (2,435 filas) |
| 3 | **Area** | text | 81.3% | `SIN` (6,144), `ZNI` (4,435), `NULL` (2,435=100% FOES) |
| 4 | Año | int | 100% | Año del concepto del subsidio |
| 5 | Trimestre | mixed | 64.2% | Número del trimestre (1-4). **35.8% NULL** = registros FOES y YYYY/T |
| 6 | **Concepto Trimestre** | text | 100% | Formato `YYYY/Tn` (ej: 2024/T3) o `YYYY/T` (sin número, años anteriores) |
| 7 | Código SUI/FSSRI | text | 100% | Código numérico del prestador |
| 8 | **Nombre del Prestador** | text | 100% | Nombre completo de la empresa (231 empresas únicas) |
| 9 | Estado Resolución | text | 100% | "Ejecutoriada" (96.5%), "Notificada" (1.8%), otros |
| 10 | **No. de Resolución** | int | 100% | Número de resolución (543 únicos, rango ~1 a ~460+) |
| 11 | Fecha Resolución | datetime | 97.8% | Fecha de expedición de la resolución |
| 12 | **Valor Resolución** | float | 100% | Monto total asignado por la resolución para este ítem |
| 13 | Link Resolución | text | 72.1% | URL al documento de la resolución |
| 14 | **Tipo de Giro** | text | 79.4% | Tipo de desembolso (ver detalle abajo) |
| 15 | Distribuidor Mayorista/Combustible | text | 2.5% | Solo para Electrocombustible con proveedor |
| 16 | **Estado Pago** | text | 100% | `Pagado` (12,937) o `Pendiente` (77) |
| 17 | Tipo Pago | text | 68.5% | "Principal", "Adicional", etc. |
| 18 | **Valor Pagado** | float | 100% | Monto efectivamente pagado |
| 19 | %Pagado | float | 53.9% | **NO confiable** — 12,411 de 13,014 no coinciden con el cálculo |
| 20 | **Diferencia (Saldo Pendiente)** | float | 100% | `= Valor Resolución - Valor Pagado` (verificado al 100%) |
| 21 | Observación | text | 20.9% | Notas libres |
| 22 | A COD General | text | 83.3% | Código general concatenado |
| 23 | **Año / Trimestre Resolución** | text | 97.5% | Periodo de la resolución (diferente del concepto del subsidio) |
| 24 | Valor Disponible | float | 79.8% | Valor disponible |
| 25 | Valor Disponible 2 | float | 0.6% | Segundo valor disponible (casi vacío) |

#### Tipo de Giro (columna 14) — Desglose

| Tipo de Giro | Filas | Fondo | Area | Descripción |
|---|---|---|---|---|
| Electrocombustible | 4,379 | FSSRI | ZNI | Pago a empresas ZNI por combustible para generación |
| Directo a la Empresa | 2,588 | FSSRI | ZNI | Pago directo al prestador de ZNI |
| Subsidios por menores tarifas | 2,989 | FSSRI+FOES | SIN+FOES | Compensación por tarifas por debajo del costo |
| Menores Tarifas | 27 | FSSRI | SIN | Variante del anterior (probablemente histórico) |
| Pago Mes Nov/Dic/Ago 2024 | 33 | FOES | FOES | Pagos mensuales FOES (no trimestrales) |
| `NULL` (sin tipo) | 2,575 | FSSRI+FOES | SIN+FOES | Registros sin clasificar |
| Otros (empresa-específicos) | ~7 | FSSRI | ZNI | Pagos a empresas individuales de ZNI |

### 1.3 Hallazgos críticos del análisis de correlación

#### A. NO existe llave natural única

- `(Resolución)` → solo 543 grupos, 500 con duplicados
- `(Resolución + Empresa)` → 10,595 grupos, 1,193 duplicados
- `(Resolución + Empresa + ConceptoTrimestre)` → 11,890 grupos, 629 duplicados
- `(Resolución + Empresa + ConceptoTrimestre + TipoGiro)` → 11,894 grupos, 627 duplicados
- `(Resolución + Empresa + ConceptoTrimestre + TipoGiro + DistMayorista)` → con `dropna=False` **NO mejora** (627 dups, porque los duplicados de Electrocombustible tienen DistMayorista=NULL)

**Conclusión**: Los duplicados de clave son **sub-ítems legítimos** (ej: una resolución de Electrocombustible para la misma empresa/trimestre puede tener múltiples pagos a diferentes proveedores de combustible con montos diferentes). Cada fila ES un ítem separado que debe SUMARSE.

#### B. 94 filas son duplicados EXACTOS (error de datos)

- 162 filas son parte de duplicados exactos → al eliminar se quedan 12,920 filas
- Todos en FSSRI: 94 "Directo a la Empresa" + 68 "Electrocombustible"
- **Acción ETL**: Eliminar duplicados exactos (`DROP DUPLICATES`)

#### C. Patrón temporal dual: `YYYY/T` vs `YYYY/Tn`

| Formato | Filas | Fondos | Rango | Deuda |
|---|---|---|---|---|
| `YYYY/T` (sin número) | 4,661 | FSSRI: 2,661, FOES: 2,000 | 2015/T a 2025/T | $0 (todo pagado) |
| `YYYY/Tn` (con número) | 8,353 | FSSRI: 7,918, FOES: 435 | FSSRI: 2016/T1–2025/T4, FOES: 2023/T3–2025/T4 | $1,318.09B (toda la deuda) |

**Interpretación**:
- `YYYY/T` = Pago anual consolidado (registros antes de ~2023 y FOES antes de 2023/T3). Están al 100% pagados.
- `YYYY/Tn` = Pago trimestral específico (registros modernos). Toda la deuda está aquí.
- **Para "¿hasta qué trimestre está pagado?"** solo se consideran registros `YYYY/Tn`.

#### D. Las resoluciones cruzan periodos de subsidio (cross-temporal)

- **Solo el 15.1%** de las filas tienen el mismo periodo de subsidio y periodo de resolución
- El **84.9%** tiene periodos diferentes → una resolución de 2026 puede pagar subsidios de 2025/T1
- Toda la deuda pendiente ($1,318B) aparece en resoluciones con "Año / Trimestre Resolución" = 2026/Tn
- Esto significa que las resoluciones de 2026 ya fueron creadas pero aún no pagadas

#### E. FOES no tiene Area ni Trimestre numérico

- FOES: 2,435 filas, **100% = Area NULL** (Diana: "para no confusiones se dejó como NA")
- FOES: 82% sin Trimestre numérico (usa YYYY/T)
- FOES: 98% sin Tipo de Giro
- **FOES no tiene deuda pendiente** ($0 deuda)

#### F. Distribución de la deuda

| Categoría | Deuda total | Nota |
|---|---|---|
| **TOTAL** | **$1,318.09 mil millones** | Solo 77 filas pendientes de 12,920 |
| FSSRI | $1,318.09B | 100% de la deuda |
| FOES | $0 | Sin deuda |
| Área SIN | $1,318.09B | 100% de la deuda |
| Área ZNI | $0 | Sin deuda |

**Top 5 deudores:**
1. FINANCIERA DE DESARROLLO NACIONAL: $227,285 M
2. EPM: $187,286 M
3. CELSIA COLOMBIA: $171,904 M
4. CENS: $90,916 M
5. AVAL FIDUCIARIA: $76,764 M

#### G. Trimestres con deuda pendiente

```
2018/T2, 2018/T3, 2018/T4,
2019/T1, 2019/T2, 2019/T3, 2019/T4,
2020/T1, 2020/T2, 2020/T3, 2020/T4,
2021/T1, 2021/T2,
2025/T1, 2025/T2, 2025/T3
```

**CEDENAR es la única empresa con deuda histórica (2018-2021)**. Las demás solo deben 2025/T1-T3.

#### H. Un trimestre posterior PUEDE estar pagado mientras uno anterior está pendiente

Ejemplo AIR-E: 2025/T4 está pagado, pero 2025/T3 tiene saldo pendiente. Esto invalida la lógica de "último trimestre consecutivo pagado" — hay que reportar cada trimestre individualmente.

### 1.4 Hojas auxiliares

#### Inicio (catálogo de empresas)
- 219 empresas con: Código SUI/FSSRI, NIT, nombre, sigla, estado (A/C/D), tipo (D/S/E), fuente generación, departamento, municipio, profesional encargado
- **Match con Pagos**: solo 126 de 231 empresas de Pagos existen en Inicio (55% match)
- Las 105 empresas solo en Pagos son probablemente: fiduciarias, empresas históricas, o nombres con variaciones
- **Uso**: enriquecer datos del chatbot (departamento, tipo empresa, profesional)

#### Conciliación (estado de conciliación)
- 7,979 registros: Empresa × Año × Trimestre → ¿envió conciliación? + Radicado ARGO
- Tiene A-ALCANCE/I-INICIAL column para tipo de conciliación
- **Uso potencial**: verificar si empresa tiene conciliaciones pendientes

#### Validación (estado de validación)
- 14,219 registros: Empresa × Año × Trimestre → Estado de validación (VF=validación final)
- **Uso potencial**: verificar si subsidios están validados antes de pago

#### Mapa (cobertura geográfica)
- 1,205 registros: Departamento × Municipio × Empresa → # localidades y # usuarios
- **Uso potencial**: consultas geográficas (¿cuántos usuarios tiene empresa X?)

---

## PARTE 2: DISEÑO DE BASE DE DATOS

### 2.1 Tabla principal: `subsidios_pagos`

```sql
CREATE TABLE IF NOT EXISTS subsidios_pagos (
    id                              SERIAL PRIMARY KEY,
    fecha_actualizacion             TIMESTAMP,
    persona_actualiza               VARCHAR(100),
    fondo                           VARCHAR(10) NOT NULL,       -- FSSRI o FOES
    area                            VARCHAR(5),                 -- SIN, ZNI, NULL (FOES)
    anio                            INTEGER NOT NULL,
    trimestre                       INTEGER,                    -- 1-4, NULL para YYYY/T
    concepto_trimestre              VARCHAR(10) NOT NULL,       -- 2024/T3 o 2023/T
    codigo_sui                      VARCHAR(20),
    nombre_prestador                VARCHAR(200) NOT NULL,
    estado_resolucion               VARCHAR(50),
    no_resolucion                   INTEGER NOT NULL,
    fecha_resolucion                DATE,
    valor_resolucion                NUMERIC(18,2) NOT NULL DEFAULT 0,
    link_resolucion                 TEXT,
    tipo_giro                       VARCHAR(100),
    distribuidor_mayorista          VARCHAR(200),
    estado_pago                     VARCHAR(20) NOT NULL,       -- Pagado/Pendiente
    tipo_pago                       VARCHAR(50),
    valor_pagado                    NUMERIC(18,2) NOT NULL DEFAULT 0,
    pct_pagado                      NUMERIC(8,4),
    saldo_pendiente                 NUMERIC(18,2) NOT NULL DEFAULT 0,
    observacion                     TEXT,
    cod_general                     VARCHAR(50),
    anio_trimestre_resolucion       VARCHAR(20),
    valor_disponible                NUMERIC(18,2),
    valor_disponible_2              NUMERIC(18,2),
    -- Metadatos ETL
    fecha_importacion               TIMESTAMP DEFAULT NOW(),
    hash_fila                       VARCHAR(64),                -- SHA256 para dedup
    CONSTRAINT chk_fondo CHECK (fondo IN ('FSSRI', 'FOES')),
    CONSTRAINT chk_estado_pago CHECK (estado_pago IN ('Pagado', 'Pendiente')),
    CONSTRAINT chk_saldo_consistencia CHECK (
        ABS(valor_resolucion - valor_pagado - saldo_pendiente) < 1
    )
);

-- Índices para las 9 preguntas del chatbot
CREATE INDEX idx_subsidios_fondo ON subsidios_pagos(fondo);
CREATE INDEX idx_subsidios_area ON subsidios_pagos(area);
CREATE INDEX idx_subsidios_nombre_prestador ON subsidios_pagos(nombre_prestador);
CREATE INDEX idx_subsidios_estado_pago ON subsidios_pagos(estado_pago);
CREATE INDEX idx_subsidios_concepto_trimestre ON subsidios_pagos(concepto_trimestre);
CREATE INDEX idx_subsidios_no_resolucion ON subsidios_pagos(no_resolucion);
CREATE INDEX idx_subsidios_anio_trim_resol ON subsidios_pagos(anio_trimestre_resolucion);
-- Índice compuesto para búsqueda búsqueda rápida por empresa + fondo
CREATE INDEX idx_subsidios_empresa_fondo ON subsidios_pagos(nombre_prestador, fondo);
-- Índice para deduplicación
CREATE UNIQUE INDEX idx_subsidios_hash ON subsidios_pagos(hash_fila);
```

### 2.2 Tablas auxiliares

```sql
-- Catálogo de empresas (hoja Inicio)
CREATE TABLE IF NOT EXISTS subsidios_empresas (
    id                  SERIAL PRIMARY KEY,
    fondo               VARCHAR(10),
    subclase            VARCHAR(10),
    codigo_sui          VARCHAR(20) UNIQUE NOT NULL,
    nit                 VARCHAR(20),
    nombre_prestador    VARCHAR(200) NOT NULL,
    sigla               VARCHAR(100),
    estado              CHAR(1),        -- A=Activa, C=Cerrada, D=Desaparecida
    tipo_empresa        CHAR(1),        -- D=Deficitaria, S=Superavitaria, E=Exenta
    fuente_generacion   VARCHAR(100),
    departamento        VARCHAR(200),
    municipio           VARCHAR(200),
    profesional         VARCHAR(100),
    fecha_importacion   TIMESTAMP DEFAULT NOW()
);

-- Cobertura geográfica (hoja Mapa)
CREATE TABLE IF NOT EXISTS subsidios_mapa (
    id                  SERIAL PRIMARY KEY,
    departamento        VARCHAR(100) NOT NULL,
    municipio           VARCHAR(100) NOT NULL,
    area                VARCHAR(5),         -- SIN/ZNI
    nombre_prestador    VARCHAR(200),
    localidades         INTEGER,
    usuarios            INTEGER,
    fecha_importacion   TIMESTAMP DEFAULT NOW()
);

-- LOG de importaciones para auditoría
CREATE TABLE IF NOT EXISTS subsidios_import_log (
    id                  SERIAL PRIMARY KEY,
    fecha               TIMESTAMP DEFAULT NOW(),
    archivo             VARCHAR(500),
    filas_leidas        INTEGER,
    filas_importadas    INTEGER,
    filas_duplicadas    INTEGER,
    filas_error         INTEGER,
    duracion_seg        NUMERIC(8,2),
    observaciones       TEXT
);
```

---

## PARTE 3: LÓGICA SQL PARA LAS 9 PREGUNTAS

### P1: ¿Cuánto se debe a hoy a las empresas?

```sql
-- Total
SELECT SUM(saldo_pendiente) AS deuda_total FROM subsidios_pagos;

-- Desglose por fondo
SELECT fondo, SUM(saldo_pendiente) AS deuda
FROM subsidios_pagos
GROUP BY fondo
ORDER BY deuda DESC;

-- Desglose por área (SIN vs ZNI)
SELECT COALESCE(area, 'FOES (sin área)') AS area, SUM(saldo_pendiente) AS deuda
FROM subsidios_pagos
GROUP BY area
ORDER BY deuda DESC;
```

### P2: ¿Cuánto se le debe en subsidios a una empresa específica?

```sql
-- Búsqueda flexible por nombre (case-insensitive, parcial)
SELECT nombre_prestador,
       SUM(saldo_pendiente) AS deuda,
       COUNT(*) AS lineas_pendientes
FROM subsidios_pagos
WHERE estado_pago = 'Pendiente'
  AND LOWER(nombre_prestador) LIKE LOWER('%{empresa}%')
GROUP BY nombre_prestador
ORDER BY deuda DESC;
```

### P3: ¿Hasta qué trimestre está pagado?

**IMPORTANTE**: No se puede usar "último trimestre consecutivo" porque hay trimestres saltados.
La lógica correcta es: listar todos los trimestres con deuda pendiente.

```sql
-- A nivel total: trimestres con deuda pendiente
SELECT concepto_trimestre,
       COUNT(DISTINCT nombre_prestador) AS empresas_con_deuda,
       SUM(saldo_pendiente) AS deuda
FROM subsidios_pagos
WHERE estado_pago = 'Pendiente'
  AND concepto_trimestre ~ '^\d{4}/T\d$'  -- Solo formato YYYY/Tn
GROUP BY concepto_trimestre
ORDER BY concepto_trimestre;

-- Por empresa: último trimestre 100% pagado
WITH trim_status AS (
    SELECT nombre_prestador,
           concepto_trimestre,
           CASE WHEN SUM(saldo_pendiente) = 0 THEN 'PAGADO'
                WHEN SUM(saldo_pendiente) < SUM(valor_resolucion) THEN 'PARCIAL'
                ELSE 'PENDIENTE'
           END AS estado
    FROM subsidios_pagos
    WHERE concepto_trimestre ~ '^\d{4}/T\d$'
    GROUP BY nombre_prestador, concepto_trimestre
)
SELECT nombre_prestador,
       MAX(CASE WHEN estado = 'PAGADO' THEN concepto_trimestre END) AS ultimo_pagado,
       MIN(CASE WHEN estado != 'PAGADO' THEN concepto_trimestre END) AS primer_pendiente
FROM trim_status
WHERE nombre_prestador LIKE '%{empresa}%'
GROUP BY nombre_prestador;
```

### P4: ¿Cuántas resoluciones se generaron en un año?

```sql
SELECT LEFT(anio_trimestre_resolucion, 4) AS anio,
       COUNT(DISTINCT no_resolucion) AS total_resoluciones
FROM subsidios_pagos
WHERE LEFT(anio_trimestre_resolucion, 4) = '{año}'
GROUP BY LEFT(anio_trimestre_resolucion, 4);
```

### P5: ¿Cuántas resoluciones están pagadas y cuántas pendientes?

```sql
WITH resol_status AS (
    SELECT no_resolucion,
           CASE
               WHEN BOOL_AND(estado_pago = 'Pagado') THEN 'PAGADO'
               WHEN BOOL_OR(estado_pago = 'Pagado') THEN 'PARCIAL'
               ELSE 'PENDIENTE'
           END AS estado
    FROM subsidios_pagos
    GROUP BY no_resolucion
)
SELECT estado, COUNT(*) AS cantidad
FROM resol_status
GROUP BY estado
ORDER BY cantidad DESC;
```

### P7: ¿Cuál es el porcentaje pagado de las resoluciones asignadas?

```sql
SELECT
    SUM(valor_resolucion) AS total_asignado,
    SUM(valor_pagado) AS total_pagado,
    ROUND(SUM(valor_pagado) / NULLIF(SUM(valor_resolucion), 0) * 100, 2) AS pct_pagado
FROM subsidios_pagos;

-- Desglose por fondo
SELECT fondo,
       SUM(valor_resolucion) AS asignado,
       SUM(valor_pagado) AS pagado,
       ROUND(SUM(valor_pagado) / NULLIF(SUM(valor_resolucion), 0) * 100, 2) AS pct
FROM subsidios_pagos
GROUP BY fondo;
```

### P8: ¿Cuánto se le debe a una empresa por FSSRI y por FOES?

```sql
SELECT nombre_prestador, fondo,
       SUM(saldo_pendiente) AS deuda
FROM subsidios_pagos
WHERE LOWER(nombre_prestador) LIKE LOWER('%{empresa}%')
GROUP BY nombre_prestador, fondo
HAVING SUM(saldo_pendiente) > 0
ORDER BY deuda DESC;
```

### P9: ¿Cuánto fue el valor pagado por subsidios en un año específico?

```sql
-- Por año de la RESOLUCIÓN (cuándo se reconoció el subsidio)
SELECT LEFT(anio_trimestre_resolucion, 4) AS anio,
       SUM(valor_resolucion) AS total_asignado,
       SUM(valor_pagado) AS total_pagado,
       SUM(saldo_pendiente) AS pendiente
FROM subsidios_pagos
WHERE LEFT(anio_trimestre_resolucion, 4) = '{año}'
GROUP BY LEFT(anio_trimestre_resolucion, 4);

-- Por año del CONCEPTO del subsidio (cuándo se prestó el servicio)
SELECT LEFT(concepto_trimestre, 4) AS anio,
       SUM(valor_resolucion) AS total_asignado,
       SUM(valor_pagado) AS total_pagado
FROM subsidios_pagos
WHERE LEFT(concepto_trimestre, 4) = '{año}'
GROUP BY LEFT(concepto_trimestre, 4);
```

---

## PARTE 4: PLAN DE IMPLEMENTACIÓN

### Fase 1: ETL — Excel → PostgreSQL
**Archivo**: `etl/etl_subsidios.py`

1. Leer `Base_Subsidios_DDE.xlsx` (hojas: Pagos, Inicio, Mapa)
2. Eliminar duplicados exactos (94 filas)
3. Normalizar nombres de columnas (snake_case)
4. Calcular `hash_fila` = SHA256 de todas las columnas para dedup incremental
5. Insertar con `ON CONFLICT (hash_fila) DO NOTHING` para importaciones repetidas
6. Registrar en `subsidios_import_log`

**Estrategia de duplicados**:
- Los 94 duplicados exactos: eliminar (son errores de copia)
- Los ~627 grupos con misma clave pero diferentes valores: **CONSERVAR** (son sub-ítems legítimos de Electrocombustible)
- Para las 9 preguntas: siempre usar `SUM()` — nunca `COUNT(DISTINCT resolución)` para montos

### Fase 2: Sincronización automática
**Archivo**: agregar entry en `scripts/arcgis/onedrive_archivos.json`

```json
{
    "nombre": "Base_Subsidios_DDE",
    "tipo": "subsidios_pagos",
    "hoja": "Pagos",
    "url_sharepoint": "https://minenergiacol.sharepoint.com/:x:/r/sites/msteams_c07b9d_609752/_layouts/15/Doc.aspx?sourcedoc=%7B751521B2-15FE-4300-A140-05067D142FB6%7D",
    "site_id": "msteams_c07b9d_609752",
    "document_guid": "751521B2-15FE-4300-A140-05067D142FB6",
    "destino_local": "data/onedrive/Base_Subsidios_DDE.xlsx"
}
```

**Prerequisito**: Configurar credenciales Microsoft Graph API en `scripts/arcgis/.env`:
- `MS_TENANT_ID` (del Azure AD del Ministerio)
- `MS_CLIENT_ID` (App Registration)
- `MS_CLIENT_SECRET` (Client Secret)

**Cron**: Agregar al cron existente de las 7 AM o crear uno independiente.

### Fase 3: Chatbot Telegram (SIN IA)
**Archivo**: `whatsapp_bot/subsidios_handler.py` (NUEVO)

#### Comandos propuestos:

| Comando | Pregunta Diana | Ejemplo de uso |
|---|---|---|
| `/deuda` | P1 | Muestra deuda total, por fondo y por área |
| `/deuda [empresa]` | P2 | `/deuda CELSIA` → deuda de Celsia |
| `/trimestre_pagado` | P3 | Último trimestre pagado (total) |
| `/trimestre_pagado [empresa]` | P3 | `/trimestre_pagado EPM` |
| `/resoluciones [año]` | P4 | `/resoluciones 2024` → 72 resoluciones |
| `/resoluciones_estado` | P5 | Pagadas: 539, Pendientes: 2, Parcial: 2 |
| `/porcentaje_pagado` | P7 | % pagado total y por fondo |
| `/deuda_fondo [empresa]` | P8 | `/deuda_fondo CELSIA` → FSSRI: $X, FOES: $Y |
| `/pagado_anio [año]` | P9 | `/pagado_anio 2024` → $4,233B pagados |

#### Arquitectura:

```
Telegram → telegram_polling.py → detecta comando /subsidio*
         → SubsidiosHandler.handle(command, args)
         → SQL directo a PostgreSQL (psycopg2)
         → Formato texto → respuesta Telegram
```

**NO pasa por el orquestador API** (para evitar que la IA vea los datos).
**NO hay endpoint REST** para estos datos (seguridad).

### Fase 4: Seguridad y auditoría

1. **Lista blanca**: Solo usuarios autorizados pueden usar comandos `/subsidio*`
   - Tabla `subsidios_usuarios_autorizados (telegram_id, nombre, rol, fecha_alta)`
   - Verificar `telegram_id` antes de ejecutar cualquier consulta
2. **Log de consultas**: Registrar cada consulta en tabla de auditoría
   - `subsidios_audit_log (id, telegram_id, comando, parametros, timestamp)`
3. **Sin cache Redis**: Los datos de subsidios NO se guardan en Redis (privacidad)
4. **Sin IA**: El handler responde directamente con datos SQL formateados

---

## PARTE 5: REGLAS DE NEGOCIO DOCUMENTADAS

### Regla 1: Cada fila es un ítem de pago separado
- SIEMPRE usar `SUM()` para agregar montos
- Nunca asumir que una resolución = una fila
- Una resolución puede tener 40+ empresas × múltiples trimestres

### Regla 2: FOES no tiene Area
- Diana: "para no confusiones se dejó como NA"
- En queries por área, FOES no aparece en SIN ni ZNI
- Para "total por área", incluir FOES como categoría separada

### Regla 3: Formato temporal dual
- `YYYY/T` (sin número) = pago anual consolidado, todo pagado, años 2015-2023
- `YYYY/Tn` (con número) = pago trimestral, año 2016+ con detalle progresivo
- Para "hasta qué trimestre pagado", SOLO considerar `YYYY/Tn`

### Regla 4: Las resoluciones cruzan periodos
- Una resolución de 2026 puede pagar subsidios de 2025/T1
- Para "valor pagado por año", clarificar: ¿año de resolución o año de subsidio?
- El chatbot debe preguntar cuál año quiere el usuario

### Regla 5: Los trimestres NO son consecutivos
- 2025/T4 puede estar pagado mientras 2025/T3 tiene saldo
- No usar lógica de "primer gap" para determinar "hasta dónde pagado"
- Reportar todos los trimestres pendientes explícitamente

### Regla 6: `ValorPagado + SaldoPendiente = ValorResolución` (siempre)
- Verificado al 100% en los 13,014 registros
- Esta es la validación de integridad más confiable

### Regla 7: `%Pagado` NO es confiable
- 12,411 de 13,014 filas tienen discrepancia
- Calcular siempre como: `valor_pagado / valor_resolucion * 100`

### Regla 8: CEDENAR tiene deuda histórica excepcional
- Única empresa con deuda desde 2018/T2 hasta 2021/T2
- Las demás 21 empresas con deuda solo deben 2025/T1-T3

### Regla 9: Búsqueda de empresas debe ser flexible
- 231 nombres en Pagos, solo 126 match exacto con catálogo Inicio
- Usar `ILIKE '%término%'` para búsquedas parciales
- Considerar tabla de aliases/sinónimos (ej: "EPM" → "EMPRESAS PÚBLICAS DE MEDELLÍN E.S.P. - EPM")

---

## PARTE 6: CIFRAS DE REFERENCIA (para validar importación)

| Métrica | Valor esperado |
|---|---|
| Total filas Pagos (tras dedup) | 12,920 |
| Empresas únicas | 231 |
| Resoluciones únicas | 543 |
| Valor total resoluciones | $30.68 billones |
| Valor total pagado | $29.37 billones |
| % pagado global | 95.70% |
| Deuda total pendiente | $1,318.09 mil millones |
| Filas pendientes | 77 |
| Resoluciones 100% pagadas | 539 |
| Resoluciones parciales | 2 |
| Resoluciones 100% pendientes | 2 |
| Años con resoluciones | 2015-2026 |

---

## PARTE 7: ARCHIVOS A CREAR/MODIFICAR

| Archivo | Acción | Descripción |
|---|---|---|
| `sql/subsidios_schema.sql` | CREAR | DDL de tablas, índices, constraints |
| `etl/etl_subsidios.py` | CREAR | Script ETL Excel → PostgreSQL |
| `whatsapp_bot/subsidios_handler.py` | CREAR | Handler de comandos /subsidio* para Telegram |
| `whatsapp_bot/telegram_polling.py` | MODIFICAR | Agregar routing a SubsidiosHandler |
| `scripts/arcgis/onedrive_archivos.json` | MODIFICAR | Agregar config de Base_Subsidios_DDE |
| `tests/test_subsidios.py` | CREAR | Tests de integración y validación |
| `docs/PLAN_SUBSIDIOS_TELEGRAM.md` | CREAR | Este documento |
