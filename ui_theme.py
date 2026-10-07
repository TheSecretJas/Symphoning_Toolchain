# ----------------------------------------------------------------
# FILENAME: ui_theme.py
# PROJECT:  Notenverwaltung Orchester
# AUTHOR:   Jonas Thern
# NOTE:     Kommentare und Formatierung wurden mit Unterstuetzung von
#           kuenstlicher Intelligenz (Claude, Anthropic) erstellt.
# ----------------------------------------------------------------
# Gemeinsames Erscheinungsbild fuer Druckexporter und Sinfonie
# Generator. Nutzt das Sun-Valley-Theme (Windows-11-Optik, sv-ttk)
# und folgt dem hellen/dunklen Systemmodus (darkdetect). Beide Pakete
# sind optional: fehlen sie, laeuft alles im Standard-Theme weiter.
# ----------------------------------------------------------------

import os
from tkinter import font as tkfont
from tkinter import ttk

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

try:
    import darkdetect
except ImportError:
    darkdetect = None


# Farben fuer klassische tk-Widgets (Canvas, Text), die das ttk-Theme
# nicht erfasst. "bg" entspricht dem Fensterhintergrund des Themes.
PALETTES = {
    "light": {
        "bg": "#fafafa", "surface": "#ffffff", "fg": "#1c1c1c",
        "muted": "#6b6b6b", "accent": "#005fb8", "border": "#e0e0e0",
        "error": "#c42b1c", "success": "#0f7b0f", "preview_bg": "#e6e6e6",
    },
    "dark": {
        "bg": "#1c1c1c", "surface": "#2b2b2b", "fg": "#fafafa",
        "muted": "#a0a0a0", "accent": "#57c8ff", "border": "#3a3a3a",
        "error": "#ff99a4", "success": "#6ccb5f", "preview_bg": "#141414",
    },
}


def _system_mode():
    if darkdetect is not None:
        try:
            return "dark" if darkdetect.isDark() else "light"
        except Exception:
            pass
    return "light"


def _dark_title_bar(root):
    """Dunkle Windows-Titelleiste passend zum dunklen Theme."""
    if os.name != "nt":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 20H1+ / 11)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def apply_theme(root):
    """Aktiviert das Theme, legt gemeinsame Stile an, liefert die Palette."""
    mode = _system_mode() if sv_ttk is not None else "light"
    palette = dict(PALETTES[mode])
    style = ttk.Style(root)

    if sv_ttk is not None:
        sv_ttk.set_theme(mode, root)
        if mode == "dark":
            _dark_title_bar(root)
        body = tkfont.nametofont("SunValleyBodyFont")
    else:
        palette["bg"] = style.lookup("TFrame", "background") or palette["bg"]
        body = tkfont.nametofont("TkDefaultFont")

    family, size = body.actual("family"), body.actual("size")
    fonts = {
        "title": tkfont.Font(root, family=family, size=size + 7, weight="bold"),
        "strong": tkfont.Font(root, family=family, size=size, weight="bold"),
        "small": tkfont.Font(root, family=family, size=max(size - 1, 8)),
        "mono": tkfont.Font(root, family="Consolas" if os.name == "nt" else "DejaVu Sans Mono",
                            size=max(size - 1, 8)),
    }
    palette["fonts"] = fonts

    # Hinweis: Im Sun-Valley-Theme wirkt eine Textfarbe aus dem Stil bei
    # Labels nicht. Label-Farben werden deshalb direkt am Widget gesetzt
    # (foreground=palette[...]), die Stile hier liefern nur die Schrift.
    style.configure("Title.TLabel", font=fonts["title"])
    style.configure("Strong.TLabel", font=fonts["strong"])
    style.configure("Muted.TLabel", font=fonts["small"])
    style.configure("Danger.TButton", foreground=palette["error"])
    # Im Standard-Theme gibt es keine roten Rahmen fuer ungueltige Felder
    if sv_ttk is None:
        style.map("TEntry", fieldbackground=[("invalid", "#ffd6d6")])
        style.configure("Accent.TButton", font=fonts["strong"])

    root.configure(bg=palette["bg"])
    return palette


def style_text(widget, palette):
    """Passt ein tk.Text-Widget an die Palette an (flach, ohne 3D-Rand)."""
    widget.configure(bg=palette["surface"], fg=palette["fg"],
                     insertbackground=palette["fg"], relief="flat",
                     highlightthickness=1, highlightbackground=palette["border"],
                     highlightcolor=palette["border"], padx=8, pady=6,
                     font=palette["fonts"]["mono"], borderwidth=0)


def style_canvas(widget, palette, bg_key="bg"):
    widget.configure(bg=palette[bg_key], highlightthickness=0, borderwidth=0)


__all__ = ["apply_theme", "style_text", "style_canvas"]
