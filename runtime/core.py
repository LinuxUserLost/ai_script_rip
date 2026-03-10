"""
core.py | ai_framework runtime_core
Shared infrastructure for all scripts and modules.
- Path resolution via __file__ only (portable, USB-safe)
- Config load/save with timestamped backups
- State load/save (no absolute paths)
- Log write (append-only, severity levels, source tags)
- ANSI helpers
- VAULT_WRITE_ENABLED flag (disabled until Step 4 validation)

Import order rule:
  entry points  →  scripts  →  lib
  modules       →  lib
  lib           →  (nothing in this project)

Do not import from scripts/ or modules/ here.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path


# ── Vault write lock ───────────────────────────────────────────────────────────
# Remains False until Step 4 (vault generator) is validated.
# lib/vault.py checks this before any write operation.
# Set to True only after vault generator validation is confirmed.

VAULT_WRITE_ENABLED = False


# ── Runtime paths ──────────────────────────────────────────────────────────────
# All paths derived from this file's location.
# __file__ = runtime/core.py

# RUNTIME_DIR = runtime/

RUNTIME_DIR = Path(__file__).resolve().parent


CONF_DIR    = RUNTIME_DIR / "configs"
LOGS_DIR    = RUNTIME_DIR / "logs"
LOG_ARCHIVE = LOGS_DIR / "archive"
STATE_FILE  = RUNTIME_DIR / "state.json"
DEBUG_LOG   = LOGS_DIR / "debug.log"
CONFLICT_LIST = LOGS_DIR / "conflict_list.txt"
CONF_BACKUP = CONF_DIR / "backups"

# Config file paths
SYSTEM_CONF_FILE   = CONF_DIR / "system_config.json"
PROMPTER_CONF_FILE = CONF_DIR / "prompter_config.json"
CLEANER_CONF_FILE  = CONF_DIR / "cleaner_config.json"


# ── Config defaults ────────────────────────────────────────────────────────────
# These are the authoritative defaults.
# load_config() merges file values on top of these.
# Missing keys always fall back to defaults — no crash.

SPEC    = "v0.5.0"
VERSION = "1.0.0"

DEFAULT_SYSTEM_CONFIG = {
    "spec":    SPEC,
    "version": VERSION,
    # Vault root as a relative string — resolved at runtime against RUNTIME_DIR
    "vault_root": "../ai-vault",
    # Vault folder names — all resolved relative to vault_root
    "vault_folders": {
        "indexes":   "000_indexes",
        "topics":    "001_topics",
        "sessions":  "002_sessions",
        "raw":       "003_raw",
        "prompts":   "004_prompts",
        "tags":      "005_tags",
        "knowledge": "006_knowledge",
        "guides":    "007_guides",
        "agents":    "008_agents",
        "tutorials": "009_tutorials",
        "bundles":   "bundles",
    },
    "session_template": {
        "prompt_field":         "prompts",
        "list_prefix":          "* ",
        "empty_slots":          2,
        "ai_markers":           True,
        "topic_block":          True,
        "include_instructions": True,
    },
    "prompt_parsing": {
        "alias_prefixes":  ["* ", "- "],
        "case_sensitive":  False,
        "strip_whitespace": True,
    },
    "composition": {
        "type_order":      ["task", "workflow", "style", "format", "constraint"],
        "section_headers": True,
    },
    "warnings": {
        "enabled":      True,
        "block_on_red": False,
        "log_warnings": True,
    },
}

DEFAULT_PROMPTER_CONFIG = {
    "spec":    SPEC,
    "version": VERSION,
    "display": {
        "show_ai_markers":  True,
        "show_topic_block": True,
        "date_format":      "%Y-%m-%d",
        "time_format":      "%H:%M",
    },
    "behavior": {
        "topic_derive_mode": "all_combined",
    },
}

DEFAULT_CLEANER_CONFIG = {
    "spec":    SPEC,
    "version": VERSION,
    "max_log_lines": 400,
    "raw_backup":    True,
    "yaml_fields": {
        "session_id":      True,
        "year_month":      True,
        "date":            True,
        "time":            True,
        "source":          True,
        "model":           True,
        "input_type":      True,
        "pipeline_stage":  True,
        "session_topic":   True,
        "prompts_used":    True,
        "tags":            True,
        "message_length":  True,
        "response_length": True,
        "prompt_count":    True,
        "note":            False,
    },
    "intelligence": {
        "suggest_tags":       True,
        "track_cooccurrence": True,
        "update_related":     True,
        "cooccur_threshold":  3,
    },
}

DEFAULT_STATE = {
    "version": VERSION,
    "spec":    SPEC,
    "log": {
        "current_number": 0,
        "current_month":  "",
    },
    "active_prompts":   [],
    "prompt_counter":   0,
    "session_defaults": {
        "model":          "",
        "pipeline_stage": "capture",
        "input_type":     "clipboard",
        "source":         "prompter",
    },
    "topic_derive_mode":      "all_combined",
    "custom_note":            "",
    "notifications_enabled":  False,
    "last_cleaned_log":       0,
    "last_cleaned_month":     "",
    "topics": {
        "keywords": [],
    },
    "templates": {
        "active": [],
    },
}


# ── Vault path resolver ────────────────────────────────────────────────────────
# Read-only during Steps 1 and 2.
# Returns resolved Path. Does not create anything.

def get_vault_root(sysconf: dict = None) -> Path:
    """
    Resolve vault root from system_config vault_root value.
    Falls back to DEFAULT_SYSTEM_CONFIG if sysconf not provided.
    Always resolved relative to RUNTIME_DIR — never absolute.
    Read-only. Does not create folders.
    """
    conf = sysconf or DEFAULT_SYSTEM_CONFIG
    rel  = conf.get("vault_root", DEFAULT_SYSTEM_CONFIG["vault_root"])
    return (RUNTIME_DIR / rel).resolve()


def get_vault_folder(key: str, sysconf: dict = None) -> Path:
    """
    Resolve a named vault folder by key from system_config vault_folders.
    e.g. get_vault_folder("prompts") → vault_root/004_prompts
    Read-only. Does not create folders.
    """
    conf    = sysconf or DEFAULT_SYSTEM_CONFIG
    folders = conf.get("vault_folders", DEFAULT_SYSTEM_CONFIG["vault_folders"])
    folder  = folders.get(key, "")
    if not folder:
        raise KeyError(f"vault_folders key not found: '{key}'")
    return get_vault_root(conf) / folder


# ── Logging ────────────────────────────────────────────────────────────────────
# Append-only. Never overwrites.
# _rotate_log() moves debug.log to archive/ when max_log_lines exceeded.
# startup_checks() calls rotation once per entry point launch.
# Source tags: P=prompter, C=cleaner, PM=manager, G=gui, U=updater, SYS=core

LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

def log_write(msg: str, level: str = "INFO", source: str = "SYS") -> None:
    """
    Append a line to logs/debug.log.
    Format: YYYY-MM-DD HH:MM:SS | LEVEL | SOURCE | message
    Creates logs/ directory if missing.
    Never raises — logging must not crash the runtime.
    """
    level = level.upper()
    if level not in LEVELS:
        level = "INFO"
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} | {level:<8} | {source:<3} | {msg}\n"
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Intentionally silent — log failure must never crash the caller
        pass


def _rotate_log(max_lines: int = 400) -> None:
    """
    Rotate debug.log if it exceeds max_lines.
    Rotation steps:
      1. Count lines in debug.log
      2. If count > max_lines:
         a. Move debug.log → logs/archive/debug_<random_hex>.log
         b. Append archived filename to logs/conflict_list.txt
         c. Create fresh empty debug.log
    Never raises. Never deletes any log file.
    max_lines is read from cleaner_config at call time.
    Called once per entry point startup via startup_checks().
    """
    if not DEBUG_LOG.exists():
        return
    try:
        with open(DEBUG_LOG, encoding="utf-8") as f:
            count = sum(1 for _ in f)
        if count <= max_lines:
            return
        import secrets
        LOG_ARCHIVE.mkdir(parents=True, exist_ok=True)
        suffix   = secrets.token_hex(3)
        arc_name = f"debug_{suffix}.log"
        arc_path = LOG_ARCHIVE / arc_name
        DEBUG_LOG.rename(arc_path)
        # Append to conflict list — never overwrite
        CONFLICT_LIST.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(CONFLICT_LIST, "a", encoding="utf-8") as f:
            f.write(f"{ts} | {arc_name}\n")
        # Fresh log
        DEBUG_LOG.touch()
        log_write(f"Log rotated. Archived as: {arc_name}", source="SYS")
    except Exception:
        # Must not crash startup
        pass


def startup_checks(source: str = "SYS") -> None:
    """
    Run once at the start of every entry point.
    Currently performs:
      - Log rotation check (reads max_log_lines from cleaner_config)
    Safe to call multiple times — rotation only triggers when needed.
    source tag identifies which entry point is starting.
    """
    try:
        cconf     = load_config("cleaner")
        max_lines = int(cconf.get("max_log_lines", 400))
    except Exception:
        max_lines = 400
    _rotate_log(max_lines)
    log_write(f"Startup. source={source}", level="DEBUG", source=source)


def check_snapshot(source: str = "SYS", interactive: bool = True) -> bool:
    """
    Verify a snapshot folder exists beside the runtime before any write.

    Scans RUNTIME_DIR.parent for any directory whose name contains
    'snapshot'. Vault folder is never included — snapshot covers
    runtime_core only, vault lives separately.

    Behaviour:
      Snapshot found     → log INFO, return True (always proceeds)
      Not found + hotkey → log WARNING, return True (never blocks silent ops)
      Not found + terminal → print warning, ask confirm:
                              y → log WARNING, return True
                              n → log ERROR, sys.exit(1)

    Called after startup_checks(), before load_state() and bootstrap.
    """
    parent = RUNTIME_DIR.parent
    snapshots = [
        d for d in parent.iterdir()
        if d.is_dir() and "snapshot" in d.name.lower()
    ] if parent.exists() else []

    if snapshots:
        names = ", ".join(d.name for d in snapshots)
        log_write(f"Snapshot confirmed: {names}", level="INFO", source=source)
        return True

    # No snapshot found
    log_write(
        "No snapshot folder found beside runtime. "
        "Step 0 (snapshot) should run before any write.",
        level="WARNING", source=source
    )

    if not interactive:
        # Hotkey / silent mode — warn in log, do not block
        log_write(
            "Continuing without snapshot (hotkey mode).",
            level="WARNING", source=source
        )
        return True

    # Terminal mode — warn visibly and ask
    print()
    print(f"{C_WARN}{'─' * 52}{RESET}")
    print(f"{C_WARN}  WARNING: No snapshot found{RESET}")
    print(f"{C_HINT}  Expected a folder named ai_framework_snapshot_YYYYMMDD{RESET}")
    print(f"{C_HINT}  beside: {parent}{RESET}")
    print(f"{C_HINT}  Step 0 (snapshot) should run before any writes.{RESET}")
    print(f"{C_WARN}{'─' * 52}{RESET}")
    print()
    print(
        f"  Continue anyway? [{C_OK}y{RESET}/{C_ERR}N{RESET}]: ",
        end="", flush=True
    )
    answer = input().strip().lower()

    if answer == "y":
        log_write(
            "User chose to continue without snapshot.",
            level="WARNING", source=source
        )
        return True

    log_write(
        "Execution stopped: no snapshot confirmed.",
        level="ERROR", source=source
    )
    print(f"{C_ERR}  Stopped. Create a snapshot first, then retry.{RESET}\n")
    sys.exit(1)


# ── State ──────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    """
    Load runtime state from state.json.
    Merges with DEFAULT_STATE so missing keys are always populated.
    Exits with error message if file is present but corrupted.
    No absolute paths in state — paths block from old format is not carried over.
    """
    if not STATE_FILE.exists():
        state = _deep_merge(DEFAULT_STATE, {})
        save_state(state)
        log_write("state.json created with defaults.", source="SYS")
        return state
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
        # Strip old absolute paths block if present (migration safety)
        loaded.pop("paths", None)
        state = _deep_merge(DEFAULT_STATE, loaded)
        return state
    except json.JSONDecodeError as e:
        log_write(f"state.json corrupted: {e}", level="CRITICAL", source="SYS")
        print(f"{C_ERR}[CRITICAL] state.json is corrupted and cannot be read.{RESET}")
        print(f"{C_HINT}  File: {STATE_FILE}{RESET}")
        print(f"{C_HINT}  Error: {e}{RESET}")
        print(f"{C_HINT}  Rename or delete state.json to reset, then restart.{RESET}")
        sys.exit(1)


def save_state(state: dict) -> None:
    """
    Write state to state.json.
    Never writes absolute paths — strips paths block before saving.
    Creates parent directory if missing.
    """
    safe = dict(state)
    safe.pop("paths", None)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2)


# ── Config ─────────────────────────────────────────────────────────────────────

_CONF_FILES = {
    "system":   (SYSTEM_CONF_FILE,   DEFAULT_SYSTEM_CONFIG),
    "prompter": (PROMPTER_CONF_FILE, DEFAULT_PROMPTER_CONFIG),
    "cleaner":  (CLEANER_CONF_FILE,  DEFAULT_CLEANER_CONFIG),
}


def load_config(section: str) -> dict:
    """
    Load a config section by name: "system", "prompter", or "cleaner".
    Merges file values on top of defaults — missing keys always fall back.
    Returns defaults if file is missing or unreadable.
    """
    if section not in _CONF_FILES:
        raise ValueError(f"Unknown config section: '{section}'. "
                         f"Valid: {list(_CONF_FILES.keys())}")
    filepath, defaults = _CONF_FILES[section]
    if not filepath.exists():
        return _deep_merge(defaults, {})
    try:
        with open(filepath, encoding="utf-8") as f:
            loaded = json.load(f)
        return _deep_merge(defaults, loaded)
    except json.JSONDecodeError as e:
        log_write(f"{section}_config.json corrupted: {e}", level="ERROR", source="SYS")
        print(f"{C_WARN}[WARNING] {filepath.name} is corrupted. Using defaults.{RESET}")
        return _deep_merge(defaults, {})


def save_config(section: str, data: dict) -> None:
    """
    Save a config section to its file.
    Always writes a timestamped backup to conf/backups/ before saving.
    Creates conf/ and conf/backups/ if missing.
    """
    if section not in _CONF_FILES:
        raise ValueError(f"Unknown config section: '{section}'.")
    filepath, _ = _CONF_FILES[section]
    filepath.parent.mkdir(parents=True, exist_ok=True)
    CONF_BACKUP.mkdir(parents=True, exist_ok=True)

    # Write backup of current file before overwriting
    if filepath.exists():
        ts      = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        bk_name = f"{filepath.stem}_{ts}.json"
        bk_path = CONF_BACKUP / bk_name
        try:
            import shutil
            shutil.copy2(str(filepath), str(bk_path))
            log_write(f"Config backup: {bk_name}", source="SYS")
        except Exception as e:
            log_write(f"Config backup failed for {filepath.name}: {e}",
                      level="WARNING", source="SYS")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    log_write(f"Config saved: {filepath.name}", source="SYS")


def load_all_configs() -> tuple:
    """
    Convenience loader. Returns (sysconf, pconf, cconf) in one call.
    """
    return (
        load_config("system"),
        load_config("prompter"),
        load_config("cleaner"),
    )


# ── Internal helpers ───────────────────────────────────────────────────────────

def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """
    Recursively merge overrides into defaults.
    Defaults provide missing keys at every nesting level.
    Override values always win over defaults.
    Neither input dict is modified.
    """
    result = dict(defaults)
    for k, v in overrides.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ── ANSI helpers ───────────────────────────────────────────────────────────────
# All terminal output styling lives here.
# Scripts import these — never redefine them locally.

RESET    = "\033[0m"
BOLD     = "\033[1m"
DIM      = "\033[2m"
C_HEADER = "\033[96m"
C_OK     = "\033[92m"
C_ERR    = "\033[91m"
C_WARN   = "\033[93m"
C_NUM    = "\033[33m"
C_KEY    = "\033[94m"
C_SELECT = "\033[96m"
C_HINT   = "\033[2m"


def c(col: str, text: str) -> str:
    return f"{col}{text}{RESET}"

def hint(text: str) -> str:
    return f"{C_HINT}{text}{RESET}"

def divider(width: int = 52) -> str:
    return c(DIM, "─" * width)

def print_header(title: str, sub: str = "") -> None:
    print()
    print(divider())
    print(c(BOLD + C_HEADER, f"  {title}"))
    if sub:
        print(c(C_HINT, f"  {sub}"))
    print(divider())

def print_menu_item(n, label: str, hint_text: str = "") -> None:
    print(f"  {c(C_NUM, f'[{n}]')} {label}"
          + (f"  {hint(hint_text)}" if hint_text else ""))

def print_nav(extras: str = "") -> None:
    base = f"  {c(C_KEY, 'q')} back   {c(C_KEY, '??')} help"
    if extras:
        base += f"   {extras}"
    print(divider())
    print(base)
    print()

def print_ok(msg: str) -> None:
    print(c(C_OK, f"\n  ✓  {msg}"))

def print_err(msg: str) -> None:
    print(c(C_ERR, f"\n  ✗  {msg}"))

def print_info(msg: str) -> None:
    print(c(C_HINT, f"  {msg}"))

def pause() -> None:
    print(f"\n  {hint('Press Enter...')}", end="", flush=True)
    input()

def get_choice(prompt: str = "Choice") -> str:
    print(f"\n  {c(C_NUM, prompt)}: ", end="", flush=True)
    return input().strip()

def prompt_input(label: str, default: str = "", example: str = "") -> str:
    p = f"\n  {label}"
    if default:
        p += f" {hint(f'[{default}]')}"
    if example:
        p += f"  {hint(f'e.g. {example}')}"
    p += ": "
    print(p, end="", flush=True)
    v = input().strip()
    return v if v else default

def confirm(msg: str) -> bool:
    print(f"\n  {msg} [{c(C_OK, 'y')}/{c(C_ERR, 'N')}]: ", end="", flush=True)
    return input().strip().lower() == "y"
