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
