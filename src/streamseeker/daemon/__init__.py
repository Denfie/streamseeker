"""StreamSeeker background daemon (FastAPI + uvicorn).

Entry points:
- ``streamseeker.daemon.lifecycle`` — PID-file, start/stop/status helpers.
- ``streamseeker.daemon.server`` — the FastAPI app factory ``create_app()``.
"""

from streamseeker.daemon.lifecycle import (
    DAEMON_HOST,
    DAEMON_PORT,
    DaemonAlreadyRunningError,
    DaemonStatus,
    is_running,
    start,
    status,
    stop,
)

__all__ = [
    "DAEMON_HOST",
    "DAEMON_PORT",
    "DaemonAlreadyRunningError",
    "DaemonStatus",
    "is_running",
    "start",
    "status",
    "stop",
]
