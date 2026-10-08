"""Gunicorn settings (production-style runtime, SPEC §3/§10)."""

import os
import shutil

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_CONCURRENCY", "4"))
threads = 1  # sync workers: one request per process, DB connection reused per worker
timeout = 30
graceful_timeout = 30  # finish in-flight requests on SIGTERM
keepalive = 5
# Worker heartbeat files must live on tmpfs: on Docker's overlay filesystem the per-loop
# heartbeat write can stall workers (gunicorn docs, "Blocking OS calls").
worker_tmp_dir = "/dev/shm"
accesslog = None  # request metrics/logs come from django-prometheus and structlog
errorlog = "-"


def on_starting(server: object) -> None:
    # Prometheus multiprocess mode: one shared directory, cleared on every start.
    directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if directory:
        shutil.rmtree(directory, ignore_errors=True)
        os.makedirs(directory, exist_ok=True)


def child_exit(server: object, worker: object) -> None:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)  # type: ignore[attr-defined,no-untyped-call]
