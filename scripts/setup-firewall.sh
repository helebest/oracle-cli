#!/usr/bin/env bash
set -euo pipefail

echo "=== Step 3: Firewall Configuration ==="

# Oracle Cloud Ubuntu VMs have default iptables rules that REJECT all
# traffic except SSH (port 22). We need to insert ACCEPT rules BEFORE
# the REJECT rule to allow HTTP/HTTPS and other services.

echo "[1/3] Adding iptables rules..."

# Find the REJECT rule number in INPUT chain
REJECT_RULE=$(sudo iptables -L INPUT --line-numbers -n | grep "REJECT" | head -1 | awk '{print $1}')

if [ -z "$REJECT_RULE" ]; then
    echo "No REJECT rule found, appending rules..."
    sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
    sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
    sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT
else
    echo "Found REJECT rule at position $REJECT_RULE, inserting before it..."
    # Insert rules before the REJECT rule (order matters, insert in reverse)
    sudo iptables -I INPUT "$REJECT_RULE" -p udp --dport 51820 -j ACCEPT -m comment --comment "WireGuard"
    sudo iptables -I INPUT "$REJECT_RULE" -p tcp --dport 443 -j ACCEPT -m comment --comment "HTTPS"
    sudo iptables -I INPUT "$REJECT_RULE" -p tcp --dport 80 -j ACCEPT -m comment --comment "HTTP"
fi

echo "[2/3] Persisting iptables rules..."
sudo apt install -y iptables-persistent
sudo netfilter-persistent save

echo "[3/3] Current iptables INPUT rules:"
sudo iptables -L INPUT -n --line-numbers

echo ""
echo "=== Firewall configuration complete ==="
echo ""
echo "REMINDER: Also open these ports in Oracle Cloud Console:"
echo "  - Security List > Ingress Rules > Add:"
echo "    - 0.0.0.0/0  TCP  80   (HTTP)"
echo "    - 0.0.0.0/0  TCP  443  (HTTPS)"
echo "    - 0.0.0.0/0  UDP  51820 (WireGuard)"
