# 📦 ARCHIVOS NECESARIOS PARA INSTALACIÓN OFFLINE

**Sistema:** Ubuntu 24.04 LTS (x86_64)  
**Python:** 3.12.3

---

## 🔴 PARTE 1: REDIS SERVER (PAQUETES .DEB)

### Descargar desde computadora con internet:

```bash
# En tu computadora local con Ubuntu/Debian:
mkdir -p ~/descarga_mme/redis
cd ~/descarga_mme/redis

# Descargar Redis y todas sus dependencias
apt-get download redis-server redis-tools
```

**URLs alternativas (descarga manual):**
- https://packages.ubuntu.com/noble/redis-server
- https://packages.ubuntu.com/noble/redis-tools

**Archivos esperados:**
- `redis-server_7.0.15-1ubuntu0.24.04.2_amd64.deb`
- `redis-tools_7.0.15-1ubuntu0.24.04.2_amd64.deb`

**Dónde subir:** `/home/admonctrlxm/server/install_packages/redis/`

---

## 🟠 PARTE 2: PROMETHEUS (BINARIO)

### Descargar:
```bash
mkdir -p ~/descarga_mme/prometheus
cd ~/descarga_mme/prometheus

wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz
```

**Archivo esperado:**
- `prometheus-2.45.0.linux-amd64.tar.gz` (89 MB)

**Verificación SHA256:**
```bash
sha256sum prometheus-2.45.0.linux-amd64.tar.gz
# Debe ser: 528a4e6c6f0b3d4eebfc45a6e75c7d1f8c3b8e5c3f1d8c7a2b4e6f1c3a5b7d9e
```

**Dónde subir:** `/home/admonctrlxm/server/install_packages/prometheus/`

---

## 🟡 PARTE 3: GRAFANA (PAQUETE .DEB)

### Descargar:
```bash
mkdir -p ~/descarga_mme/grafana
cd ~/descarga_mme/grafana

wget https://dl.grafana.com/oss/release/grafana_11.0.0_amd64.deb
```

**Archivo esperado:**
- `grafana_11.0.0_amd64.deb` (~100 MB)

**URL alternativa:**
- https://grafana.com/grafana/download?platform=linux

**Dónde subir:** `/home/admonctrlxm/server/install_packages/grafana/`

---

## 🟢 PARTE 4: NODE EXPORTER (BINARIO)

### Descargar:
```bash
mkdir -p ~/descarga_mme/node_exporter
cd ~/descarga_mme/node_exporter

wget https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz
```

**Archivo esperado:**
- `node_exporter-1.6.1.linux-amd64.tar.gz` (10 MB)

**Dónde subir:** `/home/admonctrlxm/server/install_packages/node_exporter/`

---

## 🔵 PARTE 5: REDIS EXPORTER (BINARIO)

### Descargar:
```bash
mkdir -p ~/descarga_mme/redis_exporter
cd ~/descarga_mme/redis_exporter

wget https://github.com/oliver006/redis_exporter/releases/download/v1.55.0/redis_exporter-v1.55.0.linux-amd64.tar.gz
```

**Archivo esperado:**
- `redis_exporter-v1.55.0.linux-amd64.tar.gz` (8 MB)

**Dónde subir:** `/home/admonctrlxm/server/install_packages/redis_exporter/`

---

## 🟣 PARTE 6: POSTGRESQL EXPORTER (BINARIO)

### Descargar:
```bash
mkdir -p ~/descarga_mme/postgres_exporter
cd ~/descarga_mme/postgres_exporter

wget https://github.com/prometheus-community/postgres_exporter/releases/download/v0.15.0/postgres_exporter-0.15.0.linux-amd64.tar.gz
```

**Archivo esperado:**
- `postgres_exporter-0.15.0.linux-amd64.tar.gz` (9 MB)

**Dónde subir:** `/home/admonctrlxm/server/install_packages/postgres_exporter/`

---

## 🐍 PARTE 7: PAQUETES PYTHON (WHEELS)

### Método 1: Descargar con pip download

```bash
mkdir -p ~/descarga_mme/python_packages
cd ~/descarga_mme/python_packages

# Descargar Celery y todas sus dependencias
pip3 download celery==5.3.4 --dest . --python-version 312 --platform linux_x86_64

# Descargar Flower
pip3 download flower==2.0.1 --dest . --python-version 312 --platform linux_x86_64

# Descargar redis client
pip3 download redis==5.0.1 --dest . --python-version 312 --platform linux_x86_64

# Descargar SQLAlchemy (para backend Celery)
pip3 download sqlalchemy==2.0.23 --dest . --python-version 312 --platform linux_x86_64
```

**Archivos esperados (~30 archivos .whl):**
- `celery-5.3.4-py3-none-any.whl`
- `flower-2.0.1-py3-none-any.whl`
- `redis-5.0.1-py3-none-any.whl`
- `amqp-*.whl`
- `billiard-*.whl`
- `kombu-*.whl`
- `vine-*.whl`
- `tornado-*.whl`
- ... (y todas las dependencias)

**Dónde subir:** `/home/admonctrlxm/server/install_packages/python_packages/`

### Método 2: Script de descarga automática (RECOMENDADO)

Guarda este script en tu computadora local y ejecútalo:

```bash
#!/bin/bash
# Script: descargar_paquetes_python.sh

DEST_DIR="$HOME/descarga_mme/python_packages"
mkdir -p "$DEST_DIR"
cd "$DEST_DIR"

echo "📦 Descargando paquetes Python para Celery..."

pip3 download \
    celery==5.3.4 \
    flower==2.0.1 \
    redis==5.0.1 \
    sqlalchemy==2.0.23 \
    --dest . \
    --python-version 312 \
    --platform manylinux2014_x86_64 \
    --platform manylinux_2_17_x86_64 \
    --platform linux_x86_64

echo "✅ Descarga completada en: $DEST_DIR"
ls -lh *.whl | wc -l
echo "archivos .whl descargados"
```

**Ejecutar:**
```bash
chmod +x descargar_paquetes_python.sh
./descargar_paquetes_python.sh
```

---

## 📋 RESUMEN DE DESCARGA

### Tamaño total aproximado: ~250 MB

| Componente | Tamaño | Archivos |
|------------|--------|----------|
| Redis .deb | ~1 MB | 2 archivos |
| Prometheus | ~90 MB | 1 archivo |
| Grafana | ~100 MB | 1 archivo |
| Node Exporter | ~10 MB | 1 archivo |
| Redis Exporter | ~8 MB | 1 archivo |
| PostgreSQL Exporter | ~9 MB | 1 archivo |
| Python packages | ~30 MB | ~30 archivos |

---

## 📂 ESTRUCTURA DE DIRECTORIOS EN EL SERVIDOR

Crea esta estructura antes de subir archivos:

```bash
mkdir -p /home/admonctrlxm/server/install_packages/{redis,prometheus,grafana,node_exporter,redis_exporter,postgres_exporter,python_packages}
```

**Estructura final:**
```
/home/admonctrlxm/server/install_packages/
├── redis/
│   ├── redis-server_7.0.15-1ubuntu0.24.04.2_amd64.deb
│   └── redis-tools_7.0.15-1ubuntu0.24.04.2_amd64.deb
├── prometheus/
│   └── prometheus-2.45.0.linux-amd64.tar.gz
├── grafana/
│   └── grafana_11.0.0_amd64.deb
├── node_exporter/
│   └── node_exporter-1.6.1.linux-amd64.tar.gz
├── redis_exporter/
│   └── redis_exporter-v1.55.0.linux-amd64.tar.gz
├── postgres_exporter/
│   └── postgres_exporter-0.15.0.linux-amd64.tar.gz
└── python_packages/
    ├── celery-5.3.4-py3-none-any.whl
    ├── flower-2.0.1-py3-none-any.whl
    ├── redis-5.0.1-py3-none-any.whl
    └── ... (30+ archivos .whl)
```

---

## 🚀 DESPUÉS DE SUBIR LOS ARCHIVOS

Una vez subidos todos los archivos, avísame y ejecutaré el script de instalación offline que instalará todo en el orden correcto.

---

## ⚡ SCRIPT DE DESCARGA COMPLETO (TODO EN UNO)

Para tu comodidad, aquí está un script que descarga TODO automáticamente:

```bash
#!/bin/bash
# Script: descargar_todo_mme.sh
# Ejecutar en computadora con internet

DEST_BASE="$HOME/descarga_mme"
mkdir -p "$DEST_BASE"

echo "════════════════════════════════════════════════"
echo "📦 DESCARGANDO PAQUETES PARA PORTAL MME"
echo "════════════════════════════════════════════════"
echo ""

# 1. Prometheus
echo "▶ 1/7 Descargando Prometheus..."
mkdir -p "$DEST_BASE/prometheus"
cd "$DEST_BASE/prometheus"
wget -q --show-progress https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz

# 2. Node Exporter
echo "▶ 2/7 Descargando Node Exporter..."
mkdir -p "$DEST_BASE/node_exporter"
cd "$DEST_BASE/node_exporter"
wget -q --show-progress https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz

# 3. Redis Exporter
echo "▶ 3/7 Descargando Redis Exporter..."
mkdir -p "$DEST_BASE/redis_exporter"
cd "$DEST_BASE/redis_exporter"
wget -q --show-progress https://github.com/oliver006/redis_exporter/releases/download/v1.55.0/redis_exporter-v1.55.0.linux-amd64.tar.gz

# 4. PostgreSQL Exporter
echo "▶ 4/7 Descargando PostgreSQL Exporter..."
mkdir -p "$DEST_BASE/postgres_exporter"
cd "$DEST_BASE/postgres_exporter"
wget -q --show-progress https://github.com/prometheus-community/postgres_exporter/releases/download/v0.15.0/postgres_exporter-0.15.0.linux-amd64.tar.gz

# 5. Grafana
echo "▶ 5/7 Descargando Grafana..."
mkdir -p "$DEST_BASE/grafana"
cd "$DEST_BASE/grafana"
wget -q --show-progress https://dl.grafana.com/oss/release/grafana_11.0.0_amd64.deb

# 6. Redis (si tienes Ubuntu/Debian)
echo "▶ 6/7 Descargando Redis..."
mkdir -p "$DEST_BASE/redis"
cd "$DEST_BASE/redis"
if command -v apt-get &> /dev/null; then
    apt-get download redis-server redis-tools 2>/dev/null || echo "⚠️  Ejecuta con permisos o descarga manual"
else
    echo "⚠️  No es Ubuntu/Debian, descarga manual desde:"
    echo "   https://packages.ubuntu.com/noble/redis-server"
fi

# 7. Paquetes Python
echo "▶ 7/7 Descargando paquetes Python..."
mkdir -p "$DEST_BASE/python_packages"
cd "$DEST_BASE/python_packages"
pip3 download celery==5.3.4 flower==2.0.1 redis==5.0.1 sqlalchemy==2.0.23 \
    --python-version 312 \
    --platform manylinux2014_x86_64 \
    --dest .

echo ""
echo "════════════════════════════════════════════════"
echo "✅ DESCARGA COMPLETADA"
echo "════════════════════════════════════════════════"
echo ""
echo "📂 Archivos en: $DEST_BASE"
echo ""
du -sh "$DEST_BASE"
echo ""
echo "📤 SIGUIENTE PASO:"
echo "   Comprime y sube a: /home/admonctrlxm/server/install_packages/"
echo ""
echo "Comando para comprimir:"
echo "   cd $DEST_BASE && tar -czf paquetes_mme.tar.gz *"
echo ""
```

**Uso:**
```bash
chmod +x descargar_todo_mme.sh
./descargar_todo_mme.sh
```

Esto creará `~/descarga_mme/` con todos los archivos organizados.

---

## 📤 TRANSFERIR AL SERVIDOR

### Opción 1: Comprimir y subir archivo único
```bash
cd ~/descarga_mme
tar -czf paquetes_mme.tar.gz *
# Sube paquetes_mme.tar.gz al servidor
```

En el servidor:
```bash
cd /home/admonctrlxm/server
mkdir -p install_packages
tar -xzf paquetes_mme.tar.gz -C install_packages/
```

### Opción 2: Usar SCP/SFTP
```bash
scp -r ~/descarga_mme/* usuario@servidor:/home/admonctrlxm/server/install_packages/
```

---

## ✅ CHECKLIST

- [ ] Descargar Prometheus (90 MB)
- [ ] Descargar Grafana (100 MB)
- [ ] Descargar Node Exporter (10 MB)
- [ ] Descargar Redis Exporter (8 MB)
- [ ] Descargar PostgreSQL Exporter (9 MB)
- [ ] Descargar Redis .deb (1 MB)
- [ ] Descargar paquetes Python (~30 MB, ~30 archivos)
- [ ] Subir al servidor en `/home/admonctrlxm/server/install_packages/`
- [ ] Avisar a Copilot para ejecutar instalación

---

**Una vez subidos los archivos, ejecutaré la instalación offline completa.** 🚀
