import os

# Read PORT from environment (Render sets this); default to 8000
port = os.getenv("PORT", "8000")
bind = f"0.0.0.0:{port}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
threads = 1
timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
loglevel = "info"
