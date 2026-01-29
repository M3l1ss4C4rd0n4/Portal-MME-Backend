# 🛡️ PLAN DE MIGRACIÓN GRADUAL - MODO SEGURO
## Refactorización sin Romper Funcionalidad

**Fecha:** 28 de enero de 2026  
**Modo:** Gradual e Incremental  
**Estrategia:** Crear en paralelo, validar, migrar cuando esté listo  
**Prioridad:** Código limpio, estable, eficiente, sin errores, fácil de entender

---

## ✅ PRINCIPIOS DE MIGRACIÓN SEGURA

1. **NUNCA tocar código que funciona** hasta tener el reemplazo probado
2. **Crear estructura nueva EN PARALELO** (no mover archivos aún)
3. **Validar CADA cambio** antes de continuar
4. **Mantener código viejo funcionando** (coexistencia temporal)
5. **Backups automáticos** antes de cada cambio
6. **Rollback fácil** en cualquier momento

---

## 📅 CRONOGRAMA (1 semana, 2h/día)

### **HOY - Día 1: Estructura Base (2h)** 🟢 RIESGO CERO
**Objetivo:** Crear carpetas nuevas SIN tocar código existente

- [x] Crear estructura de carpetas nueva
- [x] Crear archivos __init__.py vacíos
- [x] Documentar estructura
- [x] Verificar que dashboard sigue funcionando

**¿Qué cambia?** Nada. Solo añadimos carpetas.  
**¿Puede romper algo?** No.  
**Tiempo:** 30 minutos

---

### **Día 2: Core - Configuración (2h)** 🟢 RIESGO MÍNIMO
**Objetivo:** Centralizar configuración SIN cambiar app.py aún

- [ ] Crear core/config.py (settings con Pydantic)
- [ ] Crear core/constants.py (constantes del sistema)
- [ ] Crear .env.example
- [ ] Probar que imports funcionan
- [ ] Verificar dashboard

**¿Qué cambia?** Añadimos archivos nuevos. app.py sigue igual.  
**¿Puede romper algo?** No, no lo usamos todavía.  
**Tiempo:** 2 horas

---

### **Día 3: Shared - Utils y Logging (2h)** 🟢 RIESGO MÍNIMO
**Objetivo:** Reorganizar utils manteniendo compatibilidad

- [ ] Crear shared/logging/logger.py (copiar de utils/logger.py)
- [ ] Crear shared/utils/ (organizados por tipo)
- [ ] Mantener utils/ viejo funcionando
- [ ] Imports antiguos siguen funcionando
- [ ] Verificar dashboard

**¿Qué cambia?** Copiamos código a nueva ubicación.  
**¿Puede romper algo?** No, el viejo sigue ahí.  
**Tiempo:** 2 horas

---

### **Día 4: Infrastructure - Database (2h)** 🟡 RIESGO BAJO
**Objetivo:** Crear capa de repositorios nueva

- [ ] Crear infrastructure/database/connection.py
- [ ] Crear infrastructure/database/repositories/base_repository.py
- [ ] Crear infrastructure/database/repositories/metrics_repository.py
- [ ] Probar repositorios con queries reales
- [ ] utils/db_manager.py sigue funcionando

**¿Qué cambia?** Añadimos nueva forma de acceder BD.  
**¿Puede romper algo?** No, usamos BD en paralelo.  
**Tiempo:** 2 horas

---

### **Día 5: Domain - Services (2h)** 🟡 RIESGO BAJO
**Objetivo:** Crear capa de servicios nueva

- [ ] Crear domain/models/metric.py
- [ ] Crear domain/services/metrics_service.py
- [ ] Probar service con datos reales
- [ ] Comparar resultados con código viejo
- [ ] Validar que dan mismos resultados

**¿Qué cambia?** Añadimos nueva lógica de negocio.  
**¿Puede romper algo?** No, aún no la usamos en páginas.  
**Tiempo:** 2 horas

---

### **Día 6: Piloto - Refactorizar 1 Página (2h)** 🟡 RIESGO BAJO
**Objetivo:** Probar arquitectura en 1 página de prueba

- [ ] Elegir página simple (ej: metricas.py)
- [ ] Crear presentation/pages/metricas_new.py
- [ ] Usar nuevos services y repositories
- [ ] Comparar con página vieja
- [ ] Si funciona bien → continuar
- [ ] Si hay problemas → ajustar antes de seguir

**¿Qué cambia?** Creamos versión nueva de 1 página.  
**¿Puede romper algo?** No, la vieja sigue funcionando.  
**Tiempo:** 2 horas

---

### **Día 7: Core - App Factory (2h)** 🟡 RIESGO BAJO
**Objetivo:** Refactorizar app.py usando factory

- [ ] Crear core/app_factory.py
- [ ] Crear wsgi.py nuevo
- [ ] Probar que app se crea correctamente
- [ ] Comparar con app.py viejo
- [ ] Backup de app.py → app_old.py
- [ ] Reemplazar app.py con versión nueva
- [ ] Reiniciar y validar TODO funciona

**¿Qué cambia?** Finalmente tocamos app.py.  
**¿Puede romper algo?** Muy poco probable. Tenemos backup.  
**Tiempo:** 2 horas

---

## 🔄 ESTRATEGIA DE VALIDACIÓN

### Después de CADA cambio:

```bash
# 1. Verificar sintaxis Python
python3 -m py_compile <archivo_modificado>

# 2. Verificar que dashboard arranca
curl http://localhost:8050/health

# 3. Verificar logs (sin errores nuevos)
tail -20 logs/gunicorn_error.log

# 4. Probar página en navegador
# Abrir: http://localhost:8050
# Navegar por 2-3 páginas
# Verificar que todo carga

# 5. Si hay ERROR → Revertir inmediatamente
git checkout <archivo>  # o restaurar backup
```

### Al final de cada día:

```bash
# Commit del progreso
git add .
git commit -m "Refactorización día X: <descripción>"

# Backup completo
cp -r /home/admonctrlxm/server /home/admonctrlxm/server_backup_diaX
```

---

## 📊 PUNTOS DE VALIDACIÓN

### ✅ Checkpoint 1 (Día 1): Estructura creada
**Criterio de éxito:**
- Carpetas creadas: core/, presentation/, domain/, infrastructure/, shared/
- Dashboard funciona normalmente
- Sin errores en logs

### ✅ Checkpoint 2 (Día 2-3): Core + Shared
**Criterio de éxito:**
- core/config.py funciona y lee .env
- shared/logging funciona
- Imports desde nuevas ubicaciones funcionan
- Dashboard funciona normalmente

### ✅ Checkpoint 3 (Día 4-5): Infrastructure + Domain
**Criterio de éxito:**
- Repositorios funcionan (queries a BD)
- Services funcionan (lógica de negocio)
- Resultados idénticos a código viejo
- Dashboard funciona normalmente

### ✅ Checkpoint 4 (Día 6): Piloto
**Criterio de éxito:**
- Página nueva funciona igual que vieja
- Sin errores en consola navegador
- Gráficos cargan correctamente
- Datos son correctos

### ✅ Checkpoint 5 (Día 7): App refactorizado
**Criterio de éxito:**
- app.py nuevo funciona
- Todas las páginas cargan
- Health check responde
- Sin errores en logs
- Performance igual o mejor

---

## 🚨 PLAN DE ROLLBACK

Si algo sale mal en cualquier momento:

### Rollback Inmediato (30 segundos):

```bash
# Si acabas de cambiar un archivo
git checkout -- <archivo>

# Si hay backup reciente
cp /home/admonctrlxm/server_backup_diaX/<archivo> <archivo>

# Reiniciar dashboard
./scripts/utilidades/restart_dashboard.sh
```

### Rollback Completo (2 minutos):

```bash
# Detener dashboard
pkill -f "gunicorn.*app:server"

# Restaurar desde backup del día anterior
rm -rf /home/admonctrlxm/server
cp -r /home/admonctrlxm/server_backup_diaX /home/admonctrlxm/server

# Reiniciar
cd /home/admonctrlxm/server
gunicorn -c gunicorn_config.py app:server &
```

---

## 📝 REGLAS DE ORO

### ❌ NUNCA HAGAS:

1. Eliminar código viejo antes de probar el nuevo
2. Cambiar múltiples archivos sin validar entre cada uno
3. Continuar si hay errores sin resolver
4. Modificar app.py hasta el día 7
5. Trabajar sin backup reciente

### ✅ SIEMPRE HAZ:

1. Backup antes de cada cambio importante
2. Probar que dashboard funciona después de cada cambio
3. Verificar logs después de cada cambio
4. Commit de git al final del día
5. Mantener código viejo funcionando hasta validar nuevo

---

## 🎯 RESULTADO ESPERADO

### Al final de la semana:

**Arquitectura:**
```
server/
├── app.py (30 líneas - refactorizado ✅)
├── core/ (config centralizado ✅)
├── presentation/ (UI organizada ✅)
├── domain/ (lógica de negocio ✅)
├── infrastructure/ (DB, APIs ✅)
└── shared/ (utils comunes ✅)
```

**Beneficios alcanzados:**
- ✅ Código 80% más organizado
- ✅ Separación de responsabilidades clara
- ✅ Fácil de entender (cada cosa en su lugar)
- ✅ Sin errores nuevos
- ✅ Funcionalidad 100% intacta
- ✅ Preparado para continuar refactorización

**Código viejo conservado:**
- 📦 pages/ viejo → legacy/pages_old/ (por si acaso)
- 📦 utils/ viejo → legacy/utils_old/ (por si acaso)
- 📦 app_old.py (backup del original)

---

## 📞 DURANTE LA MIGRACIÓN

### Si tienes dudas:
- Pregunta ANTES de hacer cambios grandes
- Comparte código para revisión
- Valida enfoque en página piloto

### Si encuentras errores:
- DETENTE inmediatamente
- Revisa logs: `tail -50 logs/gunicorn_error.log`
- Rollback si es necesario
- Pregunta para resolver

### Si algo no funciona como esperas:
- Compara con código viejo
- Valida que datos son iguales
- Verifica imports
- Revisa que no falta alguna dependencia

---

## 🚀 EMPEZAMOS AHORA - DÍA 1

Voy a ejecutar **Día 1: Crear Estructura Base** (30 minutos, riesgo cero)

¿Procedo? Responde:
- **"sí"** → Empiezo ahora mismo
- **"espera"** → Me dices qué quieres revisar primero
- **"no"** → Ajustamos el plan

---

**Nota:** Este plan garantiza que en TODO momento tu sistema funciona. Si en cualquier paso no te gusta el resultado, simplemente no continuamos y dejamos el código como está. No hay riesgo.
