from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .project import create_project, create_project_from_folders, create_project_from_yolo_yaml


class ProjectWizard(tk.Toplevel):
    METHODS = [
        ("empty", "Empty managed project", "Create images/, labels/, classes.txt, and a portable project file."),
        ("folders", "Existing image/label folders", "Keep existing data in place and create a project file around it."),
        ("yaml", "Existing YOLO data.yaml", "Open a train or validation split from a standard YOLO dataset."),
    ]

    def __init__(self, parent, on_created):
        super().__init__(parent)
        self.on_created = on_created
        self.title("Create or import dataset")
        self.geometry("720x590")
        self.transient(parent)
        self.grab_set()
        self.method = tk.StringVar(value="empty")
        self.values = {
            "workspace": tk.StringVar(),
            "name": tk.StringVar(value="my_dataset"),
            "classes": tk.StringVar(value="object"),
            "images": tk.StringVar(),
            "labels": tk.StringVar(),
            "yaml": tk.StringVar(),
            "split": tk.StringVar(value="train"),
            "annotation_mode": tk.StringVar(value="detect"),
        }
        self.build_ui()
        self.refresh_fields()

    def build_ui(self):
        ttk.Label(self, text="Create or import a dataset", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W, padx=18, pady=(18, 4))
        ttk.Label(self, text="Choose how the dataset starts. Source images and labels are never modified during import.").pack(anchor=tk.W, padx=18)
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
        ttk.Button(footer, text="Create project", command=self.create).pack(side=tk.RIGHT)

    def field(self, row, label, key, browse=None):
        ttk.Label(self.fields, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(self.fields, textvariable=self.values[key]).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        if browse:
            ttk.Button(self.fields, text="Browse", command=browse).grid(row=row, column=2, pady=5)

    def choose_dir(self, key):
        value = filedialog.askdirectory(parent=self)
        if value:
            self.values[key].set(value)

    def choose_yaml(self):
        value = filedialog.askopenfilename(parent=self, filetypes=[("YOLO YAML", "*.yaml *.yml"), ("All files", "*.*")])
        if value:
            self.values["yaml"].set(value)

    def refresh_fields(self):
        for child in self.fields.winfo_children():
            child.destroy()
        self.fields.columnconfigure(1, weight=1)
        self.field(0, "Project workspace", "workspace", lambda: self.choose_dir("workspace"))
        ttk.Label(self.fields, text="Annotation type").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(
            self.fields,
            textvariable=self.values["annotation_mode"],
            values=("detect", "obb"),
            state="readonly",
        ).grid(row=1, column=1, sticky="w", padx=8, pady=5)
        method = self.method.get()
        if method == "empty":
            self.field(2, "Project name", "name")
            self.field(3, "Classes (comma-separated)", "classes")
        elif method == "folders":
            self.field(2, "Project name", "name")
            self.field(3, "Image folder", "images", lambda: self.choose_dir("images"))
            self.field(4, "Label folder", "labels", lambda: self.choose_dir("labels"))
            self.field(5, "Classes (comma-separated)", "classes")
        else:
            self.field(2, "YOLO data.yaml", "yaml", self.choose_yaml)
            ttk.Label(self.fields, text="Split").grid(row=3, column=0, sticky="w", pady=5)
            ttk.Combobox(self.fields, textvariable=self.values["split"], values=("train", "val", "test"), state="readonly").grid(row=3, column=1, sticky="w", padx=8, pady=5)

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
            else:
                project = create_project_from_yolo_yaml(workspace, self.values["yaml"].get(), self.values["split"].get(), annotation_mode)
        except Exception as exc:
            messagebox.showerror("Create project failed", str(exc), parent=self)
            return
        self.on_created(project)
        self.destroy()

    def classes(self):
        classes = [item.strip() for item in self.values["classes"].get().split(",") if item.strip()]
        if not classes:
            raise ValueError("At least one class is required.")
        if len(classes) != len(set(classes)):
            raise ValueError("Class names must be unique.")
        return classes
