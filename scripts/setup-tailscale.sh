#!/usr/bin/env bash
set -euo pipefail

# Env injected by CLI:
#   TS_HOSTNAME       (required)
#   TS_ROUTES         (optional; comma-separated CIDRs)
#   TS_EXIT_NODE      (true|false)
#   TS_AUTHKEY_FILE   (optional; 600-perm file containing tskey-auth-...)
#                     if unset or empty, `tailscale up` will print a login URL
#                     for interactive browser approval.

echo "=== Tailscale setup ==="

# [1/5] Install tailscale (skip if already present)
if ! command -v tailscale >/dev/null 2>&1; then
    echo "[1/5] Installing tailscale via official script..."
    curl -fsSL https://tailscale.com/install.sh | sh
else
    echo "[1/5] tailscale already installed ($(tailscale version | head -1))"
fi

# [2/5] IP forwarding (needed for subnet router / exit node; safe to enable ahead of time)
echo "[2/5] Enabling IP forwarding..."
cat > /etc/sysctl.d/99-tailscale.conf <<EOF
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
sysctl -p /etc/sysctl.d/99-tailscale.conf >/dev/null

# [3/5] iptables: allow tailscale0 inbound (insert before REJECT, matching setup-firewall.sh pattern)
echo "[3/5] Configuring iptables for tailscale0..."
if iptables -C INPUT -i tailscale0 -j ACCEPT 2>/dev/null; then
    echo "  (tailscale0 ACCEPT rule already present)"
else
    REJECT_RULE=$(iptables -L INPUT --line-numbers -n | grep "REJECT" | head -1 | awk '{print $1}')
    if [ -n "$REJECT_RULE" ]; then
        iptables -I INPUT "$REJECT_RULE" -i tailscale0 -j ACCEPT -m comment --comment "tailscale"
    else
        iptables -A INPUT -i tailscale0 -j ACCEPT -m comment --comment "tailscale"
    fi
    if command -v netfilter-persistent >/dev/null 2>&1; then
        netfilter-persistent save >/dev/null
    else
        apt-get install -y iptables-persistent >/dev/null
        netfilter-persistent save >/dev/null
    fi
fi

# [4/5] tailscale up (or hot-update via `set` if already running)
echo "[4/5] Bringing tailscale up..."
ARGS="--hostname=${TS_HOSTNAME} --accept-routes=true --ssh=false"
if [ -n "${TS_ROUTES:-}" ]; then
    ARGS="$ARGS --advertise-routes=${TS_ROUTES}"
fi
if [ "${TS_EXIT_NODE:-false}" = "true" ]; then
    ARGS="$ARGS --advertise-exit-node"
fi

if tailscale status --json 2>/dev/null | grep -q '"BackendState"[[:space:]]*:[[:space:]]*"Running"'; then
    echo "  (already running; hot-updating via \`tailscale set\`)"
    # shellcheck disable=SC2086
    tailscale set $ARGS
elif [ -n "${TS_AUTHKEY_FILE:-}" ] && [ -s "${TS_AUTHKEY_FILE}" ]; then
    AUTHKEY=$(cat "$TS_AUTHKEY_FILE")
    # shellcheck disable=SC2086
    tailscale up --authkey="$AUTHKEY" $ARGS
    rm -f "$TS_AUTHKEY_FILE"
else
    echo "  (no auth key — \`tailscale up\` will print a login URL; open it in any browser to approve)"
    # shellcheck disable=SC2086
    tailscale up $ARGS
fi

# [5/5] Report
echo ""
echo "[5/5] Status:"
tailscale status || true
echo ""
echo "=== Tailscale setup complete ==="
