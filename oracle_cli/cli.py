"""CLI entry point for oracle-cli."""

import sys
from pathlib import Path

# Fix Windows GBK encoding issues with Docker/SSH output
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import click
from rich.console import Console
from rich.table import Table

from .config import get_vm_config, load_config
from .oci_api import (
    get_instance_details,
    get_metrics,
    get_network_info,
    get_public_ip,
    get_security_rules,
    instance_action,
)
from .ssh import PROJECT_ROOT, get_connection, run_remote, run_script, upload_dir

console = Console()


@click.group()
def cli():
    """Manage Oracle Cloud VM instance."""


@cli.command()
def info():
    """Show VM configuration."""
    cfg = get_vm_config()
    table = Table(title="Oracle VM Instance")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Host", cfg["host"])
    table.add_row("User", cfg["user"])
    table.add_row("Shape", cfg["shape"])
    table.add_row("OCPUs", str(cfg["ocpu"]))
    table.add_row("Memory", f"{cfg['memory_gb']} GB")
    console.print(table)


@cli.command()
def status():
    """Check VM status (uptime, load, memory, disk, docker)."""
    with console.status("Connecting..."):
        with get_connection() as conn:
            uptime = conn.run("uptime -p", hide=True).stdout.strip()
            load = conn.run("cat /proc/loadavg", hide=True).stdout.strip()
            mem = conn.run("free -h | grep Mem", hide=True).stdout.strip()
            disk = conn.run("df -h / | tail -1", hide=True).stdout.strip()
            swap = conn.run("free -h | grep Swap", hide=True).stdout.strip()
            docker_ok = conn.run("docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'not installed'", hide=True).stdout.strip()
            containers = conn.run("docker ps -q 2>/dev/null | wc -l || echo 0", hide=True).stdout.strip()

    table = Table(title="VM Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Uptime", uptime)
    table.add_row("Load Avg", load)

    mem_parts = mem.split()
    table.add_row("Memory", f"{mem_parts[2]} used / {mem_parts[1]} total")

    swap_parts = swap.split()
    table.add_row("Swap", f"{swap_parts[2]} used / {swap_parts[1]} total" if swap_parts[1] != "0B" else "disabled")

    disk_parts = disk.split()
    table.add_row("Disk", f"{disk_parts[2]} used / {disk_parts[1]} total ({disk_parts[4]})")

    table.add_row("Docker", docker_ok)
    table.add_row("Containers", f"{containers} running")

    console.print(table)


@cli.command(name="run")
@click.argument("cmd")
def run_cmd(cmd):
    """Run a command on the remote VM."""
    output = run_remote(cmd)
    console.print(output)


@cli.command()
def ssh():
    """Print the SSH command to connect manually."""
    cfg = get_vm_config()
    key_path = cfg["ssh_key"]
    console.print(f"ssh -i {key_path} {cfg['user']}@{cfg['host']}")


# --- Setup commands ---

@cli.group()
def setup():
    """Setup VM infrastructure (run once)."""


@setup.command(name="all")
def setup_all():
    """Run all setup scripts in order."""
    steps = [
        ("setup-base.sh", "Base environment"),
        ("setup-docker.sh", "Docker CE"),
        ("setup-firewall.sh", "Firewall"),
        ("setup-security.sh", "Security hardening"),
    ]
    for script, desc in steps:
        console.rule(f"[bold blue]{desc}")
        run_script(script)
        console.print(f"[green]{desc} complete.")

    # Deploy Caddy
    console.rule("[bold blue]Caddy reverse proxy")
    cfg = load_config()
    remote_dir = cfg["docker"]["compose_dir"] + "/caddy"
    local_dir = PROJECT_ROOT / "docker" / "caddy"
    upload_dir(local_dir, remote_dir)
    with get_connection() as conn:
        conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)
    console.print("[green]Caddy deployed.")

    console.rule("[bold green]Setup complete!")


@setup.command(name="base")
def setup_base():
    """Run base environment setup only."""
    run_script("setup-base.sh")


@setup.command(name="docker")
def setup_docker():
    """Install Docker CE only."""
    run_script("setup-docker.sh")


@setup.command(name="firewall")
def setup_firewall():
    """Configure firewall rules only."""
    run_script("setup-firewall.sh")


@setup.command(name="security")
def setup_security():
    """Apply security hardening only."""
    run_script("setup-security.sh")


@setup.command(name="caddy")
def setup_caddy():
    """Deploy Caddy reverse proxy only."""
    cfg = load_config()
    domain = cfg.get("domain")
    if not domain:
        console.print("[red]Error: 'domain' not set in config.yaml")
        raise SystemExit(1)
    remote_dir = cfg["docker"]["compose_dir"] + "/caddy"
    local_dir = PROJECT_ROOT / "docker" / "caddy"
    upload_dir(local_dir, remote_dir)
    with get_connection() as conn:
        conn.run(f"echo 'DOMAIN={domain}' > {remote_dir}/.env", pty=True)
        conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)
    console.print("[green]Caddy deployed.")
    console.print(f"[bold]3x-ui panel: [cyan]https://3x-panel.{domain}[/]")


@setup.command(name="xray")
def setup_xray():
    """Deploy 3x-ui (Xray proxy panel)."""
    cfg = load_config()
    vm_cfg = get_vm_config()
    host = vm_cfg["host"]

    console.print("[bold yellow]Before deploying, ensure Oracle Cloud Security List has these Ingress Rules:")
    console.print("  - TCP 443  (VLESS+Reality)")
    console.print("  - TCP 2053 (3x-ui panel)")
    console.print()

    # 1. Open iptables port
    console.rule("[bold blue]Firewall")
    run_script("setup-xray-firewall.sh")

    # 2. Upload and start 3x-ui
    console.rule("[bold blue]3x-ui deployment")
    remote_dir = cfg["docker"]["compose_dir"] + "/3x-ui"
    local_dir = PROJECT_ROOT / "docker" / "3x-ui"
    upload_dir(local_dir, remote_dir)
    with get_connection() as conn:
        conn.run(f"cd {remote_dir} && docker compose pull", pty=True)
        conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)

    # 3. Print setup guide
    console.rule("[bold green]Deployment complete!")
    console.print()
    domain = cfg.get("domain")
    console.print(f"[bold]3x-ui panel: [cyan]http://{host}:2053[/]")
    if domain:
        console.print(f"[bold]3x-ui panel (Caddy): [cyan]https://3x-panel.{domain}[/]")
    console.print(f"[bold]Default login: [yellow]admin / admin[/] (change immediately!)")
    console.print()
    console.print("[bold]Next steps:")
    console.print("  1. Login and change password")
    console.print("  2. Inbounds > Add Inbound:")
    console.print("     - Protocol: VLESS")
    console.print("     - Port: 443")
    console.print("     - Security: Reality")
    console.print("     - SNI: www.google.com or www.microsoft.com")
    console.print("  3. Add client, scan QR code with:")
    console.print("     - Android: v2rayNG")
    console.print("     - iOS: Shadowrocket")
    console.print("     - Windows: v2rayN")


@setup.command(name="hermes")
@click.option("--start", is_flag=True, help="Start/restart the gateway without rebuilding")
@click.option("--status", is_flag=True, help="Check container status")
def setup_hermes(start, status):
    """Deploy Hermes Agent (uses official multi-arch image from Docker Hub)."""
    cfg = load_config()
    vm_cfg = get_vm_config()
    remote_dir = cfg["docker"]["compose_dir"] + "/hermes"
    local_dir = PROJECT_ROOT / "docker" / "hermes"
    key_path = vm_cfg["ssh_key"]
    host = vm_cfg["host"]
    user = vm_cfg["user"]

    if status:
        with get_connection() as conn:
            result = conn.run(
                "docker ps -a --filter name=hermes --format '{{.Status}}'",
                hide=True,
            ).stdout.strip()
            if result:
                console.print(f"[green]hermes: {result}")
            else:
                console.print("[yellow]hermes container not found.")
        return

    if start:
        console.rule("[bold blue]Hermes Agent")
        upload_dir(local_dir, remote_dir)
        with get_connection() as conn:
            conn.run(f"mkdir -p {remote_dir}/data")
            conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)
        console.print("[green]Hermes Agent gateway started.")
        return

    # Default: pull official image, build custom layer, deploy
    console.rule("[bold blue]Hermes Agent")
    upload_dir(local_dir, remote_dir)
    with get_connection() as conn:
        conn.run(f"mkdir -p {remote_dir}/data")
        # Write empty .env if not exists (hermes reads its own config from /opt/data)
        conn.run(f"test -f {remote_dir}/.env || touch {remote_dir}/.env", hide=True)
        console.print("Pulling image & building...")
        conn.run(f"cd {remote_dir} && docker compose build --pull", pty=True)
        # Check if interactive setup has been done (data dir is root-owned)
        has_config = conn.run(
            f"sudo test -f {remote_dir}/data/config.yaml && echo yes || echo no",
            hide=True,
        ).stdout.strip()
        if has_config != "yes":
            console.rule("[bold yellow]First-time setup required")
            console.print()
            console.print("Run interactive setup via SSH:")
            console.print(f"  [cyan]ssh -i {key_path} {user}@{host}[/]")
            console.print()
            console.print(f"  [cyan]docker run -it --rm \\")
            console.print(f"    -v {remote_dir}/data:/opt/data \\")
            console.print(f"    hermes-agent:custom setup[/]")
            console.print()
            console.print("Then start the gateway:")
            console.print("  [cyan]uv run oci-vm setup hermes --start[/]")
        else:
            conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)
            console.print("[green]Hermes Agent deployed.")


@setup.command(name="keepalive")
@click.option("--status", is_flag=True, help="Show keepalive container status + memory + recent logs")
@click.option("--remove", is_flag=True, help="Stop and remove keepalive container + image")
def setup_keepalive(status, remove):
    """Deploy keepalive container (anti-reclaim + health monitoring)."""
    cfg = load_config()
    remote_dir = cfg["docker"]["compose_dir"] + "/keepalive"
    local_dir = PROJECT_ROOT / "docker" / "keepalive"

    if status:
        with get_connection() as conn:
            conn.run(
                "docker ps -a --filter name=keepalive --format 'STATUS: {{.Status}}'",
                pty=True,
            )
            conn.run(
                "docker stats --no-stream "
                "--format 'table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}' "
                "keepalive 2>/dev/null || true",
                pty=True,
            )
            conn.run("docker logs --tail 30 keepalive 2>&1 || true", pty=True)
        return

    if remove:
        with get_connection() as conn:
            conn.run("docker rm -f keepalive 2>/dev/null || true", pty=True)
            conn.run("docker rmi keepalive:local 2>/dev/null || true", pty=True)
        console.print("[green]Keepalive removed.")
        return

    console.rule("[bold blue]Keepalive deployment")

    # Stop and remove old keepalive container if exists
    with get_connection() as conn:
        conn.run("docker rm -f keepalive 2>/dev/null || true", hide=True)

    upload_dir(local_dir, remote_dir)
    with get_connection() as conn:
        console.print("Building keepalive image...")
        conn.run(f"cd {remote_dir} && docker compose build", pty=True)
        conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)

    console.rule("[bold green]Keepalive deployed!")
    console.print()
    console.print("[bold]Features:")
    console.print("  - CPU burst: UTC+8 03:00-04:00 (anti-reclaim)")
    console.print("  - Health check: every 5 min (3x-ui, hermes, caddy)")
    console.print("  - Zombie cleanup: every 30 min")
    console.print("  - Disk monitor: every hour (auto prune > 80%)")
    console.print()
    console.print("View logs: [cyan]uv run oci-vm docker logs keepalive[/]")


@setup.command(name="tailscale")
@click.option("--status", is_flag=True, help="Show tailscale status + netcheck")
@click.option("--down", is_flag=True, help="Disconnect from tailnet (keep installed)")
@click.option("--remove", is_flag=True, help="Full uninstall")
def setup_tailscale(status, down, remove):
    """Install Tailscale and join the tailnet (native, not Docker)."""
    cfg = load_config()
    ts = cfg.get("tailscale") or {}

    if status:
        with get_connection() as conn:
            conn.run("tailscale status || true", pty=True)
            conn.run("tailscale netcheck 2>&1 | tail -20 || true", pty=True)
        return

    if down:
        with get_connection() as conn:
            conn.run("sudo tailscale down", pty=True)
        return

    if remove:
        with get_connection() as conn:
            conn.run("sudo tailscale down 2>/dev/null || true", pty=True)
            conn.run("sudo apt-get remove --purge -y tailscale", pty=True)
            conn.run("sudo rm -f /etc/sysctl.d/99-tailscale.conf", pty=True)
            conn.run("sudo sysctl --system >/dev/null", pty=True)
        console.print("[green]Tailscale removed.")
        return

    routes = ",".join(ts.get("advertise_routes") or [])
    exit_node = "true" if ts.get("advertise_exit_node") else "false"
    hostname = ts.get("hostname") or cfg["vm"]["name"]

    # Auth key is optional. If set and present locally, upload it;
    # otherwise `tailscale up` will print a login URL for browser approval.
    authkey_rel = ts.get("auth_key_file")
    has_authkey = bool(authkey_rel and (PROJECT_ROOT / authkey_rel).exists())

    console.rule("[bold blue]Tailscale deployment")
    with get_connection() as conn:
        env_parts = [
            f"TS_HOSTNAME={hostname}",
            f"TS_ROUTES={routes}",
            f"TS_EXIT_NODE={exit_node}",
        ]
        if has_authkey:
            conn.put(str(PROJECT_ROOT / authkey_rel), "/tmp/ts-authkey")
            conn.run("chmod 600 /tmp/ts-authkey")
            env_parts.append("TS_AUTHKEY_FILE=/tmp/ts-authkey")
        else:
            console.print(
                "[yellow]No auth key configured — watch the output for a "
                "[bold]login URL[/], open it in any browser to approve the device."
            )

        conn.put(
            str(PROJECT_ROOT / "scripts" / "setup-tailscale.sh"),
            "/tmp/setup-tailscale.sh",
        )
        conn.run("chmod +x /tmp/setup-tailscale.sh && sed -i 's/\\r$//' /tmp/setup-tailscale.sh")
        env = " ".join(env_parts)
        conn.run(f"sudo {env} bash /tmp/setup-tailscale.sh", pty=True)

    console.rule("[bold green]Tailscale deployed!")
    if routes or exit_node == "true":
        console.print()
        console.print("[yellow]advertise_routes / exit_node enabled — approve in admin panel:")
        console.print("  https://login.tailscale.com/admin/machines")


@setup.command(name="obsidian-sync")
@click.option("--sync-now", is_flag=True, help="Trigger an immediate bisync")
@click.option("--status", is_flag=True, help="Show container status + recent bisync log")
@click.option("--reset", is_flag=True, help="Re-establish bisync baseline (dangerous)")
def setup_obsidian_sync(sync_now, status, reset):
    """Deploy obsidian-sync: bidirectional R2 <-> Hermes vault."""
    cfg = load_config()
    remote_dir = cfg["docker"]["compose_dir"] + "/obsidian-sync"
    local_dir = PROJECT_ROOT / "docker" / "obsidian-sync"

    if status:
        with get_connection() as conn:
            conn.run(
                "docker ps -a --filter name=obsidian-sync --format 'STATUS: {{.Status}}'",
                pty=True,
            )
            conn.run("docker logs --tail 30 obsidian-sync 2>&1 || true", pty=True)
            conn.run(
                "docker exec obsidian-sync du -sh /vault 2>/dev/null || echo 'vault not ready'",
                pty=True,
            )
            conn.run(
                "docker exec obsidian-sync stat -c 'vault owner: %U:%G (%u:%g)' /vault "
                "2>/dev/null || true",
                pty=True,
            )
        return

    if sync_now:
        with get_connection() as conn:
            conn.run(
                "docker exec obsidian-sync rclone bisync r2-crypt: /vault "
                "--workdir /bisync-state --conflict-resolve newer --max-delete 5 "
                "--log-level INFO",
                pty=True,
            )
        return

    if reset:
        console.print("[red]Reset clears bisync state. Next run will do --resync.")
        if not click.confirm("Continue?"):
            return
        with get_connection() as conn:
            conn.run(
                "docker exec obsidian-sync rm -f /bisync-state/.initialized",
                pty=True,
            )
            conn.run("docker restart obsidian-sync", pty=True)
        return

    local_rclone = local_dir / "rclone.conf"
    if not local_rclone.exists():
        console.print(
            "[red]Missing docker/obsidian-sync/rclone.conf. "
            "Copy rclone.conf.example, fill in R2 creds + crypt passwords, then re-run."
        )
        return

    console.rule("[bold blue]Obsidian Sync deployment")
    upload_dir(local_dir, remote_dir)
    with get_connection() as conn:
        conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)

    console.rule("[bold green]Deployed!")
    console.print("First run does --resync to establish the bisync baseline.")
    console.print("Monitor: [cyan]uv run oci-vm setup obsidian-sync --status[/]")


# --- Docker management commands ---

@cli.group(name="docker")
def docker_group():
    """Manage Docker containers on the VM."""


@docker_group.command(name="ps")
@click.option("-a", "--all", "show_all", is_flag=True, help="Show all containers")
def docker_ps(show_all):
    """List running containers."""
    flag = "-a" if show_all else ""
    output = run_remote(f"docker ps {flag} --format 'table {{{{.Names}}}}\\t{{{{.Image}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}'", hide=True)
    console.print(output)


@docker_group.command(name="logs")
@click.argument("name")
@click.option("-n", "--tail", default=50, help="Number of lines")
def docker_logs(name, tail):
    """View container logs."""
    output = run_remote(f"docker logs --tail {tail} {name}", hide=True)
    console.print(output)


@docker_group.command(name="stats")
def docker_stats():
    """Show container resource usage."""
    output = run_remote("docker stats --no-stream --format 'table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.NetIO}}'", hide=True)
    console.print(output)


# --- Ports command ---

@cli.command()
def ports():
    """List open ports on the VM."""
    output = run_remote("sudo ss -tlnp | grep LISTEN", hide=True)
    table = Table(title="Listening Ports")
    table.add_column("Proto", style="cyan")
    table.add_column("Address", style="green")
    table.add_column("Port", style="yellow")
    table.add_column("Process", style="white")

    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 5:
            addr_port = parts[3]
            process = parts[5] if len(parts) > 5 else ""
            if ":" in addr_port:
                addr, port = addr_port.rsplit(":", 1)
                table.add_row("tcp", addr, port, process)
    console.print(table)


# --- Deploy command ---

@cli.command()
@click.argument("compose_file", type=click.Path(exists=True))
@click.option("--name", required=True, help="Service name (used as remote directory name)")
def deploy(compose_file, name):
    """Deploy a docker-compose file to the VM."""
    cfg = load_config()
    remote_dir = cfg["docker"]["compose_dir"] + f"/{name}"
    local_path = Path(compose_file).resolve()
    local_dir = local_path.parent

    console.print(f"Deploying [cyan]{name}[/] to {remote_dir}...")
    upload_dir(local_dir, remote_dir)
    with get_connection() as conn:
        conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)
    console.print(f"[green]{name} deployed successfully.")


# --- Cloud (OCI control plane) commands ---

@cli.group()
def cloud():
    """Manage OCI cloud infrastructure (no SSH required)."""


@cloud.command(name="info")
def cloud_info():
    """Show instance details from OCI API."""
    with console.status("Querying OCI API..."):
        try:
            details = get_instance_details()
        except Exception as e:
            console.print(f"[red]OCI API error: {e}")
            raise SystemExit(1)

    state = details["lifecycle_state"]
    state_colors = {"RUNNING": "green", "STOPPED": "red", "STOPPING": "yellow", "STARTING": "yellow"}
    state_style = state_colors.get(state, "white")

    table = Table(title="OCI Instance")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Name", details["display_name"])
    table.add_row("State", f"[{state_style}]{state}[/{state_style}]")
    table.add_row("Shape", details["shape"])
    table.add_row("OCPUs", str(details["ocpus"]))
    table.add_row("Memory", f"{details['memory_gb']} GB")
    table.add_row("Bandwidth", f"{details['bandwidth_gbps']} Gbps")
    table.add_row("AD", details["availability_domain"])
    table.add_row("Fault Domain", details["fault_domain"])
    table.add_row("Created", str(details["time_created"]))
    console.print(table)


@cloud.command(name="start")
def cloud_start():
    """Start the instance."""
    with console.status("Starting instance..."):
        try:
            new_state = instance_action("START")
        except Exception as e:
            console.print(f"[red]OCI API error: {e}")
            raise SystemExit(1)
    console.print(f"[green]Instance state: {new_state}")


@cloud.command(name="stop")
@click.option("--force", is_flag=True, help="Force stop instead of graceful stop")
def cloud_stop(force):
    """Stop the instance (graceful by default)."""
    action = "STOP" if force else "SOFTSTOP"
    with console.status("Stopping instance..."):
        try:
            new_state = instance_action(action)
        except Exception as e:
            console.print(f"[red]OCI API error: {e}")
            raise SystemExit(1)
    console.print(f"[yellow]Instance state: {new_state}")


@cloud.command(name="reboot")
@click.option("--force", is_flag=True, help="Hard reset instead of graceful reboot")
def cloud_reboot(force):
    """Reboot the instance (graceful by default)."""
    action = "RESET" if force else "SOFTRESET"
    with console.status("Rebooting instance..."):
        try:
            new_state = instance_action(action)
        except Exception as e:
            console.print(f"[red]OCI API error: {e}")
            raise SystemExit(1)
    console.print(f"[yellow]Instance state: {new_state}")


@cloud.command(name="ip")
def cloud_ip():
    """Show the instance's public IP address."""
    with console.status("Querying OCI API..."):
        try:
            ip = get_public_ip()
        except Exception as e:
            console.print(f"[red]OCI API error: {e}")
            raise SystemExit(1)
    if ip:
        console.print(f"[green]{ip}")
    else:
        console.print("[yellow]No public IP found")


@cloud.command(name="network")
def cloud_network():
    """Show VCN, subnet, and IP information."""
    with console.status("Querying OCI API..."):
        try:
            net = get_network_info()
        except Exception as e:
            console.print(f"[red]OCI API error: {e}")
            raise SystemExit(1)

    table = Table(title="OCI Network")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("VCN", net.get("vcn_name", "N/A"))
    table.add_row("VCN CIDR", net.get("vcn_cidr", "N/A"))
    table.add_row("Subnet", net.get("subnet_name", "N/A"))
    table.add_row("Subnet CIDR", net.get("subnet_cidr", "N/A"))
    table.add_row("Public IP", net.get("public_ip", "N/A"))
    table.add_row("Private IP", net.get("private_ip", "N/A"))
    console.print(table)


SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo or 1.0
    return "".join(
        SPARK_BLOCKS[int((v - lo) / span * (len(SPARK_BLOCKS) - 1))]
        for v in values
    )


@cloud.command(name="metrics")
@click.option("--hours", type=int, default=24, show_default=True, help="Window size in hours")
def cloud_metrics(hours):
    """Show VM load metrics from OCI Monitoring (CPU, Mem, Load, Net, Disk)."""
    with console.status(f"Querying OCI Monitoring for past {hours}h..."):
        try:
            series = get_metrics(hours)
        except Exception as e:
            console.print(f"[red]OCI API error: {e}")
            raise SystemExit(1)

    if not series:
        console.print("[yellow]No metric data returned")
        return

    window_start = series[0].get("window_start")
    window_end = series[0].get("window_end")
    interval = series[0].get("interval", "?")
    console.rule(f"[bold blue]VM metrics: past {hours}h ({interval} buckets)")
    if window_start and window_end:
        console.print(f"[dim]{window_start.isoformat()} → {window_end.isoformat()}[/]\n")

    table = Table(show_lines=False)
    table.add_column("Metric")
    table.add_column("Min", justify="right")
    table.add_column("Avg", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Pts", justify="right")
    table.add_column("Trend", overflow="fold")

    for s in series:
        label, fmt = s["label"], s["fmt"]
        if "error" in s:
            table.add_row(label, f"[red]{s['error']}[/]", "", "", "", "0", "")
            continue
        if s["avg"] is None:
            table.add_row(label, "-", "-", "-", "-", "0", "")
            continue

        total_str = f"{s['total_gb']:6.2f} GB" if s["total_gb"] is not None else "-"
        table.add_row(
            label,
            fmt.format(s["min"]),
            fmt.format(s["avg"]),
            fmt.format(s["max"]),
            total_str,
            str(s["points"]),
            _sparkline(s["values"]),
        )

    console.print(table)


@cloud.command(name="security")
def cloud_security():
    """List OCI security list ingress rules."""
    with console.status("Querying OCI API..."):
        try:
            rules = get_security_rules()
        except Exception as e:
            console.print(f"[red]OCI API error: {e}")
            raise SystemExit(1)

    table = Table(title="Security List Ingress Rules")
    table.add_column("Source", style="cyan")
    table.add_column("Protocol", style="yellow")
    table.add_column("Port", style="green")
    table.add_column("Description", style="white")
    for rule in rules:
        table.add_row(rule["source"], rule["protocol"], rule["port_range"] or "all", rule["description"])
    console.print(table)
