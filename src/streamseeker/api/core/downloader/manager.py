import json
import os
import threading

from tqdm.auto import tqdm

from streamseeker import paths
from streamseeker.api.core.helpers import Singleton

# Shared devnull stream — tqdm writes here so it never touches the terminal
_devnull = open(os.devnull, "w")


class DownloadManager(metaclass=Singleton):

    def __init__(self):
        self._lock = threading.Lock()
        self._active_positions: set[int] = set()
        self._downloads: list[dict] = []
        self._retry_contexts: dict[str, dict] = {}  # file_name -> context
        self._active_bars: dict[str, tqdm] = {}

    def acquire_position(self) -> int:
        with self._lock:
            pos = 0
            while pos in self._active_positions:
                pos += 1
            self._active_positions.add(pos)
            return pos

    def release_position(self, pos: int) -> None:
        with self._lock:
            self._active_positions.discard(pos)

    def register_thread(self, thread: threading.Thread, name: str) -> None:
        with self._lock:
            self._downloads.append({"thread": thread, "name": name})

    def register_retry_context(self, file_name: str, context: dict) -> None:
        with self._lock:
            self._retry_contexts[file_name] = context

    def report_success(self, file_name: str) -> None:
        with self._lock:
            self._retry_contexts.pop(file_name, None)
            item = self._find_in_queue(file_name)
            self._remove_from_queue(file_name)
        # Library writes happen outside the queue lock to avoid nested-lock holds
        # with LibraryStore's own lock.
        if item is not None:
            self._record_in_library(item)

    def report_failure(self, file_name: str) -> None:
        with self._lock:
            ctx = self._retry_contexts.get(file_name)
            if ctx:
                self._mark_failed_in_queue(file_name)

    def active_count(self) -> int:
        with self._lock:
            self._downloads = [d for d in self._downloads if d["thread"].is_alive()]
            return len(self._downloads)

    def wait_all(self) -> None:
        for d in list(self._downloads):
            d["thread"].join()

    # --- Bar tracking ---

    def register_bar(self, bar: tqdm, name: str) -> None:
        with self._lock:
            self._active_bars[name] = bar

    def unregister_bar(self, name: str) -> None:
        with self._lock:
            self._active_bars.pop(name, None)

    def get_progress(self) -> list[dict]:
        """Return current progress of all active downloads."""
        with self._lock:
            result = []
            for name, bar in self._active_bars.items():
                total = bar.total or 0
                n = bar.n or 0
                pct = (n / total * 100) if total > 0 else 0
                result.append({
                    "name": name,
                    "n": n,
                    "total": total,
                    "pct": pct,
                    "unit": getattr(bar, "unit", ""),
                })
            return result

    def queue_summary(self) -> dict:
        with self._lock:
            self._downloads = [d for d in self._downloads if d["thread"].is_alive()]
            downloading = len(self._downloads)
        queue = self._load_queue()
        pending = sum(1 for q in queue if q.get("status") == "pending")
        failed = sum(1 for q in queue if q.get("status") == "failed")
        skipped = sum(1 for q in queue if q.get("status") == "skipped")
        paused = sum(1 for q in queue if q.get("status") == "paused")
        return {"downloading": downloading, "pending": pending, "failed": failed, "skipped": skipped, "paused": paused}

    def mark_status(self, file_name: str, status: str, **kwargs) -> None:
        with self._lock:
            queue = self._load_queue()
            for item in queue:
                if item.get("file_name") == file_name:
                    item["status"] = status
                    for key, value in kwargs.items():
                        item[key] = value
                    break
            self._save_queue(queue)

    # --- Persistent download queue ---

    def enqueue(self, item: dict) -> None:
        """Add a download item to the persistent queue."""
        with self._lock:
            queue = self._load_queue()
            # Avoid duplicates by file_name
            existing = {q.get("file_name") for q in queue}
            if item.get("file_name") not in existing:
                item.setdefault("status", "pending")
                item.setdefault("attempts", 0)
                item.setdefault("skip_reason", None)
                item.setdefault("last_error", None)
                queue.append(item)
                self._save_queue(queue)

    def _remove_from_queue(self, file_name: str) -> None:
        queue = self._load_queue()
        queue = [item for item in queue if item.get("file_name") != file_name]
        self._save_queue(queue)

    def _find_in_queue(self, file_name: str) -> dict | None:
        for item in self._load_queue():
            if item.get("file_name") == file_name:
                return item
        return None

    @staticmethod
    def _record_in_library(item: dict) -> None:
        """Record a successful download in the Library.

        Derives ``<stream>::<slug>`` from the queue item and dispatches to
        ``LibraryStore.mark_episode_downloaded`` or ``mark_movie_downloaded``
        based on ``type``. Library writes are best-effort — failures here must
        never abort the caller's success path.
        """
        stream = item.get("stream_name")
        slug = item.get("name")
        if not stream or not slug:
            return
        key = f"{stream}::{slug}"

        # Local import to avoid a circular dependency at module load time.
        from streamseeker.api.core.library import LibraryStore

        try:
            store = LibraryStore()
            item_type = (item.get("type") or "").lower()
            season = int(item.get("season") or 0)
            episode = int(item.get("episode") or 0)

            if item_type == "filme":
                store.mark_movie_downloaded(key, episode or season or 1)
            else:
                if season > 0 and episode > 0:
                    store.mark_episode_downloaded(key, season, episode)
        except Exception:
            # Library write must not break the downloader
            return

        # Opportunistic metadata enrichment — fire-and-forget in a thread so
        # a slow external API never blocks the download pipeline. The
        # resolver itself swallows all errors internally.
        try:
            from streamseeker.api.core.metadata.resolver import MetadataResolver

            def _enrich():
                try:
                    MetadataResolver().enrich(key)
                except Exception:
                    pass

            threading.Thread(target=_enrich, name=f"enrich-{key}", daemon=True).start()
        except Exception:
            pass

    def _mark_failed_in_queue(self, file_name: str) -> None:
        queue = self._load_queue()
        for item in queue:
            if item.get("file_name") == file_name:
                item["status"] = "failed"
                item["attempts"] = item.get("attempts", 0) + 1
                break
        self._save_queue(queue)

    def get_pending_items(self) -> list[dict]:
        with self._lock:
            queue = self._load_queue()
            return [item for item in queue if item.get("status") in ("pending", "failed")]

    def get_next_pending(self) -> dict | None:
        with self._lock:
            queue = self._load_queue()
            for item in queue:
                if item.get("status") == "pending":
                    return item
            # If no pending, try failed items
            for item in queue:
                if item.get("status") == "failed":
                    return item
            return None

    def _load_queue(self) -> list[dict]:
        queue_file = paths.queue_file()
        if not queue_file.is_file():
            return []
        try:
            return json.loads(queue_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _save_queue(self, queue: list[dict]) -> None:
        queue_file = paths.queue_file()
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(json.dumps(queue, indent=2, ensure_ascii=False))

    @classmethod
    def get_queue(cls) -> list[dict]:
        queue_file = paths.queue_file()
        if not queue_file.is_file():
            return []
        try:
            return json.loads(queue_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    @classmethod
    def clear_queue(cls) -> None:
        queue_file = paths.queue_file()
        if queue_file.is_file():
            queue_file.unlink()
