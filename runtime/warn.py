"""
warn.py | ai_framework runtime_core/lib
Optional warning and status indicator system.

Severity levels:
  GREEN  = 0  — safe, informational
  YELLOW = 1  — warning, degraded but functional
  RED    = 2  — risk, possible data corruption or critical misconfiguration

Rules:
  - Never imported at top level by any script.
  - Imported inside a function with try/except only.
  - No automatic exit. Only display unless severity is RED and config
    says block_on_red is True.
  - Console output only. No GUI, no file writes, no network.
  - Never raises on bad input — silently skips invalid checks.
  - lib/core.py must not import this file.
  - Does not import flow.py or module_loader.py.

Config block read from sysconf["warnings"]:
  enabled       bool  — master switch, default True
  block_on_red  bool  — if True, sys.exit(1) on any RED warning, default False
  log_warnings  bool  — if True, write warnings to debug.log, default True

Trigger IDs (for check selection):
  log_too_large        — debug.log line count exceeds max_log_lines
  missing_snapshot     — no snapshot folder found beside runtime
  config_missing       — one or more config files absent from conf/
  vault_path_mismatch  — resolved vault path does not match expected
  module_error         — a module __init__.py raised on is_available()
"""

import sys
from pathlib import Path
from datetime import datetime


# ── Severity ───────────────────────────────────────────────────────────────────

GREEN  = 0
YELLOW = 1
RED    = 2

_LEVEL_LABELS = {GREEN: "GREEN", YELLOW: "YELLOW", RED: "RED"}

# ── ANSI (inline — must not import core) ──────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_C_OK   = "\033[92m"
_C_WARN = "\033[93m"
_C_ERR  = "\033[91m"
_C_HINT = "\033[2m"

_LEVEL_COLORS = {GREEN: _C_OK, YELLOW: _C_WARN, RED: _C_ERR}
_LEVEL_ICONS  = {GREEN: "✓", YELLOW: "⚠", RED: "✗"}

# ── Warning dataclass (plain dict — no dataclasses dependency) ─────────────────

def _w(trigger: str, severity: int, message: str, detail: str = "") -> dict:
    return {
        "trigger":  trigger,
        "severity": severity,
        "message":  message,
        "detail":   detail,
    }


# ── Config reader ──────────────────────────────────────────────────────────────

def _warn_config(sysconf: dict) -> dict:
    """
    Extract warnings config block from sysconf.
    Returns defaults if key absent or malformed.
    """
    defaults = {
        "enabled":      True,
        "block_on_red": False,
        "log_warnings": True,
    }
    try:
        block = sysconf.get("warnings", {})
        return {k: block.get(k, v) for k, v in defaults.items()}
    except Exception:
        return defaults


# ── Individual checks ──────────────────────────────────────────────────────────

def check_log_size(runtime_dir: Path, max_lines: int = 400) -> dict | None:
    """
    GREEN  — log absent or within limit
    YELLOW — log exceeds max_lines (should rotate)
    RED    — log exceeds 4× limit (rotation may have failed)
    """
    log = runtime_dir / "logs" / "debug.log"
    if not log.exists():
        return None
    try:
        count = sum(1 for _ in open(log, encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    if count <= max_lines:
        return None
    if count <= max_lines * 4:
        return _w(
            "log_too_large", YELLOW,
            "debug.log exceeds rotation limit",
            f"{count} lines (limit {max_lines}). Run cleaner to rotate."
        )
    return _w(
        "log_too_large", RED,
        "debug.log is severely oversized",
        f"{count} lines ({count // max_lines}× limit). Rotation may have failed."
    )


def check_snapshot_present(runtime_dir: Path) -> dict | None:
    """
    GREEN  — snapshot folder exists beside runtime
    YELLOW — no snapshot found
    """
    parent = runtime_dir.parent
    try:
        has_snap = any(
            d.is_dir() and "snapshot" in d.name.lower()
            for d in parent.iterdir()
        )
    except Exception:
        has_snap = False
    if has_snap:
        return None
    return _w(
        "missing_snapshot", YELLOW,
        "No snapshot folder found",
        f"Expected ai_framework_snapshot_YYYYMMDD beside {parent}. "
        "Run Step 0 before any write."
    )


def check_configs_present(conf_dir: Path) -> dict | None:
    """
    GREEN  — all three config files present
    YELLOW — one or more config files missing (defaults will be used)
    """
    required = ["system_config.json", "prompter_config.json", "cleaner_config.json"]
    missing  = [f for f in required if not (conf_dir / f).exists()]
    if not missing:
        return None
    return _w(
        "config_missing", YELLOW,
        "Config file(s) missing — using defaults",
        f"Missing: {', '.join(missing)}"
    )


def check_vault_path(runtime_dir: Path, sysconf: dict) -> dict | None:
    """
    GREEN  — vault root resolves and exists
    YELLOW — vault root resolves but directory does not exist yet
    RED    — vault_root value is absolute path (portability violation)
    """
    try:
        vault_rel = sysconf.get("vault_root", "../ai-vault")
        if Path(vault_rel).is_absolute():
            return _w(
                "vault_path_mismatch", RED,
                "vault_root is an absolute path",
                f"Value: {vault_rel!r}. Must be relative for USB portability."
            )
        resolved = (runtime_dir / vault_rel).resolve()
        if not resolved.exists():
            return _w(
                "vault_path_mismatch", YELLOW,
                "Vault directory does not exist",
                f"Resolved to: {resolved}. Run bootstrap to create."
            )
        return None
    except Exception as e:
        return _w(
            "vault_path_mismatch", YELLOW,
            "Could not resolve vault path",
            str(e)
        )


def check_modules(modules_dir: Path) -> list:
    """
    Returns a list of warnings (may be empty).
    YELLOW — a module folder has no __init__.py
    RED    — a module __init__.py raised an exception on import
    """
    warnings = []
    if not modules_dir.exists():
        return warnings
    try:
        import importlib.util
        for mod_dir in sorted(modules_dir.iterdir()):
            if not mod_dir.is_dir() or mod_dir.name.startswith("_"):
                continue
            init = mod_dir / "__init__.py"
            if not init.exists():
                warnings.append(_w(
                    "module_error", YELLOW,
                    f"Module '{mod_dir.name}' has no __init__.py",
                    "Module will be treated as unavailable."
                ))
                continue
            try:
                mod_key = f"_warn_probe_{mod_dir.name}"
                spec = importlib.util.spec_from_file_location(mod_key, init)
                mod  = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                sys.modules.pop(mod_key, None)
            except Exception as e:
                warnings.append(_w(
                    "module_error", RED,
                    f"Module '{mod_dir.name}' raised on import",
                    str(e)
                ))
    except Exception:
        pass
    return warnings


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_checks(
    runtime_dir: Path,
    sysconf: dict,
    conf_dir: Path | None = None,
    modules_dir: Path | None = None,
    max_log_lines: int = 400,
    triggers: set | None = None,
) -> list:
    """
    Run all enabled checks and return a list of warning dicts.
    triggers — optional set of trigger IDs to run. None = run all.
    Results are sorted: RED first, then YELLOW, then GREEN.
    Never raises.
    """
    wconf = _warn_config(sysconf)
    if not wconf["enabled"]:
        return []

    all_warnings = []

    def _add(result):
        if result is None:
            return
        if isinstance(result, list):
            all_warnings.extend(result)
        else:
            all_warnings.append(result)

    def _want(tid):
        return triggers is None or tid in triggers

    try:
        if _want("log_too_large"):
            _add(check_log_size(runtime_dir, max_log_lines))
        if _want("missing_snapshot"):
            _add(check_snapshot_present(runtime_dir))
        if _want("config_missing") and conf_dir:
            _add(check_configs_present(conf_dir))
        if _want("vault_path_mismatch"):
            _add(check_vault_path(runtime_dir, sysconf))
        if _want("module_error") and modules_dir:
            _add(check_modules(modules_dir))
    except Exception:
        pass

    # Sort: RED=2 first, then YELLOW=1
    return sorted(all_warnings, key=lambda w: -w["severity"])


# ── Display ────────────────────────────────────────────────────────────────────

def display(warnings: list, sysconf: dict | None = None, source: str = "SYS") -> None:
    """
    Print warnings to terminal.
    If sysconf["warnings"]["block_on_red"] is True and any RED warning
    is present, calls sys.exit(1) after displaying all warnings.
    Never raises.
    """
    if not warnings:
        return

    wconf = _warn_config(sysconf or {})
    has_red = any(w["severity"] == RED for w in warnings)

    print()
    print(f"{_C_HINT}{'─' * 52}{_RESET}")
    print(f"{_BOLD}  Runtime Warnings{_RESET}")
    print(f"{_C_HINT}{'─' * 52}{_RESET}")

    for w in warnings:
        col   = _LEVEL_COLORS.get(w["severity"], _C_HINT)
        icon  = _LEVEL_ICONS.get(w["severity"], "?")
        label = _LEVEL_LABELS.get(w["severity"], "?")
        print(f"  {col}{icon}  [{label}]{_RESET}  {w['message']}")
        if w.get("detail"):
            print(f"       {_C_HINT}{w['detail']}{_RESET}")

    print(f"{_C_HINT}{'─' * 52}{_RESET}")

    if wconf.get("log_warnings", True):
        _log_warnings(warnings, source)

    if has_red and wconf.get("block_on_red", False):
        print(f"\n{_C_ERR}  Blocked: red-severity warning with block_on_red=true.{_RESET}")
        print(f"{_C_HINT}  Resolve the issue above, then restart.{_RESET}\n")
        sys.exit(1)


def display_if_any(
    runtime_dir: Path,
    sysconf: dict,
    conf_dir: Path | None = None,
    modules_dir: Path | None = None,
    max_log_lines: int = 400,
    triggers: set | None = None,
    source: str = "SYS",
) -> list:
    """
    Convenience: run all checks and display results in one call.
    Returns the list of warnings found (empty list if none).
    """
    warnings = run_checks(
        runtime_dir, sysconf,
        conf_dir=conf_dir,
        modules_dir=modules_dir,
        max_log_lines=max_log_lines,
        triggers=triggers,
    )
    display(warnings, sysconf, source=source)
    return warnings


# ── Log helper ─────────────────────────────────────────────────────────────────

def _log_warnings(warnings: list, source: str) -> None:
    """
    Append warnings to logs/debug.log if it is reachable.
    Never raises.
    """
    try:
        # Resolve log path relative to this file (lib/warn.py → runtime_core/logs/)
        log_file = Path(__file__).resolve().parent / "logs" / "debug.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            for w in warnings:
                label = _LEVEL_LABELS.get(w["severity"], "?")
                f.write(
                    f"{ts} | {label:<8} | {source:<3} | "
                    f"[{w['trigger']}] {w['message']}"
                    + (f" — {w['detail']}" if w.get("detail") else "")
                    + "\n"
                )
    except Exception:
        pass
