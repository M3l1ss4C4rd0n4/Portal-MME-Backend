import multiprocessing
import os
from pathlib import Path

# Paths relativos
BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Server socket
bind = "127.0.0.1:8050"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gthread"
threads = 4
worker_connections = 1000
timeout = 120
max_requests = 1000
max_requests_jitter = 50
keepalive = 5

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn_dashboard_mme.pid"
# user/group managed by systemd
umask = 0
preload_app = True

# Logging
errorlog = str(LOGS_DIR / "gunicorn_error.log")
accesslog = str(LOGS_DIR / "gunicorn_access.log")
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "dashboard-mme"
