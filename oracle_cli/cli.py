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
@click.option("--start", is_flag=True, help="Skip setup, just start the gateway (after setup is done)")
@click.option("--status", is_flag=True, help="Check build status")
def setup_hermes(start, status):
    """Deploy Hermes Agent (builds from source on ARM64)."""
    cfg = load_config()
    vm_cfg = get_vm_config()
    remote_dir = cfg["docker"]["compose_dir"] + "/hermes"
    local_dir = PROJECT_ROOT / "docker" / "hermes"
    key_path = vm_cfg["ssh_key"]
    host = vm_cfg["host"]
    user = vm_cfg["user"]

    if status:
        # Check build status
        with get_connection() as conn:
            building = conn.run("pgrep -f 'docker build.*hermes' > /dev/null 2>&1 && echo 'building' || echo 'done'", hide=True).stdout.strip()
            if building == "building":
                log = conn.run("tail -5 /tmp/hermes-build.log 2>/dev/null || echo 'no log'", hide=True).stdout.strip()
                console.print("[yellow]Build in progress...")
                console.print(log)
            else:
                exists = conn.run("docker images hermes-agent:local -q", hide=True).stdout.strip()
                if exists:
                    console.print("[green]Build complete! Image ready.")
                else:
                    log = conn.run("tail -10 /tmp/hermes-build.log 2>/dev/null || echo 'no log'", hide=True).stdout.strip()
                    console.print("[red]Build not running and image not found. Last log:")
                    console.print(log)
        return

    if start:
        # Upload compose config and start gateway
        console.rule("[bold blue]Hermes Agent")
        upload_dir(local_dir, remote_dir)
        with get_connection() as conn:
            conn.run(f"mkdir -p {remote_dir}/data")
            conn.run(f"cd {remote_dir} && docker compose up -d", pty=True)
        console.print("[green]Hermes Agent gateway started.")
        return

    # Default: clone repo (if needed) and start background build
    console.rule("[bold blue]Hermes Agent - ARM64 build")
    with get_connection() as conn:
        # Check if image already exists
        exists = conn.run("docker images hermes-agent:local -q", hide=True).stdout.strip()
        if exists:
            console.print("[green]Image already built!")
        else:
            # Check if already building
            building = conn.run("pgrep -f 'docker build.*hermes' > /dev/null 2>&1 && echo 'yes' || echo 'no'", hide=True).stdout.strip()
            if building == "yes":
                console.print("[yellow]Build already in progress.")
            else:
                # Clone if needed
                has_repo = conn.run("test -d /tmp/hermes-agent && echo yes || echo no", hide=True).stdout.strip()
                if has_repo != "yes":
                    console.print("Cloning repo...")
                    conn.run("git clone --depth 1 https://github.com/nousresearch/hermes-agent.git /tmp/hermes-agent", pty=True)
                # Start background build
                conn.run("nohup docker build -t hermes-agent:local /tmp/hermes-agent > /tmp/hermes-build.log 2>&1 &")
                console.print("[yellow]Build started in background on VM.")

        conn.run(f"mkdir -p {remote_dir}/data")

    upload_dir(local_dir, remote_dir)

    console.rule("[bold green]Next steps")
    console.print()
    console.print("1. Check build progress:")
    console.print("   [cyan]uv run oci-vm setup hermes --status[/]")
    console.print()
    console.print("2. After build completes, run interactive setup:")
    console.print(f"   [cyan]ssh -i {key_path} {user}@{host}[/]")
    console.print()
    console.print(f"   [cyan]docker run -it --rm \\")
    console.print(f"     -v {remote_dir}/data:/opt/data \\")
    console.print(f"     hermes-agent:local setup[/]")
    console.print()
    console.print("3. Start the gateway:")
    console.print("   [cyan]uv run oci-vm setup hermes --start[/]")


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
