# 🔗 LINKS DE ACCESO - Portal Energético MME

**Servidor:** 172.17.0.46  
**Fecha:** 2 de Febrero, 2026

---

## 🖥️ SERVICIOS WEB

### 1. Dashboard Principal (Gunicorn + Dash)
```
🔒 ACCESO LOCAL ÚNICAMENTE:
   http://127.0.0.1:8050

✅ TÚNEL SSH DESDE TU PC:
   ssh -L 8050:localhost:8050 admonctrlxm@172.17.0.46
   Luego abrir: http://localhost:8050
```

### 2. Prometheus (Monitoreo)
```
🌐 http://172.17.0.46:9090
⚠️  Puerto puede estar bloqueado por firewall

✅ TÚNEL SSH:
   ssh -L 9090:localhost:9090 admonctrlxm@172.17.0.46
   Luego abrir: http://localhost:9090
```

### 3. Celery Flower (Monitor de Tareas)
```
🌐 http://172.17.0.46:5555
⚠️  Puerto puede estar bloqueado por firewall

✅ TÚNEL SSH:
   ssh -L 5555:localhost:5555 admonctrlxm@172.17.0.46
   Luego abrir: http://localhost:5555
```

### 4. Nginx (Servidor Web)
```
🌐 http://172.17.0.46:80
⚠️  Sin proxy a dashboard configurado actualmente
```

---

## 🗄️ BASE DE DATOS POSTGRESQL

### Información de Conexión:
```
Nombre BD:  portal_energetico
Host:       localhost (127.0.0.1)
Puerto:     5432
Usuario:    postgres / mme_user
Tamaño:     4.5 GB
Registros:  39.4 millones
```

### OPCIÓN A: Explorador Interactivo (Terminal)
```bash
# Comando rápido:
bash /home/admonctrlxm/server/scripts/ver_bd.sh

# Menú con 6 opciones:
# 1. Listar todas las tablas
# 2. Ver información de una tabla
# 3. Previsualizar datos
# 4. Ejecutar SQL personalizado
# 5. Estadísticas rápidas
# 6. Salir
```

### OPCIÓN B: PostgreSQL CLI (psql)
```bash
# Conectar:
sudo -u postgres psql -d portal_energetico

# Comandos útiles:
\dt                    # Listar tablas
\d metrics            # Ver estructura
SELECT COUNT(*) FROM metrics;  # Consultar
\q                    # Salir
```

### OPCIÓN C: Demostración Visual
```bash
# Ver ejemplos en vivo:
bash /home/admonctrlxm/server/scripts/demo_bd.sh
```

### OPCIÓN D: Desde tu PC (pgAdmin/DBeaver)
```bash
# PASO 1: Túnel SSH desde tu PC
ssh -L 5432:localhost:5432 admonctrlxm@172.17.0.46

# PASO 2: Configurar pgAdmin/DBeaver
Host:       localhost
Port:       5432
Database:   portal_energetico
Username:   postgres
Password:   (vacío o preguntar)
SSL Mode:   Disable
```

---

## 📊 CONTENIDO DE LA BASE DE DATOS

```
7 Tablas Principales:
├── metrics_hourly       → 3.1 GB  (27.0M registros horarios)
├── metrics              → 1.4 GB  (12.4M registros diarios)
├── lineas_transmision   → 2.3 MB  (8,530 líneas SIMEN)
├── distribution_metrics → 1.5 MB  (14,644 métricas)
├── catalogos            → 352 KB  (2,264 catálogos)
├── commercial_metrics   → 240 KB  (198 métricas)
└── predictions          → 128 KB  (450 predicciones ML)

Datos desde: 2020-01-01
Hasta:       2026-01-30 (6+ años)
```

---

## 🔐 SEGURIDAD ACTUAL

```
✅ PostgreSQL: Solo localhost (no accesible externamente)
✅ Dashboard:  Solo localhost (bind 127.0.0.1:8050)
⚠️  Prometheus: Escucha en todas las interfaces (0.0.0.0:9090)
⚠️  Flower:     Escucha en todas las interfaces (0.0.0.0:5555)
❌ Nginx:      Sin proxy activo a dashboard
❌ Auth:       Sin autenticación configurada
```

---

## 🚀 ACCESO RÁPIDO COPY-PASTE

### Desde el Servidor (SSH):
```bash
# Dashboard interactivo PostgreSQL
bash /home/admonctrlxm/server/scripts/ver_bd.sh

# Demostración visual
bash /home/admonctrlxm/server/scripts/demo_bd.sh

# PostgreSQL directo
sudo -u postgres psql -d portal_energetico

# Ver servicios activos
systemctl status dashboard-mme prometheus celery-flower
```

### Desde tu PC (Windows/Mac/Linux):
```bash
# Túnel SSH para Dashboard
ssh -L 8050:localhost:8050 admonctrlxm@172.17.0.46

# Túnel SSH para PostgreSQL
ssh -L 5432:localhost:5432 admonctrlxm@172.17.0.46

# Túnel SSH para Prometheus
ssh -L 9090:localhost:9090 admonctrlxm@172.17.0.46

# Túnel SSH para Flower
ssh -L 5555:localhost:5555 admonctrlxm@172.17.0.46

# Múltiples túneles simultáneos
ssh -L 8050:localhost:8050 -L 5432:localhost:5432 -L 9090:localhost:9090 -L 5555:localhost:5555 admonctrlxm@172.17.0.46
```

Luego abrir en tu navegador:
- Dashboard: http://localhost:8050
- Prometheus: http://localhost:9090
- Flower: http://localhost:5555
- PostgreSQL: localhost:5432 (en pgAdmin/DBeaver)

---

## 📚 DOCUMENTACIÓN

- **Tutorial PostgreSQL:** `/home/admonctrlxm/server/docs/TUTORIAL_RAPIDO_POSTGRESQL.md`
- **Guía Completa:** `/home/admonctrlxm/server/docs/GUIA_ACCESO_POSTGRESQL.md`
- **README:** `/home/admonctrlxm/server/README.md`

---

**Última actualización:** 2 de Febrero, 2026  
**Generado por:** GitHub Copilot - Portal Energético MME
