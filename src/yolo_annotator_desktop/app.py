from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .annotator import Annotator
from .class_manager import ClassManager
from .project import ProjectConfig, create_project, load_project
from .qc import export_yolo_dataset, inspect_project


APP_NAME = "YOLO Annotator Desktop"
APP_VERSION = "0.1.0"
STATE_PATH = Path.home() / ".yolo_annotator_desktop.json"


class ProjectHub:
    def __init__(self, root: tk.Tk, project_path: str = ""):
        self.root = root
        self.project: ProjectConfig | None = None
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("780x520")
        self.root.minsize(680, 440)
        self.build_ui()
        if project_path:
            self.open_project(Path(project_path))
        else:
            self.load_last_project()

    def build_ui(self):
        header = ttk.Frame(self.root, padding=18)
        header.pack(fill=tk.X)
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 20, "bold")).pack(anchor=tk.W)
        ttk.Label(header, text="Fast, local-first YOLO bounding-box annotation").pack(anchor=tk.W)

        actions = ttk.Frame(self.root, padding=(18, 0))
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Open Annotator", command=self.launch_annotator).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="New Project", command=self.new_project).pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Open Project", command=self.choose_project).pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Manage Classes", command=self.manage_classes).pack(side=tk.LEFT, padx=4)

        tools = ttk.Frame(self.root, padding=(18, 10))
        tools.pack(fill=tk.X)
        ttk.Button(tools, text="Run Quality Check", command=self.run_qc).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(tools, text="Export YOLO Dataset", command=self.export_dataset).pack(side=tk.LEFT, padx=4)
        ttk.Button(tools, text="Open Project Folder", command=self.open_project_folder).pack(side=tk.LEFT, padx=4)

        self.summary = tk.Text(self.root, height=18, wrap=tk.WORD, padx=14, pady=12)
        self.summary.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))
        self.summary.config(state=tk.DISABLED)
        self.refresh_summary()

    def set_summary(self, text: str):
        self.summary.config(state=tk.NORMAL)
        self.summary.delete("1.0", tk.END)
        self.summary.insert("1.0", text)
        self.summary.config(state=tk.DISABLED)

    def refresh_summary(self, extra: str = ""):
        if self.project is None:
            self.set_summary(
                "No project is open.\n\n"
                "Create a project to get images/, labels/, classes.txt, and a portable project.yad.json file.\n"
                "Or open an existing .yad.json project that points to your current YOLO image and label folders."
            )
            return
        errors = self.project.validate()
        lines = [
            f"Project: {self.project.name}",
            f"Config: {self.project.config_path}",
            f"Images: {self.project.image_dir}",
            f"Labels: {self.project.label_dir}",
            f"Classes: {self.project.classes_path}",
            f"Class names ({len(self.project.class_names())}): {', '.join(self.project.class_names())}",
        ]
        if errors:
            lines += ["", "Configuration problems:", *[f"- {item}" for item in errors]]
        if extra:
            lines += ["", extra]
        self.set_summary("\n".join(lines))

    def remember_project(self):
        if self.project and self.project.config_path:
            STATE_PATH.write_text(
                json.dumps({"last_project": str(self.project.config_path)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def load_last_project(self):
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            path = Path(state["last_project"])
            if path.exists():
                self.open_project(path)
        except (OSError, KeyError, ValueError, TypeError):
            pass

    def choose_project(self):
        path = filedialog.askopenfilename(
            title="Open YOLO Annotator Desktop project",
            filetypes=[("YAD projects", "*.yad.json"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.open_project(Path(path))

    def open_project(self, path: Path):
        try:
            self.project = load_project(path)
            self.remember_project()
            self.refresh_summary()
        except Exception as exc:
            messagebox.showerror("Open project failed", str(exc))

    def new_project(self):
        root = filedialog.askdirectory(title="Choose a folder for the new project")
        if not root:
            return
        name = simpledialog.askstring("Project name", "Project name:", initialvalue=Path(root).name)
        if name is None:
            return
        classes_text = simpledialog.askstring(
            "Classes",
            "Enter class names separated by commas:",
            initialvalue="object",
        )
        if classes_text is None:
            return
        classes = [item.strip() for item in classes_text.split(",") if item.strip()]
        if not classes:
            messagebox.showerror("Invalid classes", "At least one class is required.")
            return
        try:
            self.project = create_project(root, name, classes)
            self.remember_project()
            self.refresh_summary("Project created. Put images into the images folder, then open the annotator.")
        except Exception as exc:
            messagebox.showerror("Create project failed", str(exc))

    def require_project(self) -> bool:
        if self.project is None:
            messagebox.showinfo("No project", "Create or open a project first.")
            return False
        errors = self.project.validate()
        if errors:
            messagebox.showerror("Project is not ready", "\n".join(errors))
            return False
        return True

    def launch_annotator(self):
        if not self.require_project():
            return
        window = tk.Toplevel(self.root)
        Annotator(
            window,
            self.project.image_dir,
            self.project.label_dir,
            self.project.classes_path,
            keep_empty=self.project.keep_empty,
            order_file=self.project.order_path,
            filter_order=self.project.filter_order,
        )

    def manage_classes(self):
        if self.project is None:
            messagebox.showinfo("No project", "Create or open a project first.")
            return
        ClassManager(
            self.root,
            self.project,
            lambda: self.refresh_summary("Classes updated and existing label IDs were remapped safely."),
        )

    def run_qc(self):
        if not self.require_project():
            return
        report = inspect_project(self.project)
        text = (
            f"Quality check complete\n"
            f"Images: {report['images']}\n"
            f"Labeled: {report['labeled_images']}\n"
            f"Reviewed empty: {report['empty_reviewed_images']}\n"
            f"Unreviewed: {report['unreviewed_images']}\n"
            f"Boxes: {report['boxes']}\n"
            f"Issues: {report['issue_count']}\n"
            f"Class counts: {report['class_counts']}"
        )
        self.refresh_summary(text)
        messagebox.showinfo("Quality check", text)

    def export_dataset(self):
        if not self.require_project():
            return
        output = filedialog.askdirectory(title="Choose export destination")
        if not output:
            return
        try:
            result = export_yolo_dataset(self.project, Path(output))
            text = f"Exported YOLO dataset\nTrain images: {result['train']}\nVal images: {result['val']}\nOutput: {result['output']}"
            self.refresh_summary(text)
            messagebox.showinfo("Export complete", text)
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def open_project_folder(self):
        if self.project is None or self.project.config_path is None:
            return
        folder = str(self.project.config_path.parent)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])


def run(project_path: str = ""):
    root = tk.Tk()
    ProjectHub(root, project_path)
    root.mainloop()
