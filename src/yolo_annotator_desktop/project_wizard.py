from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .presets import CLASS_PRESETS, load_classes_file, parse_class_text
from .project import (
    SUPPORTED_ANNOTATION_MODES,
    create_project,
    create_project_from_coco,
    create_project_from_folders,
    create_project_from_pascal_voc,
    create_project_from_yolo_yaml,
)
from .widgets import fit_window


class ProjectWizard(tk.Toplevel):
    METHODS = [
        ("empty", "New managed dataset", "Create images/, labels/, classes.txt and a portable project file."),
        ("folders", "Use existing image/label folders", "Keep source data in place and create only project metadata."),
        ("yaml", "Import YOLO data.yaml", "Open train/val/test from directory splits, image-list TXT splits, or multi-directory splits."),
        ("coco", "Import COCO JSON", "Convert common COCO bbox annotations while keeping source images in place."),
        ("voc", "Import Pascal VOC XML", "Convert XML rectangle annotations while keeping source images in place."),
    ]

    def __init__(self, parent, on_created):
        super().__init__(parent)
        self.on_created = on_created
        self.title("New or Import Dataset")
        fit_window(self, (760, 660), minimum=(660, 540), margin=(100, 140))
        self.transient(parent)
        self.grab_set()
        self.method = tk.StringVar(value="empty")
        self.values = {
            "workspace": tk.StringVar(),
            "name": tk.StringVar(value="my_dataset"),
            "classes": tk.StringVar(value="object"),
            "classes_file": tk.StringVar(),
            "preset": tk.StringVar(value="Single object"),
            "images": tk.StringVar(),
            "labels": tk.StringVar(),
            "yaml": tk.StringVar(),
            "split": tk.StringVar(value="train"),
            "annotation_mode": tk.StringVar(value="detect"),
            "coco": tk.StringVar(),
            "xml_dir": tk.StringVar(),
        }
        self.build_ui()
        self.apply_preset()
        self.refresh_fields()

    def build_ui(self):
        ttk.Label(self, text="New or Import Dataset", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W, padx=18, pady=(18, 4))
        ttk.Label(
            self,
            text="Choose a source. Imports create a project wrapper and do not modify source images.",
            foreground="#606770",
        ).pack(anchor=tk.W, padx=18)

        methods = ttk.Frame(self)
        methods.pack(fill=tk.X, padx=18, pady=14)
        for value, title, description in self.METHODS:
            row = ttk.Frame(methods)
            row.pack(fill=tk.X, pady=3)
            ttk.Radiobutton(row, text=title, variable=self.method, value=value, command=self.refresh_fields).pack(anchor=tk.W)
            ttk.Label(row, text=description, foreground="#666666").pack(anchor=tk.W, padx=(24, 0))

        self.fields = ttk.LabelFrame(self, text="Settings", padding=12)
        self.fields.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=18, pady=(0, 18))
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(footer, text="Create Project", command=self.create).pack(side=tk.RIGHT)

    def field(self, row, label, key, browse=None):
        ttk.Label(self.fields, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(self.fields, textvariable=self.values[key]).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        if browse:
            ttk.Button(self.fields, text="Browse...", command=browse).grid(row=row, column=2, pady=5)

    def choose_dir(self, key):
        value = filedialog.askdirectory(parent=self)
        if value:
            self.values[key].set(value)

    def choose_yaml(self):
        value = filedialog.askopenfilename(parent=self, filetypes=[("YOLO YAML", "*.yaml *.yml"), ("All files", "*.*")])
        if value:
            self.values["yaml"].set(value)

    def choose_coco(self):
        value = filedialog.askopenfilename(parent=self, filetypes=[("COCO JSON", "*.json"), ("All files", "*.*")])
        if value:
            self.values["coco"].set(value)

    def choose_classes_file(self):
        value = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Class or YAML files", "*.txt *.names *.yaml *.yml"), ("All files", "*.*")],
        )
        if not value:
            return
        self.values["classes_file"].set(value)
        try:
            classes = load_classes_file(value)
        except Exception as exc:
            messagebox.showerror("Could not load classes", str(exc), parent=self)
            return
        self.values["classes"].set(", ".join(classes))
        self.values["preset"].set("Custom")

    def apply_preset(self, _event=None):
        names = CLASS_PRESETS.get(self.values["preset"].get(), [])
        if names:
            self.values["classes"].set(", ".join(names))

    def add_class_controls(self, start_row: int) -> int:
        ttk.Label(self.fields, text="Class preset").grid(row=start_row, column=0, sticky="w", pady=5)
        preset = ttk.Combobox(
            self.fields,
            textvariable=self.values["preset"],
            values=tuple(CLASS_PRESETS),
            state="readonly",
        )
        preset.grid(row=start_row, column=1, sticky="ew", padx=8, pady=5)
        preset.bind("<<ComboboxSelected>>", self.apply_preset)
        ttk.Button(self.fields, text="Load file...", command=self.choose_classes_file).grid(row=start_row, column=2, pady=5)
        self.field(start_row + 1, "Classes", "classes")
        ttk.Label(
            self.fields,
            text="Comma-separated or one class per line. Class IDs follow this order.",
            foreground="#606770",
        ).grid(row=start_row + 2, column=1, sticky="w", padx=8)
        return start_row + 3

    def refresh_fields(self):
        for child in self.fields.winfo_children():
            child.destroy()
        self.fields.columnconfigure(1, weight=1)
        self.field(0, "Project workspace", "workspace", lambda: self.choose_dir("workspace"))
        ttk.Label(self.fields, text="Annotation mode").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(
            self.fields,
            textvariable=self.values["annotation_mode"],
            values=tuple(sorted(SUPPORTED_ANNOTATION_MODES)),
            state="readonly",
        ).grid(row=1, column=1, sticky="w", padx=8, pady=5)

        method = self.method.get()
        if method == "empty":
            self.field(2, "Project name", "name")
            self.add_class_controls(3)
        elif method == "folders":
            self.field(2, "Project name", "name")
            self.field(3, "Image folder", "images", lambda: self.choose_dir("images"))
            self.field(4, "Label folder (optional)", "labels", lambda: self.choose_dir("labels"))
            self.add_class_controls(5)
        elif method == "yaml":
            self.field(2, "YOLO data.yaml", "yaml", self.choose_yaml)
            ttk.Label(self.fields, text="Split").grid(row=3, column=0, sticky="w", pady=5)
            ttk.Combobox(self.fields, textvariable=self.values["split"], values=("train", "val", "test"), state="readonly").grid(row=3, column=1, sticky="w", padx=8, pady=5)
            ttk.Label(
                self.fields,
                text="Supports directory splits, image-list TXT splits, and split lists with multiple directories/files.",
                foreground="#606770",
                wraplength=460,
            ).grid(row=4, column=1, sticky="w", padx=8)
        elif method == "coco":
            self.field(2, "COCO JSON", "coco", self.choose_coco)
            self.field(3, "Image root", "images", lambda: self.choose_dir("images"))
        else:
            self.field(2, "Pascal VOC XML folder", "xml_dir", lambda: self.choose_dir("xml_dir"))
            self.field(3, "Image root", "images", lambda: self.choose_dir("images"))
            ttk.Label(
                self.fields,
                text="Pascal VOC stores axis-aligned rectangles, so it imports as detect mode only.",
                foreground="#606770",
                wraplength=460,
            ).grid(row=4, column=1, sticky="w", padx=8)

    def create(self):
        workspace = self.values["workspace"].get().strip()
        if not workspace:
            messagebox.showerror("Missing workspace", "Choose a project workspace.", parent=self)
            return
        method = self.method.get()
        annotation_mode = self.values["annotation_mode"].get()
        try:
            if method == "empty":
                project = create_project(workspace, self.values["name"].get(), self.classes(), annotation_mode)
            elif method == "folders":
                images = self.values["images"].get().strip()
                labels = self.values["labels"].get().strip() or str(Path(images).parent / "labels")
                project = create_project_from_folders(workspace, self.values["name"].get(), images, labels, self.classes(), annotation_mode)
            elif method == "yaml":
                project = create_project_from_yolo_yaml(workspace, self.values["yaml"].get(), self.values["split"].get(), annotation_mode)
            elif method == "coco":
                project = create_project_from_coco(workspace, self.values["coco"].get(), self.values["images"].get(), annotation_mode)
            else:
                if annotation_mode != "detect":
                    raise ValueError("Pascal VOC XML cannot preserve rotated boxes. Choose detect mode.")
                project = create_project_from_pascal_voc(workspace, self.values["xml_dir"].get(), self.values["images"].get())
        except Exception as exc:
            messagebox.showerror("Project creation failed", str(exc), parent=self)
            return
        self.on_created(project)
        self.destroy()

    def classes(self):
        return parse_class_text(self.values["classes"].get())
