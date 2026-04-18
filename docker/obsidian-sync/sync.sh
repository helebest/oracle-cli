#!/bin/sh
# Bidirectional sync between Cloudflare R2 (rclone-crypt) and local /vault.
#
# Three-phase bootstrap, because `bisync --resync` against an empty /vault
# stalled indefinitely in practice on this setup:
#
#   Phase 1 (once): rclone copy r2-crypt: /vault
#     Populates the empty volume with the decrypted vault.
#
#   Phase 2 (once): rclone bisync --resync
#     With both sides already identical, this just writes the .lst state files
#     without transferring data — bisync needs this state to work in Phase 3.
#
#   Phase 3 (loop): rclone bisync
#     Normal bidirectional sync every $INTERVAL seconds.

REMOTE="r2-crypt:"
LOCAL="/vault"
STATE="/bisync-state"
INTERVAL=600
VAULT_UID="${VAULT_UID:-10000}"
VAULT_GID="${VAULT_GID:-10000}"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

# Keep /vault owned by VAULT_UID:VAULT_GID so the Hermes non-root user can
# write. rclone runs as root, so new files from R2 land as root:root otherwise.
fix_perms() { chown -R "$VAULT_UID:$VAULT_GID" "$LOCAL" 2>&1 | tail -n 5; }

trap 'log "Shutting down."; exit 0' TERM INT

if [ ! -f "$STATE/.populated" ]; then
    log "Phase 1: rclone copy (initial vault population)"
    if rclone copy "$REMOTE" "$LOCAL" \
        --stats 30s \
        --log-level INFO; then
        fix_perms
        touch "$STATE/.populated"
        log "Phase 1 complete."
    else
        log "ERROR: rclone copy failed. Will retry."
        sleep "$INTERVAL"
        exec "$0"
    fi
fi

if [ ! -f "$STATE/.initialized" ]; then
    log "Phase 2: rclone bisync --resync (establishing bisync state)"
    if rclone bisync "$REMOTE" "$LOCAL" \
        --resync \
        --resync-mode path1 \
        --workdir "$STATE" \
        --create-empty-src-dirs \
        --check-access=false \
        --exclude ".obsidian/workspace*" \
        --exclude ".trash/**" \
        --exclude "*.conflict*" \
        --log-level INFO; then
        fix_perms
        touch "$STATE/.initialized"
        log "Phase 2 complete. Bisync baseline established."
    else
        log "ERROR: bisync --resync failed. Will retry."
        sleep "$INTERVAL"
        exec "$0"
    fi
fi

log "Phase 3: bisync loop (interval: ${INTERVAL}s)"
while true; do
    rclone bisync "$REMOTE" "$LOCAL" \
        --workdir "$STATE" \
        --conflict-resolve newer \
        --conflict-loser num \
        --max-delete 5 \
        --check-access=false \
        --exclude ".obsidian/workspace*" \
        --exclude ".trash/**" \
        --exclude "*.conflict*" \
        --log-level INFO \
        || log "bisync returned non-zero (likely transient); retrying next tick"

    fix_perms

    sleep "$INTERVAL" &
    wait $!
done
