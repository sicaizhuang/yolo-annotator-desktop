from __future__ import annotations

import math
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk


def fit_window(window, preferred, minimum=(480, 360), margin=(80, 120), position=(20, 20)):
    available_width = max(480, window.winfo_screenwidth() - margin[0])
    available_height = max(360, window.winfo_screenheight() - margin[1])
    width = min(preferred[0], available_width)
    height = min(preferred[1], available_height)
    window.geometry(f"{width}x{height}+{position[0]}+{position[1]}")
    window.minsize(min(minimum[0], width), min(minimum[1], height))
    return width, height


def set_app_icon(window):
    image = Image.new("RGBA", (64, 64), (25, 28, 32, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 56, 56), radius=7, outline=(244, 247, 250, 255), width=4)
    draw.rectangle((17, 18, 43, 40), outline=(38, 154, 255, 255), width=4)
    draw.line((25, 45, 32, 52, 51, 29), fill=(42, 205, 120, 255), width=5, joint="curve")
    icon = ImageTk.PhotoImage(image, master=window)
    window.iconphoto(True, icon)
    window._yad_app_icon = icon


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


class IconSet:
    """Small familiar bitmap icons that do not depend on system symbol fonts."""

    def __init__(self, master, size=20, color="#222222", accent="#1473e6"):
        self.master = master
        self.size = size
        self.color = color
        self.accent = accent
        self.cache = {}

    def get(self, name):
        if name not in self.cache:
            image = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            getattr(self, f"_draw_{name}")(draw)
            self.cache[name] = ImageTk.PhotoImage(image, master=self.master)
        return self.cache[name]

    def _line(self, draw, points, fill=None, width=2):
        draw.line(points, fill=fill or self.color, width=width, joint="curve")

    def _draw_folder(self, draw):
        self._line(draw, [(2, 7), (7, 7), (9, 4), (18, 4), (18, 16), (2, 16), (2, 7)])
        self._line(draw, [(2, 8), (18, 8)])

    def _draw_save(self, draw):
        self._line(draw, [(4, 2), (15, 2), (18, 5), (18, 18), (3, 18), (3, 2), (4, 2)])
        self._line(draw, [(6, 2), (6, 8), (14, 8), (14, 2)])
        draw.rectangle((6, 12, 15, 17), outline=self.color, width=2)

    def _draw_undo(self, draw):
        self._line(draw, [(8, 5), (3, 9), (8, 13)])
        draw.arc((4, 5, 18, 18), 205, 350, fill=self.color, width=2)

    def _draw_redo(self, draw):
        self._line(draw, [(12, 5), (17, 9), (12, 13)])
        draw.arc((2, 5, 16, 18), 190, 335, fill=self.color, width=2)

    def _draw_eye_off(self, draw):
        draw.arc((2, 5, 18, 17), 190, 350, fill=self.color, width=2)
        draw.arc((2, 3, 18, 15), 10, 170, fill=self.color, width=2)
        draw.ellipse((8, 7, 12, 11), outline=self.color, width=2)
        self._line(draw, [(3, 2), (18, 17)], fill="#cc3333", width=2)

    def _draw_rect(self, draw):
        draw.rectangle((3, 4, 17, 16), outline=self.accent, width=2)

    def _draw_select(self, draw):
        draw.polygon([(4, 2), (4, 17), (8, 13), (11, 19), (14, 17), (11, 12), (17, 12)], fill=self.color)

    def _draw_obb(self, draw):
        draw.polygon([(4, 7), (14, 3), (17, 13), (7, 17)], outline=self.accent)
        self._line(draw, [(4, 7), (14, 3), (17, 13), (7, 17), (4, 7)], fill=self.accent)

    def _draw_previous(self, draw):
        draw.polygon([(14, 3), (5, 10), (14, 17)], fill=self.color)

    def _draw_next(self, draw):
        draw.polygon([(6, 3), (15, 10), (6, 17)], fill=self.color)

    def _draw_next_unreviewed(self, draw):
        self._line(draw, [(3, 10), (7, 14), (13, 5)], fill="#16803c", width=2)
        draw.polygon([(13, 8), (19, 12), (13, 16)], fill=self.color)

    def _draw_add(self, draw):
        self._line(draw, [(10, 3), (10, 17)], fill=self.accent)
        self._line(draw, [(3, 10), (17, 10)], fill=self.accent)

    def _draw_manage(self, draw):
        for y, x in ((5, 7), (10, 13), (15, 9)):
            self._line(draw, [(3, y), (17, y)])
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill="#ffffff", outline=self.color, width=2)

    def _draw_tag(self, draw):
        self._line(draw, [(3, 4), (12, 4), (18, 10), (11, 17), (3, 9), (3, 4)])
        draw.ellipse((6, 6, 9, 9), fill=self.color)

    def _draw_trash(self, draw):
        self._line(draw, [(5, 6), (16, 6)])
        self._line(draw, [(7, 6), (8, 18), (14, 18), (15, 6)])
        self._line(draw, [(8, 3), (14, 3), (15, 6), (7, 6), (8, 3)])

    def _draw_deselect(self, draw):
        draw.ellipse((3, 3, 17, 17), outline=self.color, width=2)
        self._line(draw, [(7, 7), (13, 13)], fill="#cc3333")
        self._line(draw, [(13, 7), (7, 13)], fill="#cc3333")

    def _draw_qc(self, draw):
        self._line(draw, [(3, 3), (14, 3), (14, 16), (3, 16), (3, 3)])
        self._line(draw, [(6, 7), (8, 9), (12, 5)], fill="#16803c")
        self._line(draw, [(6, 13), (9, 13)])
        draw.ellipse((12, 12, 18, 18), outline=self.accent, width=2)
        self._line(draw, [(17, 17), (19, 19)], fill=self.accent)

    def _draw_export(self, draw):
        self._line(draw, [(3, 13), (3, 18), (17, 18), (17, 13)])
        self._line(draw, [(10, 2), (10, 14)], fill=self.accent)
        self._line(draw, [(5, 9), (10, 14), (15, 9)], fill=self.accent)

    def _draw_help(self, draw):
        draw.ellipse((3, 3, 17, 17), outline=self.color, width=2)
        draw.text((7, 3), "?", fill=self.color)

    def _draw_copy(self, draw):
        draw.rectangle((6, 3, 17, 14), outline=self.color, width=2)
        draw.rectangle((3, 6, 14, 17), outline=self.accent, width=2)

    def _draw_empty(self, draw):
        draw.rectangle((3, 3, 17, 17), outline=self.color, width=2)
        self._line(draw, [(6, 10), (9, 13), (15, 6)], fill="#16803c", width=2)

    def _draw_browser(self, draw):
        draw.rectangle((2, 3, 18, 17), outline=self.color, width=2)
        self._line(draw, [(7, 3), (7, 17)])
        for y in (7, 11, 15):
            self._line(draw, [(3, y), (6, y)], fill=self.accent)


def icon_button(parent, image, tooltip: str, command, *, variable=None, value=None):
    options = {
        "image": image,
        "width": 28,
        "height": 28,
        "takefocus": False,
        "padx": 1,
        "pady": 1,
    }
    if variable is None:
        button = tk.Button(parent, command=command, **options)
    else:
        button = tk.Radiobutton(
            parent,
            indicatoron=False,
            variable=variable,
            value=value,
            command=command,
            selectcolor="#dceeff",
            **options,
        )
    button.image = image
    Tooltip(button, tooltip)
    return button
