# 🎓 TUTORIAL RÁPIDO: Cómo Ver la Base de Datos PostgreSQL

## Portal Energético MME - Guía Visual Paso a Paso

---

## 🚀 **INICIO RÁPIDO (3 formas de acceder)**

### **MÉTODO 1: Script de Acceso Rápido ⭐ (MÁS FÁCIL)**

```bash
# Simplemente ejecuta:
bash scripts/ver_bd.sh
```

**Verás este menú:**
```
════════════════════════════════════════════════════════════════════════════
🗄️  POSTGRESQL DATABASE EXPLORER - Portal Energético MME
════════════════════════════════════════════════════════════════════════════

1. Listar todas las tablas
2. Ver información de una tabla
3. Previsualizar datos de una tabla
4. Ejecutar consulta SQL personalizada
5. Estadísticas rápidas
6. Salir

👉 Selecciona una opción (1-6): _
```

---

## 📖 **EJEMPLOS DE USO PASO A PASO**

### **EJEMPLO 1: Ver todas las tablas y sus tamaños**

```bash
bash scripts/ver_bd.sh
# Opción: 1
```

**Resultado:**
```
┌──────────────┬──────────────────────┬─────────┐
│ schemaname   │ tablename            │ size    │
├──────────────┼──────────────────────┼─────────┤
│ public       │ metrics_hourly       │ 3107 MB │
│ public       │ metrics              │ 1430 MB │
│ public       │ lineas_transmision   │ 2264 kB │
│ public       │ distribution_metrics │ 1480 kB │
│ public       │ catalogos            │  352 kB │
│ public       │ commercial_metrics   │  240 kB │
│ public       │ predictions          │  128 kB │
└──────────────┴──────────────────────┴─────────┘
```

---

### **EJEMPLO 2: Ver estructura de una tabla**

```bash
bash scripts/ver_bd.sh
# Opción: 2
# Escribir: metrics
```

**Resultado:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 TABLA: metrics
📊 Total registros: 12,378,969
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Columnas:
├── id                  → INTEGER (PK)
├── fecha               → TIMESTAMP
├── metrica             → TEXT
├── entidad             → TEXT
├── recurso             → TEXT
├── valor_gwh           → DOUBLE PRECISION
├── unidad              → TEXT
└── fecha_actualizacion → TIMESTAMP
```

---

### **EJEMPLO 3: Ver datos reales (previsualización)**

```bash
bash scripts/ver_bd.sh
# Opción: 3
# Tabla: metrics
# Límite: 10
```

**Resultado:**
```
┌────────────┬─────────────────────┬──────────────┬─────────┬───────────┬────────┐
│ fecha      │ metrica             │ entidad      │ recurso │ valor_gwh │ unidad │
├────────────┼─────────────────────┼──────────────┼─────────┼───────────┼────────┤
│ 2026-01-30 │ ObligEnerFirme      │ Recurso      │ 2R22    │ 0.00      │ GWh    │
│ 2026-01-30 │ ObligEnerFirme      │ Recurso      │ 2S6U    │ 0.00      │ GWh    │
│ 2026-01-30 │ DDVContratada       │ Recurso      │ 2QFU    │ 0.00      │ GWh    │
│ 2026-01-29 │ CapEfecNeta         │ Recurso      │ 3E9G    │ 0.01      │ GWh    │
│ 2026-01-28 │ Gene                │ SistemaSIN   │ HIDRO   │ 523.45    │ GWh    │
└────────────┴─────────────────────┴──────────────┴─────────┴───────────┴────────┘
```

---

### **EJEMPLO 4: Ejecutar consulta SQL personalizada**

```bash
bash scripts/ver_bd.sh
# Opción: 4
```

**Consulta de ejemplo:**
```sql
SELECT 
    metrica,
    COUNT(*) as registros,
    MIN(fecha) as desde,
    MAX(fecha) as hasta
FROM metrics
GROUP BY metrica
ORDER BY registros DESC
LIMIT 5;
```

**Resultado:**
```
┌────────────────┬────────────┬────────────┬────────────┐
│ metrica        │ registros  │ desde      │ hasta      │
├────────────────┼────────────┼────────────┼────────────┤
│ DDVContratada  │ 2,919,648  │ 2021-01-30 │ 2026-01-30 │
│ ENFICC         │ 2,917,819  │ 2021-01-30 │ 2026-01-30 │
│ ObligEnerFirme │ 2,915,994  │ 2021-01-30 │ 2026-01-30 │
│ CapEfecNeta    │ 1,017,262  │ 2021-01-30 │ 2026-01-29 │
│ Gene           │   522,866  │ 2020-01-01 │ 2026-01-28 │
└────────────────┴────────────┴────────────┴────────────┘
```

---

### **EJEMPLO 5: Estadísticas rápidas**

```bash
bash scripts/ver_bd.sh
# Opción: 5
```

**Resultado:**
```
┌─────────────────────────────┬───────────────────────┐
│ indicador                   │ valor                 │
├─────────────────────────────┼───────────────────────┤
│ Total Métricas Únicas       │ 131                   │
│ Total Recursos Únicos       │ 1,846                 │
│ Total Días con Datos        │ 2,222 días            │
│ Último Dato Actualizado     │ 2026-01-31 23:12:21   │
└─────────────────────────────┴───────────────────────┘
```

---

## 🔍 **CONSULTAS ÚTILES PRECARGADAS**

### **Ver generación eléctrica por recurso:**

```sql
SELECT 
    recurso,
    COUNT(*) as dias_operacion,
    ROUND(SUM(valor_gwh)::numeric, 2) as total_gwh,
    ROUND(AVG(valor_gwh)::numeric, 2) as promedio_gwh
FROM metrics
WHERE metrica = 'Gene'
  AND fecha >= '2026-01-01'
GROUP BY recurso
ORDER BY total_gwh DESC
LIMIT 10;
```

### **Ver últimos datos actualizados:**

```sql
SELECT 
    fecha,
    metrica,
    recurso,
    ROUND(valor_gwh::numeric, 2) as valor_gwh,
    fecha_actualizacion
FROM metrics
ORDER BY fecha_actualizacion DESC
LIMIT 20;
```

### **Ver datos horarios de hoy:**

```sql
SELECT 
    hora,
    metrica,
    recurso,
    ROUND(valor_mwh::numeric, 2) as valor_mwh
FROM metrics_hourly
WHERE fecha = CURRENT_DATE
ORDER BY hora DESC
LIMIT 30;
```

---

## 💻 **MÉTODO 2: Línea de Comandos PostgreSQL (psql)**

### **Acceder a psql:**

```bash
sudo -u postgres psql -d portal_energetico
```

### **Comandos básicos en psql:**

```sql
-- Ver tablas
\dt

-- Ver estructura de tabla
\d metrics

-- Ver tamaño de tablas
\dt+

-- Ejecutar consulta
SELECT COUNT(*) FROM metrics;

-- Ver datos recientes
SELECT * FROM metrics ORDER BY fecha DESC LIMIT 10;

-- Salir
\q
```

---

## 📊 **MÉTODO 3: Reporte Automatizado SQL**

```bash
# Ejecutar reporte completo con estadísticas
sudo -u postgres psql -d portal_energetico -f scripts/consultas_rapidas.sql
```

**Incluye:**
- ✅ Tamaño total de la base de datos
- ✅ Listado de tablas con tamaños
- ✅ Conteo de registros por tabla
- ✅ Rango de fechas disponibles
- ✅ Datos más recientes
- ✅ Agregaciones por métrica

---

## 🎯 **CASOS DE USO COMUNES**

### **1. ¿Cuántos datos tengo de enero 2026?**

```bash
bash scripts/ver_bd.sh
# Opción: 4
```

```sql
SELECT 
    COUNT(*) as registros_enero_2026,
    COUNT(DISTINCT recurso) as recursos_activos,
    MIN(fecha) as primer_dia,
    MAX(fecha) as ultimo_dia
FROM metrics
WHERE fecha >= '2026-01-01' 
  AND fecha < '2026-02-01';
```

---

### **2. ¿Qué recursos generaron más energía este mes?**

```bash
bash scripts/ver_bd.sh
# Opción: 4
```

```sql
SELECT 
    recurso,
    ROUND(SUM(valor_gwh)::numeric, 2) as total_generacion_gwh
FROM metrics
WHERE metrica = 'Gene'
  AND fecha >= '2026-01-01'
GROUP BY recurso
ORDER BY total_generacion_gwh DESC
LIMIT 15;
```

---

### **3. ¿Cuál es la demanda promedio por hora?**

```bash
bash scripts/ver_bd.sh
# Opción: 4
```

```sql
SELECT 
    hora,
    COUNT(*) as total_registros,
    ROUND(AVG(valor_mwh)::numeric, 2) as promedio_mwh
FROM metrics_hourly
WHERE metrica = 'DemaReal'
  AND fecha >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY hora
ORDER BY hora;
```

---

### **4. ¿Cuáles son las métricas más populares?**

```bash
bash scripts/ver_bd.sh
# Opción: 4
```

```sql
SELECT 
    metrica,
    COUNT(*) as total_registros,
    COUNT(DISTINCT recurso) as recursos_diferentes
FROM metrics
GROUP BY metrica
ORDER BY total_registros DESC
LIMIT 10;
```

---

## 🆘 **PROBLEMAS COMUNES Y SOLUCIONES**

### **Problema 1: "No module named tabulate"**

**Solución:**
```bash
pip3 install tabulate --break-system-packages
```

---

### **Problema 2: "psql: connection refused"**

**Verificar estado:**
```bash
sudo systemctl status postgresql
```

**Reiniciar PostgreSQL:**
```bash
sudo systemctl restart postgresql
```

---

### **Problema 3: "Permission denied"**

**Usar sudo:**
```bash
sudo -u postgres psql -d portal_energetico
```

---

## 🎓 **TIPS Y TRUCOS**

### **TIP 1: Guardar resultados en archivo**

```bash
# Guardar consulta en archivo
sudo -u postgres psql -d portal_energetico -c "
SELECT * FROM metrics LIMIT 100;
" > resultados.txt
```

---

### **TIP 2: Exportar a CSV**

```bash
sudo -u postgres psql -d portal_energetico -c "
COPY (SELECT * FROM metrics WHERE fecha >= '2026-01-01' LIMIT 1000) 
TO '/tmp/datos_enero_2026.csv' 
WITH CSV HEADER;
"
```

---

### **TIP 3: Contar registros rápidamente**

```bash
bash scripts/ver_bd.sh
# Opción: 4
```

```sql
SELECT 
    relname as tabla,
    n_live_tup as registros_aproximados
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
```

---

## 📚 **DOCUMENTACIÓN RELACIONADA**

- **Guía completa:** [docs/GUIA_ACCESO_POSTGRESQL.md](GUIA_ACCESO_POSTGRESQL.md)
- **Configuración:** [core/config.py](../core/config.py)
- **Conexiones:** [infrastructure/database/connection.py](../infrastructure/database/connection.py)

---

## ✅ **RESUMEN COMANDOS RÁPIDOS**

```bash
# Acceso interactivo (RECOMENDADO)
bash scripts/ver_bd.sh

# Línea de comandos PostgreSQL
sudo -u postgres psql -d portal_energetico

# Reporte automatizado
sudo -u postgres psql -d portal_energetico -f scripts/consultas_rapidas.sql

# Ver estructura de tabla específica
sudo -u postgres psql -d portal_energetico -c "\d metrics"

# Contar registros
sudo -u postgres psql -d portal_energetico -c "SELECT COUNT(*) FROM metrics;"
```

---

**¡IMPORTANTE!** 🎯

> **Para uso diario:** Usa `bash scripts/ver_bd.sh` (menú interactivo)
> 
> **Para consultas rápidas:** Usa `psql` (línea de comandos)
>
> **Para reportes:** Ejecuta `scripts/consultas_rapidas.sql`

---

**Última actualización:** 2 de Febrero, 2026  
**Creado por:** GitHub Copilot - Portal Energético MME
