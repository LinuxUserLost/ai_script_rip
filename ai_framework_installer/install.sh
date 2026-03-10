#!/usr/bin/env bash
# install.sh | ai_framework installer
#
# Fresh install from an extracted release zip.
#
# Expected layout when run:
#   <any parent folder>/
#     install.sh              ← this file
#     update.sh
#     verify.sh
#     runtime/                ← source tree from zip
#
# Creates beside this script:
#   runtime_WORK/             ← live working installation
#   runtime_STEP10_LOCKED/    ← reference copy (created once, NEVER overwritten)
#   ai-vault/                 ← user vault skeleton (never deleted or replaced)
#
# Usage:
#   bash install.sh           # interactive
#   bash install.sh --yes     # skip all confirmations

set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SELF_DIR/runtime"
WORK_DIR="$SELF_DIR/runtime_WORK"
LOCKED_DIR="$SELF_DIR/runtime_STEP10_LOCKED"
VAULT_DIR="$SELF_DIR/ai-vault"
LOG_FILE="$SELF_DIR/install.log"

# ── Colours ───────────────────────────────────────────────────────────────────
C_OK="\033[92m"; C_FAIL="\033[91m"; C_WARN="\033[93m"
C_HEAD="\033[96m"; C_DIM="\033[2m"; RESET="\033[0m"

_ok()   { echo -e "  ${C_OK}PASS${RESET}  $*"; }
_fail() { echo -e "  ${C_FAIL}FAIL${RESET}  $*"; }
_warn() { echo -e "  ${C_WARN}WARN${RESET}  $*"; }
_info() { echo -e "  ${C_DIM}....${RESET}  $*"; }
_head() { echo -e "\n${C_HEAD}── $* ${RESET}"; }
_log()  { echo "$(date '+%Y-%m-%d %H:%M:%S')  install  $*" >> "$LOG_FILE"; }

# ── Args ──────────────────────────────────────────────────────────────────────
AUTO_YES=0
for arg in "$@"; do [[ "$arg" == "--yes" ]] && AUTO_YES=1; done

_confirm() {
    [[ $AUTO_YES -eq 1 ]] && return 0
    read -rp "    $1 [y/N]: " ans
    [[ "${ans,,}" == "y" ]]
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "\n${C_HEAD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${C_HEAD}║   ai_framework  install.sh                   ║${RESET}"
echo -e "${C_HEAD}╚══════════════════════════════════════════════╝${RESET}"
echo -e "  Base dir: ${C_DIM}$SELF_DIR${RESET}"

# ── Pre-flight: source must exist ─────────────────────────────────────────────
_head "1. Pre-flight checks"

if [[ ! -d "$SRC_DIR" ]]; then
    _fail "runtime/ source not found at: $SRC_DIR"
    echo -e "\n  Run this script from the extracted zip folder."
    echo -e "  Expected: runtime/ folder beside install.sh\n"
    exit 1
fi
_ok "runtime/ source present"

REQUIRED_SRC=(
    "core.py" "flow.py" "warn.py" "module_loader.py" "app.py"
    "configs/system_config.json"
    "configs/prompter_config.json"
    "configs/cleaner_config.json"
    "modules/prompter.py"
    "modules/cleaner.py"
    "modules/prompt_manager.py"
    "modules/learning/__init__.py"
    "modules/analyzer/__init__.py"
    "modules/chat/__init__.py"
    "modules/editor/__init__.py"
    "modules/gui/__init__.py"
    "modules/updater/__init__.py"
    "scripts/hotkey_prompter.sh"
    "scripts/hotkey_cleaner.sh"
    "scripts/terminal_prompter.sh"
    "scripts/terminal_cleaner.sh"
    "scripts/terminal_manager.sh"
)

SRC_FAIL=0
for f in "${REQUIRED_SRC[@]}"; do
    if [[ ! -f "$SRC_DIR/$f" ]]; then
        _fail "Missing in source: runtime/$f"
        SRC_FAIL=1
    fi
done
[[ $SRC_FAIL -eq 0 ]] && _ok "All ${#REQUIRED_SRC[@]} required source files present"
[[ $SRC_FAIL -eq 1 ]] && { echo -e "\n  Source is incomplete. Aborting.\n"; exit 1; }

# ── Check existing install ────────────────────────────────────────────────────
_head "2. Install target"

REINSTALL=0
if [[ -d "$WORK_DIR" ]]; then
    _warn "runtime_WORK/ already exists"
    if ! _confirm "Reinstall? (configs will be preserved, code will be updated)"; then
        echo -e "\n  Aborted. Use update.sh to apply a patch zip instead.\n"
        exit 0
    fi
    REINSTALL=1
    _info "Reinstall confirmed"
else
    _info "Fresh install — runtime_WORK/ will be created"
fi

# ── Create directory tree ─────────────────────────────────────────────────────
_head "3. Creating directories"

DIRS=(
    "" "configs" "modules" "scripts" "logs" "logs/archive"
    "modules/learning" "modules/analyzer" "modules/chat"
    "modules/editor" "modules/gui" "modules/updater"
)
for d in "${DIRS[@]}"; do
    mkdir -p "$WORK_DIR/$d"
done
_ok "Directory tree ready"

# ── Copy helper ───────────────────────────────────────────────────────────────
_copy() {
    local src="$SRC_DIR/$1" dst="$WORK_DIR/$1"
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
}

# ── Core lib files (always overwrite) ─────────────────────────────────────────
_head "4. Installing core library"

for f in core.py flow.py warn.py module_loader.py app.py; do
    _copy "$f"
    _info "$f"
done
_ok "Core library installed"

# ── Configs (preserve on reinstall unless missing) ────────────────────────────
_head "5. Installing configs"

CFG_NEW=0; CFG_KEPT=0
for f in configs/system_config.json configs/prompter_config.json configs/cleaner_config.json; do
    dst="$WORK_DIR/$f"
    if [[ -f "$dst" && $REINSTALL -eq 1 ]]; then
        _info "$f  (preserved existing)"
        CFG_KEPT=$((CFG_KEPT+1))
    else
        _copy "$f"
        _info "$f  (installed)"
        CFG_NEW=$((CFG_NEW+1))
    fi
done
_ok "Configs: $CFG_NEW installed, $CFG_KEPT preserved"

# ── Script modules ────────────────────────────────────────────────────────────
_head "6. Installing script modules"

for f in modules/prompter.py modules/cleaner.py modules/prompt_manager.py; do
    _copy "$f"; _info "$f"
done
_ok "Script modules installed"

# ── Module stubs ──────────────────────────────────────────────────────────────
_head "7. Installing module stubs"

for mod in learning analyzer chat editor gui updater; do
    src="$SRC_DIR/modules/$mod/__init__.py"
    if [[ -f "$src" ]]; then
        _copy "modules/$mod/__init__.py"
        _info "modules/$mod/__init__.py"
    fi
done
_ok "Module stubs installed"

# ── Shell scripts + permissions ───────────────────────────────────────────────
_head "8. Installing shell scripts"

for f in "$SRC_DIR/scripts/"*.sh; do
    fname="$(basename "$f")"
    cp "$f" "$WORK_DIR/scripts/$fname"
    chmod +x "$WORK_DIR/scripts/$fname"
    _info "scripts/$fname  (+x)"
done
_ok "Shell scripts installed and made executable"

# ── Guides ────────────────────────────────────────────────────────────────────
_head "9. Installing guides"

if [[ -d "$SRC_DIR/guides" ]]; then
    cp -r "$SRC_DIR/guides/." "$WORK_DIR/guides/"
    GUIDE_COUNT=$(find "$SRC_DIR/guides" -name "*.md" | wc -l | tr -d ' ')
    _ok "Guides installed ($GUIDE_COUNT .md files)"
else
    _warn "guides/ not found in source — skipping"
fi

# ── Locked reference (create once, never overwrite) ───────────────────────────
_head "10. Locked reference copy"

if [[ -d "$LOCKED_DIR" ]]; then
    _warn "runtime_STEP10_LOCKED/ already exists — not modified (by design)"
    _info  "  $LOCKED_DIR"
else
    cp -r "$SRC_DIR" "$LOCKED_DIR"
    rm -f  "$LOCKED_DIR/state.json"
    rm -rf "$LOCKED_DIR/logs"
    _ok "runtime_STEP10_LOCKED/ created (will never be overwritten)"
    _log "LOCKED copy created: $LOCKED_DIR"
fi

# ── Vault skeleton (create if missing, never overwrite) ───────────────────────
_head "11. Vault skeleton"

if [[ -d "$VAULT_DIR" ]]; then
    _warn "ai-vault/ already exists — not modified"
else
    VAULT_FOLDERS=(
        "000_indexes" "001_topics" "002_sessions" "003_raw"
        "004_prompts" "005_tags" "006_knowledge" "007_guides"
        "008_agents" "009_tutorials" "bundles"
    )
    for folder in "${VAULT_FOLDERS[@]}"; do
        mkdir -p "$VAULT_DIR/$folder"
    done
    _ok "ai-vault/ skeleton created with ${#VAULT_FOLDERS[@]} subfolders"
    _log "Vault skeleton created: $VAULT_DIR"
fi

# ── Verify ────────────────────────────────────────────────────────────────────
_head "12. Running verify.sh"

if [[ -f "$SELF_DIR/verify.sh" ]]; then
    bash "$SELF_DIR/verify.sh" --target "$WORK_DIR"
else
    _warn "verify.sh not found beside install.sh — skipping verify step"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
_head "Install complete"

echo -e "  ${C_OK}runtime_WORK${RESET}          $WORK_DIR"
echo -e "  ${C_OK}runtime_STEP10_LOCKED${RESET}  $LOCKED_DIR"
echo -e "  ${C_OK}ai-vault${RESET}               $VAULT_DIR"
echo -e "  ${C_DIM}log${RESET}                    $LOG_FILE"
echo

_log "install.sh done (reinstall=$REINSTALL)"
