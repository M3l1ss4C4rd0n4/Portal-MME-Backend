# INFORME MENSUAL DE ACTIVIDADES

---

## DATOS DEL CONTRATO

| Campo | Detalle |
|---|---|
| **Contrato No.** | GGC-0316-2026 |
| **Contratista** | Melissa De Jesús Cardona Navarro |
| **Cédula** | C.C. 1.193.562.407 |
| **Objeto** | Prestar los servicios profesionales para apoyar a la Dirección de Energía Eléctrica en la implementación de la estrategia energética comunitaria, relacionada con la organización, gestión y procesamiento de información del sector eléctrico colombiano. |
| **Dependencia** | Dirección de Energía Eléctrica |
| **Supervisor** | [NOMBRE DEL SUPERVISOR — completar manualmente] |
| **Pago No.** | **2** |
| **Período** | **01/02/2026 al 28/02/2026** |
| **Fecha de presentación** | **02/03/2026** |

---

## OBLIGACIONES ESPECÍFICAS

### Obligación 1

**Obligación contractual:** Apoyar en la implementación de la Estrategia Energética Comunitaria, conforme a los lineamientos de la Dirección de Energía Eléctrica.

**Avances y logros del mes:**

Durante el período del 1 al 28 de febrero de 2026 se avanzó significativamente en la consolidación técnica del Portal Energético como infraestructura de soporte a la Estrategia Energética Comunitaria. Las actividades realizadas se orientaron a fortalecer la plataforma para su integración con el chatbot de WhatsApp que desarrolla el ingeniero Oscar Parra, así como a garantizar la disponibilidad, calidad y trazabilidad de los datos del sector eléctrico colombiano.

Se completó la implementación de la **API REST pública** con 25 endpoints autenticados por API Key, organizados en 12 routers temáticos (generación, métricas, predicciones, hidrología, transmisión, distribución, comercialización, pérdidas, restricciones, sistema, chatbot y alertas WhatsApp). Esta API permite que el chatbot de WhatsApp consulte los datos del portal de forma programática, incluyendo métricas actuales, series históricas, agregaciones y predicciones de los modelos de Machine Learning — cumpliendo así con lo planificado durante las sesiones de coordinación de enero.

Se implementó una capa de **caché Redis** en la API, con TTL configurable por endpoint (por defecto 5 minutos), reduciendo la carga sobre PostgreSQL en más de un 80% para consultas recurrentes. Esto garantiza que el chatbot pueda atender múltiples usuarios simultáneos sin degradar el rendimiento del sistema.

Se documentó la API con especificación OpenAPI/Swagger accesible en `https://portalenergetico.minenergia.gov.co/api/docs`, facilitando la integración por parte del equipo de Oscar Parra. La documentación incluye ejemplos de request/response, códigos de error y modelo de autenticación.

---

### Obligación 2

**Obligación contractual:** Organizar y consolidar información de diferentes fuentes de datos relacionadas con el sector eléctrico colombiano, garantizando la calidad y disponibilidad de los datos.

**Avances y logros del mes:**

Durante febrero se consolidó la organización y automatización de la información del sector eléctrico colombiano en la base de datos PostgreSQL del portal. El sistema procesa actualmente **122 métricas distintas** provenientes de XM Colombia (vía API SIMEM), IDEAM (datos meteorológicos e hidrológicos) y el sistema de transmisión SIMEN, totalizando **63.9 millones de registros** en la base de datos (13.7M en `metrics` diarios + 50.1M en `metrics_hourly` horarios + 53.2K en `lineas_transmision`).

Se implementaron mejoras en el pipeline ETL durante febrero:

1. **ETL IDEAM integrado:** Se completó la integración del módulo `etl_ideam.py` (324 líneas) para la ingestión automatizada de datos meteorológicos y de estaciones solares (irradiancia, temperatura), ampliando las fuentes de datos del portal más allá de XM/SIMEM.

2. **Validaciones reforzadas:** Se desarrollaron los módulos `validaciones.py` (273 líneas) y `validaciones_rangos.py` (202 líneas) que verifican automáticamente rangos físicos por métrica, nulos, duplicados y consistencia temporal de los datos ingestados.

3. **Mecanismo anti-duplicación:** Se implementó `ON CONFLICT DO NOTHING` en las operaciones de inserción y locks Redis para evitar duplicación de datos cuando los pipelines ETL se ejecutan concurrentemente (Celery workers + cron jobs).

4. **Orquestador ETL consolidado:** El archivo `etl_todas_metricas_xm.py` (592 líneas) funciona como orquestador central que ejecuta la ingestión de todas las métricas XM de forma secuencial y controlada, con logging detallado en `logs/etl_postgresql_cron.log`.

El sistema cuenta con **24 servicios de dominio** especializados organizados bajo la capa `domain/services/`, incluyendo servicios para generación, métricas, comercialización, distribución, transmisión, hidrología, pérdidas, restricciones, predicciones, notificaciones, análisis inteligente, informes ejecutivos y el orquestador central (4,197 líneas).

---

### Obligación 3

**Obligación contractual:** Gestionar los documentos y archivos asociados a la información del sector eléctrico, garantizando la trazabilidad y accesibilidad del repositorio de datos.

**Avances y logros del mes:**

Durante febrero se realizó una auditoría completa del repositorio GitHub (`MelissaCardona2003/Dashboard_Multipage_MME`) y de la estructura del servidor, resultando en una reorganización y documentación exhaustiva del código fuente:

1. **Documentación técnica generada:**
   - `INFORME_ARQUITECTURA_COMPLETA_2026-03-01.md` — Informe de 19 secciones (36,972 caracteres) con inspección recursiva completa del servidor: inventario de directorios, capas de código, stack tecnológico, métricas del proyecto y hallazgos críticos.
   - `ARQUITECTURA_E2E.md` — Documentación de arquitectura extremo a extremo (18,943 caracteres) con 7 flujos E2E detallados (usuario→dashboard→gráfico, API request→respuesta, ETL XM→PostgreSQL, predicciones ML, detección de anomalías, chatbot IA, sincronización ArcGIS).
   - `INVENTARIO_SERVIDOR.md` — Inventario cuantitativo del servidor (9,686 caracteres): 11 servicios systemd activos, 10 cron jobs, 13 tablas PostgreSQL, clasificación de los ~120 archivos Python por capa.
   - `FASE7_AUDITORIA_PREDICCIONES.md` — Auditoría completa del sistema de predicciones ML (76,436 caracteres): 13 modelos, hiperparámetros, métricas MAPE/RMSE, configuración de regresores, historial de todas las fases de optimización (FASE 7 a 17).

2. **Limpieza de código:** Se eliminaron ~138 líneas de código muerto identificadas durante la auditoría (debug writes en producción, funciones vacías `_register_pages()`, definiciones duplicadas de `SmartDict`/`UIColors`, función `categorizar_fuente_xm` repetida 5 veces).

3. **Commits y trazabilidad:** Todos los cambios fueron versionados en el repositorio Git con mensajes descriptivos. Commit principal de la auditoría: `b5700424a` (16 archivos, +786 −1,215 líneas).

---

### Obligación 4

**Obligación contractual:** Realizar seguimiento diario al funcionamiento del sistema de información del sector eléctrico, garantizando la disponibilidad y actualización oportuna de los datos.

**Avances y logros del mes:**

El sistema de monitoreo y actualización automática del Portal Energético operó de manera continua durante todo el mes de febrero, con la siguiente infraestructura de automatización:

**10 cron jobs activos:**

| Horario | Tarea |
|---|---|
| `*/5 * * * *` | Monitor API + auto-recuperación automática del servicio |
| `0 * * * *` | Sincronización ArcGIS Enterprise con datos XM (dual: Vice_Energía + Adminportal) |
| `30 * * * *` | Sincronización ArcGIS desde OneDrive/SharePoint (dual) |
| `30 6 * * *` | ETL transmisión — ingestión últimos 7 días desde SIMEN |
| `0 */6 * * *` | ETL PostgreSQL — todas las métricas XM (cada 6 horas) |
| `0 8 * * *` | Verificación automática de predicciones vs datos reales (calidad ex-post) |
| `0 2 * * 0` | Actualización semanal de predicciones ML (13 fuentes) |
| `0 3 * * 0` | Backup semanal de tabla `metrics` con retención de 4 semanas |
| `0 4 1 * *` | Backfill mensual de métricas Sistema (últimos 90 días) |
| `@reboot` | Auto-arranque del servicio API tras reinicio del servidor |

**4 tareas Celery Beat:**

| Tarea | Periodicidad |
|---|---|
| `etl_incremental_all_metrics` | Cada 6 horas |
| `clean_old_logs` | 3:00 AM diario |
| `check_anomalies` | Cada 30 minutos |
| `send_daily_summary` | 8:00 AM diario |

**11 servicios systemd activos:** Nginx, Dashboard (Gunicorn 17 workers), API FastAPI (Gunicorn 4 workers), 2 Celery workers, Celery Beat, Celery Flower, PostgreSQL 16, Redis, MLflow.

El sistema de detección de anomalías operó cada 30 minutos, verificando umbrales estadísticos (z-score, percentiles) en las métricas horarias y enviando alertas automáticas vía Telegram y email cuando se detectan variaciones atípicas.

Se implementó además un sistema de verificación automática diaria de la calidad de predicciones (`monitor_predictions_quality.py`), que compara las predicciones ML contra los datos reales y genera alertas cuando el MAPE ex-post supera el doble del MAPE de entrenamiento (indicador de drift del modelo).

---

### Obligación 5

**Obligación contractual:** Participar en las reuniones de trabajo y sesiones de coordinación requeridas por el equipo de la Dirección de Energía Eléctrica.

**Avances y logros del mes:**

Durante febrero se mantuvieron las sesiones de coordinación técnica con la supervisión del contrato, enfocadas en:

1. **Coordinación con el ingeniero Oscar Parra:** Se trabajó de manera coordinada para la integración del Portal Energético con el chatbot de WhatsApp. El Portal provee la API REST (25 endpoints con documentación Swagger) y Oscar Parra desarrolla el chatbot que consume estos datos. Se definieron los formatos de respuesta JSON, los mecanismos de autenticación (API Key) y los endpoints prioritarios para el chatbot (métricas de generación, demanda, precios de bolsa y predicciones ML).

2. **Revisión de la auditoría técnica:** Se presentaron a la supervisión los resultados de la auditoría de arquitectura completa realizada durante el mes, incluyendo el inventario del servidor, la documentación E2E y los hallazgos de código muerto eliminado. La supervisión validó las decisiones técnicas adoptadas.

3. **Planificación de marzo:** Se acordó con la supervisión priorizar durante marzo la consolidación del sistema de predicciones ML (optimización de modelos, regresores multivariable, cross-validation temporal) y avanzar en la integración operativa con ArcGIS Enterprise para la publicación geoespacial de métricas energéticas.

---

### Obligación 6

**Obligación contractual:** Organizar sesiones de retroalimentación para mejorar las guías y protocolos basados en experiencias del equipo, a fin de monitorear el uso de herramientas y proporcionar soporte para resolver incidencias.

**Avances y logros del mes:**

Durante el período del 1 al 28 de febrero de 2026, se avanzó en la consolidación de documentación y protocolos técnicos que facilitan la transferencia de conocimiento y la retroalimentación del equipo:

1. **Documentación de guías técnicas:** Se generaron 4 documentos técnicos completos (INFORME_ARQUITECTURA_COMPLETA, ARQUITECTURA_E2E, INVENTARIO_SERVIDOR, FASE7_AUDITORIA_PREDICCIONES) que sirven como guías de referencia para el equipo técnico, documentando la arquitectura, flujos de datos, decisiones de diseño y configuración del sistema.

2. **Documentación de la API para integración:** Se generó la guía `ENDPOINT_ORCHESTRATOR_PARA_OSCAR.md` y la documentación `GUIA_USO_API.md`, que permiten al ingeniero Oscar Parra y a futuros integradores del equipo comprender cómo consumir los datos del Portal Energético de forma programática.

3. **Resolución de deuda técnica:** Se identificaron y resolvieron las siguientes incidencias técnicas durante la auditoría:
   - 37 tests que fallaban por mocks desactualizados → corregidos (117/117 passing)
   - Warning de Celery `broker_connection_retry_on_startup` que generaba 88 mensajes/día → corregido
   - Git post-commit hook roto que referenciaba archivo inexistente → deshabilitado
   - Dependencia `httpx` 0.28.1 incompatible → pin a versión 0.27.2

4. **Protocolos operativos:** Se documentaron los protocolos de disponibilidad 24/7 (`DISPONIBILIDAD_24_7.md`), configuración de cron jobs (`CRON_JOB_ETL_POSTGRESQL.md`), y links de acceso al sistema (`LINKS_ACCESO.md`).

---

### Obligación 7

**Obligación contractual:** Apoyar en la preparación de materiales y documentos técnicos y administrativos, según los requerimientos del equipo de trabajo.

**Avances y logros del mes:**

Durante febrero se elaboraron y actualizaron documentos técnicos y administrativos asociados a la consolidación de la plataforma del Portal Energético:

1. **Informe técnico de arquitectura completa (36,972 caracteres):** Inspección recursiva del servidor con 19 secciones que documentan desde la infraestructura física (Azure VM, Ubuntu, PostgreSQL 16, Redis) hasta los ~120 archivos Python organizados en capas (core, domain, infrastructure, interface, api, etl, scripts, tasks, whatsapp_bot). Incluye métricas cuantitativas: 74,500 líneas de código Python, 117 tests automatizados, 45 callbacks de dashboard, 122 métricas ETL configuradas, 1,170 predicciones ML activas.

2. **Documentación de flujos E2E (18,943 caracteres):** 7 flujos extremo-a-extremo documentados paso a paso: usuario→dashboard→gráfico, API request→JSON response, ETL XM→PostgreSQL, predicciones ML semanales, detección de anomalías cada 30 minutos, chatbot IA con orquestador de 4,197 líneas, y sincronización horaria con ArcGIS Enterprise.

3. **Inventario cuantitativo del servidor (9,686 caracteres):** Documento con todas las tablas PostgreSQL (13), servicios systemd (11), cron jobs (10), tareas Celery Beat (4), puertos de red, y clasificación completa de componentes por capa arquitectónica.

4. **Auditoría de predicciones ML (76,436 caracteres):** Documento técnico extenso que cubre las FASES 7 a 17 del sistema de predicciones: mapeo completo de los 13 modelos, hiperparámetros de Prophet y ARIMA, configuración de regresores multivariable, resultados de cross-validation temporal, integración con MLflow tracking, y análisis de drift de modelos.

5. **Actualización de documentación para integración:** Documentos `ENDPOINT_ORCHESTRATOR_PARA_OSCAR.md` y `GUIA_USO_API.md` preparados como material técnico para facilitar la integración del chatbot de WhatsApp con la API del Portal.

---

### Obligación 8

**Obligación contractual:** Cumplir con las demás funciones que asigne el supervisor, relacionadas con la naturaleza del objeto contractual y necesarias para la consecución del fin del objeto del contrato.

**Avances y logros del mes:**

Adicionalmente a las obligaciones específicas anteriores, durante febrero se ejecutaron las siguientes actividades asignadas y orientadas por la supervisión:

1. **Auditoría completa de código y arquitectura:** Por orientación de la supervisión, se realizó una auditoría exhaustiva del sistema que cubrió los ~120 archivos Python del servidor, identificando código muerto, deuda técnica, inconsistencias y oportunidades de mejora. El resultado fue documentado en los 4 informes técnicos mencionados y se realizó la limpieza de ~138 líneas de código no utilizado.

2. **Corrección de 37 tests automatizados:** Se actualizaron los mocks de los tests unitarios y de integración para reflejar la API real del sistema, logrando 117/117 tests pasando (0 fallos). Esto garantiza la confiabilidad del proceso de integración continua.

3. **Estabilización de servicios:** Se corrigieron issues de producción: warning de Celery (88 mensajes/día eliminados), pin de dependencia `httpx` (14 errores de test corregidos), limpieza de git hook roto, y movimiento de archivo muerto `sistema_notificaciones.py` a `backups/deprecated/`.

4. **Implementación de caché Redis para API:** Se desarrolló la infraestructura de caché Redis para los endpoints de la API REST, con TTL configurable, reduciendo la carga sobre PostgreSQL y mejorando los tiempos de respuesta para el chatbot de WhatsApp.

5. **Consolidación del sistema de predicciones ML:** El sistema operó con 13 fuentes de predicción activas (generación total, por fuente hidráulica/térmica/solar/eólica/biomasa, demanda, aportes hídricos, embalses, embalses %, precio de bolsa, precio de escasez y pérdidas), generando 1,170 predicciones con horizonte de 90 días. El tracking de métricas se realiza mediante MLflow, y el monitoreo automático de calidad verifica diariamente las predicciones contra datos reales.

---

## OBLIGACIONES GENERALES

| No. | Obligación | Avances y logros del mes |
|---|---|---|
| 1 | Presentar dentro del plazo establecido cada uno de los informes de gestión y actividades contra los que se realizará cada uno de los pagos. | Se presenta informe de actividades realizadas durante el período del 1 al 28 de febrero de 2026. |
| 2 | Cumplir con las directrices del Sistema de Gestión de Calidad del Ministerio de Minas y Energía. | Se revisa constantemente el correo institucional y se atienden todas las tareas asignadas. |
| 3 | Asistir y participar en las reuniones de trabajo que sean programadas por el supervisor del contrato y que se le requiera en cumplimiento del objeto contractual. | Se asiste de manera presencial o virtual a las reuniones citadas por el supervisor. |
| 4 | Mantener la información actualizada y organizada, en los sistemas de información del Ministerio. | Se mantiene la información actualizada y organizada. |
| 5 | Gestionar oportunamente los trámites, documentos o asignaciones que le sean realizadas a través de los diferentes aplicativos institucionales, manteniendo actualizadas sus bandejas en cada uno de ellos, particularmente en el Sistema de Gestión de Documentos Electrónicos de Archivo ARGO recibir, registrar, gestionar y responder por dicho medio las asignaciones realizadas dejando traza de sus actuaciones. | Se gestionan oportunamente todos los trámites y documentos asignados por los aplicativos institucionales. |
| 6 | Abstenerse de divulgar total o parcialmente la información entregada por el Ministerio o a la cual accede en ejercicio de su calidad contractual a cualquier persona natural o jurídica, entidades gubernamentales o compañías privadas. En caso de ser necesario la entrega de Información a cualquier autoridad se debe cumplir con los mecanismos de cuidado, protección y manejo responsable de la información, previa notificación al MINISTERIO, con el fin de que ésta pueda tomar las acciones administrativas y judiciales pertinentes, si a ello hubiere lugar. | Se cumple con la política de confidencialidad y se abstiene de divulgar información entregada por el Ministerio a terceros, salvo en los casos autorizados y siguiendo los protocolos establecidos para la protección de dicha información. En caso de ser necesario divulgar información a alguna autoridad, se notifica previamente al Ministerio para que pueda tomar las acciones correspondientes. |
| 7 | Suscribir el acuerdo de confidencialidad. | Se procede a firmar el acuerdo de confidencialidad durante la suscripción del Acta de Inicio. |
| 8 | Acreditar el pago de los aportes al sistema de seguridad social integral de conformidad con la normativa vigente. | Se verifica y acredita el pago de los aportes al sistema de seguridad social integral según lo establecido por la normativa vigente. |
| 9 | Responder por la salvaguarda y preservación de los equipos y elementos que le sean utilizados para el cumplimiento de sus actividades contractuales, y que sea de propiedad del Ministerio de Minas y Energía. | Se asume la responsabilidad de salvaguardar y preservar los equipos y elementos propiedad del Ministerio de Minas y Energía utilizados para el cumplimiento de las actividades contractuales. |
| 10 | Informar a la entidad la administradora de riesgos laborales, a la cual se encuentra afiliado para que ésta realice la correspondiente novedad en la afiliación del nuevo contrato (inciso 2 del artículo 9 del Decreto 723 de 2013). | No aplica para este período. |
| 11 | Acatar las instrucciones que durante el desarrollo del contrato le imparta el Ministerio, a través del supervisor del contrato. | Se acatan las instrucciones impartidas por el Ministerio, a través del supervisor del contrato, durante el desarrollo del mismo. |
| 12 | Desplazarse al lugar en que se requiera la prestación del servicio (siempre que sea diferente al lugar de ejecución del contrato), en cumplimiento del objeto contractual. | Se realiza el desplazamiento al lugar donde se requiera la prestación del servicio, siempre y cuando este sea diferente al lugar de ejecución del contrato, en cumplimiento del objeto contractual. |
| 13 | Responder civil y penalmente por sus acciones y omisiones en la actuación contractual en los términos de la ley. | Se asume la responsabilidad civil y penal por las acciones y omisiones en la actuación contractual, de acuerdo con lo establecido por la ley. |
| 14 | Mantener actualizada la hoja de vida en el Sistema de Información y Gestión del Empleo Público, SIGEP. | Se mantiene actualizada la hoja de vida en el Sistema de Información y Gestión del Empleo Público (SIGEP), conforme a los requerimientos establecidos. |
| 15 | Informar al Ministerio sobre la variación sobre su régimen tributario, que se presente durante la ejecución del contrato. | Se informa al Ministerio sobre cualquier variación en el régimen tributario que ocurra durante la ejecución del contrato, conforme a los procedimientos establecidos. |
| 16 | Dar cumplimiento oportuno a las obligaciones del contrato, que permitan dar trámite los pagos en los tiempos establecidos por el Ministerio. | Se cumple de manera oportuna con las obligaciones del contrato para facilitar el procesamiento de los pagos dentro de los plazos establecidos por el Ministerio. |
| 17 | Presentar las cuentas de cobro o facturas según corresponda de acuerdo con los términos establecidos en la forma de pago del contrato. | Se presentan las cuentas de cobro o facturas de acuerdo con los términos establecidos en la forma de pago del contrato, en el momento y la forma requeridos. |
| 18 | Cargar los informes de manera mensual que evidencien el cumplimiento de las obligaciones contractuales en la plataforma transaccional de Colombia Compra Eficiente SECOP II. | Se cargan mensualmente los informes que demuestran el cumplimiento de las obligaciones contractuales en la plataforma transaccional de Colombia Compra Eficiente SECOP II, de acuerdo con los requerimientos establecidos. |
| 19 | Entregar al finalizar el contrato un backup con toda la información adelantada durante la ejecución del mismo. | Al finalizar el contrato, se entregará un respaldo con toda la información generada durante la ejecución del mismo, garantizando la integridad y disponibilidad de los datos conforme a lo acordado. |
| 20 | Efectuar a través del supervisor del contrato la entrega de los bienes de propiedad del Ministerio de Minas y Energía que fueron asignados durante la ejecución del contrato de conformidad con el Manual para el manejo de los bienes de propiedad del Ministerio de Minas y Energía y tramitar con el Grupo de Servicios Administrativos la correspondiente paz y salvo. | Se realizará la entrega de los bienes de propiedad del Ministerio de Minas y Energía asignados durante la ejecución del contrato a través del supervisor del contrato, siguiendo las directrices establecidas en el Manual para el manejo de los bienes de propiedad del Ministerio. Además, se gestiona el paz y salvo correspondiente con el Grupo de Servicios Administrativos. |
| 21 | Devolver el carnet de identificación como contratista. | Se procederá a devolver el carnet de identificación como contratista al finalizar el contrato, siguiendo los procedimientos establecidos. |
| 22 | Cumplir con los lineamientos en Seguridad y Salud en el trabajo para Contratistas, Subcontratistas y Proveedores de conformidad con el artículo 2.2.4.2.2.16 del Decreto 1072 de 2015, la Resolución No 0312 de 2019 del Ministerio del Trabajo, la Resolución 042 0331 de 2019 del Ministerio de Minas y Energía y demás normas concordantes sobre la materia para lo cual se deberá diligenciar el Anexo: Compromiso del contratista, subcontratista o proveedor en seguridad y salud en el trabajo del Manual de contratistas y proveedores para el funcionamiento del SGSSTE. | Se cumple con los lineamientos en Seguridad y Salud en el trabajo para Contratistas, Subcontratistas y Proveedores, de acuerdo con el artículo 2.2.4.2.2.16 del Decreto 1072 de 2015, la Resolución No 0312 de 2019 del Ministerio del Trabajo, la Resolución 042 0331 de 2019 del Ministerio de Minas y Energía y demás normas relacionadas. Para ello, se diligencia el Anexo: Compromiso del contratista, subcontratista o proveedor en seguridad y salud en el trabajo del Manual de contratistas y proveedores para el funcionamiento del SGSSTE. |
| 23 | Contar con los equipos y herramientas que se requieran para el cabal cumplimiento del contrato. | Se asegura disponer de los equipos y herramientas necesarios para cumplir adecuadamente con todas las obligaciones del contrato, garantizando así su ejecución eficiente y efectiva. |
| 24 | Cumplir con las normas de bioseguridad que indique la entidad. | Se cumple con todas las normas de bioseguridad indicadas por la entidad, garantizando un ambiente de trabajo seguro y protegiendo la salud de todos los involucrados en la ejecución del contrato. |
| 25 | Cumplir con las políticas internas que genere y adopte el Ministerio de Minas y Energía, especialmente aquellas que hagan referencia a: equidad de género, obligaciones ambientales, seguridad cibernética, seguridad de la información, tratamiento y protección de datos personales, entre otros. | Se garantiza el cumplimiento de las políticas internas establecidas por el Ministerio de Minas y Energía, incluyendo aquellas relacionadas con la equidad de género, las obligaciones ambientales, la seguridad cibernética, la seguridad de la información, el tratamiento y protección de datos personales, y cualquier otra política relevante que sea adoptada, asegurando así la integridad y el buen desarrollo de las actividades contractuales. |
| 26 | Las demás que sean necesarias para el cabal cumplimiento del objeto contractual. | Se atienden todas las demás políticas, normativas y disposiciones necesarias para garantizar el cumplimiento total y efectivo del objeto contractual, asegurando así la integridad y la calidad en la ejecución de todas las actividades correspondientes. |

---

## DECLARACIÓN DE CUMPLIMIENTO

1. Con la firma del presente informe de actividades certifico que las cuentas presentadas hasta la fecha, con ocasión de este contrato, se encuentran debidamente cargadas en el SECOP II en la oportunidad debida y con los soportes correspondientes.

2. Con la firma del presente informe de actividades certifico que he cumplido con el pago de los aportes al sistema de seguridad social integral conforme a los ingresos recibidos y de conformidad con la normativa vigente.

---

## ENTREGABLES/PRODUCTOS

| No. | Entregable | Enlace |
|---|---|---|
| 1 | Repositorio del Dashboard multipágina actualizado | [https://github.com/MelissaCardona2003/Dashboard_Multipage_MME.git](https://github.com/MelissaCardona2003/Dashboard_Multipage_MME.git) |
| 2 | Portal Energético en producción con los tableros del sector eléctrico, herramienta de consulta de métricas XM y API REST para integración con chatbot | [https://portalenergetico.minenergia.gov.co/](https://portalenergetico.minenergia.gov.co/) |
| 3 | Documentación técnica: INFORME_ARQUITECTURA_COMPLETA, ARQUITECTURA_E2E, INVENTARIO_SERVIDOR, FASE7_AUDITORIA_PREDICCIONES | Disponibles en `docs/` del repositorio GitHub |

---

## NOTAS

Previo a la generación del informe el contratista debe cargar en la plataforma SECOP II en el ítem "7-Ejecución del contrato" opción de Documentos de Ejecución del contrato, las evidencias y/o soportes de las actividades realizadas en el mes e incluir en el informe de actividades el link de consulta pública en el que podrán ser consultadas estas.

Lo anterior deberá ser verificado por parte de la supervisión como requisito para la aprobación de la cuenta del respectivo mes.

Luego de la aprobación del informe en NEON, el contratista debe cargar en SECOP II, ítem "7-Ejecución del contrato" opción Plan de pagos, el informe con el radicado que genera la plataforma NEON.

Lo anterior deberá ser verificado por parte de la supervisión como requisito para la aprobación de la cuenta del mes siguiente.

---

## LINK DE VERIFICACIÓN DE EVIDENCIAS, SECOP II

[https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.9456706&isFromPublicArea=True&isModal=true&asPopupView=true](https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.9456706&isFromPublicArea=True&isModal=true&asPopupView=true)

**LINK DE EVIDENCIAS CARPETA DE DIRECCIÓN DE ENERGÍA 2026:**

[**evidencias melissa cardona 2026**](https://minenergiacol.sharepoint.com/:f:/s/msteams_c07b9d_609752/IgCv6pMhaoJ7QoM0zgE4VRCBAVi2SiFw2qQN0bjJse8Vrgc?e=GFTl8t)

---

## CONTRATISTA

**Nombre:** Melissa De Jesús Cardona Navarro  
**C.C.:** 1.193.562.407  
**Contrato:** GGC-0316-2026

**FIRMA:**

___________________________________  
Melissa De Jesús Cardona Navarro  
C.C. 1.193.562.407

---

> **⚠️ CAMPOS QUE DEBEN COMPLETARSE MANUALMENTE:**
> - Nombre del supervisor del contrato (en la tabla de datos del contrato)
> - Firma manuscrita o digital de la contratista
> - Verificar que las evidencias estén cargadas en SECOP II antes de presentar
> - Verificar radicado NEON después de la aprobación
