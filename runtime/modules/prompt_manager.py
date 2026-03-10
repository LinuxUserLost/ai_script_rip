#!/usr/bin/env python3
"""
prompt_manager.py | Version 1.0.0 | Spec v0.5.0
Prompt indexing, validation, versioning, duplicate handling, health reports.
Zero dependencies — pure Python 3.x.

### Run from scripts/ directory or via terminal_promptmgr.sh
### Reads/writes vault/004_prompts/ and vault/bundles/
### Generates: prompt_index.json, prompt_stats.json, prompt_health_report.json
###
### PROMPT FILE FORMAT (v0.5.0):
### ---
### id: 20260307143022_a3f2b1
### version: 1.0
### name: brainstorm
### description: ...
### category: tasks
### type: task
### created: 2026-03-07
### updated: 2026-03-07
### usage_count: 0
### last_used:
### status: draft
### aliases:
###   - brainstorm
###   - bs
### tags:
###   - creative
### related:
### ---
### [prompt instructions]
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timedelta
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

RESET    = "\033[0m";  BOLD  = "\033[1m";  DIM  = "\033[2m"
C_HEADER = "\033[96m"; C_OK  = "\033[92m"; C_ERR = "\033[91m"
C_WARN   = "\033[93m"; C_NUM = "\033[33m"; C_KEY = "\033[94m"
C_SELECT = "\033[96m"; C_DIM = "\033[2m";  C_HINT = "\033[2m"

def c(col, text): return f"{col}{text}{RESET}"
def hint(t):      return f"{C_HINT}{t}{RESET}"
def divider(w=52):return c(DIM, "─" * w)
def print_ok(m):  print(c(C_OK,   f"\n  ✓  {m}"))
def print_err(m): print(c(C_ERR,  f"\n  ✗  {m}"))
def print_info(m):print(c(C_HINT, f"  {m}"))
def print_header(title, sub=""):
    print(); print(divider())
    print(c(BOLD+C_HEADER, f"  {title}"))
    if sub: print(c(C_HINT, f"  {sub}"))
    print(divider())
def print_menu_item(n, label, hint_text=""):
    print(f"  {c(C_NUM,f'[{n}]')} {label}"
          + (f"  {hint(hint_text)}" if hint_text else ""))
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

VERSION    = "1.0.0"
SPEC       = "v0.5.0"
SCRIPT_DIR = Path(__file__).resolve().parent
CONF_DIR   = SCRIPT_DIR.parent / "configs"
LOG_DIR    = SCRIPT_DIR / "logs"
DEBUG_LOG  = LOG_DIR / "debug.log"

# ── Runtime path resolver ──────────────────────────────────────────────────────
# Reads vault_root and vault_folders from system_config.json.
# Falls back to legacy layout if config is missing or unreadable.
# All downstream code uses these names unchanged.

def _resolve_runtime_paths():
    """
    Resolve VAULT_ROOT, PROMPT_DIR, BUNDLE_DIR from system_config.
    Relative vault_root resolved against SCRIPT_DIR.
    Returns (vault_root, prompt_dir, bundle_dir).
    """
    conf_file = CONF_DIR / "system_config.json"
    try:
        if conf_file.exists():
            with open(conf_file, encoding="utf-8") as f:
                conf = json.load(f)
            vault_rel = conf.get("vault_root", "../ai-vault")
            folders   = conf.get("vault_folders", {})
            vault     = (SCRIPT_DIR.parent / vault_rel).resolve()
            prompt    = vault / folders.get("prompts", "004_prompts")
            bundle    = vault / folders.get("bundles", "bundles")
            return vault, prompt, bundle
    except Exception:
        pass
    # Fallback: legacy layout beside SCRIPT_DIR
    vault  = (SCRIPT_DIR.parent / "ai-vault").resolve()
    return vault, vault / "004_prompts", vault / "bundles"

VAULT_ROOT, PROMPT_DIR, BUNDLE_DIR = _resolve_runtime_paths()

PROMPT_INDEX_JSON  = PROMPT_DIR / "prompt_index.json"
PROMPT_STATS_JSON  = PROMPT_DIR / "prompt_stats.json"
HEALTH_REPORT_JSON = PROMPT_DIR / "prompt_health_report.json"

TYPE_ORDER    = ["task", "workflow", "style", "format", "constraint"]
CATEGORY_DIRS = {"tasks", "styles", "formats", "workflows", "constraints"}
STATUS_VALUES = {"draft", "active", "archived"}

### Fields written in this order to frontmatter
FM_SIMPLE = ["id","version","name","description","category","type",
             "created","updated","usage_count","last_used","status"]
FM_LISTS  = ["aliases","tags","related"]
FM_ALL    = FM_SIMPLE + FM_LISTS


# ── Logging ────────────────────────────────────────────────────────────────────

def log_write(msg, level="INFO"):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"{ts} | {level} | PM | {msg}\n")


# ── Frontmatter parser / writer ────────────────────────────────────────────────

def _parse_fm(content: str) -> tuple:
    """
    Parse YAML-style frontmatter. Returns (meta_dict, body_str).
    Never raises — returns ({}, content) on any failure.
    Handles both list values and inline comma values.
    """
    try:
        if not content.startswith("---"):
            return {}, content
        rest = content[3:]
        if rest.startswith("\n"):
            rest = rest[1:]
        nl_dashes = rest.find("\n---")
        if nl_dashes == -1:
            return {}, content
        fm_text = rest[:nl_dashes]
        body    = rest[nl_dashes + 4:]
        if body.startswith("\n"):
            body = body[1:]

        meta = {}
        current_key  = None
        current_list = None

        for line in fm_text.split("\n"):
            if not line.strip():
                continue
            ls = line.lstrip()
            # List item — belongs to most recent list key
            if ls.startswith("- ") and current_list is not None:
                val = ls[2:].strip().strip("\"'")
                current_list.append(val)
                continue
            # Key: value  (no leading indent)
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip().strip("\"'")
                if v:
                    meta[k] = v
                    current_key  = k
                    current_list = None
                else:
                    lst = []
                    meta[k]      = lst
                    current_key  = k
                    current_list = lst

        return meta, body
    except Exception as e:
        log_write(f"_parse_fm error: {e}", "WARNING")
        return {}, content


def _format_fm(meta: dict) -> str:
    """Format metadata dict to YAML-style frontmatter string."""
    lines = []
    for k in FM_SIMPLE:
        if k in meta:
            v = meta[k]
            lines.append(f"{k}:" if (v is None or v == "") else f"{k}: {v}")
    for k in FM_LISTS:
        if k in meta:
            v = meta[k]
            if isinstance(v, list):
                items = v
            elif isinstance(v, str) and v:
                items = [i.strip() for i in v.split(",") if i.strip()]
            else:
                items = []
            if items:
                lines.append(f"{k}:")
                for item in items:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{k}:")
    return "\n".join(lines) + "\n"


def _write_prompt_safe(filepath: Path, meta: dict, body: str,
                        old_body: str = None) -> bool:
    """
    Atomically write a prompt file:
      1. Compute body hash — bump version if body changed
      2. Write to .tmp file
      3. Validate round-trip parse
      4. os.replace (atomic on POSIX)
    Returns True on success, raises on failure.
    """
    if old_body is not None:
        h_new = hashlib.md5(body.strip().encode()).hexdigest()
        h_old = hashlib.md5(old_body.strip().encode()).hexdigest()
        if h_new != h_old:
            meta["version"] = _bump_version(meta.get("version", "1.0"))
            meta["updated"] = datetime.now().strftime("%Y-%m-%d")

    fm      = _format_fm(meta)
    content = f"---\n{fm}---\n{body}"
    tmp     = filepath.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        test_meta, _ = _parse_fm(tmp.read_text())
        if not test_meta.get("id"):
            raise ValueError("Round-trip validation: id missing")
        os.replace(str(tmp), str(filepath))
        log_write(f"Wrote: {filepath.name}")
        return True
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _bump_version(v: str) -> str:
    """'1.0' → '1.1', '1.9' → '1.10'"""
    try:
        maj, mn = v.split(".")
        return f"{maj}.{int(mn)+1}"
    except Exception:
        return "1.1"


def _generate_id() -> str:
    ts  = datetime.now().strftime("%Y%m%d%H%M%S")
    uid = uuid.uuid4().hex[:6]
    return f"{ts}_{uid}"


# ── Prompt scanning ────────────────────────────────────────────────────────────

SKIP_FILES = {"prompt_index.md", "prompt_index.json",
              "prompt_stats.json", "prompt_health_report.json",
              "README.md"}

def scan_prompt_files(base_dir: Path = None) -> list:
    """
    Recursively scan base_dir for prompt .md files.
    Returns list of (filepath, meta, body).
    Skips index/stats files. Skips if parse fails.
    """
    base   = base_dir or PROMPT_DIR
    result = []
    if not base.exists():
        return result
    for f in sorted(base.rglob("*.md")):
        if f.name in SKIP_FILES:
            continue
        if f.name.endswith(".tmp"):
            continue
        try:
            content    = f.read_text(encoding="utf-8")
            meta, body = _parse_fm(content)
            result.append((f, meta, body))
        except Exception as e:
            log_write(f"scan skip {f.name}: {e}", "WARNING")
    return result


def scan_bundle_files() -> list:
    """Scan vault/bundles/ for bundle .md files. Returns (filepath, meta, body)."""
    if not BUNDLE_DIR.exists():
        return []
    result = []
    for f in sorted(BUNDLE_DIR.glob("*.md")):
        if f.name in SKIP_FILES:
            continue
        try:
            content    = f.read_text(encoding="utf-8")
            meta, body = _parse_fm(content)
            result.append((f, meta, body))
        except Exception:
            pass
    return result


# ── Index builder ──────────────────────────────────────────────────────────────

def build_prompt_index(prompts: list = None) -> dict:
    """
    Builds prompt_index.json with alias → filepath mapping.
    Index structure:
      aliases: {normalized_alias: relative_path}
      by_id:   {id: relative_path}
      by_name: {name: relative_path}
      meta:    {relative_path: {id, name, type, status, aliases, tags}}
    Writes to PROMPT_DIR/prompt_index.json.
    Returns the index dict.
    """
    if prompts is None:
        prompts = scan_prompt_files()

    index = {"aliases": {}, "by_id": {}, "by_name": {}, "meta": {},
             "generated": datetime.now().isoformat(), "count": 0}

    for filepath, meta, body in prompts:
        if not meta:
            continue
        rel = str(filepath.relative_to(VAULT_ROOT))

        # Collect all aliases for this prompt
        file_aliases = []
        # Name as alias
        name = meta.get("name", "").strip()
        if name:
            file_aliases.append(name.lower())
        # Explicit aliases list
        aliases_raw = meta.get("aliases", [])
        if isinstance(aliases_raw, list):
            for a in aliases_raw:
                norm = a.strip().lower()
                if norm and norm not in file_aliases:
                    file_aliases.append(norm)
        elif isinstance(aliases_raw, str) and aliases_raw:
            for a in aliases_raw.split(","):
                norm = a.strip().lower()
                if norm and norm not in file_aliases:
                    file_aliases.append(norm)
        # Old single-alias format
        old_alias = meta.get("alias", "").strip().lower()
        if old_alias and old_alias not in file_aliases:
            file_aliases.append(old_alias)
        # Filename stem without number prefix (old format)
        stem = re.sub(r"^\d+_", "", filepath.stem).lower()
        if stem and stem not in file_aliases:
            file_aliases.append(stem)

        # Obsidian [[wikilink]] — resolve [[name]] same as name
        # (handled implicitly since we index by name)

        for alias in file_aliases:
            if alias not in index["aliases"]:
                index["aliases"][alias] = rel

        pid = meta.get("id", "")
        if pid:
            index["by_id"][pid] = rel

        if name:
            index["by_name"][name.lower()] = rel

        index["meta"][rel] = {
            "id":      pid,
            "name":    name,
            "type":    meta.get("type", ""),
            "status":  meta.get("status", ""),
            "aliases": file_aliases,
            "tags":    meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
            "category":meta.get("category",""),
        }
        index["count"] += 1

    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_INDEX_JSON.write_text(json.dumps(index, indent=2))
    log_write(f"Index built: {index['count']} prompts, "
              f"{len(index['aliases'])} aliases")
    return index


# ── Stats builder ──────────────────────────────────────────────────────────────

def build_prompt_stats(prompts: list = None) -> dict:
    """
    Generates prompt_stats.json:
      total, by_type, by_status, by_category,
      top_used, never_used, draft_count, archived_count
    """
    if prompts is None:
        prompts = scan_prompt_files()

    stats = {
        "generated":  datetime.now().isoformat(),
        "total":      0,
        "by_type":    {},
        "by_status":  {},
        "by_category":{},
        "top_used":   [],
        "never_used": [],
        "draft_count":0,
        "archived_count": 0,
    }
    usage_list = []

    for filepath, meta, body in prompts:
        if not meta:
            continue
        stats["total"] += 1

        t = meta.get("type", "untyped")
        stats["by_type"][t] = stats["by_type"].get(t, 0) + 1

        s = meta.get("status", "unknown")
        stats["by_status"][s] = stats["by_status"].get(s, 0) + 1
        if s == "draft":    stats["draft_count"]    += 1
        if s == "archived": stats["archived_count"] += 1

        cat = meta.get("category", "uncategorized")
        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1

        name  = meta.get("name", filepath.stem)
        count = int(meta.get("usage_count", 0) or 0)
        usage_list.append((name, count))
        if count == 0:
            stats["never_used"].append(name)

    usage_list.sort(key=lambda x: x[1], reverse=True)
    stats["top_used"] = [{"name": n, "count": c} for n, c in usage_list[:10]]

    PROMPT_STATS_JSON.write_text(json.dumps(stats, indent=2))
    log_write(f"Stats built: {stats['total']} prompts")
    return stats


# ── Health report ──────────────────────────────────────────────────────────────

def build_health_report(prompts: list = None) -> dict:
    """
    Generates prompt_health_report.json.
    Categories: unused, most_used, duplicates, missing_tags,
                stale_drafts, no_aliases, high_stack_freq (placeholder)
    """
    if prompts is None:
        prompts = scan_prompt_files()

    now     = datetime.now()
    report  = {
        "generated":     now.isoformat(),
        "summary":       {},
        "unused":        [],
        "most_used":     [],
        "duplicates":    [],
        "missing_tags":  [],
        "stale_drafts":  [],
        "no_aliases":    [],
        "missing_type":  [],
        "archived":      [],
    }

    # Detect duplicates by name
    names_seen = {}
    for filepath, meta, body in prompts:
        name = meta.get("name", "").strip().lower()
        if name:
            names_seen.setdefault(name, []).append(str(filepath.name))
    for name, files in names_seen.items():
        if len(files) > 1:
            report["duplicates"].append({"name": name, "files": files})

    usage_list = []
    for filepath, meta, body in prompts:
        if not meta:
            continue
        name    = meta.get("name", filepath.stem)
        count   = int(meta.get("usage_count", 0) or 0)
        status  = meta.get("status", "")
        created = meta.get("created", "")
        tags    = meta.get("tags", [])
        aliases = meta.get("aliases", [])
        ptype   = meta.get("type", "")

        usage_list.append((name, count))
        if count == 0:
            report["unused"].append(name)
        if not tags or (isinstance(tags, list) and len(tags) == 0):
            report["missing_tags"].append(name)
        if not aliases or (isinstance(aliases, list) and len(aliases) == 0):
            report["no_aliases"].append(name)
        if not ptype:
            report["missing_type"].append(name)
        if status == "archived":
            report["archived"].append(name)
        # Stale drafts: draft status + created > 30 days ago
        if status == "draft" and created:
            try:
                created_dt = datetime.strptime(created, "%Y-%m-%d")
                if (now - created_dt).days > 30:
                    report["stale_drafts"].append({
                        "name": name, "created": created,
                        "days": (now - created_dt).days
                    })
            except ValueError:
                pass

    usage_list.sort(key=lambda x: x[1], reverse=True)
    report["most_used"] = [{"name": n, "count": c}
                           for n, c in usage_list[:10] if c > 0]

    report["summary"] = {
        "total":          len(prompts),
        "unused":         len(report["unused"]),
        "duplicates":     len(report["duplicates"]),
        "missing_tags":   len(report["missing_tags"]),
        "stale_drafts":   len(report["stale_drafts"]),
        "no_aliases":     len(report["no_aliases"]),
        "missing_type":   len(report["missing_type"]),
        "archived":       len(report["archived"]),
    }

    HEALTH_REPORT_JSON.write_text(json.dumps(report, indent=2))
    log_write(f"Health report built: {report['summary']}")
    return report


# ── Validation ─────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {"id", "name", "created"}

def validate_prompt(filepath: Path, meta: dict) -> list:
    """Returns list of issue strings. Empty = valid."""
    issues = []
    for field in REQUIRED_FIELDS:
        if not meta.get(field):
            issues.append(f"missing required field: {field}")
    if meta.get("type") and meta["type"] not in TYPE_ORDER:
        issues.append(f"invalid type: {meta['type']} (allowed: {TYPE_ORDER})")
    if meta.get("status") and meta["status"] not in STATUS_VALUES:
        issues.append(f"invalid status: {meta['status']}")
    if not meta.get("aliases"):
        issues.append("no aliases defined")
    return issues


# ── Normalization (old → new format) ──────────────────────────────────────────

def normalize_prompt(filepath: Path, meta: dict, body: str,
                     dry_run: bool = False) -> dict:
    """
    Migrates old v0.4.5 prompt format to v0.5.0.
    - Adds id if missing (new generated ID)
    - Adds version: 1.0 if missing
    - Converts alias: string → aliases: [string]
    - Converts tags: "tag1, tag2" → list
    - Adds status: active (old prompts assumed active)
    - Adds updated = created if missing
    Changes are written to file unless dry_run=True.
    Returns updated meta.
    """
    changed = False
    m = dict(meta)

    if not m.get("id"):
        m["id"] = _generate_id()
        changed = True

    if not m.get("version"):
        m["version"] = "1.0"
        changed = True

    if not m.get("updated"):
        m["updated"] = m.get("created", datetime.now().strftime("%Y-%m-%d"))
        changed = True

    if not m.get("status"):
        m["status"] = "active"   # existing prompts are active
        changed = True

    # Migrate single alias → list
    old_alias = m.pop("alias", None)
    if old_alias and not m.get("aliases"):
        m["aliases"] = [old_alias.strip().lower()]
        changed = True
    elif not m.get("aliases"):
        # Use name or filename stem
        name = m.get("name") or re.sub(r"^\d+_", "", filepath.stem)
        m["aliases"] = [name.strip().lower()]
        changed = True

    # Migrate tags: "tag1, tag2" → list
    tags = m.get("tags", [])
    if isinstance(tags, str) and tags:
        m["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        changed = True
    elif not isinstance(tags, list):
        m["tags"] = []

    # Ensure lists for all list fields
    for k in FM_LISTS:
        if k not in m:
            m[k] = []

    if changed and not dry_run:
        try:
            _write_prompt_safe(filepath, m, body)
            log_write(f"Normalized: {filepath.name}")
        except Exception as e:
            log_write(f"Normalize write failed {filepath.name}: {e}", "ERROR")

    return m


# ── Duplicate handling ─────────────────────────────────────────────────────────

def handle_duplicates(prompts: list = None) -> list:
    """
    Detects prompts with duplicate names or alias conflicts.
    Renames later files: name.md → name_2.md, name_3.md
    Auto-tags renamed files with 'duplicate'.
    Returns list of (original_name, new_name) renames performed.
    """
    if prompts is None:
        prompts = scan_prompt_files()

    # Map: normalized_name → first filepath seen
    seen_names   = {}
    seen_aliases = {}
    renames      = []

    for filepath, meta, body in prompts:
        if not meta:
            continue
        name = meta.get("name", "").strip().lower()
        if not name:
            continue

        if name in seen_names:
            # Duplicate — find a free name
            base   = filepath.stem
            parent = filepath.parent
            n      = 2
            while True:
                new_stem = f"{base}_{n}"
                new_path = parent / f"{new_stem}.md"
                if not new_path.exists():
                    break
                n += 1
            try:
                filepath.rename(new_path)
                # Update meta: add duplicate tag, update name
                new_meta = dict(meta)
                tags = new_meta.get("tags", [])
                if isinstance(tags, list) and "duplicate" not in tags:
                    tags.append("duplicate")
                    new_meta["tags"] = tags
                new_meta["name"]    = new_stem
                new_meta["updated"] = datetime.now().strftime("%Y-%m-%d")
                # Update aliases to include new name
                als = new_meta.get("aliases", [])
                if isinstance(als, list) and new_stem.lower() not in als:
                    als.append(new_stem.lower())
                new_meta["aliases"] = als
                _write_prompt_safe(new_path, new_meta, body)
                renames.append((str(filepath.name), str(new_path.name)))
                log_write(f"Duplicate renamed: {filepath.name} → {new_path.name}")
            except Exception as e:
                log_write(f"Rename failed {filepath.name}: {e}", "ERROR")
        else:
            seen_names[name] = filepath

        aliases = meta.get("aliases", [])
        if isinstance(aliases, list):
            for a in aliases:
                seen_aliases.setdefault(a.lower(), []).append(filepath)

    return renames


# ── Auto-categorization ────────────────────────────────────────────────────────

def auto_categorize(prompts: list = None, dry_run: bool = False) -> list:
    """
    Moves prompt files into subdirectories based on their first tag.
    Only moves if first tag matches a known CATEGORY_DIRS name.
    Updates prompt index after moves.
    Returns list of (old_path, new_path) moves performed.
    """
    if prompts is None:
        prompts = scan_prompt_files()

    moves = []
    for filepath, meta, body in prompts:
        if not meta:
            continue
        # Skip if already in a category subdirectory
        if filepath.parent != PROMPT_DIR:
            continue
        tags = meta.get("tags", [])
        if not isinstance(tags, list) or not tags:
            continue
        first_tag = tags[0].strip().lower()
        if first_tag not in CATEGORY_DIRS:
            continue
        cat_dir  = PROMPT_DIR / first_tag
        new_path = cat_dir / filepath.name
        if new_path == filepath:
            continue
        if not dry_run:
            cat_dir.mkdir(exist_ok=True)
            filepath.rename(new_path)
            # Update category field in metadata
            new_meta = dict(meta)
            new_meta["category"] = first_tag
            new_meta["updated"]  = datetime.now().strftime("%Y-%m-%d")
            try:
                _write_prompt_safe(new_path, new_meta, body)
            except Exception:
                pass
            log_write(f"Moved to {first_tag}/: {filepath.name}")
        moves.append((str(filepath), str(new_path)))

    if moves and not dry_run:
        build_prompt_index()   # Rebuild index after moves

    return moves


# ── Terminal menus ─────────────────────────────────────────────────────────────

def menu_validate(prompts):
    print_header("Validate Prompts", "Check all files for required fields")
    total = len(prompts)
    issues_found = 0
    for filepath, meta, body in prompts:
        issues = validate_prompt(filepath, meta)
        if issues:
            issues_found += 1
            print(f"\n  {c(C_WARN,'⚠')}  {c(C_SELECT, filepath.name)}")
            for iss in issues:
                print_info(f"   · {iss}")
    if not issues_found:
        print_ok(f"All {total} prompt files valid.")
    else:
        print()
        print_info(f"{issues_found}/{total} files have issues.")
        print_info("Run Normalize [2] to auto-fix most issues.")
    pause()


def menu_normalize(prompts):
    print_header("Normalize Prompts",
                 "Migrate old v0.4.5 format fields to v0.5.0")
    print_info(f"{len(prompts)} files to check.")
    print_info("Adds: id, version, aliases list, status, updated")
    print_info("Converts: tags string → list, alias → aliases list")
    print()
    if not confirm("Normalize all prompts now?"):
        print_info("Cancelled.")
        pause()
        return
    changed = 0
    for filepath, meta, body in prompts:
        new_meta = normalize_prompt(filepath, meta, body)
        if new_meta != meta:
            changed += 1
    print_ok(f"Done. {changed}/{len(prompts)} files updated.")
    pause()


def menu_build_index(prompts):
    print_header("Build Index", "Generates prompt_index.json")
    index = build_prompt_index(prompts)
    print_ok(f"Index built: {index['count']} prompts, "
             f"{len(index['aliases'])} aliases")
    print_info(f"Written to: {PROMPT_INDEX_JSON.name}")
    pause()


def menu_health(prompts):
    report = build_health_report(prompts)
    s      = report["summary"]
    print_header("Prompt Health Report",
                 f"Generated {report['generated'][:10]}")
    print()
    def row(label, val, warn=False):
        col = C_WARN if (warn and val > 0) else C_OK
        print(f"  {hint(label):<28} {c(col, str(val))}")

    row("Total prompts",     s["total"])
    row("Unused",            s["unused"],       warn=True)
    row("Missing tags",      s["missing_tags"], warn=True)
    row("Missing type",      s["missing_type"], warn=True)
    row("No aliases",        s["no_aliases"],   warn=True)
    row("Stale drafts (30d)",s["stale_drafts"], warn=True)
    row("Duplicates",        s["duplicates"],   warn=True)
    row("Archived",          s["archived"])

    if report["most_used"]:
        print()
        print(f"  {hint('Top used:')}")
        for e in report["most_used"][:5]:
            print(f"    {c(C_SELECT, e['name']):<30} {c(C_NUM, str(e['count']))}")

    if report["stale_drafts"]:
        print()
        print(f"  {hint('Stale drafts (>30 days):')}")
        for e in report["stale_drafts"]:
            print(f"    {c(C_WARN, e['name']):<30} {hint(str(e['days']) + ' days')}")
    pause()


def menu_categorize(prompts):
    print_header("Auto-Categorize",
                 "Move prompts to subdirs by first tag")
    moves = auto_categorize(prompts, dry_run=True)
    if not moves:
        print_info("No moves needed — all categorizable prompts already placed.")
        pause()
        return
    print_info(f"{len(moves)} file(s) would move:")
    for src, dst in moves:
        src_n = Path(src).name
        dst_n = Path(dst).relative_to(VAULT_ROOT)
        print(f"  {c(C_WARN,'→')}  {src_n}  {hint('→ ' + str(dst_n))}")
    print()
    if confirm("Perform moves now?"):
        auto_categorize(prompts)   # live run
        print_ok(f"Moved {len(moves)} file(s). Index rebuilt.")
    else:
        print_info("Cancelled.")
    pause()


def menu_duplicates(prompts):
    print_header("Handle Duplicates", "Detect and rename duplicate prompt names")
    report = build_health_report(prompts)
    dups   = report.get("duplicates", [])
    if not dups:
        print_ok("No duplicates found.")
        pause()
        return
    print_info(f"{len(dups)} duplicate name(s):")
    for d in dups:
        print(f"  {c(C_WARN, d['name'])}")
        for fn in d["files"]:
            print(f"    · {fn}")
    print()
    if confirm("Rename duplicates now? (later files get _2, _3 suffix)"):
        renames = handle_duplicates(prompts)
        for old, new in renames:
            print_info(f"{old} → {new}")
        print_ok(f"{len(renames)} file(s) renamed.")
    pause()


def terminal_menu():
    while True:
        prompts  = scan_prompt_files()
        bundles  = scan_bundle_files()
        p_count  = len(prompts)
        b_count  = len(bundles)
        idx_age  = ""
        if PROMPT_INDEX_JSON.exists():
            ts      = datetime.fromtimestamp(PROMPT_INDEX_JSON.stat().st_mtime)
            idx_age = ts.strftime("%Y-%m-%d %H:%M")

        print_header(f"prompt_manager  v{VERSION}  ({SPEC})",
                     "Prompt indexing, validation, versioning, health")
        print(f"  {hint('Prompts:')} {c(C_SELECT, str(p_count))}"
              f"  {hint('Bundles:')} {c(C_SELECT, str(b_count))}")
        if idx_age:
            print(f"  {hint('Index last built:')} {c(C_DIM, idx_age)}")
        print()
        print_menu_item(1, "Validate",        "check required fields")
        print_menu_item(2, "Normalize",       "migrate old format → v0.5.0")
        print_menu_item(3, "Build index",     "generate prompt_index.json")
        print_menu_item(4, "Health report",   "unused, stale drafts, duplicates")
        print_menu_item(5, "Auto-categorize", "move files by first tag")
        print_menu_item(6, "Handle duplicates","rename name_2, name_3")
        print_menu_item(7, "Build stats",     "generate prompt_stats.json")
        print()
        print(f"  {c(C_KEY,'q')} exit   {c(C_KEY,'??')} help")
        print()

        ch = get_choice()
        if ch in ("q", "0"):
            break
        elif ch == "1": menu_validate(prompts)
        elif ch == "2": menu_normalize(prompts)
        elif ch == "3": menu_build_index(prompts)
        elif ch == "4": menu_health(prompts)
        elif ch == "5": menu_categorize(prompts)
        elif ch == "6": menu_duplicates(prompts)
        elif ch == "7":
            build_prompt_stats(prompts)
            print_ok("prompt_stats.json written.")
            pause()
        elif ch == "??":
            print_header("HELP")
            print("""
  prompt_manager manages the prompt library without touching Obsidian content.
  Safe write: temp file → validate → atomic replace. Never corrupts prompts.

  TYPICAL RUN ORDER:
    [2] Normalize   — upgrade old prompts to v0.5.0 format
    [3] Build index — rebuild prompt_index.json (prompter uses this)
    [4] Health      — see what needs attention

  AUTO-CATEGORIZE:
    Move files by first tag: tasks/, styles/, formats/, workflows/, constraints/
    IDs remain constant after moves. Index is rebuilt automatically.

  NORMALIZE:
    Adds id, version, aliases list, status fields to old prompts.
    Never changes prompt instruction text.
""")
            pause()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Prompt library manager.")
    parser.add_argument("--build-index",  action="store_true")
    parser.add_argument("--health",       action="store_true")
    parser.add_argument("--normalize",    action="store_true")
    parser.add_argument("--stats",        action="store_true")
    args = parser.parse_args()

    _startup_checks("PM")
    _check_snapshot(source="PM", interactive=True)
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    if _WARN_AVAILABLE:
        _sysconf_pm = {}
        try:
            import json as _json
            _cf = CONF_DIR / "system_config.json"
            if _cf.exists():
                _sysconf_pm = _json.loads(_cf.read_text())
        except Exception:
            pass
        _warn_display(
            SCRIPT_DIR.parent, _sysconf_pm,
            conf_dir=CONF_DIR,
            modules_dir=SCRIPT_DIR.parent / "modules",
            max_log_lines=400,
            source="PM",
        )

    if args.build_index:
        index = build_prompt_index()
        print(f"Index built: {index['count']} prompts")
        return
    if args.health:
        report = build_health_report()
        print(json.dumps(report["summary"], indent=2))
        return
    if args.normalize:
        prompts = scan_prompt_files()
        for fp, meta, body in prompts:
            normalize_prompt(fp, meta, body)
        print(f"Normalized {len(prompts)} files.")
        return
    if args.stats:
        build_prompt_stats()
        print("Stats written.")
        return

    terminal_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(c(C_HINT, "\n\n  Exited.\n"))
        sys.exit(0)
