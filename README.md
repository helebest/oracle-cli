# oracle-cli

CLI tool for managing an Oracle Cloud ARM VM instance (VM.Standard.A1.Flex). Provisions infrastructure over SSH and drives the OCI control plane via the Python SDK.

## Setup

```bash
# Install dependencies
uv sync

# Copy config template and fill in VM / OCI IDs
cp config.example.yaml config.yaml

# Place the SSH key in credentials/
mkdir -p credentials
cp /path/to/your/ssh-key.key credentials/
chmod 600 credentials/*.key

# OCI SDK auth (one-time)
oci setup config    # writes ~/.oci/config
```

## Usage

```bash
# VM info / status
uv run oci-vm info                         # Config summary
uv run oci-vm status                       # Uptime, load, memory, disk, docker
uv run oci-vm ssh                          # Print SSH command for manual login
uv run oci-vm ports                        # Open ports
uv run oci-vm run "uptime"                 # One-shot remote command

# Infrastructure setup (run once, or per-service)
uv run oci-vm setup all                    # Base → Docker → firewall → security
uv run oci-vm setup base                   # Base OS env
uv run oci-vm setup docker                 # Docker CE
uv run oci-vm setup firewall               # iptables / ufw
uv run oci-vm setup security               # Hardening
uv run oci-vm setup caddy                  # Caddy reverse proxy (auto-HTTPS)
uv run oci-vm setup xray                   # 3x-ui Xray proxy panel
uv run oci-vm setup hermes                 # Hermes AI agent (nousresearch/hermes-agent)
uv run oci-vm setup keepalive              # Anti-reclaim keepalive + health monitor
uv run oci-vm setup keepalive --status     #   status + memory usage
uv run oci-vm setup keepalive --remove     #   remove
uv run oci-vm setup obsidian-sync          # R2 ↔ Hermes vault bisync
uv run oci-vm setup obsidian-sync --status #   container status + recent bisync log
uv run oci-vm setup obsidian-sync --sync-now # trigger immediate bisync
uv run oci-vm setup obsidian-sync --reset  #   re-establish bisync baseline (dangerous)
uv run oci-vm setup tailscale              # Install Tailscale + join tailnet (native)
uv run oci-vm setup tailscale --status     #   tailscale status + netcheck
uv run oci-vm setup tailscale --down       #   disconnect from tailnet (keep installed)
uv run oci-vm setup tailscale --remove     #   full uninstall

# Docker management (over SSH)
uv run oci-vm docker ps                    # List containers
uv run oci-vm docker logs <name>
uv run oci-vm docker stats
uv run oci-vm deploy ./path/to/docker-compose.yml --name myservice

# OCI cloud control plane (no SSH required)
uv run oci-vm cloud info                   # Instance details
uv run oci-vm cloud start                  # Start instance
uv run oci-vm cloud stop                   # Graceful stop
uv run oci-vm cloud stop --force           # Hard stop
uv run oci-vm cloud reboot                 # Graceful reboot
uv run oci-vm cloud ip                     # Public IP
uv run oci-vm cloud network                # VCN / subnet info
uv run oci-vm cloud security               # Ingress security rules
uv run oci-vm cloud metrics                # Past 24h CPU / Mem / Load / Net / Disk
uv run oci-vm cloud metrics --hours 168    # Custom window (hours)
```

## Services on the VM

| Service | Role | Compose |
|---|---|---|
| Caddy | Reverse proxy + auto-HTTPS on :80 / :443 | `docker/caddy/` |
| 3x-ui | Xray proxy panel (:2053 web, :8443 VLESS+Reality) | `docker/3x-ui/` |
| Hermes | `nousresearch/hermes-agent` — `gateway run`; Obsidian vault at `/opt/data/vault/secondbrain` | `docker/hermes/` |
| Keepalive | 180s CPU burst every 20 min + health checks + zombie / disk cleanup (anti-reclaim on Oracle Free Tier) | `docker/keepalive/` |
| obsidian-sync | `rclone` bisync between Cloudflare R2 (rclone-crypt) and the shared `obsidian-sync_obsidian-vault` docker volume | `docker/obsidian-sync/` |
| Tailscale | Mesh VPN joining an existing tailnet — native install (not Docker). Subnet router / exit node capability pre-wired, off by default. | `scripts/setup-tailscale.sh` |

All containers run with `network_mode: host` — Oracle Cloud's iptables rules block Docker bridge outbound traffic.

## Project Structure

```
oracle-cli/
├── config.example.yaml   # Config template (copy to config.yaml, gitignored)
├── credentials/          # SSH keys + tailscale auth key (gitignored)
├── docker/               # Docker compose configs
│   ├── 3x-ui/
│   ├── caddy/
│   ├── hermes/
│   ├── keepalive/
│   └── obsidian-sync/
├── oracle_cli/           # Python CLI package
│   ├── cli.py            # Click commands (info / status / setup / docker / cloud / …)
│   ├── config.py         # config.yaml loader
│   ├── oci_api.py        # OCI SDK helpers (instance, network, security, metrics)
│   └── ssh.py            # SSH / Fabric helpers
└── scripts/              # Remote setup shell scripts
```

## Auth & Config

- `config.yaml` (gitignored) holds VM SSH details and OCI instance / compartment OCIDs.
- `~/.oci/config` (written by `oci setup config`) holds OCI SDK credentials.
- `docker/obsidian-sync/rclone.conf` (gitignored) holds R2 credentials and crypt passwords; copy from `rclone.conf.example`.
- `docker/obsidian-sync/.env` (gitignored, optional) can override `VAULT_UID` / `VAULT_GID` — defaults `10000:10000` match the non-root `hermes` user in the upstream Hermes image.
- Tailscale auth defaults to **interactive**: `setup tailscale` prints a login URL — open it in any browser to approve the VM. `config.yaml` → `tailscale:` section tunes hostname / `advertise_routes` / `advertise_exit_node`. For fully non-interactive provisioning, generate a reusable auth key at [admin panel → Settings → Keys](https://login.tailscale.com/admin/settings/keys), save it to `credentials/tailscale.authkey` (gitignored), and set `auth_key_file` in config. After enabling `advertise_routes` or `advertise_exit_node`, approve the machine at [admin panel → Machines](https://login.tailscale.com/admin/machines).
