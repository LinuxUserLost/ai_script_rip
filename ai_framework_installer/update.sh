#!/usr/bin/env bash
# update.sh | ai_framework patch updater
#
# Merges a partial patch zip into runtime_WORK/.
# A patch zip contains any subset of the runtime/ folder tree.
#
# Rules:
#   - runtime_STEP10_LOCKED/ is NEVER touched
#   - ai-vault/ is NEVER touched
#   - configs are only replaced if the patch explicitly includes them
#   - Every overwritten file is backed up with a timestamp first
#   - Backup folder: backup_YYYYMMDD_HHMMSS/ beside this script
#   - runtime_WORK/ must exist (run install.sh first)
#
# Usage:
#   bash update.sh <patch.zip>
#   bash update.sh <patch.zip> --yes     # skip confirmation

set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
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
_log()  { echo "$(date '+%Y-%m-%d %H:%M:%S')  update   $*" >> "$LOG_FILE"; }

# ── Args ──────────────────────────────────────────────────────────────────────
PATCH_ZIP=""
AUTO_YES=0
for arg in "$@"; do
    [[ "$arg" == "--yes" ]] && AUTO_YES=1
    [[ "$arg" != "--yes" && -z "$PATCH_ZIP" ]] && PATCH_ZIP="$arg"
done

_confirm() {
    [[ $AUTO_YES -eq 1 ]] && return 0
    read -rp "    $1 [y/N]: " ans
    [[ "${ans,,}" == "y" ]]
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "\n${C_HEAD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${C_HEAD}║   ai_framework  update.sh                    ║${RESET}"
echo -e "${C_HEAD}╚══════════════════════════════════════════════╝${RESET}"
echo -e "  Base dir: ${C_DIM}$SELF_DIR${RESET}"

# ── Pre-flight ────────────────────────────────────────────────────────────────
_head "1. Pre-flight checks"

if [[ -z "$PATCH_ZIP" ]]; then
    _fail "No patch zip specified"
    echo -e "\n  Usage: bash update.sh <patch.zip> [--yes]\n"
    exit 1
fi

# Resolve zip path: if relative, resolve from CWD
[[ "$PATCH_ZIP" != /* ]] && PATCH_ZIP="$(pwd)/$PATCH_ZIP"

if [[ ! -f "$PATCH_ZIP" ]]; then
    _fail "Patch zip not found: $PATCH_ZIP"
    exit 1
fi
_ok "Patch zip found: $(basename "$PATCH_ZIP")"

if [[ ! -d "$WORK_DIR" ]]; then
    _fail "runtime_WORK/ not found at: $WORK_DIR"
    echo -e "\n  Run install.sh first.\n"
    exit 1
fi
_ok "runtime_WORK/ present"

if [[ -d "$LOCKED_DIR" ]]; then
    _ok "runtime_STEP10_LOCKED/ present (will not be touched)"
else
    _warn "runtime_STEP10_LOCKED/ not found — locked reference is missing"
fi

# ── Timestamp ─────────────────────────────────────────────────────────────────
TS="$(date '+%Y%m%d_%H%M%S')"
BACKUP_DIR="$SELF_DIR/backup_${TS}"
EXTRACT_DIR="$SELF_DIR/.patch_work_${TS}"

_cleanup() { rm -rf "$EXTRACT_DIR"; }
trap _cleanup EXIT

# ── Extract patch zip ─────────────────────────────────────────────────────────
_head "2. Extracting patch"

mkdir -p "$EXTRACT_DIR"
if ! unzip -q "$PATCH_ZIP" -d "$EXTRACT_DIR" 2>/dev/null; then
    _fail "Failed to extract: $PATCH_ZIP"
    exit 1
fi
_ok "Extracted"

# Locate runtime/ root — may be at top level or one folder deep
PATCH_SRC=""
if [[ -d "$EXTRACT_DIR/runtime" ]]; then
    PATCH_SRC="$EXTRACT_DIR/runtime"
else
    for d in "$EXTRACT_DIR"/*/runtime; do
        [[ -d "$d" ]] && { PATCH_SRC="$d"; break; }
    done
fi

if [[ -z "$PATCH_SRC" || ! -d "$PATCH_SRC" ]]; then
    _fail "Could not find runtime/ folder inside patch zip"
    echo -e "\n  Patch zip must contain a runtime/ folder at root or one level deep.\n"
    exit 1
fi

PATCH_FILE_COUNT=$(find "$PATCH_SRC" -type f | wc -l | tr -d ' ')
_ok "Patch root: $PATCH_SRC"
_info "$PATCH_FILE_COUNT file(s) in patch"

# ── Safety: refuse dangerous patch contents ───────────────────────────────────
_head "3. Safety checks"

SAFE=1

# Patch must not include vault or locked dir names
if find "$EXTRACT_DIR" -maxdepth 2 -name "ai-vault" -o \
        -maxdepth 2 -name "runtime_STEP10_LOCKED" 2>/dev/null | grep -q .; then
    _fail "Patch contains ai-vault/ or runtime_STEP10_LOCKED/ — refusing"
    SAFE=0
fi

# Warn if patch replaces configs (but allow it — it's intentional)
if find "$PATCH_SRC" -path "*/configs/*.json" | grep -q .; then
    _warn "Patch includes config files — will replace (existing files backed up first)"
fi

[[ $SAFE -eq 0 ]] && { echo -e "\n  Unsafe patch. Aborting.\n"; exit 1; }
_ok "Patch contents safe"

# ── Confirm ───────────────────────────────────────────────────────────────────
_head "4. Ready to apply"

echo -e "  Patch:    $(basename "$PATCH_ZIP")"
echo -e "  Target:   $WORK_DIR"
echo -e "  Backup:   $BACKUP_DIR"
echo -e "  Files:    $PATCH_FILE_COUNT"

if ! _confirm "Apply patch?"; then
    echo -e "\n  Aborted.\n"
    exit 0
fi

# ── Apply patch ───────────────────────────────────────────────────────────────
_head "5. Applying patch"

mkdir -p "$BACKUP_DIR"
APPLIED=0; BACKED_UP=0; SKIPPED=0; CREATED=0

_apply_file() {
    local rel="$1"
    local dst="$WORK_DIR/$rel"
    local src="$PATCH_SRC/$rel"
    local dst_dir; dst_dir="$(dirname "$dst")"

    # Never touch locked dir (belt + suspenders check)
    if [[ "$dst" == "$LOCKED_DIR"* ]]; then
        _warn "SKIP (locked): $rel"
        SKIPPED=$((SKIPPED+1))
        return
    fi

    # Never touch vault
    if [[ "$dst" == "$VAULT_DIR"* ]]; then
        _warn "SKIP (vault): $rel"
        SKIPPED=$((SKIPPED+1))
        return
    fi

    # Backup if existing file will be overwritten
    if [[ -f "$dst" ]]; then
        local bk_path="$BACKUP_DIR/$rel"
        mkdir -p "$(dirname "$bk_path")"
        cp "$dst" "$bk_path"
        BACKED_UP=$((BACKED_UP+1))
        _info "backup: $rel"
    else
        CREATED=$((CREATED+1))
    fi

    # Install
    mkdir -p "$dst_dir"
    cp "$src" "$dst"

    # Restore executable bit for shell scripts
    if [[ "$rel" == scripts/*.sh || "$rel" == *.sh ]]; then
        chmod +x "$dst"
        _info "apply (+x): $rel"
    else
        _info "apply: $rel"
    fi

    APPLIED=$((APPLIED+1))
    _log "applied: $rel"
}

# Walk all files in the patch
while IFS= read -r -d '' src_file; do
    rel="${src_file#$PATCH_SRC/}"
    _apply_file "$rel"
done < <(find "$PATCH_SRC" -type f -print0 | sort -z)

_ok "$APPLIED file(s) applied ($CREATED new, $((APPLIED-CREATED)) updated)"
[[ $BACKED_UP -gt 0 ]] && _ok "$BACKED_UP file(s) backed up → backup_${TS}/"
[[ $SKIPPED -gt 0 ]]   && _warn "$SKIPPED file(s) skipped (locked/vault)"

# ── Ensure all scripts are executable after patch ─────────────────────────────
_head "6. Permissions"

if [[ -d "$WORK_DIR/scripts" ]]; then
    find "$WORK_DIR/scripts" -name "*.sh" -exec chmod +x {} \;
    _ok "All scripts/*.sh set +x"
fi

# ── Post-patch verify ─────────────────────────────────────────────────────────
_head "7. Post-patch verification"

if [[ -f "$SELF_DIR/verify.sh" ]]; then
    bash "$SELF_DIR/verify.sh" --target "$WORK_DIR"
else
    _warn "verify.sh not found — skipping"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
_head "Update complete"

echo -e "  ${C_OK}Applied${RESET}   $APPLIED file(s)"
[[ $BACKED_UP -gt 0 ]] && echo -e "  ${C_OK}Backup${RESET}    backup_${TS}/  ($BACKED_UP files)"
echo -e "  ${C_DIM}Log${RESET}       $LOG_FILE"
echo

_log "update.sh done (applied=$APPLIED backed_up=$BACKED_UP patch=$(basename "$PATCH_ZIP"))"
