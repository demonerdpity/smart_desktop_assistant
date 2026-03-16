from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "downloads_path": r"C:\Users\admin\Downloads",
    "scan_interval": 600,
    "max_clipboard_history": 1000,
    "auto_start": True,
}


def load_config(config_path: Path, *, defaults: Dict[str, Any]) -> Dict[str, Any]:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        save_config(config_path, defaults)
        return dict(defaults)

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}

    merged = dict(defaults)
    if isinstance(raw, dict):
        merged.update(raw)

    if merged != raw:
        save_config(config_path, merged)
    return merged


def save_config(config_path: Path, config: Dict[str, Any]) -> None:
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

