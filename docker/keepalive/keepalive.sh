#!/bin/sh
# Keepalive service for Oracle Cloud Always Free tier.
# Prevents VM reclamation by holding ~5GB in a tmpfs ballast
# and running periodic health checks for network activity.

BALLAST_FILE="/ballast/fill"
BALLAST_MB=5120
HEALTH_INTERVAL=300

# --- Phase 1: Fill memory ballast ---
echo "[keepalive] Allocating ${BALLAST_MB}MB memory ballast..."
dd if=/dev/urandom of="$BALLAST_FILE" bs=1M count="$BALLAST_MB" 2>&1
ballast_size=$(du -sh "$BALLAST_FILE" 2>/dev/null | cut -f1)
echo "[keepalive] Ballast allocated: $ballast_size"

# --- Phase 2: Health check loop ---
trap 'echo "[keepalive] Shutting down."; exit 0' TERM INT

echo "[keepalive] Starting health check loop (interval: ${HEALTH_INTERVAL}s)"
while true; do
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Local connectivity (Caddy)
    if wget -q -O /dev/null --timeout=10 http://localhost:80 2>/dev/null; then
        echo "$ts [health] caddy: OK"
    else
        echo "$ts [health] caddy: UNREACHABLE"
    fi

    # External connectivity
    if wget -q -O /dev/null --timeout=10 https://www.gstatic.com/generate_204 2>/dev/null; then
        echo "$ts [health] external: OK"
    else
        echo "$ts [health] external: UNREACHABLE"
    fi

    # Ballast integrity
    ballast_size=$(du -sh "$BALLAST_FILE" 2>/dev/null | cut -f1)
    echo "$ts [ballast] size=$ballast_size"

    sleep "$HEALTH_INTERVAL" &
    wait $!
done
