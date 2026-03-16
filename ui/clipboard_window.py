from __future__ import annotations

import logging
from typing import Optional

import pyperclip
import tkinter as tk
from tkinter import ttk

from core.database import Database


class ClipboardWindow:
    def __init__(
        self,
        *,
        root: tk.Tk,
        database: Database,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.root = root
        self.database = database
        self.logger = logger or logging.getLogger(__name__)

        self._window: Optional[tk.Toplevel] = None
        self._content_frame: Optional[ttk.Frame] = None

    def show(self) -> None:
        if self._window is not None and self._window.winfo_exists():
            self._window.deiconify()
            self._window.lift()
            self.refresh()
            return

        window = tk.Toplevel(self.root)
        window.title("Clipboard History (Latest 50)")
        window.geometry("700x500")
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        self._window = window

        toolbar = ttk.Frame(window)
        toolbar.pack(fill="x", padx=8, pady=8)
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left")

        container = ttk.Frame(window)
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        content_frame = ttk.Frame(canvas)
        self._content_frame = content_frame
        content_frame_id = canvas.create_window((0, 0), window=content_frame, anchor="nw")

        def _on_configure(event: tk.Event) -> None:  # type: ignore[type-arg]
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(content_frame_id, width=canvas.winfo_width())

        content_frame.bind("<Configure>", _on_configure)

        self.refresh()

    def refresh(self) -> None:
        if self._content_frame is None:
            return

        for child in list(self._content_frame.winfo_children()):
            child.destroy()

        try:
            entries = self.database.fetch_clipboard_history(limit=50)
        except Exception:
            self.logger.exception("Failed to read clipboard history")
            entries = []

        for entry in entries:
            created_at = entry.get("created_at") or ""
            content = entry.get("content") or ""
            preview = content.replace("\r\n", "\n").replace("\n", " ")
            if len(preview) > 200:
                preview = preview[:200] + "…"

            row = ttk.Frame(self._content_frame)
            row.pack(fill="x", pady=4)

            text = f"{created_at}  {preview}"
            label = ttk.Label(row, text=text, wraplength=560, justify="left")
            label.pack(side="left", fill="x", expand=True)

            ttk.Button(row, text="Copy", command=lambda c=content: self._copy(c)).pack(
                side="right"
            )

    def _copy(self, content: str) -> None:
        try:
            pyperclip.copy(content)
        except Exception:
            self.logger.exception("Failed to copy to clipboard")

