# Module API Reference

**Level:** Developer  
**File:** `runtime_core/lib/module_loader.py`

---

## Module contract

Every module in `modules/*/` must provide an `__init__.py` with exactly
these four exports. All four must never raise under any circumstances.

```python
def is_available() -> bool:
    """Can this module be used right now?"""
    ...

def commands() -> dict:
    """{command_name: short_description}"""
    ...

def help_text() -> str:
    """Multi-line help string."""
    ...

def diagnostics() -> list:
    """[{key: str, value: str, status: 'ok'|'warn'|'error'}]"""
    ...
```

---

## `is_available()`

- Called by `module_loader._probe()` on every availability check
- Must return `bool` — never raise
- If your module needs an external tool, check for it here
- The gui module uses this to check `import tkinter`
- Example: a module requiring `git` would do `shutil.which("git") is not None`

```python
def is_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False
```

---

## `commands()`

- Returns a flat dict of `{command: one-line description}`
- Commands are names for planned or implemented features
- No maximum on command count — keep descriptions under 60 characters
- Commands are not callable through `module_loader` — they are metadata only

```python
def commands() -> dict:
    return {
        "scan":   "Scan vault folders for structural issues",
        "report": "Generate a health report",
    }
```

---

## `help_text()`

- Returns a multi-line string
- Plain text only — no ANSI codes, no Markdown formatting
- Should include: module name, purpose, all commands with one-line descriptions,
  any important caveats
- Displayed in the GUI Help tab and in any terminal help viewer

```python
def help_text() -> str:
    return (
        "analyzer module\n"
        "\n"
        "Read-only diagnostics...\n"
        "\n"
        "Commands:\n"
        "  scan  -- ...\n"
    )
```

---

## `diagnostics()`

Returns a list of dicts. Each dict has exactly three keys:

| Key | Type | Values |
|---|---|---|
| `key` | `str` | Short identifier (no spaces) |
| `value` | `str` | Human-readable current value |
| `status` | `str` | `"ok"`, `"warn"`, or `"error"` |

Status semantics:
- `ok` — this item is present and working
- `warn` — missing or degraded but the module can still function
- `error` — missing and required for this module to work

```python
def diagnostics() -> list:
    import shutil
    found = shutil.which("wl-copy") is not None
    return [{
        "key":    "wl-copy",
        "value":  shutil.which("wl-copy") or "not found",
        "status": "ok" if found else "warn",
    }]
```

---

## module_loader public API

All functions return safe empty values on any failure and never raise.

```python
import module_loader as ml

# Availability
ml.list_available()          # {name: bool} for all known modules
ml.is_module_available(name) # bool for one module
ml.describe()                # "modules: learning=yes  gui=no  ..."

# Module path
ml.modules_dir()             # Path to runtime_core/modules/

# Attribute queries (return empty values if module unavailable)
ml.get_commands(name)        # dict
ml.get_help(name)            # str
ml.get_diagnostics(name)     # list

# Bulk queries (available modules only)
ml.all_commands()            # {module: {command: desc}}
ml.all_diagnostics()         # {module: [diag_items]}
```

---

## How `_probe()` works

```
1. Resolve _MODULES_DIR / name / __init__.py
2. Load __init__.py with importlib.util.spec_from_file_location
3. Call is_available()
4. Pop sys.modules[key] to prevent caching
5. Return bool result
```

`_probe()` is called once per module per `list_available()` call.
The `sys.modules.pop()` ensures repeated calls always re-probe from disk.
This means a module can be enabled or disabled at runtime by editing its
`__init__.py` — no restart required.

---

## Adding a module

1. Create `modules/mymodule/` and `modules/mymodule/__init__.py`
2. Implement `is_available()`, `commands()`, `help_text()`, `diagnostics()`
3. Add `"mymodule"` to `KNOWN_MODULES` list in `module_loader.py`
4. The module is now discoverable — no other changes needed

**Rules for new modules:**
- No top-level imports of `core`, `flow`, `warn`, or `module_loader`
- All external imports go inside functions with `try/except`
- No absolute paths — use `Path(__file__).resolve().parent` to navigate
- `is_available()` must return `True` only when the module is genuinely usable
- A broken module must return `False` from `is_available()`, not raise

---

## sys.modules key convention

Probe keys: `_ai_module_{name}` (used by `_probe()`)  
Attribute keys: `_ai_modattr_{name}` (used by `_load_module_obj()`)  
GUI app key: `_ai_gui_app`

All are popped from `sys.modules` immediately after use.

---

*See also: [Module Guide](../intermediate/module_guide.md), [GUI Guide](gui_guide.md)*
