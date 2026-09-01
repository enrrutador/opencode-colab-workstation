from pathlib import Path
import subprocess

def is_mounted(path: Path) -> bool:
    result = subprocess.run("mount", shell=True, text=True, capture_output=True)
    return str(path) in result.stdout if result.returncode == 0 else False

def detect_and_mount(mount_candidates=None):
    """Refactor de sección 2. GOOGLE DRIVE del monolito.
    Detecta montaje existente o monta en /content/drive.
    Retorna Path al mount point.
    """
    from google.colab import drive
    if mount_candidates is None:
        mount_candidates = [Path("/content/drive"), Path("/content/gdrive")]
    for c in mount_candidates:
        if is_mounted(c):
            return c
    target = Path("/content/drive")
    target.mkdir(parents=True, exist_ok=True)
    drive.mount(str(target), force_remount=False)
    return target
