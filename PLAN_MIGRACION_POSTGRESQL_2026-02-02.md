# 🔄 MIGRACIÓN COMPLETA A POSTGRESQL - PLAN DE ACCIÓN

**Fecha:** 2 de febrero de 2026  
**Estado:** PostgreSQL activo con 12+ millones de registros  
**Objetivo:** Eliminar referencias a SQLite y consolidar en PostgreSQL

---

## ✅ ESTADO ACTUAL

### PostgreSQL - ACTIVO
```
Base de datos: portal_energetico
Host: localhost:5432
Tablas: 7 (metrics, commercial_metrics, distribution_metrics, etc.)
Registros: 12,378,969
Estado: ✅ Operativo y en uso por el dashboard
```

### SQLite - OBSOLETO
```
Archivos encontrados:
1. portal_energetico.db (12 GB) ⚠️ 
2. data/metricas_xm.db (0 bytes) ✅
3. data/xm_data.db (0 bytes) ✅
4. infrastructure/database/simem_metrics.db (0 bytes) ✅
5. backups/database/simem_legacy.db (0 bytes) ✅
```

---

## 🎯 RECOMENDACIONES

### ✅ **RECOMENDACIÓN #1: ELIMINAR SQLite COMPLETAMENTE**

**Razones:**
- PostgreSQL ya tiene todos los datos (12M+ registros)
- SQLite causa confusión en el código
- `portal_energetico.db` ocupa 12 GB de espacio innecesario
- Evita errores futuros por usar la BD incorrecta

**Beneficios:**
- ✅ Un solo sistema de BD (menos complejidad)
- ✅ Libera 12 GB de disco
- ✅ Código más limpio y mantenible
- ✅ Evita bugs por usar BD incorrecta

---

### ✅ **RECOMENDACIÓN #2: ACTUALIZAR DOCUMENTACIÓN DE ETL**

Los archivos de ETL tienen comentarios obsoletos que mencionan SQLite:

**Archivos a actualizar:**
```
etl/etl_todas_metricas_xm.py → Línea 7, 394 (menciona SQLite)
etl/etl_xm_to_sqlite.py → TODO EL ARCHIVO (renombrar a etl_xm_to_postgres.py)
etl/etl_distribucion.py → Línea 4, 83
etl/etl_comercializacion.py → Línea 4
```

---

### ✅ **RECOMENDACIÓN #3: LIMPIAR REFERENCIAS EN CÓDIGO**

**Archivos que mencionan SQLite innecesariamente:**
```python
# infrastructure/external/xm_service.py
def obtener_datos_desde_sqlite()  # ✅ Ya usa MetricsRepository (PostgreSQL)
                                   # ⚠️ Nombre confuso, renombrar a:
                                   # obtener_datos_desde_bd()

# domain/services/*.py
# Varios servicios tienen comentarios "SQLite" pero usan PostgreSQL correctamente
```

---

## 📋 PLAN DE ACCIÓN RECOMENDADO

### FASE 1: BACKUP Y VERIFICACIÓN (5 min)
```bash
# 1. Verificar que PostgreSQL tiene todos los datos
sudo -u postgres psql -d portal_energetico -c "SELECT COUNT(*) FROM metrics;"
# Resultado esperado: 12,378,969 registros

# 2. Backup de PostgreSQL (por seguridad)
sudo -u postgres pg_dump portal_energetico > /tmp/portal_energetico_backup_$(date +%Y%m%d).sql

# 3. Verificar que el dashboard funciona con PostgreSQL
systemctl status dashboard-mme
```

### FASE 2: ELIMINAR ARCHIVOS SQLITE (2 min)
```bash
# 1. Mover archivos SQLite a carpeta de archivo
mkdir -p /home/admonctrlxm/server/legacy_archive/sqlite_deprecated_2026
mv /home/admonctrlxm/server/portal_energetico.db legacy_archive/sqlite_deprecated_2026/
mv /home/admonctrlxm/server/data/*.db legacy_archive/sqlite_deprecated_2026/
mv /home/admonctrlxm/server/infrastructure/database/*.db legacy_archive/sqlite_deprecated_2026/

# 2. Crear README explicativo
cat > legacy_archive/sqlite_deprecated_2026/README.md << 'EOF'
# Archivos SQLite Deprecados

**Fecha de migración:** 2 de febrero de 2026
**Razón:** Migración completa a PostgreSQL

Estos archivos fueron reemplazados por PostgreSQL (portal_energetico).
Se conservan temporalmente por seguridad, pero NO deben usarse.

**¿Eliminar estos archivos?**
Después de 30 días sin problemas, pueden eliminarse con:
```bash
rm -rf /home/admonctrlxm/server/legacy_archive/sqlite_deprecated_2026/
```
EOF
```

### FASE 3: ACTUALIZAR CÓDIGO (15 min)
```bash
# 1. Renombrar archivos ETL obsoletos
mv etl/etl_xm_to_sqlite.py etl/etl_xm_to_postgres.py

# 2. Actualizar comentarios en archivos ETL
# (Copilot puede hacer esto automáticamente)

# 3. Renombrar funciones confusas
# obtener_datos_desde_sqlite() → obtener_datos_desde_bd()
```

### FASE 4: REINICIAR SERVICIOS (2 min)
```bash
# Reiniciar dashboard con código actualizado
sudo systemctl restart dashboard-mme
systemctl status dashboard-mme
```

### FASE 5: VERIFICACIÓN FINAL (5 min)
```bash
# 1. Verificar que no hay archivos .db
find /home/admonctrlxm/server -name "*.db" -type f 2>/dev/null

# 2. Verificar que el dashboard funciona
curl http://localhost:8050/generacion/fuentes
# Debe cargar sin errores

# 3. Verificar logs
tail -50 logs/dashboard.log | grep -i error
```

---

## ⚠️ CONSIDERACIONES IMPORTANTES

### 1. **Backup Crítico**
Antes de eliminar SQLite, asegurar que:
- ✅ PostgreSQL tiene todos los datos
- ✅ Backup de PostgreSQL está creado
- ✅ Dashboard funciona correctamente

### 2. **Variables de Entorno**
Verificar que `.env` tenga:
```bash
USE_POSTGRES=True
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=portal_energetico
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<tu_password>
```

### 3. **Servicios que usan PostgreSQL**
```
✅ dashboard-mme (principal)
✅ celery-worker (tasks ETL)
✅ celery-beat (scheduler)
❓ celery-flower (monitoreo)
```

---

## 📊 IMPACTO ESPERADO

### Antes (con SQLite)
```
Espacio en disco: 12 GB (SQLite) + XGB (PostgreSQL) = ~12+ GB
Complejidad: 2 sistemas de BD
Riesgo de bugs: ALTO (confusión entre SQLite/PostgreSQL)
Mantenimiento: DIFÍCIL (dos sistemas)
```

### Después (solo PostgreSQL)
```
Espacio en disco: XGB (PostgreSQL) = ~12 GB liberados
Complejidad: 1 sistema de BD
Riesgo de bugs: BAJO (un solo sistema)
Mantenimiento: FÁCIL (un sistema, código limpio)
```

---

## 🚀 TIEMPO ESTIMADO TOTAL

| Fase | Duración | Criticidad |
|------|----------|------------|
| Backup y verificación | 5 min | ALTA |
| Eliminar archivos SQLite | 2 min | MEDIA |
| Actualizar código | 15 min | MEDIA |
| Reiniciar servicios | 2 min | ALTA |
| Verificación final | 5 min | ALTA |
| **TOTAL** | **~30 min** | |

---

## ✅ CHECKLIST FINAL

- [ ] Backup de PostgreSQL creado
- [ ] Verificar registros en PostgreSQL (>12M)
- [ ] Mover archivos .db a legacy_archive
- [ ] Actualizar comentarios en archivos ETL
- [ ] Renombrar etl_xm_to_sqlite.py → etl_xm_to_postgres.py
- [ ] Renombrar obtener_datos_desde_sqlite() → obtener_datos_desde_bd()
- [ ] Reiniciar dashboard-mme
- [ ] Verificar que el dashboard carga sin errores
- [ ] Verificar logs sin errores SQLite
- [ ] Documentar cambios en git commit

---

## 📝 NOTAS ADICIONALES

### ¿Por qué NO eliminar SQLite inmediatamente?
Por seguridad, primero MOVER a `legacy_archive/` y después de 30 días de operación sin problemas, eliminar definitivamente.

### ¿Qué pasa con los backups antiguos?
Los backups en `backups/database/` pueden conservarse como historial, ocupan 0 bytes.

### ¿Y si algo falla?
El backup de PostgreSQL permite restaurar en minutos. Los archivos SQLite en `legacy_archive/` están disponibles como último recurso.

---

**Siguiente paso recomendado:**
Ejecutar FASE 1 (Backup y Verificación) y confirmar que todo está OK antes de proceder.
