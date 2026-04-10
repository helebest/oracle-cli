# oracle-cli

CLI tool for managing Oracle Cloud ARM VM instance (VM.Standard.A1.Flex).

## Setup

```bash
# Install dependencies
uv sync

# Copy config template and fill in your VM details
cp config.example.yaml config.yaml

# Place your SSH key in credentials/
mkdir -p credentials
cp /path/to/your/ssh-key.key credentials/
chmod 600 credentials/*.key
```

## Usage

```bash
# Show VM info
uv run oci-vm info

# Check VM status
uv run oci-vm status

# One-click infrastructure setup
uv run oci-vm setup all

# Deploy 3x-ui (Xray proxy)
uv run oci-vm setup xray

# Deploy Hermes Agent
uv run oci-vm setup hermes

# Manage Docker containers
uv run oci-vm docker ps
uv run oci-vm docker logs <name>
uv run oci-vm docker stats

# Deploy custom docker-compose
uv run oci-vm deploy ./path/to/docker-compose.yml --name myservice

# Run remote command
uv run oci-vm run "uptime"

# OCI cloud management (no SSH required)
uv run oci-vm cloud info         # Instance details
uv run oci-vm cloud start        # Start instance
uv run oci-vm cloud stop         # Graceful stop
uv run oci-vm cloud stop --force # Hard stop
uv run oci-vm cloud reboot       # Graceful reboot
uv run oci-vm cloud ip           # Public IP lookup
uv run oci-vm cloud network      # VCN/subnet info
uv run oci-vm cloud security     # OCI firewall rules
```

## Project Structure

```
oracle-cli/
├── config.example.yaml    # Config template (copy to config.yaml)
├── credentials/           # SSH keys (git ignored)
├── docker/                # Docker compose configs
│   ├── 3x-ui/            # Xray proxy panel
│   ├── caddy/            # Reverse proxy
│   └── hermes/           # Hermes Agent
├── oracle_cli/            # Python CLI package
│   ├── cli.py            # Click commands
│   ├── config.py         # Config loader
│   ├── oci_api.py        # OCI SDK helpers
│   └── ssh.py            # SSH/Fabric helpers
└── scripts/               # Remote setup scripts
```
