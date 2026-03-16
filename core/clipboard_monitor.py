from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Optional

import pyperclip

from core.database import Database


class ClipboardMonitor(threading.Thread):
    def __init__(
        self,
        *,
        database: Database,
        max_history: int,
        enabled_event: threading.Event,
        stop_event: threading.Event,
        poll_interval: float = 0.5,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(name="ClipboardMonitor", daemon=True)
        self.database = database
        self.max_history = max_history
        self.enabled_event = enabled_event
        self.stop_event = stop_event
        self.poll_interval = poll_interval
        self.logger = logger or logging.getLogger(__name__)

        self._last_hash: Optional[str] = None

    def run(self) -> None:
        self.logger.info("Clipboard monitor started")
        while not self.stop_event.is_set():
            if not self.enabled_event.is_set():
                self.stop_event.wait(0.2)
                continue

            text = self._safe_paste()
            if not text:
                self.stop_event.wait(self.poll_interval)
                continue

            if not text.strip():
                self.stop_event.wait(self.poll_interval)
                continue

            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if content_hash == self._last_hash:
                self.stop_event.wait(self.poll_interval)
                continue

            self._last_hash = content_hash

            try:
                self.database.add_clipboard_text(
                    text, max_history=self.max_history, content_hash=content_hash
                )
            except Exception:
                self.logger.exception("Failed to write clipboard to database")

            self.stop_event.wait(self.poll_interval)

        self.logger.info("Clipboard monitor stopped")

    def _safe_paste(self) -> Optional[str]:
        try:
            # 读取系统剪贴板
            text = pyperclip.paste()
        except pyperclip.PyperclipException:
            return None
        except Exception:
            self.logger.exception("Unexpected clipboard error")
            return None
        if isinstance(text, str):
            return text
        return None

