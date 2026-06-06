from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .project import ProjectConfig, remap_classes
from .widgets import fit_window


class ClassManager(tk.Toplevel):
    def __init__(self, parent: tk.Misc, project: ProjectConfig, on_saved):
        super().__init__(parent)
        self.project = project
        self.on_saved = on_saved
        self.items: list[dict] = [
            {"original_id": idx, "name": name} for idx, name in enumerate(project.class_names())
        ]
        self.results = queue.Queue()
        self.running = False
        self.title("管理类别")
        fit_window(self, (580, 500), minimum=(500, 420), margin=(100, 140))
        self.transient(parent)
        self.grab_set()
        self.build_ui()
        self.refresh()
        self.listbox.bind("<Double-Button-1>", lambda _event: self.rename())
        self.bind("<Delete>", lambda _event: self.delete())
        self.bind("<Control-s>", lambda _event: self.save())
        if sys.platform == "darwin":
            self.bind("<Command-s>", lambda _event: self.save())

    def build_ui(self):
        ttk.Label(
            self,
            text="类别顺序就是 YOLO 类别 ID。保存前会备份标签与类别文件，并安全重映射已有 ID。",
            wraplength=470,
        ).pack(fill=tk.X, padx=16, pady=(16, 8))
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox = tk.Listbox(list_frame, height=16, yscrollcommand=scrollbar.set)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=16, pady=4)
        self.edit_buttons = []
        for text, command, padx in (
            ("添加", self.add, (0, 6)),
            ("重命名", self.rename, 6),
            ("删除", self.delete, 6),
            ("上移", lambda: self.move(-1), 6),
            ("下移", lambda: self.move(1), 6),
        ):
            button = ttk.Button(row, text=text, command=command)
            button.pack(side=tk.LEFT, padx=padx)
            self.edit_buttons.append(button)

        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=16, pady=16)
        self.cancel_button = ttk.Button(footer, text="取消", command=self.destroy)
        self.cancel_button.pack(side=tk.RIGHT, padx=(6, 0))
        self.save_button = ttk.Button(footer, text="保存并重映射标签", command=self.save)
        self.save_button.pack(side=tk.RIGHT)
        self.progress = ttk.Progressbar(self, mode="indeterminate")

    def selected_index(self):
        selection = self.listbox.curselection()
        return selection[0] if selection else None

    def refresh(self, selected: int | None = None):
        self.listbox.delete(0, tk.END)
        for new_id, item in enumerate(self.items):
            old = "新类别" if item["original_id"] is None else f"原 ID {item['original_id']}"
            self.listbox.insert(tk.END, f"{new_id}: {item['name']}  ({old})")
        if selected is not None and 0 <= selected < len(self.items):
            self.listbox.selection_set(selected)
            self.listbox.see(selected)

    def add(self):
        name = simpledialog.askstring("添加类别", "新类别名称：", parent=self)
        if name and name.strip():
            name = name.strip()
            if name in [item["name"] for item in self.items]:
                messagebox.showerror("类别已存在", f"类别“{name}”已经存在。", parent=self)
                return
            self.items.append({"original_id": None, "name": name})
            self.refresh(len(self.items) - 1)

    def rename(self):
        idx = self.selected_index()
        if idx is None:
            return
        name = simpledialog.askstring("重命名类别", "类别名称：", initialvalue=self.items[idx]["name"], parent=self)
        if name and name.strip():
            name = name.strip()
            if name in [item["name"] for pos, item in enumerate(self.items) if pos != idx]:
                messagebox.showerror("类别已存在", f"类别“{name}”已经存在。", parent=self)
                return
            self.items[idx]["name"] = name
            self.refresh(idx)

    def delete(self):
        idx = self.selected_index()
        if idx is None:
            return
        item = self.items[idx]
        if messagebox.askyesno(
            "删除类别",
            f"删除“{item['name']}”？\n\n保存时，使用该类别的所有标注框都会被删除。",
            parent=self,
        ):
            self.items.pop(idx)
            self.refresh(min(idx, len(self.items) - 1))

    def move(self, delta: int):
        idx = self.selected_index()
        if idx is None:
            return
        target = idx + delta
        if 0 <= target < len(self.items):
            self.items[idx], self.items[target] = self.items[target], self.items[idx]
            self.refresh(target)

    def save(self):
        if self.running:
            return
        names = [item["name"] for item in self.items]
        if not names:
            messagebox.showerror("类别无效", "至少需要保留一个类别。", parent=self)
            return
        if len(names) != len(set(names)):
            messagebox.showerror("类别无效", "类别名称不能重复。", parent=self)
            return
        old_to_new = {
            item["original_id"]: new_id
            for new_id, item in enumerate(self.items)
            if item["original_id"] is not None
        }
        self.running = True
        self.save_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.DISABLED)
        self.listbox.config(state=tk.DISABLED)
        for button in self.edit_buttons:
            button.config(state=tk.DISABLED)
        self.progress.pack(fill=tk.X, padx=16, pady=(0, 12))
        self.progress.start(12)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        threading.Thread(target=self.save_worker, args=(names, old_to_new), daemon=True).start()
        self.after(80, self.poll_save)

    def save_worker(self, names, old_to_new):
        try:
            result = remap_classes(self.project, names, old_to_new)
        except Exception as exc:
            self.results.put(("error", exc))
            return
        self.results.put(("ok", result))

    def poll_save(self):
        try:
            kind, value = self.results.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(80, self.poll_save)
            return
        self.running = False
        self.progress.stop()
        self.progress.pack_forget()
        self.save_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.NORMAL)
        self.listbox.config(state=tk.NORMAL)
        for button in self.edit_buttons:
            button.config(state=tk.NORMAL)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        if kind == "error":
            messagebox.showerror("保存失败", str(value), parent=self)
            return
        result = value
        messagebox.showinfo(
            "类别已保存",
            f"修改的标签文件：{result['changed_files']}\n"
            f"重映射的标注框：{result['remapped_boxes']}\n"
            f"删除的标注框：{result['dropped_boxes']}\n"
            f"标签备份：{result['backup'] or '无需备份'}\n"
            f"类别备份：{result['classes_backup']}",
            parent=self,
        )
        self.on_saved()
        self.destroy()
