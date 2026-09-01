import subprocess
from pathlib import Path

def setup_repo(workspace: Path, github_repo: str = "", github_token: str = "", credential_file: Path | None = None):
    workspace.mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(workspace)
    if not (workspace / ".git").exists():
        subprocess.run("git init", shell=True, check=False)
        subprocess.run("git checkout -B main", shell=True, check=False)
    subprocess.run('git config user.name "OpenCode Colab"', shell=True, check=False)
    subprocess.run('git config user.email "opencode-colab@localhost"', shell=True, check=False)
    if github_repo:
        subprocess.run("git remote remove origin", shell=True, check=False)
        # TODO v5: sanitizar github_repo y usar shell=False
        subprocess.run(f"git remote add origin '{github_repo}'", shell=True, check=False)
    if github_token and credential_file:
        credential_file.write_text(f"https://x-access-token:{github_token}@github.com\n", encoding="utf-8")
        try:
            import os as _os; _os.chmod(credential_file, 0o600)
        except Exception:
            pass
        subprocess.run(f"git config credential.helper 'store --file={credential_file}'", shell=True, check=False)
