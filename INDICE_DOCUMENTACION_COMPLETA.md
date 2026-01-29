# 📚 ÍNDICE DE DOCUMENTACIÓN - LIMPIEZA Y OPTIMIZACIÓN

**Generado:** 28 de Enero de 2026  
**Sistema:** Portal Energético MME  
**Ingeniero:** Especialista en Arquitectura y Optimización

---

## 🎯 INICIO RÁPIDO

### ¿Por dónde empezar?

1. **Si tienes 5 minutos:**  
   Lee → **[RESUMEN_EJECUTIVO_LIMPIEZA.md](RESUMEN_EJECUTIVO_LIMPIEZA.md)**

2. **Si tienes 15 minutos:**  
   Lee → **RESUMEN_EJECUTIVO** + Ejecuta → **`./verificar_sistema.sh`**

3. **Si tienes 30 minutos:**  
   Ejecuta → **`./limpieza_fase1_reorganizar.sh`** (limpieza completa)

4. **Si quieres detalles técnicos:**  
   Lee → **[PLAN_LIMPIEZA_OPTIMIZACION.md](PLAN_LIMPIEZA_OPTIMIZACION.md)** (documento completo)

---

## 📋 DOCUMENTOS DISPONIBLES

### � **NUEVO: Optimización Completada (28 Ene 2026)**

**[OPTIMIZACION_COMPLETA_20260128.md](docs/OPTIMIZACION_COMPLETA_20260128.md)** 🌟
- 📊 Reporte completo de optimización en 3 fases
- ⏱️ Duración total: ~1.5 horas
- ✅ Sistema 40-60% más rápido
- 🎯 6GB liberados + 7 nuevos índices en BD
- 📈 Métricas detalladas antes/después
- 🔧 18 workers activos (vs 7 anteriores)
- 📋 Checklist completo de mejoras implementadas
### 🏗️ **NUEVO: Plan de Refactorización Arquitectónica**

**[PLAN_REFACTORIZACION_ARQUITECTONICA.md](docs/PLAN_REFACTORIZACION_ARQUITECTONICA.md)** ⭐ **EN REVISIÓN**
- 🏛️ Transformación a arquitectura Clean/Hexagonal
- 📐 Nueva estructura: core/ → presentation/ → domain/ → infrastructure/
- 🔧 Refactorización completa de código (app.py: 206 → 30 líneas)
- 🧪 Sistema de tests automatizado
- 🌐 Preparación para API REST
- 📦 Migración gradual en 7 fases (13 horas estimadas)
- 💡 +60 ejemplos de código listos para implementar
- 🎯 **Estado:** Esperando aprobación para ejecución
---

### �🔴 **CRÍTICOS (Leer primero)**

#### 1️⃣ **RESUMEN_EJECUTIVO_LIMPIEZA.md**
- **Qué es:** Resumen ejecutivo de 2 páginas
- **Contenido:** Problemas, solución, pasos rápidos
- **Audiencia:** Todos (técnicos y no técnicos)
- **Tiempo lectura:** 5 minutos
- **Acción:** Entender el problema y la solución

```bash
cat RESUMEN_EJECUTIVO_LIMPIEZA.md
```

#### 2️⃣ **PLAN_LIMPIEZA_OPTIMIZACION.md**
- **Qué es:** Plan completo de limpieza y optimización
- **Contenido:** Análisis detallado, comandos, scripts
- **Audiencia:** Ingenieros y administradores
- **Tiempo lectura:** 30 minutos
- **Acción:** Entender cada optimización en detalle

```bash
less PLAN_LIMPIEZA_OPTIMIZACION.md
```

---

### 🟢 **INFORMATIVOS**

#### 3️⃣ **INFORME_INSPECCION_SISTEMA_20260128.md**
- **Qué es:** Inspección completa del sistema
- **Contenido:** Arquitectura, BD, IA, ML, infraestructura
- **Fecha:** 28 de Enero de 2026
- **Tiempo lectura:** 20 minutos
- **Acción:** Conocer el estado completo del sistema

```bash
less INFORME_INSPECCION_SISTEMA_20260128.md
```

#### 4️⃣ **README.md** (Raíz del proyecto)
- **Qué es:** Documentación principal del proyecto
- **Contenido:** Características, instalación, uso
- **Estado:** Actualizado a Diciembre 2025
- **Tiempo lectura:** 15 minutos

```bash
cat README.md
```

---

## 🛠️ SCRIPTS EJECUTABLES

### ⚡ **Scripts de Limpieza y Optimización**

#### 1️⃣ **verificar_sistema.sh** 
**🔍 Verificador rápido del estado del sistema**

```bash
./verificar_sistema.sh
```

**Qué hace:**
- ✅ Verifica espacio en disco
- ✅ Revisa procesos Gunicorn
- ✅ Comprueba base de datos
- ✅ Evalúa health check
- ✅ Detecta cache Python
- ✅ Cuenta logs antiguos

**Tiempo:** 10 segundos  
**Cuándo usar:** Siempre, antes y después de cambios

---

#### 2️⃣ **limpieza_fase1_reorganizar.sh**
**🧹 Limpieza completa y reorganización**

```bash
./limpieza_fase1_reorganizar.sh
```

**Qué hace:**
- 📦 Mueve backup 5.8 GB a `/backups/`
- 📝 Organiza documentación en `/docs/`
- 🔧 Mueve scripts a carpetas apropiadas
- 🐍 Elimina 11,850 archivos cache Python
- 📋 Limpia 304 logs antiguos (>30 días)
- 📦 Comprime logs de 7-30 días con gzip

**Tiempo:** 30 minutos  
**Ahorro:** ~6 GB  
**Riesgo:** ⚠️ Bajo (todo se mueve, no se elimina)  
**Backup:** ✅ Automático antes de cambios

---

#### 3️⃣ **limpieza_fase2_optimizar_db.sh**
**🗄️ Optimización completa de base de datos**

```bash
./limpieza_fase2_optimizar_db.sh
```

**Qué hace:**
- 📦 Backup automático antes de optimizar
- 🔧 VACUUM (desfragmentación)
- 📊 ANALYZE (estadísticas actualizadas)
- 📑 Crea 7 índices optimizados
- ⚡ Habilita WAL mode
- 💾 Configura cache de 64 MB
- ✅ Verifica integridad

**Tiempo:** 1 hora  
**Mejora:** 40-60% en queries  
**Riesgo:** ⚠️ Bajo (backup automático)  
**Requiere:** Ventana de mantenimiento

---

## 📊 RESULTADOS ESPERADOS

### **Antes de la Limpieza:**
```
✗ Espacio usado: 42 GB
✗ Archivos basura: 5.8 GB backup + 11,850 cache
✗ Logs antiguos: 304 archivos (>30 días)
✗ BD sin optimizar: Queries ~250ms
✗ Estructura desorganizada: 15+ .md en raíz
```

### **Después de Fase 1:**
```
✓ Espacio usado: 36 GB (-6 GB)
✓ Estructura organizada: docs/, backups/, scripts/
✓ Cache limpio: 0 archivos innecesarios
✓ Logs gestionados: Rotación configurada
✓ .gitignore actualizado
```

### **Después de Fase 2:**
```
✓ BD optimizada: VACUUM + 7 índices
✓ Queries: ~100ms (-60%)
✓ WAL mode activo
✓ Cache 64 MB configurado
✓ Integridad verificada
```

---

## 🎯 PLAN DE EJECUCIÓN RECOMENDADO

### **HOY (28 Enero 2026):**

```bash
# 1. Verificar estado actual
./verificar_sistema.sh

# 2. Leer documentación
cat RESUMEN_EJECUTIVO_LIMPIEZA.md

# 3. Entender el plan completo (opcional pero recomendado)
less PLAN_LIMPIEZA_OPTIMIZACION.md
```

---

### **Mañana o Esta Semana:**

```bash
# 4. Ejecutar Fase 1 (seguro, rápido)
./limpieza_fase1_reorganizar.sh

# 5. Verificar que todo funciona
./verificar_sistema.sh
curl http://localhost:8050/health

# 6. Revisar nueva estructura
ls -la docs/ backups/ scripts/
```

---

### **Ventana de Mantenimiento (Próxima Semana):**

```bash
# 7. Programar ventana de mantenimiento (1-2 horas)
# Recomendado: Sábado o Domingo 2:00 AM - 4:00 AM

# 8. Ejecutar Fase 2 (optimización BD)
./limpieza_fase2_optimizar_db.sh

# 9. Verificar mejoras
./verificar_sistema.sh

# 10. Test de rendimiento
time sqlite3 portal_energetico.db \
  "SELECT COUNT(*) FROM metrics WHERE fecha >= date('now', '-30 days');"
```

---

## 📁 ESTRUCTURA FINAL

Después de ejecutar todo, la estructura quedará así:

```
server/
│
├── 📄 Archivos principales (raíz limpia)
│   ├── app.py
│   ├── gunicorn_config.py
│   ├── requirements.txt
│   ├── .env
│   ├── .gitignore
│   └── README.md
│
├── 📚 docs/ (NUEVA - Toda la documentación)
│   ├── analisis_historicos/
│   │   ├── 2025-12-17_correccion_hidrologia.md
│   │   ├── 2025-12-17_inspeccion_etl.md
│   │   └── analisis_metricas_sospechosas.txt
│   ├── informes_mensuales/
│   │   ├── 2025-12_informe_diciembre.md
│   │   └── 2026-01_inspeccion_sistema.md
│   ├── tecnicos/
│   │   └── DOCUMENTACION_TECNICA_IA_ML.md
│   └── referencias/
│       └── convenio_utp_creg.pdf
│
├── 💾 backups/ (NUEVA - Backups organizados)
│   └── database/
│       ├── backup_antes_correccion_20251217.db (5.8 GB)
│       └── portal_energetico_preopt_*.db
│
├── 🔧 scripts/
│   ├── utilidades/
│   │   ├── check_database.py
│   │   └── validar_post_etl.sh
│   └── analisis_historico/
│       ├── analizar_metricas_sospechosas.py
│       ├── inspeccionar_etl_completo.py
│       └── inspeccionar_etl_db.py
│
├── 🧪 tests/
│   ├── test_*.py
│   └── verificaciones/
│       ├── test_chatbot_store.py
│       └── verificar_chatbot.py
│
├── 📋 logs/ (Limpio y rotado)
│   ├── dashboard.log (últimos 7 días)
│   ├── etl_diario_*.log
│   ├── validacion_*.log
│   └── archived/
│       └── *.log.gz (logs comprimidos)
│
├── 🗄️ portal_energetico.db (6.5 GB optimizado)
│
└── [Resto de carpetas sin cambios]
    ├── api-energia/
    ├── assets/
    ├── componentes/
    ├── etl/
    ├── pages/
    ├── siea/
    ├── sql/
    └── utils/
```

---

## ⚠️ PRECAUCIONES Y SEGURIDAD

### ✅ **Lo que SÍ es seguro:**

1. **Ejecutar `verificar_sistema.sh`** → Solo lectura
2. **Leer documentación** → Sin cambios
3. **Fase 1** → Mueve archivos, no elimina
4. **Fase 2** → Backup automático antes de optimizar

### ⚠️ **Lo que requiere precaución:**

1. **Fase 2 tarda ~1 hora** → Programar ventana de mantenimiento
2. **No interrumpir VACUUM** → Puede corromper BD
3. **Verificar espacio** → Necesita ~7 GB libres
4. **Backup externo** → Siempre tener backup fuera del servidor

---

## 🆘 EN CASO DE PROBLEMAS

### **Si algo sale mal:**

```bash
# 1. Restaurar BD desde backup
cp backups/database/portal_energetico_preopt_*.db portal_energetico.db

# 2. Verificar integridad
sqlite3 portal_energetico.db "PRAGMA integrity_check;"

# 3. Reiniciar servicio
sudo systemctl restart dashboard-mme.service

# 4. Ver logs de error
tail -100 logs/dashboard-error.log
```

### **Contactos:**

- **Logs del sistema:** `/home/admonctrlxm/server/logs/`
- **Backups:** `/home/admonctrlxm/server/backups/database/`
- **Health check:** `http://localhost:8050/health`

---

## ✅ CHECKLIST FINAL

### **Antes de Ejecutar:**
- [ ] Leer RESUMEN_EJECUTIVO_LIMPIEZA.md
- [ ] Ejecutar ./verificar_sistema.sh
- [ ] Verificar que hay >7 GB libres
- [ ] Informar al equipo sobre mantenimiento

### **Fase 1 (Hoy/Mañana):**
- [ ] Ejecutar ./limpieza_fase1_reorganizar.sh
- [ ] Verificar sistema: ./verificar_sistema.sh
- [ ] Probar dashboard: curl http://localhost:8050/health
- [ ] Revisar nueva estructura: ls -la docs/

### **Fase 2 (Ventana de Mantenimiento):**
- [ ] Programar ventana de 2 horas
- [ ] Ejecutar ./limpieza_fase2_optimizar_db.sh
- [ ] Verificar mejoras de rendimiento
- [ ] Documentar cambios realizados

### **Post-Ejecución:**
- [ ] Verificar funcionamiento completo
- [ ] Documentar tiempo de ejecución
- [ ] Registrar mejoras de rendimiento
- [ ] Programar próxima revisión (Febrero 2026)

---

## 📞 SOPORTE ADICIONAL

### **Documentación Original:**
- README.md (raíz del proyecto)
- DOCUMENTACION_TECNICA_IA_ML.md → docs/tecnicos/
- INFORME_DICIEMBRE_2025.md → docs/informes_mensuales/

### **Scripts de Verificación:**
- `./verificar_sistema.sh` → Estado actual
- `curl http://localhost:8050/health` → Health check
- `systemctl status dashboard-mme.service` → Estado servicio

---

**🎉 RESULTADO FINAL ESPERADO:**

✅ **7 GB de espacio liberado**  
✅ **60% mejora en rendimiento**  
✅ **Estructura profesional y organizada**  
✅ **Sistema limpio y mantenible**  
✅ **Documentación completa y accesible**

---

**Preparado por:** Ingeniero de Sistemas Especializado  
**Fecha:** 28 de Enero de 2026  
**Ubicación:** /home/admonctrlxm/server/  
**Próxima revisión:** Febrero 2026
