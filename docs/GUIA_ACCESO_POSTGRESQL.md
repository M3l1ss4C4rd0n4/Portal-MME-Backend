# 🗄️ GUÍA DE ACCESO A BASE DE DATOS POSTGRESQL

## Portal Energético MME - Ministerio de Minas y Energía

---

## 📊 **INFORMACIÓN DE LA BASE DE DATOS**

### **Conexión:**
- **Nombre BD:** `portal_energetico`
- **Host:** `localhost` (127.0.0.1)
- **Puerto:** `5432`
- **Usuario Owner:** `mme_user`
- **Usuario Admin:** `postgres`
- **Tamaño Total:** **4.5 GB** (4,549 MB)

### **Contenido:**
```
7 Tablas + 39.4 Millones de Registros Total:
├── metrics_hourly       → 3.1 GB  (27.0 millones de registros horarios)
├── metrics              → 1.4 GB  (12.4 millones de registros diarios)
├── lineas_transmision   → 2.3 MB  (8,530 líneas de transmisión)
├── distribution_metrics → 1.5 MB  (14,644 métricas de distribución)
├── catalogos            → 352 KB  (2,264 catálogos)
├── commercial_metrics   → 240 KB  (198 métricas comerciales)
└── predictions          → 128 KB  (450 predicciones ML)
```

### **Rango de Datos:**
- **Fecha Mínima:** 2020-01-01
- **Fecha Máxima:** 2026-01-30
- **Período Total:** 2,221 días (6+ años de datos)

---

## 🖥️ **MÉTODOS DE ACCESO (SIN HERRAMIENTAS EXTERNAS)**

### **OPCIÓN 1: Explorador Interactivo Python (RECOMENDADO) ✅**

**Acceso rápido:**
```bash
cd /home/admonctrlxm/server
bash scripts/ver_bd.sh
```

**O ejecutar directamente:**
```bash
python3 /home/admonctrlxm/server/scripts/db_explorer.py
```

**Menú interactivo:**
```
1. Listar todas las tablas
2. Ver información de una tabla
3. Previsualizar datos de una tabla
4. Ejecutar consulta SQL personalizada
5. Estadísticas rápidas
6. Salir
```

---

### **OPCIÓN 2: PostgreSQL CLI (psql) - Línea de Comandos**

**Conectar a la base de datos:**
```bash
sudo -u postgres psql -d portal_energetico
```

**Comandos útiles dentro de psql:**
```sql
-- Listar tablas
\dt

-- Ver estructura de una tabla
\d metrics

-- Ver tamaño de tablas
\dt+

-- Ejecutar consulta
SELECT COUNT(*) FROM metrics;

-- Ver últimos 10 registros
SELECT * FROM metrics ORDER BY fecha DESC LIMIT 10;

-- Salir
\q
```

---

### **OPCIÓN 3: Reporte Rápido SQL (Automatizado)**

**Ejecutar reporte completo:**
```bash
sudo -u postgres psql -d portal_energetico -f scripts/consultas_rapidas.sql
```

**Incluye:**
- ✅ Tamaño total de la BD
- ✅ Listado de tablas con tamaños
- ✅ Conteo de registros por tabla
- ✅ Rango de fechas
- ✅ Top 10 recursos más recientes
- ✅ Generación total por métrica (últimos 7 días)

---

### **OPCIÓN 4: Desde Código Python**

**Ejemplo de consulta:**
```python
import psycopg2
from psycopg2.extras import RealDictCursor

# Conectar
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="portal_energetico",
    user="postgres",
    cursor_factory=RealDictCursor
)

# Consultar
with conn.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) as total FROM metrics")
    result = cursor.fetchone()
    print(f"Total registros: {result['total']:,}")

conn.close()
```

**Usando la infraestructura del proyecto:**
```python
from infrastructure.database.connection import PostgreSQLConnectionManager

manager = PostgreSQLConnectionManager()
with manager.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT metrica, COUNT(*) as total
            FROM metrics
            WHERE fecha >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY metrica
            ORDER BY total DESC
            LIMIT 10;
        """)
        
        for row in cursor.fetchall():
            print(f"{row['metrica']}: {row['total']:,}")
```

---

## 📋 **ESTRUCTURA DE TABLAS PRINCIPALES**

### **Tabla: metrics (12.4M registros)**
```sql
Columnas:
- id                  → INTEGER (PK)
- fecha               → TIMESTAMP
- metrica             → TEXT (Generacion, Demanda, Precio, etc.)
- entidad             → TEXT (XM, operador, recurso)
- recurso             → TEXT (hidráulica, térmica, solar, eólica)
- valor_gwh           → DOUBLE PRECISION (valor en GWh)
- unidad              → TEXT (GWh, MWh, COP, etc.)
- fecha_actualizacion → TIMESTAMP
```

### **Tabla: metrics_hourly (27.0M registros)**
```sql
Columnas:
- id          → INTEGER (PK)
- fecha_hora  → TIMESTAMP
- metrica     → TEXT
- entidad     → TEXT
- recurso     → TEXT
- valor_mwh   → DOUBLE PRECISION
- unidad      → TEXT
```

### **Tabla: lineas_transmision (8,530 registros)**
```sql
Líneas de transmisión del SIMEN
- Coordenadas geográficas
- Tensión (kV)
- Estado operativo
```

---

## 🔍 **CONSULTAS ÚTILES**

### **1. Generación total por recurso (último mes):**
```sql
SELECT 
    recurso,
    COUNT(*) as registros,
    ROUND(SUM(valor_gwh)::numeric, 2) as total_gwh,
    ROUND(AVG(valor_gwh)::numeric, 2) as promedio_gwh
FROM metrics
WHERE fecha >= CURRENT_DATE - INTERVAL '30 days'
  AND metrica = 'Generacion'
GROUP BY recurso
ORDER BY total_gwh DESC;
```

### **2. Datos más recientes:**
```sql
SELECT 
    fecha,
    metrica,
    entidad,
    recurso,
    ROUND(valor_gwh::numeric, 2) as valor_gwh
FROM metrics
ORDER BY fecha DESC
LIMIT 20;
```

### **3. Estadísticas por año:**
```sql
SELECT 
    EXTRACT(YEAR FROM fecha) as año,
    COUNT(*) as registros,
    ROUND(SUM(valor_gwh)::numeric, 2) as total_gwh
FROM metrics
WHERE metrica = 'Generacion'
GROUP BY año
ORDER BY año DESC;
```

### **4. Recursos más activos:**
```sql
SELECT 
    recurso,
    COUNT(DISTINCT fecha) as dias_con_datos,
    MIN(fecha) as primera_fecha,
    MAX(fecha) as ultima_fecha
FROM metrics
GROUP BY recurso
ORDER BY dias_con_datos DESC;
```

---

## 🚀 **ACCESO DESDE TU PC (OPCIONAL)**

Si quieres acceder desde **pgAdmin** o **DBeaver** en tu computadora local:

### **Crear túnel SSH:**
```bash
# Desde tu PC (cmd/terminal)
ssh -L 5432:localhost:5432 admonctrlxm@172.17.0.46
```

### **Luego conectar en pgAdmin/DBeaver:**
```
Host: localhost
Port: 5432
Database: portal_energetico
Username: postgres
Password: (sin password por trust local)
```

---

## ⚠️ **SEGURIDAD ACTUAL**

- ✅ PostgreSQL escucha **SOLO en localhost** (no accesible desde red)
- ✅ Autenticación local por **trust** (sin password desde servidor)
- ⚠️ Para acceso remoto: Configurar `/etc/postgresql/*/main/pg_hba.conf`
- ⚠️ Para producción: Establecer password para `mme_user`

---

## 📝 **ARCHIVOS ÚTILES**

```
/home/admonctrlxm/server/
├── scripts/
│   ├── db_explorer.py          → Explorador interactivo Python
│   ├── ver_bd.sh               → Script de acceso rápido
│   └── consultas_rapidas.sql   → Reporte SQL automatizado
├── core/
│   └── config.py               → Configuración de conexión PostgreSQL
└── infrastructure/
    └── database/
        ├── connection.py       → Gestores de conexión
        └── repositories/       → Repositorios de datos (DDD)
```

---

## 🆘 **SOPORTE TÉCNICO**

### **Verificar estado de PostgreSQL:**
```bash
sudo systemctl status postgresql
```

### **Ver logs de PostgreSQL:**
```bash
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

### **Reiniciar PostgreSQL:**
```bash
sudo systemctl restart postgresql
```

### **Backup de la base de datos:**
```bash
sudo -u postgres pg_dump portal_energetico > backup_$(date +%Y%m%d).sql
```

### **Restaurar desde backup:**
```bash
sudo -u postgres psql portal_energetico < backup_20260202.sql
```

---

## ✅ **RECOMENDACIÓN FINAL**

**Para uso diario:** Utiliza el **explorador Python interactivo** (`bash scripts/ver_bd.sh`)

**Para consultas rápidas:** Usa **psql** (`sudo -u postgres psql -d portal_energetico`)

**Para reportes:** Ejecuta el **script SQL** (`sudo -u postgres psql -d portal_energetico -f scripts/consultas_rapidas.sql`)

---

**Última actualización:** 2 de Febrero, 2026  
**Base de datos:** portal_energetico v4.0 (PostgreSQL Migration)  
**Documentado por:** GitHub Copilot - Portal Energético MME
