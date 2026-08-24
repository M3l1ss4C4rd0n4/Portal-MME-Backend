# Fuentes del RAG del Portal MME

Documento de referencia — inventario completo de todas las plataformas/APIs externas usadas para alimentar el RAG del Asistente IA (`ontologia.informes_documentos` + `ontologia.informes_texto_embeddings`), qué se indexa de cada una, qué NO se indexa y por qué, y qué queda como backlog evaluado (investigado, con veredicto, sin implementar). Última actualización: 2026-08-21.

**Estado agregado actual**: 1.265 documentos, 25.725 fragmentos de texto (chunks), 15 `tema`s distintos, 4 entidades/plataformas externas activas + 1 fuente interna (SharePoint del Ministerio).

Todo el pipeline corre diariamente vía `scripts/ontologia/refresh_ontologia.py` → `scripts/ontologia/build_informes_embeddings.py::main()`, seguido de `scripts/ontologia/clasificar_tema_informes.py` (asigna `tema` por prefijo de `carpeta_origen`). El Asistente IA consulta este corpus a través del tool `buscar_texto_rag` (`domain/services/asistente_ia_service.py`), con `tema` como filtro opcional.

---

## Índice

1. [XM — repositorio público (api-portalxm.xm.com.co)](#1-xm--repositorio-público-api-portalxmxmcomco)
2. [XM / Ministerio — SharePoint interno (Microsoft Graph)](#2-xm--ministerio--sharepoint-interno-microsoft-graph)
3. [CREG — Gestor Normativo Alejandría 2.0](#3-creg--gestor-normativo-alejandría-20)
4. [UPME — normativa (misma plataforma Alejandría)](#4-upme--normativa-misma-plataforma-alejandría)
5. [Ministerio de Minas y Energía — normativa (misma plataforma Alejandría)](#5-ministerio-de-minas-y-energía--normativa-misma-plataforma-alejandría)
6. [UPME — publicaciones técnicas (sitio propio, WordPress)](#6-upme--publicaciones-técnicas-sitio-propio-wordpress)
7. [Ministerio de Minas y Energía — publicaciones misionales (sitio propio, Liferay)](#7-ministerio-de-minas-y-energía--publicaciones-misionales-sitio-propio-liferay)
8. [Fuentes investigadas y descartadas](#8-fuentes-investigadas-y-descartadas-con-evidencia)
9. [Estructura de base de datos común a todas las fuentes](#9-estructura-de-base-de-datos-común-a-todas-las-fuentes)
10. [Tabla resumen de temas (`tema`)](#10-tabla-resumen-de-temas-tema)

---

## 1. XM — repositorio público (api-portalxm.xm.com.co)

**Qué es**: el repositorio de archivos públicos que XM (operador del mercado eléctrico colombiano) expone sin autenticación en `https://api-portalxm.xm.com.co/administracion-archivos/ficheros`. Es el mismo árbol de carpetas que XM también sirve por FTPS bajo `/INFORMACION_XM/PUBLICO/...`, aquí accedido vía una API REST no documentada oficialmente (encontrada por inspección de red, no por documentación pública de XM).

**Cliente**: `infrastructure/xm/portalxm_client.py` — `listar_ficheros(ruta)`, `listar_todos_ficheros(ruta)` (paginado), `descargar_fichero(ruta)`. Nunca lanza excepción.

### Qué contiene la API completa (los 13 directorios raíz de `/M:/InformacionAgentes/Usuarios/Publico/`)

Verificado en vivo, archivo por archivo (no solo por nombre de carpeta — un primer intento asumiendo por nombre llevó a un proceso de 73 minutos por mala clasificación, ver Fase 33 del historial del proyecto):

| Carpeta raíz | Contenido real | ¿Se usa? |
|---|---|---|
| **PlaneacionOperacion** | Estudios narrativos de planeación: Corto/Mediano/Largo Plazo, Flexibilidad, Boletín Energético, Senda de Referencia | ✅ Parcialmente — es el ÚNICO corpus narrativo real de todo el repositorio |
| DESPACHO | Datos crudos de despacho diario (.txt) | ❌ No — dato numérico, ya cubierto por el ETL oficial `pydataxm` hacia `sector_energetico.metrics` |
| INFODESPACHO | "Informe del Despacho" diario (PDF, 25-30 páginas) — solo las primeras 3 páginas son narrativas (resumen, novedades, indisponibilidades); el resto son tablas horarias | ✅ Parcialmente — solo primeras 3 páginas |
| DEMANDAS | Pronóstico oficial/propuesta CND/seguimiento de demanda (.txt/.xlsx diarios) + `indicadores` (PPTX mensual, ~40MB) | ❌ No — datos crudos; el PPTX de indicadores falló con error 500 del servidor de XM en el único intento, nunca reintentado |
| Genminimas | Mantenimientos programados por planta ("Reporte Mangen"), pruebas de generación — formato tabular | ❌ No — sin valor narrativo |
| OFERTAS (8 subcarpetas: CAOferta, Compromiso, DDV, desempate, DESPACHO, EVE, InfoHidro, INICIAL) | Ofertas de precio/despacho por agente (.txt) | ❌ No — datos crudos de mercado |
| PredespachoIdeal, PredespachoProgramado, Redespacho, VerPC | Datos numéricos de predespacho/redespacho | ❌ No — datos crudos |
| SIC | Módulo "COMERCIA" descontinuado desde 2016 | ❌ No — inactivo |
| INFORMAC (Iopf/Dispreal) | Archivos .csv | ❌ No — datos crudos |
| DespachoPreliminar | No explorada a fondo | ⚠️ Sin verificar — no confirmado ni descartado |

### PlaneacionOperacion — el corpus que sí se usa (6 subcarpetas)

Cada subcarpeta se investigó archivo por archivo, no solo por nombre — varias rutas "prometedoras" por nombre resultaron ser 100% datos crudos y se excluyeron explícitamente:

| Subcarpeta | Ruta(s) indexada(s) | `carpeta_origen` | Excluido en la misma subcarpeta (verificado, no solo por nombre) |
|---|---|---|---|
| **CortoPlazo** | `CortoPlazo/Informacion Energetica/<año>/<mes>/<semana>` (estructura 2024+) y `CortoPlazo/<año>/...` (estructura vieja 2021-2024, XM reorganizó su árbol en algún punto de 2024) | `PLANEACION_XM_CORTOPLAZO` | — |
| **Flexibilidad** | Carpeta completa | `PLANEACION_XM_FLEXIBILIDAD` | — |
| **LargoPlazo** | `AnalisisTrimestralRestricciones`, `InformacionEnergetica/AS/Resultados Estudios`, `IPOELP` | `PLANEACION_XM_LARGOPLAZO` | `CargoporConfiabilidad` (specs estáticas + datos), `CEE` (.txt crudo), `MinimosOperativos` (.xlsx crudo), `BasesDatosPowerFactoryLP`, `InformacionEnergetica/MPODE/Resultados Estudios` (0 PDFs pese al nombre prometedor) |
| **MedianoPlazo** | `EstudiosTrimestrales`, `Estudios Ecuador`, `Estudios EDAC` | `PLANEACION_XM_MEDIANOPLAZO` | `IPOEMP` (vacío en 5 muestras), `InformacionEnergetica/Resultados_Estudios` (0 PDF, solo .xlsx/.zip), `InformacionEnergetica/BoletinEnergetico` (356 archivos, verificado no narrativo — no confundir con el Boletín Energético real, ver fila siguiente), `BasesDatosPowerFactoryMP` |
| **MedianoyLargoPlazo** | `IPOEL` | `PLANEACION_XM_MEDIANOYLARGOPLAZO` | `IPOEMLP` (vacío), `BasesDatosPowerFactoryMLP/MP` |
| **Senda de Referencia** | — (carpeta completa excluida) | — | 100% `.xlsx` crudo (`Supuestos_Resultados_SendaReferencia_...`), confirmado en 2 años muestreados |
| — | **Boletín Energético** — hallado en `MedianoPlazo/InformacionEnergetica/BoletinEnergetico`, NO confundir con lo excluido arriba: 356 PDFs reales del "Boletín Energético"/"Panorama Energético" de XM (semanal, desde 2014) | `PLANEACION_XM_BOLETIN` | — |

**INFODESPACHO** (fuera de PlaneacionOperacion): `_indexar_infodespacho_xm()` — solo `PAGINAS_NARRATIVAS_INFODESPACHO = 3` primeras páginas por documento (de 25-30 totales), ventana `DIAS_INFORMES_XM = 14` días.

### Ventana de retención

`ANIOS_RETENCION_PLANEACION_XM = 2` — solo se conservan los últimos 2 años de Corto/Mediano/Largo Plazo/Flexibilidad/Boletín (decisión explícita del usuario: no acumular histórico innecesario del sector). El propio recorrido del árbol NO desciende a carpetas de año fuera de la ventana (ahorra llamadas), más una función de poda (`_podar_planeacion_xm_historico()`) que limpia cualquier documento que quede fuera de ventana al recalcularse cada corrida (ej. al cruzar de año calendario).

### Estado actual en base de datos

| `carpeta_origen` | `tema` | docs | tipo |
|---|---|---|---|
| PLANEACION_XM_CORTOPLAZO | planeacion_xm | 179 | pdf |
| PLANEACION_XM_LARGOPLAZO | planeacion_xm | 20 | pdf |
| PLANEACION_XM_MEDIANOPLAZO | planeacion_xm | 42 | pdf |
| PLANEACION_XM_MEDIANOYLARGOPLAZO | planeacion_xm | 10 | pdf |
| PLANEACION_XM_FLEXIBILIDAD | planeacion_xm | 9 | pdf |
| PLANEACION_XM_BOLETIN | boletin_energetico_xm | 71 | pdf |
| INFODESPACHO_XM | despacho | 14 | pdf |

---

## 2. XM / Ministerio — SharePoint interno (Microsoft Graph)

**Qué es**: el sitio SharePoint "Planeación estratégica - DEE" del propio Ministerio (drive interno, no público), accedido vía Microsoft Graph API con token de aplicación. A diferencia de las demás fuentes de este documento, este NO es un repositorio externo de terceros — es el propio almacenamiento documental interno del equipo.

**Cliente**: funciones internas de `scripts/ontologia/build_informes_embeddings.py` (`_procesar_item`, `_sp_download_item`, `_get_access_token`) sobre el drive `DRIVE_ID_PMO`.

### Qué se indexa (curado carpeta por carpeta, no todo el sitio)

El sitio completo tiene decenas de carpetas (PMO administrativo, contratos individuales por persona con datos personales, bases de datos internas, etc.) — se indexan solo las carpetas verificadas con contenido narrativo real y sin riesgo de exponer datos personales:

| `carpeta_origen` | Ruta SharePoint | `tema` |
|---|---|---|
| `/General/19. PMO` (+ subcarpeta Informes de Seguimiento) | PMO administrativo | `pmo_interno` / `metodologia_alertas` / `comunidades` (mixto, ver detalle abajo) |
| ACTAS_ELECTROCAQUETA | Actas de contratos OR | `comunidades` |
| COMUNIDADES_SOSTENIBILIDAD, COMUNIDADES_SEGUIMIENTOS, COMUNIDADES_RESOLUCIONES | `/General/01. Comunidades Energéticas/...` (3 subcarpetas específicas) | `comunidades` |
| COMUNIDADES_ESQUEMAS_COMERCIALIZACION | `/General/21. Esquemas de comercialización/...` (2 rutas) | `comunidades` |
| COLOMBIA_SOLAR_GENERAL, _REGULATORIO, _PRESENTACIONES, _CONTRATO_2026 | `/General/17. Colombia Solar 2025/...` (4 subcarpetas) | `colombia_solar` |
| SUBSIDIOS_CONCILIACIONES_SIN, _EXENTOS, _DIAGNOSTICO_STM | `/General/06. Subsidios/...` (3 subcarpetas) | `subsidios` |
| PROYECTOS_ESTRATEGICOS_INTERCONEXIONES | `/General/05.Proyectos estratégicos y regulación/02. Interconexiones` | `proyectos_estrategicos` |
| INFORME_EMPALME | Resuelto dinámicamente (archivo más reciente de una carpeta, caché 6h) | `informe_empalme` |
| BOLETINES_XM | Boletín/Panorama Energético (copia en SharePoint, distinta del hallado en el portal público de XM) | `panorama_climatico` |

### Explícitamente excluido de este sitio SharePoint (con motivo)

- **Carpetas "Soportes contratistas/contractuales"** de Supervisión, Colombia Solar, Comunidades y Fondos: archivos administrativos individuales por persona (decenas a cientos de MB c/u) — riesgo real de datos personales, no informes narrativos.
- **"01/02/03 Registros..." de Comunidades Energéticas**: ~200 resoluciones individuales por CE, casi idénticas entre sí — bajo valor semántico por unidad frente al costo de embeberlas. Solo se indexa el nivel directo de "08. Resoluciones".
- **"20. Trazabilidad Convocatoria y contratación ORs y Generadores"**: confirmado vacío en las hojas reales.
- **"24. FENOGE - Colombia Solar"**: 0 items en sus 3 subcarpetas.
- **"07. Reglamentos" y "13. Financiero DEE"**: investigadas, resultaron ser contenido administrativo/de RRHH sin valor narrativo.

---

## 3. CREG — Gestor Normativo Alejandría 2.0

**Qué es**: `gestornormativo.creg.gov.co`, operado por **Avance Jurídico Casa Editorial S.A.S.** (tercerizado) para la CREG. Plataforma de fragmentos HTML estáticos (no una API JSON formal, pero 100% curlable sin autenticación ni JS).

**Cliente**: `infrastructure/creg/gestor_normativo_client.py` — `listar_documentos_anio(tipo, año)` (páginas por año, patrón CREG), `listar_documentos_entidad(entidad, tipo)` (página única multi-año, patrón UPME/MME), `descargar_texto_documento(url_relativa)`.

### Qué contiene la plataforma completa (menú "Compilaciones" por entidad)

Cada entidad regulada tiene hasta 5 categorías de documento en esta plataforma:

| Categoría | ¿Se usa para CREG? | Motivo |
|---|---|---|
| **Resoluciones originales** | ✅ Sí | Es la norma vigente — la fuente de verdad regulatoria |
| **Circulares** | ✅ Sí | Instrucciones operativas vinculantes |
| **Proyectos de resolución** | ❌ No | Borradores, no vigentes — menor autoridad que la resolución final; no se encontró una página de listado limpia para descubrirlos sistemáticamente |
| **Conceptos** | ❌ No | Opiniones/interpretaciones jurídicas puntuales, no normas — no investigado a fondo, backlog |
| **Compilación jurídica** | ❌ No | No investigado |

### Formato del contenido

- Listado por año: `<tipo>_por_orden_cronologico_<año>.html` (fragmento con número/título/resumen/enlace por documento).
- Documento completo: `docs/resolucion_creg_<numero>_<año>.htm`, texto legal íntegro dentro de `<div class="panel-documento">` — incluye **anotaciones de vigencia** embebidas tipo `<Numeral modificado por el artículo 1 de la Resolución 101 112 de 2026. El nuevo texto es el siguiente:>`, el registro legislativo oficial de cada norma (usado por `scripts/ontologia/vigilancia_normativa_creg.py` NIVEL 1, ver más abajo).
- Inconsistencia real de formato: el texto visible omite ceros a la izquierda ("71 de 2006") mientras las URLs internas los rellenan ("0071_2006") — resuelto con `_normalizar_segmentos_numero_creg()`.

### Qué se indexa de CREG

1. **Corpus general**: resoluciones + circulares de los últimos `ANIOS_RETENCION_CREG = 3` años.
2. **Corpus núcleo** (`CREG_RESOLUCIONES_NUCLEO`, nunca se poda por año): las 8 resoluciones que sustentan directamente `core/umbrales_oficiales.py` (Índice NE, HSIN, PBP, Condición del Sistema):

   | Año | Número | Tema |
   |---|---|---|
   | 2014 | 026 | Estatuto de Riesgo de Desabastecimiento |
   | 2006 | 071 | Cargo por Confiabilidad / precio de escasez |
   | 2017 | 140 | Metodología precio marginal de escasez |
   | 2020 | 125 | Deroga Cap. II (inicio/fin período de riesgo) de 026/2014 |
   | 2020 | 209 | Senda de Referencia e Índice NE |
   | 2024 | 101_055 | Complemento al Estatuto de Desabastecimiento |
   | 2024 | 101_066 | 3 niveles de precio de escasez (PEI/PE/PES) |
   | 2026 | 101_112 | Deroga la regla del 70% absoluto del Índice NE |

### Qué NO se indexa de CREG y por qué

- **"Documentos CREG" técnicos** (series 901/905 — análisis de comentarios a proyectos de resolución, estudios técnicos, ej. "DOCUMENTO CREG-901 079 de 2025", 312 páginas sobre Comunidades Energéticas): **investigado el 2026-08-21, contenido real y valioso confirmado** (mismo dominio `gestornormativo.creg.gov.co`, curlable, `docs/pdf/doc_creg_<serie>_<numero>_<año>.pdf` y `docs/originales/<contexto>/<archivo>.pdf`), pero **sin página de listado sistemático encontrada** — cada documento vive en una carpeta nombrada según el proyecto de resolución/circular al que pertenece, sin un índice maestro descubierto. **Veredicto: no implementado por ahora** — esfuerzo de descubrimiento incierto, audiencia de nicho (economistas/abogados regulatorios), y el "Considerando" de las resoluciones ya indexadas cubre parcialmente el mismo razonamiento técnico. Ver sección 8.
- El sitio institucional `creg.gov.co` (NO el gestor normativo, dominio distinto, plataforma Nexura) se investigó como posible fuente adicional de "Documentos CREG": la URL encontrada (`loader.php?lServicio=Documentos&...`) devuelve una página de 6.5MB con 98% de relleno en blanco — no sirve contenido real de forma simple.

### Vigilancia normativa (mecanismo derivado, no una fuente nueva)

`scripts/ontologia/vigilancia_normativa_creg.py` — corre semanalmente sobre el corpus CREG ya indexado, en 2 niveles:
- **NIVEL 1** (alta confianza): parsea las anotaciones de vigencia embebidas en el texto de las 8 resoluciones núcleo — 25 modificaciones reales detectadas en los últimos 3 años.
- **NIVEL 2** (mejor esfuerzo): busca menciones textuales de las núcleo + palabra de modificación en el corpus general — 32 hallazgos únicos, auditados manualmente uno por uno (2026-08-20), ninguno reveló un bug nuevo más allá del ya corregido.

### Estado actual en base de datos

| `carpeta_origen` | docs | tipo | tema |
|---|---|---|---|
| CREG_RESOLUCIONES | 423 | html | creg_normativa |
| CREG_CIRCULARES | 313 | html | creg_normativa |
| CREG_RESOLUCIONES_NUCLEO | 8 | html | creg_normativa |

---

## 4. UPME — normativa (misma plataforma Alejandría)

**Qué es**: la MISMA plataforma Alejandría de Avance Jurídico (`gestornormativo.creg.gov.co`) también aloja la normativa de la UPME (Unidad de Planeación Minero Energética) — hallazgo de esta sesión (2026-08-20), nunca explorado antes pese a compartir infraestructura con lo ya usado para CREG.

**Diferencia estructural real con CREG**: en vez de páginas de listado por año, UPME (y MME, sección 5) sirven **una sola página con los 26 años completos** (2000-2026) ya renderizados en el HTML — `compilacion_resoluciones_unidad_planeacion_minero_energetica_upme.html` / `compilacion_circulares_unidad_planeacion_minero_energetica_upme.html`. Mismas clases CSS (`opcion-nueva`/`id-documento`/`descripcion-documento`) que los fragmentos por año de CREG — se reutilizó el mismo parser, con una función nueva `listar_documentos_entidad()` en vez de `listar_documentos_anio()`.

### Qué se indexa

Resoluciones + circulares de los últimos 3 años (`ANIOS_RETENCION_CREG`, mismo criterio de retención que CREG — filtrado en memoria tras traer la página completa, sin poda posterior necesaria porque nunca se llega a insertar lo que está fuera de ventana).

### Qué NO se indexa

- **Proyectos de resolución / Conceptos** de UPME: mismo motivo que CREG (borradores/opiniones, no normas vigentes; sin listado sistemático descubierto).
- Nunca se investigó si UPME tiene "Documentos técnicos" propios análogos a los "Documento CREG" 901/905.

### Estado actual en base de datos

| `carpeta_origen` | docs | tipo | tema |
|---|---|---|---|
| UPME_RESOLUCIONES | 20 | html | normativa_upme_mme |
| UPME_CIRCULARES | 3 | html | normativa_upme_mme |

---

## 5. Ministerio de Minas y Energía — normativa (misma plataforma Alejandría)

**Qué es**: misma plataforma Alejandría, tercera entidad — hallazgo colateral al buscar la de UPME. Slugs: `compilacion_resoluciones_ministerio_minas_energia_mme.html` / `compilacion_circulares_ministerio_minas_energia_mme.html` / `compilacion_conceptos_ministerio_minas_energia.html` (este último confirmado existente, `200`, pero no indexado — ver abajo).

**Particularidad de numeración**: las resoluciones del Ministerio usan una numeración de 5 dígitos (ej. "40341 de 2026"), distinta al patrón de 1-3 dígitos de CREG/UPME — el parser es agnóstico a esto (extrae el año vía regex `\bde\s+(\d{4})\b`, no depende del formato del número).

### Qué se indexa

Resoluciones + circulares de los últimos 3 años, mismo mecanismo que UPME (`listar_documentos_entidad(ENTIDAD_MME, tipo)`).

### Qué NO se indexa

- **Conceptos** del Ministerio (`compilacion_conceptos_ministerio_minas_energia.html`, confirmado `200` pero nunca explorado su contenido).
- Ver también sección 8 para 2 fuentes normativas ADICIONALES del propio Ministerio (`normativame.minenergia.gov.co`) investigadas y descartadas.

### Estado actual en base de datos

| `carpeta_origen` | docs | tipo | tema |
|---|---|---|---|
| MME_RESOLUCIONES | 22 | html | normativa_upme_mme |
| MME_CIRCULARES | 17 | html | normativa_upme_mme |

---

## 6. UPME — publicaciones técnicas (sitio propio, WordPress)

**Qué es**: `www.upme.gov.co`, el sitio institucional de la UPME — corre en WordPress y expone la **API REST estándar** `/wp-json/wp/v2/media` (**716 PDFs catalogados en total**, sin autenticación), además de las páginas HTML normales del sitio.

**Cliente**: `infrastructure/upme/upme_wp_client.py` — `listar_publicaciones_pagina(url)`, `descargar_pdf(url)`.

### Por qué NO se usa la API de búsqueda directamente

Se probó buscar por nombre de familia de informe ("Plan de Expansion", "PROURE", "Plan Energetico Nacional") vía `?search=<término>&mime_type=application/pdf` — **0 resultados** para los 3 términos más importantes. Causa: el campo `search` de WordPress matchea contra el TÍTULO/nombre de archivo interno, que no siempre coincide con el nombre oficial del informe (ej. la edición 2025 del Plan Energético Nacional vive en una ruta cuyo nombre de archivo no contiene "Plan Energético Nacional" en ninguna forma reconocible).

### Fuente real usada: páginas curadas del sitio (`PAGINAS_UPME`)

| Página | Qué aporta | Documentos reales (tras exclusión de ruido) |
|---|---|---|
| `https://www.upme.gov.co/` (portada) | Lo que UPME destaca HOY — se autoactualiza sin mantenimiento nuestro | 10 (al momento de esta doc.) |
| `https://www.upme.gov.co/home/estudios-y-publicaciones/` | Catálogo mucho más rico y estable: serie completa de 20 "Resúmenes Ejecutivos" (conflictividad social/territorial en proyectos minero-energéticos), 2 guías metodológicas, boletines históricos, diagnósticos de distritos mineros | 27 |
| **Total único** (deduplicado por nombre de archivo entre ambas páginas) | | **35** |

### Filtro de exclusión (`_PATRONES_EXCLUIDOS`)

`/normatividad/`, `circular_`, `formato_`, `boletin_convocatorias`, `mapa_del_sitio` — trámites/formularios/normativa ya cubierta por la sección 4, sin valor narrativo.

### Documentos reales indexados (ejemplos representativos)

- `Conceptualizacion_de_escenarios_PEN_2025-2055_TomoII_resultados.pdf` — Plan Energético Nacional (98MB, el más grande de todo el corpus)
- `Boletin_Estadistico_2021-2026_S1.pdf` — Boletín Estadístico de Minas y Energía vigente (193 páginas)
- `PNSL_v3.pdf` / `Anexo_PNSLv3.pdf` — hidrocarburos
- `Oportunidades_del_Biogas_y_del_Biometano_PIBE_Pacifico_2025.pdf`
- Serie `1_..._20_...` de Resúmenes Ejecutivos (conflictividad social/territorial — dominio distinto al resto del RAG, agrupado bajo el mismo tema por ahora, ver backlog)
- `Guia_Metodologica_DMEDP_Tomo_I/II.pdf`
- Diagnósticos de distritos mineros (Nordeste Antioqueño, Sur de Córdoba)

### Límite de tamaño

`MAX_PAGINAS_INFORME_UPME = 60` páginas por documento — algunos informes superan las 300 páginas/90MB, se trunca para acotar el costo de procesamiento (mismo criterio que el resto del RAG: capturar la porción introductoria/metodológica sin indexar cientos de páginas de anexos tabulares).

### Qué NO se usa de la API de UPME

- Los ~680 PDFs restantes del catálogo WordPress que no aparecen en ninguna de las 2 páginas curadas — no explorados sistemáticamente; podrían incluir contenido válido, pero también mucho ruido administrativo (boletines de convocatorias, agendas de eventos, formatos de trámite) según lo ya observado en el resto del catálogo.
- Ver también sección 8 — biblioteca Koha de UPME/Ministerio, investigada y descartada.

### Estado actual en base de datos

| `carpeta_origen` | docs | tipo | tema |
|---|---|---|---|
| UPME_PUBLICACIONES | 35 | pdf | publicaciones_upme |

---

## 7. Ministerio de Minas y Energía — publicaciones misionales (sitio propio, Liferay)

**Qué es**: `www.minenergia.gov.co` — el sitio institucional del propio Ministerio, plataforma **Liferay** (confirmado: patrón de URL `/documents/<id>/<archivo>.pdf`, estándar de Liferay Document Library). Nunca se había tocado como fuente hasta esta sesión (2026-08-20/21).

**Cliente**: `infrastructure/minenergia/minenergia_client.py` — `listar_publicaciones_pagina(ruta)`, `descargar_pdf(url)`.

### Por qué se investigó (hallazgo del hueco)

El **Plan de Expansión de Referencia Generación-Transmisión** — uno de los documentos de planeación más importantes del sector (define qué proyectos de generación/transmisión necesita el sistema a futuro) — no estaba en NINGÚN corpus ya indexado (ni XM, ni UPME). Se encontró en `www.minenergia.gov.co/es/misional/energia-electrica-2/planes-expansion/`, con la edición vigente `Plan-Expansion-Transmision-2025-2039.pdf`.

### Páginas del sitio evaluadas

| Página | Veredicto | Motivo |
|---|---|---|
| `/es/misional/energia-electrica-2/planes-expansion/` | ✅ **Usada** | Plan de Expansión vigente + ediciones históricas, contenido técnico real |
| `/es/servicio-al-ciudadano/informes-publicaciones/` | ❌ Descartada | 162 PDFs, casi todos reportes de PQRS/atención al ciudadano (encuestas de satisfacción, interacción ciudadana trimestral) — bajo valor de negocio |
| `/es/repositorio-normativo/` | ⚠️ No explorada | Identificada, no investigada a fondo |
| `biblioteca.minenergia.gov.co` (Koha) | ❌ Descartada | Ver sección 8 |
| `normativame.minenergia.gov.co` (Nexura) | ❌ Descartada | Ver sección 8 |

### Filtro de exclusión (`_PATRONES_EXCLUIDOS`)

`circular`, `resol` (cubre "Resolución", "Resol_Ejecutiva", el typo real "Resoluicon"), `pendiente_documento`, `procedimiento`, `ejecutiva` — la página de Planes de Expansión también lista resoluciones/circulares/procedimientos de declaratoria de utilidad pública de proyectos específicos (caso a caso, menor relevancia general).

### Documentos reales indexados

`Plan-Expansion-Transmision-2025-2039.pdf` (vigente), `Plan_de_Expansion_2022-2036.pdf`, `Plan_maestro_modernizacion_Tomo_2.pdf`, `Plan_GT_2019-2033_SOLOTRANSMISION.pdf`, `Volumen_1/2/3` (edición 2020-2034, Introducción/Generación/Transmisión) + 2 documentos numéricos residuales sin filtrar del todo (aceptado, bajo riesgo — mismo criterio de tolerancia a ruido menor que el resto del proyecto).

### Límite de tamaño

`MAX_PAGINAS_INFORME_MME = 60` páginas — mismo criterio que UPME.

### Estado actual en base de datos

| `carpeta_origen` | docs | tipo | tema |
|---|---|---|---|
| MME_PLANES_EXPANSION | 9 | pdf | publicaciones_mme |

(12 encontrados, 9 procesados con éxito — 3 fallos de extracción, comportamiento esperado del diseño "nunca lanza excepción, degrada con gracia": algunos son escaneos de baja calidad sin texto extraíble.)

---

## 8. Fuentes investigadas y descartadas (con evidencia)

Todas estas se evaluaron a pedido explícito del usuario ("¿vale la pena?") con investigación real (no solo teórica) antes de decidir no implementarlas. Se documentan aquí para que ninguna ronda futura las vuelva a investigar desde cero sin evidencia nueva.

### 8.1 "Documentos CREG" técnicos (series 901/905)

- **Qué son**: análisis de comentarios a proyectos de resolución + estudios técnicos que sustentan decisiones regulatorias — ej. "DOCUMENTO CREG-901 079 de 2025", 312 páginas, "Análisis de Comentarios al Proyecto de Resolución CREG 701 051 de 2024 sobre Comunidades Energéticas".
- **Confirmado real y de calidad**: contenido sustancial, mismo dominio ya confiable (`gestornormativo.creg.gov.co`), curlable sin auth.
- **Por qué no se implementó**: sin página de listado sistemático encontrada (archivados por carpeta de proyecto, sin índice maestro) — esfuerzo de descubrimiento incierto. Audiencia de nicho (economistas/abogados regulatorios) frente a las preguntas operativas que el Asistente responde hoy. Solapamiento parcial con el "Considerando" que ya traen las resoluciones indexadas.
- **Veredicto**: no vale la pena por ahora. Revisar si en el futuro se encuentra un mecanismo de descubrimiento sistemático (ej. crawlear cada resolución/circular ya indexada buscando enlaces cruzados a su documento técnico).

### 8.2 `creg.gov.co` (sitio institucional, plataforma Nexura — NO el gestor normativo)

- **Investigado dos veces con conclusiones distintas**: la primera pasada concluyó erróneamente "requiere JavaScript" — la URL `loader.php?lServicio=Documentos&lFuncion=infoCategoriaConsumo&tipo=RE` sí responde 200 con contenido, pero resultó ser un HTML de 6.5MB con **98% de relleno en blanco** (123KB de contenido real) — página rota o mal formada, no un problema de JS.
- **Veredicto**: no vale la pena — no sirve contenido real de forma simple, y el contenido que SÍ importa (Documentos CREG técnicos) vive en el otro dominio (ver 8.1), no aquí.

### 8.3 Biblioteca Koha (`biblioteca.minenergia.gov.co`)

- **Catálogo real y rico**: sistema de gestión bibliotecaria Koha (open-source), 3.047 resultados reales solo para "energía" — títulos genuinamente valiosos: "Plan Energético Nacional de Colombia: Ideario energético 2050", estudios de factibilidad hidroeléctrica (Río Cusiana, Alto Magdalena), informes EITI Colombia, "Biodiversidad y Servicios Ecosistémicos Sector Minero Energético".
- **Por qué no se implementó**: los enlaces de texto completo apuntan a un dominio legado (`biblioteca.minminas.gov.co`) que está **completamente caído** — HTTP 500 en la raíz del dominio y en los 4 archivos probados individualmente. Sin texto completo, solo quedarían metadatos bibliográficos (título/autor/tema) — insuficiente para RAG.
- **Veredicto**: no vale la pena mientras el servidor de archivos legado siga caído. Revisar si algún día se restaura (bajo costo re-verificar periódicamente, ej. una vez al trimestre).

### 8.4 Sistema normativo del Ministerio (`normativame.minenergia.gov.co`, plataforma Nexura)

- **Confirmado funcional** (a diferencia de 8.2): `loader.php?lServicio=Normatividad&lTipo=User&lFuncion=buscar` devuelve una tabla real de resoluciones/decretos/circulares, con contenido actualizado (fecha tan reciente como 3 días antes de la investigación).
- **Por qué no se implementó**: el listado por defecto está dominado por **trámites administrativos internos** (nombramientos de personal, designación de coordinaciones de grupos internos de trabajo) — no normativa sustantiva del sector. Las páginas de detalle individual (`/normatividad/<id>/norma/`) solo muestran metadatos (Tema/Subtema/Entidad/Vigencia/Tipo/Estado) — **sin enlace a PDF ni texto legal completo**, a diferencia de la plataforma Alejandría que sí embebe el texto íntegro.
- **Veredicto**: no vale la pena — ni el contenido (mayormente ruido administrativo) ni el mecanismo de acceso (sin texto completo confirmado) lo justifican.

### 8.5 Otras carpetas de SharePoint descartadas

Ver sección 2 — "07. Reglamentos", "13. Financiero DEE", "20. Trazabilidad...", "24. FENOGE - Colombia Solar", carpetas de "Soportes contratistas".

---

## 9. Estructura de base de datos común a todas las fuentes

Todas las fuentes de este documento, sin excepción, convergen en el mismo esquema de 2 tablas (`ontologia.*`):

```sql
-- Metadata de cada documento fuente
ontologia.informes_documentos (
    documento_id             SERIAL PRIMARY KEY,
    carpeta_origen           TEXT NOT NULL,   -- etiqueta de fuente (ver tablas de cada sección)
    nombre_archivo           TEXT NOT NULL,
    tipo_archivo             TEXT NOT NULL CHECK (tipo_archivo IN ('pdf','pptx','docx','html')),
    hash_contenido           TEXT NOT NULL,   -- sha256 — detecta cambios sin reprocesar
    sharepoint_item_id       TEXT,            -- reusado como "identificador de origen" (item de SharePoint, o URL relativa/completa según la fuente)
    tamano_bytes             BIGINT,
    modificado_en_sharepoint TIMESTAMPTZ,     -- NULL cuando la fuente no expone fecha individual (ej. Alejandría)
    tema                     TEXT,            -- asignado por scripts/ontologia/clasificar_tema_informes.py
    indexado_en              TIMESTAMPTZ NOT NULL,
    UNIQUE (carpeta_origen, nombre_archivo)
);

-- Fragmentos de texto + embedding, uno o varios por documento
ontologia.informes_texto_embeddings (
    documento_id  INTEGER REFERENCES ontologia.informes_documentos(documento_id) ON DELETE CASCADE,
    chunk_index   INTEGER NOT NULL,
    contenido     TEXT NOT NULL,
    embedding     vector NOT NULL,   -- pgvector, modelo paraphrase-multilingual-MiniLM-L12-v2
    modelo        TEXT NOT NULL
);
```

**Patrón de idempotencia común**: cada indexador calcula `hash_contenido` (sha256) del texto/bytes descargado y lo compara contra `hash_map` (cargado una vez al inicio de `main()`) — si coincide con la última corrida, se salta sin reprocesar. `ON CONFLICT (carpeta_origen, nombre_archivo) DO UPDATE` hace el upsert atómico.

**Extracción de texto** (`infrastructure/ml/document_extraction.py`): `extraer_paginas_pdf()` (con `max_paginas` opcional), `extraer_slides_pptx()`, `extraer_parrafos_docx()`, `chunk_texto_plano()` (para fuentes que llegan como texto ya extraído, ej. HTML de Alejandría — sin páginas/diapositivas naturales que trocear).

**Búsqueda**: `infrastructure/database/repositories/semantic_search_repository.py` — búsqueda híbrida (vector + full-text Postgres) con fusión RRF, re-ranking por cross-encoder, bono de recencia y bono de prioridad de fuente — ver `infrastructure/ml/reranking.py`.

---

## 10. Tabla resumen de temas (`tema`)

| `tema` | Fuente(s) | docs | Contenido |
|---|---|---|---|
| `creg_normativa` | Sección 3 | 744 | Texto legal completo de resoluciones/circulares CREG |
| `planeacion_xm` | Sección 1 | 260 | Estudios de planeación Corto/Mediano/Largo Plazo/Flexibilidad de XM |
| `normativa_upme_mme` | Secciones 4, 5 | 62 | Texto legal completo de resoluciones/circulares UPME + MME |
| `boletin_energetico_xm` | Sección 1 | 71 | Boletín/Panorama Energético semanal de XM |
| `publicaciones_upme` | Sección 6 | 35 | Estudios técnicos/planeación de la UPME |
| `comunidades` | Sección 2 | 20 | Comunidades Energéticas — sostenibilidad, seguimiento, actas, resoluciones |
| `colombia_solar` | Sección 2 | 20 | Programa Colombia Solar — marco regulatorio, presentaciones |
| `subsidios` | Sección 2 | 13 | Conciliaciones Fondo SIN, exentos, diagnóstico focalización |
| `despacho` | Sección 1 | 14 | Informe de Despacho diario de XM (novedades, indisponibilidades) |
| `publicaciones_mme` | Sección 7 | 9 | Plan de Expansión de Referencia Generación-Transmisión (Ministerio) |
| `proyectos_estrategicos` | Sección 2 | 8 | Interconexiones eléctricas internacionales |
| `pmo_interno` | Sección 2 | 5 | Estructura organizacional/administrativa del equipo |
| `metodologia_alertas` | Sección 2 | 2 | Metodología de umbrales/alertas del portal |
| `informe_empalme` | Sección 2 | 1 | Informe de empalme del Ministerio |
| `panorama_climatico` | Sección 2 | 1 | Boletín climático (copia SharePoint) |

**Total**: 1.265 documentos, 25.725 fragmentos (chunks) indexados.

---

## Cómo extender este inventario

Al agregar una fuente nueva:
1. Investigar en vivo (nunca asumir por nombre de carpeta/API) qué contiene realmente — página por página o carpeta por carpeta si el volumen lo permite.
2. Documentar explícitamente qué se descarta y por qué (mismo principio de curación por relevancia de todo este RAG).
3. Nunca lanzar excepción desde el cliente — degradar a `None`/lista vacía, dejar rastro en logs (`logger.warning`).
4. Agregar la fila correspondiente a este documento (sección nueva o extensión de una existente) y a la tabla de la sección 10.
