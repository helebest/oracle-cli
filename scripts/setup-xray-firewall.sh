#!/usr/bin/env bash
set -euo pipefail

echo "=== 3x-ui Firewall Setup ==="

# Open TCP 2053 (3x-ui panel) in iptables before the REJECT rule
REJECT_RULE=$(sudo iptables -L INPUT --line-numbers -n | grep "REJECT" | head -1 | awk '{print $1}')

if [ -z "$REJECT_RULE" ]; then
    sudo iptables -A INPUT -p tcp --dport 2053 -j ACCEPT -m comment --comment "3x-ui panel"
else
    # Check if rule already exists
    if sudo iptables -L INPUT -n | grep -q "dpt:2053"; then
        echo "Port 2053 already open in iptables."
    else
        echo "Inserting TCP 2053 before REJECT rule at position $REJECT_RULE..."
        sudo iptables -I INPUT "$REJECT_RULE" -p tcp --dport 2053 -j ACCEPT -m comment --comment "3x-ui panel"
    fi
fi

# Persist
sudo netfilter-persistent save

echo "Current iptables INPUT rules:"
sudo iptables -L INPUT -n --line-numbers

echo "=== Firewall setup complete ==="
