"""
modules/gui/__init__.py
Thin delegation wrapper — all logic lives in runtime/app.py.
__file__ = runtime/modules/gui/__init__.py
app.py   = runtime/app.py = Path(__file__).parent.parent.parent / "app.py"
"""
import sys
from pathlib import Path

_APP = Path(__file__).resolve().parent.parent.parent / "app.py"


def _load_app():
    """Load app.py module object. Returns None on any failure."""
    import importlib.util
    if not _APP.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_ai_app", _APP)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules.pop("_ai_app", None)
        return mod
    except Exception:
        sys.modules.pop("_ai_app", None)
        return None


def is_available() -> bool:
    app = _load_app()
    return app.is_available() if app else False

def commands() -> dict:
    app = _load_app()
    return app.commands() if app else {}

def help_text() -> str:
    app = _load_app()
    return app.help_text() if app else ""

def diagnostics() -> list:
    app = _load_app()
    return app.diagnostics() if app else []

def launch(**kwargs) -> bool:
    app = _load_app()
    return app.launch(**kwargs) if app else False

def status(**kwargs) -> dict:
    app = _load_app()
    return app.status(**kwargs) if app else {"can_launch": False}
