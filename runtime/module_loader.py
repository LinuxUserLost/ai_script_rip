"""
module_loader.py | ai_framework runtime_core/lib
Optional module discovery for the runtime.

Rules:
  - Never imported at top level by any script.
  - Imported inside functions with try/except only.
  - Never auto-loads module logic — only reports presence.
  - Never raises on missing or broken modules.
  - core.py must not import this file.
  - Import direction: scripts/modules → lib. Never lib → scripts/modules.

Usage from a script (inside a function, never at top level):
    try:
        from module_loader import list_available, is_module_available
    except ImportError:
        list_available = lambda: {}
        is_module_available = lambda name: False
"""

import importlib
import sys
from pathlib import Path


# All known module names in declared order.
# This list defines the canonical module set — add new names here only.
KNOWN_MODULES = [
    "learning",
    "analyzer",
    "chat",
    "editor",
    "gui",
    "updater",
]

# Resolved once at import time. modules/ is a sibling of lib/.
_MODULES_DIR = Path(__file__).resolve().parent / "modules"


def _probe(name: str) -> bool:
    """
    Check whether a module folder exists and its is_available() returns True.
    Imports the module's __init__.py in isolation.
    Never raises — returns False on any failure.
    """
    mod_dir = _MODULES_DIR / name
    if not mod_dir.is_dir():
        return False
    init = mod_dir / "__init__.py"
    if not init.exists():
        return False
    try:
        # Build a unique module key to avoid collision with other imports
        mod_key = f"_ai_module_{name}"
        spec    = importlib.util.spec_from_file_location(mod_key, init)
        mod     = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result  = bool(mod.is_available())
        # Remove from sys.modules so repeated calls always re-probe
        sys.modules.pop(mod_key, None)
        return result
    except Exception:
        sys.modules.pop(f"_ai_module_{name}", None)
        return False


def list_available() -> dict:
    """
    Return a dict of {module_name: bool} for all known modules.
    True  = folder present, __init__.py present, is_available() returned True.
    False = absent, broken, or is_available() returned False.
    Order matches KNOWN_MODULES.
    Never raises.
    """
    return {name: _probe(name) for name in KNOWN_MODULES}


def is_module_available(name: str) -> bool:
    """
    Check a single module by name.
    Returns False for unknown names without raising.
    """
    if name not in KNOWN_MODULES:
        return False
    return _probe(name)


def modules_dir() -> Path:
    """
    Return the resolved path to runtime_core/modules/.
    Does not create the directory.
    """
    return _MODULES_DIR


def describe() -> str:
    """
    Return a human-readable summary of module availability.
    Suitable for a debug log line or terminal status display.
    """
    statuses = list_available()
    parts = [
        f"{name}={'yes' if ok else 'no'}"
        for name, ok in statuses.items()
    ]
    return "modules: " + "  ".join(parts)


# ── Module attribute API ───────────────────────────────────────────────────────
# Functions below load a module's __init__.py, call the requested attribute,
# then immediately remove the module from sys.modules.
# Never raises. Returns safe empty values on any failure.

def _load_module_obj(name: str):
    """
    Load a module's __init__.py and return the module object.
    Returns None if absent, broken, or is_available() is False.
    Caller is responsible for popping from sys.modules after use.
    """
    mod_dir = _MODULES_DIR / name
    init    = mod_dir / "__init__.py"
    if not mod_dir.is_dir() or not init.exists():
        return None
    mod_key = f"_ai_modattr_{name}"
    try:
        spec = importlib.util.spec_from_file_location(mod_key, init)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        sys.modules.pop(mod_key, None)
        return None


def get_commands(name: str) -> dict:
    """
    Return the commands dict from a module's commands() function.
    Returns {} if module absent, unavailable, or commands() not defined.
    Format: {command_name: short_description}
    """
    if name not in KNOWN_MODULES:
        return {}
    mod_key = f"_ai_modattr_{name}"
    mod = _load_module_obj(name)
    try:
        if mod is None:
            return {}
        fn = getattr(mod, "commands", None)
        return dict(fn()) if callable(fn) else {}
    except Exception:
        return {}
    finally:
        sys.modules.pop(mod_key, None)


def get_help(name: str) -> str:
    """
    Return the help text string from a module's help_text() function.
    Returns empty string if module absent, unavailable, or help_text() not defined.
    """
    if name not in KNOWN_MODULES:
        return ""
    mod_key = f"_ai_modattr_{name}"
    mod = _load_module_obj(name)
    try:
        if mod is None:
            return ""
        fn = getattr(mod, "help_text", None)
        return str(fn()) if callable(fn) else ""
    except Exception:
        return ""
    finally:
        sys.modules.pop(mod_key, None)


def get_diagnostics(name: str) -> list:
    """
    Return the diagnostics list from a module's diagnostics() function.
    Returns [] if module absent, unavailable, or diagnostics() not defined.
    Each item: {key: str, value: str, status: 'ok' | 'warn' | 'error'}
    """
    if name not in KNOWN_MODULES:
        return []
    mod_key = f"_ai_modattr_{name}"
    mod = _load_module_obj(name)
    try:
        if mod is None:
            return []
        fn = getattr(mod, "diagnostics", None)
        return list(fn()) if callable(fn) else []
    except Exception:
        return []
    finally:
        sys.modules.pop(mod_key, None)


def all_commands() -> dict:
    """
    Return commands for all available modules in one call.
    Format: {module_name: {command_name: description}}
    Skips unavailable or broken modules silently.
    """
    result = {}
    for name in KNOWN_MODULES:
        if _probe(name):
            cmds = get_commands(name)
            if cmds:
                result[name] = cmds
    return result


def all_diagnostics() -> dict:
    """
    Return diagnostics for all available modules in one call.
    Format: {module_name: [diagnostic_items]}
    Skips unavailable or broken modules silently.
    """
    result = {}
    for name in KNOWN_MODULES:
        if _probe(name):
            diags = get_diagnostics(name)
            if diags:
                result[name] = diags
    return result
