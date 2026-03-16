from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    _WATCHDOG_AVAILABLE = True
except Exception:  # pragma: no cover
    _WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = object  # type: ignore[assignment,misc]
    FileSystemEvent = object  # type: ignore[assignment,misc]


FILE_RULES: Dict[str, List[str]] = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "Videos": [".mp4", ".mkv", ".avi", ".mov"],
    "Documents": [
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".txt",
    ],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Installers": [".exe", ".msi"],
    "Code": [".py", ".js", ".ts", ".vue", ".json", ".html", ".css"],
    "Others": [],
}

TEMP_EXTENSIONS = {".crdownload", ".tmp", ".part"}


def classify_file(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    if ext in TEMP_EXTENSIONS:
        return None
    for category, exts in FILE_RULES.items():
        if exts and ext in exts:
            return category
    return "Others"


def _dedupe_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    i = 1
    while True:
        candidate = parent / f"{stem}({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _wait_for_file_ready(path: Path, *, stop_event: threading.Event, timeout_s: float = 30) -> bool:
    deadline = time.monotonic() + timeout_s
    last_size = None
    stable_since = None

    while time.monotonic() < deadline and not stop_event.is_set():
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        except OSError:
            stop_event.wait(0.2)
            continue

        size = stat.st_size
        if last_size == size:
            if stable_since is None:
                stable_since = time.monotonic()
            elif time.monotonic() - stable_since >= 1.0:
                try:
                    with path.open("rb"):
                        return True
                except OSError:
                    pass
        else:
            last_size = size
            stable_since = None

        stop_event.wait(0.2)

    return False


class _DownloadsEventHandler(FileSystemEventHandler):
    def __init__(self, *, downloads_path: Path, path_queue: "queue.Queue[Path]") -> None:
        self.downloads_path = downloads_path
        self.path_queue = path_queue

    def on_created(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        self._enqueue(event)

    def on_moved(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        self._enqueue(event, moved=True)

    def _enqueue(self, event: FileSystemEvent, *, moved: bool = False) -> None:
        try:
            if getattr(event, "is_directory", False):
                return
            raw_path = getattr(event, "dest_path" if moved else "src_path", None)
            if not raw_path:
                return
            path = Path(raw_path)
            if path.parent.resolve() != self.downloads_path.resolve():
                return
            self.path_queue.put_nowait(path)
        except Exception:
            return


class DownloadsOrganizer(threading.Thread):
    def __init__(
        self,
        *,
        downloads_path: Path,
        scan_interval: int,
        enabled_event: threading.Event,
        stop_event: threading.Event,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(name="DownloadsOrganizer", daemon=True)
        self.downloads_path = downloads_path
        self.scan_interval = max(30, int(scan_interval))
        self.enabled_event = enabled_event
        self.stop_event = stop_event
        self.logger = logger or logging.getLogger(__name__)

        self._path_queue: "queue.Queue[Path]" = queue.Queue()
        self._observer = None
        self._last_scan = 0.0
        self._manual_run_event = threading.Event()

    def request_organize_now(self) -> None:
        self._manual_run_event.set()

    def scan_once(self) -> None:
        if not self.downloads_path.exists():
            return
        try:
            for child in self.downloads_path.iterdir():
                if child.is_file():
                    self._path_queue.put_nowait(child)
        except Exception:
            self.logger.exception("Scan failed: %s", self.downloads_path)

    def run(self) -> None:
        self.logger.info("Downloads organizer started. Path=%s", self.downloads_path)
        self._start_watchdog()

        while not self.stop_event.is_set():
            if self._manual_run_event.is_set():
                self._manual_run_event.clear()
                self.logger.info("Manual organize requested")
                self.scan_once()
                self._drain_queue()
                continue

            if not self.enabled_event.is_set():
                self.stop_event.wait(0.2)
                continue

            now = time.monotonic()
            if now - self._last_scan >= self.scan_interval:
                self._last_scan = now
                self.scan_once()

            try:
                path = self._path_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._organize_path(path)
            except Exception:
                self.logger.exception("Failed to organize: %s", path)

        self._stop_watchdog()
        self.logger.info("Downloads organizer stopped")

    def _drain_queue(self) -> None:
        start = time.monotonic()
        while not self.stop_event.is_set():
            if time.monotonic() - start > 60:
                self.logger.info("Manual organize timed out after 60s")
                return
            try:
                path = self._path_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._organize_path(path)
            except Exception:
                self.logger.exception("Failed to organize: %s", path)

    def _start_watchdog(self) -> None:
        if not _WATCHDOG_AVAILABLE:
            self.logger.warning("watchdog not available; using periodic scanning only")
            return
        if not self.downloads_path.exists():
            return
        try:
            observer = Observer()
            handler = _DownloadsEventHandler(
                downloads_path=self.downloads_path, path_queue=self._path_queue
            )
            observer.schedule(handler, str(self.downloads_path), recursive=False)
            observer.start()
            self._observer = observer
            self.logger.info("watchdog observer started")
        except Exception:
            self.logger.exception("watchdog failed; using periodic scanning only")
            self._observer = None

    def _stop_watchdog(self) -> None:
        observer = self._observer
        self._observer = None
        if observer is None:
            return
        try:
            observer.stop()
            observer.join(timeout=5)
        except Exception:
            self.logger.exception("Failed to stop watchdog observer")

    def _organize_path(self, path: Path) -> None:
        if not path.exists():
            return
        if path.parent.resolve() != self.downloads_path.resolve():
            return
        if not path.is_file():
            return

        category = classify_file(path)
        if category is None:
            return

        dest_dir = self.downloads_path / category
        dest_dir.mkdir(parents=True, exist_ok=True)

        if not _wait_for_file_ready(path, stop_event=self.stop_event):
            return

        dest = _dedupe_destination(dest_dir / path.name)
        try:
            path.rename(dest)
            self.logger.info("Moved %s -> %s", path.name, dest)
        except Exception:
            self.logger.exception("Move failed: %s -> %s", path, dest)
