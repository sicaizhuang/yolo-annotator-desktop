from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .formats import export_coco, export_pascal_voc
from .project import ProjectConfig
from .qc import export_yolo_dataset
from .widgets import fit_window


class ExportDialog(tk.Toplevel):
    FORMATS = (
        ("yolo", "YOLO 训练数据集", "生成 train/val、data.yaml 和源数据质量报告。"),
        ("coco", "COCO JSON", "通用交换格式；旋转框会保留为 polygon segmentation。"),
        ("voc", "Pascal VOC XML", "传统检测格式；仅支持普通矩形框。"),
    )

    def __init__(self, parent, project: ProjectConfig, on_complete=None):
        super().__init__(parent)
        self.project = project
        self.on_complete = on_complete
        self.format = tk.StringVar(value="yolo")
        self.output = tk.StringVar()
        self.val_ratio = tk.DoubleVar(value=0.2)
        self.seed = tk.IntVar(value=42)
        self.results = queue.Queue()
        self.running = False
        self.title("导出数据集")
        fit_window(self, (620, 430), minimum=(560, 390), margin=(100, 140))
        self.transient(parent)
        self.grab_set()
        self.build_ui()

    def build_ui(self):
        ttk.Label(self, text="导出数据集", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W, padx=18, pady=(18, 4))
        ttk.Label(self, text="选择目标格式。导出不会修改源图片或标签。", foreground="#606770").pack(anchor=tk.W, padx=18)
        choices = ttk.Frame(self)
        choices.pack(fill=tk.X, padx=18, pady=14)
        for value, title, description in self.FORMATS:
            row = ttk.Frame(choices)
            row.pack(fill=tk.X, pady=4)
            ttk.Radiobutton(row, text=title, variable=self.format, value=value, command=self.refresh_options).pack(anchor=tk.W)
            ttk.Label(row, text=description, foreground="#606770").pack(anchor=tk.W, padx=(24, 0))

        destination = ttk.LabelFrame(self, text="输出", padding=10)
        destination.pack(fill=tk.X, padx=18, pady=(0, 10))
        ttk.Entry(destination, textvariable=self.output).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(destination, text="选择...", command=self.choose_output).pack(side=tk.LEFT, padx=(8, 0))

        self.options = ttk.LabelFrame(self, text="YOLO 划分设置", padding=10)
        self.options.pack(fill=tk.X, padx=18)
        ttk.Label(self.options, text="验证集比例").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(self.options, from_=0.05, to=0.5, increment=0.05, textvariable=self.val_ratio, width=8).grid(row=0, column=1, padx=8)
        ttk.Label(self.options, text="随机种子").grid(row=0, column=2, sticky="w", padx=(18, 0))
        ttk.Spinbox(self.options, from_=0, to=999999, textvariable=self.seed, width=10).grid(row=0, column=3, padx=8)

        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=18, pady=18)
        self.cancel_button = ttk.Button(footer, text="取消", command=self.destroy)
        self.cancel_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.export_button = ttk.Button(footer, text="开始导出", command=self.export)
        self.export_button.pack(side=tk.RIGHT)
        self.progress = ttk.Progressbar(self, mode="indeterminate")

    def refresh_options(self):
        if self.format.get() == "yolo":
            self.options.pack(fill=tk.X, padx=18)
        else:
            self.options.pack_forget()
        self.output.set("")

    def choose_output(self):
        if self.format.get() == "coco":
            value = filedialog.asksaveasfilename(
                parent=self,
                title="保存 COCO JSON",
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
            )
        else:
            value = filedialog.askdirectory(parent=self, title="选择导出目录")
        if value:
            self.output.set(value)

    def export(self):
        if self.running:
            return
        output = self.output.get().strip()
        if not output:
            messagebox.showerror("缺少输出位置", "请先选择输出文件或目录。", parent=self)
            return
        self.running = True
        self.export_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.DISABLED)
        self.progress.pack(fill=tk.X, padx=18, pady=(0, 14))
        self.progress.start(12)
        parameters = (self.format.get(), output, self.val_ratio.get(), self.seed.get())
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        threading.Thread(target=self.export_worker, args=(parameters,), daemon=True).start()
        self.after(80, self.poll_export)

    def export_worker(self, parameters):
        export_format, output, val_ratio, seed = parameters
        try:
            if export_format == "yolo":
                result = export_yolo_dataset(self.project, Path(output), val_ratio, seed)
            elif export_format == "coco":
                result = export_coco(self.project, Path(output))
            else:
                result = export_pascal_voc(self.project, Path(output))
        except Exception as exc:
            self.results.put(("error", exc))
            return
        self.results.put(("ok", result))

    def poll_export(self):
        try:
            kind, value = self.results.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(80, self.poll_export)
            return
        self.running = False
        self.progress.stop()
        self.progress.pack_forget()
        self.export_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.NORMAL)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        if kind == "error":
            messagebox.showerror("导出失败", str(value), parent=self)
            return
        result = value
        text = "\n".join(f"{key}: {value}" for key, value in result.items())
        messagebox.showinfo("导出完成", text, parent=self)
        if self.on_complete:
            self.on_complete(text)
        self.destroy()
