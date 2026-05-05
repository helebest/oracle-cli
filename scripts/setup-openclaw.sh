#!/usr/bin/env bash
set -euo pipefail

# Env injected by CLI:
#   REMOTE_DIR  (required) — absolute path of remote docker/openclaw dir

REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/docker/openclaw}"

echo "=== OpenClaw setup ==="

# [1/3] persistent dirs (uid 1000 = node user inside the openclaw image)
echo "[1/3] Preparing persistent dirs..."
mkdir -p "$REMOTE_DIR/data/config" "$REMOTE_DIR/data/workspace"
chown -R 1000:1000 "$REMOTE_DIR/data"

# [2/3] pull + start
echo "[2/3] Pulling image and starting container..."
cd "$REMOTE_DIR"
docker compose pull
docker compose up -d

# [3/3] verify loopback-only bind
echo "[3/3] Verifying bind..."
sleep 3
if ss -tlnp 2>/dev/null | grep -q "127.0.0.1:18789"; then
    echo "  OK — gateway listening on 127.0.0.1:18789 only."
elif ss -tlnp 2>/dev/null | grep -q ":18789"; then
    echo "  WARN — port 18789 is open on a non-loopback address. Check --bind flag." >&2
    ss -tlnp | grep ":18789" >&2
else
    echo "  (port not yet listening; container may still be starting — check \`--status\`)"
fi

echo ""
echo "Web UI is loopback-only. To reach it from a tailnet peer:"
echo "  ssh -L 18789:127.0.0.1:18789 ubuntu@oracle-vm"
echo "Then open http://localhost:18789 locally."
echo ""
echo "=== OpenClaw setup complete ==="
