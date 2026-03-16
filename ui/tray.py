from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw, ImageFont


if TYPE_CHECKING:  # pragma: no cover
    from app import AppController


def _load_icon_image() -> Image.Image:
    # Create a simple generated icon to avoid packaging issues.
    size = (64, 64)
    img = Image.new("RGBA", size, (28, 117, 188, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 63, 63), outline=(255, 255, 255, 255), width=2)
    try:
        font = ImageFont.load_default()
        draw.text((18, 20), "S", fill=(255, 255, 255, 255), font=font)
    except Exception:
        draw.text((18, 20), "S", fill=(255, 255, 255, 255))
    return img


def create_tray_icon(controller: "AppController") -> pystray.Icon:
    logger = logging.getLogger("tray")

    def on_organize_now(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        controller.organize_now()

    def on_open_history(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        controller.open_clipboard_history()

    def on_toggle_organizer(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        controller.toggle_file_organizer()

    def on_toggle_clipboard(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        controller.toggle_clipboard_monitor()

    def on_open_logs(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        controller.open_logs_folder()

    def on_exit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        try:
            controller.exit_app()
        except Exception:
            logger.exception("Exit failed")

    def organizer_pause_label(item: pystray.MenuItem) -> str:
        return (
            "Resume File Organizer"
            if controller.is_file_organizer_paused()
            else "Pause File Organizer"
        )

    def clipboard_pause_label(item: pystray.MenuItem) -> str:
        return (
            "Resume Clipboard Monitor"
            if controller.is_clipboard_monitor_paused()
            else "Pause Clipboard Monitor"
        )

    menu = pystray.Menu(
        pystray.MenuItem("Organize Downloads Now", on_organize_now),
        pystray.MenuItem("Open Clipboard History", on_open_history),
        pystray.MenuItem(
            organizer_pause_label,
            on_toggle_organizer,
            checked=lambda item: controller.is_file_organizer_paused(),
        ),
        pystray.MenuItem(
            clipboard_pause_label,
            on_toggle_clipboard,
            checked=lambda item: controller.is_clipboard_monitor_paused(),
        ),
        pystray.MenuItem("Open Logs Folder", on_open_logs),
        pystray.MenuItem("Exit", on_exit),
    )

    icon = pystray.Icon(
        "SmartDesktopAssistant",
        _load_icon_image(),
        "Smart Desktop Assistant",
        menu=menu,
    )
    return icon

