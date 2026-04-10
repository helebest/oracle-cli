#!/usr/bin/env bash
set -euo pipefail

echo "=== Step 4: Security Hardening ==="

# SSH hardening
echo "[1/3] Hardening SSH..."
SSHD_CONFIG="/etc/ssh/sshd_config"

sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONFIG"
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD_CONFIG"
sudo sed -i 's/^#\?PermitEmptyPasswords.*/PermitEmptyPasswords no/' "$SSHD_CONFIG"
sudo sed -i 's/^#\?MaxAuthTries.*/MaxAuthTries 3/' "$SSHD_CONFIG"

sudo systemctl restart ssh
echo "SSH hardened: root login disabled, password auth disabled, max 3 auth tries."

# Install fail2ban via apt
echo "[2/3] Installing fail2ban..."
if command -v fail2ban-server &>/dev/null; then
    echo "fail2ban already installed: $(fail2ban-server --version 2>&1 | head -1)"
else
    sudo apt install -y fail2ban
fi

# Configure fail2ban jail
echo "[3/3] Configuring fail2ban SSH jail..."
sudo tee /etc/fail2ban/jail.local > /dev/null <<'JAIL'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
bantime = 3600
JAIL

sudo systemctl enable fail2ban
sudo systemctl restart fail2ban

echo "--- Fail2ban status ---"
sudo fail2ban-client status sshd 2>/dev/null || echo "fail2ban starting up..."

echo "=== Security hardening complete ==="
