import argparse
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk


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
    ):
        self.root = root
        self.image_dir = image_dir
        self.label_dir = label_dir
        self.classes = [line.strip() for line in classes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.keep_empty = keep_empty
        self.images = self.find_images(image_dir, order_file, filter_order)
        self.index = 0
        self.boxes = []
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.labels_visible = True
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

        self.label_dir.mkdir(parents=True, exist_ok=True)
        self.root.title(f"YOLO Annotator Desktop - {image_dir.name}")
        self.root.geometry("1220x860")
        self.root.minsize(900, 650)

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

    def build_ui(self):
        top = tk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        self.info = tk.Label(top, text="", anchor="w")
        self.info.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(top, text="Prev (A)", command=self.prev_image).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Save (Ctrl+S)", command=self.save_labels).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Next (D)", command=self.next_image).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Next Unreviewed (U)", command=self.next_unreviewed).pack(side=tk.LEFT, padx=3)
        self.jump_value = tk.StringVar()
        tk.Entry(top, width=6, textvariable=self.jump_value).pack(side=tk.LEFT, padx=(10, 2))
        tk.Button(top, text="Go", command=self.jump_to_image).pack(side=tk.LEFT, padx=2)

        body = tk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(body, bg="#151515", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<ButtonPress-3>", self.on_right_press)
        self.canvas.bind("<B3-Motion>", self.on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_right_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())

        panel = tk.Frame(body, width=260)
        panel.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=4)
        panel.pack_propagate(False)

        tk.Label(panel, text="Class").pack(anchor="w")
        for idx, name in enumerate(self.classes):
            text = f"{idx + 1}. {name}"
            tk.Radiobutton(panel, text=text, variable=self.current_class, value=idx, anchor="w").pack(fill=tk.X, anchor="w")

        tk.Label(panel, text="Boxes").pack(anchor="w", pady=(16, 2))
        self.box_list = tk.Listbox(panel, height=16)
        self.box_list.pack(fill=tk.BOTH, expand=True)
        self.box_list.bind("<<ListboxSelect>>", self.on_select_box)

        self.toggle_labels_button = tk.Button(panel, text="Hide Labels (H)", command=self.toggle_labels)
        self.toggle_labels_button.pack(fill=tk.X, pady=(8, 2))
        tk.Button(panel, text="Undo (Ctrl+Z)", command=self.undo).pack(fill=tk.X, pady=2)
        tk.Button(panel, text="Redo (Ctrl+Y)", command=self.redo).pack(fill=tk.X, pady=2)
        tk.Button(panel, text="Set Selected Class (C)", command=self.set_selected_class).pack(fill=tk.X, pady=2)
        tk.Button(panel, text="Deselect (Esc)", command=self.clear_selection).pack(fill=tk.X, pady=2)
        tk.Button(panel, text="Delete Selected (Del)", command=self.delete_selected).pack(fill=tk.X, pady=2)
        tk.Button(panel, text="Delete All Boxes", command=self.delete_all).pack(fill=tk.X, pady=2)

        max_key = min(9, len(self.classes))
        help_text = (
            "Draw: drag empty area with left mouse\n"
            "Select: left click box, right click, or list\n"
            "Reclass: choose class, press C\n"
            f"Classes: keys 1-{max_key}\n"
            "Prev/Next: A / D or arrows\n"
            "Save: Ctrl+S\n"
            "Undo/Redo: Ctrl+Z / Ctrl+Y\n"
            "Hide/show label text: H\n"
            "Zoom: mouse wheel\n"
            "Pan: drag with right mouse\n"
            "Resize: select box, drag its handles\n"
            "Labels save as YOLO txt"
        )
        tk.Label(panel, text=help_text, justify=tk.LEFT, fg="#555").pack(anchor="w", pady=12)

    def bind_keys(self):
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
        self.root.bind("<Control-g>", lambda _event: self.jump_to_image())
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
            if len(parts) != 5:
                continue
            try:
                cls = int(float(parts[0]))
                xc, yc, bw, bh = [float(v) for v in parts[1:]]
            except ValueError:
                continue
            x1 = (xc - bw / 2) * w
            y1 = (yc - bh / 2) * h
            x2 = (xc + bw / 2) * w
            y2 = (yc + bh / 2) * h
            if 0 <= cls < len(self.classes):
                boxes.append({"cls": cls, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return boxes

    def save_labels(self, silent=False):
        if self.img is None or not self.images:
            return
        w, h = self.img.size
        lines = []
        for box in self.boxes:
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

    def update_list(self):
        self.box_list.delete(0, tk.END)
        for idx, box in enumerate(self.boxes):
            name = self.classes[box["cls"]]
            x1, y1, x2, y2 = [round(box[k]) for k in ("x1", "y1", "x2", "y2")]
            self.box_list.insert(tk.END, f"{idx + 1}. {name}  [{x1},{y1},{x2},{y2}]")
        if self.selected is not None and 0 <= self.selected < len(self.boxes):
            self.box_list.selection_clear(0, tk.END)
            self.box_list.selection_set(self.selected)
            self.box_list.see(self.selected)

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
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        if not dragged:
            self.clear_selection()
            return
        self.record_history()
        self.boxes.append({"cls": int(self.current_class.get()), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
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
        return [box.copy() for box in self.boxes]

    def record_history(self):
        self.undo_stack.append(self.snapshot_boxes())
        self.redo_stack.clear()

    def restore_boxes(self, boxes, status):
        self.boxes = [box.copy() for box in boxes]
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
        text = "Hide Labels (H)" if self.labels_visible else "Show Labels (H)"
        self.toggle_labels_button.config(text=text)
        self.redraw()
        self.update_info("labels shown" if self.labels_visible else "labels hidden")

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

    def jump_to_image(self):
        if not self.images:
            return
        raw = self.jump_value.get().strip()
        try:
            target = int(raw) - 1
        except ValueError:
            self.update_info("enter an image number")
            return
        if not 0 <= target < len(self.images):
            self.update_info(f"image number must be 1-{len(self.images)}")
            return
        self.save_labels(silent=True)
        self.index = target
        self.load_current()


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
