# Module Guide

**Level:** Intermediate  
**File:** `runtime_core/lib/module_loader.py`

---

## What are modules?

Modules are optional capability extensions in `runtime_core/modules/`.
Each module has its own subfolder. Modules can expose commands, help text,
and diagnostic checks, but none of them run automatically.

The runtime works fully without any modules. Modules are additive only.

---

## Available modules

| Module | Status | Purpose |
|---|---|---|
| `learning` | ready | Knowledge browsing, tutorial walker, guide search |
| `analyzer` | ready | Vault diagnostics, session stats, health reports |
| `chat` | ready | Clipboard helpers, marker stripping, format tools |
| `editor` | ready | Script viewer, config inspector, snapshot diff |
| `gui` | requires tkinter | Dashboard window (deferred) |
| `updater` | ready | Drop-in update pack handler (deferred) |

"Ready" means the stub is in place and is_available() returns True.
Full implementation of each module's commands comes in later phases.

---

## Checking module availability

From the terminal (inside a function — never at top level):

```python
try:
    from module_loader import list_available, describe
except ImportError:
    list_available = lambda: {}
    describe = lambda: "modules: unavailable"

print(describe())
# modules: learning=yes  analyzer=yes  chat=yes  editor=yes  gui=no  updater=yes
```

---

## Module API — three standard exports

Every module `__init__.py` must expose:

| Function | Returns | Purpose |
|---|---|---|
| `is_available()` | `bool` | Can this module be used right now? |
| `commands()` | `dict` | `{command_name: short_description}` |
| `help_text()` | `str` | Multi-line help for this module |
| `diagnostics()` | `list` | `[{key, value, status}]` status items |

All four must never raise. `is_available()` is called by `module_loader`
during every probe. The others are called on demand only.

---

## Reading module commands

```python
try:
    from module_loader import get_commands, all_commands
except ImportError:
    get_commands  = lambda name: {}
    all_commands  = lambda: {}

# Single module
cmds = get_commands("learning")
# {'browse': 'Browse knowledge...', 'search': '...', ...}

# All available modules
all_cmds = all_commands()
# {'learning': {...}, 'analyzer': {...}, ...}
```

---

## Reading module help

```python
try:
    from module_loader import get_help
except ImportError:
    get_help = lambda name: ""

print(get_help("analyzer"))
```

---

## Reading module diagnostics

```python
try:
    from module_loader import get_diagnostics, all_diagnostics
except ImportError:
    get_diagnostics = lambda name: []
    all_diagnostics = lambda: {}

for item in get_diagnostics("editor"):
    icon = {"ok": "✓", "warn": "⚠", "error": "✗"}.get(item["status"], "?")
    print(f"  {icon}  {item['key']}: {item['value']}")
```

---

## Diagnostic status values

| Status | Meaning |
|---|---|
| `ok` | Feature or path is present and working |
| `warn` | Feature or path is missing but not critical |
| `error` | Feature or path is missing and required for this module |

---

## Module-specific notes

### learning
Checks for vault folders `006_knowledge`, `007_guides`, `008_agents`,
`009_tutorials`. Reports `warn` if any are missing — they are created
by bootstrap, so run option `11` from the prompter if needed.

### analyzer
Checks for `session_index.md` and `prompt_index.json`. These are created
by the cleaner and manager on first use. Missing at startup is normal.

### chat
Checks for Wayland clipboard tools: `wl-copy`, `wl-paste`, `xclip`, `xsel`.
Only `wl-copy` is required for the prompter to function. The others are
optional fallbacks.

### editor
Checks that `scripts/` and `exec/` folders have files, `$EDITOR` is set,
and a snapshot exists. Set `$EDITOR` in your shell profile:
```bash
export EDITOR=nano
```

### gui
Checks for `tkinter` and a display (DISPLAY or WAYLAND_DISPLAY).
See the [GUI Guide](../developer/gui_guide.md) for full details.

### updater
Checks for an `update_pack/` folder beside `runtime_core/` and a snapshot.
Drop an update pack in place, then call `updater.check()` to inspect it.

---

## Adding a new module

1. Create `runtime_core/modules/mymodule/`
2. Create `__init__.py` with `is_available()`, `commands()`, `help_text()`, `diagnostics()`
3. Add `"mymodule"` to `KNOWN_MODULES` in `module_loader.py`
4. All functions must never raise
5. No absolute paths
6. No top-level imports of `core`, `flow`, `warn`, or other lib files

---

*See also: [Flow Guide](flow_guide.md), [Developer — Module API](../developer/module_api.md)*
