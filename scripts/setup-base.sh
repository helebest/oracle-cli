#!/usr/bin/env bash
set -euo pipefail

echo "=== Step 1: Base Environment Setup ==="

# System update
echo "[1/4] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Timezone
echo "[2/4] Setting timezone to UTC..."
sudo timedatectl set-timezone UTC

# Swap (4GB) - prevents OOM on 24GB RAM when running heavy containers
echo "[3/4] Setting up 4GB swap..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 4G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    # Tune swappiness - only swap when really needed
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.d/99-swap.conf
    sudo sysctl -p /etc/sysctl.d/99-swap.conf
    echo "Swap configured."
else
    echo "Swap already exists, skipping."
fi

# Essential tools
echo "[4/4] Installing base tools..."
sudo apt install -y curl git htop jq unzip wget ca-certificates gnupg lsb-release

echo "=== Base setup complete ==="
