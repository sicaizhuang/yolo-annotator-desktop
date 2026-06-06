from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .project import ProjectConfig
from .qc import inspect_project
from .safe_io import atomic_write_text
from .widgets import fit_window


class QualityReportDialog(tk.Toplevel):
    def __init__(self, parent, project: ProjectConfig, on_complete=None, on_issue=None, report=None):
        super().__init__(parent)
        self.project = project
        self.on_complete = on_complete
        self.on_issue = on_issue
        self.report = report if report is not None else inspect_project(project)
        self.title("数据质量报告")
        fit_window(self, (920, 620), minimum=(720, 480), margin=(100, 140))
        self.transient(parent)
        self.build_ui()

    def build_ui(self):
        header = ttk.Frame(self, padding=(16, 14, 16, 8))
        header.pack(fill=tk.X)
        ttk.Label(header, text="数据质量报告", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W)
        reviewed = self.report["labeled_images"] + self.report["empty_reviewed_images"]
        ttk.Label(
            header,
            text=(
                f"图片 {self.report['images']}  |  已审核 {reviewed}  |  "
                f"标注框 {self.report['boxes']}  |  "
                f"错误 {self.report['blocking_issue_count']}  |  提醒 {self.report['warning_count']}"
            ),
            foreground="#606770",
        ).pack(anchor=tk.W, pady=(3, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        overview = ttk.Frame(notebook, padding=12)
        issues_tab = ttk.Frame(notebook, padding=8)
        notebook.add(overview, text="概览")
        notebook.add(issues_tab, text=f"问题 ({self.report['issue_count']})")

        overview_scroll = ttk.Scrollbar(overview, orient=tk.VERTICAL)
        overview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        overview_text = tk.Text(
            overview,
            wrap=tk.WORD,
            padx=10,
            pady=10,
            relief=tk.FLAT,
            yscrollcommand=overview_scroll.set,
        )
        overview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        overview_scroll.config(command=overview_text.yview)
        lines = [
            f"项目：{self.report['project']}",
            f"图片：{self.report['images']}",
            f"已标注图片：{self.report['labeled_images']}",
            f"已审核空图：{self.report['empty_reviewed_images']}",
            f"未审核图片：{self.report['unreviewed_images']}",
            f"标注框：{self.report['boxes']}",
            "",
            "类别数量：",
            *[f"  {name}: {count}" for name, count in self.report["class_counts"].items()],
            "",
            "图片尺寸：",
            *[f"  {size}: {count}" for size, count in self.report["image_sizes"].items()],
            "",
            "问题类型：",
            *([f"  {name}: {count}" for name, count in self.report["issue_types"].items()] or ["  无"]),
            "",
            f"阻止导出的错误：{self.report['blocking_issue_count']}",
            f"非阻止性提醒：{self.report['warning_count']}",
        ]
        overview_text.insert("1.0", "\n".join(lines))
        overview_text.config(state=tk.DISABLED)

        columns = ("severity", "type", "file", "detail")
        self.issue_tree = ttk.Treeview(issues_tab, columns=columns, show="headings")
        self.issue_tree.heading("severity", text="级别")
        self.issue_tree.heading("type", text="类型")
        self.issue_tree.heading("file", text="文件")
        self.issue_tree.heading("detail", text="详情")
        self.issue_tree.column("severity", width=70, stretch=False)
        self.issue_tree.column("type", width=190, stretch=False)
        self.issue_tree.column("file", width=360)
        self.issue_tree.column("detail", width=300)
        self.issue_tree.tag_configure("error", foreground="#b42318")
        self.issue_tree.tag_configure("warning", foreground="#8a5a00")
        yscroll = ttk.Scrollbar(issues_tab, orient=tk.VERTICAL, command=self.issue_tree.yview)
        xscroll = ttk.Scrollbar(issues_tab, orient=tk.HORIZONTAL, command=self.issue_tree.xview)
        self.issue_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.issue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for idx, issue in enumerate(self.report["issues"]):
            detail = issue.get("detail", "")
            severity = "错误" if issue.get("severity") == "error" else "提醒"
            self.issue_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(severity, issue["type"], issue.get("file", ""), detail),
                tags=(issue.get("severity", "warning"),),
            )
        self.issue_tree.bind("<Double-Button-1>", lambda _event: self.open_selected())

        footer = ttk.Frame(self, padding=(16, 8, 16, 16))
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="关闭", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(footer, text="保存 JSON 报告...", command=self.save_report).pack(side=tk.RIGHT, padx=8)
        ttk.Button(
            footer,
            text="跳转到问题图片" if self.on_issue else "打开选中文件",
            command=self.open_selected,
        ).pack(side=tk.RIGHT)
        if self.on_complete:
            self.on_complete(
                f"质量检查：{self.report['images']} 张图片，{self.report['boxes']} 个框，"
                f"{self.report['issue_count']} 个问题。"
            )

    def save_report(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="保存质量报告",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            atomic_write_text(path, json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
            messagebox.showinfo("报告已保存", path, parent=self)

    def open_selected(self):
        selection = self.issue_tree.selection()
        if not selection:
            return
        issue = self.report["issues"][int(selection[0])]
        if self.on_issue:
            self.on_issue(issue)
            return
        path = Path(str(issue.get("file", "")))
        if not path.exists():
            messagebox.showinfo("无法打开", "该问题没有可打开的本地文件。", parent=self)
            return
        target = str(path)
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])


class QualityProgressDialog(tk.Toplevel):
    def __init__(self, parent, project: ProjectConfig, on_complete=None, on_issue=None):
        super().__init__(parent)
        self.parent = parent
        self.project = project
        self.on_complete = on_complete
        self.on_issue = on_issue
        self.results = queue.Queue()
        self.title("正在检查数据质量")
        fit_window(self, (420, 130), minimum=(420, 130), margin=(100, 140))
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(self, text="正在读取图片和标签，请稍候…", font=("Segoe UI", 11, "bold")).pack(
            anchor=tk.W,
            padx=18,
            pady=(20, 10),
        )
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=18)
        self.progress.start(12)
        threading.Thread(target=self.worker, daemon=True).start()
        self.after(80, self.poll)

    def worker(self):
        try:
            self.results.put(("ok", inspect_project(self.project)))
        except Exception as exc:
            self.results.put(("error", exc))

    def poll(self):
        try:
            kind, value = self.results.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(80, self.poll)
            return
        self.progress.stop()
        self.grab_release()
        self.destroy()
        if kind == "error":
            messagebox.showerror("质量检查失败", str(value), parent=self.parent)
            return
        QualityReportDialog(
            self.parent,
            self.project,
            self.on_complete,
            self.on_issue,
            report=value,
        )


def open_quality_report(parent, project: ProjectConfig, on_complete=None, on_issue=None):
    return QualityProgressDialog(parent, project, on_complete, on_issue)
