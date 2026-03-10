#!/usr/bin/env python3
"""
prompter.py | Version 6.0.0 | Spec v0.5.0
SESSION block builder with prompt composition engine.
Zero dependencies — pure Python 3.x.

### PORTABLE: all paths relative to SCRIPT_DIR
### Scripts: ai_framework_vault/scripts/
### Vault:   ai_framework_vault/ai-vault/
### Prompts: ai-vault/004_prompts/  (flat + category subdirs)
### Bundles: ai-vault/bundles/
###
### HOTKEY SETUP (KDE):
### Silent:   bash hotkey_prompter.sh    (Meta+A)
### Terminal: bash terminal_prompter.sh  (Meta+Shift+A)
###
### COMPOSITION ENGINE (v0.5.0):
### Active prompts resolved via prompt_index.json
### Sorted by type order: task → workflow → style → format → constraint
### Assembled into ---INSTRUCTIONS--- block inside SESSION
###
### /COMMANDS (terminal mode):
### /newprompt, /preview, /search, /editprompt, /addtag,
### /removetag, /addalias, /renameprompt, /health
###
### BUNDLE SUPPORT:
### vault/bundles/name.md — macro stacks of aliases
### Bundle alias expands before composition
###
### KEY CHANGES FROM v5:
### - Prompt composition replaces flat alias list in SESSION output
### - prompt_index.json used for fast alias resolution
### - New prompt frontmatter: id, version, type, status, aliases[]
### - /commands in terminal menu input
### - Bundle loading and expansion
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

# ── lib path (Step 4: startup_checks integration) ─────────────────────────────
# Works from runtime_core/scripts/ after Step 5 move.
# Falls back silently if lib not yet reachable (old location).
_RUNTIME_DIR = str(Path(__file__).resolve().parent.parent)
if _RUNTIME_DIR not in sys.path:
    sys.path.insert(0, _RUNTIME_DIR)
try:
    from core import startup_checks as _startup_checks
    from core import check_snapshot as _check_snapshot
except ImportError:
    def _startup_checks(source="?"): pass
    def _check_snapshot(source="?", interactive=True): return True

try:
    from flow import run_post_copy as _run_post_copy
    from flow import get_flow_mode as _get_flow_mode
    from flow import is_flow_active as _is_flow_active
    _FLOW_AVAILABLE = True
except ImportError:
    def _run_post_copy(*a, **kw): pass
    def _get_flow_mode(pconf): return "normal"
    def _is_flow_active(pconf): return False
    _FLOW_AVAILABLE = False

try:
    from warn import display_if_any as _warn_display
    _WARN_AVAILABLE = True
except ImportError:
    def _warn_display(*a, **kw): return []
    _WARN_AVAILABLE = False


# ── ANSI ───────────────────────────────────────────────────────────────────────

RESET    = "\033[0m"; BOLD  = "\033[1m"; DIM   = "\033[2m"
C_HEADER = "\033[96m"; C_OK = "\033[92m"; C_ERR = "\033[91m"
C_WARN   = "\033[93m"; C_NUM= "\033[33m"; C_KEY = "\033[94m"
C_SELECT = "\033[96m"; C_DIM= "\033[2m";  C_HINT= "\033[2m"

def c(col, text): return f"{col}{text}{RESET}"
def hint(t):      return f"{C_HINT}{t}{RESET}"
def divider(w=52):return c(DIM, "─" * w)
def print_header(title, sub=""):
    print(); print(divider())
    print(c(BOLD+C_HEADER, f"  {title}"))
    if sub: print(c(C_HINT, f"  {sub}"))
    print(divider())
def print_menu_item(n, label, hint_text=""):
    print(f"  {c(C_NUM,f'[{n}]')} {label}"
          + (f"  {hint(hint_text)}" if hint_text else ""))
def print_nav(extras=""):
    base = f"  {c(C_KEY,'q')} back   {c(C_KEY,'??')} help"
    if extras: base += f"   {extras}"
    print(divider()); print(base); print()
def print_ok(m):   print(c(C_OK,   f"\n  ✓  {m}"))
def print_err(m):  print(c(C_ERR,  f"\n  ✗  {m}"))
def print_info(m): print(c(C_HINT, f"  {m}"))
def pause():
    print(f"\n  {hint('Press Enter...')}", end="", flush=True); input()
def get_choice(p="Choice"):
    print(f"\n  {c(C_NUM,p)}: ", end="", flush=True)
    return input().strip()
def prompt_input(label, default="", example=""):
    p = f"\n  {label}"
    if default: p += f" {hint(f'[{default}]')}"
    if example: p += f"  {hint(f'e.g. {example}')}"
    p += ": "; print(p, end="", flush=True)
    v = input().strip(); return v if v else default
def confirm(msg):
    print(f"\n  {msg} [{c(C_OK,'y')}/{c(C_ERR,'N')}]: ", end="", flush=True)
    return input().strip().lower() == "y"


# ── Constants ──────────────────────────────────────────────────────────────────

VERSION    = "6.0.0"
SPEC       = "v0.5.0"
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR.parent / "state.json"
CONF_DIR   = SCRIPT_DIR.parent / "configs"
LOG_DIR    = SCRIPT_DIR.parent / "logs"
DEBUG_LOG  = LOG_DIR / "debug.log"

SYSTEM_CONF  = CONF_DIR / "system_config.json"
PROMPTER_CONF= CONF_DIR / "prompter_config.json"

# ── Runtime path resolver ──────────────────────────────────────────────────────
# Reads vault_root and vault_folders from system_config.json.
# Falls back to legacy layout if config is missing or unreadable.
# All downstream code uses VAULT_ROOT, PROMPT_DIR, BUNDLE_DIR unchanged.

def _resolve_runtime_paths():
    try:
        if SYSTEM_CONF.exists():
            with open(SYSTEM_CONF, encoding="utf-8") as f:
                conf = json.load(f)
            vault_rel = conf.get("vault_root", "../ai-vault")
            folders   = conf.get("vault_folders", {})
            vault     = (SCRIPT_DIR.parent / vault_rel).resolve()
            prompt    = vault / folders.get("prompts", "004_prompts")
            bundle    = vault / folders.get("bundles", "bundles")
            return vault, prompt, bundle
    except Exception:
        pass
    vault = (SCRIPT_DIR.parent / "ai-vault").resolve()
    return vault, vault / "004_prompts", vault / "bundles"

VAULT_ROOT, PROMPT_DIR, BUNDLE_DIR = _resolve_runtime_paths()
INDEX_JSON  = PROMPT_DIR / "prompt_index.json"
HEALTH_JSON = PROMPT_DIR / "prompt_health_report.json"

SESSION_OPEN  = "<---SESSION--->"
SESSION_CLOSE = "<---SESSION END--->"
MARKER_AI_START = "<---Marker 2--->"
MARKER_AI_END   = "<---Marker 3--->"

TYPE_ORDER      = ["task", "workflow", "style", "format", "constraint"]
PIPELINE_STAGES = ["capture","clean","summarize","extract","analyze","archive"]
INPUT_TYPES     = ["clipboard","file","manual","api"]
TOPIC_MODES     = ["first_line","repeated_phrase","prompt_names","all_combined"]
STATUS_VALUES   = ["draft", "active", "archived"]
FM_SIMPLE       = ["id","version","name","description","category","type",
                   "created","updated","usage_count","last_used","status"]
FM_LISTS        = ["aliases","tags","related"]

PROMPT_TEMPLATE = """\
---
id: {id}
version: 1.0
name: {name}
description: {description}
category: {category}
type: {ptype}
created: {created}
updated: {created}
usage_count: 0
last_used:
status: draft
aliases:
  - {name}
tags:{tags_block}
related:
---

# {name}

## Purpose

## Instructions

## Output Format
"""

BUNDLE_TEMPLATE = """\
---
name: {name}
description: {description}
prompts:{prompts_block}
tags:
  - bundle
---

# Bundle: {name}

Notes:
"""

DEFAULT_SYSTEM_CONFIG = {
    "spec":    SPEC, "version": VERSION,
    "prompt_dir": "004_prompts", "bundle_dir": "bundles",
    "session_template": {
        "prompt_field": "prompts", "list_prefix": "* ",
        "empty_slots": 2, "ai_markers": True, "topic_block": True,
        "include_instructions": True,
    },
    "prompt_parsing": {
        "alias_prefixes": ["* ", "- "], "case_sensitive": False,
        "strip_whitespace": True,
    },
    "composition": {
        "type_order": TYPE_ORDER, "section_headers": True,
    },
}

DEFAULT_PROMPTER_CONFIG = {
    "spec":    SPEC, "version": VERSION,
    "display": {
        "show_ai_markers": True, "show_topic_block": True,
        "date_format": "%Y-%m-%d", "time_format": "%H:%M",
    },
    "behavior": {
        "topic_derive_mode": "all_combined",
        "flow_mode":         "normal",
    },
}


# ── Logging ────────────────────────────────────────────────────────────────────

def log_write(msg, level="INFO"):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"{ts} | {level} | P | {msg}\n")


# ── Frontmatter parser (shared with prompt_manager) ───────────────────────────

def _parse_fm(content: str) -> tuple:
    """Parse YAML-style frontmatter. Returns (meta, body). Never raises."""
    try:
        if not content.startswith("---"):
            return {}, content
        rest = content[3:]
        if rest.startswith("\n"):
            rest = rest[1:]
        nl_d = rest.find("\n---")
        if nl_d == -1:
            return {}, content
        fm_text = rest[:nl_d]
        body    = rest[nl_d+4:]
        if body.startswith("\n"):
            body = body[1:]
        meta = {}
        cur_key = None; cur_list = None
        for line in fm_text.split("\n"):
            if not line.strip():
                continue
            ls = line.lstrip()
            if ls.startswith("- ") and cur_list is not None:
                cur_list.append(ls[2:].strip().strip("\"'"))
                continue
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                k = k.strip(); v = v.strip().strip("\"'")
                if v:
                    meta[k] = v; cur_key = k; cur_list = None
                else:
                    lst=[]; meta[k]=lst; cur_key=k; cur_list=lst
        return meta, body
    except Exception as e:
        log_write(f"_parse_fm: {e}", "WARNING")
        return {}, content


def _format_fm(meta: dict) -> str:
    lines = []
    for k in FM_SIMPLE:
        if k in meta:
            v = meta[k]
            lines.append(f"{k}:" if (v is None or v=="") else f"{k}: {v}")
    for k in FM_LISTS:
        if k in meta:
            v = meta[k]
            items = v if isinstance(v, list) else (
                [i.strip() for i in v.split(",") if i.strip()]
                if isinstance(v,str) and v else [])
            if items:
                lines.append(f"{k}:"); [lines.append(f"  - {i}") for i in items]
            else:
                lines.append(f"{k}:")
    return "\n".join(lines) + "\n"


def _write_prompt_safe(filepath: Path, meta: dict, body: str,
                        old_body: str = None) -> bool:
    """Atomic write: temp → validate → os.replace."""
    if old_body is not None:
        h_new = hashlib.md5(body.strip().encode()).hexdigest()
        h_old = hashlib.md5(old_body.strip().encode()).hexdigest()
        if h_new != h_old:
            try:
                maj, mn = meta.get("version","1.0").split(".")
                meta["version"] = f"{maj}.{int(mn)+1}"
            except Exception:
                meta["version"] = "1.1"
            meta["updated"] = datetime.now().strftime("%Y-%m-%d")

    fm  = _format_fm(meta)
    content = f"---\n{fm}---\n{body}"
    tmp = filepath.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        test, _ = _parse_fm(tmp.read_text())
        if not test.get("id"):
            raise ValueError("id missing after write")
        os.replace(str(tmp), str(filepath))
        log_write(f"Wrote: {filepath.name}")
        return True
    except Exception:
        if tmp.exists(): tmp.unlink(missing_ok=True)
        raise


def _generate_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]


# ── Bootstrap ──────────────────────────────────────────────────────────────────

def bootstrap_directories(state, sysconf=None):
    if sysconf is None:
        sysconf = load_system_config()
    month = datetime.now().strftime("%Y-%m")
    # Runtime dirs — always beside script, not in vault
    for d in ["conf", "logs", "prompt_usage"]:
        p = SCRIPT_DIR.parent / d
        if not p.exists(): p.mkdir(parents=True, exist_ok=True)
    # Vault root — resolved from sysconf, relative to SCRIPT_DIR
    _vault_rel = sysconf.get("vault_root", "../ai-vault")
    _vault     = (SCRIPT_DIR.parent / _vault_rel).resolve()
    _folders   = sysconf.get("vault_folders", {})
    # All vault folders from config — no hardcoded names
    for key, name in _folders.items():
        p = _vault / name
        if not p.exists(): p.mkdir(parents=True, exist_ok=True)
    # Month subdirs for sessions and raw
    for key in ("sessions", "raw"):
        name = _folders.get(key, "")
        if name:
            p = _vault / name / month
            if not p.exists(): p.mkdir(parents=True, exist_ok=True)
    # Index stubs
    _idx_dir = _vault / _folders.get("indexes", "000_indexes")
    _touch_index(_idx_dir / "session_index.md", "# Session Index\n\n")
    _prm_dir = _vault / _folders.get("prompts", "004_prompts")
    _touch_index(_prm_dir / "prompt_index.md", "# Prompt Index\n\n")
    if not SYSTEM_CONF.exists(): save_system_config(DEFAULT_SYSTEM_CONFIG)
    if not PROMPTER_CONF.exists(): save_prompter_config(DEFAULT_PROMPTER_CONFIG)
    log_write("Bootstrap complete.")


def _touch_index(path, header):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header)


# ── State ──────────────────────────────────────────────────────────────────────

def _default_state():
    return {
        "version": VERSION, "spec": SPEC,
        "log":     {"current_number": 0, "current_month": ""},
        "active_prompts":    [],
        "prompt_counter":    0,
        "session_defaults":  {"model":"","pipeline_stage":"capture",
                              "input_type":"clipboard","source":"prompter"},
        "topic_derive_mode": "all_combined",
        "custom_note":       "",
        "notifications_enabled": False,
        "paths": {
            "vault_root":    str(VAULT_ROOT),
            "prompt_dir":    str(PROMPT_DIR),
            "sessions_dir":  str(VAULT_ROOT/"002_sessions"),
            "raw_dir":       str(VAULT_ROOT/"003_raw"),
            "indexes_dir":   str(VAULT_ROOT/"000_indexes"),
            "topics_dir":    str(VAULT_ROOT/"001_topics"),
            "tags_dir":      str(VAULT_ROOT/"005_tags"),
            "session_index": str(VAULT_ROOT/"000_indexes"/"session_index.md"),
        },
        "templates": {"active": []},
        "topics":   {"keywords": []},
    }


def load_state():
    if not STATE_FILE.exists():
        s = _default_state(); save_state(s); return s
    try:
        with open(STATE_FILE) as f: state = json.load(f)
        state, changed = _migrate_state(state)
        if changed: save_state(state)
        return state
    except json.JSONDecodeError as e:
        log_write(f"state.json corrupted: {e}", "ERROR")
        print(c(C_ERR, "\n[ERROR] state.json corrupted.")); sys.exit(1)


def _migrate_state(state):
    defaults = _default_state(); changed = False
    for k, v in defaults.items():
        if k not in state: state[k] = v; changed = True
    # v4 → v5: prompt_subsections → active_prompts
    if "prompt_subsections" in state:
        if not state.get("active_prompts"):
            migrated = []
            for sd in state["prompt_subsections"].values():
                migrated.extend(sd.get("active",[]))
            state["active_prompts"] = migrated
        del state["prompt_subsections"]; changed = True
    for k, v in defaults["paths"].items():
        if k not in state.get("paths",{}):
            state.setdefault("paths",{})[k] = v; changed = True
    return state, changed


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2)


# ── Config ─────────────────────────────────────────────────────────────────────

def load_system_config():
    if not SYSTEM_CONF.exists(): return dict(DEFAULT_SYSTEM_CONFIG)
    try:
        with open(SYSTEM_CONF) as f: conf = json.load(f)
        for k, v in DEFAULT_SYSTEM_CONFIG.items():
            if k not in conf: conf[k] = v
        return conf
    except Exception: return dict(DEFAULT_SYSTEM_CONFIG)


def save_system_config(conf):
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    with open(SYSTEM_CONF, "w") as f: json.dump(conf, f, indent=2)


def load_prompter_config():
    if not PROMPTER_CONF.exists(): return dict(DEFAULT_PROMPTER_CONFIG)
    try:
        with open(PROMPTER_CONF) as f: conf = json.load(f)
        for k, v in DEFAULT_PROMPTER_CONFIG.items():
            if k not in conf: conf[k] = v
        return conf
    except Exception: return dict(DEFAULT_PROMPTER_CONFIG)


def save_prompter_config(conf):
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROMPTER_CONF, "w") as f: json.dump(conf, f, indent=2)


# ── Notifications ──────────────────────────────────────────────────────────────

def notify(title, msg, state):
    if not state.get("notifications_enabled"): return
    if not shutil.which("notify-send"): return
    try: subprocess.run(["notify-send", title, msg], check=True)
    except Exception as e: log_write(f"notify-send: {e}", "WARNING")


# ── Log number ─────────────────────────────────────────────────────────────────

def get_and_increment_log(state):
    now_m = datetime.now().strftime("%Y-%m")
    if state["log"]["current_month"] != now_m:
        state["log"]["current_number"] = 1
        state["log"]["current_month"]  = now_m
    else:
        state["log"]["current_number"] += 1
    num = state["log"]["current_number"]
    return f"{now_m}-LOG-{num:04d}", num


# ── Prompt index ───────────────────────────────────────────────────────────────

def load_prompt_index() -> dict:
    """
    Load prompt_index.json generated by prompt_manager.
    Falls back to scanning files directly if index missing.
    Returns dict with 'aliases', 'by_id', 'by_name', 'meta' keys.
    """
    if INDEX_JSON.exists():
        try:
            with open(INDEX_JSON) as f:
                idx = json.load(f)
            if idx.get("aliases"):
                return idx
        except Exception:
            pass
    # Fallback: build lightweight alias map from filenames
    log_write("prompt_index.json missing — scanning files directly", "WARNING")
    idx = {"aliases": {}, "by_id": {}, "by_name": {}, "meta": {}}
    if not PROMPT_DIR.exists():
        return idx
    for f in PROMPT_DIR.rglob("*.md"):
        if f.name in ("prompt_index.md","prompt_index.json","README.md"):
            continue
        try:
            content    = f.read_text()
            meta, body = _parse_fm(content)
            rel        = str(f.relative_to(VAULT_ROOT))
            stem       = re.sub(r"^\d+_", "", f.stem).lower()
            name       = meta.get("name","").lower() or stem
            # Register stem, name, and explicit aliases
            for alias in set([stem, name] +
                             [a.strip().lower()
                              for a in (meta.get("aliases",[])
                              if isinstance(meta.get("aliases"),list) else [])]):
                if alias and alias not in idx["aliases"]:
                    idx["aliases"][alias] = rel
            if meta.get("id"):
                idx["by_id"][meta["id"]] = rel
            if name:
                idx["by_name"][name] = rel
        except Exception:
            pass
    return idx


# ── Bundle loading ─────────────────────────────────────────────────────────────

def load_bundle(alias: str) -> list:
    """
    Search vault/bundles/ for a bundle matching alias.
    Returns list of prompt aliases expanded from the bundle, or None if not found.
    Supports: bundle name, filename stem, [[wikilink]] style.
    """
    if not BUNDLE_DIR.exists():
        return None
    alias_clean = re.sub(r"^\[\[|\]\]$", "", alias.strip()).lower()
    for f in BUNDLE_DIR.glob("*.md"):
        content    = f.read_text()
        meta, body = _parse_fm(content)
        bundle_name = meta.get("name","").lower()
        stem        = f.stem.lower()
        if bundle_name == alias_clean or stem == alias_clean:
            prompts = meta.get("prompts", [])
            if isinstance(prompts, list):
                return [p.strip() for p in prompts if p.strip()]
            return []
    return None


# ── Prompt resolution ──────────────────────────────────────────────────────────

def resolve_prompt(alias: str, idx: dict) -> tuple:
    """
    Resolve an alias to (filepath, meta, body) using the prompt index.
    Returns (None, None, None) if not found.
    Handles [[wikilink]] syntax by stripping brackets.
    """
    alias_clean = re.sub(r"^\[\[|\]\]$", "", alias.strip()).lower()
    rel = idx.get("aliases", {}).get(alias_clean)
    if not rel:
        rel = idx.get("by_name", {}).get(alias_clean)
    if not rel:
        return None, None, None
    filepath = VAULT_ROOT / rel
    if not filepath.exists():
        return None, None, None
    try:
        content    = filepath.read_text()
        meta, body = _parse_fm(content)
        return filepath, meta, body
    except Exception:
        return None, None, None


def expand_active_prompts(active: list, idx: dict) -> list:
    """
    Expand active_prompts list: bundles are expanded to their constituent aliases.
    Returns flat list of (alias, filepath, meta, body).
    Bundles are always expanded before direct aliases.
    De-duplicates by alias.
    """
    expanded = []
    seen     = set()

    def _add(alias, fp, meta, body):
        if alias not in seen:
            seen.add(alias)
            expanded.append((alias, fp, meta, body))

    for alias in active:
        bundle_prompts = load_bundle(alias)
        if bundle_prompts is not None:
            # Bundle — expand each alias in it
            for ba in bundle_prompts:
                fp, meta, body = resolve_prompt(ba, idx)
                _add(ba, fp, meta, body)
        else:
            fp, meta, body = resolve_prompt(alias, idx)
            _add(alias, fp, meta, body)

    return expanded


# ── Composition engine ─────────────────────────────────────────────────────────

def compose_prompts(expanded: list, sysconf: dict) -> str:
    """
    Sort resolved prompts by type order and assemble structured instructions.
    Composition order: task → workflow → style → format → constraint → untyped.

    Output format:
      ## Task
      [task instructions]

      ## Style
      [style instructions]
      ...

    Returns empty string if no prompts have instruction bodies.
    """
    type_order = sysconf.get("composition", {}).get(
        "type_order", TYPE_ORDER)
    show_headers = sysconf.get("composition", {}).get(
        "section_headers", True)

    # Bucket by type
    buckets  = {t: [] for t in type_order}
    untyped  = []

    for alias, filepath, meta, body in expanded:
        if meta is None:
            continue
        body_stripped = body.strip() if body else ""
        if not body_stripped:
            continue   # Skip prompts with no instruction body
        ptype = (meta.get("type") or "").lower().strip()
        if ptype in buckets:
            buckets[ptype].append((alias, meta, body_stripped))
        else:
            untyped.append((alias, meta, body_stripped))

    sections = []
    for ptype in type_order:
        items = buckets[ptype]
        if not items:
            continue
        if show_headers:
            section_lines = [f"## {ptype.capitalize()}"]
        else:
            section_lines = []
        for alias, meta, body in items:
            section_lines.append(body)
        sections.append("\n\n".join(section_lines))

    if untyped:
        if show_headers:
            lines = ["## Additional"]
        else:
            lines = []
        for alias, meta, body in untyped:
            lines.append(body)
        sections.append("\n\n".join(lines))

    return "\n\n".join(sections)


# ── SESSION block builder ──────────────────────────────────────────────────────

def build_session_block(log_num, log_raw_num, state, sysconf, pconf,
                         idx=None, custom_note="", live_fields=None):
    """
    Builds the full SESSION block.

    Structure (v0.5.0):
      <---SESSION--->
      session_id: ...

      ---USER INPUT---

      [metadata]

      prompts:
      * alias1
      * alias2
      *             ← empty slots

      tags:

      [message_length / response_length / prompt_count]

      ---INSTRUCTIONS---
      ## Task
      [task body]

      ## Style
      [style body]
      ---END INSTRUCTIONS---

      ####AI MARKERS####
      ...
      <---SESSION END--->

    The INSTRUCTIONS section is only included if any active prompts
    have non-empty instruction bodies and include_instructions is True.
    """
    now      = datetime.now()
    d_fmt    = pconf.get("display",{}).get("date_format","%Y-%m-%d")
    t_fmt    = pconf.get("display",{}).get("time_format","%H:%M")
    month    = now.strftime("%Y-%m")
    date_str = now.strftime(d_fmt)
    time_str = now.strftime(t_fmt)

    defaults = state.get("session_defaults", {})
    lf       = live_fields or {}
    model    = lf.get("model",           defaults.get("model",""))
    stage    = lf.get("pipeline_stage",  defaults.get("pipeline_stage","capture"))
    itype    = lf.get("input_type",      defaults.get("input_type","clipboard"))
    source   = lf.get("source",          defaults.get("source","prompter"))
    topic    = lf.get("session_topic",   "")
    extra_tags = lf.get("tags", [])

    # Prompt list section
    tmpl       = sysconf.get("session_template", {})
    prefix     = tmpl.get("list_prefix", "* ")
    empty_slots= tmpl.get("empty_slots", 2)
    active     = state.get("active_prompts", [])
    p_lines    = [f"{prefix}{a}" for a in active]
    for _ in range(empty_slots):
        p_lines.append(prefix.rstrip())
    prompt_block = "prompts:\n" + "\n".join(p_lines)

    # Tags
    tag_lines = "\n".join(f"  - [[{t}]]" for t in extra_tags) \
                if extra_tags else "  - "

    # Note
    note_line = f"\nnote: {custom_note}" if custom_note else ""

    # Composition — build INSTRUCTIONS section
    instructions_block = ""
    if tmpl.get("include_instructions", True) and idx and active:
        expanded = expand_active_prompts(active, idx)
        composed = compose_prompts(expanded, sysconf)
        if composed.strip():
            instructions_block = (
                "\n---INSTRUCTIONS---\n\n"
                + composed.strip()
                + "\n\n---END INSTRUCTIONS---\n"
            )

    # Topic marker instructions
    topic_block = ""
    if pconf.get("display",{}).get("show_topic_block", True):
        kw = state.get("topics",{}).get("keywords",[])
        if kw:
            topic_block = (
                f"####TOPIC MARKERS####\n"
                f"When mentioning: {', '.join(kw)}\n"
                f"Wrap like: <---Topic: {kw[0]}--->\n"
                f"Never use topic markers any other time.\n\n"
            )

    # AI markers
    ai_markers = ""
    if pconf.get("display",{}).get("show_ai_markers", True):
        ai_markers = (
            f"####AI MARKERS####\n"
            f"Add the following to the beginning of your next response:\n"
            f"{MARKER_AI_START} {log_num}\n"
            f"---AI RESPONSE---\n"
            f"Add the following to the end of your next response:\n"
            f"{MARKER_AI_END}"
        )

    block = (
        f"{SESSION_OPEN}\n"
        f"session_id: [[session_{log_num}]]\n"
        f"\n"
        f"---USER INPUT---\n\n\n"
        f"year_month: [[{month}]]\n"
        f"date: {date_str}\n"
        f"time: {time_str}\n"
        f"source: {source}\n"
        f"model: {model}\n"
        f"input_type: {itype}\n"
        f"pipeline_stage: {stage}\n"
        f"session_topic: {topic}{note_line}\n"
        f"\n"
        f"{prompt_block}\n"
        f"\n"
        f"tags:\n"
        f"{tag_lines}\n"
        f"\n"
        f"message_length:\n"
        f"response_length:\n"
        f"prompt_count:\n"
        f"{instructions_block}\n"
        f"{topic_block}"
        f"{ai_markers}\n"
        f"\n"
        f"{SESSION_CLOSE}\n"
        f"Never say either of those markers any other time."
    )
    return block


# ── Clipboard ──────────────────────────────────────────────────────────────────

def copy_to_clipboard(text):
    try:
        subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True)
        log_write("Clipboard written."); return True
    except FileNotFoundError:
        log_write("wl-copy not found.", "ERROR"); return False
    except subprocess.CalledProcessError as e:
        log_write(f"wl-copy failed: {e}", "ERROR"); return False


# ── Topic derive ───────────────────────────────────────────────────────────────

def derive_session_topic(user_input, state, pconf):
    mode = state.get("topic_derive_mode", "all_combined")
    stop = {"the","a","an","and","or","but","in","on","at","to","for","of",
            "with","as","by","from","it","is","are","was","were","this",
            "that","i","my","we","you","be","been","have","has"}
    first = ""
    for line in (user_input or "").split("\n"):
        s = line.strip()
        if s:
            first = re.sub(r'[^\w\s-]','',s)[:40].strip(); break
    rep = ""
    if user_input:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', user_input.lower())
        freq  = {}
        for w in words:
            if w not in stop: freq[w] = freq.get(w,0)+1
        if freq: rep = max(freq, key=freq.get)
    ps = "_".join(a.replace("-","_") for a in state.get("active_prompts",[])[:3])
    if mode=="first_line":   raw=first
    elif mode=="repeated_phrase": raw=rep
    elif mode=="prompt_names":    raw=ps
    else:
        parts=[p for p in [first,rep,ps] if p]
        raw="_".join(parts[:3])
    slug = re.sub(r'[^\w]','_',raw.lower())
    slug = re.sub(r'_+','_',slug).strip('_')
    return slug[:60]


# ── Prompt file creation ───────────────────────────────────────────────────────

def _next_prompt_number() -> int:
    if not PROMPT_DIR.exists(): return 1
    max_n = 0
    for f in PROMPT_DIR.rglob("*.md"):
        m = re.match(r'^(\d+)_', f.name)
        if m: max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def create_prompt_file(alias, description="", category="",
                        ptype="", tags=None, state=None) -> tuple:
    """
    Creates a new prompt file in 004_prompts/ using the standard v0.5.0 template.
    Returns (filename, filepath) or (None, None) on failure.
    """
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    alias_clean = alias.strip().replace(" ","_").lower()

    # Check duplicate
    if _find_by_alias(alias_clean):
        log_write(f"Alias already exists: {alias_clean}", "WARNING")
        return None, None

    num      = _next_prompt_number()
    filename = f"{num:05d}_{alias_clean}.md"
    filepath = PROMPT_DIR / filename

    tags_block = ""
    if tags:
        tags_block = "\n" + "\n".join(f"  - {t}" for t in tags)

    content = PROMPT_TEMPLATE.format(
        id          = _generate_id(),
        name        = alias_clean,
        description = description,
        category    = category,
        ptype       = ptype or "task",
        created     = datetime.now().strftime("%Y-%m-%d"),
        tags_block  = tags_block,
    )
    filepath.write_text(content)

    if state:
        state["prompt_counter"] = max(state.get("prompt_counter",0), num)
        save_state(state)

    _append_prompt_index_md(alias_clean, filename)
    log_write(f"Created prompt: {filename}")
    return filename, filepath


def _append_prompt_index_md(alias, filename):
    idx_path = PROMPT_DIR / "prompt_index.md"
    if not idx_path.exists():
        idx_path.write_text("# Prompt Index\n\n")
    m = re.match(r'^(\d+)_', filename)
    num = m.group(1) if m else "?????"
    with open(idx_path, "a") as f:
        f.write(f"{num} | {alias} | [[{filename}]]\n")


def _find_by_alias(alias: str) -> Path:
    """Quick scan for existing alias match."""
    alias_c = alias.strip().lower()
    if not PROMPT_DIR.exists(): return None
    for f in PROMPT_DIR.rglob("*.md"):
        if f.name in ("prompt_index.md","README.md"): continue
        stem = re.sub(r"^\d+_","",f.stem).lower()
        if stem == alias_c: return f
        try:
            meta, _ = _parse_fm(f.read_text())
            als = meta.get("aliases",[])
            if isinstance(als,list) and alias_c in [a.lower() for a in als]:
                return f
        except Exception:
            pass
    return None


# ── Prompt commands ────────────────────────────────────────────────────────────

def _prompt_edit_meta(filepath: Path, field: str, value) -> bool:
    """
    Safe in-place metadata field update.
    Reads file, updates one field, writes back via temp.
    Never modifies body.
    """
    try:
        content    = filepath.read_text()
        meta, body = _parse_fm(content)
        if not meta:
            log_write(f"No frontmatter: {filepath.name}", "WARNING")
            return False
        meta[field] = value
        _write_prompt_safe(filepath, meta, body)   # no old_body → no version bump
        return True
    except Exception as e:
        log_write(f"Edit meta {filepath.name} field={field}: {e}", "ERROR")
        return False


def cmd_add_tag(filepath: Path, tag: str) -> bool:
    content    = filepath.read_text()
    meta, body = _parse_fm(content)
    tags = meta.get("tags", [])
    if not isinstance(tags, list): tags = []
    tag_clean = tag.strip().lower()
    if tag_clean in [t.lower() for t in tags]:
        return False  # already exists
    tags.append(tag_clean)
    meta["tags"] = tags
    _write_prompt_safe(filepath, meta, body)
    return True


def cmd_remove_tag(filepath: Path, tag: str) -> bool:
    content    = filepath.read_text()
    meta, body = _parse_fm(content)
    tags = meta.get("tags", [])
    if not isinstance(tags, list): return False
    new_tags = [t for t in tags if t.lower() != tag.strip().lower()]
    if len(new_tags) == len(tags): return False
    meta["tags"] = new_tags
    _write_prompt_safe(filepath, meta, body)
    return True


def cmd_add_alias(filepath: Path, alias: str) -> bool:
    content    = filepath.read_text()
    meta, body = _parse_fm(content)
    aliases = meta.get("aliases", [])
    if not isinstance(aliases, list): aliases = []
    a_clean = alias.strip().lower()
    if a_clean in [a.lower() for a in aliases]: return False
    aliases.append(a_clean)
    meta["aliases"] = aliases
    _write_prompt_safe(filepath, meta, body)
    return True


def cmd_rename_prompt(filepath: Path, new_name: str) -> Path:
    """Rename: updates name+aliases in metadata. File rename is optional."""
    content    = filepath.read_text()
    meta, body = _parse_fm(content)
    old_name   = meta.get("name","")
    meta["name"]    = new_name.strip()
    meta["updated"] = datetime.now().strftime("%Y-%m-%d")
    # Add new name to aliases
    aliases = meta.get("aliases", [])
    if not isinstance(aliases, list): aliases = []
    new_clean = new_name.strip().lower()
    if new_clean not in [a.lower() for a in aliases]:
        aliases.append(new_clean)
    meta["aliases"] = aliases
    _write_prompt_safe(filepath, meta, body)
    return filepath


def cmd_set_status(filepath: Path, status: str) -> bool:
    if status not in ("draft","active","archived"): return False
    return _prompt_edit_meta(filepath, "status", status)


# ── Terminal: prompt selection helper ──────────────────────────────────────────

def _pick_prompt_interactive(prompt_text="Select prompt") -> tuple:
    """Numbered list of library prompts → returns (filepath, meta, body) or (None,None,None)."""
    library = []
    if PROMPT_DIR.exists():
        for f in sorted(PROMPT_DIR.rglob("*.md")):
            if f.name in ("prompt_index.md","prompt_index.json","README.md"):
                continue
            try:
                content = f.read_text()
                meta, body = _parse_fm(content)
                library.append((f, meta, body))
            except Exception:
                pass
    if not library:
        print_info("Prompt library is empty. Create prompts first.")
        return None, None, None
    print()
    for i, (fp, meta, body) in enumerate(library, 1):
        name   = meta.get("name", fp.stem)
        ptype  = meta.get("type","")
        status = meta.get("status","")
        print(f"  {c(C_NUM,str(i))}  {c(C_SELECT,name):<28}"
              f"  {hint(ptype):<12}  {hint(status)}")
    print_nav()
    ch = get_choice(prompt_text)
    if ch.lower() in ("q","0"): return None, None, None
    if ch.isdigit() and 1 <= int(ch) <= len(library):
        return library[int(ch)-1]
    return None, None, None


# ── /command dispatcher ────────────────────────────────────────────────────────

def handle_slash_command(cmd: str, state, sysconf, pconf, idx) -> bool:
    """
    Handle /commands from terminal menu input.
    Returns True if a command was handled (prevents numbered menu logic).
    """
    cmd = cmd.strip().lower()

    if cmd == "/newprompt":
        state = menu_create_prompt(state)
        return True

    if cmd == "/preview":
        menu_preview_composition(state, sysconf, pconf, idx)
        return True

    if cmd.startswith("/search"):
        parts = cmd.split(None, 1)
        kw    = parts[1] if len(parts) > 1 else ""
        menu_search_prompts(kw, idx)
        return True

    if cmd == "/health":
        menu_health_report()
        return True

    if cmd in ("/editprompt", "/addtag", "/removetag",
               "/addalias", "/renameprompt"):
        menu_prompt_commands(cmd[1:], idx)
        return True

    return False


# ── Terminal menus ─────────────────────────────────────────────────────────────

def menu_live_edit(state, sysconf, pconf):
    defaults = state.get("session_defaults",{})
    lf = {}
    print_header("Live Edit", "All fields skippable — blank keeps default")
    lf["model"] = prompt_input("model", default=defaults.get("model",""),
                                example="claude-sonnet-4-6")
    print(f"\n  {c(C_NUM,'pipeline_stage')}:")
    cur = defaults.get("pipeline_stage","capture")
    for i,s in enumerate(PIPELINE_STAGES,1):
        print(f"    {'→' if s==cur else ' '} {c(C_NUM,str(i))} {s}")
    raw = prompt_input("Select number or type", default=cur)
    lf["pipeline_stage"] = (PIPELINE_STAGES[int(raw)-1]
        if raw.isdigit() and 1<=int(raw)<=len(PIPELINE_STAGES) else (raw or cur))
    print(f"\n  {c(C_NUM,'input_type')}:")
    cur_i = defaults.get("input_type","clipboard")
    for i,t in enumerate(INPUT_TYPES,1):
        print(f"    {'→' if t==cur_i else ' '} {c(C_NUM,str(i))} {t}")
    raw = prompt_input("Select number or type", default=cur_i)
    lf["input_type"] = (INPUT_TYPES[int(raw)-1]
        if raw.isdigit() and 1<=int(raw)<=len(INPUT_TYPES) else (raw or cur_i))
    derived = derive_session_topic("", state, pconf)
    lf["session_topic"] = prompt_input("session_topic", default=derived,
                                        example="linux_workflow")
    raw_tags = prompt_input("tags (comma separated)", example="ai-workflow")
    lf["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()] \
                 if raw_tags else []
    note = prompt_input("custom note (blank to skip)",
                         default=state.get("custom_note",""))
    if confirm("Save model/stage/type as new defaults?"):
        state["session_defaults"]["model"]          = lf.get("model","")
        state["session_defaults"]["pipeline_stage"] = lf.get("pipeline_stage","capture")
        state["session_defaults"]["input_type"]     = lf.get("input_type","clipboard")
        state["custom_note"] = note
        save_state(state)
        print_ok("Defaults saved.")
    return lf, note


def menu_active_prompts(state, idx):
    while True:
        active  = state.get("active_prompts",[])
        print_header("Active Prompts",
                     "Aliases shown in every SESSION block · bundles auto-expand")
        if active:
            print()
            for i, alias in enumerate(active, 1):
                fp, meta, _ = resolve_prompt(alias, idx)
                ptype  = meta.get("type","")   if meta else ""
                status = meta.get("status","") if meta else ""
                found  = c(C_OK,"✓") if fp else c(C_WARN,"?")
                print(f"  {c(C_NUM,str(i))}.  {found}  {c(C_SELECT,alias):<28}"
                      f"  {hint(ptype):<12}  {hint(status)}")
        else:
            print_info("No active prompts.")
        n = len(active)
        print()
        print_menu_item(n+1, "Add from library",   "pick by number")
        print_menu_item(n+2, "Add by typing",       "type alias or /newprompt")
        print_menu_item(n+3, "Remove",              "remove from active list")
        print_menu_item(n+4, "Reorder",             "change slot order")
        print_menu_item(n+5, "Add bundle",          "expand vault/bundles/*.md")
        print_nav()
        ch = get_choice()
        if ch.lower() in ("q","0"): return state
        if ch == "??": _show_help("prompts"); continue
        if not ch.isdigit(): continue
        idx_n = int(ch)
        if idx_n == n+1:
            fp, meta, body = _pick_prompt_interactive("Add")
            if fp:
                alias = meta.get("name", fp.stem)
                if alias not in active:
                    state["active_prompts"].append(alias)
                    save_state(state); print_ok(f"Added: {alias}")
                else:
                    print_info("Already active.")
            pause()
        elif idx_n == n+2:
            alias = prompt_input("Alias", example="brainstorm")
            if alias:
                alias = alias.strip().replace(" ","_").lower()
                if alias not in active:
                    state["active_prompts"].append(alias); save_state(state)
                    print_ok(f"Added: {alias}")
                    if not resolve_prompt(alias, idx)[0]:
                        print_info("No file found for alias — will auto-create on first clean.")
                else:
                    print_info("Already active.")
            pause()
        elif idx_n == n+3:
            if not active: pause(); continue
            for i, a in enumerate(active, 1): print_menu_item(i, a)
            rc = get_choice("Remove number")
            if rc.isdigit() and 1<=int(rc)<=len(active):
                removed = active.pop(int(rc)-1)
                state["active_prompts"] = active
                save_state(state); print_ok(f"Removed: {removed}")
            pause()
        elif idx_n == n+4:
            if len(active) < 2: print_info("Need 2+ prompts."); pause(); continue
            for i, a in enumerate(active, 1): print_menu_item(i, a)
            rc = get_choice("Move which number")
            if rc.isdigit() and 1<=int(rc)<=len(active):
                item = active.pop(int(rc)-1)
                for i, a in enumerate(active, 1): print_menu_item(i, a)
                pos = get_choice(f"Insert '{item}' before position")
                if pos.isdigit() and 1<=int(pos)<=len(active)+1:
                    active.insert(int(pos)-1, item)
                else:
                    active.append(item)
                state["active_prompts"] = active
                save_state(state); print_ok("Order updated.")
            pause()
        elif idx_n == n+5:
            _show_bundles_and_add(state)
    return state


def _show_bundles_and_add(state):
    if not BUNDLE_DIR.exists() or not list(BUNDLE_DIR.glob("*.md")):
        print_info("No bundle files found in vault/bundles/.")
        pause(); return
    bundles = []
    for f in sorted(BUNDLE_DIR.glob("*.md")):
        meta, _ = _parse_fm(f.read_text())
        bundles.append((f.stem, meta.get("description",""), meta))
    print_header("Bundles", "vault/bundles/")
    for i, (stem, desc, meta) in enumerate(bundles, 1):
        prompts_list = meta.get("prompts",[])
        n = len(prompts_list) if isinstance(prompts_list,list) else 0
        print(f"  {c(C_NUM,str(i))}  {c(C_SELECT,stem):<24}  "
              f"{hint(desc or '')}  {hint(f'{n} prompts')}")
    print_nav()
    rc = get_choice("Add bundle number")
    if rc.isdigit() and 1<=int(rc)<=len(bundles):
        stem = bundles[int(rc)-1][0]
        if stem not in state["active_prompts"]:
            state["active_prompts"].append(stem)
            save_state(state); print_ok(f"Bundle '{stem}' added to active prompts.")
        else:
            print_info("Already active.")
    pause()


def menu_create_prompt(state):
    """
    Prompt Studio — /newprompt wizard.
    Creates a new v0.5.0 prompt file with full metadata.
    """
    print_header("Prompt Studio", "/newprompt — create a new prompt file")
    num = _next_prompt_number()
    print_info(f"Next number: {c(C_SELECT, f'{num:05d}')}")

    alias = prompt_input("Name / alias", example="concept_extract")
    if not alias:
        print_info("Cancelled."); pause(); return state
    alias = alias.strip().replace(" ","_").lower()
    if _find_by_alias(alias):
        print_err(f"Alias '{alias}' already exists. Use /addalias to add to existing.")
        pause(); return state

    description = prompt_input("Description (optional)",
                                example="Extract key concepts as wikilinks")
    category = prompt_input("Category (optional)",
                             example="tasks / styles / formats / workflows / constraints")
    print(f"\n  {hint('type — sets composition order:')}")
    for i, t in enumerate(TYPE_ORDER, 1):
        print(f"  {c(C_NUM,str(i))} {t}")
    raw_type = get_choice("Select type number (or blank for task)")
    ptype = (TYPE_ORDER[int(raw_type)-1]
             if raw_type.isdigit() and 1<=int(raw_type)<=len(TYPE_ORDER)
             else "task")

    raw_tags = prompt_input("Initial tags (comma separated, blank to skip)",
                             example="creative, brainstorm")
    tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()] \
           if raw_tags else []

    print()
    print(f"  {hint('Will create:')} {c(C_SELECT, f'{num:05d}_{alias}.md')}")
    print(f"  {hint('type:')} {ptype}  {hint('status:')} draft")
    if description: print(f"  {hint('description:')} {description}")
    if tags:        print(f"  {hint('tags:')} {', '.join(tags)}")
    print()

    if not confirm("Create prompt?"):
        print_info("Cancelled."); pause(); return state

    fname, fpath = create_prompt_file(
        alias, description=description, category=category,
        ptype=ptype, tags=tags, state=state)
    if fname:
        print_ok(f"Created: {fname}")
        print_info("Open in Obsidian to write Purpose / Instructions / Output Format.")
        if confirm("Add to active prompts now?"):
            if alias not in state["active_prompts"]:
                state["active_prompts"].append(alias)
                save_state(state); print_ok(f"'{alias}' added to active prompts.")
    else:
        print_err("Creation failed. Check logs/debug.log.")
    pause()
    return state


def menu_search_prompts(keyword: str = "", idx: dict = None):
    """
    /search <keyword> — search name, aliases, tags, description.
    """
    if not keyword:
        keyword = prompt_input("Search keyword", example="brainstorm")
    if not keyword:
        pause(); return

    kw = keyword.strip().lower()
    results = []

    if PROMPT_DIR.exists():
        for f in sorted(PROMPT_DIR.rglob("*.md")):
            if f.name in ("prompt_index.md","prompt_index.json","README.md"):
                continue
            try:
                content    = f.read_text()
                meta, body = _parse_fm(content)
                if not meta: continue

                name  = meta.get("name","").lower()
                desc  = meta.get("description","").lower()
                tags  = " ".join(meta.get("tags",[])  if isinstance(meta.get("tags"),list)  else []).lower()
                als   = " ".join(meta.get("aliases",[]) if isinstance(meta.get("aliases"),list) else []).lower()
                stem  = re.sub(r"^\d+_","",f.stem).lower()

                if kw in name or kw in desc or kw in tags or kw in als or kw in stem:
                    results.append((f, meta))
            except Exception:
                pass

    print_header("Search Results", f"keyword: '{keyword}'")
    if not results:
        print_info("No matches found.")
    else:
        for fp, meta in results:
            name   = meta.get("name", fp.stem)
            ptype  = meta.get("type","")
            status = meta.get("status","")
            desc   = meta.get("description","")[:60]
            tags   = ", ".join(meta.get("tags",[]) if isinstance(meta.get("tags"),list) else [])
            print()
            print(f"  {c(C_SELECT, name)}")
            if ptype or status:
                print(f"  {hint('type:')} {ptype}  {hint('status:')} {status}")
            if desc:
                print(f"  {hint(desc)}")
            if tags:
                print(f"  {hint('tags:')} {tags}")
    pause()


def menu_preview_composition(state, sysconf, pconf, idx):
    """
    /preview — show the fully composed prompt before copying.
    """
    active = state.get("active_prompts",[])
    print_header("Preview Composition",
                 "Fully assembled instructions — exactly what goes into SESSION")
    if not active:
        print_info("No active prompts. Add some first.")
        pause(); return

    expanded = expand_active_prompts(active, idx)
    print()
    print(f"  {hint('Active:')} {', '.join(active)}")
    print()
    composed = compose_prompts(expanded, sysconf)
    if composed.strip():
        print(f"  {hint('--- Composed output ---')}")
        print()
        for line in composed.split("\n"):
            print(f"  {line}")
    else:
        print_info("No instruction bodies found.")
        print_info("Prompt files may be empty stubs.")
        print_info("Fill in Instructions sections in Obsidian first.")
    print()
    pause()


def menu_prompt_commands(subcmd: str = "", idx: dict = None):
    """
    Hub for /editprompt, /addtag, /removetag, /addalias, /renameprompt.
    """
    if not subcmd:
        print_header("Prompt Commands", "/editprompt /addtag /removetag /addalias /renameprompt")
        print_menu_item(1, "/editprompt",   "edit description, type, status, category")
        print_menu_item(2, "/addtag",       "add a tag to a prompt")
        print_menu_item(3, "/removetag",    "remove a tag from a prompt")
        print_menu_item(4, "/addalias",     "add alias to a prompt")
        print_menu_item(5, "/renameprompt", "rename a prompt (updates metadata, keeps file)")
        print_nav()
        ch = get_choice()
        if ch in ("q","0"): return
        cmds = ["editprompt","addtag","removetag","addalias","renameprompt"]
        if ch.isdigit() and 1<=int(ch)<=len(cmds):
            subcmd = cmds[int(ch)-1]
        else:
            return

    print_header(f"/{subcmd}")
    fp, meta, body = _pick_prompt_interactive("Select prompt")
    if not fp: return

    name = meta.get("name", fp.stem)

    if subcmd == "editprompt":
        print_info(f"Editing: {name}")
        fields = ["description","type","status","category"]
        for i, f in enumerate(fields, 1):
            cur = meta.get(f,"")
            print_menu_item(i, f, hint_text=f"current: {cur}")
        ch = get_choice("Edit field number")
        if ch.isdigit() and 1<=int(ch)<=len(fields):
            field = fields[int(ch)-1]
            if field == "type":
                for i, t in enumerate(TYPE_ORDER, 1):
                    print_menu_item(i, t)
                raw = get_choice("Select")
                v = TYPE_ORDER[int(raw)-1] if raw.isdigit() and 1<=int(raw)<=len(TYPE_ORDER) else ""
            elif field == "status":
                for i, s in enumerate(STATUS_VALUES, 1):
                    print_menu_item(i, s)
                raw = get_choice("Select")
                v = STATUS_VALUES[int(raw)-1] if raw.isdigit() and 1<=int(raw)<=len(STATUS_VALUES) else ""
            else:
                v = prompt_input(f"New {field}", default=meta.get(field,""))
            if v:
                if _prompt_edit_meta(fp, field, v):
                    print_ok(f"{name}.{field} → {v}")
                else:
                    print_err("Update failed.")

    elif subcmd == "addtag":
        tag = prompt_input("Tag to add", example="creative")
        if tag:
            if cmd_add_tag(fp, tag): print_ok(f"Tag '{tag}' added to {name}")
            else: print_info("Tag already exists.")

    elif subcmd == "removetag":
        tags = meta.get("tags",[])
        if not isinstance(tags,list) or not tags:
            print_info("No tags on this prompt."); pause(); return
        for i, t in enumerate(tags, 1): print_menu_item(i, t)
        rc = get_choice("Remove number")
        if rc.isdigit() and 1<=int(rc)<=len(tags):
            tag = tags[int(rc)-1]
            if cmd_remove_tag(fp, tag): print_ok(f"Removed: {tag}")

    elif subcmd == "addalias":
        alias = prompt_input("New alias", example="bs")
        if alias:
            if cmd_add_alias(fp, alias): print_ok(f"Alias '{alias}' added to {name}")
            else: print_info("Alias already exists.")

    elif subcmd == "renameprompt":
        new_name = prompt_input("New name", default=name)
        if new_name and new_name != name:
            cmd_rename_prompt(fp, new_name)
            print_ok(f"Renamed: {name} → {new_name}")
            print_info("File stays at original path. Run prompt_manager [3] to rebuild index.")

    pause()


def menu_health_report():
    """Display latest prompt_health_report.json or prompt to generate it."""
    if not HEALTH_JSON.exists():
        print_header("/health", "No health report found")
        print_info("Run prompt_manager.py [4] to generate one.")
        print_info("Or run: python3 prompt_manager.py --health")
        pause(); return
    try:
        with open(HEALTH_JSON) as f:
            report = json.load(f)
    except Exception:
        print_err("Could not read health report."); pause(); return

    s = report.get("summary", {})
    ts= report.get("generated","")[:10]
    print_header("/health", f"Prompt health report — {ts}")
    print()
    def row(label, val, warn=False):
        col = C_WARN if (warn and val > 0) else C_OK
        print(f"  {hint(label):<28} {c(col, str(val))}")
    row("Total prompts",       s.get("total",0))
    row("Unused",              s.get("unused",0),      warn=True)
    row("Missing tags",        s.get("missing_tags",0),warn=True)
    row("Missing type",        s.get("missing_type",0),warn=True)
    row("No aliases",          s.get("no_aliases",0),  warn=True)
    row("Stale drafts (>30d)", s.get("stale_drafts",0),warn=True)
    row("Duplicates",          s.get("duplicates",0),  warn=True)
    row("Archived",            s.get("archived",0))
    print()
    most = report.get("most_used",[])
    if most:
        print(f"  {hint('Top used:')}")
        for e in most[:5]:
            print(f"    {c(C_SELECT,e['name']):<30} {c(C_NUM,str(e['count']))}")
    print()
    print_info("Run prompt_manager.py to rebuild report with latest data.")
    pause()


def menu_session_defaults(state):
    while True:
        d = state.get("session_defaults",{})
        print_header("Session Defaults", "Hotkey uses these — Live Edit overrides per session")
        print(f"\n  model:          {c(C_SELECT, d.get('model','') or '(none)')}")
        print(f"  pipeline_stage: {c(C_SELECT, d.get('pipeline_stage','capture'))}")
        print(f"  input_type:     {c(C_SELECT, d.get('input_type','clipboard'))}")
        print()
        print_menu_item(1,"Set model");    print_menu_item(2,"Set pipeline_stage")
        print_menu_item(3,"Set input_type"); print_nav()
        ch = get_choice()
        if ch in ("q","0"): return state
        if ch == "1":
            v = prompt_input("model", default=d.get("model",""),
                             example="claude-sonnet-4-6")
            state["session_defaults"]["model"] = v
            save_state(state); print_ok(f"model → {v or '(cleared)'}"); pause()
        elif ch == "2":
            for i,s in enumerate(PIPELINE_STAGES,1): print_menu_item(i,s)
            raw = get_choice("Select")
            if raw.isdigit() and 1<=int(raw)<=len(PIPELINE_STAGES):
                v = PIPELINE_STAGES[int(raw)-1]
                state["session_defaults"]["pipeline_stage"] = v
                save_state(state); print_ok(f"pipeline_stage → {v}")
            pause()
        elif ch == "3":
            for i,t in enumerate(INPUT_TYPES,1): print_menu_item(i,t)
            raw = get_choice("Select")
            if raw.isdigit() and 1<=int(raw)<=len(INPUT_TYPES):
                v = INPUT_TYPES[int(raw)-1]
                state["session_defaults"]["input_type"] = v
                save_state(state); print_ok(f"input_type → {v}")
            pause()
    return state


def menu_preview_block(state, sysconf, pconf, idx):
    now_m   = datetime.now().strftime("%Y-%m")
    next_n  = state["log"]["current_number"] + 1
    log_num = f"{now_m}-LOG-{next_n:04d}"
    output  = build_session_block(log_num, next_n, state, sysconf, pconf, idx)
    print_header("Preview Block", "Exactly what will be copied on next press")
    print(); print(output); print()
    pause()


# ── Help ───────────────────────────────────────────────────────────────────────

HELP_PAGES = {
    "main": """
  PROMPTER v6  (spec v0.5.0)
  ─────────────────────────────────────────
  SESSION blocks now include a composed INSTRUCTIONS section.

  COMPOSITION ENGINE:
    Active prompts are resolved from vault/004_prompts/.
    Sorted by type: task → workflow → style → format → constraint
    Assembled under ## headers in ---INSTRUCTIONS--- block.
    AI receives structured instructions, not raw aliases.

  /COMMANDS (type in the choice prompt):
    /newprompt    create a new prompt (Prompt Studio)
    /preview      show composed instructions before copying
    /search kw    search prompts by keyword
    /health       show prompt health report
    /editprompt   edit type / status / description
    /addtag       add tag to a prompt
    /removetag    remove tag from a prompt
    /addalias     add alias to a prompt
    /renameprompt rename a prompt

  BUNDLES:
    vault/bundles/name.md — macro stacks of aliases
    Add a bundle to active prompts — it expands automatically.

  PORTABILITY:
    All paths relative to script location. USB-safe.
""",
    "prompts": """
  PROMPT LIBRARY (v0.5.0)
  ─────────────────────────────────────────
  Files: vault/004_prompts/00001_alias.md
  Type field sets composition order.
  Status: draft → active → archived
  Aliases: list — all resolve to same file

  Run prompt_manager.py to validate and build index.
""",
}

def _show_help(page):
    print(); print(divider())
    print(c(BOLD+C_HEADER,"  HELP")); print(divider())
    print(HELP_PAGES.get(page, "  No help for this page.")); pause()


# ── Main terminal menu ─────────────────────────────────────────────────────────

def terminal_menu(state, sysconf, pconf):
    idx = load_prompt_index()

    while True:
        active    = state.get("active_prompts",[])
        log_n     = state["log"]["current_number"]
        month     = state["log"]["current_month"] or datetime.now().strftime("%Y-%m")
        idx_count = len(idx.get("aliases",{}))

        print_header(f"prompter  v{VERSION}  ({SPEC})",
                     "SESSION builder · composition engine · /commands")
        print(f"  {hint('Log:')}    {c(C_SELECT,f'{month}-LOG-{log_n:04d}')}")
        print(f"  {hint('Active:')} {c(C_OK,str(len(active))) if active else c(C_WARN,'none')}"
              f"  {hint('index: '+str(idx_count)+' aliases')}")
        print(f"  {hint('model:')}  {c(C_SELECT,state['session_defaults'].get('model','') or '(none)')}")
        print()
        print_menu_item(1,"Copy to clipboard",     "uses saved defaults")
        print_menu_item(2,"Live edit + copy",       "set fields before copying")
        print_menu_item(3,"Preview composition",    "/preview — see composed instructions")
        print_menu_item(4,"Preview block",          "full SESSION block without copying")
        print()
        print_menu_item(5,"Active prompts",         "manage aliases + bundles")
        print_menu_item(6,"Create prompt",          "/newprompt — Prompt Studio")
        print_menu_item(7,"Search prompts",         "/search — find by keyword")
        print()
        print_menu_item(8,"Prompt commands",        "/editprompt /addtag etc.")
        print_menu_item(9,"Health report",          "/health")
        print_menu_item(10,"Session defaults",      "model, pipeline_stage, input_type")
        print_menu_item(11,"Bootstrap dirs",        "create missing vault folders")
        print()
        print(f"  {c(C_KEY,'q')} exit   {c(C_KEY,'??')} help   "
              f"{hint('/newprompt  /preview  /search kw  /health  ...')}")
        print()

        ch = get_choice()
        ch_l = ch.strip().lower()

        if ch_l in ("0","q"):
            print(c(C_HINT,"\n  Goodbye.\n")); break

        if ch_l == "??":
            _show_help("main"); continue

        # /command handling
        if ch_l.startswith("/"):
            if handle_slash_command(ch_l, state, sysconf, pconf, idx):
                idx = load_prompt_index()   # refresh after any changes
                continue

        if not ch.isdigit(): continue

        n = int(ch)
        if n == 1:
            lnum, lraw = get_and_increment_log(state)
            note   = state.get("custom_note","")
            output = build_session_block(lnum, lraw, state, sysconf, pconf, idx,
                                          custom_note=note)
            if copy_to_clipboard(output):
                save_state(state)
                print_ok(f"Copied. Log: {lnum}")
                notify("prompter", f"Copied {lnum}", state)
                # ── flow hook ────────────────────────────────────────────
                if _FLOW_AVAILABLE and _is_flow_active(pconf):
                    def _build_next():
                        _lnum, _lraw = get_and_increment_log(state)
                        _out = build_session_block(
                            _lnum, _lraw, state, sysconf, pconf, idx,
                            custom_note=state.get("custom_note","")
                        )
                        return _out, _lnum
                    _run_post_copy(
                        output, lnum, pconf,
                        copy_fn=copy_to_clipboard,
                        save_fn=lambda: save_state(state),
                        build_fn=_build_next,
                    )
                else:
                    pause()
                # ─────────────────────────────────────────────────────────
            else:
                print_err("wl-copy failed. Check logs/debug.log")
                pause()

        elif n == 2:
            lf, ln = menu_live_edit(state, sysconf, pconf)
            lnum, lraw = get_and_increment_log(state)
            output = build_session_block(lnum, lraw, state, sysconf, pconf, idx,
                                          custom_note=ln, live_fields=lf)
            if copy_to_clipboard(output):
                save_state(state)
                print_ok(f"Copied with live edits. Log: {lnum}")
            else:
                print_err("wl-copy failed.")
            pause()

        elif n == 3: menu_preview_composition(state, sysconf, pconf, idx)
        elif n == 4: menu_preview_block(state, sysconf, pconf, idx)
        elif n == 5:
            state = menu_active_prompts(state, idx)
            idx   = load_prompt_index()
        elif n == 6:
            state = menu_create_prompt(state)
            idx   = load_prompt_index()
        elif n == 7: menu_search_prompts(idx=idx)
        elif n == 8:
            menu_prompt_commands(idx=idx)
            idx = load_prompt_index()
        elif n == 9:  menu_health_report()
        elif n == 10: state = menu_session_defaults(state)
        elif n == 11:
            bootstrap_directories(state)
            print_ok("Bootstrap complete."); pause()


# ── Hotkey ─────────────────────────────────────────────────────────────────────

def run_hotkey(state, sysconf, pconf):
    idx    = load_prompt_index()
    lnum, lraw = get_and_increment_log(state)
    note   = state.get("custom_note","")
    output = build_session_block(lnum, lraw, state, sysconf, pconf, idx,
                                  custom_note=note)
    if copy_to_clipboard(output):
        save_state(state)
        log_write(f"Hotkey: copied {lnum}")
        notify("prompter", f"Copied {lnum}", state)
    else:
        log_write("Hotkey: wl-copy failed.", "ERROR")
        notify("prompter ERROR", "wl-copy failed", state)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hotkey",  action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    _startup_checks("P")
    _check_snapshot(source="P", interactive=not args.hotkey)
    state   = load_state()
    sysconf = load_system_config()
    pconf   = load_prompter_config()
    bootstrap_directories(state, sysconf)
    if not args.hotkey and _WARN_AVAILABLE:
        _warn_display(
            SCRIPT_DIR.parent, sysconf,
            conf_dir=CONF_DIR,
            modules_dir=SCRIPT_DIR.parent / "modules",
            max_log_lines=400,
            source="P",
        )

    if args.dry_run:
        idx    = load_prompt_index()
        now_m  = datetime.now().strftime("%Y-%m")
        lnum   = f"{now_m}-LOG-{state['log']['current_number']+1:04d}"
        output = build_session_block(lnum, 0, state, sysconf, pconf, idx)
        print_header("DRY RUN","Nothing copied"); print(); print(output)
        return

    if args.hotkey:
        run_hotkey(state, sysconf, pconf); return

    terminal_menu(state, sysconf, pconf)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(c(C_HINT, "\n\n  Exited cleanly.\n"))
        log_write("Exited via KeyboardInterrupt.")
        sys.exit(0)
