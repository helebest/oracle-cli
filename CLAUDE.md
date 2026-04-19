# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation sync

Whenever a change affects user-visible behavior — new/renamed CLI commands or options, new services or mount paths, setup steps, or config keys — update **both** `CLAUDE.md` (this file) and `README.md` in the same commit. Keep the command list in `README.md` and the command table here in sync. Silent drift between the two is the main failure mode.

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
uv run oci-vm cloud metrics                # Past 24h CPU/Mem/Load/Net/Disk from OCI Monitoring
uv run oci-vm cloud metrics --hours 168    # Custom window (hours)
uv run oci-vm setup keepalive           # Deploy anti-reclaim keepalive service
uv run oci-vm setup keepalive --status  # Keepalive status + memory usage
uv run oci-vm setup keepalive --remove  # Remove keepalive service
uv run oci-vm setup obsidian-sync             # Deploy R2<->vault bisync for Hermes
uv run oci-vm setup obsidian-sync --status    # Sync container status + recent log
uv run oci-vm setup obsidian-sync --sync-now  # Trigger immediate bisync
uv run oci-vm setup obsidian-sync --reset     # Re-establish bisync baseline (dangerous)
uv run oci-vm setup tailscale                 # Install Tailscale and join tailnet (native, not Docker)
uv run oci-vm setup tailscale --status        # tailscale status + netcheck
uv run oci-vm setup tailscale --down          # Disconnect from tailnet (keep installed)
uv run oci-vm setup tailscale --remove        # Full uninstall
```

There are no tests, linter, or CI pipeline configured.

## Architecture

Two parallel backends: **CLI → SSH** (OS-level) and **CLI → OCI SDK** (cloud control plane)

- **cli.py** — Click command groups with Rich output. Command groups: `setup` (provisioning), `docker` (containers), `cloud` (OCI control plane). Top-level: `info`, `status`, `run`, `ssh`, `ports`, `deploy`.
- **config.py** — Loads `config.yaml` (project root, hardcoded path). Config schema matches `config.example.yaml`.
- **ssh.py** — Fabric/Paramiko wrapper. `get_connection()`, `run_remote()`, `run_script()`, `upload_dir()`.
- **oci_api.py** — OCI Python SDK wrapper. `get_instance_details()`, `instance_action()`, `get_public_ip()`, `get_network_info()`, `get_security_rules()`, `add_ingress_rule()`, `get_metrics(hours)` (queries Monitoring namespace `oci_computeagent`; bytes metrics use MQL `.rate()` because raw values are cumulative counters). Uses `~/.oci/config` for auth and `config.yaml` for instance/compartment IDs.

## Docker Services & Networking

All Docker services run with `network_mode: host` (sharing the host network stack). This is required because Oracle Cloud's iptables rules block Docker bridge network outbound traffic.

- **Caddy** (reverse proxy) — Listens on ports 80/443. Auto-HTTPS via Let's Encrypt. Caddyfile uses `{$DOMAIN}` env var injected via `.env` file on the remote.
- **3x-ui** (Xray proxy panel) — Web panel on port 2053, VLESS+Reality on port 8443.
- **Hermes** (AI agent) — `nousresearch/hermes-agent` from Docker Hub (multi-arch: amd64 + arm64). Custom Dockerfile adds `gh` and `vim`. Runs `gateway run` for messaging platforms. Has optional HTTP API on port 8642 (disabled by default, enable via `API_SERVER_ENABLED=true`).
- **Keepalive** (anti-reclaim) — Alpine container that runs a 180s CPU burst (sha256 loop on `/dev/urandom`) every 20 min to keep CPU utilization above Oracle's Free Tier idle threshold. Also does health checks of 3x-ui / hermes / caddy every 5 min (auto-restarts unhealthy containers), zombie-process cleanup every 30 min, and disk-space prune when > 80% full. No memory ballast — Oracle's reclamation criteria are AND-joined (CPU + network + memory all < 20% for 7 days) and CPU bursts alone have been empirically sufficient. Resource limits: 256M memory, 1.0 CPU.
- **obsidian-sync** — `rclone/rclone` container doing `bisync` between Cloudflare R2 (Remotely Save's rclone-crypt encrypted bucket) and a shared Docker volume `obsidian-sync_obsidian-vault`. Hermes mounts the decrypted volume read-write at `/opt/data/vault/secondbrain`, enabling its built-in Obsidian skill to read/search/create notes that round-trip to all your devices via Remotely Save. Bisync interval 10 min; conflict strategy = keep mtime-newer, loser saved as `.conflict1.md`; safety cap `--max-delete 5`. sync.sh runs `chown -R $VAULT_UID:$VAULT_GID /vault` (default `10000:10000`, matching the `hermes` user in `nousresearch/hermes-agent`; override via `docker/obsidian-sync/.env`) after each sync so the non-root Hermes agent can write. Secrets live in `docker/obsidian-sync/rclone.conf` (gitignored).
- **Tailscale** (mesh VPN) — Installed natively on the host (not Docker) via `scripts/setup-tailscale.sh`. Joins an existing tailnet so other nodes reach VM services over the tailnet IP without opening public ports. Config in `config.yaml` → `tailscale:` section (hostname, optional `advertise_routes`, optional `advertise_exit_node`). Auth defaults to interactive: `tailscale up` prints a login URL; open it in any browser to approve the device. For non-interactive / automated provisioning, optionally drop a reusable auth key at `credentials/tailscale.authkey` (gitignored) and set `auth_key_file` in config. IP forwarding is pre-enabled via `/etc/sysctl.d/99-tailscale.conf` so subnet-router / exit-node can be toggled later without touching the host. `--ssh=true` so tailnet peers can `ssh ubuntu@oracle-vm` without a key (authenticated by Tailscale identity + ACL); OpenSSH keeps listening on public :22 for out-of-tailnet access. Container-based install is avoided because the userspace-networking mode conflicts with Oracle's iptables setup.

Caddy reverse proxy routes:
- `3x-panel.{domain}` → `localhost:2053` (3x-ui panel, auto HTTPS)
- `:80` → default response

Config requirement: `domain` field in `config.yaml` (e.g. `domain: i-am-holo.top`). DNS A record must point the subdomain to the VM IP with Cloudflare proxy disabled (DNS only).

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
