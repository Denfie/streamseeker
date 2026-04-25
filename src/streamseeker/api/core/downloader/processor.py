import os
import random
import threading
import time

from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.downloader.helper import DownloadHelper
from streamseeker.api.core.exceptions import ProviderError, LanguageError, DownloadExistsError, LinkUrlError
from streamseeker.api.streams.streams import Streams

from streamseeker.api.core.logger import Logger
logger = Logger().instance()


class QueueProcessor(metaclass=Singleton):
    def __init__(self):
        self._manager = DownloadManager()
        self._helper = DownloadHelper()
        self._streams = Streams()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._config: dict = {}
        self._ddos_counter = 0
        self._active_downloads: list[threading.Thread] = []
        self._active_lock = threading.Lock()

    def start(self, config: dict = None) -> None:
        """Start the queue processor if not already running."""
        if config:
            self._config = config
        if self._thread and self._thread.is_alive():
            return
        # Reset items stuck in "downloading" from a previous interrupted session
        self._recover_interrupted()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def _recover_interrupted(self) -> None:
        """Reset 'downloading' items back to 'pending' and delete partial files."""
        queue = self._manager.get_queue()
        for item in queue:
            if item.get("status") == "downloading":
                file_name = item.get("file_name", "")
                # Delete partial file
                if file_name and os.path.isfile(file_name):
                    try:
                        os.remove(file_name)
                        logger.info(f"Deleted incomplete file: {os.path.basename(file_name)}")
                    except OSError:
                        pass
                self._manager.mark_status(file_name, "pending")

    def stop(self) -> None:
        """Signal the processor to stop after current download."""
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _active_count(self) -> int:
        """Count currently running download threads."""
        with self._active_lock:
            self._active_downloads = [t for t in self._active_downloads if t.is_alive()]
            return len(self._active_downloads)

    def _wait_for_slot(self) -> None:
        """Block until a download slot is available."""
        max_concurrent = self._config.get("max_concurrent", 2)
        while self._active_count() >= max_concurrent:
            if self._stop_event.is_set():
                return
            time.sleep(0.5)

    def _process_loop(self) -> None:
        """Main processing loop — pulls items and starts parallel downloads.

        Idles (doesn't exit) when the queue drains so the daemon can pick up
        items enqueued later. Use ``stop()`` to terminate cleanly.
        """
        while not self._stop_event.is_set():
            item = self._manager.get_next_pending()
            if item is None:
                # Queue empty — wait briefly and poll again. This keeps the
                # thread alive for items added to the queue after the first
                # drain (e.g. via the browser extension's overlay).
                if self._stop_event.wait(2.0):
                    break
                continue

            # Wait for a free slot
            self._wait_for_slot()
            if self._stop_event.is_set():
                break

            # Start download in its own thread
            worker = threading.Thread(
                target=self._process_item, args=(item,), daemon=True
            )
            worker.start()
            with self._active_lock:
                self._active_downloads.append(worker)

            # DDOS timing: after N starts, wait before starting next
            self._ddos_counter += 1
            ddos_limit = self._config.get("ddos_limit", 3)
            ddos_timer = self._config.get("ddos_timer", 90)
            if self._ddos_counter >= ddos_limit:
                logger.info(f"DDOS protection: waiting {ddos_timer}s before next batch")
                for _ in range(ddos_timer):
                    if self._stop_event.is_set():
                        return
                    time.sleep(1)
                self._ddos_counter = 0
            else:
                # Random delay between download starts
                delay_min = self._config.get("start_delay_min", 5)
                delay_max = self._config.get("start_delay_max", 25)
                delay = random.uniform(delay_min, delay_max)
                logger.debug(f"Nächste Verarbeitung in {delay:.0f}s")
                for _ in range(int(delay)):
                    if self._stop_event.is_set():
                        return
                    time.sleep(1)

        # Wait for all remaining downloads to finish
        for t in list(self._active_downloads):
            t.join(timeout=5)

        logger.info("Queue processor finished")

    def _process_item(self, item: dict) -> None:
        """Process a single queue item. Runs in its own thread."""
        file_name = item.get("file_name", "")
        stream_name = item.get("stream_name", "")
        name = item.get("name", "")
        language = item.get("language", "")
        preferred_provider = item.get("preferred_provider", "")
        type_ = item.get("type", "")
        season = item.get("season", 0)
        episode = item.get("episode", 0)

        # Check if max retries exceeded → skip
        max_retries = self._config.get("max_retries", 3)
        attempts = item.get("attempts", 0)
        if attempts >= max_retries:
            last_error = item.get("last_error", "Unknown error")
            logger.warning(f"Max retries ({max_retries}) reached for {os.path.basename(file_name)}")
            self._manager.mark_status(
                file_name, "skipped",
                skip_reason=f"Max retries reached: {last_error}"
            )
            return

        # Mark as downloading
        self._manager.mark_status(file_name, "downloading")

        # Check if already downloaded
        if self._helper.is_downloaded(file_name):
            logger.info(f"Bereits in Sammlung: {file_name}")
            self._manager.report_success(file_name)
            return

        # Delete partial file from previous attempt
        if file_name and os.path.isfile(file_name) and not self._helper.is_downloaded(file_name):
            try:
                os.remove(file_name)
                logger.debug(f"Removed incomplete file: {os.path.basename(file_name)}")
            except OSError:
                pass

        # Get stream and set config
        try:
            stream = self._streams.get(stream_name)
            stream.set_config(self._config)
        except Exception as e:
            self._manager.mark_status(file_name, "failed", last_error=f"Stream not found: {e}")
            return

        # Try to download with provider fallback
        try:
            downloader = stream.download(name, preferred_provider, language, type_, season, episode)
            if downloader is not None:
                # Wait for this download to complete
                # (downloader registers its own thread with the manager)
                downloader.join()
                # Success is reported by the downloader itself via manager.report_success()
            else:
                self._manager.mark_status(file_name, "failed", last_error="Downloader returned None")
        except DownloadExistsError:
            logger.info(f"Already exists: {file_name}")
            self._manager.report_success(file_name)
        except LanguageError as e:
            reason = str(e)
            logger.warning(f"Skipped: {reason}")
            self._manager.mark_status(file_name, "skipped", skip_reason=reason)
        except LinkUrlError as e:
            self._manager.mark_status(file_name, "failed",
                                       last_error=str(e),
                                       attempts=item.get("attempts", 0) + 1)
        except ProviderError as e:
            self._manager.mark_status(file_name, "failed",
                                       last_error=str(e),
                                       attempts=item.get("attempts", 0) + 1)
        except Exception as e:
            logger.error(f"Unexpected error processing {file_name}: {e}")
            self._manager.mark_status(file_name, "failed",
                                       last_error=str(e),
                                       attempts=item.get("attempts", 0) + 1)
