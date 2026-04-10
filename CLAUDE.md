# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

oracle-cli is a CLI tool for managing Oracle Cloud ARM VM instances (VM.Standard.A1.Flex). It provisions infrastructure, deploys Docker services (3x-ui proxy, Caddy, Hermes AI agent), and manages containers over SSH.

## Commands

```bash
uv sync                        # Install dependencies
uv run oci-vm <command>        # Run the CLI
uv run oci-vm setup all        # Full VM setup (base → docker → firewall → security)
uv run oci-vm status           # VM metrics
uv run oci-vm docker ps        # List containers
uv run oci-vm cloud info       # Instance details from OCI API
uv run oci-vm cloud start      # Start instance (no SSH needed)
uv run oci-vm cloud stop       # Graceful stop
uv run oci-vm cloud ip         # Public IP lookup
uv run oci-vm cloud network    # VCN/subnet info
uv run oci-vm cloud security   # OCI firewall rules
```

There are no tests, linter, or CI pipeline configured.

## Architecture

Two parallel backends: **CLI → SSH** (OS-level) and **CLI → OCI SDK** (cloud control plane)

- **cli.py** — Click command groups with Rich output. Command groups: `setup` (provisioning), `docker` (containers), `cloud` (OCI control plane). Top-level: `info`, `status`, `run`, `ssh`, `ports`, `deploy`.
- **config.py** — Loads `config.yaml` (project root, hardcoded path). Config schema matches `config.example.yaml`.
- **ssh.py** — Fabric/Paramiko wrapper. `get_connection()`, `run_remote()`, `run_script()`, `upload_dir()`.
- **oci_api.py** — OCI Python SDK wrapper. `get_instance_details()`, `instance_action()`, `get_public_ip()`, `get_network_info()`, `get_security_rules()`. Uses `~/.oci/config` for auth and `config.yaml` for instance/compartment IDs.

## Key Conventions

- Entry point: `oracle_cli.cli:cli` registered as `oci-vm`
- Config lives at `config.yaml` (gitignored); copy from `config.example.yaml`
- SSH key goes in `credentials/` (gitignored)
- Remote Docker compose files deploy to `/home/ubuntu/docker/<service>/`
- Setup scripts in `scripts/` are self-contained bash scripts executed remotely via `run_script()`
- Docker service configs in `docker/<service>/docker-compose.yml`

## Dependencies

click (CLI), fabric (SSH), oci (OCI Python SDK), rich (terminal UI), pyyaml (config). Python ≥ 3.12. Managed with uv.

OCI SDK auth config lives at `~/.oci/config` (created by `oci setup config`). Instance/compartment IDs stored in `config.yaml` under `oci:` section.
