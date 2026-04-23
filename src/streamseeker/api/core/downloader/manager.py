import json
import os
import threading

from tqdm.auto import tqdm

from streamseeker.api.core.helpers import Singleton

# Shared devnull stream — tqdm writes here so it never touches the terminal
_devnull = open(os.devnull, "w")


class DownloadManager(metaclass=Singleton):
    QUEUE_FILE = os.path.join("logs", "download_queue.json")

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
            self._remove_from_queue(file_name)

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
        if not os.path.isfile(self.QUEUE_FILE):
            return []
        try:
            with open(self.QUEUE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_queue(self, queue: list[dict]) -> None:
        os.makedirs(os.path.dirname(self.QUEUE_FILE), exist_ok=True)
        with open(self.QUEUE_FILE, "w") as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)

    @classmethod
    def get_queue(cls) -> list[dict]:
        if not os.path.isfile(cls.QUEUE_FILE):
            return []
        try:
            with open(cls.QUEUE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    @classmethod
    def clear_queue(cls) -> None:
        if os.path.isfile(cls.QUEUE_FILE):
            os.remove(cls.QUEUE_FILE)
