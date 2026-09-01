# AGENTS.md — Server Backend MME

> **Última actualización:** 2026-05-02 (creación) — **corregido 2026-09-01**: stack de BD real (psycopg2, no asyncpg), líneas reales de God Files, deuda técnica de tests ya resuelta  
> **Framework:** SKILL_PACK_V4.1.md (Field Medic Framework — Jerarquía de Verdad + CDA + Ciclos + Hardware Physics)
> **Ubicación:** `/home/admonctrlxm/server/SKILL_PACK_V4.1.md`  
> Corregido 2026-09-01: la referencia anterior a una copia en `/home/admonctrlxm/portal-direccion-mme/SKILL_PACK_V4.1.md` era incorrecta — ese archivo no existe en el repo del frontend. Solo hay una copia, en este repo.

## 🚨 PASO 0: LEER EL SKILL PACK COMPLETO

**ANTES de cualquier acción en este proyecto, leer COMPLETAMENTE:**

```
/home/admonctrlxm/server/SKILL_PACK_V4.1.md
```

**NO resumir. NO memorizar selectivamente. LEER COMPLETO.**

El framework NO es sugerencia. Es el **contrato** operacional.

**¿Por qué V4.1 y no SKILL_PACK_CLAUDE.md?**
- V4.1 incluye: Jerarquía de Verdad con pesos, CDA 7-fases, detección de ciclos (estáticos Y lógicos), verificación de datos con Método A/B/C/D por tamaño tabla, cálculo de riesgo con `bc`, trampa ANALYZE, diff textual de PDF
- SKILL_PACK_CLAUDE.md era un draft incompleto. Kimi intentó un shortcut y falló.

---

## Stack

- Python 3.11 + FastAPI + Dash (legacy dashboard)
- PostgreSQL vía `psycopg2.pool.ThreadedConnectionPool` — usar `_get_pool()` de `infrastructure/database/connection.py`
  (corregido 2026-09-01: la referencia anterior a `asyncpg`/`get_pool()` de `core/database/pool.py` era incorrecta —
  ese módulo no existe en el repo; el acceso real a datos es síncrono vía psycopg2, no asyncpg)
- Redis (caché)
- Celery + Celery Beat (tareas async + scheduling — RIESGO ALTO)
- Systemd (4 servicios: `portal-api`, `dashboard-mme`, `whatsapp-bot`, `telegram-polling`)
- Producción: `https://api.portaldireccionee.minenergia.gov.co`

## Ecosistema Completo

Este repo es el **backend**. El **frontend** vive en `/home/admonctrlxm/portal-direccion-mme/` con su propio `AGENTS.md`.
Cualquier cambio que afecte ambos (API contracts, DB schema, deploy coordinado) requiere leer AMBOS AGENTS.md.

| Proyecto | Ruta | Stack | AGENTS.md |
|---|---|---|---|
| Backend (este) | `/home/admonctrlxm/server/` | Python 3.11 + FastAPI + Dash | Este archivo |
| Frontend | `/home/admonctrlxm/portal-direccion-mme/` | Next.js 15 + React 19 | `portal-direccion-mme/AGENTS.md` |
| WhatsApp Bot | `/home/admonctrlxm/server/whatsapp_bot/` | FastAPI (puerto 8001) | Este archivo |

## Servicios Systemd (4 servicios activos)

| Servicio | Propósito | Puertos | Restricción |
|---|---|---|---|
| `portal-api.service` | API principal FastAPI | 8000 | Tocar solo con backup + `systemctl status` pre/post |
| `dashboard-mme.service` | Dash legacy | — | Mismo que arriba |
| `whatsapp-bot.service` | Bot WhatsApp | 8001 | **NO tocar venv anidado** — ver Decisiones Congeladas abajo |
| `telegram-polling.service` | Bot Telegram | — | Mismo que arriba |

## Roadmap y Decisiones Congeladas

**Fuente de verdad:** `/home/admonctrlxm/portal-direccion-mme/PROPUESTA_MAESTRA.md`.

Decisiones explícitamente **PAUSED** (NO tocar sin coordinación con equipo humano):
- **DT-009 — Unificar `whatsapp_bot/venv/`**: El venv anidado del bot está hardcodeado en múltiples servicios systemd (`whatsapp-bot.service`, `telegram-polling.service`). La PROPUESTA_MAESTRA marca esta tarea como **PAUSED** porque requiere coordinación con el equipo de WhatsApp. Un agente que intente "limpiar el venv" o "unificar entornos" romperá los bots en producción.
- **DT-003 — Extraer WhatsApp Bot**: 522 nodos en el grafo, comparte DB e infraestructura con la API principal. Marcado como trabajo futuro (2-3 semanas). NO extraer sin plan escrito de múltiples fases.
- **Refactorizar `core/container.py` sin plan**: 575 nodos, cohesión 0.01. Solo extracción gradual con factories separadas (ver Skill 2.3 del SKILL_PACK).

Si un agente sugiere cualquiera de las acciones de arriba, mostrarle esta sección y **PAUSAR**.

---

## God Files y God Services — Señal de ALTO Automática

> Líneas verificadas 2026-09-01 (`grep -c "^"` directo sobre el archivo real, no de memoria). El conteo de "nodos" de `core/container.py` es una métrica de graphify (grafo de dependencias), no se remidió en esta pasada — su línea física real hoy es 614.

| Archivo | Líneas | Restricción |
|---|---|---|
| `core/container.py` | 614 líneas (575 nodos en el último graphify conocido, cohesión 0.01) | PROHIBIDO modificar directamente. Crear factory en archivo separado. |
| `domain/services/report_service.py` | **3.584 líneas** (antes documentado 1.850 — casi duplicó su tamaño) | `pdftotext` diff obligatorio. No refactorizar lógica sin tests de integración. |
| `domain/services/portal_report_service.py` | 2.819 líneas (no estaba en esta tabla antes) | `pdftotext` diff obligatorio — genera el informe ejecutivo público del portal. |
| `domain/services/executive_report_service.py` | 1.618 líneas | `pdftotext` diff obligatorio. |
| `domain/services/asistente_ia_service.py` | 1.443 líneas (no estaba en esta tabla antes) | Tool-calling del Asistente IA — cambios de prompt/catálogo de tools requieren correr `scripts/asistente/run_golden_dataset.py` antes de dar por cerrado un cambio. |
| `domain/services/notification_service.py` | 1.347 líneas | Canal de alertas críticas (Telegram/email) — no tocar sin probar en un canal de prueba primero. |
| `domain/services/losses_nt_service.py` | 1.208 líneas | Validación contra cálculo manual. |
| `domain/services/cu_service.py` | 1.122 líneas | Mock de XM obligatorio. |
| `domain/services/news_service.py` | 901 líneas (no estaba en esta tabla antes) | Cache de 8h compartido — invalidar en Redis tras cambiar la forma de los datos que devuelve. |
| `domain/services/intelligent_analysis_service.py` | 892 líneas | — |
| `domain/services/predictions_service_extended.py` | 887 líneas | Fixture de modelo. |
| `domain/services/simulation_service.py` | 748 líneas | Seed fijo en tests. |
| `domain/services/cu_minorista_service.py` | 676 líneas (no estaba en esta tabla antes) | Fórmula Art. 4 Res. CREG 119/2007 — no modificar sin citar la resolución exacta. |
| `domain/services/ai_service.py` | 574 líneas | `AgentIA` — failover multi-proveedor (Gemini→Groq→OpenRouter), ver `infrastructure/ml/llm_failover.py`. |

---

## Comandos de Baseline (N1 — ejecutar al inicio de cualquier tarea)

```bash
cd /home/admonctrlxm/server
pytest tests/ -q --tb=no
curl -s http://localhost:8000/health | head -1
sudo systemctl status portal-api.service --no-pager | grep "Active"
```

---

## Tablas de Alta Vigilancia

| Tabla | Tamaño aprox. | Método seguro | Restricción |
|---|---|---|---|
| `metrics_hourly` | ~32 GB | D (stat proxy exclusivo) | PROHIBIDO `COUNT(*)`, `string_agg`, `TABLESAMPLE` |
| Cualquier otra | Verificar con `pg_relation_size` | A/B/C/D según resultado | Ver Skill 9 del SKILL_PACK |

**SIEMPRE ejecutar `pg_relation_size('tabla')` antes de cualquier query sobre datos.**

---

## Scripts de Agent Tools

```bash
# Snapshot de tabla con método correcto (A/B/C/D automático)
python3 /home/admonctrlxm/server/scripts/agent-tools/verify_table.py [nombre_tabla]

# Detección de ciclos estáticos y lógicos
python3 /home/admonctrlxm/server/scripts/agent-tools/check_cycles.py domain.ServicioA domain.ServicioB
```

---

## Reglas Absolutas de Este Proyecto

| # | Regla | Por qué | Skill |
|---|---|---|---|
| 1 | `core/container.py` (575 nodos) → PROHIBIDO modificar directamente | God file (Multiply risk) | Skill 8 |
| 2 | Ciclos → Detectar estáticos Y lógicos ANTES de extraer | Bloquea refactorización | Skill 1.3 |
| 3 | ETL en Celery Beat → Dry-run + aprobación obligatoria | Riesgo ×3.0 | Skill 9.2 |
| 4 | Tablas >1GB → `pg_relation_size` primero. Método C/D correcto | Protege producción | Skill 9 |
| 5 | `metrics_hourly` (~32GB) → Método D exclusivo | Query completa = bloquea servidor | Skill 9 |
| 6 | God services (>1000 líneas) → `pdftotext` diff si output PDF | Diff binario miente | Skill 2.4 |
| 7 | SQL dinámico → `sql_validator.py` obligatorio, NO concatenación | SQL injection | - |
| 8 | `.service` systemd → backup + verify status pre/post | Crash en producción | - |
| 9 | Riesgo multiplicatorio → `echo "X * Y * Z" \| bc -l`, NUNCA mental | LLMs mienten >3 factores | Skill 2.1 |
| 10 | ANALYZE en tabla >10GB → PAUSAR y pedir permiso humano | Pico CPU 5-15s | Skill 9.2 |
| 11 | Crear .md → pasar test Skill 11 primero | Evita basura documental | Skill 11 |
| 12 | **CONFIAR EN /tmp/diag_*.md, NO EN MEMORIA** | Contexto se agota | Skill 0 |
| 13 | Código sin tests → NO tocar en producción (riesgo ×2.0) | Breaking changes silenciosos | - |

---

## Jerarquía de Verdad (NIVEL 1-4 con Pesos)

Cuando tomes decisiones de cambio, usa este sistema de confianza:

| Nivel | Fuente | Peso | Ejemplo |
|---|---|---|---|
| 1 | pytest PASA | +0.40 | Tests ejecutados ✅ |
| 1 | curl /health = 200 | +0.25 | Servicio respondiendo ✅ |
| 1 | SELECT COUNT(*) coincide | +0.25 | Datos consistentes ✅ |
| 2 | grep -B5 -A5 | +0.30 | AST confirma uso real ✅ |
| 3 | Graphify EXTRACTED | +0.20 | Aristas verificadas ✅ |
| 3 | Graphify INFERRED | +0.08 | Aristas inferidas (poca confianza) ⚠️ |
| 4 | Supuestos | 0.00 | "Probablemente no se usa" (no confiar) ❌ |

**REGLA CRÍTICA:** Peso acumulado ≥ 0.7 para ejecutar sin aprobación adicional.

Ver SKILL_PACK_V4.1.md Principio Fundamental para tabla completa.

---

## Deuda Técnica Activa (NO asumir que está corregida)

- ~~7 tests fallando~~ — corregido 2026-08-26: eran 3 tests desactualizados en `test_ai_service.py`
  que asumían el viejo diseño de `AgentIA` (un solo `client`/`provider` fijado en `__init__`); se
  actualizaron para reflejar el refactor del 2026-08-22 (`disponible` en vez de `client`). Suite
  completa en verde: `pytest tests/ -q --tb=no` → 373 passed, 0 failed.
- Servicios marcados "deprecated" que tienen imports activos: verificar con grep antes de eliminar
- 65 archivos con `print()` en lugar de logger

---

## Ciclos de Dependencia (CRÍTICO ANTES DE REFACTORIZAR)

Hay DOS tipos. Detectar AMBOS:

### Ciclo Estático (Import Cycle)
```bash
python3 -c "from domain.services.A import A; from domain.services.B import B; print('OK')"
# Si falla ImportError → CICLO ESTÁTICO CONFIRMADO
```

### Ciclo Lógico (Dependency Injection — Container)
```bash
# Verificar que Container NO inyecta A→B→A
grep -n "ServiceA" core/container.py | grep -i "ServiceB"
# Debe retornar vacío o solo comments
```

Tratamiento: Crear interfaz, aplicar Dependency Inversion (Skill 1.3a/b en SKILL_PACK_V4.1.md)

---

## PostgreSQL/Datos >1 GB: Métodos A/B/C/D

ANTES de tocar datos, obtener tamaño:

```bash
psql -d portal_energetico -t -A -c "SELECT pg_relation_size('tabla')"
```

| Tamaño | Método | Confianza | Qué hacer |
|---|---|---|---|
| < 100 MB | A | 100% | Checksum completo (SELECT md5) |
| 100 MB - 1 GB | B | 99% | Checksum (puede tardar 10-30s) |
| 1 - 10 GB | C | 85% | Stat proxy + TABLESAMPLE |
| > 10 GB | D | 70% | Stat proxy SOLO (PROHIBIDO COUNT) |

Ver SKILL_PACK_V4.1.md SKILL 9 para comandos exactos y trampa ANALYZE.

---

## Cálculo de Riesgo (Multiplicadores — Skill 2.1)

NUNCA calcular en tu cabeza. Usar `bc` (LLMs mienten >3 factores):

```bash
# Ejemplo: Sin tests (2.0) × tabla >1GB (1.5) × ETL Beat (3.0)
echo "2.0 * 1.5 * 3.0" | bc -l
# Output: 9.0 (> 8.0 = ROJO ABSOLUTO)
```

**Interpretación:**
- **<1.0** = Verde. Ejecutar.
- **1.0-2.5** = Verde + registrar
- **2.5-5.0** = Amarillo (plan obligatorio)
- **5.0-8.0** = Naranja (plan + verificación)
- **8.0-15.0** = ROJO (plan + aprobación)
- **>15.0** = ROJO OSCURO (subdividir)

Ver SKILL_PACK_V4.1.md Skill 2.1 para tabla completa.
