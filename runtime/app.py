"""
app.py | ai_framework runtime/
GUI dashboard. Tkinter window + availability API.

Merged from: modules/gui/__init__.py + modules/gui/app.py
Location: runtime/app.py (same directory as core.py, flow.py, warn.py)

Rules:
  - is_available() never raises even without tkinter.
  - launch() only opens a window if all three gates pass.
  - All data gathering happens before any tkinter import.
  - No automatic launch. Caller must call launch() explicitly.
  - No absolute paths.
"""

import os
import sys
from pathlib import Path

# ── Runtime dir (same dir as this file) ───────────────────────────────────────
_RUNTIME_DIR = Path(__file__).resolve().parent


# ══════════════════════════════════════════════════════════════════════════════
# Public API (safe to call without tkinter)
# ══════════════════════════════════════════════════════════════════════════════

def is_available() -> bool:
    """Returns True only if tkinter is importable. Never raises."""
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False


def commands() -> dict:
    return {
        "launch": "Launch the GUI dashboard (requires tkinter + display)",
        "status": "Show GUI availability and environment info",
    }


def help_text() -> str:
    marker = "AVAILABLE" if is_available() else "NOT AVAILABLE (tkinter missing)"
    return (
        f"gui / app.py  [{marker}]\n"
        "\n"
        "Tkinter dashboard for the ai_framework runtime.\n"
        "Shows module status, warnings, commands, and help in one window.\n"
        "\n"
        "Tabs:\n"
        "  Status   -- module availability and per-module diagnostics\n"
        "  Warnings -- runtime warnings (severity colour-coded)\n"
        "  Commands -- all available module commands\n"
        "  Help     -- per-module help text browser\n"
        "\n"
        "Commands:\n"
        "  launch   -- open the dashboard window\n"
        "  status   -- print GUI availability to the terminal\n"
        "\n"
        "No features are GUI-only. Terminal interface is always full-capability.\n"
        "No automatic launch. Must be called explicitly.\n"
    )


def diagnostics() -> list:
    results = []
    try:
        import tkinter
        results.append({"key": "tkinter", "value": f"Tk {tkinter.TkVersion}", "status": "ok"})
    except ImportError:
        results.append({"key": "tkinter", "value": "not available", "status": "error"})

    display = os.environ.get("DISPLAY", "")
    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    results.append({
        "key":    "display",
        "value":  f"DISPLAY={display!r}  WAYLAND={wayland!r}",
        "status": "ok" if (display or wayland) else "warn",
    })
    results.append({
        "key":    "app.py",
        "value":  str(Path(__file__).resolve()),
        "status": "ok",
    })
    return results


def status(verbose: bool = False) -> dict:
    """
    Return availability status dict without launching the window.
    Keys: tkinter_available, display_available, app_file_present, can_launch.
    Adds 'diagnostics' list when verbose=True.
    Never raises.
    """
    tk_ok   = is_available()
    disp_ok = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    result  = {
        "tkinter_available": tk_ok,
        "display_available": disp_ok,
        "app_file_present":  True,   # this file is app.py itself
        "can_launch":        tk_ok and disp_ok,
    }
    if verbose:
        result["diagnostics"] = diagnostics()
    return result


def launch(runtime_dir=None, sysconf=None, conf_dir=None, modules_dir=None) -> bool:
    """
    Launch the GUI window.
    Returns True if opened and closed normally.
    Returns False if any gate fails. Never raises.
    Gates: (1) tkinter available  (2) display present  (3) no import error
    """
    if not is_available():
        print("\n  [gui] tkinter not available. Use terminal interface instead.\n")
        return False
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("\n  [gui] No display detected (DISPLAY / WAYLAND_DISPLAY unset).\n")
        return False

    rt  = Path(runtime_dir).resolve() if runtime_dir else _RUNTIME_DIR
    sc  = sysconf or _load_sysconf(rt)
    cd  = conf_dir    or (rt / "configs")
    md  = modules_dir or (rt / "modules")

    try:
        win = AppWindow(runtime_dir=rt, sysconf=sc, conf_dir=cd, modules_dir=md)
        win.run()
        return True
    except Exception as e:
        print(f"\n  [gui] launch error: {e}\n")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Data loader (all lib access; isolated from widgets)
# ══════════════════════════════════════════════════════════════════════════════

def _load_data(runtime_dir=None, sysconf=None, conf_dir=None, modules_dir=None):
    """
    Gather all display content before any widget is created.
    Each section is independently try/except-wrapped.
    Returns dict with keys: availability, diagnostics, warnings, commands, help.
    """
    data = {"availability": {}, "diagnostics": {}, "warnings": [], "commands": {}, "help": {}}

    rt_dir = Path(runtime_dir).resolve() if runtime_dir else _RUNTIME_DIR
    lib    = rt_dir
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))

    try:
        import module_loader as ml
        data["availability"] = ml.list_available()
        data["commands"]     = ml.all_commands()
        data["diagnostics"]  = ml.all_diagnostics()
        data["help"]         = {
            name: ml.get_help(name)
            for name in ml.KNOWN_MODULES
            if data["availability"].get(name)
        }
    except Exception:
        pass

    try:
        import warn as w
        sc = sysconf or {}
        cd = conf_dir    or (rt_dir / "configs")
        md = modules_dir or (rt_dir / "modules")
        data["warnings"] = w.run_checks(rt_dir, sc, conf_dir=cd, modules_dir=md)
    except Exception:
        pass

    return data


# ══════════════════════════════════════════════════════════════════════════════
# Tkinter window (only reached after is_available() == True)
# ══════════════════════════════════════════════════════════════════════════════

import tkinter as tk
from tkinter import ttk

BG       = "#1e1e1e"
BG_PANEL = "#2a2a2a"
BG_ROW   = "#2e2e2e"
BG_ALT   = "#252525"
FG       = "#e0e0e0"
FG_DIM   = "#808080"
FG_OK    = "#5faf5f"
FG_WARN  = "#cfcf4f"
FG_ERR   = "#cf5f5f"
FG_HEAD  = "#5fafcf"
FONT     = ("Monospace", 10)
FONT_H   = ("Monospace", 10, "bold")
FONT_SM  = ("Monospace", 9)
PAD      = 8


def _sc(status):
    return {"ok": FG_OK, "warn": FG_WARN, "error": FG_ERR}.get(status, FG_DIM)

def _sev_c(severity):
    return {0: FG_OK, 1: FG_WARN, 2: FG_ERR}.get(severity, FG_DIM)


def _build_status_tab(parent, data):
    frame = tk.Frame(parent, bg=BG_PANEL)
    tk.Label(frame, text="Module Status", font=FONT_H, bg=BG_PANEL, fg=FG_HEAD, anchor="w").pack(fill="x", padx=PAD, pady=(PAD, 2))
    avail = data.get("availability", {})
    for i, (name, ok) in enumerate(avail.items()):
        row = tk.Frame(frame, bg=BG_ROW if i % 2 == 0 else BG_ALT)
        row.pack(fill="x", padx=PAD, pady=1)
        col  = FG_OK if ok else FG_DIM
        tk.Label(row, text=f"  {'●' if ok else '○'}  {name}", font=FONT, bg=row["bg"], fg=col, anchor="w", width=18).pack(side="left")
        tk.Label(row, text="available" if ok else "not available", font=FONT_SM, bg=row["bg"], fg=col, anchor="w").pack(side="left")
    tk.Label(frame, text="\nDiagnostics", font=FONT_H, bg=BG_PANEL, fg=FG_HEAD, anchor="w").pack(fill="x", padx=PAD, pady=(PAD, 2))
    for mod_name, items in data.get("diagnostics", {}).items():
        tk.Label(frame, text=f"  {mod_name}", font=FONT_H, bg=BG_PANEL, fg=FG, anchor="w").pack(fill="x", padx=PAD)
        for item in items:
            tk.Label(frame, text=f"    {item['key']:20}  {item.get('value','')}", font=FONT_SM, bg=BG_PANEL, fg=_sc(item.get("status","warn")), anchor="w").pack(fill="x", padx=PAD)
    return frame


def _build_warnings_tab(parent, data):
    frame    = tk.Frame(parent, bg=BG_PANEL)
    warnings = data.get("warnings", [])
    if not warnings:
        tk.Label(frame, text="\n  ✓  No warnings", font=FONT_H, bg=BG_PANEL, fg=FG_OK, anchor="w").pack(fill="x", padx=PAD, pady=PAD)
        return frame
    tk.Label(frame, text="Runtime Warnings", font=FONT_H, bg=BG_PANEL, fg=FG_HEAD, anchor="w").pack(fill="x", padx=PAD, pady=(PAD, 2))
    sev_labels = {0: "GREEN", 1: "YELLOW", 2: "RED"}
    icons      = {0: "✓", 1: "⚠", 2: "✗"}
    for w in warnings:
        sev = w.get("severity", 1)
        col = _sev_c(sev)
        row = tk.Frame(frame, bg=BG_ROW, padx=PAD, pady=2)
        row.pack(fill="x", padx=PAD, pady=2)
        tk.Label(row, text=f"{icons.get(sev,'?')}  [{sev_labels.get(sev,'?')}]", font=FONT_H, bg=BG_ROW, fg=col, anchor="w", width=14).pack(side="left")
        tk.Label(row, text=w.get("message",""), font=FONT, bg=BG_ROW, fg=FG, anchor="w").pack(side="left")
        if w.get("detail"):
            tk.Label(frame, text=f"     {w['detail']}", font=FONT_SM, bg=BG_PANEL, fg=FG_DIM, anchor="w").pack(fill="x", padx=PAD)
    return frame


def _build_commands_tab(parent, data):
    frame    = tk.Frame(parent, bg=BG_PANEL)
    commands = data.get("commands", {})
    tk.Label(frame, text="Module Commands", font=FONT_H, bg=BG_PANEL, fg=FG_HEAD, anchor="w").pack(fill="x", padx=PAD, pady=(PAD, 2))
    if not commands:
        tk.Label(frame, text="  No modules available.", font=FONT, bg=BG_PANEL, fg=FG_DIM, anchor="w").pack(padx=PAD, pady=PAD)
        return frame
    for mod_name, cmds in commands.items():
        tk.Label(frame, text=f"\n  {mod_name}", font=FONT_H, bg=BG_PANEL, fg=FG, anchor="w").pack(fill="x", padx=PAD)
        for cmd, desc in cmds.items():
            row = tk.Frame(frame, bg=BG_PANEL)
            row.pack(fill="x", padx=PAD)
            tk.Label(row, text=f"    {cmd}", font=FONT, bg=BG_PANEL, fg=FG_HEAD, anchor="w", width=14).pack(side="left")
            tk.Label(row, text=desc, font=FONT_SM, bg=BG_PANEL, fg=FG_DIM, anchor="w").pack(side="left")
    return frame


def _build_help_tab(parent, data):
    frame   = tk.Frame(parent, bg=BG_PANEL)
    help_d  = data.get("help", {})
    modules = list(help_d.keys())
    if not modules:
        tk.Label(frame, text="  No help available.", font=FONT, bg=BG_PANEL, fg=FG_DIM, anchor="w").pack(padx=PAD, pady=PAD)
        return frame
    pane = tk.PanedWindow(frame, orient="horizontal", bg=BG, sashwidth=4)
    pane.pack(fill="both", expand=True)
    left  = tk.Frame(pane, bg=BG_PANEL, width=140)
    right = tk.Frame(pane, bg=BG_PANEL)
    pane.add(left); pane.add(right)
    text_w = tk.Text(right, bg=BG_PANEL, fg=FG, font=FONT_SM, relief="flat", wrap="word", state="disabled", padx=PAD, pady=PAD)
    text_w.pack(fill="both", expand=True)
    def _show(name):
        text_w.config(state="normal"); text_w.delete("1.0","end")
        text_w.insert("end", help_d.get(name,"No help available.")); text_w.config(state="disabled")
    for name in modules:
        tk.Button(left, text=f"  {name}", font=FONT, bg=BG_ROW, fg=FG, activebackground=BG_ALT,
                  activeforeground=FG_HEAD, relief="flat", anchor="w", padx=PAD,
                  command=lambda n=name: _show(n)).pack(fill="x", pady=1)
    if modules:
        _show(modules[0])
    return frame


class AppWindow:
    """Main GUI window. Instantiated and run by launch(). Never auto-instantiated."""

    def __init__(self, runtime_dir=None, sysconf=None, conf_dir=None, modules_dir=None):
        self._data = _load_data(runtime_dir, sysconf, conf_dir, modules_dir)

    def run(self):
        root = tk.Tk()
        root.title("ai_framework — runtime dashboard")
        root.configure(bg=BG)
        root.geometry("820x560")
        root.minsize(600, 400)

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",     background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_PANEL, foreground=FG, padding=[10,4], font=FONT)
        style.map("TNotebook.Tab", background=[("selected", BG_ROW)], foreground=[("selected", FG_HEAD)])

        for label, builder in [
            ("Status",   _build_status_tab),
            ("Warnings", _build_warnings_tab),
            ("Commands", _build_commands_tab),
            ("Help",     _build_help_tab),
        ]:
            tab = builder(nb, self._data)
            tab.pack(fill="both", expand=True)
            nb.add(tab, text=f"  {label}  ")

        root.mainloop()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_sysconf(runtime_dir: Path) -> dict:
    try:
        import json
        cf = runtime_dir / "configs" / "system_config.json"
        if cf.exists():
            return json.loads(cf.read_text())
    except Exception:
        pass
    return {}
