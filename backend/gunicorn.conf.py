# GearCargo - Gunicorn Configuration

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes — capped at 4 by default to stay within the container's
# 1 GB memory budget (each sync worker uses ~50-100 MB).
# Override via GUNICORN_WORKERS env var if you run with more RAM.
workers = int(os.environ.get("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 4)))
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Logging
errorlog = "-"
accesslog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "gearcargo"

# Only run background scheduler in ONE worker process to prevent duplicate
# scheduled jobs (backups, emails etc.) from firing N times in parallel.
def post_fork(server, worker):
    """Called after a worker process is forked. Only worker 0 runs the scheduler."""
    import os
    if worker.age == 0:
        # First worker: init the scheduler
        pass  # Scheduler is already initialized in create_app()
    else:
        # All other workers: disable the scheduler that was started by create_app()
        try:
            from app.services import scheduler
            if scheduler.running:
                scheduler.shutdown(wait=False)
        except Exception:
            pass

# SSL (handled by external reverse proxy)
# keyfile = None
# certfile = None

# Hooks
def on_starting(server):
    """Called before the master process is initialized."""
    pass

def on_reload(server):
    """Called before reloading."""
    pass

def worker_int(worker):
    """Called when a worker receives SIGINT or SIGQUIT."""
    pass

def worker_abort(worker):
    """Called when a worker receives SIGABRT."""
    pass
