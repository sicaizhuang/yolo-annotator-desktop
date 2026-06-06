from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .project import (
    create_project,
    create_project_from_coco,
    create_project_from_folders,
    create_project_from_pascal_voc,
    create_project_from_yolo_yaml,
)
from .widgets import fit_window


class ProjectWizard(tk.Toplevel):
    METHODS = [
        ("empty", "新建空数据集", "创建 images、labels、classes.txt 和便携项目文件。"),
        ("folders", "接管已有图片 / 标签目录", "保留现有数据位置，只创建项目配置和类别文件。"),
        ("yaml", "导入已有 YOLO data.yaml", "从标准 YOLO 数据集打开 train、val 或 test 划分。"),
        ("coco", "导入 COCO JSON", "转换常见 COCO bbox 标注，并保留源图片位置。"),
        ("voc", "导入 Pascal VOC XML", "转换 XML 矩形框，并保留源图片位置。"),
    ]

    def __init__(self, parent, on_created):
        super().__init__(parent)
        self.on_created = on_created
        self.title("新建或导入数据集")
        fit_window(self, (720, 590), minimum=(620, 500), margin=(100, 140))
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
            "coco": tk.StringVar(),
            "xml_dir": tk.StringVar(),
        }
        self.build_ui()
        self.refresh_fields()

    def build_ui(self):
        ttk.Label(self, text="新建或导入数据集", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W, padx=18, pady=(18, 4))
        ttk.Label(self, text="选择项目来源。导入时不会修改源图片和标签。", foreground="#606770").pack(anchor=tk.W, padx=18)
        methods = ttk.Frame(self)
        methods.pack(fill=tk.X, padx=18, pady=14)
        for value, title, description in self.METHODS:
            row = ttk.Frame(methods)
            row.pack(fill=tk.X, pady=3)
            ttk.Radiobutton(row, text=title, variable=self.method, value=value, command=self.refresh_fields).pack(anchor=tk.W)
            ttk.Label(row, text=description, foreground="#666666").pack(anchor=tk.W, padx=(24, 0))

        self.fields = ttk.LabelFrame(self, text="设置", padding=12)
        self.fields.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=18, pady=(0, 18))
        ttk.Button(footer, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(footer, text="创建项目", command=self.create).pack(side=tk.RIGHT)

    def field(self, row, label, key, browse=None):
        ttk.Label(self.fields, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(self.fields, textvariable=self.values[key]).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        if browse:
            ttk.Button(self.fields, text="选择...", command=browse).grid(row=row, column=2, pady=5)

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

    def refresh_fields(self):
        for child in self.fields.winfo_children():
            child.destroy()
        self.fields.columnconfigure(1, weight=1)
        self.field(0, "项目工作目录", "workspace", lambda: self.choose_dir("workspace"))
        ttk.Label(self.fields, text="标注类型").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(
            self.fields,
            textvariable=self.values["annotation_mode"],
            values=("detect", "obb"),
            state="readonly",
        ).grid(row=1, column=1, sticky="w", padx=8, pady=5)
        method = self.method.get()
        if method == "empty":
            self.field(2, "项目名称", "name")
            self.field(3, "类别（英文逗号分隔）", "classes")
        elif method == "folders":
            self.field(2, "项目名称", "name")
            self.field(3, "图片目录", "images", lambda: self.choose_dir("images"))
            self.field(4, "标签目录（可留空）", "labels", lambda: self.choose_dir("labels"))
            self.field(5, "类别（英文逗号分隔）", "classes")
        elif method == "yaml":
            self.field(2, "YOLO data.yaml", "yaml", self.choose_yaml)
            ttk.Label(self.fields, text="数据划分").grid(row=3, column=0, sticky="w", pady=5)
            ttk.Combobox(self.fields, textvariable=self.values["split"], values=("train", "val", "test"), state="readonly").grid(row=3, column=1, sticky="w", padx=8, pady=5)
        elif method == "coco":
            self.field(2, "COCO JSON", "coco", self.choose_coco)
            self.field(3, "图片根目录", "images", lambda: self.choose_dir("images"))
        else:
            self.field(2, "Pascal VOC XML 目录", "xml_dir", lambda: self.choose_dir("xml_dir"))
            self.field(3, "图片根目录", "images", lambda: self.choose_dir("images"))

    def create(self):
        workspace = self.values["workspace"].get().strip()
        if not workspace:
            messagebox.showerror("缺少工作目录", "请选择项目工作目录。", parent=self)
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
                project = create_project_from_coco(
                    workspace,
                    self.values["coco"].get(),
                    self.values["images"].get(),
                    annotation_mode,
                )
            else:
                if annotation_mode != "detect":
                    raise ValueError("Pascal VOC XML 不能保留旋转框；请使用普通框模式，或导入 COCO/YOLO OBB。")
                project = create_project_from_pascal_voc(workspace, self.values["xml_dir"].get(), self.values["images"].get())
        except Exception as exc:
            messagebox.showerror("创建项目失败", str(exc), parent=self)
            return
        self.on_created(project)
        self.destroy()

    def classes(self):
        classes = [item.strip() for item in self.values["classes"].get().split(",") if item.strip()]
        if not classes:
            raise ValueError("至少需要一个类别。")
        if len(classes) != len(set(classes)):
            raise ValueError("类别名称不能重复。")
        return classes
