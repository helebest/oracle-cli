"""SSH connection helpers using Fabric."""

from pathlib import Path

from fabric import Connection

from .config import get_vm_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_connection() -> Connection:
    """Create an SSH connection to the Oracle VM."""
    cfg = get_vm_config()
    key_path = PROJECT_ROOT / cfg["ssh_key"]
    return Connection(
        host=cfg["host"],
        user=cfg["user"],
        connect_kwargs={"key_filename": str(key_path)},
    )


def run_remote(cmd: str, hide: bool = False) -> str:
    """Run a command on the remote VM and return stdout."""
    with get_connection() as conn:
        result = conn.run(cmd, hide=hide)
        return result.stdout.strip()


def run_script(script_name: str) -> None:
    """Upload and execute a script from the scripts/ directory."""
    local_path = PROJECT_ROOT / "scripts" / script_name
    remote_path = f"/tmp/{script_name}"
    with get_connection() as conn:
        conn.put(str(local_path), remote_path)
        conn.run(f"chmod +x {remote_path}")
        conn.run(f"sudo bash {remote_path}", pty=True)
        conn.run(f"rm {remote_path}")


def upload_dir(local_dir: Path, remote_dir: str) -> None:
    """Upload a local directory to the remote VM."""
    with get_connection() as conn:
        conn.run(f"mkdir -p {remote_dir}")
        for f in local_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(local_dir)
                remote_file = f"{remote_dir}/{rel}"
                remote_parent = str(Path(remote_file).parent)
                conn.run(f"mkdir -p {remote_parent}")
                conn.put(str(f), remote_file)
