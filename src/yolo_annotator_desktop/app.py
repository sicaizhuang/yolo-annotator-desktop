from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .annotator import Annotator
from .class_manager import ClassManager
from .diagnostics import install_tk_exception_handler
from .export_dialog import ExportDialog
from .project import ProjectConfig, load_project
from .project_wizard import ProjectWizard
from .quality_dialog import open_quality_report
from .qc import inspect_project
from .state import forget_missing_projects, remember_project
from .widgets import fit_window, set_app_icon


APP_NAME = "YOLO Annotator Desktop"
APP_VERSION = __version__


class ProjectHub:
    def __init__(self, root: tk.Tk, project_path: str = ""):
        self.root = root
        set_app_icon(self.root)
        self.project: ProjectConfig | None = None
        self.recent_paths: list[str] = []
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        fit_window(self.root, (980, 620), minimum=(720, 480), margin=(100, 140))
        self.configure_style()
        self.build_menu()
        self.build_ui()
        self.refresh_recent()
        if project_path:
            self.open_project(Path(project_path))
        else:
            self.load_last_project()

    def configure_style(self):
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Project.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Metric.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Muted.TLabel", foreground="#606770")

    def build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="新建或导入数据集...", command=self.new_project, accelerator="Ctrl+N")
        file_menu.add_command(label="打开项目...", command=self.choose_project, accelerator="Ctrl+O")
        file_menu.add_command(label="打开项目目录", command=self.open_project_folder)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=file_menu)

        dataset_menu = tk.Menu(menubar, tearoff=False)
        dataset_menu.add_command(label="打开标注工作区", command=self.launch_annotator, accelerator="Enter")
        dataset_menu.add_command(label="管理类别...", command=self.manage_classes)
        dataset_menu.add_separator()
        dataset_menu.add_command(label="质量检查...", command=self.run_qc)
        dataset_menu.add_command(label="导出数据集...", command=self.export_dataset)
        menubar.add_cascade(label="数据集", menu=dataset_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="打开错误日志目录", command=self.open_log_dir)
        help_menu.add_command(
            label="关于",
            command=lambda: messagebox.showinfo(
                "关于",
                f"{APP_NAME} {APP_VERSION}\n轻量、本地优先、可恢复的 YOLO 数据集标注工具",
                parent=self.root,
            ),
        )
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menubar)
        self.root.bind("<Control-n>", lambda _event: self.new_project())
        self.root.bind("<Control-o>", lambda _event: self.choose_project())
        self.root.bind("<Return>", lambda _event: self.launch_annotator())
        if sys.platform == "darwin":
            self.root.bind("<Command-n>", lambda _event: self.new_project())
            self.root.bind("<Command-o>", lambda _event: self.choose_project())

    def build_ui(self):
        header = ttk.Frame(self.root, padding=(20, 16, 20, 12))
        header.pack(fill=tk.X)
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="打开项目，检查数据质量，然后进入标注工作区。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        content = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        recent_panel = ttk.Frame(content, padding=12)
        content.add(recent_panel, weight=1)
        ttk.Label(recent_panel, text="最近项目", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        ttk.Label(recent_panel, text="双击项目即可打开", style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 8))
        self.recent_list = tk.Listbox(recent_panel, activestyle="none", exportselection=False)
        self.recent_list.pack(fill=tk.BOTH, expand=True)
        self.recent_list.bind("<Double-Button-1>", lambda _event: self.open_recent())
        self.recent_list.bind("<<ListboxSelect>>", lambda _event: self.preview_recent())
        recent_actions = ttk.Frame(recent_panel)
        recent_actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(recent_actions, text="新建 / 导入", command=self.new_project).pack(side=tk.LEFT)
        ttk.Button(recent_actions, text="打开项目", command=self.choose_project).pack(side=tk.LEFT, padx=6)

        project_panel = ttk.Frame(content, padding=16)
        content.add(project_panel, weight=3)
        self.project_name = ttk.Label(project_panel, text="尚未打开项目", style="Project.TLabel")
        self.project_name.pack(anchor=tk.W)
        self.project_path = ttk.Label(project_panel, text="", style="Muted.TLabel", wraplength=650)
        self.project_path.pack(anchor=tk.W, pady=(2, 14))

        progress_row = ttk.Frame(project_panel)
        progress_row.pack(fill=tk.X)
        ttk.Label(progress_row, text="审核进度").pack(side=tk.LEFT)
        self.progress_text = ttk.Label(progress_row, text="0 / 0", style="Muted.TLabel")
        self.progress_text.pack(side=tk.RIGHT)
        self.progress = ttk.Progressbar(project_panel, maximum=100)
        self.progress.pack(fill=tk.X, pady=(4, 16))

        metrics = ttk.Frame(project_panel)
        metrics.pack(fill=tk.X)
        self.metric_values = {}
        for column, (key, label) in enumerate(
            (("images", "图片"), ("reviewed", "已审核"), ("boxes", "标注框"), ("issues", "问题"))
        ):
            cell = ttk.Frame(metrics, padding=(0, 0, 24, 0))
            cell.grid(row=0, column=column, sticky="w")
            value = ttk.Label(cell, text="0", style="Metric.TLabel")
            value.pack(anchor=tk.W)
            ttk.Label(cell, text=label, style="Muted.TLabel").pack(anchor=tk.W)
            self.metric_values[key] = value

        ttk.Separator(project_panel).pack(fill=tk.X, pady=16)
        actions = ttk.Frame(project_panel)
        actions.pack(fill=tk.X)
        self.open_workspace_button = ttk.Button(actions, text="打开标注工作区", command=self.launch_annotator)
        self.open_workspace_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="质量检查", command=self.run_qc).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="导出数据集", command=self.export_dataset).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="管理类别", command=self.manage_classes).pack(side=tk.LEFT, padx=6)

        ttk.Label(project_panel, text="项目详情", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(18, 5))
        self.summary = tk.Text(project_panel, height=11, wrap=tk.WORD, padx=10, pady=9, relief=tk.SOLID, bd=1)
        self.summary.pack(fill=tk.BOTH, expand=True)
        self.summary.config(state=tk.DISABLED)
        self.refresh_summary()

    def set_summary(self, text: str):
        self.summary.config(state=tk.NORMAL)
        self.summary.delete("1.0", tk.END)
        self.summary.insert("1.0", text)
        self.summary.config(state=tk.DISABLED)

    def refresh_recent(self):
        state = forget_missing_projects()
        self.recent_paths = state["recent_projects"]
        self.recent_list.delete(0, tk.END)
        for path in self.recent_paths:
            config_path = Path(path)
            try:
                name = load_project(config_path).name
            except Exception:
                name = config_path.stem
            self.recent_list.insert(tk.END, name)

    def refresh_summary(self, extra: str = ""):
        if self.project is None:
            self.project_name.config(text="尚未打开项目")
            self.project_path.config(text="从左侧最近项目打开，或新建 / 导入一个数据集。")
            self.progress["value"] = 0
            self.progress_text.config(text="0 / 0")
            for value in self.metric_values.values():
                value.config(text="0")
            self.set_summary("支持标准 YOLO Detect 与 YOLO OBB 项目。源图片和标签在导入时不会被修改。")
            return

        errors = self.project.validate()
        report = inspect_project(self.project, verify_images=False) if not errors else None
        self.project_name.config(text=self.project.name)
        self.project_path.config(text=str(self.project.config_path or self.project.image_dir))
        if report:
            reviewed = report["labeled_images"] + report["empty_reviewed_images"]
            total = report["images"]
            self.progress["value"] = reviewed / total * 100 if total else 0
            self.progress_text.config(text=f"{reviewed} / {total}")
            values = {
                "images": total,
                "reviewed": reviewed,
                "boxes": report["boxes"],
                "issues": report["issue_count"],
            }
            for key, value in values.items():
                self.metric_values[key].config(text=str(value))
        lines = [
            f"图片目录：{self.project.image_dir}",
            f"标签目录：{self.project.label_dir}",
            f"类别文件：{self.project.classes_path}",
            f"标注类型：{self.project.annotation_mode}",
            f"类别（{len(self.project.class_names())}）：{', '.join(self.project.class_names())}",
        ]
        if errors:
            lines += ["", "配置问题：", *[f"- {item}" for item in errors]]
        elif report and report["issues"]:
            lines += ["", "质量问题：", *[f"- {kind}: {count}" for kind, count in report["issue_types"].items()]]
        if extra:
            lines += ["", extra]
        self.set_summary("\n".join(lines))

    def load_last_project(self):
        state = forget_missing_projects()
        path = state.get("last_project", "")
        if path and Path(path).exists():
            self.open_project(Path(path))

    def choose_project(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="打开 YOLO Annotator Desktop 项目",
            filetypes=[("YAD 项目", "*.yad.json"), ("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if path:
            self.open_project(Path(path))

    def preview_recent(self):
        selection = self.recent_list.curselection()
        if selection:
            self.open_project(Path(self.recent_paths[selection[0]]))

    def open_recent(self):
        self.preview_recent()
        self.launch_annotator()

    def open_project(self, path: Path):
        try:
            self.project = load_project(path)
            remember_project(path)
            self.refresh_recent()
            self.refresh_summary()
        except Exception as exc:
            messagebox.showerror("打开项目失败", str(exc), parent=self.root)

    def new_project(self):
        ProjectWizard(self.root, self.project_created)

    def project_created(self, project):
        self.project = project
        if project.config_path:
            remember_project(project.config_path)
        self.refresh_recent()
        self.refresh_summary("项目已创建或导入，可以进入标注工作区。")

    def require_project(self) -> bool:
        if self.project is None:
            messagebox.showinfo("尚未打开项目", "请先新建、导入或打开一个项目。", parent=self.root)
            return False
        errors = self.project.validate()
        if errors:
            messagebox.showerror("项目尚未就绪", "\n".join(errors), parent=self.root)
            return False
        return True

    def launch_annotator(self):
        if not self.require_project():
            return
        if self.project.config_path is None:
            messagebox.showerror("无法打开工作区", "项目没有可用的配置文件路径。", parent=self.root)
            return
        subprocess.Popen([sys.executable, "-m", "yolo_annotator_desktop", "--project", str(self.project.config_path)])

    def manage_classes(self):
        if self.project is None:
            messagebox.showinfo("尚未打开项目", "请先打开一个项目。", parent=self.root)
            return
        ClassManager(
            self.root,
            self.project,
            lambda: self.refresh_summary("类别已更新，已有标签 ID 已安全重映射。"),
        )

    def run_qc(self):
        if not self.require_project():
            return
        open_quality_report(self.root, self.project, self.refresh_summary)

    def export_dataset(self):
        if not self.require_project():
            return
        ExportDialog(self.root, self.project, self.refresh_summary)

    def open_project_folder(self):
        if self.project is None:
            return
        folder = str((self.project.config_path.parent if self.project.config_path else self.project.image_dir).resolve())
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    def open_log_dir(self):
        from .diagnostics import LOG_DIR

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        target = str(LOG_DIR)
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])


def run(project_path: str = "", hub: bool = False):
    root = tk.Tk()
    install_tk_exception_handler(root)
    if project_path and not hub:
        try:
            project = load_project(project_path)
        except Exception as exc:
            messagebox.showerror("无法打开项目", str(exc), parent=root)
            root.destroy()
            return
        errors = project.validate()
        if errors:
            messagebox.showerror("项目尚未就绪", "\n".join(errors))
            root.destroy()
            return
        remember_project(project_path)
        Annotator(
            root,
            project.image_dir,
            project.label_dir,
            project.classes_path,
            keep_empty=project.keep_empty,
            order_file=project.order_path,
            filter_order=project.filter_order,
            annotation_mode=project.annotation_mode,
            project_name=project.name,
            project_path=project.config_path,
        )
    else:
        ProjectHub(root, project_path)
    root.mainloop()
