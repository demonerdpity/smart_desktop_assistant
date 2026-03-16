from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
# GUI界面
import tkinter as tk

from core.clipboard_monitor import ClipboardMonitor
from core.config import DEFAULT_CONFIG, load_config
from core.database import Database
from core.organizer import DownloadsOrganizer
from ui.clipboard_window import ClipboardWindow
from ui.tray import create_tray_icon

# 检查程序是否被PyInstaller打包
def _is_frozen() -> bool:
    # 获取sys.frozen的值，默认为False，PyInstaller打包后，sys.frozen存在且为真
    return bool(getattr(sys, "frozen", False))

# 决定数据目录
def get_runtime_base_dir() -> Path:
    if _is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "SmartDesktopAssistant"
    return Path(__file__).resolve().parent


def setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "smart_desktop_assistant.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s"
    )
    # 日志超过1MB则切割
    file_handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# 核心控制类，
class AppController:
    def __init__(self, *, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.logs_dir = base_dir / "logs"
        self.config_path = base_dir / "config.json"
        self.db_path = self.data_dir / "smart.db"

        setup_logging(self.logs_dir)
        self.logger = logging.getLogger("app")
        '''
        threading.Event 实例,内部维护一个线程安全的布尔标志,常用方法/含义：
        e.is_set()：读当前 flag(True/False)
        e.set()：把 flag 置为 True,并唤醒所有在 wait() 的线程
        e.clear()：把 flag 置为 False
        e.wait(timeout=None)：如果 flag 已是 True 立即返回；否则阻塞等待直到 set() 或超时（返回 True 表示被 set 唤醒,False 表示超时）
        '''
        # 创建独立的事件对象，承担不同的状态信号
        # 全局关机信号
        self.stop_event = threading.Event()
        # 文件整理是否运行
        self.organizer_enabled = threading.Event()
        # 剪贴板监控是否运行
        self.clipboard_enabled = threading.Event()
        self.organizer_enabled.set()
        self.clipboard_enabled.set()

        self.config = load_config(self.config_path, defaults=DEFAULT_CONFIG)

        self.database = Database(self.db_path, logger=self.logger)
        self.database.init_db()

        self.downloads_path = Path(self.config["downloads_path"])

        # 创建文件整理线程
        self.organizer = DownloadsOrganizer(
            downloads_path=self.downloads_path,
            scan_interval=int(self.config["scan_interval"]),
            enabled_event=self.organizer_enabled,
            stop_event=self.stop_event,
            logger=logging.getLogger("organizer"),
        )
        # 剪贴板监控线程
        self.clipboard_monitor = ClipboardMonitor(
            database=self.database,
            max_history=int(self.config["max_clipboard_history"]),
            enabled_event=self.clipboard_enabled,
            stop_event=self.stop_event,
            logger=logging.getLogger("clipboard"),
        )
        # 创建GUI
        self.root = tk.Tk()
        self.root.withdraw()
        self.clipboard_window = ClipboardWindow(
            root=self.root,
            database=self.database,
            logger=logging.getLogger("clipboard_window"),
        )
        # 创建系统托盘图标(包括右键之后的各个选项)
        self.icon = create_tray_icon(self)

    def run(self) -> None:
        self.logger.info("Smart Desktop Assistant starting. Base dir=%s", self.base_dir)
        if not self.downloads_path.exists():
            self.logger.warning("Downloads path does not exist: %s", self.downloads_path)

        self.organizer.start()
        self.clipboard_monitor.start()

        self.icon.run_detached()

        try:
            # GUI主循环
            self.root.mainloop()
        finally:
            self.stop()

    def stop(self) -> None:
        if self.stop_event.is_set():
            return
        self.logger.info("Stopping Smart Desktop Assistant...")
        self.stop_event.set()
        try:
            # 停止托盘
            self.icon.stop()
        except Exception:
            self.logger.exception("Failed to stop tray icon")

        self.organizer.join(timeout=5) # 最多等 5 秒让该线程退出并结束运行，然后主线程继续往下走（不无限卡住）
        self.clipboard_monitor.join(timeout=5)

        try:
            # 关闭GUI
            self.root.destroy()
        except Exception:
            pass

    # 退出 Tkinter 主循环
    def exit_app(self) -> None:
        self.root.after(0, self.root.quit)
    # 立即整理文件
    def organize_now(self) -> None:
        self.organizer.request_organize_now()
    # 打开剪贴板历史
    def open_clipboard_history(self) -> None:
        self.root.after(0, self.clipboard_window.show) # 打开 GUI

    # 暂停文件整理
    def toggle_file_organizer(self) -> None:
        if self.organizer_enabled.is_set():
            self.organizer_enabled.clear()
            self.logger.info("File organizer paused")
        else:
            self.organizer_enabled.set()
            self.logger.info("File organizer resumed")

    # 暂停剪贴板监听
    def toggle_clipboard_monitor(self) -> None:
        if self.clipboard_enabled.is_set():
            self.clipboard_enabled.clear()
            self.logger.info("Clipboard monitor paused")
        else:
            self.clipboard_enabled.set()
            self.logger.info("Clipboard monitor resumed")

    # 打开日志文件夹
    def open_logs_folder(self) -> None:
        try:
            os.startfile(self.logs_dir) 
        except Exception:
            self.logger.exception("Failed to open logs folder: %s", self.logs_dir)

    def is_file_organizer_paused(self) -> bool:
        return not self.organizer_enabled.is_set()

    def is_clipboard_monitor_paused(self) -> bool:
        return not self.clipboard_enabled.is_set()


def main() -> None:
    controller = AppController(base_dir=get_runtime_base_dir())
    controller.run()


if __name__ == "__main__":
    main()
