#!/usr/bin/env python3
"""
cleaner.py | Version 4.0.0 | Spec v0.5.0
Parses SESSION blocks, archives to vault, updates prompt intelligence.
Zero dependencies — pure Python 3.x.

### PORTABLE: all paths relative to SCRIPT_DIR
### Scripts: ai_framework_vault/scripts/
### Vault:   ai_framework_vault/ai-vault/
### Prompts: ai-vault/004_prompts/  (flat + subdirs)
###
### HOTKEY SETUP (KDE):
### Silent:   bash hotkey_cleaner.sh    (Meta+C)
### Terminal: bash terminal_cleaner.sh  (Meta+Shift+C)
###
### INTELLIGENCE LAYER (v0.5.0):
### - update usage_count + last_used in prompt frontmatter (v0.5.0 format)
### - suggest tags from session_topic (appends, never overwrites)
### - track co-occurrence → update related: field
### - update prompt_health_report.json after each clean
###
### SAFE WRITE RULES (Obsidian compatibility):
### - read file → parse frontmatter → update metadata only
### - write temp file → validate → os.replace (atomic)
### - if metadata parse fails → skip file, log warning, do NOT corrupt
### - never modify instruction body
###
### KEY CHANGES FROM v3:
### - Prompt files use new v0.5.0 frontmatter (id, version, type, status, aliases[])
### - resolve_alias() uses prompt_index.json when available
### - update_prompt_intelligence() — tags + related field updates
### - Co-occurrence tracking written to vault/000_indexes/cooccurrence.json
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
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
    return input().strip().lower()
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

VERSION    = "4.0.0"
SPEC       = "v0.5.0"
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR.parent / "state.json"
CONF_DIR   = SCRIPT_DIR.parent / "configs"
LOG_DIR    = SCRIPT_DIR.parent / "logs"
DEBUG_LOG  = LOG_DIR / "debug.log"
SYSTEM_CONF= CONF_DIR / "system_config.json"

# ── Runtime path resolver ──────────────────────────────────────────────────────
# Reads vault_root and vault_folders from system_config.json.
# Falls back to legacy layout if config is missing or unreadable.
# All downstream code uses these names unchanged.

def _resolve_runtime_paths():
    try:
        if SYSTEM_CONF.exists():
            with open(SYSTEM_CONF, encoding="utf-8") as f:
                conf = json.load(f)
            vault_rel = conf.get("vault_root", "../ai-vault")
            folders   = conf.get("vault_folders", {})
            vault     = (SCRIPT_DIR.parent / vault_rel).resolve()
            return (
                vault,
                vault / folders.get("prompts",  "004_prompts"),
                vault / folders.get("sessions", "002_sessions"),
                vault / folders.get("raw",      "003_raw"),
                vault / folders.get("indexes",  "000_indexes"),
                vault / folders.get("topics",   "001_topics"),
                vault / folders.get("tags",     "005_tags"),
            )
    except Exception:
        pass
    vault = (SCRIPT_DIR.parent / "ai-vault").resolve()
    return (
        vault,
        vault / "004_prompts",
        vault / "002_sessions",
        vault / "003_raw",
        vault / "000_indexes",
        vault / "001_topics",
        vault / "005_tags",
    )

(VAULT_ROOT, PROMPT_DIR, SESSIONS_DIR,
 RAW_DIR, INDEXES_DIR, TOPICS_DIR, TAGS_DIR) = _resolve_runtime_paths()

INDEX_JSON   = PROMPT_DIR  / "prompt_index.json"
HEALTH_JSON  = PROMPT_DIR  / "prompt_health_report.json"
COOCCUR_JSON = INDEXES_DIR / "cooccurrence.json"

SESSION_OPEN  = "<---SESSION--->"
SESSION_CLOSE = "<---SESSION END--->"
MARKER_AI_START = "<---Marker 2--->"
MARKER_AI_END   = "<---Marker 3--->"

### v0.5.0 frontmatter field order (shared with prompter, prompt_manager)
FM_SIMPLE = ["id","version","name","description","category","type",
             "created","updated","usage_count","last_used","status"]
FM_LISTS  = ["aliases","tags","related"]

DEFAULT_SYSTEM_CONFIG = {
    "spec":   SPEC,
    "prompt_dir": "004_prompts",
    "session_template": {
        "prompt_field": "prompts", "list_prefix": "* ",
        "empty_slots": 2,
    },
    "prompt_parsing": {
        "alias_prefixes": ["* ", "- "], "case_sensitive": False,
        "strip_whitespace": True,
    },
}

DEFAULT_CLEANER_CONF = {
    "max_log_lines":     400,
    "raw_backup":        True,
    "yaml_fields": {
        "session_id":True, "year_month":True, "date":True, "time":True,
        "source":True, "model":True, "input_type":True, "pipeline_stage":True,
        "session_topic":True, "prompts_used":True, "tags":True,
        "message_length":True, "response_length":True, "prompt_count":True,
        "note":False,
    },
    "intelligence": {
        "suggest_tags":      True,   # append session_topic words as prompt tags
        "track_cooccurrence":True,   # record which prompts appear together
        "update_related":    True,   # write to related: field when co-occurrence high
        "cooccur_threshold": 3,      # min co-occurrences before adding to related
    },
}


# ── Logging ────────────────────────────────────────────────────────────────────

def log_write(msg, level="INFO"):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"{ts} | {level} | C | {msg}\n")


# ── Bootstrap ──────────────────────────────────────────────────────────────────

def bootstrap_directories(sysconf=None):
    if sysconf is None:
        sysconf = load_system_config()
    month = datetime.now().strftime("%Y-%m")
    # Runtime dirs — always beside script, not in vault
    for p in (LOG_DIR, CONF_DIR):
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


def _touch_index(path, header):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header)


# ── State ──────────────────────────────────────────────────────────────────────

def load_state():
    if not STATE_FILE.exists():
        s = _min_state(); save_state(s); return s
    try:
        with open(STATE_FILE) as f: state = json.load(f)
        if "cleaner_conf" not in state:
            state["cleaner_conf"] = dict(DEFAULT_CLEANER_CONF); save_state(state)
        return state
    except json.JSONDecodeError as e:
        log_write(f"state.json corrupted: {e}", "ERROR")
        print(c(C_ERR,"\n[ERROR] state.json corrupted.")); sys.exit(1)


def _min_state():
    return {
        "version":VERSION, "spec":SPEC,
        "log":{"current_number":0,"current_month":""},
        "active_prompts":[], "prompt_counter":0,
        "last_cleaned_log":0, "last_cleaned_month":"",
        "topics":{"keywords":[]}, "topic_derive_mode":"all_combined",
        "notifications_enabled":False,
        "cleaner_conf": dict(DEFAULT_CLEANER_CONF),
    }


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE,"w") as f: json.dump(state, f, indent=2)


# ── Config ─────────────────────────────────────────────────────────────────────

def load_system_config():
    if not SYSTEM_CONF.exists(): return dict(DEFAULT_SYSTEM_CONFIG)
    try:
        with open(SYSTEM_CONF) as f: conf = json.load(f)
        for k, v in DEFAULT_SYSTEM_CONFIG.items():
            if k not in conf: conf[k] = v
        return conf
    except Exception: return dict(DEFAULT_SYSTEM_CONFIG)


# ── Notifications ──────────────────────────────────────────────────────────────

def notify(title, msg, state):
    if not state.get("notifications_enabled"): return
    if not shutil.which("notify-send"): return
    try: subprocess.run(["notify-send", title, msg], check=True)
    except Exception as e: log_write(f"notify-send: {e}", "WARNING")


# ── Clipboard ──────────────────────────────────────────────────────────────────

def read_clipboard():
    try:
        r = subprocess.run(["wl-paste","--no-newline"],
                           capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None
    except FileNotFoundError:
        log_write("wl-paste not found.", "ERROR"); return None


# ── Frontmatter parser / writer (shared with prompter, prompt_manager) ─────────

def _parse_fm(content: str) -> tuple:
    """Parse YAML-style frontmatter. Returns (meta, body). Never raises."""
    try:
        if not content.startswith("---"): return {}, content
        rest = content[3:]
        if rest.startswith("\n"): rest = rest[1:]
        nl_d = rest.find("\n---")
        if nl_d == -1: return {}, content
        fm_text = rest[:nl_d]
        body    = rest[nl_d+4:]
        if body.startswith("\n"): body = body[1:]
        meta = {}
        cur_key = None; cur_list = None
        for line in fm_text.split("\n"):
            if not line.strip(): continue
            ls = line.lstrip()
            if ls.startswith("- ") and cur_list is not None:
                cur_list.append(ls[2:].strip().strip("\"'")); continue
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                k = k.strip(); v = v.strip().strip("\"'")
                if v:
                    meta[k] = v; cur_key = k; cur_list = None
                else:
                    lst=[]; meta[k]=lst; cur_key=k; cur_list=lst
        return meta, body
    except Exception as e:
        log_write(f"_parse_fm: {e}", "WARNING"); return {}, content


def _format_fm(meta: dict) -> str:
    lines = []
    for k in FM_SIMPLE:
        if k in meta:
            v = meta[k]
            lines.append(f"{k}:" if (v is None or v=="") else f"{k}: {v}")
    for k in FM_LISTS:
        if k in meta:
            v = meta[k]
            items = v if isinstance(v,list) else (
                [i.strip() for i in v.split(",") if i.strip()]
                if isinstance(v,str) and v else [])
            if items:
                lines.append(f"{k}:"); [lines.append(f"  - {i}") for i in items]
            else:
                lines.append(f"{k}:")
    return "\n".join(lines) + "\n"


def _write_prompt_safe(filepath: Path, meta: dict, body: str) -> bool:
    """
    Atomically update ONLY metadata of a prompt file.
    Instruction body passed in unchanged — this function never modifies it.
    Uses temp file → validate → os.replace for atomicity.
    If validation fails, temp is deleted and original is preserved.
    """
    fm      = _format_fm(meta)
    content = f"---\n{fm}---\n{body}"
    tmp     = filepath.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        test, _ = _parse_fm(tmp.read_text())
        if not test.get("id"):
            raise ValueError("id missing after round-trip")
        os.replace(str(tmp), str(filepath))
        log_write(f"Updated: {filepath.name}")
        return True
    except Exception as e:
        if tmp.exists(): tmp.unlink(missing_ok=True)
        log_write(f"Safe write FAILED {filepath.name}: {e}", "ERROR")
        return False


# ── Prompt index / alias resolution ───────────────────────────────────────────

def load_prompt_index() -> dict:
    """Load prompt_index.json. Fallback: scan files."""
    if INDEX_JSON.exists():
        try:
            with open(INDEX_JSON) as f:
                idx = json.load(f)
            if idx.get("aliases"): return idx
        except Exception: pass
    log_write("prompt_index.json missing — scanning files", "WARNING")
    idx = {"aliases":{}, "by_id":{}, "by_name":{}, "meta":{}}
    if not PROMPT_DIR.exists(): return idx
    for f in PROMPT_DIR.rglob("*.md"):
        if f.name in ("prompt_index.md","prompt_index.json","README.md"): continue
        try:
            content    = f.read_text()
            meta, body = _parse_fm(content)
            rel        = str(f.relative_to(VAULT_ROOT))
            stem       = re.sub(r"^\d+_","",f.stem).lower()
            name       = meta.get("name","").lower() or stem
            old_alias  = meta.get("alias","").lower()
            aliases    = ([a.strip().lower() for a in meta.get("aliases",[])
                          if isinstance(meta.get("aliases"),list)]
                         if isinstance(meta.get("aliases"),list) else [])
            for a in set([stem, name, old_alias]+aliases):
                if a and a not in idx["aliases"]:
                    idx["aliases"][a] = rel
            if meta.get("id"): idx["by_id"][meta["id"]] = rel
            if name:           idx["by_name"][name] = rel
        except Exception: pass
    return idx


def resolve_alias(alias: str, sysconf: dict, idx: dict = None) -> Path:
    """
    Resolve an alias → prompt filepath.
    Priority: prompt_index.json → direct file scan.
    Handles old format (number_alias.md stem) and new format (aliases:[]).
    Returns Path or None.
    """
    if idx is None: idx = load_prompt_index()
    pp     = sysconf.get("prompt_parsing",{})
    case   = pp.get("case_sensitive", False)
    alias_n = alias.strip()
    if pp.get("strip_whitespace",True): alias_n = alias_n.strip()
    if not case: alias_n = alias_n.lower()

    rel = idx.get("aliases",{}).get(alias_n)
    if rel:
        fp = VAULT_ROOT / rel
        if fp.exists(): return fp

    # Fallback: direct scan
    for f in PROMPT_DIR.rglob("*.md"):
        if f.name in ("prompt_index.md","prompt_index.json","README.md"): continue
        stem = re.sub(r"^\d+_","",f.stem)
        if (stem.lower() if not case else stem) == alias_n: return f
        try:
            meta, _ = _parse_fm(f.read_text())
            aliases = meta.get("aliases",[])
            if isinstance(aliases, list):
                norms = [a.lower() for a in aliases] if not case else aliases
                if alias_n in norms: return f
        except Exception: pass
    return None


# ── Prompt file creation (auto-create for unknown aliases) ─────────────────────

def _next_prompt_number() -> int:
    if not PROMPT_DIR.exists(): return 1
    max_n = 0
    for f in PROMPT_DIR.rglob("*.md"):
        m = re.match(r'^(\d+)_', f.name)
        if m: max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _generate_id() -> str:
    import uuid
    return datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]


def create_prompt_file(alias: str, sysconf: dict, state: dict) -> tuple:
    """
    Auto-create a v0.5.0 prompt stub for an unknown alias.
    Status defaults to 'draft'.
    Returns (filename, filepath) or (None, None).
    """
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)

    # Handle spaces → underscores
    alias_clean = alias.strip().replace(" ","_").lower()

    # Ensure unique filename
    num   = _next_prompt_number()
    base  = f"{num:05d}_{alias_clean}"
    filepath = PROMPT_DIR / f"{base}.md"
    n = 2
    while filepath.exists():
        filepath = PROMPT_DIR / f"{base}_{n}.md"
        alias_clean_n = f"{alias_clean}_{n}"
        n += 1

    content = (
        "---\n"
        f"id: {_generate_id()}\n"
        "version: 1.0\n"
        f"name: {alias_clean}\n"
        "description: Auto-created from session alias\n"
        "category:\n"
        "type: task\n"
        f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"updated: {datetime.now().strftime('%Y-%m-%d')}\n"
        "usage_count: 1\n"
        f"last_used: {datetime.now().strftime('%Y-%m-%d')}\n"
        "status: draft\n"
        "aliases:\n"
        f"  - {alias_clean}\n"
        "tags:\n"
        "related:\n"
        "---\n\n"
        f"# {alias_clean}\n\n"
        "## Purpose\n\n"
        "## Instructions\n\n"
        "## Output Format\n"
    )
    filepath.write_text(content)

    if state:
        state["prompt_counter"] = max(state.get("prompt_counter",0), num)
        save_state(state)

    # Append to human-readable prompt_index.md
    idx_md = PROMPT_DIR / "prompt_index.md"
    if not idx_md.exists(): idx_md.write_text("# Prompt Index\n\n")
    m = re.match(r'^(\d+)_', filepath.name)
    num_s = m.group(1) if m else "?????"
    with open(idx_md, "a") as f:
        f.write(f"{num_s} | {alias_clean} | [[{filepath.name}]]\n")

    log_write(f"Auto-created prompt: {filepath.name}")
    return filepath.name, filepath


# ── Prompt usage update ────────────────────────────────────────────────────────

def update_prompt_usage(filepath: Path, session_date: str) -> bool:
    """
    Update usage_count (increment) and last_used in prompt frontmatter.
    Safe: temp → validate → replace. Never touches body.
    Handles both old format (no id) and new v0.5.0 format.
    If frontmatter has no id field (old format), adds one.
    Returns True on success.
    """
    try:
        content    = filepath.read_text()
        meta, body = _parse_fm(content)
        if not meta:
            log_write(f"No frontmatter — skipping: {filepath.name}", "WARNING")
            return False

        # Handle old format: ensure id exists
        if not meta.get("id"):
            meta["id"] = _generate_id()
            log_write(f"Added id to: {filepath.name}")

        count = int(meta.get("usage_count",0) or 0)
        meta["usage_count"] = count + 1
        meta["last_used"]   = session_date

        return _write_prompt_safe(filepath, meta, body)
    except Exception as e:
        log_write(f"update_prompt_usage {filepath.name}: {e}", "ERROR")
        return False


# ── Intelligence layer ─────────────────────────────────────────────────────────

def update_prompt_intelligence(filepath: Path, session: dict,
                                conf: dict, all_aliases: list) -> None:
    """
    Analyzes session context and updates prompt metadata fields.
    Operations (all safe — never modify body):
      1. Suggest tags from session_topic words
      2. Update related: field based on co-occurring aliases
    Rules:
      - Only appends tags — never removes or overwrites existing tags
      - Only appends to related — never removes entries
      - Uses co-occurrence threshold from cleaner_conf.intelligence
      - Both operations can be disabled via cleaner_conf.intelligence flags
    """
    intel = conf.get("intelligence", DEFAULT_CLEANER_CONF["intelligence"])

    try:
        content    = filepath.read_text()
        meta, body = _parse_fm(content)
        if not meta: return
        changed = False

        # 1. Tag suggestion from session_topic
        if intel.get("suggest_tags", True):
            topic = session.get("session_topic", "")
            if topic:
                # Extract meaningful words from topic slug
                words = re.findall(r'[a-zA-Z]{3,}', topic)
                stop  = {"the","and","for","with","that","this","has","was",
                         "are","log","session","from","into","using"}
                new_tags = [w.lower() for w in words if w.lower() not in stop]
                existing = meta.get("tags", [])
                if not isinstance(existing, list): existing = []
                existing_lower = [t.lower() for t in existing]
                for tag in new_tags:
                    if tag not in existing_lower:
                        existing.append(tag)
                        changed = True
                if changed:
                    meta["tags"] = existing

        # 2. Co-occurrence → related field
        if intel.get("update_related", True):
            cooccur = _load_cooccurrence()
            alias   = meta.get("name","") or re.sub(r"^\d+_","",filepath.stem)
            alias   = alias.lower()
            threshold = intel.get("cooccur_threshold", 3)
            related   = meta.get("related", [])
            if not isinstance(related, list): related = []
            rel_lower = [r.lower() for r in related]

            for other in all_aliases:
                if other.lower() == alias: continue
                pair_key = _cooccur_key(alias, other)
                count    = cooccur.get(pair_key, 0)
                if count >= threshold and other.lower() not in rel_lower:
                    related.append(other)
                    rel_lower.append(other.lower())
                    changed = True
            if changed:
                meta["related"] = related

        if changed:
            _write_prompt_safe(filepath, meta, body)

    except Exception as e:
        log_write(f"intelligence update {filepath.name}: {e}", "ERROR")


def _cooccur_key(a: str, b: str) -> str:
    """Canonical co-occurrence key (order-independent)."""
    return "|".join(sorted([a.lower(), b.lower()]))


def _load_cooccurrence() -> dict:
    if COOCCUR_JSON.exists():
        try:
            with open(COOCCUR_JSON) as f: return json.load(f)
        except Exception: pass
    return {}


def _update_cooccurrence(aliases: list) -> None:
    """
    Increment co-occurrence counts for every pair of aliases in this session.
    Writes to vault/000_indexes/cooccurrence.json.
    """
    if len(aliases) < 2: return
    cooccur = _load_cooccurrence()
    for i, a in enumerate(aliases):
        for b in aliases[i+1:]:
            key = _cooccur_key(a, b)
            cooccur[key] = cooccur.get(key, 0) + 1
    INDEXES_DIR.mkdir(parents=True, exist_ok=True)
    COOCCUR_JSON.write_text(json.dumps(cooccur, indent=2))


# ── Handle prompts pipeline ────────────────────────────────────────────────────

def handle_prompts(session: dict, sysconf: dict, state: dict,
                   idx: dict = None) -> list:
    """
    Core prompt resolution for a single session.
    For each alias in session.prompts_used:
      1. Normalize alias
      2. Resolve via index / scan
      3. Found   → update usage_count + last_used
      4. Found   → run intelligence update (tags, related)
      5. Missing → auto-create prompt file (status: draft)
    Then: update co-occurrence tracking for all aliases in this session.
    Returns list of (alias, result_str).
    """
    if idx is None: idx = load_prompt_index()
    session_date = session.get("date") or datetime.now().strftime("%Y-%m-%d")
    aliases      = [a.strip() for a in session.get("prompts_used",[]) if a.strip()]
    results      = []
    cc           = state.get("cleaner_conf", DEFAULT_CLEANER_CONF)

    for alias in aliases:
        fp = resolve_alias(alias, sysconf, idx)
        if fp:
            update_prompt_usage(fp, session_date)
            # Intelligence update — pass all sibling aliases for co-occurrence context
            update_prompt_intelligence(fp, session, cc, aliases)
            results.append((alias, f"updated → {fp.name}"))
        else:
            fname, _ = create_prompt_file(alias, sysconf, state)
            results.append((alias, f"auto-created → {fname}" if fname
                            else "skipped (error)"))

    # Track co-occurrence across all aliases in this session
    if len(aliases) >= 2:
        intel = cc.get("intelligence", {})
        if intel.get("track_cooccurrence", True):
            _update_cooccurrence(aliases)

    return results


# ── SESSION parser ─────────────────────────────────────────────────────────────

def parse_session_blocks(raw: str, sysconf: dict) -> list:
    """Split clipboard text on SESSION_OPEN. Returns list of session dicts."""
    if SESSION_OPEN not in raw:
        log_write("No SESSION blocks found.", "WARNING"); return []
    blocks   = raw.split(SESSION_OPEN)
    sessions = []
    for block in blocks[1:]:
        end = block.find(SESSION_CLOSE)
        if end >= 0: block = block[:end]
        parsed = _parse_session_fields(block, sysconf)
        parsed["_raw_block"] = SESSION_OPEN + block
        sessions.append(parsed)
    log_write(f"Parsed {len(sessions)} session block(s).")
    return sessions


def _parse_session_fields(block: str, sysconf: dict) -> dict:
    session = {
        "session_id":"", "year_month":"", "date":"", "time":"",
        "source":"", "model":"", "input_type":"", "pipeline_stage":"",
        "session_topic":"", "prompts_used":[], "tags":[],
        "message_length":"", "response_length":"", "prompt_count":"",
        "note":"", "user_input":"", "ai_response":"", "_raw_block":"",
    }

    # Split on ---USER INPUT--- / ---AI RESPONSE---
    user_input = ""; ai_response = ""; metadata_src = block
    if "---USER INPUT---" in block:
        after = block.split("---USER INPUT---",1)[1]
        if "---AI RESPONSE---" in after:
            ui_part, ai_part = after.split("---AI RESPONSE---",1)
            user_input   = ui_part.strip()
            ai_response  = ai_part.strip()
            metadata_src = ui_part
        else:
            user_input, ai_response = _extract_marker_response(after)
            metadata_src = after
    else:
        user_input, ai_response = _extract_marker_response(block)

    session["user_input"]  = user_input
    session["ai_response"] = ai_response

    # session_id from top of block
    for line in block.split("\n"):
        s = line.strip()
        if s.startswith("session_id:"):
            session["session_id"] = s.split(":",1)[1].strip().strip("[[]]").strip()
            break

    # Parse fields from metadata section
    pp             = sysconf.get("prompt_parsing",{})
    alias_prefixes = pp.get("alias_prefixes",["* ","- "])
    tags_parsing   = False
    prompts_parsing= False

    for line in metadata_src.split("\n"):
        stripped = line.strip()

        if stripped.startswith("tags:"):
            tags_parsing = True; prompts_parsing = False
            after = stripped[5:].strip()
            if after and after != "-": _collect_tags(after, session["tags"])
            continue
        if tags_parsing:
            if stripped.startswith("- "):
                _collect_tags(stripped[2:].strip(), session["tags"]); continue
            elif stripped and not stripped.startswith("-"):
                tags_parsing = False

        if stripped.lower().startswith("prompts:"):
            prompts_parsing = True; tags_parsing = False; continue
        if prompts_parsing:
            alias = _extract_alias(stripped, alias_prefixes)
            if alias is not None:
                if alias: session["prompts_used"].append(alias)
                continue
            elif stripped and not stripped.startswith("#"):
                prompts_parsing = False

        if ":" in stripped and not stripped.startswith("#") \
           and not stripped.startswith("---"):
            k, _, v = stripped.partition(":")
            k = k.strip().lower().replace("-","_")
            v = v.strip().strip("[[]]").strip()
            if k in session and k not in ("tags","prompts_used","_raw_block",
                                           "user_input","ai_response"):
                session[k] = v

    if session["user_input"] and not session["message_length"]:
        session["message_length"] = str(len(session["user_input"].split()))
    if session["ai_response"] and not session["response_length"]:
        session["response_length"] = str(len(session["ai_response"].split()))
    if not session["prompt_count"] and session["prompts_used"]:
        session["prompt_count"] = str(len(session["prompts_used"]))

    session["ai_response"] = _convert_topic_markers(session["ai_response"])
    return session


def _extract_alias(line: str, prefixes: list):
    for prefix in prefixes:
        stripped_p = prefix.rstrip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()
        elif line == stripped_p or line == stripped_p.strip():
            return ""
    return None


def _collect_tags(text: str, tag_list: list) -> None:
    for item in re.split(r'[,\s]+', text):
        item = item.strip("[[]]").strip()
        if item and item not in tag_list:
            tag_list.append(item)


def _extract_marker_response(text: str) -> tuple:
    user_part = text; ai_part = ""
    if MARKER_AI_START in text:
        parts = text.split(MARKER_AI_START,1)
        user_part = parts[0]
        after     = parts[1]
        if MARKER_AI_END in after:
            ai_part = after.split(MARKER_AI_END,1)[0].strip()
            lines   = ai_part.split("\n")
            if lines and re.match(r'^\d{4}-\d{2}-LOG-\d+',lines[0].strip()):
                ai_part = "\n".join(lines[1:]).strip()
        else:
            ai_part = after.strip()
    return user_part.strip(), ai_part.strip()


def _convert_topic_markers(text: str) -> str:
    return re.sub(r'<---Topic:\s*([^-]+)--->', r'[[\1]]', text)


# ── Topic derive ───────────────────────────────────────────────────────────────

def derive_session_topic(session: dict, state: dict) -> str:
    if session.get("session_topic"): return session["session_topic"]
    mode  = state.get("topic_derive_mode","all_combined")
    stop  = {"the","a","an","and","or","but","in","on","at","to","for","of",
             "with","as","by","from","it","is","are","was","were","this",
             "that","i","my","we","you","be","been","have","has"}
    text  = session.get("user_input","")
    first = ""
    for line in text.split("\n"):
        s = line.strip()
        if s: first = re.sub(r'[^\w\s-]','',s)[:40].strip(); break
    rep = ""
    if text:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        freq  = {}
        for w in words:
            if w not in stop: freq[w] = freq.get(w,0)+1
        if freq: rep = max(freq, key=freq.get)
    ps = "_".join(a.replace("-","_") for a in session.get("prompts_used",[])[:3])
    if mode=="first_line":        raw=first
    elif mode=="repeated_phrase": raw=rep
    elif mode=="prompt_names":    raw=ps
    else:
        parts=[p for p in [first,rep,ps] if p]; raw="_".join(parts[:3])
    slug = re.sub(r'[^\w]','_',raw.lower()); slug=re.sub(r'_+','_',slug).strip('_')
    session["session_topic"] = slug[:60]
    return session["session_topic"]


# ── Index / note updaters ──────────────────────────────────────────────────────

def update_session_index(session: dict, filename: str, state: dict) -> None:
    idx_path = INDEXES_DIR / "session_index.md"
    _touch_index(idx_path, "# Session Index\n\n")
    row = (f"{session.get('session_id','')} | {session.get('date','')} | "
           f"{session.get('session_topic','')} | {session.get('model','')} | "
           f"{session.get('pipeline_stage','')} | [[{filename}]]\n")
    with open(idx_path,"a") as f: f.write(row)


def update_tag_notes(session: dict, state: dict) -> None:
    tags = session.get("tags",[])
    if not tags: return
    sid  = session.get("session_id","")
    backlink = f"- [[{sid}]]"
    for tag in tags:
        if not tag: continue
        tag_file = TAGS_DIR / f"{tag}.md"
        if not tag_file.exists():
            tag_file.write_text(
                f"# {tag}\n\ncreated: {datetime.now().strftime('%Y-%m-%d')}"
                f"\n\n## Sessions\n\n{backlink}\n")
        else:
            _append_backlink(tag_file, backlink)


def update_topic_note(session: dict, state: dict) -> None:
    topic = session.get("session_topic","").strip()
    if not topic: return
    sid      = session.get("session_id","")
    backlink = f"- [[{sid}]]"
    tf       = TOPICS_DIR / f"{topic}.md"
    if not tf.exists():
        tf.write_text(
            f"# {topic}\n\ncreated: {datetime.now().strftime('%Y-%m-%d')}"
            f"\n\n---\n\n## Sessions\n\n{backlink}\n")
    else:
        _append_backlink(tf, backlink)


def _append_backlink(filepath: Path, backlink: str) -> None:
    content = filepath.read_text()
    if backlink in content: return
    if "## Sessions" in content:
        content = content.rstrip() + "\n" + backlink + "\n"
    else:
        content = content.rstrip() + "\n\n## Sessions\n\n" + backlink + "\n"
    filepath.write_text(content)


# ── File builders ──────────────────────────────────────────────────────────────

def build_session_filename(session: dict) -> str:
    sid = session.get("session_id","").strip()
    if sid:
        if not sid.startswith("session_"): sid = "session_" + sid
        return f"{sid}.md"
    d = session.get("date", datetime.now().strftime("%Y-%m-%d")).replace("/","-")
    t = session.get("time","0000").replace(":","")
    return f"session_{d}_{t}.md"


def build_yaml_frontmatter(session: dict, state: dict) -> str:
    yf = state.get("cleaner_conf",{}).get("yaml_fields", DEFAULT_CLEANER_CONF["yaml_fields"])
    def field(k, v):
        return f"{k}: {v}\n" if yf.get(k,True) and v else ""
    prompts_yaml = ""
    if yf.get("prompts_used",True) and session.get("prompts_used"):
        items = "\n".join(f"  - {a}" for a in session["prompts_used"])
        prompts_yaml = f"prompts_used:\n{items}\n"
    tags_yaml = ""
    if yf.get("tags",True) and session.get("tags"):
        items = "\n".join(f"  - [[{t}]]" for t in session["tags"])
        tags_yaml = f"tags:\n{items}\n"
    fm = "---\n"
    for k in ("session_id","year_month","date","time","source","model",
              "input_type","pipeline_stage","session_topic"):
        fm += field(k, session.get(k,""))
    fm += prompts_yaml
    fm += tags_yaml
    for k in ("message_length","response_length","prompt_count"):
        fm += field(k, session.get(k,""))
    if yf.get("note",False) and session.get("note"):
        fm += f"note: {session['note']}\n"
    fm += "---\n"
    return fm


def build_session_body(session: dict) -> str:
    body = ""
    if session.get("user_input"):
        body += f"## User\n\n{session['user_input']}\n\n---\n\n"
    if session.get("ai_response"):
        body += f"## AI\n\n{session['ai_response']}\n"
    return body


# ── Save session ───────────────────────────────────────────────────────────────

def save_session(session: dict, sysconf: dict, state: dict,
                 month: str, idx: dict = None) -> tuple:
    """
    Full save pipeline for one session:
      1. Build YAML frontmatter + body
      2. Write to 002_sessions/YYYY-MM/session_X.md (safe append on duplicate)
      3. Write raw backup to 003_raw/YYYY-MM/
      4. update_session_index
      5. update_tag_notes
      6. update_topic_note
      7. handle_prompts (usage + intelligence + auto-create)
    Returns (filename, prompt_results).
    """
    filename  = build_session_filename(session)
    month_dir = SESSIONS_DIR / month
    month_dir.mkdir(parents=True, exist_ok=True)
    filepath  = month_dir / filename

    yaml_str  = build_yaml_frontmatter(session, state)
    body_str  = build_session_body(session)
    content   = yaml_str + "\n" + body_str

    if filepath.exists():
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note = f"\n\n---\n\n<!-- Duplicate clean: {ts} -->\n\n"
        with open(filepath,"a") as f: f.write(note + content)
        log_write(f"Duplicate append: {filename}", "WARNING")
    else:
        filepath.write_text(content)
        log_write(f"Saved: {filepath}")

    # Raw backup
    cc = state.get("cleaner_conf",{})
    if cc.get("raw_backup",True):
        raw_dir = RAW_DIR / month
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"raw_{filename}").write_text(session.get("_raw_block",""))

    update_session_index(session, filename, state)
    update_tag_notes(session, state)
    update_topic_note(session, state)

    prompt_results = handle_prompts(session, sysconf, state, idx)
    return filename, prompt_results


# ── Main pipeline ──────────────────────────────────────────────────────────────

def process_clipboard(raw: str, sysconf: dict, state: dict) -> tuple:
    sessions = parse_session_blocks(raw, sysconf)
    if not sessions: return 0, [], []

    month     = datetime.now().strftime("%Y-%m")
    idx       = load_prompt_index()
    filenames = []
    all_prompts = []

    for session in sessions:
        derive_session_topic(session, state)
        fname, pres = save_session(session, sysconf, state, month, idx)
        filenames.append(fname)
        all_prompts.append((session.get("session_id",""), pres))

    last = sessions[-1]
    m    = re.search(r'LOG-(\d+)', last.get("session_id",""))
    if m:
        state["last_cleaned_log"]   = int(m.group(1))
        state["last_cleaned_month"] = month
        save_state(state)

    log_write(f"Processed {len(sessions)} session(s).")
    return len(sessions), filenames, all_prompts


# ── Terminal menus ─────────────────────────────────────────────────────────────

def menu_preview(sysconf):
    raw = read_clipboard()
    if not raw: print_err("Clipboard empty."); pause(); return
    sessions = parse_session_blocks(raw, sysconf)
    if not sessions: print_err("No SESSION blocks found."); pause(); return
    print_header("Preview", f"{len(sessions)} session(s) found")
    for i, s in enumerate(sessions, 1):
        print()
        print(f"  {c(C_NUM,str(i))}. {c(C_SELECT,s.get('session_id','(no id)'))}")
        print(f"     date:    {s.get('date','')}")
        print(f"     topic:   {s.get('session_topic','') or '(blank — will be derived)'}")
        print(f"     prompts: {', '.join(s.get('prompts_used',[])) or '(none)'}")
        print(f"     tags:    {', '.join(s.get('tags',[])) or '(none)'}")
        print(f"     words:   user {len(s.get('user_input','').split())}"
              f"  ai {len(s.get('ai_response','').split())}")
    pause()


def menu_clean_save(sysconf, state):
    raw = read_clipboard()
    if not raw: print_err("Clipboard empty."); pause(); return state
    n = raw.count(SESSION_OPEN)
    print_header("Clean and Save", f"Found {n} SESSION block(s)")
    if n == 0: print_err("No SESSION blocks found."); pause(); return state
    if not confirm("Process and save all sessions?"): print_info("Cancelled."); pause(); return state
    count, filenames, all_prompts = process_clipboard(raw, sysconf, state)
    print_ok(f"Saved {count} session(s).")
    for fname in filenames:
        print(f"  {c(C_OK,'→')} {fname}")
    if any(res for _, res in all_prompts):
        print(f"\n  {hint('Prompt operations:')}")
        for sid, results in all_prompts:
            for alias, result in results:
                print(f"  {hint(sid)}  {c(C_SELECT,alias)}  {hint(result)}")
    pause()
    return state


def menu_keywords(state):
    while True:
        kw = state["topics"]["keywords"]
        print_header("Topic Keywords")
        for i, w in enumerate(kw, 1): print_menu_item(i, w)
        if not kw: print_info("No keywords set.")
        print()
        print_menu_item(1 if not kw else len(kw)+1, "Add keyword")
        print_menu_item(2 if not kw else len(kw)+2, "Remove keyword")
        modes = ["first_line","repeated_phrase","prompt_names","all_combined"]
        print_menu_item(3 if not kw else len(kw)+3, "Set derive mode",
                        hint_text=f"current: {state.get('topic_derive_mode','all_combined')}")
        print_nav()
        ch = get_choice()
        if ch in ("q","0"): return state
        n = len(kw)
        if ch == str(n+1) or (not kw and ch=="1"):
            w = prompt_input("Keyword", example="Linux")
            if w and w not in kw: kw.append(w); save_state(state); print_ok(f"Added: {w}")
            pause()
        elif ch == str(n+2) or (not kw and ch=="2"):
            if kw:
                raw = get_choice("Remove number")
                if raw.isdigit() and 1<=int(raw)<=len(kw):
                    removed = kw.pop(int(raw)-1); save_state(state)
                    print_ok(f"Removed: {removed}")
            pause()
        elif ch == str(n+3) or (not kw and ch=="3"):
            for i,m in enumerate(modes,1): print_menu_item(i,m)
            raw = get_choice("Select")
            if raw.isdigit() and 1<=int(raw)<=len(modes):
                state["topic_derive_mode"] = modes[int(raw)-1]
                save_state(state); print_ok(f"derive mode → {state['topic_derive_mode']}")
            pause()
    return state


def menu_prompt_usage(sysconf):
    print_header("Prompt Usage Report", "Reads usage_count from prompt frontmatter")
    entries = []
    if PROMPT_DIR.exists():
        for f in sorted(PROMPT_DIR.rglob("*.md")):
            if f.name in ("prompt_index.md","prompt_index.json","README.md"): continue
            alias = re.sub(r"^\d+_","",f.stem)
            count = 0; last = ""
            try:
                meta, _ = _parse_fm(f.read_text())
                count = int(meta.get("usage_count",0) or 0)
                last  = meta.get("last_used","") or ""
            except Exception: pass
            entries.append((alias, count, last))
    if not entries: print_info("No prompts found."); pause(); return
    entries.sort(key=lambda x: x[1], reverse=True)
    max_c = max(e[1] for e in entries) or 1
    bar_w = 20
    print()
    for alias, count, last in entries:
        bar = c(C_OK,"█" * int(bar_w * count / max_c))
        pad = " " * (bar_w - int(bar_w * count / max_c))
        print(f"  {c(C_SELECT,alias):<28}  {bar}{pad}  "
              f"{c(C_NUM,str(count)):>4}  {hint(last or 'never')}")
    pause()


def menu_cooccurrence():
    print_header("Co-occurrence", "Prompt pairs used together in sessions")
    cooccur = _load_cooccurrence()
    if not cooccur: print_info("No co-occurrence data yet."); pause(); return
    pairs = sorted(cooccur.items(), key=lambda x: x[1], reverse=True)
    print()
    for key, count in pairs[:20]:
        a, b = key.split("|")
        print(f"  {c(C_SELECT,a):<20}  {c(C_SELECT,b):<20}  "
              f"{c(C_NUM,str(count))} times")
    pause()


def menu_yaml_settings(state):
    cc  = state.setdefault("cleaner_conf", dict(DEFAULT_CLEANER_CONF))
    while True:
        yf     = cc.setdefault("yaml_fields", dict(DEFAULT_CLEANER_CONF["yaml_fields"]))
        fields = list(DEFAULT_CLEANER_CONF["yaml_fields"].keys())
        print_header("YAML Frontmatter Settings")
        for i, k in enumerate(fields, 1):
            status = c(C_OK,"ON ") if yf.get(k,True) else c(C_ERR,"OFF")
            print(f"  [{status}]  {c(C_NUM,str(i))}  {k}")
        print_nav()
        ch = get_choice("Toggle number")
        if ch in ("q","0"): save_state(state); return state
        if ch.isdigit() and 1<=int(ch)<=len(fields):
            k = fields[int(ch)-1]; yf[k] = not yf.get(k,True)
            save_state(state); print_ok(f"{k} → {'ON' if yf[k] else 'OFF'}")


def menu_intelligence_settings(state):
    """Toggle intelligence layer options."""
    cc    = state.setdefault("cleaner_conf", dict(DEFAULT_CLEANER_CONF))
    intel = cc.setdefault("intelligence", dict(DEFAULT_CLEANER_CONF["intelligence"]))
    while True:
        print_header("Intelligence Settings", "Prompt metadata auto-update rules")
        toggle_fields = ["suggest_tags","track_cooccurrence","update_related"]
        for i, k in enumerate(toggle_fields, 1):
            status = c(C_OK,"ON ") if intel.get(k,True) else c(C_ERR,"OFF")
            print(f"  [{status}]  {c(C_NUM,str(i))}  {k}")
        print(f"\n  {hint('cooccur_threshold:')} {c(C_SELECT,str(intel.get('cooccur_threshold',3)))}")
        print_menu_item(4, "Set cooccur_threshold",
                        hint_text="min pair frequency before adding to related:")
        print_nav()
        ch = get_choice("Toggle number")
        if ch in ("q","0"): save_state(state); return state
        if ch.isdigit() and 1<=int(ch)<=3:
            k = toggle_fields[int(ch)-1]; intel[k] = not intel.get(k,True)
            save_state(state); print_ok(f"{k} → {'ON' if intel[k] else 'OFF'}")
        elif ch == "4":
            v = prompt_input("Threshold", default=str(intel.get("cooccur_threshold",3)),
                             example="3")
            if v.isdigit():
                intel["cooccur_threshold"] = int(v)
                save_state(state); print_ok(f"threshold → {v}")


def terminal_menu(sysconf, state):
    while True:
        log_n  = state.get("last_cleaned_log",0)
        month  = state.get("last_cleaned_month","") or "—"
        p_cnt  = max(0, sum(1 for f in PROMPT_DIR.rglob("*.md")
                           if f.name not in ("prompt_index.md","prompt_index.json",
                                             "README.md"))
                    ) if PROMPT_DIR.exists() else 0

        print_header(f"cleaner  v{VERSION}  ({SPEC})",
                     "SESSION parser · prompt intelligence · vault archiver")
        print(f"  {hint('Last cleaned:')} {c(C_SELECT,f'LOG-{log_n:04d}')}  {hint(month)}")
        print(f"  {hint('Prompt library:')} {c(C_SELECT,str(p_cnt))} files")
        print()
        print_menu_item(1,"Preview",          "parse clipboard — nothing saved")
        print_menu_item(2,"Clean and save",   "parse + save + prompt intelligence")
        print()
        print_menu_item(3,"Topic keywords",   "manage auto-link keywords + derive mode")
        print_menu_item(4,"Prompt usage",     "usage_count bar chart")
        print_menu_item(5,"Co-occurrence",    "prompt pairs used together")
        print_menu_item(6,"Intelligence",     "tag suggestions, related field, thresholds")
        print()
        print_menu_item(7,"YAML settings",    "toggle frontmatter fields in session files")
        print_menu_item(8,"Bootstrap dirs",   "create missing vault folders")
        print()
        print(f"  {c(C_KEY,'q')} exit   {c(C_KEY,'??')} help   "
              f"{c(C_KEY,'0')} exit")
        print()

        ch = get_choice()
        if ch in ("0","q"): print(c(C_HINT,"\n  Goodbye.\n")); break
        if ch == "??":
            print_header("HELP")
            print("""
  CLEANER v4  (spec v0.5.0)
  ────────────────────────────────────────────
  Reads clipboard SESSION blocks, archives to vault, updates prompt metadata.

  INTELLIGENCE LAYER:
    After cleaning, for each prompt used in a session:
    - usage_count incremented, last_used updated (never modifies body)
    - tags suggested from session_topic words (only appended, never removed)
    - co-occurrence tracked: prompts used together → related: field
    All intelligence updates use safe write (temp → validate → replace).

  SAFE WRITE:
    Frontmatter is updated in isolation. Instruction body preserved exactly.
    If frontmatter cannot be parsed → file is skipped, error logged.
    Temp file used for every write → atomic replace.

  CO-OCCURRENCE:
    Stored in vault/000_indexes/cooccurrence.json
    When pair count >= threshold → alias added to related: field
    Set threshold in [6] Intelligence settings
""")
            pause(); continue
        if ch == "1": menu_preview(sysconf)
        elif ch == "2": state = menu_clean_save(sysconf, state)
        elif ch == "3": state = menu_keywords(state)
        elif ch == "4": menu_prompt_usage(sysconf)
        elif ch == "5": menu_cooccurrence()
        elif ch == "6": state = menu_intelligence_settings(state)
        elif ch == "7": state = menu_yaml_settings(state)
        elif ch == "8":
            bootstrap_directories()
            print_ok("Bootstrap complete."); pause()


# ── Hotkey ─────────────────────────────────────────────────────────────────────

def run_hotkey(sysconf, state):
    raw = read_clipboard()
    if not raw:
        log_write("Hotkey: empty clipboard.", "WARNING")
        notify("cleaner","Clipboard empty.", state); return
    if SESSION_OPEN not in raw:
        log_write("Hotkey: no SESSION blocks.", "WARNING")
        notify("cleaner","No SESSION blocks found.", state); return
    count, filenames, _ = process_clipboard(raw, sysconf, state)
    log_write(f"Hotkey: cleaned {count} session(s).")
    notify("cleaner", f"Cleaned {count}: {', '.join(filenames[:3])}", state)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hotkey",  action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    _startup_checks("C")
    _check_snapshot(source="C", interactive=not args.hotkey)
    sysconf = load_system_config()
    bootstrap_directories(sysconf)
    state   = load_state()
    if not args.hotkey and _WARN_AVAILABLE:
        _warn_display(
            SCRIPT_DIR.parent, sysconf,
            conf_dir=CONF_DIR,
            modules_dir=SCRIPT_DIR.parent / "modules",
            max_log_lines=400,
            source="C",
        )

    if args.dry_run:
        raw = read_clipboard()
        if not raw: print_err("Clipboard empty."); return
        sessions = parse_session_blocks(raw, sysconf)
        print_header("DRY RUN","Nothing saved")
        for i, s in enumerate(sessions, 1):
            print(f"\n  {c(C_NUM,str(i))} {s.get('session_id','(no id)')}")
            print(f"     prompts: {', '.join(s.get('prompts_used',[])) or '(none)'}")
            print(f"     tags:    {', '.join(s.get('tags',[])) or '(none)'}")
        return

    if args.hotkey:
        run_hotkey(sysconf, state); return

    terminal_menu(sysconf, state)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(c(C_HINT,"\n\n  Exited cleanly.\n"))
        log_write("Exited via KeyboardInterrupt.")
        sys.exit(0)
