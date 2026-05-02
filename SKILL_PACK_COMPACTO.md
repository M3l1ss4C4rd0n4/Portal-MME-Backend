# SKILL PACK COMPACTO — Portal Dirección MME

> Leer COMPLETO antes de cualquier acción. Tiempo estimado: 90 segundos.

---

## 1. Jerarquía de Verdad (15s)

```
N1: RUNTIME    > N2: AST       > N3: GRAPHIFY   > N4: SUPUESTO
pytest pasa     grep confirma    grafo orienta     "parece que..."
curl 200        py_compile       query navega      "probablemente"
COUNT coincide  tsc --noEmit     path conecta      "seguramente"
```

**REGLA DE ORO:** Nunca decidir un cambio basado solo en N3 o N4. Mínimo 1 confirmación en N1 o N2.

---

## 2. Reglas Absolutas (30s)

| # | Regla | Nivel |
|---|-------|-------|
| 1 | NO modificar `core/container.py` directamente | 🔴 |
| 2 | NO agregar lógica a `HomeSlider.tsx` — extraer a hook | 🔴 |
| 3 | NO refactorizar servicio >1000 líneas sin diff textual de output | 🔴 |
| 4 | NO SQL dinámico sin pasar por `sql_validator.py` | 🔴 |
| 5 | NO exponer secrets en variables `NEXT_PUBLIC_*` | 🔴 |
| 6 | NO eliminar archivos sin `grep -r` + `git log` | 🟡 |
| 7 | NO cambiar schema DB sin snapshot previo (`verify_table.py`) | 🟡 |
| 8 | NO tocar `.service` systemd sin `systemctl status` + backup | 🟡 |
| 9 | NO tocar ETL en Celery Beat sin dry-run en tabla de prueba | 🟡 |
| 10 | NO crear archivo resultado >500 líneas | 🟡 |

---

## 3. Ciclo de Diagnóstico — CDA (15s)

```
1. OBSERVAR   → N1: tests, counts, curl, logs
2. PALPAR     → N2: grep -B5 -A5, py_compile, tsc --noEmit
3. MAPEAR     → N3: graphify query (orientación, NO verdad)
4. DIAGNOSTICAR → ¿Síntoma o causa? God file = síntoma. Acoplamiento = causa.
5. TRATAR     → Intervención mínima. Romper ciclos ANTES de extraer.
6. PERSISTIR  → Escribir /tmp/diag_[tarea].md INMEDIATAMENTE
7. MONITOREAR → Leer /tmp/diag_*.md, comparar contra baseline
```

**REGLA DE PERSISTENCIA:** El agente NO confía en su ventana de contexto. Baseline siempre en disco.

---

## 4. Señales de ALTO — PAUSAR (15s)

Código:
- `grep` muestra >10 archivos importando lo que voy a modificar
- El cambio afecta un servicio >1000 líneas
- No hay tests para lo que voy a cambiar Y afecta `infrastructure/`

Datos:
- Tabla >1GB y no sé su tamaño (`pg_relation_size`)
- 0 FKs en la tabla que toco
- ETL en Celery Beat
- Tabla >1GB sin stat proxy / TABLESAMPLE

Operativo:
- Multi-equipo (bot compartido)
- Cambio afecta `.service` systemd
- No hay commit reciente (<1h) y el cambio es >3 archivos

Si se activa CUALQUIERA de las señales de datos (tabla >1GB, 0 FKs, ETL Celery, .service) → **PAUSAR y obtener aprobación**.

---

## 5. Test de Necesidad de .md (10s)

ANTES de crear CUALQUIER `.md`:

1. ¿Existe ya un archivo con esta información? → SÍ = NO crear
2. ¿Será relevante dentro de 1 semana? → NO = usar `/tmp/`
3. ¿Es del estado ACTUAL del proyecto? → NO = commit message
4. ¿Un dev que no participó lo necesitaría? → NO = contexto de sesión
5. ¿Pasa el test de categoría? → Estado/Procedimiento/Arquitectura = OK. Otra cosa = NO crear.

---

## 6. Comandos Esenciales (15s)

```bash
# N1 — Runtime
cd /home/admonctrlxm/server && pytest tests/ -q --tb=no
cd /home/admonctrlxm/portal-direccion-mme && npm run build 2>&1 | tail -5
curl -s http://localhost:8000/health | head -1
pm2 status --no-color

# N2 — AST
grep -rn "from domain.services.X import" --include="*.py" .
python3 -c "from X import X; print(dir(X))"
python3 -m py_compile archivo.py

# N3 — Graphify
cat graphify-out/GRAPH_REPORT.md | head -80
graphify query "dependencias de X" --budget 3000

# Data — snapshot automático
python3 scripts/agent-tools/verify_table.py metrics_hourly
python3 scripts/agent-tools/check_cycles.py domain.A domain.B

# Persistencia
cat > /tmp/diag_tarea.md << 'EOF'
[baseline]
EOF
cat /tmp/diag_tarea.md
```

---

## 7. Checklist de Calidad (10s)

Técnico:
- [ ] `pytest` pasa (mismo baseline)
- [ ] `npm run build` pasa (si aplica)
- [ ] `curl` health checks OK

Datos (si tocó DB/ETL):
- [ ] `verify_table.py` post-check coincide con baseline
- [ ] Si Método D + DML masivo: `ANALYZE` ejecutado antes de post-check
- [ ] ETL idempotente verificado (2 ejecuciones = mismo resultado)

Arquitectura (si extrajo módulos):
- [ ] `check_cycles.py` verifica 0 ciclos (estáticos + lógicos)

Artefacto:
- [ ] Ningún archivo nuevo >500 líneas
- [ ] Nombres descriptivos en dominio del negocio

Documental:
- [ ] No se crearon `.md` innecesarios (test de 5 preguntas)
- [ ] `.md` existentes actualizados si el cambio es arquitectónico

---

## 8. Ejemplos Reales de Errores de Agentes Previos (20s)

### Caso 1: geo_service "deprecated" (Tarea 1.4)
**ERROR:** Agente asumió que `geo_service.py`, `orchestrator_service.py` y `predictions_service.py` estaban muertos basándose en N4 (supuesto: "están en lista de deprecated").

**DETECCIÓN (N2):** `grep -r "geo_service" --include="*.py"` mostró 2 imports activos en `interface/pages/hidrologia/`.

**RESULTADO:** Tarea saltada. Nada roto.

**LECCIÓN:** "Deprecated" es N4. Verificar siempre con N2 (`grep`) antes de eliminar.

### Caso 2: metrics_hourly = 32 GB sin stat proxy
**ERROR:** Agente ejecutó `SELECT COUNT(*) FROM metrics_hourly` + `string_agg` en tabla de 32 GB, bloqueando la BD.

**DETECCIÓN (N1):** `pg_relation_size` mostró 34,234,234,234 bytes.

**RESULTADO:** Query cancelada manualmente. BD recuperó en 5 min.

**LECCIÓN:** Siempre `pg_relation_size` PRIMERO. >10GB = Método D (stat proxy exclusivo). PROHIBIDO `string_agg` en tablas >1GB.

### Caso 3: Docstrings en __init__.py como "documentación"
**ERROR:** Agentes anteriores crearon docstrings ASCII de 35 líneas en `__init__.py`, generando nodos fantasmas en graphify.

**DETECCIÓN (N3):** `GRAPH_REPORT.md` mostró `__init__.py` como hubs con texto masivo.

**RESULTADO:** 23 archivos limpiados, 177 líneas eliminadas. Build sin regresión.

**LECCIÓN:** `__init__.py` = aggregators de imports, no documentación. Docstrings generan ruido en análisis estructural.

---

*Skill Pack Compacto — v1.0*
*Para el detallado completo, ver `SKILL_PACK_DETALLADO.md`*
*Para scripts ejecutables, ver `scripts/agent-tools/`*
