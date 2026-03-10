# GUI Guide

**Level:** Developer  
**Files:** `modules/gui/__init__.py`, `modules/gui/app.py`

---

## Design principles

1. **GUI is never required.** The runtime functions identically without it.
2. **No auto-launch.** The window only opens when `launch()` is called explicitly.
3. **Data before widgets.** All data gathering happens in `_load_data()` before
   any tkinter object is created.
4. **Three gates before launch.** `is_available()` → display present → `app.py`
   present. All three must pass.
5. **Terminal parity.** Every piece of information shown in the GUI is also
   accessible from the terminal. No GUI-only features.

---

## File responsibilities

| File | Responsibility |
|---|---|
| `__init__.py` | Availability check, public API (`launch`, `status`), no tkinter at top level |
| `app.py` | Tkinter window definition. Only imported after all three gates pass. |

`__init__.py` has zero top-level tkinter imports. `app.py` imports tkinter at
the module level — that is safe because it is only ever loaded by `launch()`
after `is_available()` has confirmed tkinter is present.

---

## Launch contract

```python
def launch(
    runtime_dir  = None,   # Path to runtime_core/. Resolved from __file__ if omitted.
    sysconf      = None,   # system_config dict. Loaded from conf/ if omitted.
    conf_dir     = None,   # Path to conf/. Resolved from runtime_dir if omitted.
    modules_dir  = None,   # Path to modules/. Resolved from runtime_dir if omitted.
) -> bool:
```

Returns:
- `True` — window was opened and the user closed it normally
- `False` — one of the three gates failed, or an exception occurred

Never raises. Prints a message to the terminal if a gate fails.

---

## Three gates

```python
# Gate 1: tkinter importable
if not is_available():
    print("[gui] tkinter not available")
    return False

# Gate 2: display present
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    print("[gui] no display detected")
    return False

# Gate 3: app.py present
if not (Path(__file__).parent / "app.py").exists():
    print("[gui] app.py missing")
    return False
```

If all three pass, `app.py` is loaded via `importlib.util`, `AppWindow` is
instantiated, `run()` is called, and the import key is popped from `sys.modules`.

---

## `status()` API

```python
s = gui.status()
# {
#   "tkinter_available": bool,
#   "display_available": bool,
#   "app_file_present":  bool,
#   "can_launch":        bool,   # True only if all three are True
# }

s = gui.status(verbose=True)
# Same as above, plus:
# {
#   "diagnostics": [
#     {"key": "tkinter", "value": "Tk 8.6", "status": "ok"},
#     {"key": "display", "value": "DISPLAY=':1'  WAYLAND=''", "status": "ok"},
#     {"key": "app.py",  "value": "/path/to/app.py", "status": "ok"},
#   ]
# }
```

---

## app.py structure

```
_load_data()         — gathers all data before any widget is created
    imports module_loader → list_available, all_commands, all_diagnostics, get_help
    imports warn         → run_checks
    returns: {availability, diagnostics, warnings, commands, help}

AppWindow.__init__() — stores data, no tkinter yet
AppWindow.run()      — creates root window, builds notebook, calls mainloop()

_build_status_tab()   — module availability + diagnostics summary
_build_warnings_tab() — runtime warnings with severity colour
_build_commands_tab() — all module commands, grouped by module
_build_help_tab()     — PanedWindow: module selector left, Text right
```

---

## Colour palette

The GUI uses a dark theme matched to the terminal ANSI palette:

| Constant | Hex | Used for |
|---|---|---|
| `BG` | `#1e1e1e` | Main window background |
| `BG_PANEL` | `#2a2a2a` | Tab and panel backgrounds |
| `FG` | `#e0e0e0` | Normal text |
| `FG_OK` | `#5faf5f` | OK / green / available |
| `FG_WARN` | `#cfcf4f` | Warning / yellow |
| `FG_ERR` | `#cf5f5f` | Error / red |
| `FG_HEAD` | `#5fafcf` | Headers and selected items |

---

## Extending the GUI

To add a new tab:

1. Write a `_build_mytab_tab(parent, data)` function in `app.py`
2. The function receives the `tk.Frame` parent and the `data` dict from `_load_data()`
3. Return the built frame — `AppWindow.run()` will add it to the notebook
4. Add data your tab needs to `_load_data()` under a new key
5. No imports at module level — all inside functions

To add a new data source to `_load_data()`:

```python
try:
    # your import here
    data["my_key"] = ...
except Exception:
    data["my_key"] = {}  # safe empty default
```

Each section of `_load_data()` is independently `try/except`-wrapped.
A broken source cannot prevent the window from opening.

---

## Calling launch() from a script

Never call at top level. Always inside a function, after checking availability:

```python
def open_dashboard(runtime_dir, sysconf):
    try:
        from module_loader import is_module_available
        if not is_module_available("gui"):
            print("GUI not available on this system.")
            return
        # Load gui __init__ via importlib to avoid top-level import
        import importlib.util, sys
        from pathlib import Path
        gui_init = Path(runtime_dir) / "modules" / "gui" / "__init__.py"
        spec = importlib.util.spec_from_file_location("_gui_entry", gui_init)
        gui  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gui)
        gui.launch(runtime_dir=runtime_dir, sysconf=sysconf)
        sys.modules.pop("_gui_entry", None)
    except Exception as e:
        print(f"GUI error: {e}")
```

---

*See also: [Module API](module_api.md), [Build Steps](build_steps.md)*
