# Config Reference

**Level:** Advanced  
**Files:** `runtime_core/conf/*.json`

---

## Config files

| File | Controls |
|---|---|
| `system_config.json` | Vault layout, session template, warnings |
| `prompter_config.json` | Display options, flow mode, topic derive |
| `cleaner_config.json` | Archive rules, log rotation, conflict handling |

All three are created from defaults on first run if absent.
All three are backed up to `conf/backups/` before any save.
Delete a file to reset it to defaults — it will be recreated.

---

## system_config.json

```json
{
  "vault_root": "../ai-vault",
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
    "bundles":   "bundles"
  },
  "session_template": {
    "prompt_field":         "prompts",
    "list_prefix":          "* ",
    "empty_slots":          2,
    "ai_markers":           true,
    "topic_block":          true,
    "include_instructions": true
  },
  "prompt_parsing": {
    "alias_prefixes":   ["* ", "- "],
    "case_sensitive":   false,
    "strip_whitespace": true
  },
  "composition": {
    "type_order":      ["task", "workflow", "style", "format", "constraint"],
    "section_headers": true
  },
  "warnings": {
    "enabled":      true,
    "block_on_red": false,
    "log_warnings": true
  }
}
```

### Key fields

**`vault_root`** — relative path from `runtime_core/` to the vault.
Must be relative. An absolute path triggers a RED warning.

**`vault_folders`** — dict of `{key: folder_name}`. Keys are used by
scripts and modules to look up folders without hardcoding names.
Changing a key here changes where all scripts look for that folder.

**`session_template.empty_slots`** — number of blank prompt lines to
include at the end of each SESSION block's prompt section.

**`session_template.ai_markers`** — whether to wrap the block in
`<---Start--->` / `<---End--->` markers for the AI to recognise boundaries.

**`warnings.block_on_red`** — set to `true` to refuse startup on any
RED warning. Safe for production use; too strict for development.

---

## prompter_config.json

```json
{
  "display": {
    "show_ai_markers":  true,
    "show_topic_block": true,
    "date_format":      "%Y-%m-%d",
    "time_format":      "%H:%M"
  },
  "behavior": {
    "topic_derive_mode": "all_combined",
    "flow_mode":         "normal"
  }
}
```

### Key fields

**`display.show_ai_markers`** — show `<---Start--->` / `<---End--->` in
the preview. Does not affect the copied block.

**`display.date_format`** / **`time_format`** — Python `strftime` format
strings. Appear in SESSION block header.

**`behavior.topic_derive_mode`** — how the topic field is built:
- `all_combined` — combine keywords from all active prompts
- `first_only` — use only the first active prompt's keywords
- `manual` — never derive; use whatever is in `state.json`

**`behavior.flow_mode`** — `"normal"`, `"paste_flow"`, or `"chat_flow"`.
See [Flow Guide](../intermediate/flow_guide.md).

---

## cleaner_config.json

```json
{
  "archive": {
    "max_log_lines":     400,
    "session_subfolder": true,
    "raw_subfolder":     true
  },
  "conflict": {
    "auto_resolve":   false,
    "log_conflicts":  true
  }
}
```

### Key fields

**`archive.max_log_lines`** — rotate `debug.log` when it exceeds this
many lines. Also used by `warn.py` for the `log_too_large` check.

**`archive.session_subfolder`** — organise archived sessions into
`YYYY-MM/` subfolders inside `002_sessions/`.

**`conflict.auto_resolve`** — if `true`, silently pick the newest version
when a session filename conflict is detected. Default is `false` (log and skip).

---

## Config loading order

```
lib/core.py DEFAULT_* dict     ← hard defaults
    ↓  deep merge
conf/*.json file on disk        ← your overrides
    ↓  result
script uses the merged dict
```

You only need to set the keys you want to change.
Any missing key in the JSON file is filled from the defaults.

---

## Backup policy

Before every save, the config system copies the existing file to
`conf/backups/system_config_YYYYMMDD_HHMMSS.json`.
Keep an eye on backup count — clean up old backups periodically.

---

*See also: [Vault Structure](vault_structure.md)*
