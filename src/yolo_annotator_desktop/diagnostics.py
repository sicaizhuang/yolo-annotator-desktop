from __future__ import annotations

from datetime import datetime
from pathlib import Path
import traceback
from tkinter import messagebox

from .safe_io import atomic_write_text


LOG_DIR = Path.home() / ".yolo_annotator_desktop_logs"
LOG_PATH = LOG_DIR / "app.log"
MAX_LOG_BYTES = 2_000_000


def append_exception(exc_type, exc_value, exc_traceback) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    existing = ""
    try:
        existing = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    if len(existing.encode("utf-8")) > MAX_LOG_BYTES:
        existing = existing[-500_000:]
    entry = (
        f"\n[{datetime.now().isoformat(timespec='seconds')}]\n"
        + "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    )
    atomic_write_text(LOG_PATH, existing + entry)
    return LOG_PATH


def install_tk_exception_handler(root) -> None:
    def report_callback_exception(exc_type, exc_value, exc_traceback):
        log_path = append_exception(exc_type, exc_value, exc_traceback)
        messagebox.showerror(
            "操作失败",
            f"软件遇到未预期错误，但数据写入使用安全模式。\n\n"
            f"{exc_value}\n\n详细日志：{log_path}",
            parent=root,
        )

    root.report_callback_exception = report_callback_exception
