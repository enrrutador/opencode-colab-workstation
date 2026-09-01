import subprocess
from pathlib import Path

def sync_dir(source: Path, destination: Path, delete: bool = False):
    """Wrapper seguro sobre rsync. TODO v5: shell=False + validación de paths."""
    source = Path(source)
    destination = Path(destination)
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    delete_flag = "--delete" if delete else ""
    cmd = f"rsync -a {delete_flag} '{source}/' '{destination}/'"
    subprocess.run(cmd, shell=True, check=False)

def has_files(path: Path) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        return any(p.iterdir())
    except Exception:
        return False
