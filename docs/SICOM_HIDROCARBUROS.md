# Tableros SICOM — Dirección de Hidrocarburos

Migración del tablero Power BI **«Tablero Combustible SICOM»** al Portal del Viceministerio de
Energía, con actualización automática desde OneDrive.

Fecha: 2026-10-12 · Fuente: SICOM (Sistema de Información de Combustibles Líquidos)

---

## 1. Qué se entregó

Cuatro tableros nuevos dentro del grupo **Dirección de Hidrocarburos**, junto a los ya existentes
de Presupuesto y Exploración, con la misma tecnología, estilos y componentes del portal:

| Tablero | Ruta | Base SICOM | Metodología |
|---|---|---|---|
| Agentes SICOM | `/hidrocarburos/agentes` | cubo Agentes | §6, §12 |
| Compras de Combustibles | `/hidrocarburos/compras` | cubo Compras | §8, §13 |
| Compras EDS | `/hidrocarburos/compras-eds` | cubo Compras EDS | §9, §14 |
| Capacidad Operativa | `/hidrocarburos/capacidad` | cubo Capacidad | §7, §15 |

Las referencias «§» corresponden al *Informe de Consolidación y Análisis de Información de
Combustibles* que acompaña los datos en la carpeta de OneDrive.

### Equivalencia de visuales Power BI → portal

| Visual Power BI | Implementación en el portal |
|---|---|
| Tarjeta (card) | `Card` + KPI del portal |
| Embudo (funnel) | `components/dashboard/FunnelChart.tsx` (SVG propio, barras centradas) |
| Treemap | `components/dashboard/TreemapChart.tsx` (algoritmo *squarified*, el mismo de Power BI) |
| Barras 100 % apiladas | barra segmentada con leyenda |
| Barras apiladas | `@nivo/bar` con el tema del portal |
| Áreas | `@nivo/line` con `enableArea` |
| Circular | `@nivo/pie` |
| Cascada (waterfall) | `components/dashboard/WaterfallChart.tsx` |
| Columnas + línea | `components/dashboard/BarLineChart.tsx` (capa personalizada sobre Nivo) |
| **Azure Maps** | `components/maps/MapaCoropletaDepartamentos.tsx` — coropleta departamental sobre el GeoJSON que ya usa el portal |

No se añadió ninguna dependencia nueva: los visuales que Nivo no cubre se implementaron en SVG,
igual que `SemiPieChart`, `BulletChart` y `MapaEmbalsesSVG` ya existentes.

### Desviación deliberada respecto al .pbix

El visual **«Agentes por año»** del Power BI original es una dispersión cuyo eje X es
`Suma(AÑO CREACION)` — sumar años no tiene interpretación (da ~14 millones para un subtipo con
6.983 agentes). Se implementó la versión que describe la propia metodología §12.4: columnas por
año de creación más línea de acumulado. La desviación está anotada en el código y declarada al pie
del tablero.

---

## 1-bis. Extracción directa de los cubos (12-oct-2026)

> **Desde el 13-oct-2026 los cuatro tableros se alimentan del cubo**, no del Excel. La ruta de
> OneDrive (sección 2) sigue activa y cargando las tablas `sicom_*`, pero ya solo sirve de
> contraste: ninguna página del portal la consulta. Ver `v_sicom_contraste`.

Siguiendo el instructivo «Consulta de Cubos» del propio grupo (que explica cómo conectarse desde
Excel), se verificó que el mismo origen es accesible por programa y se construyó el pipeline.

```
Cubos OLAP de SICOM  ·  https://bi.sicom.gov.co/OLAP/msmdpump.dll
        │  XMLA sobre SOAP, autenticación básica, TLS verificado
        ▼
etl/sicom_olap_client.py     cliente XMLA (Discover + Execute, aplanado de MDDataSet)
        ▼
etl/etl_sicom_olap.py        un MDX por base, troceado por año de ciclo, limpieza, COPY
        ▼
PostgreSQL · hidrocarburos.sicom_olap_{agentes,capacidad,compras}
                             + sicom_olap_control (conciliación)
                             + v_sicom_olap_compras_eds (vista)
```

Cron: diario 13:30 (SICOM procesa los cubos por la mañana). Linaje en `ontologia.etl_lineage`,
pipeline `sicom_olap`.

### Dos obstáculos técnicos y cómo se resolvieron

1. **El servidor no envía su certificado intermedio.** El certificado de hoja es legítimo
   (`*.sicom.gov.co`, DigiCert, O=Ministerio de Minas y Energía), pero la cadena llega incompleta y
   cualquier cliente la rechaza. Se aporta el intermedio público en `config/sicom_ca_chain.pem`
   (intermedio + raíz, ambos públicos). **No se usa `verify=False` en ningún punto.**
2. **SSAS responde un MDDataSet, no una tabla.** Las celdas vienen separadas de los ejes y de forma
   dispersa; `_iter_mddataset` cruza `CellOrdinal` contra las tuplas del eje de filas para
   reconstruir cada registro.

Credenciales: cifradas en el vault del proyecto (`core/secrets.py`, claves `SICOM_XMLA_USER` y
`SICOM_XMLA_PASSWORD`). Es el primer consumidor del vault en producción; el resto de ETL lee `.env`.

### Lo que la extracción directa corrigió

| Problema de la ruta de Excel | Cómo se resuelve |
|---|---|
| Compras EDS truncado en 1.048.576 filas | No hay límite; se descarga por año de ciclo. |
| Compras: faltaba el 25,4 % del volumen | **Era un defecto de la exportación manual.** El cubo declara 347.143 millones y el Excel declaraba 344.932: el dato de SICOM siempre estuvo bien. |
| Municipios sin código DANE → 1,6 % «Sin asignar» | El cubo expone los códigos DANE. **1.009 de 1.009 municipios cruzan con `ontologia.dim_geografia`.** |
| Capacidad con magnitudes implausibles | El cubo tiene dimensión de **ciclo**, que el Excel colapsaba sumando 17 años. Ver abajo. |

### Tres hallazgos nuevos, que cambian cómo deben leerse las cifras

**a) `AGENTE CANTIDAD` es un conteo distinto: sumarlo sobre un cruce infla la cifra.**
El cubo declara **8.907 agentes**. El mismo cruce de atributos que hacía el Excel suma 10.665,
porque un agente con dos productos o dos proveedores se cuenta dos veces. Por eso se extrae el
`CODIGO SICOM AGENTE`: `COUNT(DISTINCT codigo_sicom_agente)` da 8.907, exactamente el total del
cubo. De esos, **6.803 están ACTIVO** y 2.104 INACTIVO.

> Consecuencia para el tablero: el KPI «Agentes Activos: 9.370» que viene de la ruta de Excel no es
> ni el total ni los activos. Las cifras defendibles son 8.907 registrados y 6.803 activos.

**b) La capacidad operativa se declara por ciclo.** Sumar los 17 años da 2,74 billones, que no es
capacidad instalada sino acumulación de declaraciones. Además, **cuatro ciclos (2011-09, 2012-05,
2012-06, 2012-07) concentran el 94 % del total**, con ~645.000 millones cada uno frente a una
mediana de 673 millones. Son atípicos de tres órdenes de magnitud; están pendientes de explicación
por parte de SICOM (ver `SICOM_SOLICITUD_DATOS.md`).

**c) Compras y Compras EDS salen del mismo cubo.** No existe ninguna medida «VOLUMEN COMPRA EDS» en
SICOM: el Excel llamaba así al `VOLUMEN COMPRADO` filtrado a estaciones de servicio. Aquí hay una
sola tabla de hechos y el criterio de EDS vive en la vista `v_sicom_olap_compras_eds`, visible y
auditable, en vez de escondido en una tabla dinámica.

### ⚠️ La trampa que hacía perder el 25 % del volumen en Compras

Es el hallazgo más importante de la migración, y aplica a cualquier consulta futura sobre estos
cubos.

**Cruzar por una dimensión a la que parte de los hechos no está asociada descarta esos hechos en
silencio.** En `SBI-Compras`, el 30,8 % del volumen está registrado **sin agente proveedor**. Si se
incluye cualquier atributo de la dimensión `[AGENTE PROVEEDOR]` en el producto cruzado —el tipo, el
nombre, el NIT o el código— esas filas desaparecen del resultado sin ningún aviso ni error.

Medido sobre el ciclo 2024, cuyo total real es 23.430.763.318:

| Atributo añadido al cruce | Desvío |
|---|---|
| `CODIGO SICOM AGENTE COMPRADOR` | 0,000 % |
| `TIPO` / `SUBTIPO AGENTE COMPRADOR` | 0,000 % |
| `CODIGO DANE MUNICIPIO AGENTE COMPRADOR` | 0,000 % |
| **cualquier atributo de `[AGENTE PROVEEDOR]`** | **30,812 %** |
| `PLANTA AGENTE PROVEEDOR` | 0,000 % |
| `MUNICIPIO PLANTA AGENTE PROVEEDOR` | 0,000 % |
| `PRODUCTO`, `MES CICLO` | 0,000 % |

`.ALLMEMBERS` no lo corrige: el miembro desconocido no está expuesto en la dimensión.

**Esto explica por qué el Excel perdía el 25,4 %:** su tabla dinámica incluía «Tipo agente
proveedor». No era un error de quien exportaba, es una trampa del modelo del cubo.

**Cómo se resuelve aquí:** la tabla de hechos identifica al proveedor por **planta**
(`planta_agente_proveedor` y su ubicación), no por agente. Con ese conjunto de atributos el detalle
concilia al **0,0000 %** contra el total del cubo. El coste es que no se tiene el agente proveedor
en el 100 % de las filas; a cambio no se pierde ni un galón. Las plantas sí identifican al
suministrador en la práctica («REFINERIA GCB», «PLANTA TERPEL MANSILLA»…), con un grupo «-» que son
precisamente las compras sin proveedor identificado y que ahora quedan visibles en vez de
desaparecer.

### Limpieza aplicada (metodología §10)

De los ocho pasos del proceso manual, los tres primeros —consolidar, organizar y convertir la tabla
dinámica en tabla— desaparecen por construcción: MDX ya devuelve una tabla plana sin fila de
totales. Los que sí se implementan, en `_limpiar`:

- Miembros estructurales de SSAS (`(All)`, `Unknown`) y miembros nulos. Ojo: cuando un atributo es
  nulo, SSAS devuelve un `Caption` vacío y un `UName` técnico como `[AGENTE].[OPERADA POR].&[]`;
  caer al `UName` metería ese texto en los datos.
- Espacios sobrantes (los nombres del Excel venían con espacios iniciales).
- Centinelas `-`, `nan`, vacío → NULL. **Cambio deliberado respecto a la ruta de Excel**, donde el
  guion se conservaba: en los cubos es claramente un relleno y dejarlo haría aparecer «-» como si
  fuera un departamento o una bandera.
- Coerción numérica explícita y verificación del conteo tras el COPY.

### Decisiones de ingeniería del ETL

Varias nacieron de una revisión de código posterior a la primera versión; se anotan porque no son
evidentes al leer el módulo.

- **Carga en dos fases.** Primero se descargan todos los trozos a CSV en disco (`tempfile`) y solo
  después se abre la transacción para reemplazar la tabla. Si se cargara trozo a trozo con la
  transacción abierta, quedaría abierta los ~17 minutos que tarda compras y mantendría el horizonte
  de `xmin` de toda la base, frenando el autovacuum de `portal_energetico` entera.
- **`DELETE` y no `TRUNCATE`.** TRUNCATE toma un bloqueo ACCESS EXCLUSIVE que dejaría los tableros
  sin poder leer durante la carga. Con DELETE los lectores siguen viendo la versión anterior hasta
  el commit. Se compensa con `VACUUM (ANALYZE)` posterior, fuera de la transacción.
- **Compuertas antes de confirmar.** Una respuesta vacía del cubo (reprocesamiento, permisos) habría
  borrado la tabla y confirmado la carga como exitosa. Ahora 0 filas aborta, y la conciliación contra
  el total del cubo es una compuerta, no un apunte en el log: si no cuadra, la transacción se
  deshace. Tolerancia 1e-6, solo para el redondeo de float.
- **Recarga parcial acotada.** `--desde` borra exactamente los años que reescribe (`= ANY(...)`), no
  un rango: un `>= año` podría borrar años que el cubo no devuelva y perder histórico en silencio.
  Sobre una base sin dimensión de ciclo, `--desde` se rechaza de entrada.
- **Candado entre corridas.** `pg_try_advisory_lock` por base, para que el cron y una ejecución a
  mano no se pisen.
- **Las corridas fallidas sí quedan registradas.** Como el rollback deshace el INSERT de control, el
  fallo se escribe aparte, con su motivo, en `sicom_olap_control.error`.
- **Medidas identificadas por `UName`, no por el Caption visible.** Si el servidor devolviera la
  etiqueta traducida o con otra capitalización, la columna entera quedaría en NULL sin dar error.
  Además se verifica con la primera fila que el cubo devolvió todos los atributos esperados.
- **Precisión decimal.** Las medidas se guardan con su texto original en NUMERIC; pasar por `float`
  recorta a ~15-17 cifras y la suma podría dejar de cuadrar con el total del cubo.
- **Memoria.** Los textos de los miembros se internan (se repiten muchísimo) y los nodos ya
  procesados se liberan del árbol de lxml, no solo con `clear()`. El pico por trozo baja de ~1 GB a
  unos cientos de MB, relevante en este servidor.

### Conciliación

Mucho más fuerte que la de la ruta de Excel: se consulta al cubo la medida **sin dimensiones** —su
total real— y se compara contra lo cargado. Para agentes se compara contra `COUNT(DISTINCT código)`,
no contra la suma. Queda registrado en `hidrocarburos.sicom_olap_control`.

### Operación

```bash
venv/bin/python3 etl/etl_sicom_olap.py --todas              # lo que corre el cron
venv/bin/python3 etl/etl_sicom_olap.py --base agentes
venv/bin/python3 etl/etl_sicom_olap.py --base compras --desde 2024
```

Log: `logs/etl_sicom_olap.log`. Los otros 11 catálogos de SICOM (Ventas, Productos-Precios,
Inventarios, Sanciones, Uso, Cupos-IPSE, Cupos-UPME, Ordenes-Pedidos y variantes, Documentos BPM)
están identificados y accesibles con el mismo cliente, pero no se extraen todavía.

### Qué cambió en los tableros al pasar al cubo

| | Antes (Excel) | Ahora (cubo) |
|---|---|---|
| Agentes — tarjeta principal | «Agentes activos: 9.370» | **8.907 registrados**, de ellos **6.802 activos** y 2.105 inactivos |
| Agentes — tipos | 8 | **11** (aparecen almacenador, agencia logística y fuerzas públicas) |
| Compras — volumen | 257.292 millones | **347.143 millones** (+34,9 %) |
| Compras EDS — cobertura | cortado en la «E», 3.307 compradores | **completo, 7.508 compradores** |
| Compras — proveedor | por agente (descartaba el 30,8 % del volumen) | por **planta** (no descarta nada) |
| Capacidad — filas | 29.213 (ciclos colapsados) | **880.027**, con año y mes de ciclo |
| Capacidad — serie temporal | no existía | gráfico por año de ciclo |
| Mapas | nombre de municipio, 1,6 % «Sin asignar» por homónimos | **código DANE**, sin ambigüedad |

La tarjeta de agentes es el cambio con más impacto para quien lea el tablero: la cifra bajó de
9.370 a 8.907 no porque se hayan perdido datos sino porque la anterior estaba inflada (ver más
arriba, «AGENTE CANTIDAD es un conteo distinto»).

### Estado del contraste al 13-oct-2026

```
base        filas cubo   filas Excel      suma cubo         suma Excel     dif
agentes         10.666         9.341          10.666              9.370   +13,8 %   (*)
capacidad      880.027        29.213   2.736.742.769.664  2.733.823.806.605   +0,1 %
compras      3.017.065       161.495     347.143.399.781    257.291.713.597  +34,9 %
```
(*) En agentes la comparación de sumas no es la relevante: ambas están infladas por el cruce. La
cifra buena es el conteo distinto, 8.907, que coincide exactamente con el total del cubo.

---

## 2. Actualización automática

Replica el mecanismo de los demás tableros del portal: OneDrive → detección de cambios → ETL →
PostgreSQL, sin intervención manual.

```
Carpeta OneDrive "Datos de hidrocarburos"
        │  (Microsoft Graph, credenciales de aplicación ya existentes)
        ▼
etl/etl_sharepoint_sync.py        entradas #11 SICOM_Agentes y #12 SICOM_Cubos4
        │                         direccionadas por `graph_path`, no por link de archivo
        ▼
data/onedrive/SICOM_Agentes.xlsx · SICOM_Cubos4.xlsx
        ▼
etl/etl_hidrocarburos_sicom.py    lectura en streaming + COPY, una transacción por archivo
        ▼
PostgreSQL · esquema hidrocarburos
        sicom_agentes · sicom_capacidad · sicom_compras · sicom_compras_eds
        sicom_carga_control  ← conciliación y cobertura de cada corrida
        ▼
BFF Next.js  /api/hidrocarburos/sicom/*   →   tableros
```

**Disparadores** (ya en el crontab, no hubo que tocarlo — ambos iteran `SHAREPOINT_FILES` completo):

- `etl_sharepoint_watcher.py` cada 5 min: consulta `lastModifiedDateTime` por Graph y dispara el
  ETL solo del archivo que cambió.
- `etl_sharepoint_sync.py` diario 04:02: pasada completa de respaldo.
- `monitor_sp_watcher.sh` cada 15 min: healthcheck del watcher.

**Por qué `graph_path` y no un link por archivo:** el recurso compartido es la *carpeta*; los Excel
se reemplazan dentro de ella en cada corte, lo que invalidaría un link `:x:` por archivo. El
mecanismo ya existía en el sync pero ninguna entrada lo usaba.

### Puesta en marcha / operación

```bash
# listar la configuración
venv/bin/python3 etl/etl_sharepoint_sync.py --listar

# forzar una corrida concreta
venv/bin/python3 etl/etl_sharepoint_sync.py --nombre SICOM_Cubos4 --forzar

# correr el ETL contra un Excel suelto, sin pasar por OneDrive
venv/bin/python3 etl/etl_hidrocarburos_sicom.py --cubos /ruta/Cubos4.xlsx
```

Logs: `logs/etl_hidrocarburos_sicom.log`, `logs/etl_sharepoint_sync.log`, `logs/sp_watcher.log`.
Linaje: `ontologia.etl_lineage`, pipeline `sicom_hidrocarburos` (este ETL es el primero del
pipeline de SharePoint que registra linaje; los demás no lo hacían).

Tiempo de carga de referencia: 1.239.283 filas en ~44 s.

---

## 3. Controles de calidad implementados

La metodología §17 pide «validación de totales antes y después de la transformación» y §19
distinguir la fecha del dato de la del tablero. El ETL lo hace en cada corrida y guarda el
resultado en `hidrocarburos.sicom_carga_control`; los tableros lo muestran en una franja superior.

Controles automáticos:

1. **Validación de encabezados.** Si el cubo cambia de estructura, el ETL falla con el detalle de
   qué columnas faltan o sobran, en vez de cargar datos corridos en silencio.
2. **Fila «Total general».** Las tablas dinámicas exportadas traen una fila de totales al final.
   Se separa (cargarla duplicaría los agregados), se usa para conciliar el detalle y se descarta.
   Tolerancia: 0,5 %.
3. **Detección de truncamiento.** Si una hoja llega a 1.048.575 filas de datos está cortada en el
   límite físico de Excel; se marca y se registra el rango cubierto.
4. **Verificación de conteo** tras el `COPY`, dentro de la misma transacción.

---

## 4. Hallazgos sobre los datos recibidos

Tres defectos encontrados al perfilar el corte del 2026-10-02. Los tres están **declarados en la
interfaz**, no corregidos silenciosamente.

### 4.1 Compras EDS está truncado · BLOQUEANTE

El export llegó al límite de filas de Excel (1.048.576 incluyendo encabezado) y quedó cortado
**alfabéticamente por comprador**: cubre de `CIUDAD LIMPIA BOGOTA SA. ESP (2411)` a
`ESTACION DE SERVICIO DISTRACOM SAN PABLO (3399)`. Faltan todos los compradores de la F a la Z.

Las cifras del tablero no son el total nacional y así se declara.

**Qué se necesita:** el extracto completo **troceado por año de ciclo** (ningún año individual se
acerca al millón de filas), o por rangos de comprador.

### 4.2 Compras no concilia con su propia fuente · BLOQUEANTE

| | Volumen comprado | Volumen en tránsito |
|---|---|---|
| Suma del detalle (161.495 filas) | 257.291.713.597 | 14.163.916.825 |
| Fila «Total general» del export | 344.931.636.719 | 14.164.103.103 |
| Diferencia | **−87.639.923.122 (−25,41 %)** | −186.278 (−0,001 %) |

El tránsito cuadra y el volumen comprado no, sobre **las mismas filas**. La diferencia está
repartida entre todos los años y tipos de agente, no concentrada. Es decir, no faltan registros:
los valores de `VOLUMEN COMPRADO` del detalle no suman lo que el propio cubo declara.

**Qué se necesita:** reexportar la hoja y conciliar contra el total del cubo antes de publicar
cualquier cifra de volumen de compras como oficial.

### 4.3 «Capacidad operativa» sin unidad y con magnitudes implausibles · ADVERTENCIA

- El cubo **no documenta la unidad de medida**.
- 648 registros de *distribuidor mayorista* (2,2 % de las filas) concentran el **94,9 %** de la
  capacidad total. Un solo registro llega a 2,4 × 10¹¹, frente a una mediana de 14.110 en
  estaciones de servicio. Como capacidad de almacenamiento estática no es físicamente plausible:
  apunta a otra unidad o a volumen acumulado.
- El 35,7 % de los registros tiene capacidad cero.

**Qué se necesita:** confirmación de la unidad y del criterio de registro de los mayoristas. Hasta
entonces el total agregado no debe publicarse como capacidad instalada del país.

### 4.4 Observaciones menores

- 45 agentes (0,5 %) no tienen año de creación; quedan fuera del gráfico por año, y así se indica.
- Los códigos de `PRODUCTO A COMERCIALIZAR` (`N`, `S`, `CLDP`, `CLDP Y GNV`) no están definidos en
  la documentación recibida. Se muestran tal cual, con la salvedad anotada.
- La metodología §8 advertía que «Tipo agente comprador» aparecía dos veces en la estructura de
  Compras. **Queda resuelto:** el archivo real tiene `TIPO AGENTE COMPRADOR` y `TIPO AGENTE
  PROVEEDOR`, campos distintos, más los municipios de planta de comprador y de proveedor.

---

## 5. Decisión sobre los mapas

Las bases de Compras y Compras EDS traen el municipio **sin departamento ni código DANE**, y en
Colombia 67 nombres de municipio se repiten entre departamentos (ARMENIA en Quindío y Antioquia,
RIONEGRO en Antioquia y Santander, SABANALARGA en tres…). Cruzar solo por nombre multiplicaría el
volumen de esos municipios por 2 o 3.

Regla aplicada: se resuelve únicamente lo inequívoco contra `ontologia.dim_geografia`
(vista `hidrocarburos.v_dane_municipio_unico`, función `hidrocarburos.f_clave_municipio`). Los
nombres ambiguos se agrupan visiblemente como **«Sin asignar»** en vez de atribuirlos a un
departamento por conjetura. Al corte actual eso deja el 98,4 % del volumen georreferenciado.

Única discrepancia de nomenclatura detectada: SICOM escribe «CALI», el DANE «Santiago De Cali».

Capacidad no necesita esta resolución: trae el departamento en la propia base.

---

## 6. Archivos

**Backend** (`/home/admonctrlxm/server/`)
- `sql/hidrocarburos_sicom_schema.sql` — DDL idempotente, índices, grants, función y vista de geografía
- `etl/etl_hidrocarburos_sicom.py` — ETL de las cuatro bases
- `etl/etl_sharepoint_sync.py` — entradas #11/#12 y handlers `etl_sicom_agentes` / `etl_sicom_cubos`

**Frontend** (`/home/admonctrlxm/portal-direccion-mme/`)
- `src/app/(dashboards)/hidrocarburos/{agentes,compras,compras-eds,capacidad}/page.tsx`
- `src/app/api/hidrocarburos/sicom/{agentes,compras,compras-eds,capacidad}/route.ts`
- `src/lib/sicom.ts` — contrato de cobertura compartido
- `src/components/dashboard/{CoberturaBanner,FunnelChart,TreemapChart,WaterfallChart,BarLineChart}.tsx`
- `src/components/maps/MapaCoropletaDepartamentos.tsx`
- `src/components/Header.tsx` — entradas de navegación
