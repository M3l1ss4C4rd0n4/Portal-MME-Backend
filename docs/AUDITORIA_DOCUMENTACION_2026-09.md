# Auditoría de Documentación — Portal Dirección MME (Backend)

**Fecha:** 2026-09-01
**Metodología:** cada documento fue leído completo y contrastado contra el código real (grep de funciones/rutas/tablas citadas, verificación de `systemctl`, corrida real de `pytest`, lectura de `tasks/__init__.py::beat_schedule`, y comparación de conteos de líneas/endpoints contra el estado actual del repo) — no se asumió que un documento fuera correcto por su fecha o su apariencia.

**Alcance**: ~25 documentos `.md` reales del proyecto (se excluyeron `venv/`/`node_modules/`/`.pytest_cache/`/licencias de terceros, y `docs/trabajo de grado/` — bitácora de tesis de un tercero, no documentación del portal).

---

## Tabla consolidada

| # | Documento | Estado | Hallazgo principal | Recomendación |
|---|---|---|---|---|
| 1 | `README.md` (raíz) | Corregido 2026-09-01 | Cifras desactualizadas (350→459 archivos, 30→42 servicios, 52→110 endpoints), 2 enlaces rotos, sin mención de Ontología/Asistente IA/Voz/CU | ✅ Ya reescrito |
| 2 | `docs/METODOLOGIA_CU.md` | VIGENTE | Actualizado 2026-08-31 (§9.14, ponderación por demanda real) | Mantener |
| 3 | `docs/tecnicos/ANALISIS_HIDROLOGIA_SEMAFORO.md` | VIGENTE | Actualizado 2026-08-31 (§10, distinción NE vs. IDEAM/UNGRD) | Mantener |
| 4 | `docs/tecnicos/PREDICCIONES_EMBALSES_VALIDACION_RIGUROSA.md` | VIGENTE | Creado 2026-08-31 | Mantener |
| 5 | `docs/FUENTES_RAG.md` | **VIGENTE** | El mejor mantenido de todo el set — cada constante citada (`DIAS_INFORMES_XM`, `ANIOS_RETENCION_*`, etc.) verificada exacta contra el código | Mantener sin cambios |
| 6 | `docs/GUIA_TROUBLESHOOTING.md` | VIGENTE (menor) | Todo correcto salvo 1 enlace roto a `INVENTARIO_SERVIDOR.md` (no existe) | Quitar ese enlace |
| 7 | `docs/INFORME_EJECUTIVO_CONTENIDO.md` | VIGENTE | Cada función citada (`_build_page_mercado`, etc.) verificada en la línea exacta | Mantener |
| 8 | `docs/INFORME_PORTAL_CAPITULOS_PENDIENTES.md` | VIGENTE | Los 7 capítulos suspendidos siguen existiendo tal cual se describen | Mantener |
| 9 | `docs/tecnicos/NOTA_FILA_TOTALES_EXCEL.md` | VIGENTE | El fix citado sigue en el código exacto (`etl/etl_subsidios.py:135`) | Mantener |
| 10 | `docs/CACHE_USAGE_GUIDE.md` | DESACTUALIZADO | Los endpoints `/api/cache/stats`, `/api/cache/clear` que documenta **no existen** — el real es `/v1/predictions/cache/stats` | Reescribir sección "Endpoints de Administración" |
| 11 | `docs/COMPONENTS_GUIDE.md` | DESACTUALIZADO | Árbol de directorios desactualizado (`inputs/`/`layout/` no tienen el contenido descrito); CSS reales son `mme-corporate.css`/`professional-style.css`, no los `0X-*.css` citados | Actualizar árbol y sección de troubleshooting CSS |
| 12 | `docs/CRON_JOB_ETL_POSTGRESQL.md` | DESACTUALIZADO (severo) | ~30 cron jobs reales vs. 7-9 documentados; horarios de varios jobs documentados también cambiaron (`@reboot`, reentrenamiento) | Regenerar tabla completa desde `crontab -l` |
| 13 | `docs/DISPONIBILIDAD_24_7.md` | DESACTUALIZADO | Mismo desfase de cron que #12; sección de systemd sigue correcta | Actualizar tabla de cron (o enlazar a #12 una vez corregido) |
| 14 | `docs/ENDPOINT_ORCHESTRATOR_PARA_OSCAR.md` | DESACTUALIZADO | Dice 13 intents soportados; el orquestador real mapea **101** strings a 54 handlers | Aclarar que 13 es el contrato estable para Oscar, no el total real |
| 15 | `docs/GUIA_ONBOARDING.md` | DESACTUALIZADO | Enlaza a 3 archivos inexistentes (`ARQUITECTURA_E2E.md`, `DOCUMENTACION_TECNICA_ORQUESTADOR.md`, `MAPEO_COMPLETO_METRICAS.md`) + 1 más (`INVENTARIO_SERVIDOR.md`) | Corregir/quitar los 4 enlaces rotos |
| 16 | `docs/GUIA_USO_API.md` | DESACTUALIZADO (severo) | Documenta 25 endpoints; hay **110** reales, faltan por completo Ontología/Asistente IA/Voz/CU | Regenerar desde `api/v1/routes/*.py` |
| 17 | `docs/LINKS_ACCESO.md` | DESACTUALIZADO | Fechado jul-2026, no menciona el schema `ontologia` (creado después); inventario de tablas/tamaño de BD desactualizado | Regenerar inventario de esquemas/tablas |
| 18 | `docs/refactoring/ARCHIVOS_GRANDES_PLAN.md` | DESACTUALIZADO | `report_service.py` pasó de 1.850 a **3.584** líneas (casi el doble) — el refactor propuesto nunca se ejecutó | Actualizar conteos; el plan sigue vigente, ahora más urgente |
| 19 | `docs/tecnicos/DOCUMENTACION_TECNICA_IA_ML.md` | **OBSOLETO** | Describe una arquitectura SQLite/`/utils/ai_agent.py` que no existe desde hace meses — completamente superada | **Candidato a borrar** |
| 20 | `docs/tecnicos/README_SEMAFORO.md` | **OBSOLETO** | La matriz Participación×Volumen que describe ya fue retirada y desautorizada explícitamente por `ANALISIS_HIDROLOGIA_SEMAFORO.md` §10 | **Candidato a borrar** |
| 21 | `AGENTS.md` (raíz) | DESACTUALIZADO (crítico) | Afirma que la BD usa `asyncpg`/`get_pool()` — **no existe**, la conexión real es `psycopg2.ThreadedConnectionPool`. Enlaza a un `SKILL_PACK_V4.1.md` del frontend que ya no existe ahí (ahora V5.0) | **Corregir la línea de BD de inmediato** — puede llevar a un agente a buscar código que no existe |
| 22 | `RUNBOOK_PRODUCCION.md` | DESACTUALIZADO (crítico) | Rutas de logs de la API (`logs/api-error.log`) **no existen** — la ruta real es `/var/log/portal-api.log`. Tabla de Celery Beat solo lista 5 de ~14 tareas reales (falta el backtest riguroso de predicciones y el sanador de vistas de ontología). Ejemplo JSON de `/health` usa clave equivocada (`checks` vs. `services` real) | **Corregir rutas de log de inmediato** — un operador en un incidente real buscaría en el lugar equivocado |
| 23 | `SKILL_PACK_V4.1.md` (raíz) | VIGENTE (metodología) / DESACTUALIZADO (1 tabla) | El framework de trabajo sigue siendo válido; solo la tabla de "God Services" tiene los mismos conteos de líneas desactualizados que #18 | Actualizar solo esa tabla |
| 24 | `.knowledge/CORRECTIONS_SUMMARY.md` | **OBSOLETO** | Describe un estado de mayo-2026 ya superado — el archivo que decía "corrupto, eliminado" (`Matriz_Subsidios_KPIs.xlsx`) volvió a existir como archivo válido después, y hay 2 handlers ETL nuevos no mencionados | **Candidato a borrar** (o reemplazar por un doc vivo de fuentes ETL) |
| 25 | `.knowledge/ORPHANED_FILES_AUDIT.md` | DESACTUALIZADO | El hallazgo central (3 archivos huérfanos) sigue siendo cierto, pero la narrativa de "archivo corrupto eliminado" ya no es cierta (mismo problema que #24) | Actualizar o fusionar con #24 |
| 26 | `api/README.md` | DESACTUALIZADO (severo) | Documenta ~2 de los 30 archivos de rutas reales; no menciona Ontología, Asistente IA, Voz ni CU en absoluto | Reescribir completo desde `api/v1/routes/` |
| 27 | `docker/README.md` | **OBSOLETO** (pendiente de confirmar con el equipo) | Presenta Docker Compose como ruta de producción viable — Docker **no está instalado** en el servidor real, que corre 100% por systemd | Agregar aviso explícito de "no es la ruta de producción actual" como mínimo |
| 28 | `domain/interfaces/README.md` | DESACTUALIZADO | Documenta 7 de las 13 interfaces reales (faltan las de ontología); dice que la Fase 2/3 de migración a interfaces está "pendiente" cuando ya está mayormente implementada (23 archivos consumidores confirmados) | Regenerar tabla de interfaces y corregir estado de migración |
| 29 | `whatsapp_bot/README.md` | DESACTUALIZADO (contradictorio) | Ya tiene una nota interna que se autocorrige pero queda desactualizada de nuevo; comandos documentados no coinciden con los reales; falta mencionar los 2 archivos más grandes/importantes del subsistema | Reescribir separando claramente canal Telegram (real) vs. WhatsApp (dormido) |
| 30 | `whatsapp_bot/QUICKSTART.md` | DESACTUALIZADO | Solo cubre onboarding de WhatsApp/Twilio (el canal sin tráfico real), no menciona Telegram (el canal real en producción) | Agregar guía de Telegram o marcar como "canal secundario" |
| 31 | `whatsapp_bot/GUIA_TELEGRAM_BOT_PASO_A_PASO.md` | **OBSOLETO — riesgo operativo real** | Instruye configurar un **webhook** de Telegram — el bot real usa `long polling` (`telegram_polling.py`), y Telegram no permite webhook + polling simultáneos (error 409). Seguir esta guía **rompería el bot en producción** | **Reescribir con urgencia** — es la única guía de este set que activamente rompería algo si se sigue tal cual |
| 32 | `whatsapp_bot/whatsapp-web-service/DEPENDENCIAS.md` | **OBSOLETO** | Documenta un componente (`whatsapp-web.js`) que nunca se desplegó — sin `node_modules`, sin Chrome instalado, ningún proceso corriendo | **Candidato a borrar** o marcar explícitamente como experimento abandonado |

---

## Resumen ejecutivo

- **6 documentos candidatos a borrar** (obsoletos, superados por otro documento vigente): #19, #20, #24, #27 (pendiente confirmar con el equipo), #31 (o reescribir en vez de borrar, dado el riesgo operativo), #32.
- **2 hallazgos operativos críticos, ya corregidos en este README**: rutas de log falsas en `RUNBOOK_PRODUCCION.md`, y stack de BD falso en `AGENTS.md` (`asyncpg` inexistente).
- **1 hallazgo de riesgo operativo real, aún sin corregir**: `whatsapp_bot/GUIA_TELEGRAM_BOT_PASO_A_PASO.md` puede romper el bot de producción si alguien la sigue literalmente.
- **5 documentos VIGENTES sin necesidad de cambios**: `FUENTES_RAG.md`, `GUIA_TROUBLESHOOTING.md` (menor), `INFORME_EJECUTIVO_CONTENIDO.md`, `INFORME_PORTAL_CAPITULOS_PENDIENTES.md`, `NOTA_FILA_TOTALES_EXCEL.md`.
- **Patrón sistémico**: 5+ enlaces rotos repetidos (`ARQUITECTURA_E2E.md`, `INDICE.md`, `DOCUMENTACION_TECNICA_ORQUESTADOR.md`, `MAPEO_COMPLETO_METRICAS.md`, `INVENTARIO_SERVIDOR.md`) — ninguno de estos 5 archivos existe en el repo, pero son citados desde múltiples documentos distintos.

## Backlog pendiente (no ejecutado en esta ronda — requiere confirmación del usuario)

Reescrituras significativas (más que un ajuste menor), por prioridad:

1. `whatsapp_bot/GUIA_TELEGRAM_BOT_PASO_A_PASO.md` — riesgo operativo real, máxima prioridad.
2. `RUNBOOK_PRODUCCION.md` — rutas de log + tabla de Celery Beat incompleta (~9 tareas faltantes).
3. `api/README.md` — documenta ~2 de 30 archivos de rutas.
4. `docs/GUIA_USO_API.md` — documenta 25 de 110 endpoints.
5. `docs/CRON_JOB_ETL_POSTGRESQL.md` — ~20 jobs faltantes.
6. `AGENTS.md` — corregir la línea de stack de BD (`asyncpg` → `psycopg2`).
7. `domain/interfaces/README.md`, `whatsapp_bot/README.md`, `whatsapp_bot/QUICKSTART.md`, `docs/ENDPOINT_ORCHESTRATOR_PARA_OSCAR.md`, `docs/LINKS_ACCESO.md`, `docs/refactoring/ARCHIVOS_GRANDES_PLAN.md`, `SKILL_PACK_V4.1.md` (solo su tabla) — actualizaciones más acotadas.

Ninguno de estos 7 puntos se ejecutó todavía — se dejó documentado para que el usuario decida el orden/alcance, dado el volumen de trabajo que implicaría hacerlos todos en la misma sesión.
