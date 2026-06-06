from __future__ import annotations

import tkinter as tk


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.window = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _event=None):
        if self.window is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.window,
            text=self.text,
            bg="#222222",
            fg="#ffffff",
            padx=7,
            pady=4,
            relief=tk.SOLID,
            borderwidth=1,
        ).pack()

    def hide(self, _event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None


def icon_button(parent, text: str, tooltip: str, command, *, width: int = 2, variable=None, value=None):
    if variable is None:
        button = tk.Button(parent, text=text, width=width, command=command, takefocus=False)
    else:
        button = tk.Radiobutton(
            parent,
            text=text,
            width=width,
            indicatoron=False,
            variable=variable,
            value=value,
            command=command,
            takefocus=False,
            selectcolor="#dceeff",
        )
    Tooltip(button, tooltip)
    return button
