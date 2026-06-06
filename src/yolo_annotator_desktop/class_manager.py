from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .project import ProjectConfig, remap_classes


class ClassManager(tk.Toplevel):
    def __init__(self, parent: tk.Misc, project: ProjectConfig, on_saved):
        super().__init__(parent)
        self.project = project
        self.on_saved = on_saved
        self.items: list[dict] = [
            {"original_id": idx, "name": name} for idx, name in enumerate(project.class_names())
        ]
        self.title("Manage Classes")
        self.geometry("520x470")
        self.transient(parent)
        self.grab_set()
        self.build_ui()
        self.refresh()

    def build_ui(self):
        ttk.Label(
            self,
            text="Class order defines YOLO class IDs. Saving creates a label backup and remaps IDs safely.",
            wraplength=470,
        ).pack(fill=tk.X, padx=16, pady=(16, 8))
        self.listbox = tk.Listbox(self, height=16)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=16, pady=4)
        ttk.Button(row, text="Add", command=self.add).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row, text="Rename", command=self.rename).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="Delete", command=self.delete).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="Move Up", command=lambda: self.move(-1)).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="Move Down", command=lambda: self.move(1)).pack(side=tk.LEFT, padx=6)

        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=16, pady=16)
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(footer, text="Save and Remap Labels", command=self.save).pack(side=tk.RIGHT)

    def selected_index(self):
        selection = self.listbox.curselection()
        return selection[0] if selection else None

    def refresh(self, selected: int | None = None):
        self.listbox.delete(0, tk.END)
        for new_id, item in enumerate(self.items):
            old = "new" if item["original_id"] is None else f"old ID {item['original_id']}"
            self.listbox.insert(tk.END, f"{new_id}: {item['name']}  ({old})")
        if selected is not None and 0 <= selected < len(self.items):
            self.listbox.selection_set(selected)
            self.listbox.see(selected)

    def add(self):
        name = simpledialog.askstring("Add class", "New class name:", parent=self)
        if name and name.strip():
            self.items.append({"original_id": None, "name": name.strip()})
            self.refresh(len(self.items) - 1)

    def rename(self):
        idx = self.selected_index()
        if idx is None:
            return
        name = simpledialog.askstring("Rename class", "Class name:", initialvalue=self.items[idx]["name"], parent=self)
        if name and name.strip():
            self.items[idx]["name"] = name.strip()
            self.refresh(idx)

    def delete(self):
        idx = self.selected_index()
        if idx is None:
            return
        item = self.items[idx]
        if messagebox.askyesno(
            "Delete class",
            f"Delete '{item['name']}'?\n\nAll boxes using this class will be removed when you save.",
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
        names = [item["name"] for item in self.items]
        if not names:
            messagebox.showerror("Invalid classes", "At least one class is required.", parent=self)
            return
        if len(names) != len(set(names)):
            messagebox.showerror("Invalid classes", "Class names must be unique.", parent=self)
            return
        old_to_new = {
            item["original_id"]: new_id
            for new_id, item in enumerate(self.items)
            if item["original_id"] is not None
        }
        try:
            result = remap_classes(self.project, names, old_to_new)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Classes saved",
            f"Changed label files: {result['changed_files']}\n"
            f"Remapped boxes: {result['remapped_boxes']}\n"
            f"Dropped boxes: {result['dropped_boxes']}\n"
            f"Label backup: {result['backup'] or 'not needed'}\n"
            f"Classes backup: {result['classes_backup']}",
            parent=self,
        )
        self.on_saved()
        self.destroy()
