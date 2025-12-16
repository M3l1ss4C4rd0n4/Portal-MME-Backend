# Configuración OPTIMIZADA de Gunicorn para Dashboard MME
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

bind = "0.0.0.0:8050"

# OPTIMIZADO: 6 workers para mejor rendimiento con múltiples usuarios concurrentes
workers = 6

# OPTIMIZADO: gthread permite manejar múltiples requests concurrentes por worker
worker_class = "gthread"
threads = 3  # 3 threads por worker = 18 threads totales (6 workers × 3)

# OPTIMIZADO: Timeout extendido para queries largas a API XM (5 minutos)
timeout = 300

# OPTIMIZADO: Keepalive para conexiones persistentes
keepalive = 5

# OPTIMIZADO: Límites de requests con jitter para reciclar workers (prevenir memory leaks)
max_requests = 1000
max_requests_jitter = 50

# OPTIMIZADO: preload_app desactivado (compatible con Dash callbacks)
# El callback unificado previene ejecuciones múltiples sin necesidad de preload
preload_app = False

# Logging mejorado
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"
