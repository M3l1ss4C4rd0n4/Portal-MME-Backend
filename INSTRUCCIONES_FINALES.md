# ✅ CORRECCIONES APLICADAS - INSTRUCCIONES FINALES

**Fecha:** 2026-02-02  
**Estado:** Código corregido, listo para ejecutar ETL y validar

---

## 📝 RESUMEN DE CAMBIOS APLICADOS

### ✅ Fix #1: Aportes Hídricos (CRÍTICO)
**Archivo:** `domain/services/hydrology_service.py`
- ✅ Cambiado `entity='Sistema'` → `entity='Rio'` (líneas 64, 72)
- ✅ Agregado logging detallado de agregación por ríos
- ✅ Integrada validación con `MetricValidators`

### ✅ Fix #2: Restricciones (CRÍTICO)
**Archivo:** `domain/services/restrictions_service.py`
- ✅ Implementado fallback robusto para filtro `unit='COP'`
- ✅ Si falla filtro SQL, hace filtrado manual en pandas
- ✅ Si no hay datos locales, consulta API XM

### ✅ Fix #3: Validadores de Rangos (NUEVO)
**Archivo:** `domain/services/validators.py` (CREADO)
- ✅ Clase `MetricValidators` con rangos razonables
- ✅ Método `validate()` para verificar valores
- ✅ Función `safe_division()` para evitar divisiones por cero
- ✅ Incluye tests unitarios ejecutables

### ✅ Scripts de Automatización (NUEVOS)
- ✅ `ejecutar_etl_completo.sh` - Carga datos históricos
- ✅ `validate_fixes.sh` - Valida que todo funcione

---

## 🚀 PASOS PARA COMPLETAR LA CORRECCIÓN

### **PASO 1: EJECUTAR ETL (5-10 minutos)**

```bash
cd /home/admonctrlxm/server
bash ejecutar_etl_completo.sh
```

**Qué hace:**
- Descarga datos XM de últimos 3-6 meses
- Carga métricas: AporEner, Gene, RestAliv, RestSinAliv, etc.
- Muestra estadísticas de registros cargados

**Resultado esperado:**
```
✅ ETL COMPLETADO EXITOSAMENTE
⏱️ Duración: 4m 32s

📊 Estadísticas de la base de datos:
┌────────────────────┬────────────┬────────────┬────────────┐
│ metrica            │ registros  │ fecha_min  │ fecha_max  │
├────────────────────┼────────────┼────────────┼────────────┤
│ AporEner           │ 83805      │ 2020-01-01 │ 2026-02-01 │
│ RestAliv           │ 1523       │ 2023-01-01 │ 2026-02-01 │
│ RestSinAliv        │ 1489       │ 2023-01-01 │ 2026-02-01 │
└────────────────────┴────────────┴────────────┴────────────┘
```

---

### **PASO 2: REINICIAR SERVICIOS (30 segundos)**

```bash
# Reiniciar dashboard y workers
sudo systemctl restart dashboard-mme celery-worker celery-beat

# Esperar que inicien
sleep 10

# Verificar estado
systemctl status dashboard-mme celery-worker celery-beat | grep "Active:"
```

**Resultado esperado:**
```
Active: active (running) since ...
Active: active (running) since ...
Active: active (running) since ...
```

---

### **PASO 3: VALIDAR CORRECCIONES (10 segundos)**

```bash
cd /home/admonctrlxm/server
bash validate_fixes.sh
```

**Resultado esperado:**
```
════════════════════════════════════════
🔍 VALIDACIÓN POST-CORRECCIÓN
════════════════════════════════════════

1️⃣ Verificando datos en SQLite...
   Aportes (Rio): 83805 registros
   RestAliv: 1523 registros
   ✅ Aportes OK
   ✅ Restricciones OK

2️⃣ Verificando servicios...
   ✅ dashboard-mme
   ✅ celery-worker
   ✅ celery-beat

3️⃣ Verificando workers Celery...
   Workers activos: 3
   ✅ Celery OK

4️⃣ Verificando dashboard...
   ✅ Dashboard respondiendo (HTTP 200)

5️⃣ Verificando correcciones aplicadas...
   ✅ Fix #1 (Aportes entity='Rio') aplicado
   ✅ Fix #2 (Restricciones fallback) aplicado
   ✅ Fix #3 (validators.py) creado

════════════════════════════════════════
✅ VALIDACIÓN COMPLETADA
════════════════════════════════════════
```

---

### **PASO 4: VERIFICAR DASHBOARD VISUAL (Manual)**

Abre en navegador: **http://localhost:8050**

**Checklist visual:**

#### Página: Generación → Hidrología
- [ ] **Aportes Hídricos:** Debe mostrar 50-70% (NO 0%)
- [ ] **Reservas Hídricas:** Debe mantener ~76% (ya estaba correcto)
- [ ] **Gráfico temporal:** Debe mostrar curvas con variación (NO línea plana)
- [ ] **Ficha KPI:** Debe mostrar "vs. histórico: +X%" o "-X%"

#### Página: Restricciones
- [ ] **Restricciones Totales:** Debe mostrar >$500 millones COP (NO $0)
- [ ] **Gráfico de barras:** Debe mostrar valores para cada tipo de restricción
- [ ] **Evolución temporal:** Debe tener datos para los últimos 6 meses

#### Página: Comercialización
- [ ] **Precio Bolsa:** $150-300 $/kWh (rango razonable)
- [ ] **Spread Escasez:** $50-150 $/kWh (NO $502)
- [ ] **Gráficos:** Deben mostrar variación natural (no constantes)

#### Página: Distribución
- [ ] **DNA Nacional:** 180-220 GWh/día (NO 33 GWh)
- [ ] **Mercado Regulado/No Regulado:** Valores coherentes

---

## 🐛 TROUBLESHOOTING

### Problema: ETL falla con timeout

**Síntoma:**
```
⏱️ Timeout (30s) AporEner/Rio
```

**Solución:**
```bash
# La API XM puede estar lenta, ejecutar por rangos más cortos
# Editar etl/etl_todas_metricas_xm.py y cambiar:
# MESES_HISTORICOS = 6  →  MESES_HISTORICOS = 3
```

---

### Problema: Dashboard muestra errores 500

**Síntoma:**
El navegador muestra "Internal Server Error"

**Solución:**
```bash
# Ver logs en tiempo real
tail -f logs/app.log

# Buscar líneas con ERROR o CRITICAL
grep "ERROR\|CRITICAL" logs/app.log | tail -20
```

---

### Problema: Aportes siguen en 0%

**Verificación:**
```bash
# Confirmar que hay datos en BD
sqlite3 data/metricas_xm.db "SELECT COUNT(*) FROM metrics WHERE metrica='AporEner' AND entidad='Rio';"

# Debe retornar >50000
```

**Si retorna 0:**
```bash
# El ETL no cargó datos, ejecutar manualmente
python3 etl/etl_todas_metricas_xm.py
```

**Si retorna >50000 pero dashboard muestra 0%:**
```bash
# Verificar que el código tiene el fix aplicado
grep "entity='Rio'" domain/services/hydrology_service.py

# Debe aparecer: entity='Rio',  # ✅ FIX APLICADO
```

---

### Problema: Celery Beat inactivo

**Verificación:**
```bash
sudo systemctl status celery-beat
```

**Si está "inactive (dead)":**
```bash
# Iniciar manualmente
sudo systemctl start celery-beat

# Habilitar inicio automático
sudo systemctl enable celery-beat
```

---

## 📊 VALORES ESPERADOS POST-FIX

| Métrica | Antes (Bug) | Después (Fix) | Unidad |
|---------|-------------|---------------|--------|
| **Aportes Hídricos** | 0.00% ❌ | 60-70% ✅ | % |
| **Reservas Hídricas** | 76.41% ✅ | 70-85% ✅ | % |
| **Restricciones** | $0 M ❌ | $500-2000 M ✅ | COP |
| **Precio Bolsa** | $208 ✅ | $150-300 ✅ | $/kWh |
| **Spread Escasez** | $502 ❌ | $50-150 ✅ | $/kWh |
| **DNA Nacional** | 33 GWh ❌ | 180-220 GWh ✅ | GWh/día |
| **Generación SIN** | 242.84 GWh ✅ | 200-260 GWh ✅ | GWh/día |

---

## 🎯 CHECKLIST FINAL

### Pre-validación (antes de reiniciar)
- [x] Fix #1 aplicado en hydrology_service.py
- [x] Fix #2 aplicado en restrictions_service.py
- [x] Fix #3 validators.py creado
- [x] Scripts de automatización creados

### Post-ETL
- [ ] ETL ejecutado sin errores
- [ ] BD tiene >50k registros de AporEner
- [ ] BD tiene >1k registros de restricciones
- [ ] Fechas max en BD son recientes (2026-01-XX)

### Post-reinicio
- [ ] Dashboard responde HTTP 200
- [ ] Celery workers activos (3+)
- [ ] Celery Beat activo
- [ ] Sin errores CRITICAL en logs

### Post-validación visual
- [ ] Aportes > 50%
- [ ] Restricciones > $0
- [ ] Gráficos con datos
- [ ] No hay valores absurdos ($502, 33 GWh, etc.)

---

## 🎉 CONFIRMACIÓN DE ÉXITO

**Cuando veas:**
- ✅ Aportes Hídricos: **65.3%** (vs. histórico: +2.1%)
- ✅ Restricciones Totales: **$1,234 millones COP**
- ✅ Gráfico de aportes con curva suave (no línea plana)
- ✅ Sin alertas de "valores fuera de rango" en logs

**Significa que el sistema está 100% funcional.**

---

## 📞 SOPORTE

Si algún paso falla:
1. Revisa la sección **TROUBLESHOOTING** arriba
2. Ejecuta `validate_fixes.sh` para diagnóstico automático
3. Revisa logs: `tail -50 logs/app.log`
4. Consulta el **REPORTE_DIAGNOSTICO_BUGS_2026-02-02.md** para detalles técnicos

---

**FIN DE INSTRUCCIONES**
