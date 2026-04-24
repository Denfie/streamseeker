"""Daemon process lifecycle — PID file, start, stop, status.

The daemon binds to ``127.0.0.1:8765`` by default. Only one instance may run
per user data root at a time; a stale PID file is detected and overwritten.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from streamseeker import paths

DAEMON_HOST = "127.0.0.1"
DAEMON_PORT = 8765


class DaemonAlreadyRunningError(RuntimeError):
    """Raised when start() is called while a daemon is already alive."""

    def __init__(self, pid: int) -> None:
        super().__init__(f"daemon already running (pid={pid})")
        self.pid = pid


@dataclass(frozen=True)
class DaemonStatus:
    running: bool
    pid: int | None = None
    host: str = DAEMON_HOST
    port: int = DAEMON_PORT


# ---------------------------------------------------------------------
# PID file
# ---------------------------------------------------------------------


def _pid_path() -> Path:
    return paths.daemon_pid_file()


def _read_pid() -> int | None:
    file = _pid_path()
    if not file.is_file():
        return None
    try:
        return int(file.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_pid(pid: int) -> None:
    file = _pid_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(str(pid))


def _clear_pid() -> None:
    file = _pid_path()
    if file.is_file():
        try:
            file.unlink()
        except OSError:
            pass


def _pid_alive(pid: int) -> bool:
    """Check whether a process with ``pid`` is alive on this system."""
    if pid <= 0:
        return False
    try:
        # Signal 0: no action, just permission/existence check.
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we lack perms — treat as alive.
        return True
    return True


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------


def is_running() -> bool:
    return status().running


def status() -> DaemonStatus:
    """Non-intrusive status check.

    Reads the PID file and verifies the process is alive. Stale PID files
    (process no longer exists) are cleaned up.
    """
    pid = _read_pid()
    if pid is None:
        return DaemonStatus(running=False)
    if _pid_alive(pid):
        return DaemonStatus(running=True, pid=pid)
    _clear_pid()
    return DaemonStatus(running=False)


def start(*, foreground: bool = False) -> DaemonStatus:
    """Start the daemon process.

    - ``foreground=True``: run the uvicorn server in the current process; this
      call blocks until the server exits. Used by systemd/LaunchAgent.
    - ``foreground=False``: double-fork into the background, return immediately
      with the new PID.
    """
    current = status()
    if current.running:
        raise DaemonAlreadyRunningError(current.pid or 0)

    _ensure_port_free()

    if foreground:
        _run_server_blocking()
        return DaemonStatus(running=False)  # only reached after graceful exit

    pid = _fork_detached()
    if pid == 0:
        # Child process — run server until terminated
        _run_server_blocking()
        os._exit(0)  # pragma: no cover
    # Parent — wait for the HTTP server to actually accept connections so
    # callers returning from start() can immediately use the daemon.
    _wait_until_listening(timeout=10.0)
    return status()


def stop(*, timeout: float = 10.0) -> bool:
    """Stop a running daemon. Returns True if a process was stopped."""
    current = status()
    if not current.running or current.pid is None:
        return False

    try:
        os.kill(current.pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_pid()
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(current.pid):
            _clear_pid()
            return True
        time.sleep(0.1)

    # Graceful shutdown didn't work — last resort
    try:
        os.kill(current.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _clear_pid()
    return True


# ---------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------


def _ensure_port_free() -> None:
    """Check that our configured port is free. Raises OSError if in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((DAEMON_HOST, DAEMON_PORT))
        except OSError as exc:
            raise OSError(
                f"port {DAEMON_PORT} is already in use — another daemon or service?"
            ) from exc


def _wait_until_listening(timeout: float = 10.0) -> bool:
    """Poll the daemon's port until it accepts TCP connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            try:
                sock.connect((DAEMON_HOST, DAEMON_PORT))
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                time.sleep(0.1)
    return False


def _fork_detached() -> int:
    """Double-fork, detach from controlling terminal. Returns child PID to parent."""
    pid = os.fork()
    if pid > 0:
        return pid  # parent of first fork — return to caller

    # First child — become session leader, fork again
    os.setsid()
    pid = os.fork()
    if pid > 0:
        # Intermediate — exit immediately; grandchild is our daemon
        os._exit(0)

    # Grandchild — redirect stdio to daemon log files
    log_path = paths.daemon_log_file()
    err_path = paths.daemon_err_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(os.devnull, "rb") as null_in:
        os.dup2(null_in.fileno(), sys.stdin.fileno())
    with open(log_path, "ab", buffering=0) as out:
        os.dup2(out.fileno(), sys.stdout.fileno())
    with open(err_path, "ab", buffering=0) as err:
        os.dup2(err.fileno(), sys.stderr.fileno())

    return 0  # signal to caller: I am the child


def _run_server_blocking() -> None:
    """Write PID, run uvicorn, clear PID on exit."""
    from streamseeker.daemon.server import create_app
    import uvicorn

    _write_pid(os.getpid())
    _install_signal_handlers()

    try:
        uvicorn.run(
            create_app(),
            host=DAEMON_HOST,
            port=DAEMON_PORT,
            log_level="info",
            access_log=False,
        )
    finally:
        _clear_pid()


def _install_signal_handlers() -> None:
    """Ensure SIGTERM / SIGINT trigger a clean shutdown."""

    def _graceful(_signo, _frame):
        # uvicorn installs its own handlers for SIGINT/SIGTERM and will exit
        # cleanly; this handler is a safety net if uvicorn hasn't grabbed them
        # yet (e.g. during startup).
        _clear_pid()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)


def describe() -> dict:
    """Return a summary dict used by ``streamseeker daemon status`` and ``/status``."""
    s = status()
    data = {
        "running": s.running,
        "host": s.host,
        "port": s.port,
        "pid_file": str(_pid_path()),
    }
    if s.pid is not None:
        data["pid"] = s.pid
    return data


# Provide a JSON-friendly status for scripting
def status_json() -> str:
    return json.dumps(describe(), indent=2)
