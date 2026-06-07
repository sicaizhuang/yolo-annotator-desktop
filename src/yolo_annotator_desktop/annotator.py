import argparse
import colorsys
import copy
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import uuid

from PIL import Image, ImageTk
from .label_formats import parse_label_line, serialize_annotation
from .project import label_path_for_image
from .safe_io import atomic_write_text
from .state import load_state, save_state
from .widgets import IconSet, fit_window, icon_button, set_app_icon


PROJECT = Path.cwd()
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
MAX_HISTORY = 200
IGNORED_DIR_NAMES = {".git", ".yad_backups", "__pycache__"}
REVIEW_TEXT = {"unreviewed": "未审核", "empty": "空图", "labeled": "已标注"}
STATUS_TEXT = {
    "selected": "已选中",
    "saved": "已保存",
    "auto-saved": "已自动保存",
    "rotated box auto-saved": "旋转框已自动保存",
    "moved auto-saved": "移动已自动保存",
    "resized auto-saved": "调整大小已自动保存",
    "class changed": "类别已修改",
    "deselected": "已取消选择",
    "nudged auto-saved": "微调已自动保存",
    "box copied": "已复制标注框",
    "box pasted": "已粘贴标注框",
    "reviewed empty": "已审核为空图",
    "undo auto-saved": "撤销已自动保存",
    "redo auto-saved": "重做已自动保存",
    "labels shown": "已显示标签文字",
    "labels hidden": "已隐藏标签文字",
    "smooth scaling on": "已启用平滑缩放",
    "pixel scaling on": "已启用像素缩放",
    "classes reloaded": "类别已重新加载",
    "next unreviewed": "已跳转到下一张未审核图片",
    "all images reviewed": "全部图片已审核",
    "project refreshed": "项目已刷新",
    "fit to window": "已适应窗口",
    "actual pixels": "实际像素 100%",
    "select and move mode": "选择与移动模式",
    "rectangle mode": "普通矩形框模式",
    "three-point rotated rectangle mode": "三点式旋转框模式",
    "no selected box": "未选中标注框",
    "class unchanged": "类别未变化",
    "no selected box to copy": "没有可复制的标注框",
    "box clipboard is empty": "标注框剪贴板为空",
    "nothing to undo": "没有可撤销的操作",
    "nothing to redo": "没有可重做的操作",
    "already at first image": "已经是第一张图片",
    "already at last image": "已经是最后一张图片",
    "no images match filter": "没有图片符合筛选条件",
    "no images": "没有图片",
    "rotated box must stay inside the image": "旋转框必须完整位于图片内",
    "move mouse to set width, then click": "移动鼠标确定宽度，然后单击完成",
}


def natural_sort_key(value):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(value))]


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


class Annotator:
    def __init__(
        self,
        root: tk.Tk,
        image_dir: Path,
        label_dir: Path,
        classes_path: Path,
        keep_empty: bool = False,
        order_file: Path | None = None,
        filter_order: bool = False,
        annotation_mode: str = "detect",
        keypoint_names: list[str] | None = None,
        project_name: str = "",
        project_path: Path | None = None,
    ):
        self.root = root
        set_app_icon(self.root)
        self.project_name = project_name or image_dir.name
        self.project_path = project_path
        self.lock_path = (
            project_path.with_name(f".{project_path.name}.lock")
            if project_path
            else label_dir.parent / ".yad.lock"
        )
        self.lock_token = ""
        self.image_dir = image_dir
        self.label_dir = label_dir
        self.classes_path = classes_path
        self.classes = [line.strip() for line in classes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.keep_empty = keep_empty
        self.order_file = order_file
        self.filter_order = filter_order
        self.images = self.find_images(image_dir, order_file, filter_order)
        self.all_images = list(self.images)
        self.image_status_cache = {}
        self.index = 0
        self.boxes = []
        self.preserved_label_lines = []
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.dirty = False
        self.backed_up_labels = set()
        self.session_backup_dir = (
            self.label_dir.parent / ".yad_backups" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        )
        self.labels_visible = True
        self.annotation_mode = annotation_mode
        self.keypoint_names = keypoint_names or []
        self.tool_mode = tk.StringVar(value=self.default_tool_for_mode(annotation_mode))
        self.image_filter = tk.StringVar(value="全部")
        self.image_search = tk.StringVar()
        self.class_search = tk.StringVar()
        self.visible_class_ids = []
        self.obb_baseline = None
        self.obb_preview = None
        self.polygon_points = []
        self.polygon_preview = None
        self.pose_next_keypoint = 0
        self.drag_start = None
        self.press_box_index = None
        self.resize_handle = None
        self.resize_history_recorded = False
        self.move_box_origin = None
        self.move_history_recorded = False
        self.preview_rect = None
        self.img = None
        self.tk_img = None
        self.render_cache_key = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.right_drag_start = None
        self.right_drag_origin = None
        self.right_drag_moved = False
        self.current_class = tk.IntVar(value=0)
        self.current_class.trace_add("write", lambda *_args: self.sync_class_selection())
        self.icons = IconSet(self.root)
        self.clipboard_box = None
        self.clipboard_image_size = None
        self.state = load_state()
        preferences = self.state.get("preferences", {})
        self.labels_visible = bool(preferences.get("show_labels", True))
        self.smooth_image = bool(preferences.get("smooth_image", True))
        self.image_browser_visible = bool(preferences.get("image_browser_visible", True))
        self.annotation_panel_visible = bool(preferences.get("annotation_panel_visible", True))
        self.autosave = bool(preferences.get("autosave", True))
        self.labels_visible_var = tk.BooleanVar(value=self.labels_visible)
        self.smooth_image_var = tk.BooleanVar(value=self.smooth_image)
        self.image_browser_visible_var = tk.BooleanVar(value=self.image_browser_visible)
        self.annotation_panel_visible_var = tk.BooleanVar(value=self.annotation_panel_visible)

        self.label_dir.mkdir(parents=True, exist_ok=True)
        self.root.title(f"YOLO Annotator Desktop - {self.project_name}")
        fit_window(self.root, (1380, 900), minimum=(880, 560), margin=(100, 160))

        if not self.acquire_project_lock():
            self.root.destroy()
            return
        self.build_menu()
        self.build_ui()
        self.bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if not self.images:
            messagebox.showerror("没有图片", f"图片目录中没有可用图片：\n{image_dir}")
        else:
            self.load_current()

    @staticmethod
    def find_images(image_dir: Path, order_file: Path | None = None, filter_order: bool = False):
        images = []
        for path in sorted(image_dir.rglob("*"), key=natural_sort_key):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            relative_parts = path.relative_to(image_dir).parts[:-1]
            if any(part.startswith(".") or part in IGNORED_DIR_NAMES for part in relative_parts):
                continue
            images.append(path)
        if order_file and order_file.exists():
            ordered_names = []
            for line in order_file.read_text(encoding="utf-8-sig").splitlines():
                name = line.split(",", 1)[0].strip().strip('"')
                if name and name.lower() != "image":
                    ordered_names.append(name.replace("\\", "/"))
            rank = {name: idx for idx, name in enumerate(ordered_names)}
            def image_rank(path):
                relative = path.relative_to(image_dir).as_posix()
                return rank.get(relative, rank.get(path.name, len(rank)))
            if filter_order:
                images = [path for path in images if image_rank(path) < len(rank)]
            images.sort(key=lambda path: (image_rank(path), path.as_posix()))
        return images

    def refresh_class_controls(self):
        if not hasattr(self, "class_list"):
            return
        self.class_list.delete(0, tk.END)
        query = self.class_search.get().strip().lower()
        self.visible_class_ids = []
        for idx, name in enumerate(self.classes):
            if query and query not in name.lower() and query != str(idx + 1):
                continue
            self.visible_class_ids.append(idx)
            self.class_list.insert(tk.END, f"{idx + 1}. {name}")
        self.sync_class_selection()

    def sync_class_selection(self):
        if not hasattr(self, "class_list"):
            return
        idx = int(self.current_class.get())
        try:
            visible_index = self.visible_class_ids.index(idx)
        except ValueError:
            self.class_list.selection_clear(0, tk.END)
            return
        current = self.class_list.curselection()
        if current and current[0] == visible_index:
            return
        self.class_list.selection_clear(0, tk.END)
        if 0 <= visible_index < self.class_list.size():
            self.class_list.selection_set(visible_index)
            self.class_list.see(visible_index)

    def on_select_class(self, _event=None):
        selection = self.class_list.curselection()
        if selection:
            class_id = self.visible_class_ids[selection[0]]
            if self.current_class.get() != class_id:
                self.current_class.set(class_id)

    def bind_keys(self):
        self.root.bind("<Control-n>", self.shortcut(self.open_project_hub))
        self.root.bind("<Control-o>", self.shortcut(self.open_project_dialog))
        self.root.bind("<Control-s>", self.shortcut(self.save_labels))
        self.root.bind("<Control-z>", self.shortcut(self.undo))
        self.root.bind("<Control-y>", self.shortcut(self.redo))
        self.root.bind("<Control-c>", self.shortcut(self.copy_selected))
        self.root.bind("<Control-v>", self.shortcut(self.paste_box))
        self.root.bind("<Control-d>", self.shortcut(self.duplicate_selected))
        self.root.bind("<Left>", self.shortcut(lambda: self.handle_arrow(-1, 0)))
        self.root.bind("<Right>", self.shortcut(lambda: self.handle_arrow(1, 0)))
        self.root.bind("<Up>", self.shortcut(lambda: self.handle_arrow(0, -1)))
        self.root.bind("<Down>", self.shortcut(lambda: self.handle_arrow(0, 1)))
        self.root.bind("<Shift-Left>", self.shortcut(lambda: self.handle_arrow(-10, 0)))
        self.root.bind("<Shift-Right>", self.shortcut(lambda: self.handle_arrow(10, 0)))
        self.root.bind("<Shift-Up>", self.shortcut(lambda: self.handle_arrow(0, -10)))
        self.root.bind("<Shift-Down>", self.shortcut(lambda: self.handle_arrow(0, 10)))
        self.root.bind("a", self.shortcut(self.prev_image))
        self.root.bind("d", self.shortcut(self.next_image))
        self.root.bind("h", self.shortcut(self.toggle_labels))
        self.root.bind("c", self.shortcut(self.set_selected_class))
        self.root.bind("u", self.shortcut(self.next_unreviewed))
        self.root.bind("n", self.shortcut(self.mark_reviewed_empty))
        self.root.bind("v", self.shortcut(lambda: self.set_tool_mode("select")))
        self.root.bind("b", self.shortcut(lambda: self.set_tool_mode("aabb")))
        self.root.bind("r", self.shortcut(lambda: self.set_tool_mode("obb")))
        self.root.bind("p", self.shortcut(lambda: self.set_tool_mode("polygon")))
        self.root.bind("k", self.shortcut(lambda: self.set_tool_mode("keypoint")))
        self.root.bind("<Return>", self.shortcut(self.finish_polygon))
        self.root.bind("f", self.shortcut(self.reset_view))
        self.root.bind("<Control-g>", self.shortcut(self.jump_dialog))
        self.root.bind("<Control-Key-0>", self.shortcut(self.reset_view))
        self.root.bind("<Control-Key-1>", self.shortcut(self.zoom_actual_pixels))
        self.root.bind("<F1>", self.shortcut(self.show_controls))
        self.root.bind("<F5>", self.shortcut(self.refresh_project))
        self.root.bind("<Escape>", self.shortcut(self.clear_selection))
        self.root.bind("<Delete>", self.shortcut(self.delete_selected))
        self.canvas.bind("<Button-4>", lambda event: self.on_linux_wheel(event, 120))
        self.canvas.bind("<Button-5>", lambda event: self.on_linux_wheel(event, -120))
        for idx in range(min(9, len(self.classes))):
            self.root.bind(str(idx + 1), self.shortcut(lambda i=idx: self.current_class.set(i)))
        if sys.platform == "darwin":
            for sequence, action in (
                ("<Command-n>", self.open_project_hub),
                ("<Command-o>", self.open_project_dialog),
                ("<Command-s>", self.save_labels),
                ("<Command-z>", self.undo),
                ("<Command-y>", self.redo),
                ("<Command-c>", self.copy_selected),
                ("<Command-v>", self.paste_box),
                ("<Command-d>", self.duplicate_selected),
                ("<Command-g>", self.jump_dialog),
                ("<Command-Key-0>", self.reset_view),
                ("<Command-Key-1>", self.zoom_actual_pixels),
            ):
                self.root.bind(sequence, self.shortcut(action))

    def shortcut(self, action):
        def handler(event=None):
            focus = self.root.focus_get()
            if focus is not None and focus.winfo_class() in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}:
                return None
            action()
            return "break"

        return handler

    def on_close(self):
        if self.dirty:
            if self.autosave:
                self.save_labels(silent=True)
            else:
                decision = messagebox.askyesnocancel(
                    "保存修改",
                    "当前图片有尚未保存的修改。关闭前保存吗？",
                    parent=self.root,
                )
                if decision is None:
                    return
                if decision:
                    self.save_labels(silent=True)
        self.release_project_lock()
        self.root.destroy()

    def acquire_project_lock(self):
        self.lock_token = uuid.uuid4().hex
        payload = {
            "token": self.lock_token,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "opened": datetime.now().isoformat(timespec="seconds"),
            "project": self.project_name,
        }
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.lock_path.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            return True
        except FileExistsError:
            try:
                existing = self.lock_path.read_text(encoding="utf-8-sig", errors="replace")
                existing_payload = json.loads(existing)
            except OSError:
                existing = "无法读取锁信息"
                existing_payload = {}
            except (ValueError, TypeError):
                existing_payload = {}
            if (
                existing_payload.get("host") == socket.gethostname()
                and isinstance(existing_payload.get("pid"), int)
                and not process_is_running(existing_payload["pid"])
            ):
                try:
                    self.lock_path.unlink()
                    with self.lock_path.open("x", encoding="utf-8") as stream:
                        json.dump(payload, stream, ensure_ascii=False, indent=2)
                        stream.write("\n")
                    return True
                except OSError:
                    pass
            if not messagebox.askyesno(
                "项目可能已在编辑",
                "检测到该项目的编辑锁。另一个窗口可能正在编辑同一批标签。\n\n"
                f"{existing}\n"
                "仍然强制打开吗？同时保存可能互相覆盖。",
                parent=self.root,
            ):
                return False
            self.lock_token = ""
            return True

    def release_project_lock(self):
        if not self.lock_token or not self.lock_path.exists():
            return
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8-sig"))
            if payload.get("token") == self.lock_token:
                self.lock_path.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            return

    def current_image_path(self):
        return self.images[self.index]

    def current_label_path(self):
        return self.label_path_for(self.current_image_path())

    def label_path_for(self, image_path):
        return label_path_for_image(image_path, self.image_dir, self.label_dir)

    def load_current(self):
        path = self.current_image_path()
        try:
            with Image.open(path) as source:
                self.img = source.convert("RGB")
        except OSError as exc:
            self.img = None
            self.boxes = []
            self.selected = None
            self.update_list()
            self.refresh_image_browser()
            self.redraw()
            self.update_info(f"无法打开图片：{exc}")
            return
        self.render_cache_key = None
        self.boxes = self.load_labels()
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.obb_baseline = None
        self.polygon_points = []
        self.polygon_preview = None
        self.pose_next_keypoint = 0
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update_list()
        self.redraw()
        self.refresh_image_browser()
        self.update_info()

    def load_labels(self):
        label_path = self.current_label_path()
        self.preserved_label_lines = []
        if not label_path.exists() or self.img is None:
            return []
        boxes = []
        for line in label_path.read_text(encoding="utf-8-sig").splitlines():
            parsed, _error = parse_label_line(
                line,
                mode=getattr(self, "annotation_mode", "detect"),
                class_count=len(self.classes),
                image_size=self.img.size,
            )
            if parsed is None:
                self.preserved_label_lines.append(line)
                continue
            boxes.append(parsed)
        return boxes

    def save_labels(self, silent=False):
        if self.img is None or not self.images:
            return
        if self.dirty:
            self.backup_current_label()
        size = self.img.size
        lines = []
        keypoint_count = len(getattr(self, "keypoint_names", []))
        for box in self.boxes:
            line = serialize_annotation(box, size, expected_keypoints=keypoint_count)
            if line:
                lines.append(line)
        lines.extend(self.preserved_label_lines)
        label_path = self.current_label_path()
        if lines:
            atomic_write_text(label_path, "\n".join(lines) + "\n")
        elif self.keep_empty or (label_path.exists() and not label_path.read_text(encoding="utf-8-sig", errors="ignore").strip()):
            atomic_write_text(label_path, "")
        elif label_path.exists():
            label_path.unlink()
        self.dirty = False
        if not silent:
            self.update_info("saved")
        self.image_status_cache.pop(str(self.current_image_path().resolve()), None)
        self.refresh_image_browser()

    def backup_current_label(self):
        label = self.current_label_path()
        key = str(label.resolve())
        if key in self.backed_up_labels:
            return
        self.backed_up_labels.add(key)
        if not label.exists():
            return
        try:
            relative = label.resolve().relative_to(self.label_dir.resolve())
        except ValueError:
            relative = Path(label.name)
        target = self.session_backup_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(label, target)

    def autosave_labels(self, status="auto-saved"):
        if self.autosave:
            self.save_labels(silent=True)
        translated = STATUS_TEXT.get(status, status)
        self.update_info(translated if self.autosave else f"{translated}；尚未保存，请按 Ctrl+S")

    def update_info(self, status=""):
        if not self.images:
            self.info.config(text="没有图片")
            return
        path = self.current_image_path()
        status = STATUS_TEXT.get(status, status)
        suffix = f" | {status}" if status else ""
        dimensions = f"{self.img.width}x{self.img.height}" if self.img else ""
        review, _count = self.image_review_status(path)
        text = (
            f"{self.index + 1}/{len(self.images)}  {path.name}  {dimensions}  "
            f"框={len(self.boxes)}  缩放={self.zoom:.2f}x  状态={REVIEW_TEXT.get(review, review)}{suffix}"
        )
        if self.preserved_label_lines:
            text += f"  | 已保留异常标签行={len(self.preserved_label_lines)}"
        self.info.config(text=text)

    def redraw(self):
        self.canvas.delete("all")
        if self.img is None:
            return
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        iw, ih = self.img.size
        fit_scale = min(cw / iw, ch / ih)
        self.scale = fit_scale * self.zoom
        disp_w = max(1, int(iw * self.scale))
        disp_h = max(1, int(ih * self.scale))
        self.offset_x = (cw - disp_w) / 2 + self.pan_x
        self.offset_y = (ch - disp_h) / 2 + self.pan_y

        cache_key = (id(self.img), disp_w, disp_h, self.smooth_image)
        if cache_key != self.render_cache_key or self.tk_img is None:
            resampling = Image.Resampling.LANCZOS if self.smooth_image else Image.Resampling.NEAREST
            resized = self.img.resize((disp_w, disp_h), resampling)
            self.tk_img = ImageTk.PhotoImage(resized)
            self.render_cache_key = cache_key
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.tk_img)

        for idx, box in enumerate(self.boxes):
            self.draw_box(box, selected=(idx == self.selected))
        if self.obb_baseline is not None and self.obb_preview is not None:
            points = [self.image_to_canvas(x, y) for x, y in self.obb_preview]
            self.canvas.create_polygon(*[value for point in points for value in point], outline="#ffffff", fill="", dash=(5, 4), width=2)
        if self.polygon_points:
            points = [self.image_to_canvas(x, y) for x, y in self.polygon_points]
            if self.polygon_preview is not None:
                points.append(self.image_to_canvas(*self.polygon_preview))
            flat = [value for point in points for value in point]
            if len(points) >= 2:
                self.canvas.create_line(*flat, fill="#ffffff", dash=(5, 4), width=2)
            for hx, hy in [self.image_to_canvas(x, y) for x, y in self.polygon_points]:
                self.canvas.create_oval(hx - 4, hy - 4, hx + 4, hy + 4, fill="#ffffff", outline="#222222")

    def image_to_canvas(self, x, y):
        return self.offset_x + x * self.scale, self.offset_y + y * self.scale

    def canvas_to_image(self, x, y):
        if self.img is None:
            return 0, 0
        iw, ih = self.img.size
        ix = (x - self.offset_x) / self.scale
        iy = (y - self.offset_y) / self.scale
        return max(0, min(iw, ix)), max(0, min(ih, iy))

    def draw_box(self, box, selected=False):
        color = "#ff3030" if selected else self.color_for_class(box["cls"])
        if box.get("kind") == "classify":
            if self.labels_visible:
                self.draw_label(8, 8, f"Image: {self.classes[box['cls']]}", color)
            return
        if box.get("kind") == "polygon":
            points = [self.image_to_canvas(x, y) for x, y in box["points"]]
            flat = [value for point in points for value in point]
            self.canvas.create_polygon(*flat, outline=color, fill="", width=3 if selected else 2)
            if self.labels_visible and points:
                label_x, label_y = min(points, key=lambda point: (point[1], point[0]))
                self.draw_label(label_x, label_y, self.classes[box["cls"]], color)
            if selected:
                for hx, hy in points:
                    self.canvas.create_oval(hx - 5, hy - 5, hx + 5, hy + 5, fill="#ffffff", outline="#ff3030", width=2)
            return
        if box.get("kind", "aabb") == "obb":
            points = [self.image_to_canvas(x, y) for x, y in box["points"]]
            flat = [value for point in points for value in point]
            self.canvas.create_polygon(*flat, outline=color, fill="", width=3 if selected else 2)
            label_x, label_y = min(points, key=lambda point: (point[1], point[0]))
            if self.labels_visible:
                self.draw_label(label_x, label_y, self.classes[box["cls"]], color)
            if selected:
                for hx, hy in points:
                    self.canvas.create_oval(hx - 5, hy - 5, hx + 5, hy + 5, fill="#ffffff", outline="#ff3030", width=2)
            return
        x1, y1 = self.image_to_canvas(box["x1"], box["y1"])
        x2, y2 = self.image_to_canvas(box["x2"], box["y2"])
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3 if selected else 2)
        if self.labels_visible:
            self.draw_label(x1, y1, self.classes[box["cls"]], color)
        if selected:
            for _name, hx, hy in self.resize_handle_positions(box):
                size = 5
                self.canvas.create_rectangle(
                    hx - size,
                    hy - size,
                    hx + size,
                    hy + size,
                    fill="#ffffff",
                    outline="#ff3030",
                    width=2,
                )
        if box.get("kind") == "pose":
            for idx, (kx, ky, visible) in enumerate(box.get("keypoints", [])):
                if not visible:
                    continue
                cx, cy = self.image_to_canvas(kx, ky)
                radius = 5 if selected else 4
                self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill="#ffffff", outline=color, width=2)
                if self.labels_visible:
                    name = self.keypoint_names[idx] if idx < len(self.keypoint_names) else str(idx + 1)
                    self.canvas.create_text(cx + 7, cy - 7, text=name, fill=color, anchor=tk.SW)

    def draw_label(self, x, y, text, background):
        above = y >= 24
        text_id = self.canvas.create_text(
            x + 4,
            y - 3 if above else y + 3,
            anchor=tk.SW if above else tk.NW,
            fill=self.contrast_text_color(background),
            text=text,
            width=max(40, self.canvas.winfo_width() - 12),
        )
        bounds = self.canvas.bbox(text_id)
        if bounds:
            canvas_width = max(1, self.canvas.winfo_width())
            canvas_height = max(1, self.canvas.winfo_height())
            dx = min(0, canvas_width - bounds[2] - 4)
            dy = min(0, canvas_height - bounds[3] - 4)
            if bounds[0] + dx < 4:
                dx += 4 - (bounds[0] + dx)
            if bounds[1] + dy < 4:
                dy += 4 - (bounds[1] + dy)
            if dx or dy:
                self.canvas.move(text_id, dx, dy)
                bounds = self.canvas.bbox(text_id)
            rectangle = self.canvas.create_rectangle(
                bounds[0] - 3,
                bounds[1] - 2,
                bounds[2] + 3,
                bounds[3] + 2,
                fill=background,
                outline=background,
            )
            self.canvas.tag_lower(rectangle, text_id)

    @staticmethod
    def contrast_text_color(background):
        value = background.lstrip("#")
        red, green, blue = (int(value[idx : idx + 2], 16) for idx in (0, 2, 4))
        luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255
        return "#111111" if luminance >= 0.58 else "#ffffff"

    @staticmethod
    def color_for_class(class_id):
        hue = (class_id * 0.61803398875 + 0.38) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(hue, 0.72, 0.95)
        return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"

    def resize_handle_positions(self, box):
        x1, y1 = self.image_to_canvas(box["x1"], box["y1"])
        x2, y2 = self.image_to_canvas(box["x2"], box["y2"])
        xm = (x1 + x2) / 2
        ym = (y1 + y2) / 2
        return [
            ("nw", x1, y1),
            ("n", xm, y1),
            ("ne", x2, y1),
            ("e", x2, ym),
            ("se", x2, y2),
            ("s", xm, y2),
            ("sw", x1, y2),
            ("w", x1, ym),
        ]

    def find_resize_handle(self, canvas_x, canvas_y):
        if self.selected is None or not (0 <= self.selected < len(self.boxes)):
            return None
        selected_box = self.boxes[self.selected]
        if selected_box.get("kind") == "classify":
            return None
        if selected_box.get("kind", "aabb") == "obb":
            for idx, point in enumerate(selected_box["points"]):
                hx, hy = self.image_to_canvas(*point)
                if abs(canvas_x - hx) <= 9 and abs(canvas_y - hy) <= 9:
                    return f"obb:{idx}"
            return None
        if selected_box.get("kind") == "polygon":
            for idx, point in enumerate(selected_box["points"]):
                hx, hy = self.image_to_canvas(*point)
                if abs(canvas_x - hx) <= 9 and abs(canvas_y - hy) <= 9:
                    return f"polygon:{idx}"
            return None
        if selected_box.get("kind") == "pose":
            for idx, (kx, ky, visible) in enumerate(selected_box.get("keypoints", [])):
                if not visible:
                    continue
                hx, hy = self.image_to_canvas(kx, ky)
                if abs(canvas_x - hx) <= 9 and abs(canvas_y - hy) <= 9:
                    return f"keypoint:{idx}"
        for name, hx, hy in self.resize_handle_positions(selected_box):
            if abs(canvas_x - hx) <= 9 and abs(canvas_y - hy) <= 9:
                return name
        return None

    def find_box_at(self, ix, iy):
        if self.img is None:
            return None
        tolerance = max(3.0, 5.0 / max(self.scale, 0.01))
        matches = []
        for idx, box in enumerate(self.boxes):
            if box.get("kind") == "classify":
                continue
            if box.get("kind") == "polygon":
                if self.point_in_polygon(ix, iy, box["points"]):
                    area = abs(self.polygon_area(box["points"]))
                    matches.append((max(1.0, area), idx))
                continue
            if box.get("kind", "aabb") == "obb":
                if self.point_in_polygon(ix, iy, box["points"]):
                    area = abs(self.polygon_area(box["points"]))
                    matches.append((max(1.0, area), idx))
                continue
            x1 = min(box["x1"], box["x2"]) - tolerance
            y1 = min(box["y1"], box["y2"]) - tolerance
            x2 = max(box["x1"], box["x2"]) + tolerance
            y2 = max(box["y1"], box["y2"]) + tolerance
            if x1 <= ix <= x2 and y1 <= iy <= y2:
                area = max(1.0, abs((box["x2"] - box["x1"]) * (box["y2"] - box["y1"])))
                matches.append((area, idx))
        if not matches:
            return None
        matches.sort()
        return matches[0][1]

    @staticmethod
    def polygon_area(points):
        return sum(
            points[idx][0] * points[(idx + 1) % len(points)][1]
            - points[(idx + 1) % len(points)][0] * points[idx][1]
            for idx in range(len(points))
        ) / 2

    @staticmethod
    def point_in_polygon(x, y, points):
        inside = False
        previous = points[-1]
        for current in points:
            x1, y1 = previous
            x2, y2 = current
            if (y1 > y) != (y2 > y):
                crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                if x < crossing_x:
                    inside = not inside
            previous = current
        return inside

    def select_box(self, idx, status="selected"):
        if idx is None or not (0 <= idx < len(self.boxes)):
            self.clear_selection()
            return
        self.selected = idx
        self.current_class.set(self.boxes[idx]["cls"])
        self.update_list()
        self.redraw()
        self.update_info(status)

    def on_press(self, event):
        if self.img is None:
            return
        if self.tool_mode.get() == "polygon":
            ix, iy = self.canvas_to_image(event.x, event.y)
            if len(self.polygon_points) >= 3:
                first_x, first_y = self.polygon_points[0]
                if math.hypot(ix - first_x, iy - first_y) <= max(8.0, 10.0 / max(self.scale, 0.01)):
                    self.finish_polygon()
                    return
            self.polygon_points.append((ix, iy))
            self.polygon_preview = None
            self.update_info("Polygon point added. Press Enter or click the first point to finish.")
            self.redraw()
            return
        if self.tool_mode.get() == "keypoint":
            self.place_pose_keypoint(*self.canvas_to_image(event.x, event.y))
            return
        if self.tool_mode.get() == "obb" and self.obb_baseline is not None:
            points = self.make_obb_points(*self.obb_baseline, self.canvas_to_image(event.x, event.y))
            if points is not None:
                if any(
                    x < 0 or y < 0 or x > self.img.width or y > self.img.height
                    for x, y in points
                ):
                    self.update_info("rotated box must stay inside the image")
                    return
                self.record_history()
                self.boxes.append({"kind": "obb", "cls": int(self.current_class.get()), "points": points})
                self.selected = len(self.boxes) - 1
                self.obb_baseline = None
                self.obb_preview = None
                self.update_list()
                self.autosave_labels("rotated box auto-saved")
                self.redraw()
            return
        self.drag_start = self.canvas_to_image(event.x, event.y)
        self.resize_handle = self.find_resize_handle(event.x, event.y)
        self.resize_history_recorded = False
        self.move_history_recorded = False
        if self.resize_handle is not None:
            self.press_box_index = None
            return
        self.press_box_index = self.find_box_at(*self.drag_start)
        if self.tool_mode.get() == "select":
            if self.press_box_index is None:
                self.clear_selection()
                self.drag_start = None
                return
            self.select_box(self.press_box_index)
            self.move_box_origin = self.snapshot_boxes()
            return
        if self.preview_rect:
            self.canvas.delete(self.preview_rect)
            self.preview_rect = None

    def on_drag(self, event):
        if self.drag_start is None:
            return
        if self.tool_mode.get() == "select" and self.selected is not None and self.move_box_origin is not None:
            if not self.move_history_recorded:
                self.record_history()
                self.move_history_recorded = True
            ix, iy = self.canvas_to_image(event.x, event.y)
            dx, dy = ix - self.drag_start[0], iy - self.drag_start[1]
            original = self.move_box_origin[self.selected]
            self.boxes[self.selected] = self.offset_box(original, dx, dy)
            self.update_list()
            self.redraw()
            return
        if self.resize_handle is not None and self.selected is not None:
            if not self.resize_history_recorded:
                self.record_history()
                self.resize_history_recorded = True
            ix, iy = self.canvas_to_image(event.x, event.y)
            box = self.boxes[self.selected]
            handle = self.resize_handle
            if handle.startswith("obb:"):
                previous_points = copy.deepcopy(box["points"])
                self.resize_obb_corner(box, int(handle.split(":", 1)[1]), (ix, iy))
                if self.img and any(
                    x < 0 or y < 0 or x > self.img.width or y > self.img.height
                    for x, y in box["points"]
                ):
                    box["points"] = previous_points
                self.update_list()
                self.redraw()
                return
            if handle.startswith("polygon:"):
                point_index = int(handle.split(":", 1)[1])
                previous_points = copy.deepcopy(box["points"])
                box["points"][point_index] = (ix, iy)
                if self.img and (
                    ix < 0
                    or iy < 0
                    or ix > self.img.width
                    or iy > self.img.height
                    or abs(self.polygon_area(box["points"])) <= 1e-6
                ):
                    box["points"] = previous_points
                self.update_list()
                self.redraw()
                return
            if handle.startswith("keypoint:"):
                point_index = int(handle.split(":", 1)[1])
                keypoints = list(box.get("keypoints", []))
                if 0 <= point_index < len(keypoints):
                    _old_x, _old_y, visible = keypoints[point_index]
                    keypoints[point_index] = (ix, iy, visible or 2)
                    box["keypoints"] = keypoints
                self.update_list()
                self.redraw()
                return
            if "w" in handle:
                box["x1"] = min(ix, box["x2"] - 5)
            if "e" in handle:
                box["x2"] = max(ix, box["x1"] + 5)
            if "n" in handle:
                box["y1"] = min(iy, box["y2"] - 5)
            if "s" in handle:
                box["y2"] = max(iy, box["y1"] + 5)
            self.update_list()
            self.redraw()
            return
        x1, y1 = self.image_to_canvas(*self.drag_start)
        ix2, iy2 = self.canvas_to_image(event.x, event.y)
        x2, y2 = self.image_to_canvas(ix2, iy2)
        if self.preview_rect:
            self.canvas.delete(self.preview_rect)
        if self.tool_mode.get() == "obb":
            self.preview_rect = self.canvas.create_line(x1, y1, x2, y2, fill="#ffffff", dash=(5, 4), width=2, arrow=tk.BOTH)
        else:
            self.preview_rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ffffff", dash=(5, 4), width=2)

    def on_release(self, event):
        if self.drag_start is None:
            return
        if self.tool_mode.get() == "select":
            moved = self.move_history_recorded
            self.drag_start = None
            self.press_box_index = None
            self.move_box_origin = None
            self.move_history_recorded = False
            if moved:
                self.autosave_labels("moved auto-saved")
                self.update_list()
                self.redraw()
            return
        if self.resize_handle is not None:
            resized = self.resize_history_recorded
            self.drag_start = None
            self.press_box_index = None
            self.resize_handle = None
            self.resize_history_recorded = False
            if resized:
                self.autosave_labels("resized auto-saved")
                self.update_list()
                self.redraw()
            return
        x1, y1 = self.drag_start
        x2, y2 = self.canvas_to_image(event.x, event.y)
        press_box_index = self.press_box_index
        self.drag_start = None
        self.press_box_index = None
        if self.preview_rect:
            self.canvas.delete(self.preview_rect)
            self.preview_rect = None
        dragged = abs(x2 - x1) >= 5 and abs(y2 - y1) >= 5
        if press_box_index is not None and not dragged:
            self.select_box(press_box_index)
            return
        if not dragged:
            self.clear_selection()
            return
        if self.tool_mode.get() == "obb":
            self.obb_baseline = ((x1, y1), (x2, y2))
            self.obb_preview = None
            self.update_info("move mouse to set width, then click")
            self.redraw()
            return
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        self.record_history()
        kind = "pose" if self.annotation_mode == "pose" else "aabb"
        box = {"kind": kind, "cls": int(self.current_class.get()), "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        if kind == "pose":
            box["keypoints"] = [(0.0, 0.0, 0) for _idx in range(len(self.keypoint_names))]
        self.boxes.append(box)
        self.selected = len(self.boxes) - 1
        self.update_list()
        self.autosave_labels()
        self.redraw()

    def on_select_box(self, _event):
        selection = self.box_list.curselection()
        self.selected = selection[0] if selection else None
        if self.selected is not None and 0 <= self.selected < len(self.boxes):
            self.current_class.set(self.boxes[self.selected]["cls"])
        self.redraw()

    def on_right_press(self, event):
        self.right_drag_start = (event.x, event.y)
        self.right_drag_origin = (self.pan_x, self.pan_y)
        self.right_drag_moved = False

    def on_right_drag(self, event):
        if self.right_drag_start is None or self.right_drag_origin is None:
            return
        dx = event.x - self.right_drag_start[0]
        dy = event.y - self.right_drag_start[1]
        if abs(dx) >= 3 or abs(dy) >= 3:
            self.right_drag_moved = True
        self.pan_x = self.right_drag_origin[0] + dx
        self.pan_y = self.right_drag_origin[1] + dy
        self.redraw()

    def on_right_release(self, event):
        if self.img is None:
            return
        if not self.right_drag_moved:
            ix, iy = self.canvas_to_image(event.x, event.y)
            idx = self.find_box_at(ix, iy)
            if idx is not None:
                self.select_box(idx)
            else:
                self.clear_selection()
        self.right_drag_start = None
        self.right_drag_origin = None
        self.right_drag_moved = False

    def on_mouse_wheel(self, event):
        if self.img is None or event.delta == 0:
            return
        anchor_x, anchor_y = self.canvas_to_image(event.x, event.y)
        factor = 1.15 if event.delta > 0 else 1 / 1.15
        new_zoom = max(1.0, min(12.0, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-9:
            return
        self.zoom = new_zoom

        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        iw, ih = self.img.size
        new_scale = min(cw / iw, ch / ih) * self.zoom
        centered_x = (cw - iw * new_scale) / 2
        centered_y = (ch - ih * new_scale) / 2
        self.pan_x = event.x - anchor_x * new_scale - centered_x
        self.pan_y = event.y - anchor_y * new_scale - centered_y
        self.redraw()
        self.update_info()

    def on_linux_wheel(self, event, delta):
        event.delta = delta
        self.on_mouse_wheel(event)

    def on_motion(self, event):
        if self.tool_mode.get() == "polygon" and self.polygon_points:
            self.polygon_preview = self.canvas_to_image(event.x, event.y)
            self.redraw()
            return
        if self.tool_mode.get() != "obb" or self.obb_baseline is None:
            return
        self.obb_preview = self.make_obb_points(*self.obb_baseline, self.canvas_to_image(event.x, event.y))
        self.redraw()

    def finish_polygon(self):
        if self.tool_mode.get() != "polygon" or not self.polygon_points:
            return
        if len(self.polygon_points) < 3:
            self.polygon_points = []
            self.polygon_preview = None
            self.redraw()
            self.update_info("Polygon cancelled: at least 3 points are required.")
            return
        if abs(self.polygon_area(self.polygon_points)) <= 1e-6:
            self.update_info("Polygon is degenerate; move points before finishing.")
            return
        self.record_history()
        self.boxes.append({"kind": "polygon", "cls": int(self.current_class.get()), "points": list(self.polygon_points)})
        self.selected = len(self.boxes) - 1
        self.polygon_points = []
        self.polygon_preview = None
        self.update_list()
        self.autosave_labels("auto-saved")
        self.redraw()

    def place_pose_keypoint(self, ix, iy):
        if self.selected is None or not (0 <= self.selected < len(self.boxes)):
            self.update_info("Select a pose box before placing keypoints.")
            return
        box = self.boxes[self.selected]
        if box.get("kind") != "pose":
            self.update_info("Selected annotation is not a pose object.")
            return
        self.record_history()
        keypoints = list(box.get("keypoints", []))
        target_count = max(len(self.keypoint_names), len(keypoints), 1)
        while len(keypoints) < target_count:
            keypoints.append((0.0, 0.0, 0))
        index = self.pose_next_keypoint % target_count
        keypoints[index] = (ix, iy, 2)
        box["keypoints"] = keypoints
        self.pose_next_keypoint = (index + 1) % target_count
        self.update_list()
        self.autosave_labels("auto-saved")
        self.redraw()
        name = self.keypoint_names[index] if index < len(self.keypoint_names) else f"keypoint_{index + 1}"
        self.update_info(f"Placed {name}")

    @staticmethod
    def make_obb_points(start, end, cursor):
        ax, ay = start
        bx, by = end
        cx, cy = cursor
        dx = bx - ax
        dy = by - ay
        length = math.hypot(dx, dy)
        if length < 5:
            return None
        nx = -dy / length
        ny = dx / length
        distance = (cx - ax) * nx + (cy - ay) * ny
        if abs(distance) < 3:
            return None
        offset = (nx * distance, ny * distance)
        return [(ax, ay), (bx, by), (bx + offset[0], by + offset[1]), (ax + offset[0], ay + offset[1])]

    @staticmethod
    def resize_obb_corner(box, corner_index, target):
        points = box["points"]
        indices = [(corner_index + offset) % 4 for offset in range(4)]
        q0, q1, q2, q3 = [points[idx] for idx in indices]
        ux, uy = q1[0] - q0[0], q1[1] - q0[1]
        length = math.hypot(ux, uy)
        if length < 1e-6:
            return
        ux, uy = ux / length, uy / length
        vx, vy = -uy, ux
        old_vx, old_vy = q3[0] - q0[0], q3[1] - q0[1]
        if old_vx * vx + old_vy * vy < 0:
            vx, vy = -vx, -vy
        diagonal_x, diagonal_y = q2[0] - target[0], q2[1] - target[1]
        width = diagonal_x * ux + diagonal_y * uy
        height = diagonal_x * vx + diagonal_y * vy
        if abs(width) < 3 or abs(height) < 3:
            return
        resized = [
            target,
            (target[0] + ux * width, target[1] + uy * width),
            q2,
            (target[0] + vx * height, target[1] + vy * height),
        ]
        for idx, value in zip(indices, resized):
            points[idx] = value

    def set_tool_mode(self, mode):
        expected = self.default_tool_for_mode(self.annotation_mode)
        allowed = self.allowed_tools_for_mode(self.annotation_mode)
        if mode not in allowed and self.boxes:
            label = {
                "aabb": "YOLO Detect",
                "obb": "YOLO OBB",
                "polygon": "YOLO Segmentation",
                "keypoint": "YOLO Pose keypoints",
                "select": "Select",
            }.get(mode, mode)
            if not messagebox.askyesno(
                "标注类型不同",
                f"当前项目配置为 {self.annotation_mode} 标注。\n\n"
                f"绘制 {label} 框会混合标注格式，并阻止训练导出。仍然继续吗？",
                parent=self.root,
            ):
                self.tool_mode.set(expected)
                return
        self.tool_mode.set(mode)
        if hasattr(self, "canvas"):
            self.canvas.config(cursor="arrow" if mode == "select" else "crosshair")
        self.obb_baseline = None
        self.obb_preview = None
        if mode != "polygon":
            self.polygon_points = []
            self.polygon_preview = None
        self.drag_start = None
        self.move_box_origin = None
        self.redraw()
        if mode == "select":
            self.update_info("select and move mode")
            return
        base = {
            "aabb": STATUS_TEXT["rectangle mode"],
            "obb": STATUS_TEXT["three-point rotated rectangle mode"],
            "polygon": "Polygon segmentation mode",
            "keypoint": "Pose keypoint mode",
        }.get(mode, mode)
        warning = " | Warning: tool differs from project task" if mode not in allowed else ""
        self.update_info(base + warning)

    @staticmethod
    def default_tool_for_mode(mode):
        return {
            "detect": "aabb",
            "obb": "obb",
            "segment": "polygon",
            "pose": "aabb",
            "classify": "select",
        }.get(mode, "aabb")

    @staticmethod
    def allowed_tools_for_mode(mode):
        return {
            "detect": {"select", "aabb"},
            "obb": {"select", "obb"},
            "segment": {"select", "polygon"},
            "pose": {"select", "aabb", "keypoint"},
            "classify": {"select"},
        }.get(mode, {"select", "aabb"})

    def reset_view(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.redraw()
        self.update_info("fit to window")

    def zoom_actual_pixels(self):
        if self.img is None:
            return
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        fit_scale = min(canvas_width / self.img.width, canvas_height / self.img.height)
        self.zoom = max(1.0, min(12.0, 1.0 / fit_scale))
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.redraw()
        self.update_info("actual pixels")

    def open_project_hub(self):
        subprocess.Popen([sys.executable, "-m", "yolo_annotator_desktop", "--hub"])

    def set_selected_class(self):
        if self.annotation_mode == "classify":
            self.record_history()
            self.boxes = [{"kind": "classify", "cls": int(self.current_class.get())}]
            self.selected = 0
            self.update_list()
            self.autosave_labels("class changed")
            self.redraw()
            return
        if self.selected is None or not (0 <= self.selected < len(self.boxes)):
            self.update_info("no selected box")
            return
        new_class = int(self.current_class.get())
        if self.boxes[self.selected]["cls"] == new_class:
            self.update_info("class unchanged")
            return
        self.record_history()
        self.boxes[self.selected]["cls"] = new_class
        self.update_list()
        self.box_list.selection_clear(0, tk.END)
        self.box_list.selection_set(self.selected)
        self.box_list.see(self.selected)
        self.autosave_labels("class changed")
        self.redraw()

    def clear_selection(self):
        self.selected = None
        self.box_list.selection_clear(0, tk.END)
        self.redraw()
        self.update_info("deselected")

    def offset_box(self, box, dx, dy):
        shifted = copy.deepcopy(box)
        if self.img is None:
            return shifted
        if shifted.get("kind") == "classify":
            return shifted
        width, height = self.img.size
        if shifted.get("kind") in {"obb", "polygon"}:
            min_x = min(point[0] for point in shifted["points"])
            max_x = max(point[0] for point in shifted["points"])
            min_y = min(point[1] for point in shifted["points"])
            max_y = max(point[1] for point in shifted["points"])
        else:
            min_x, max_x = shifted["x1"], shifted["x2"]
            min_y, max_y = shifted["y1"], shifted["y2"]
        dx = max(-min_x, min(width - max_x, dx))
        dy = max(-min_y, min(height - max_y, dy))
        if shifted.get("kind") in {"obb", "polygon"}:
            shifted["points"] = [(x + dx, y + dy) for x, y in shifted["points"]]
        else:
            for key in ("x1", "x2"):
                shifted[key] += dx
            for key in ("y1", "y2"):
                shifted[key] += dy
            if shifted.get("kind") == "pose":
                shifted["keypoints"] = [
                    (x + dx, y + dy, visible) if visible else (x, y, visible)
                    for x, y, visible in shifted.get("keypoints", [])
                ]
        return shifted

    def handle_arrow(self, dx, dy):
        if self.selected is None or not (0 <= self.selected < len(self.boxes)):
            if dx < 0:
                self.prev_image()
            elif dx > 0:
                self.next_image()
            return
        self.record_history()
        self.boxes[self.selected] = self.offset_box(self.boxes[self.selected], dx, dy)
        self.update_list()
        self.autosave_labels("nudged auto-saved")
        self.redraw()

    def copy_selected(self):
        if self.selected is None or not (0 <= self.selected < len(self.boxes)):
            self.update_info("no selected box to copy")
            return
        self.clipboard_box = copy.deepcopy(self.boxes[self.selected])
        self.clipboard_image_size = self.img.size if self.img else None
        self.update_info("box copied")

    def paste_box(self):
        if self.clipboard_box is None:
            self.update_info("box clipboard is empty")
            return
        self.record_history()
        pasted = self.scale_box_to_current_image(self.clipboard_box, self.clipboard_image_size)
        self.boxes.append(self.offset_box(pasted, 10, 10))
        self.selected = len(self.boxes) - 1
        self.update_list()
        self.autosave_labels("box pasted")
        self.redraw()

    def duplicate_selected(self):
        self.copy_selected()
        if self.clipboard_box is not None:
            self.paste_box()

    def scale_box_to_current_image(self, box, source_size):
        scaled = copy.deepcopy(box)
        if self.img is None or not source_size or source_size == self.img.size:
            return scaled
        scale_x = self.img.width / source_size[0]
        scale_y = self.img.height / source_size[1]
        if scaled.get("kind") in {"obb", "polygon"}:
            scaled["points"] = [(x * scale_x, y * scale_y) for x, y in scaled["points"]]
        else:
            if scaled.get("kind") != "classify":
                scaled["x1"] *= scale_x
                scaled["x2"] *= scale_x
                scaled["y1"] *= scale_y
                scaled["y2"] *= scale_y
            if scaled.get("kind") == "pose":
                scaled["keypoints"] = [
                    (x * scale_x, y * scale_y, visible) if visible else (x, y, visible)
                    for x, y, visible in scaled.get("keypoints", [])
                ]
        return scaled

    def mark_reviewed_empty(self):
        if not self.images:
            return
        if self.preserved_label_lines:
            messagebox.showwarning(
                "标签包含异常行",
                "当前标签含有无法安全编辑的异常行。软件已保留原始内容；请先在质量检查中处理，避免误删数据。",
                parent=self.root,
            )
            return
        if self.boxes and not messagebox.askyesno(
            "标记为空图",
            "当前图片已有标注框。删除全部框并将图片标记为已审核空图吗？",
            parent=self.root,
        ):
            return
        if self.boxes:
            self.record_history()
        self.boxes = []
        self.selected = None
        self.backup_current_label()
        atomic_write_text(self.current_label_path(), "")
        self.dirty = False
        self.image_status_cache.pop(str(self.current_image_path().resolve()), None)
        self.update_list()
        self.refresh_image_browser()
        self.redraw()
        self.update_info("reviewed empty")

    def snapshot_boxes(self):
        return copy.deepcopy(self.boxes)

    def record_history(self):
        self.undo_stack.append(self.snapshot_boxes())
        if len(self.undo_stack) > MAX_HISTORY:
            del self.undo_stack[0]
        self.redo_stack.clear()
        self.dirty = True

    def restore_boxes(self, boxes, status):
        self.boxes = copy.deepcopy(boxes)
        self.dirty = True
        self.selected = None
        self.update_list()
        self.autosave_labels(status)
        self.redraw()

    def undo(self):
        if not self.undo_stack:
            self.update_info("nothing to undo")
            return
        self.redo_stack.append(self.snapshot_boxes())
        self.restore_boxes(self.undo_stack.pop(), "undo auto-saved")

    def redo(self):
        if not self.redo_stack:
            self.update_info("nothing to redo")
            return
        self.undo_stack.append(self.snapshot_boxes())
        self.restore_boxes(self.redo_stack.pop(), "redo auto-saved")

    def toggle_labels(self):
        self.labels_visible = not self.labels_visible
        self.labels_visible_var.set(self.labels_visible)
        self.state.setdefault("preferences", {})["show_labels"] = self.labels_visible
        save_state(self.state)
        self.redraw()
        self.update_info("labels shown" if self.labels_visible else "labels hidden")

    def toggle_smoothing(self):
        self.smooth_image = not self.smooth_image
        self.smooth_image_var.set(self.smooth_image)
        self.state.setdefault("preferences", {})["smooth_image"] = self.smooth_image
        save_state(self.state)
        self.render_cache_key = None
        self.redraw()
        self.update_info("smooth scaling on" if self.smooth_image else "pixel scaling on")

    def add_class(self):
        name = simpledialog.askstring("添加自定义类别", "新类别名称：", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.classes:
            messagebox.showinfo("类别已存在", f"类别“{name}”已经存在。", parent=self.root)
            return
        self.classes.append(name)
        atomic_write_text(self.classes_path, "\n".join(self.classes) + "\n")
        self.current_class.set(len(self.classes) - 1)
        self.refresh_class_controls()
        self.update_info(f"已添加类别：{name}")

    def manage_classes(self):
        from .class_manager import ClassManager

        ClassManager(self.root, self.project_config(), self.reload_classes)

    def reload_classes(self):
        self.classes = [
            line.strip()
            for line in self.classes_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        self.current_class.set(min(self.current_class.get(), max(0, len(self.classes) - 1)))
        self.refresh_class_controls()
        self.boxes = self.load_labels()
        self.selected = None
        self.update_list()
        self.redraw()
        self.update_info("classes reloaded")

    def delete_selected(self):
        if self.selected is None:
            self.update_info("no selected box")
            return
        if 0 <= self.selected < len(self.boxes):
            self.record_history()
            self.boxes.pop(self.selected)
            self.selected = None
            self.update_list()
            self.autosave_labels()
            self.redraw()

    def delete_all(self):
        if not self.boxes:
            return
        if messagebox.askyesno("删除全部标注框", "删除当前图片的全部标注框吗？"):
            self.record_history()
            self.boxes = []
            self.selected = None
            self.update_list()
            self.autosave_labels()
            self.redraw()

    def prev_image(self):
        if not self.images:
            return
        if self.index == 0:
            self.update_info("already at first image")
            return
        self.save_labels(silent=True)
        self.index -= 1
        self.load_current()

    def next_image(self):
        if not self.images:
            return
        if self.index == len(self.images) - 1:
            self.update_info("already at last image")
            return
        self.save_labels(silent=True)
        self.index += 1
        self.load_current()

    def next_unreviewed(self):
        if not self.images:
            return
        self.save_labels(silent=True)
        for offset in range(1, len(self.images) + 1):
            idx = (self.index + offset) % len(self.images)
            if not self.label_path_for(self.images[idx]).exists():
                self.index = idx
                self.load_current()
                self.update_info("next unreviewed")
                return
        self.update_info("all images reviewed")

    def build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="新建或导入数据集...", command=self.open_project_hub, accelerator="Ctrl+N")
        file_menu.add_command(label="打开项目...", command=self.open_project_dialog, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="打开图片目录", command=lambda: self.open_path(self.image_dir))
        file_menu.add_command(label="打开标签目录", command=lambda: self.open_path(self.label_dir))
        file_menu.add_command(label="打开类别文件", command=lambda: self.open_path(self.classes_path))
        file_menu.add_command(label="打开自动备份目录", command=self.open_backup_dir)
        file_menu.add_separator()
        file_menu.add_command(label="保存", command=self.save_labels, accelerator="Ctrl+S")
        file_menu.add_command(label="退出", command=self.on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="撤销", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="重做", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="复制选中框", command=self.copy_selected, accelerator="Ctrl+C")
        edit_menu.add_command(label="粘贴框", command=self.paste_box, accelerator="Ctrl+V")
        edit_menu.add_command(label="复制并偏移", command=self.duplicate_selected, accelerator="Ctrl+D")
        edit_menu.add_separator()
        edit_menu.add_command(label="设置选中框类别", command=self.set_selected_class, accelerator="C")
        edit_menu.add_command(label="删除选中框", command=self.delete_selected, accelerator="Delete")
        edit_menu.add_command(label="删除本图全部框", command=self.delete_all)
        edit_menu.add_separator()
        edit_menu.add_command(label="管理类别...", command=self.manage_classes)
        menubar.add_cascade(label="编辑", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="隐藏或显示标签", command=self.toggle_labels, accelerator="H")
        view_menu.add_command(label="隐藏或显示图片列表", command=self.toggle_image_browser)
        view_menu.add_command(label="隐藏或显示标注面板", command=self.toggle_annotation_panel)
        view_menu.add_command(label="适应窗口", command=self.reset_view, accelerator="Ctrl+0")
        view_menu.add_command(label="实际像素 100%", command=self.zoom_actual_pixels, accelerator="Ctrl+1")
        view_menu.add_separator()
        view_menu.add_command(label="上一张", command=self.prev_image, accelerator="A / Left")
        view_menu.add_command(label="下一张", command=self.next_image, accelerator="D / Right")
        view_menu.add_command(label="下一张未审核", command=self.next_unreviewed, accelerator="U")
        view_menu.add_command(label="跳转到图片...", command=self.jump_dialog, accelerator="Ctrl+G")
        menubar.add_cascade(label="视图", menu=view_menu)

        annotation_menu = tk.Menu(menubar, tearoff=False)
        annotation_menu.add_radiobutton(
            label="选择与移动",
            variable=self.tool_mode,
            value="select",
            command=lambda: self.set_tool_mode("select"),
            accelerator="V",
        )
        annotation_menu.add_radiobutton(
            label="普通矩形框",
            variable=self.tool_mode,
            value="aabb",
            command=lambda: self.set_tool_mode("aabb"),
            accelerator="B",
        )
        annotation_menu.add_radiobutton(
            label="三点式旋转框",
            variable=self.tool_mode,
            value="obb",
            command=lambda: self.set_tool_mode("obb"),
            accelerator="R",
        )
        annotation_menu.add_radiobutton(
            label="Polygon segmentation",
            variable=self.tool_mode,
            value="polygon",
            command=lambda: self.set_tool_mode("polygon"),
            accelerator="P",
        )
        annotation_menu.add_radiobutton(
            label="Pose keypoint",
            variable=self.tool_mode,
            value="keypoint",
            command=lambda: self.set_tool_mode("keypoint"),
            accelerator="K",
        )
        annotation_menu.add_separator()
        annotation_menu.add_command(label="标记为空图并完成审核", command=self.mark_reviewed_empty, accelerator="N")
        annotation_menu.add_separator()
        annotation_menu.add_command(label="添加自定义类别...", command=self.add_class)
        annotation_menu.add_command(label="管理类别...", command=self.manage_classes)
        menubar.add_cascade(label="标注", menu=annotation_menu)

        dataset_menu = tk.Menu(menubar, tearoff=False)
        dataset_menu.add_command(label="刷新图片与标签", command=self.refresh_project, accelerator="F5")
        dataset_menu.add_separator()
        dataset_menu.add_command(label="质量检查...", command=self.run_quality_check)
        dataset_menu.add_command(label="导出数据集...", command=self.export_dataset)
        dataset_menu.add_separator()
        dataset_menu.add_command(label="打开项目与数据集中心", command=self.open_project_hub)
        menubar.add_cascade(label="数据集", menu=dataset_menu)

        settings_menu = tk.Menu(menubar, tearoff=False)
        settings_menu.add_checkbutton(
            label="显示标签文字",
            variable=self.labels_visible_var,
            command=self.toggle_labels,
        )
        settings_menu.add_checkbutton(
            label="显示图片列表",
            variable=self.image_browser_visible_var,
            command=self.toggle_image_browser,
        )
        settings_menu.add_checkbutton(
            label="显示标注面板",
            variable=self.annotation_panel_visible_var,
            command=self.toggle_annotation_panel,
        )
        settings_menu.add_checkbutton(
            label="平滑缩放图片",
            variable=self.smooth_image_var,
            command=self.toggle_smoothing,
        )
        settings_menu.add_separator()
        settings_menu.add_command(label="恢复默认工作区布局", command=self.reset_workspace_layout)
        menubar.add_cascade(label="设置", menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="操作说明", command=self.show_controls, accelerator="F1")
        help_menu.add_command(
            label="打开错误日志目录",
            command=lambda: self.open_path(self.ensure_log_dir()),
        )
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menubar)

    def build_ui(self):
        top = tk.Frame(self.root, bd=1, relief=tk.GROOVE)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=5)

        self.add_toolbar_button(top, "folder", "打开项目 (Ctrl+O)", self.open_project_dialog)
        self.add_toolbar_button(top, "save", "保存标签 (Ctrl+S)", self.save_labels)
        self.add_toolbar_separator(top)
        self.add_toolbar_button(top, "select", "选择和移动标注框 (V)", lambda: self.set_tool_mode("select"), "select")
        self.add_toolbar_button(top, "rect", "普通矩形框 (B)", lambda: self.set_tool_mode("aabb"), "aabb")
        self.add_toolbar_button(top, "obb", "三点式旋转框 (R)", lambda: self.set_tool_mode("obb"), "obb")
        self.add_toolbar_button(top, "polygon", "多边形分割 (P)", lambda: self.set_tool_mode("polygon"), "polygon")
        self.add_toolbar_button(top, "keypoint", "姿态关键点 (K)", lambda: self.set_tool_mode("keypoint"), "keypoint")
        self.add_toolbar_separator(top)
        self.add_toolbar_button(top, "undo", "撤销 (Ctrl+Z)", self.undo)
        self.add_toolbar_button(top, "redo", "重做 (Ctrl+Y)", self.redo)
        self.add_toolbar_button(top, "eye_off", "隐藏或显示标签 (H)", self.toggle_labels)
        self.add_toolbar_button(top, "empty", "标记当前图片为空图并完成审核 (N)", self.mark_reviewed_empty)
        self.add_toolbar_separator(top)
        self.add_toolbar_button(top, "previous", "上一张 (A / 左方向键)", self.prev_image)
        self.add_toolbar_button(top, "next", "下一张 (D / 右方向键)", self.next_image)
        self.add_toolbar_button(top, "next_unreviewed", "下一张未审核 (U)", self.next_unreviewed)

        body = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=5, sashrelief=tk.RAISED, bd=0)
        body.pack(fill=tk.BOTH, expand=True)

        self.image_browser = tk.Frame(body, width=210, bd=1, relief=tk.GROOVE)
        self.build_image_browser(self.image_browser)
        body.add(self.image_browser, minsize=180, width=210, stretch="never")

        canvas_frame = tk.Frame(body)
        body.add(canvas_frame, minsize=320, stretch="always")

        self.canvas = tk.Canvas(canvas_frame, bg="#151515", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<ButtonPress-3>", self.on_right_press)
        self.canvas.bind("<B3-Motion>", self.on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_right_release)
        self.canvas.bind("<ButtonPress-2>", self.on_right_press)
        self.canvas.bind("<B2-Motion>", self.on_right_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_right_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())

        panel = tk.Frame(body, width=300)
        body.add(panel, minsize=240, width=300, stretch="never")
        panel.pack_propagate(False)
        self.panel = panel
        self.annotation_panel = panel
        self.body_panes = body

        class_header = tk.Frame(panel)
        class_header.pack(fill=tk.X)
        tk.Label(class_header, text="类别").pack(side=tk.LEFT, anchor="w")
        self.add_toolbar_button(class_header, "add", "添加自定义类别", self.add_class, padx=(8, 2))
        self.add_toolbar_button(class_header, "manage", "管理、重命名、删除或调整类别顺序", self.manage_classes)
        ttk.Entry(panel, textvariable=self.class_search).pack(fill=tk.X, pady=(4, 0))
        self.class_search.trace_add("write", lambda *_args: self.refresh_class_controls())
        class_list_frame = tk.Frame(panel)
        class_list_frame.pack(fill=tk.X, pady=(4, 0))
        class_scroll = ttk.Scrollbar(class_list_frame, orient=tk.VERTICAL)
        class_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.class_list = tk.Listbox(
            class_list_frame,
            height=8,
            exportselection=False,
            activestyle="none",
            yscrollcommand=class_scroll.set,
        )
        self.class_list.pack(fill=tk.X, expand=True)
        class_scroll.config(command=self.class_list.yview)
        self.class_list.bind("<<ListboxSelect>>", self.on_select_class)
        self.refresh_class_controls()

        tk.Label(panel, text="标注框").pack(anchor="w", pady=(12, 2))
        box_list_frame = tk.Frame(panel)
        box_list_frame.pack(fill=tk.BOTH, expand=True)
        box_y_scroll = ttk.Scrollbar(box_list_frame, orient=tk.VERTICAL)
        box_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        box_x_scroll = ttk.Scrollbar(box_list_frame, orient=tk.HORIZONTAL)
        box_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.box_list = tk.Listbox(
            box_list_frame,
            height=16,
            xscrollcommand=box_x_scroll.set,
            yscrollcommand=box_y_scroll.set,
        )
        self.box_list.pack(fill=tk.BOTH, expand=True)
        box_y_scroll.config(command=self.box_list.yview)
        box_x_scroll.config(command=self.box_list.xview)
        self.box_list.bind("<<ListboxSelect>>", self.on_select_box)

        box_actions = tk.Frame(panel)
        box_actions.pack(fill=tk.X, pady=(6, 2))
        self.add_toolbar_button(box_actions, "tag", "将选中框设置为当前类别 (C)", self.set_selected_class)
        self.add_toolbar_button(box_actions, "copy", "复制选中框 (Ctrl+C)，粘贴为 Ctrl+V", self.copy_selected)
        self.add_toolbar_button(box_actions, "trash", "删除选中框 (Delete)", self.delete_selected)
        self.add_toolbar_button(box_actions, "deselect", "取消选择 (Esc)", self.clear_selection)

        tk.Label(
            panel,
            text="选择/移动 V | 普通框 B | 旋转框 R | 滚轮缩放 | 右键拖动画面",
            justify=tk.LEFT,
            fg="#666666",
            wraplength=230,
        ).pack(anchor="w", pady=(8, 4))

        self.info = tk.Label(self.root, text="", anchor="w", bd=1, relief=tk.SUNKEN, padx=6)
        self.info.pack(side=tk.BOTTOM, fill=tk.X)
        if not self.image_browser_visible:
            self.root.after_idle(self.toggle_image_browser)
        if not self.annotation_panel_visible:
            self.root.after_idle(self.toggle_annotation_panel)

    def build_image_browser(self, parent):
        header = tk.Frame(parent)
        header.pack(fill=tk.X, padx=6, pady=(6, 3))
        tk.Label(header, text="图片", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.image_progress = tk.Label(header, text="", fg="#666666")
        self.image_progress.pack(side=tk.RIGHT)

        search = ttk.Entry(parent, textvariable=self.image_search)
        search.pack(fill=tk.X, padx=6, pady=3)
        self.image_search.trace_add("write", lambda *_args: self.apply_image_filter())
        ttk.Combobox(
            parent,
            textvariable=self.image_filter,
            values=("全部", "未审核", "已标注", "空图"),
            state="readonly",
        ).pack(fill=tk.X, padx=6, pady=(0, 5))
        self.image_filter.trace_add("write", lambda *_args: self.apply_image_filter())

        tree_frame = tk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        horizontal.pack(side=tk.BOTTOM, fill=tk.X)
        self.image_tree = ttk.Treeview(
            tree_frame,
            show="tree",
            selectmode="browse",
            yscrollcommand=scrollbar.set,
            xscrollcommand=horizontal.set,
        )
        self.image_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.image_tree.yview)
        horizontal.config(command=self.image_tree.xview)
        self.image_tree.bind("<<TreeviewSelect>>", self.on_image_tree_select)
        self.refresh_image_browser()

    def image_review_status(self, image):
        key = str(image.resolve())
        if key in self.image_status_cache:
            return self.image_status_cache[key]
        label = self.label_path_for(image)
        if not label.exists():
            result = ("unreviewed", 0)
            self.image_status_cache[key] = result
            return result
        text = label.read_text(encoding="utf-8-sig", errors="ignore").strip()
        if not text:
            result = ("empty", 0)
        else:
            result = ("labeled", len(text.splitlines()))
        self.image_status_cache[key] = result
        return result

    def refresh_image_browser(self):
        if not hasattr(self, "image_tree"):
            return
        selected_path = self.current_image_path().resolve() if self.images else None
        self.image_tree.delete(*self.image_tree.get_children())
        reviewed = 0
        for idx, image in enumerate(self.images):
            status, count = self.image_review_status(image)
            if status != "unreviewed":
                reviewed += 1
            marker = {"unreviewed": "○", "empty": "✓", "labeled": "●"}[status]
            suffix = "" if status == "unreviewed" else ("  空图" if status == "empty" else f"  {count}")
            try:
                name = str(image.relative_to(self.image_dir))
            except ValueError:
                name = image.name
            self.image_tree.insert("", tk.END, iid=str(idx), text=f"{marker} {name}{suffix}")
            if selected_path is not None and image.resolve() == selected_path:
                self.image_tree.selection_set(str(idx))
                self.image_tree.see(str(idx))
        self.image_progress.config(text=f"{reviewed}/{len(self.images)}")

    def apply_image_filter(self):
        if not hasattr(self, "image_tree"):
            return
        current = self.current_image_path().resolve() if self.images else None
        mode = {"全部": "all", "未审核": "unreviewed", "已标注": "labeled", "空图": "empty"}.get(
            self.image_filter.get(),
            "all",
        )
        query = self.image_search.get().strip().lower()
        filtered = []
        for image in self.all_images:
            status, _count = self.image_review_status(image)
            try:
                name = str(image.relative_to(self.image_dir)).lower()
            except ValueError:
                name = image.name.lower()
            if query and query not in name:
                continue
            if mode != "all" and status != mode:
                continue
            filtered.append(image)
        self.images = filtered
        if not self.images:
            self.index = 0
            self.img = None
            self.boxes = []
            self.update_list()
            self.refresh_image_browser()
            self.redraw()
            self.update_info("no images match filter")
            return
        matching = [idx for idx, image in enumerate(self.images) if current is not None and image.resolve() == current]
        self.index = matching[0] if matching else 0
        self.load_current()

    def on_image_tree_select(self, _event):
        selection = self.image_tree.selection()
        if not selection:
            return
        try:
            target = int(selection[0])
        except ValueError:
            return
        if target == self.index or not 0 <= target < len(self.images):
            return
        self.save_labels(silent=True)
        self.index = target
        self.load_current()

    def toggle_image_browser(self):
        if str(self.image_browser) in self.body_panes.panes():
            self.body_panes.forget(self.image_browser)
            self.image_browser_visible = False
        else:
            self.body_panes.add(
                self.image_browser,
                before=self.canvas.master,
                minsize=180,
                width=210,
                stretch="never",
            )
            self.image_browser_visible = True
        self.image_browser_visible_var.set(self.image_browser_visible)
        self.state.setdefault("preferences", {})["image_browser_visible"] = self.image_browser_visible
        save_state(self.state)

    def toggle_annotation_panel(self):
        if str(self.annotation_panel) in self.body_panes.panes():
            self.body_panes.forget(self.annotation_panel)
            self.annotation_panel_visible = False
        else:
            self.body_panes.add(self.annotation_panel, minsize=240, width=300, stretch="never")
            self.annotation_panel_visible = True
        self.annotation_panel_visible_var.set(self.annotation_panel_visible)
        self.state.setdefault("preferences", {})["annotation_panel_visible"] = self.annotation_panel_visible
        save_state(self.state)

    def reset_workspace_layout(self):
        if str(self.image_browser) not in self.body_panes.panes():
            self.toggle_image_browser()
        if str(self.annotation_panel) not in self.body_panes.panes():
            self.toggle_annotation_panel()
        if not self.labels_visible:
            self.toggle_labels()
        if not self.smooth_image:
            self.toggle_smoothing()
        self.reset_view()

    def add_toolbar_button(self, parent, icon, tooltip, command, mode=None, padx=2):
        options = {}
        if mode is not None:
            options = {"variable": self.tool_mode, "value": mode}
        button = icon_button(parent, self.icons.get(icon), tooltip, command, **options)
        button.pack(side=tk.LEFT, padx=padx, pady=2)
        return button

    @staticmethod
    def add_toolbar_separator(parent):
        tk.Frame(parent, width=1, bg="#bbbbbb").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=4)

    def update_list(self):
        self.box_list.delete(0, tk.END)
        for idx, box in enumerate(self.boxes):
            name = self.classes[box["cls"]]
            if box.get("kind") == "classify":
                self.box_list.insert(tk.END, f"{idx + 1}. Image class: {name}")
                continue
            if box.get("kind") == "polygon":
                center_x = round(sum(point[0] for point in box["points"]) / len(box["points"]))
                center_y = round(sum(point[1] for point in box["points"]) / len(box["points"]))
                self.box_list.insert(tk.END, f"{idx + 1}. Polygon {name} points={len(box['points'])} center=[{center_x},{center_y}]")
                continue
            if box.get("kind") == "pose":
                visible = sum(1 for _x, _y, flag in box.get("keypoints", []) if flag)
                x1, y1, x2, y2 = [round(box[key]) for key in ("x1", "y1", "x2", "y2")]
                self.box_list.insert(tk.END, f"{idx + 1}. Pose {name} kpts={visible}/{max(len(self.keypoint_names), len(box.get('keypoints', [])))} [{x1},{y1},{x2},{y2}]")
                continue
            if box.get("kind", "aabb") == "obb":
                center_x = round(sum(point[0] for point in box["points"]) / 4)
                center_y = round(sum(point[1] for point in box["points"]) / 4)
                self.box_list.insert(tk.END, f"{idx + 1}. ◇ {name}  中心=[{center_x},{center_y}]")
            else:
                x1, y1, x2, y2 = [round(box[key]) for key in ("x1", "y1", "x2", "y2")]
                self.box_list.insert(tk.END, f"{idx + 1}. □ {name}  [{x1},{y1},{x2},{y2}]")
        if self.selected is not None and 0 <= self.selected < len(self.boxes):
            self.box_list.selection_clear(0, tk.END)
            self.box_list.selection_set(self.selected)
            self.box_list.see(self.selected)

    def project_config(self):
        from .project import ProjectConfig

        return ProjectConfig(
            name=self.project_name,
            images=str(self.image_dir),
            labels=str(self.label_dir),
            classes=str(self.classes_path),
            keep_empty=self.keep_empty,
            order_file=str(self.order_file) if self.order_file else "",
            filter_order=self.filter_order,
            annotation_mode=self.annotation_mode,
            keypoints=", ".join(self.keypoint_names),
            config_path=self.project_path,
        )

    def refresh_project(self):
        self.save_labels(silent=True)
        current = self.current_image_path().resolve() if self.images else None
        self.all_images = self.find_images(self.image_dir, self.order_file, self.filter_order)
        self.image_status_cache.clear()
        self.classes = [
            line.strip()
            for line in self.classes_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        self.refresh_class_controls()
        self.images = list(self.all_images)
        matching = [idx for idx, image in enumerate(self.images) if current is not None and image.resolve() == current]
        self.index = matching[0] if matching else 0
        if self.images:
            self.load_current()
            self.update_info("project refreshed")
        else:
            self.img = None
            self.boxes = []
            self.update_list()
            self.refresh_image_browser()
            self.redraw()
            self.update_info("no images")

    def open_project_dialog(self):
        from .project import load_project

        path = filedialog.askopenfilename(
            parent=self.root,
            title="打开 YOLO Annotator Desktop 项目",
            filetypes=[("YAD 项目", "*.yad.json"), ("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            project = load_project(path)
            errors = project.validate()
            if errors:
                raise ValueError("\n".join(errors))
            subprocess.Popen([sys.executable, "-m", "yolo_annotator_desktop", "--project", path])
        except Exception as exc:
            messagebox.showerror("打开项目失败", str(exc), parent=self.root)

    def open_path(self, path):
        target = str(Path(path).resolve())
        try:
            if sys.platform == "win32":
                os.startfile(target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:
            messagebox.showerror("无法打开", str(exc), parent=self.root)

    def open_backup_dir(self):
        backup_root = self.label_dir.parent / ".yad_backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        self.open_path(backup_root)

    @staticmethod
    def ensure_log_dir():
        from .diagnostics import LOG_DIR

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        return LOG_DIR

    def run_quality_check(self):
        from .quality_dialog import open_quality_report

        open_quality_report(self.root, self.project_config(), on_issue=self.jump_to_issue)

    def jump_to_issue(self, issue):
        file_path = Path(str(issue.get("file", ""))).resolve()
        candidates = []
        for image in self.all_images:
            if image.resolve() == file_path or self.label_path_for(image).resolve() == file_path:
                candidates.append(image)
        if not candidates:
            if file_path.exists():
                self.open_path(file_path)
            else:
                messagebox.showinfo("无法跳转", "没有找到该问题对应的图片或文件。", parent=self.root)
            return
        self.image_search.set("")
        self.image_filter.set("全部")
        self.images = list(self.all_images)
        self.index = self.images.index(candidates[0])
        self.load_current()
        self.root.lift()
        self.root.focus_force()

    def export_dataset(self):
        from .export_dialog import ExportDialog

        ExportDialog(self.root, self.project_config())

    def jump_dialog(self):
        if not self.images:
            return
        target = simpledialog.askinteger(
            "跳转到图片",
            f"输入图片序号（1-{len(self.images)}）：",
            parent=self.root,
            minvalue=1,
            maxvalue=len(self.images),
            initialvalue=self.index + 1,
        )
        if target is None:
            return
        self.save_labels(silent=True)
        self.index = target - 1
        self.load_current()

    def show_controls(self):
        messagebox.showinfo(
            "操作说明",
            "V：选择与移动框；方向键微调，Shift+方向键大幅微调\n"
            "B：普通矩形框；R：三点式旋转框\n"
            "Ctrl+C / Ctrl+V / Ctrl+D：复制、粘贴、偏移复制框\n"
            "N：将当前图片标记为空图并完成审核\n"
            "A / D：上一张 / 下一张；U：下一张未审核\n"
            "滚轮：以鼠标位置为中心缩放；右键拖动：平移画面\n"
            "Ctrl+Z / Ctrl+Y：撤销 / 重做；H：隐藏或显示标签\n\n"
            "标签在本次会话首次修改前会自动备份，可从“文件”菜单打开备份目录。",
            parent=self.root,
        )

    def show_about(self):
        from . import __version__

        messagebox.showinfo(
            "关于",
            f"YOLO Annotator Desktop {__version__}\n本地优先、可开源的 YOLO 数据集标注工具",
            parent=self.root,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", default=str(PROJECT / "images"))
    parser.add_argument("--labels", default=str(PROJECT / "labels"))
    parser.add_argument("--classes", default=str(PROJECT / "classes.txt"))
    parser.add_argument("--keep-empty", action="store_true", help="Keep empty txt files for reviewed negative images.")
    parser.add_argument("--order-file", default="", help="Optional CSV/TXT whose first column lists image names in review order.")
    parser.add_argument("--filter-order", action="store_true", help="Only open images listed by --order-file.")
    args = parser.parse_args()

    root = tk.Tk()
    from .diagnostics import install_tk_exception_handler

    install_tk_exception_handler(root)
    Annotator(
        root,
        Path(args.images),
        Path(args.labels),
        Path(args.classes),
        keep_empty=args.keep_empty,
        order_file=Path(args.order_file) if args.order_file else None,
        filter_order=args.filter_order,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
