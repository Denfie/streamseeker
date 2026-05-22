"""In-process watchdog that detects daemon hangs and triggers a restart.

The daemon ships with KeepAlive=true (launchd) and Restart=on-failure (systemd),
but those only fire when the process exits. A deadlocked or unresponsive
process (event loop stuck, blocking I/O in a worker, native lib deadlock)
stays "alive" from the OS' point of view and never gets restarted.

This watchdog runs in a daemon thread inside the daemon process itself. It
periodically self-pings the local /health endpoint over HTTP. After
``failure_threshold`` consecutive failures it calls ``os._exit(1)`` so the
service manager (launchd / systemd) restarts the daemon cleanly.

The watchdog also heals a narrower, more common failure: the queue-processor
worker thread can exit (clean ``stop()``, uncaught exception in the loop)
while the FastAPI app keeps serving /health. In that case the daemon looks
healthy but the queue is frozen, and any items left as ``status=downloading``
stay zombies forever because ``_recover_interrupted`` only runs at
``processor.start()``. On each tick we re-start the processor when it isn't
running and there is still work pending, which triggers the recovery path
in-process so no full daemon restart is required.
"""

from __future__ import annotations

import os
import socket
import threading
import time
import urllib.error
import urllib.request

from streamseeker.api.core.logger import Logger

logger = Logger().instance()


class Watchdog:
    """Self-pinging watchdog. Force-exits the process if /health hangs."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        interval: float = 30.0,
        timeout: float = 5.0,
        failure_threshold: int = 3,
        startup_grace: float = 10.0,
        heal_processor: bool = True,
        heartbeat_every: int = 20,
    ) -> None:
        self._url = f"http://{host}:{port}/health"
        self._interval = interval
        self._timeout = timeout
        self._failure_threshold = failure_threshold
        self._startup_grace = startup_grace
        self._heal_processor = heal_processor
        # Every Nth tick we emit an "alive" log line. Without this the only
        # evidence the watchdog is still running is the absence of a hang —
        # which is exactly the signal we lose when it dies silently. At the
        # default interval=30s, heartbeat_every=20 logs once every 10 minutes.
        self._heartbeat_every = max(1, heartbeat_every)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -----------------------------------------------------------------
    # lifecycle
    # -----------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="ss-watchdog", daemon=True
        )
        self._thread.start()
        logger.info(
            f"watchdog started (interval={self._interval:.0f}s, "
            f"threshold={self._failure_threshold} consecutive failures)"
        )

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=self._interval + self._timeout + 1)
        self._thread = None

    # -----------------------------------------------------------------
    # internal
    # -----------------------------------------------------------------

    def _run(self) -> None:
        # Give uvicorn time to actually bind the socket before counting fails.
        if self._stop.wait(self._startup_grace):
            return

        consecutive_failures = 0
        tick = 0
        while not self._stop.is_set():
            # The whole iteration is wrapped: the watchdog's job is to detect
            # other components dying, so it must never die itself. We've seen
            # the in-the-wild case where the worker exited, the watchdog
            # should have healed it but didn't, and there was no log line
            # explaining why — strongly suggesting the watchdog thread
            # itself was gone. After this guard, any unexpected exception
            # is logged and the loop continues on the next tick.
            try:
                tick += 1
                ok, reason = self._probe()
                if ok:
                    if consecutive_failures > 0:
                        logger.info(
                            f"watchdog: /health recovered after {consecutive_failures} failures"
                        )
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    logger.warning(
                        f"watchdog: /health probe failed ({consecutive_failures}/"
                        f"{self._failure_threshold}) - {reason}"
                    )
                    if consecutive_failures >= self._failure_threshold:
                        self._force_exit(reason)
                        return
                if self._heal_processor:
                    self._heal_processor_if_needed()
                # Periodic "still alive" beacon so an operator inspecting
                # the log can tell at a glance the watchdog isn't dead.
                if tick % self._heartbeat_every == 0:
                    logger.info(
                        f"watchdog: heartbeat (tick={tick}, "
                        f"failures={consecutive_failures})"
                    )
            except BaseException as exc:  # noqa: BLE001 - protect the watchdog
                logger.exception(
                    f"watchdog: unexpected error in tick, continuing: {exc}"
                )
            if self._stop.wait(self._interval):
                return

    def _probe(self) -> tuple[bool, str]:
        try:
            req = urllib.request.Request(self._url, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if 200 <= resp.status < 300:
                    return True, "ok"
                return False, f"status={resp.status}"
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def _heal_processor_if_needed(self) -> None:
        """Re-start the queue processor when it has died with work still queued.

        Two states count as "work pending": items flagged ``pending`` and items
        flagged ``downloading``. The latter are zombies left over from the run
        in which the processor died, they only get reset to ``pending`` when
        ``processor.start()`` runs ``_recover_interrupted``.
        """
        try:
            from streamseeker.api.core.downloader.manager import DownloadManager
            from streamseeker.api.core.downloader.processor import QueueProcessor
        except Exception as exc:  # noqa: BLE001 (never crash the watchdog)
            logger.debug(f"watchdog: processor heal skipped (import failed: {exc})")
            return

        try:
            processor = QueueProcessor()
            if processor.is_running():
                return
            queue = DownloadManager.get_queue()
            pending = sum(1 for q in queue if q.get("status") == "pending")
            zombies = sum(1 for q in queue if q.get("status") == "downloading")
            if pending == 0 and zombies == 0:
                return
            logger.warning(
                f"watchdog: queue processor not running but queue has work "
                f"(pending={pending}, zombies={zombies}), restarting processor"
            )
            processor.start()
        except Exception as exc:  # noqa: BLE001 (never crash the watchdog)
            logger.warning(f"watchdog: processor heal failed: {exc}")

    def _force_exit(self, reason: str) -> None:
        logger.error(
            f"watchdog: daemon appears hung ({reason}) — forcing exit so "
            f"the service manager can restart it"
        )
        # _exit skips Python finalizers; that's intentional — finalizers may
        # themselves be hung. The OS reclaims sockets and FDs cleanly.
        os._exit(1)
