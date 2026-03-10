# Flow Guide

**Level:** Intermediate  
**File:** `runtime_core/lib/flow.py`

---

## What is a flow mode?

Flow modes change what happens after you copy a SESSION block.
The default (`normal`) returns you to the menu after copying.
Alternative modes keep you in a tight loop so you can work faster
without navigating the menu between every exchange.

Flow is optional. Default is `normal`. Nothing changes unless you opt in.

---

## Available modes

| Mode | Key | Best for |
|---|---|---|
| `normal` | — | Default, menu-based workflow |
| `paste_flow` | `r` `Enter` `q` | Single-window chat, manual paste |
| `chat_flow` | `c` `n` `s` `q` | Terminal-only, minimal keystrokes |

---

## Setting your flow mode

Edit `runtime_core/conf/prompter_config.json`:

```json
{
  "behavior": {
    "flow_mode": "paste_flow"
  }
}
```

Valid values: `"normal"`, `"paste_flow"`, `"chat_flow"`

Any invalid value falls back to `"normal"` automatically.

---

## paste_flow

Stays active after you copy a block. You paste into your chat window manually,
get a response, then come back and press Enter to copy the next block.

```
Copy block  →  paste into chat  →  get response  →  Enter (next)
```

**Keys:**

| Key | Action |
|---|---|
| `Enter` | Build and copy next SESSION block |
| `r` | Re-copy the current block (if clipboard was cleared) |
| `q` | Exit flow, return to menu |

**When to use:** You have one terminal window and one chat window side by side.
You alternate between them manually.

---

## chat_flow

Minimal interface. Four single-character commands. No menu navigation.
Good for fast iteration when you know what you want.

**Keys:**

| Key | Action |
|---|---|
| `c` | Copy current block to clipboard |
| `n` | Build and copy next block |
| `s` | Show current block in the terminal |
| `q` | Exit flow, return to menu |

**When to use:** Pure terminal session. You want the minimum keystrokes
between sending one prompt and building the next.

---

## How flow is activated

Flow only activates when:
1. `flow_mode` is not `"normal"` in `prompter_config.json`
2. `flow.py` is present in `lib/`
3. You use option `1` (Copy to clipboard) from the main menu

If `flow.py` is missing, the prompter falls back to `normal` silently.

---

## The build_fn closure

When flow activates, it receives a `build_fn` closure that captures the
current session state. Each call to `build_fn()` produces the next SESSION
block and increments the log number. The flow loop never directly calls
`build_session_block()` — it uses the closure.

This means:
- Log numbers stay sequential even across many flow iterations
- State is saved on each successful copy
- Closing the flow returns to the menu without losing state

---

## Turning flow off

Set `flow_mode` back to `"normal"` in `prompter_config.json`, or delete the
`flow_mode` key entirely — the default is `"normal"`.

---

*See also: [Warning Guide](warning_guide.md), [Module Guide](module_guide.md)*
