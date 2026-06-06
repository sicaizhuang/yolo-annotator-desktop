import argparse
import copy
import math
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from PIL import Image, ImageTk
from .widgets import IconSet, icon_button


PROJECT = Path.cwd()
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
COLORS = ["#00d084", "#ffb000", "#3aa3ff", "#ff4f81", "#b56cff", "#00e5ff", "#d6ff3f", "#ffffff"]


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
    ):
        self.root = root
        self.image_dir = image_dir
        self.label_dir = label_dir
        self.classes_path = classes_path
        self.classes = [line.strip() for line in classes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.keep_empty = keep_empty
        self.images = self.find_images(image_dir, order_file, filter_order)
        self.index = 0
        self.boxes = []
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.labels_visible = True
        self.annotation_mode = annotation_mode
        self.tool_mode = tk.StringVar(value="obb" if annotation_mode == "obb" else "aabb")
        self.obb_baseline = None
        self.obb_preview = None
        self.drag_start = None
        self.press_box_index = None
        self.resize_handle = None
        self.resize_history_recorded = False
        self.preview_rect = None
        self.img = None
        self.tk_img = None
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
        self.icons = IconSet(self.root)

        self.label_dir.mkdir(parents=True, exist_ok=True)
        self.root.title(f"YOLO Annotator Desktop - {image_dir.name}")
        window_width = min(820, max(760, self.root.winfo_screenwidth() - 300))
        window_height = min(700, max(600, self.root.winfo_screenheight() - 260))
        self.root.geometry(f"{window_width}x{window_height}+20+20")
        self.root.minsize(760, 600)

        self.build_menu()
        self.build_ui()
        self.bind_keys()
        if not self.images:
            messagebox.showerror("No images", f"No images found in:\n{image_dir}")
        else:
            self.load_current()

    @staticmethod
    def find_images(image_dir: Path, order_file: Path | None = None, filter_order: bool = False):
        images = []
        for path in sorted(image_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            if any(part.startswith("_") for part in path.parts):
                continue
            images.append(path)
        if order_file and order_file.exists():
            ordered_names = []
            for line in order_file.read_text(encoding="utf-8-sig").splitlines():
                name = line.split(",", 1)[0].strip().strip('"')
                if name and name.lower() != "image":
                    ordered_names.append(name)
            rank = {name: idx for idx, name in enumerate(ordered_names)}
            if filter_order:
                images = [path for path in images if path.name in rank]
            images.sort(key=lambda path: (rank.get(path.name, len(rank)), path.name))
        return images

    def refresh_class_controls(self):
        for child in self.class_frame.winfo_children():
            child.destroy()
        for idx, name in enumerate(self.classes):
            text = f"{idx + 1}. {name}"
            tk.Radiobutton(self.class_frame, text=text, variable=self.current_class, value=idx, anchor="w").pack(fill=tk.X, anchor="w")

    def bind_keys(self):
        self.root.bind("<Control-n>", lambda _event: self.open_project_hub())
        self.root.bind("<Control-o>", lambda _event: self.open_project_dialog())
        self.root.bind("<Control-s>", lambda _event: self.save_labels())
        self.root.bind("<Control-z>", lambda _event: self.undo())
        self.root.bind("<Control-y>", lambda _event: self.redo())
        self.root.bind("<Left>", lambda _event: self.prev_image())
        self.root.bind("<Right>", lambda _event: self.next_image())
        self.root.bind("a", lambda _event: self.prev_image())
        self.root.bind("d", lambda _event: self.next_image())
        self.root.bind("h", lambda _event: self.toggle_labels())
        self.root.bind("c", lambda _event: self.set_selected_class())
        self.root.bind("u", lambda _event: self.next_unreviewed())
        self.root.bind("b", lambda _event: self.set_tool_mode("aabb"))
        self.root.bind("r", lambda _event: self.set_tool_mode("obb"))
        self.root.bind("<Control-g>", lambda _event: self.jump_dialog())
        self.root.bind("<F1>", lambda _event: self.show_controls())
        self.root.bind("<Escape>", lambda _event: self.clear_selection())
        self.root.bind("<Delete>", lambda _event: self.delete_selected())
        for idx in range(min(9, len(self.classes))):
            self.root.bind(str(idx + 1), lambda _event, i=idx: self.current_class.set(i))

    def current_image_path(self):
        return self.images[self.index]

    def current_label_path(self):
        return self.label_dir / f"{self.current_image_path().stem}.txt"

    def label_path_for(self, image_path):
        return self.label_dir / f"{image_path.stem}.txt"

    def load_current(self):
        path = self.current_image_path()
        self.img = Image.open(path).convert("RGB")
        self.boxes = self.load_labels()
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.obb_baseline = None
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update_list()
        self.redraw()
        self.update_info()

    def load_labels(self):
        label_path = self.current_label_path()
        if not label_path.exists() or self.img is None:
            return []
        boxes = []
        w, h = self.img.size
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            try:
                cls = int(float(parts[0]))
            except ValueError:
                continue
            if not 0 <= cls < len(self.classes):
                continue
            if len(parts) == 5:
                try:
                    xc, yc, bw, bh = [float(v) for v in parts[1:]]
                except ValueError:
                    continue
                boxes.append(
                    {
                        "kind": "aabb",
                        "cls": cls,
                        "x1": (xc - bw / 2) * w,
                        "y1": (yc - bh / 2) * h,
                        "x2": (xc + bw / 2) * w,
                        "y2": (yc + bh / 2) * h,
                    }
                )
            elif len(parts) == 9:
                try:
                    coords = [float(v) for v in parts[1:]]
                except ValueError:
                    continue
                boxes.append(
                    {
                        "kind": "obb",
                        "cls": cls,
                        "points": [(coords[idx] * w, coords[idx + 1] * h) for idx in range(0, 8, 2)],
                    }
                )
        return boxes

    def save_labels(self, silent=False):
        if self.img is None or not self.images:
            return
        w, h = self.img.size
        lines = []
        for box in self.boxes:
            if box.get("kind", "aabb") == "obb":
                points = [
                    (max(0, min(w, x)) / w, max(0, min(h, y)) / h)
                    for x, y in box["points"]
                ]
                flat = " ".join(f"{value:.6f}" for point in points for value in point)
                lines.append(f"{box['cls']} {flat}")
                continue
            x1 = max(0, min(w, box["x1"]))
            y1 = max(0, min(h, box["y1"]))
            x2 = max(0, min(w, box["x2"]))
            y2 = max(0, min(h, box["y2"]))
            if x2 <= x1 or y2 <= y1:
                continue
            xc = ((x1 + x2) / 2) / w
            yc = ((y1 + y2) / 2) / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            lines.append(f"{box['cls']} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
        label_path = self.current_label_path()
        if lines:
            label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        elif self.keep_empty:
            label_path.write_text("", encoding="utf-8")
        elif label_path.exists():
            label_path.unlink()
        if not silent:
            self.update_info("saved")

    def update_info(self, status=""):
        if not self.images:
            self.info.config(text="No images")
            return
        path = self.current_image_path()
        suffix = f" | {status}" if status else ""
        text = f"{self.index + 1}/{len(self.images)}  {path.name}  boxes={len(self.boxes)}  save_dir={self.label_dir}{suffix}"
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

        resized = self.img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(resized)
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.tk_img)

        for idx, box in enumerate(self.boxes):
            self.draw_box(box, selected=(idx == self.selected))
        if self.obb_baseline is not None and self.obb_preview is not None:
            points = [self.image_to_canvas(x, y) for x, y in self.obb_preview]
            self.canvas.create_polygon(*[value for point in points for value in point], outline="#ffffff", fill="", dash=(5, 4), width=2)

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
        color = "#ff3030" if selected else COLORS[box["cls"] % len(COLORS)]
        if box.get("kind", "aabb") == "obb":
            points = [self.image_to_canvas(x, y) for x, y in box["points"]]
            flat = [value for point in points for value in point]
            self.canvas.create_polygon(*flat, outline=color, fill="", width=3 if selected else 2)
            label_x, label_y = min(points, key=lambda point: (point[1], point[0]))
            if self.labels_visible:
                label = self.classes[box["cls"]]
                self.canvas.create_rectangle(label_x, label_y - 20, label_x + max(90, len(label) * 8), label_y, fill=color, outline=color)
                self.canvas.create_text(label_x + 4, label_y - 10, anchor=tk.W, fill="#000000", text=label)
            if selected:
                for hx, hy in points:
                    self.canvas.create_oval(hx - 5, hy - 5, hx + 5, hy + 5, fill="#ffffff", outline="#ff3030", width=2)
            return
        x1, y1 = self.image_to_canvas(box["x1"], box["y1"])
        x2, y2 = self.image_to_canvas(box["x2"], box["y2"])
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3 if selected else 2)
        if self.labels_visible:
            label = self.classes[box["cls"]]
            self.canvas.create_rectangle(x1, y1 - 20, x1 + max(90, len(label) * 8), y1, fill=color, outline=color)
            self.canvas.create_text(x1 + 4, y1 - 10, anchor=tk.W, fill="#000000", text=label)
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
        if self.boxes[self.selected].get("kind", "aabb") == "obb":
            return None
        for name, hx, hy in self.resize_handle_positions(self.boxes[self.selected]):
            if abs(canvas_x - hx) <= 9 and abs(canvas_y - hy) <= 9:
                return name
        return None

    def find_box_at(self, ix, iy):
        if self.img is None:
            return None
        tolerance = max(3.0, 5.0 / max(self.scale, 0.01))
        matches = []
        for idx, box in enumerate(self.boxes):
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
        if self.tool_mode.get() == "obb" and self.obb_baseline is not None:
            points = self.make_obb_points(*self.obb_baseline, self.canvas_to_image(event.x, event.y))
            if points is not None:
                self.record_history()
                self.boxes.append({"kind": "obb", "cls": int(self.current_class.get()), "points": points})
                self.selected = len(self.boxes) - 1
                self.obb_baseline = None
                self.obb_preview = None
                self.update_list()
                self.save_labels(silent=True)
                self.redraw()
                self.update_info("rotated box auto-saved")
            return
        self.drag_start = self.canvas_to_image(event.x, event.y)
        self.resize_handle = self.find_resize_handle(event.x, event.y)
        self.resize_history_recorded = False
        if self.resize_handle is not None:
            self.press_box_index = None
            return
        self.press_box_index = self.find_box_at(*self.drag_start)
        if self.preview_rect:
            self.canvas.delete(self.preview_rect)
            self.preview_rect = None

    def on_drag(self, event):
        if self.drag_start is None:
            return
        if self.resize_handle is not None and self.selected is not None:
            if not self.resize_history_recorded:
                self.record_history()
                self.resize_history_recorded = True
            ix, iy = self.canvas_to_image(event.x, event.y)
            box = self.boxes[self.selected]
            handle = self.resize_handle
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
        if self.resize_handle is not None:
            resized = self.resize_history_recorded
            self.drag_start = None
            self.press_box_index = None
            self.resize_handle = None
            self.resize_history_recorded = False
            if resized:
                self.save_labels(silent=True)
                self.update_list()
                self.redraw()
                self.update_info("resized auto-saved")
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
        self.boxes.append({"kind": "aabb", "cls": int(self.current_class.get()), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        self.selected = len(self.boxes) - 1
        self.update_list()
        self.save_labels(silent=True)
        self.redraw()
        self.update_info("auto-saved")

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

    def on_motion(self, event):
        if self.tool_mode.get() != "obb" or self.obb_baseline is None:
            return
        self.obb_preview = self.make_obb_points(*self.obb_baseline, self.canvas_to_image(event.x, event.y))
        self.redraw()

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

    def set_tool_mode(self, mode):
        expected = "obb" if self.annotation_mode == "obb" else "aabb"
        if mode != expected and self.boxes:
            label = "YOLO OBB" if mode == "obb" else "standard Detect"
            if not messagebox.askyesno(
                "Different annotation type",
                f"This project is configured for '{self.annotation_mode}' annotations.\n\n"
                f"Drawing a {label} box will mix annotation formats and block training export. Continue?",
                parent=self.root,
            ):
                self.tool_mode.set(expected)
                return
        self.tool_mode.set(mode)
        self.obb_baseline = None
        self.obb_preview = None
        self.drag_start = None
        self.redraw()
        warning = " | warning: differs from project annotation type" if mode != expected else ""
        self.update_info(("rectangle mode" if mode == "aabb" else "three-point rotated rectangle mode") + warning)

    def reset_view(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.redraw()

    def open_project_hub(self):
        subprocess.Popen([sys.executable, "-m", "yolo_annotator_desktop", "--hub"])

    def set_selected_class(self):
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
        self.save_labels(silent=True)
        self.redraw()
        self.update_info("class changed")

    def clear_selection(self):
        self.selected = None
        self.box_list.selection_clear(0, tk.END)
        self.redraw()
        self.update_info("deselected")

    def snapshot_boxes(self):
        return copy.deepcopy(self.boxes)

    def record_history(self):
        self.undo_stack.append(self.snapshot_boxes())
        self.redo_stack.clear()

    def restore_boxes(self, boxes, status):
        self.boxes = copy.deepcopy(boxes)
        self.selected = None
        self.update_list()
        self.save_labels(silent=True)
        self.redraw()
        self.update_info(status)

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
        self.redraw()
        self.update_info("labels shown" if self.labels_visible else "labels hidden")

    def add_class(self):
        name = simpledialog.askstring("Add custom class", "New class name:", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.classes:
            messagebox.showinfo("Class exists", f"'{name}' already exists.", parent=self.root)
            return
        self.classes.append(name)
        self.classes_path.write_text("\n".join(self.classes) + "\n", encoding="utf-8")
        self.current_class.set(len(self.classes) - 1)
        self.refresh_class_controls()
        self.update_info(f"added class: {name}")

    def manage_classes(self):
        from .class_manager import ClassManager
        from .project import ProjectConfig

        project = ProjectConfig(
            name=self.image_dir.name,
            images=str(self.image_dir),
            labels=str(self.label_dir),
            classes=str(self.classes_path),
            annotation_mode=self.annotation_mode,
        )
        ClassManager(self.root, project, self.reload_classes)

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
            self.save_labels(silent=True)
            self.redraw()
            self.update_info("auto-saved")

    def delete_all(self):
        if not self.boxes:
            return
        if messagebox.askyesno("Delete all", "Delete all boxes for this image?"):
            self.record_history()
            self.boxes = []
            self.selected = None
            self.update_list()
            self.save_labels(silent=True)
            self.redraw()
            self.update_info("auto-saved")

    def prev_image(self):
        if not self.images:
            return
        self.save_labels(silent=True)
        self.index = max(0, self.index - 1)
        self.load_current()

    def next_image(self):
        if not self.images:
            return
        self.save_labels(silent=True)
        self.index = min(len(self.images) - 1, self.index + 1)
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
        file_menu.add_separator()
        file_menu.add_command(label="保存", command=self.save_labels, accelerator="Ctrl+S")
        file_menu.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="撤销", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="重做", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="设置选中框类别", command=self.set_selected_class, accelerator="C")
        edit_menu.add_command(label="删除选中框", command=self.delete_selected, accelerator="Delete")
        edit_menu.add_command(label="删除本图全部框", command=self.delete_all)
        edit_menu.add_separator()
        edit_menu.add_command(label="管理类别...", command=self.manage_classes)
        menubar.add_cascade(label="编辑", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="隐藏或显示标签", command=self.toggle_labels, accelerator="H")
        view_menu.add_command(label="重置缩放与平移", command=self.reset_view)
        view_menu.add_separator()
        view_menu.add_command(label="上一张", command=self.prev_image, accelerator="A / Left")
        view_menu.add_command(label="下一张", command=self.next_image, accelerator="D / Right")
        view_menu.add_command(label="下一张未审核", command=self.next_unreviewed, accelerator="U")
        view_menu.add_command(label="跳转到图片...", command=self.jump_dialog, accelerator="Ctrl+G")
        menubar.add_cascade(label="视图", menu=view_menu)

        annotation_menu = tk.Menu(menubar, tearoff=False)
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
        annotation_menu.add_separator()
        annotation_menu.add_command(label="添加自定义类别...", command=self.add_class)
        annotation_menu.add_command(label="管理类别...", command=self.manage_classes)
        menubar.add_cascade(label="标注", menu=annotation_menu)

        dataset_menu = tk.Menu(menubar, tearoff=False)
        dataset_menu.add_command(label="质量检查...", command=self.run_quality_check)
        dataset_menu.add_command(label="导出 YOLO 数据集...", command=self.export_dataset)
        dataset_menu.add_separator()
        dataset_menu.add_command(label="打开项目与数据集中心", command=self.open_project_hub)
        menubar.add_cascade(label="数据集", menu=dataset_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="操作说明", command=self.show_controls, accelerator="F1")
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menubar)

    def build_ui(self):
        top = tk.Frame(self.root, bd=1, relief=tk.GROOVE)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=5)

        self.add_toolbar_button(top, "folder", "打开项目 (Ctrl+O)", self.open_project_dialog)
        self.add_toolbar_button(top, "save", "保存标签 (Ctrl+S)", self.save_labels)
        self.add_toolbar_separator(top)
        self.add_toolbar_button(top, "rect", "普通矩形框 (B)", lambda: self.set_tool_mode("aabb"), "aabb")
        self.add_toolbar_button(top, "obb", "三点式旋转框 (R)", lambda: self.set_tool_mode("obb"), "obb")
        self.add_toolbar_separator(top)
        self.add_toolbar_button(top, "undo", "撤销 (Ctrl+Z)", self.undo)
        self.add_toolbar_button(top, "redo", "重做 (Ctrl+Y)", self.redo)
        self.add_toolbar_button(top, "eye_off", "隐藏或显示标签 (H)", self.toggle_labels)
        self.add_toolbar_separator(top)
        self.add_toolbar_button(top, "previous", "上一张 (A / 左方向键)", self.prev_image)
        self.add_toolbar_button(top, "next", "下一张 (D / 右方向键)", self.next_image)
        self.add_toolbar_button(top, "next_unreviewed", "下一张未审核 (U)", self.next_unreviewed)

        body = tk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, minsize=240)

        self.canvas = tk.Canvas(body, bg="#151515", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<ButtonPress-3>", self.on_right_press)
        self.canvas.bind("<B3-Motion>", self.on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_right_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())

        panel = tk.Frame(body, width=240)
        panel.grid(row=0, column=1, sticky="ns", padx=8, pady=4)
        panel.pack_propagate(False)
        self.panel = panel

        class_header = tk.Frame(panel)
        class_header.pack(fill=tk.X)
        tk.Label(class_header, text="类别").pack(side=tk.LEFT, anchor="w")
        self.add_toolbar_button(class_header, "add", "添加自定义类别", self.add_class, padx=(8, 2))
        self.add_toolbar_button(class_header, "manage", "管理、重命名、删除或调整类别顺序", self.manage_classes)
        self.class_frame = tk.Frame(panel)
        self.class_frame.pack(fill=tk.X)
        self.refresh_class_controls()

        tk.Label(panel, text="标注框").pack(anchor="w", pady=(12, 2))
        self.box_list = tk.Listbox(panel, height=16)
        self.box_list.pack(fill=tk.BOTH, expand=True)
        self.box_list.bind("<<ListboxSelect>>", self.on_select_box)

        box_actions = tk.Frame(panel)
        box_actions.pack(fill=tk.X, pady=(6, 2))
        self.add_toolbar_button(box_actions, "tag", "将选中框设置为当前类别 (C)", self.set_selected_class)
        self.add_toolbar_button(box_actions, "trash", "删除选中框 (Delete)", self.delete_selected)
        self.add_toolbar_button(box_actions, "deselect", "取消选择 (Esc)", self.clear_selection)

        tk.Label(
            panel,
            text="普通框 B | 旋转框 R | 滚轮缩放 | 右键拖动画面",
            justify=tk.LEFT,
            fg="#666666",
            wraplength=230,
        ).pack(anchor="w", pady=(8, 4))

        self.info = tk.Label(self.root, text="", anchor="w", bd=1, relief=tk.SUNKEN, padx=6)
        self.info.pack(side=tk.BOTTOM, fill=tk.X)

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
            if box.get("kind", "aabb") == "obb":
                center_x = round(sum(point[0] for point in box["points"]) / 4)
                center_y = round(sum(point[1] for point in box["points"]) / 4)
                self.box_list.insert(tk.END, f"{idx + 1}. ◇ {name}  center=[{center_x},{center_y}]")
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
            name=self.image_dir.name,
            images=str(self.image_dir),
            labels=str(self.label_dir),
            classes=str(self.classes_path),
            keep_empty=self.keep_empty,
            annotation_mode=self.annotation_mode,
        )

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

    def run_quality_check(self):
        from .qc import inspect_project

        report = inspect_project(self.project_config())
        text = (
            f"图片：{report['images']}\n"
            f"已标注：{report['labeled_images']}\n"
            f"已审核空图：{report['empty_reviewed_images']}\n"
            f"未审核：{report['unreviewed_images']}\n"
            f"标注框：{report['boxes']}\n"
            f"格式：{report['format_counts']}\n"
            f"问题：{report['issue_count']}"
        )
        messagebox.showinfo("质量检查", text, parent=self.root)

    def export_dataset(self):
        from .qc import export_yolo_dataset

        output = filedialog.askdirectory(parent=self.root, title="选择 YOLO 数据集导出目录")
        if not output:
            return
        try:
            result = export_yolo_dataset(self.project_config(), Path(output))
            messagebox.showinfo(
                "导出完成",
                f"训练集图片：{result['train']}\n验证集图片：{result['val']}\n目录：{result['output']}",
                parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self.root)

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
            "左键拖动：画普通框或旋转框基线\n"
            "左键单击框：选中最小的框\n"
            "滚轮：以鼠标位置为中心缩放\n"
            "右键拖动：平移画面\n"
            "B / R：切换普通框与三点式旋转框\n"
            "Ctrl+Z / Ctrl+Y：撤销 / 重做\n"
            "A / D：上一张 / 下一张",
            parent=self.root,
        )

    def show_about(self):
        messagebox.showinfo(
            "关于",
            "YOLO Annotator Desktop\n本地优先、可开源的 YOLO 数据集标注工具",
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
