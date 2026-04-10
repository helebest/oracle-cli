#!/usr/bin/env bash
set -euo pipefail

echo "=== Step 2: Docker CE Installation ==="

# Check if Docker is already installed
if command -v docker &>/dev/null; then
    echo "Docker already installed: $(docker --version)"
    echo "Skipping installation."
    exit 0
fi

# Remove any old/conflicting packages
echo "[1/4] Removing conflicting packages..."
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
    sudo apt remove -y "$pkg" 2>/dev/null || true
done

# Add Docker's official GPG key and repository
echo "[2/4] Adding Docker official repository..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update

# Install Docker CE 29.x + plugins
echo "[3/4] Installing Docker CE + Compose plugin..."
sudo apt install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

# Post-install: add ubuntu user to docker group
echo "[4/4] Configuring Docker..."
sudo usermod -aG docker ubuntu
sudo systemctl enable docker
sudo systemctl start docker

# Verify
echo "--- Verification ---"
docker version
docker compose version

echo "=== Docker installation complete ==="
echo "NOTE: Log out and back in for docker group to take effect, or run: newgrp docker"
