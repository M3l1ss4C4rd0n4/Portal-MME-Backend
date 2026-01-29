#!/bin/bash
# ════════════════════════════════════════════════════════════════
#   FASE 3: Configuración y Optimizaciones Finales
# ════════════════════════════════════════════════════════════════

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  ⚙️  OPTIMIZACIÓN FASE 3 - Configuración Final${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# ════════════════════════════════════════════════════════════════
# 1. CONFIGURAR LOGROTATE
# ════════════════════════════════════════════════════════════════

echo -e "${YELLOW}1️⃣  Configurando logrotate...${NC}"

LOGROTATE_CONF="/home/admonctrlxm/server/config/logrotate.conf"
mkdir -p /home/admonctrlxm/server/config

cat > "$LOGROTATE_CONF" << 'EOF'
/home/admonctrlxm/server/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
    create 0644 admonctrlxm admonctrlxm
    dateext
    dateformat -%Y%m%d
    maxage 30
}

/home/admonctrlxm/server/logs/etl/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
    create 0644 admonctrlxm admonctrlxm
    dateext
    dateformat -%Y%m%d
    maxage 30
}

/home/admonctrlxm/server/logs/api-energia/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
    create 0644 admonctrlxm admonctrlxm
    dateext
    dateformat -%Y%m%d
    maxage 30
}
EOF

echo -e "   ${GREEN}✅ Configuración logrotate creada${NC}"

# Crear cron para logrotate
LOGROTATE_CRON="/home/admonctrlxm/server/scripts/utilidades/run_logrotate.sh"
cat > "$LOGROTATE_CRON" << 'EOF'
#!/bin/bash
/usr/sbin/logrotate -s /home/admonctrlxm/server/logs/.logrotate-state /home/admonctrlxm/server/config/logrotate.conf
EOF

chmod +x "$LOGROTATE_CRON"
echo -e "   ${GREEN}✅ Script logrotate creado${NC}"

# ════════════════════════════════════════════════════════════════
# 2. OPTIMIZAR GUNICORN CONFIG
# ════════════════════════════════════════════════════════════════

echo -e "\n${YELLOW}2️⃣  Optimizando configuración Gunicorn...${NC}"

cat > /home/admonctrlxm/server/gunicorn_config.py << 'EOF'
"""Gunicorn configuration - Optimizado para Portal Energético MME"""
import multiprocessing
import os

# Server socket
bind = "127.0.0.1:8050"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1  # Fórmula recomendada
worker_class = "gthread"
threads = 4  # Aumentado de 3 a 4 threads por worker
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 120
keepalive = 5

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn_dashboard_mme.pid"
user = None
group = None
umask = 0
tmp_upload_dir = None

# Logging
errorlog = "/home/admonctrlxm/server/logs/gunicorn_error.log"
accesslog = "/home/admonctrlxm/server/logs/gunicorn_access.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "dashboard-mme"

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    pass

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    pass

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Gunicorn server ready. Listening on: %s", bind)

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forked child, re-executing.")

def worker_int(worker):
    """Called just after a worker received the SIGINT or SIGQUIT signal."""
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal")
EOF

echo -e "   ${GREEN}✅ gunicorn_config.py optimizado${NC}"
WORKER_COUNT=$(python3 -c "import multiprocessing; print(multiprocessing.cpu_count() * 2 + 1)" 2>/dev/null || echo 'auto')
echo -e "      Workers: $WORKER_COUNT"
echo -e "      Threads por worker: 4"

# ════════════════════════════════════════════════════════════════
# 3. OPTIMIZAR NGINX CONFIG
# ════════════════════════════════════════════════════════════════

echo -e "\n${YELLOW}3️⃣  Optimizando configuración Nginx...${NC}"

cat > /home/admonctrlxm/server/nginx-dashboard.conf << 'EOF'
upstream dashboard_mme {
    server 127.0.0.1:8050 fail_timeout=0;
}

# Cache zone para activos estáticos
proxy_cache_path /var/cache/nginx/dashboard levels=1:2 keys_zone=dashboard_cache:10m max_size=100m inactive=60m use_temp_path=off;

server {
    listen 80;
    server_name dashboard.mme.gov.co;  # Cambiar por dominio real
    
    client_max_body_size 50M;
    client_body_timeout 120s;
    
    # Logs
    access_log /home/admonctrlxm/server/logs/nginx_access.log;
    error_log /home/admonctrlxm/server/logs/nginx_error.log warn;
    
    # Compresión
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml+rss application/rss+xml font/truetype font/opentype application/vnd.ms-fontobject image/svg+xml;
    gzip_comp_level 6;
    gzip_proxied any;
    
    # Cache para activos estáticos
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://dashboard_mme;
        proxy_cache dashboard_cache;
        proxy_cache_valid 200 60m;
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_revalidate on;
        proxy_cache_lock on;
        add_header X-Cache-Status $upstream_cache_status;
        expires 1h;
        access_log off;
    }
    
    # WebSocket support
    location /_dash-update-component {
        proxy_pass http://dashboard_mme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        proxy_buffering off;
    }
    
    # Aplicación principal
    location / {
        proxy_pass http://dashboard_mme;
        proxy_redirect off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        
        # Buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        proxy_busy_buffers_size 8k;
    }
    
    # Health check endpoint
    location /health {
        proxy_pass http://dashboard_mme;
        access_log off;
    }
}
EOF

echo -e "   ${GREEN}✅ nginx-dashboard.conf optimizado${NC}"
echo -e "      • Compresión gzip habilitada"
echo -e "      • Cache Nginx para estáticos (60min)"
echo -e "      • WebSocket support mejorado"
echo -e "      • Buffers optimizados"

# ════════════════════════════════════════════════════════════════
# 4. CREAR SCRIPT DE REINICIO SEGURO
# ════════════════════════════════════════════════════════════════

echo -e "\n${YELLOW}4️⃣  Creando script de reinicio seguro...${NC}"

cat > /home/admonctrlxm/server/scripts/utilidades/restart_dashboard.sh << 'EOF'
#!/bin/bash
# Script para reiniciar el dashboard de forma segura

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Reiniciando Dashboard MME...${NC}"

# Obtener PIDs de Gunicorn
PIDS=$(pgrep -f "gunicorn.*dashboard-mme")

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}⚠️  No se encontraron procesos Gunicorn en ejecución${NC}"
else
    echo -e "${YELLOW}🛑 Deteniendo procesos Gunicorn...${NC}"
    for PID in $PIDS; do
        echo "   Matando proceso $PID"
        kill -TERM $PID 2>/dev/null || kill -9 $PID 2>/dev/null
    done
    sleep 2
fi

# Limpiar PID file si existe
rm -f /tmp/gunicorn_dashboard_mme.pid

# Iniciar Gunicorn
cd /home/admonctrlxm/server
echo -e "${GREEN}🚀 Iniciando Gunicorn...${NC}"
nohup gunicorn -c gunicorn_config.py app:server > /dev/null 2>&1 &

sleep 3

# Verificar
if pgrep -f "gunicorn.*dashboard-mme" > /dev/null; then
    echo -e "${GREEN}✅ Dashboard reiniciado exitosamente${NC}"
    echo -e "${GREEN}   Procesos activos: $(pgrep -f 'gunicorn.*dashboard-mme' | wc -l)${NC}"
else
    echo -e "${RED}❌ Error al reiniciar el dashboard${NC}"
    exit 1
fi
EOF

chmod +x /home/admonctrlxm/server/scripts/utilidades/restart_dashboard.sh
echo -e "   ${GREEN}✅ restart_dashboard.sh creado${NC}"

# ════════════════════════════════════════════════════════════════
# 5. OPTIMIZAR SYSTEMD SERVICE
# ════════════════════════════════════════════════════════════════

echo -e "\n${YELLOW}5️⃣  Optimizando systemd service...${NC}"

cat > /home/admonctrlxm/server/dashboard-mme.service << 'EOF'
[Unit]
Description=Dashboard Portal Energético MME
After=network.target

[Service]
Type=notify
User=admonctrlxm
Group=admonctrlxm
WorkingDirectory=/home/admonctrlxm/server
Environment="PATH=/home/admonctrlxm/.local/bin:/usr/bin"
ExecStart=/home/admonctrlxm/.local/bin/gunicorn -c gunicorn_config.py app:server
ExecReload=/bin/kill -s HUP $MAINPID
ExecStop=/bin/kill -s TERM $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

# Límites de recursos
LimitNOFILE=65536
LimitNPROC=4096

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/admonctrlxm/server/logs
ReadWritePaths=/home/admonctrlxm/server/portal_energetico.db
ReadWritePaths=/home/admonctrlxm/server/portal_energetico.db-shm
ReadWritePaths=/home/admonctrlxm/server/portal_energetico.db-wal
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
EOF

echo -e "   ${GREEN}✅ dashboard-mme.service optimizado${NC}"
echo -e "      • Restart automático habilitado"
echo -e "      • Límites de recursos configurados"
echo -e "      • Security hardening aplicado"

# ════════════════════════════════════════════════════════════════
# 6. CREAR MONITORING SCRIPT
# ════════════════════════════════════════════════════════════════

echo -e "\n${YELLOW}6️⃣  Creando script de monitoreo...${NC}"

cat > /home/admonctrlxm/server/scripts/utilidades/monitor_dashboard.sh << 'EOF'
#!/bin/bash
# Monitoreo continuo del dashboard

CHECK_INTERVAL=60  # Segundos entre checks

while true; do
    # Verificar si Gunicorn está corriendo
    if ! pgrep -f "gunicorn.*dashboard-mme" > /dev/null; then
        echo "[$(date)] ⚠️ Dashboard no está corriendo. Reiniciando..."
        /home/admonctrlxm/server/scripts/utilidades/restart_dashboard.sh
    fi
    
    # Verificar health endpoint
    HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8050/health)
    if [ "$HEALTH" != "200" ]; then
        echo "[$(date)] ⚠️ Health check falló (HTTP $HEALTH). Reiniciando..."
        /home/admonctrlxm/server/scripts/utilidades/restart_dashboard.sh
    fi
    
    sleep $CHECK_INTERVAL
done
EOF

chmod +x /home/admonctrlxm/server/scripts/utilidades/monitor_dashboard.sh
echo -e "   ${GREEN}✅ monitor_dashboard.sh creado${NC}"

# ════════════════════════════════════════════════════════════════
# 7. VERIFICAR PERMISOS
# ════════════════════════════════════════════════════════════════

echo -e "\n${YELLOW}7️⃣  Verificando permisos...${NC}"

chmod 755 /home/admonctrlxm/server/scripts/utilidades/*.sh
chmod 644 /home/admonctrlxm/server/*.conf
chmod 644 /home/admonctrlxm/server/gunicorn_config.py
chmod 644 /home/admonctrlxm/server/dashboard-mme.service

echo -e "   ${GREEN}✅ Permisos verificados${NC}"

# ════════════════════════════════════════════════════════════════
# RESUMEN
# ════════════════════════════════════════════════════════════════

echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ FASE 3 COMPLETADA${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}📊 Configuraciones creadas:${NC}"
echo "   • Logrotate configurado (30 días, compresión)"
echo "   • Gunicorn optimizado (auto workers, 4 threads)"
echo "   • Nginx optimizado (gzip, cache, WebSocket)"
echo "   • Systemd service mejorado (restart auto, security)"
echo "   • Scripts de reinicio y monitoreo"
echo ""
echo -e "${YELLOW}🎯 Próximos pasos manuales (opcional):${NC}"
echo "   1. Copiar systemd service:"
echo "      sudo cp dashboard-mme.service /etc/systemd/system/"
echo "      sudo systemctl daemon-reload"
echo "      sudo systemctl enable dashboard-mme"
echo "      sudo systemctl start dashboard-mme"
echo ""
echo "   2. Aplicar config Nginx (si se usa):"
echo "      sudo cp nginx-dashboard.conf /etc/nginx/sites-available/dashboard"
echo "      sudo ln -s /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/"
echo "      sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "   3. Reiniciar dashboard con nueva config:"
echo "      ./scripts/utilidades/restart_dashboard.sh"
echo ""
echo -e "${GREEN}💡 Para monitoreo continuo:${NC}"
echo "   nohup ./scripts/utilidades/monitor_dashboard.sh &"
echo ""
