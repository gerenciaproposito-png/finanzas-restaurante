"""Background scheduler: every N minutes runs Drive sync + Sheets write-back."""
import os
import threading
import time

from app.database import SessionLocal

INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "600"))   # 10 min
INITIAL_DELAY = int(os.getenv("SYNC_INITIAL_DELAY", "5"))

_started = False
_lock = threading.Lock()


def _tick() -> None:
    from app.services.sync import run_sync
    from app.services.sync_ventas import run_sync_ventas
    from app.services.writeback import push_pending

    try:
        run_sync()
    except Exception:
        pass
    try:
        run_sync_ventas()
    except Exception:
        pass
    try:
        with SessionLocal() as db:
            push_pending(db)
    except Exception:
        pass


def _loop() -> None:
    time.sleep(INITIAL_DELAY)
    while True:
        _tick()
        time.sleep(INTERVAL_SECONDS)


def start() -> None:
    """Idempotent: only spawns the scheduler thread once."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, daemon=True, name="finanzas-scheduler").start()
