"""External access layer for OpenCode Web on ephemeral runtimes (Kaggle).

Kaggle does not expose arbitrary kernel ports to the public Internet.
This module uses Cloudflare Tunnel (cloudflared) to obtain a real HTTPS URL.

Modes:
  1. Named tunnel — CLOUDFLARE_TUNNEL_TOKEN from Kaggle Secrets (recommended)
  2. Quick tunnel — cloudflared tunnel --url http://127.0.0.1:PORT
     yields a random https://*.trycloudflare.com URL (changes each run)

Security:
  - OpenCode must be protected with OPENCODE_SERVER_PASSWORD (HTTP basic auth)
  - Tunnel token / password never written to Dataset or printed
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CLOUDFLARED_VERSION = "2025.2.1"
_URL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.(?:trycloudflare\.com|cfargotunnel\.com)[^\s]*")


@dataclass
class AccessInfo:
    available: bool
    url: Optional[str] = None
    authentication: str = "none"
    provider: str = "none"
    status: str = "unavailable"
    message: str = ""
    local_port: int = 4096
    opencode_listening: bool = False

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "url": self.url,
            "authentication": self.authentication,
            "provider": self.provider,
            "status": self.status,
            "message": self.message,
            "local_port": self.local_port,
            "opencode_listening": self.opencode_listening,
        }


def wait_for_port(host: str, port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def ensure_cloudflared(bin_dir: Optional[Path] = None) -> str:
    existing = shutil.which("cloudflared")
    if existing:
        return existing

    bin_dir = Path(bin_dir or Path.home() / ".local" / "bin")
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "cloudflared"
    if target.exists() and os.access(target, os.X_OK):
        return str(target)

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system != "linux":
        raise RuntimeError(f"cloudflared auto-install supports Linux only (got {system}).")
    arch = "arm64" if machine in ("aarch64", "arm64") else "amd64"
    if machine not in ("aarch64", "arm64", "x86_64", "amd64"):
        raise RuntimeError(f"Unsupported architecture: {machine}")

    url = (
        f"https://github.com/cloudflare/cloudflared/releases/download/"
        f"{CLOUDFLARED_VERSION}/cloudflared-linux-{arch}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "opencode-cloud-workstation/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        if getattr(resp, "status", 200) not in (200, 301, 302):
            raise RuntimeError(f"cloudflared download HTTP {getattr(resp, 'status', '?')}")
        data = resp.read()
    if len(data) < 1_000_000:
        raise RuntimeError("cloudflared download too small; refusing to install")

    fd, tmp_name = tempfile.mkstemp(prefix="cloudflared_", dir=str(bin_dir))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_bytes(data)
        tmp_path.chmod(0o755)
        tmp_path.replace(target)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    return str(target)


def _parse_tunnel_url(text: str) -> Optional[str]:
    matches = _URL_RE.findall(text)
    for m in matches:
        if "trycloudflare.com" in m or "cfargotunnel.com" in m:
            return m.rstrip(".,;)")
    return matches[0].rstrip(".,;)") if matches else None


class AccessLayer:
    def __init__(
        self,
        port: int = 4096,
        *,
        tunnel_token: Optional[str] = None,
        cloudflared_bin: Optional[str] = None,
        log_path: Optional[Path] = None,
    ):
        self.port = port
        self.tunnel_token = tunnel_token or ""
        self.cloudflared_bin = cloudflared_bin
        self.log_path = Path(log_path) if log_path else None
        self._proc: Optional[subprocess.Popen] = None
        self._url: Optional[str] = None
        self._stderr_buf: list[str] = []
        self._reader: Optional[threading.Thread] = None
        self.last_error: Optional[str] = None

    def start(self, *, wait_url_timeout: float = 45.0) -> AccessInfo:
        listening = wait_for_port("127.0.0.1", self.port, timeout=5.0)
        if not listening:
            return AccessInfo(
                available=False,
                status="opencode_not_listening",
                message=f"OpenCode is not accepting connections on 127.0.0.1:{self.port}",
                local_port=self.port,
                opencode_listening=False,
            )

        try:
            bin_path = self.cloudflared_bin or ensure_cloudflared()
        except Exception as e:
            self.last_error = type(e).__name__
            return AccessInfo(
                available=False,
                status="cloudflared_unavailable",
                message=f"Could not obtain cloudflared: {type(e).__name__}",
                local_port=self.port,
                opencode_listening=True,
            )

        if self.tunnel_token:
            cmd = [bin_path, "tunnel", "run", "--token", self.tunnel_token]
            provider = "cloudflare_named_tunnel"
        else:
            cmd = [bin_path, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"]
            provider = "cloudflare_quick_tunnel"

        log_handle = None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(self.log_path, "a", encoding="utf-8")

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except Exception as e:
            self.last_error = type(e).__name__
            if log_handle:
                log_handle.close()
            return AccessInfo(
                available=False,
                status="tunnel_start_failed",
                message=f"Failed to start cloudflared: {type(e).__name__}",
                local_port=self.port,
                opencode_listening=True,
                provider=provider,
            )

        self._stderr_buf = []
        self._reader = threading.Thread(target=self._consume_output, args=(log_handle,), daemon=True)
        self._reader.start()

        url = None
        deadline = time.time() + wait_url_timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                return AccessInfo(
                    available=False,
                    status="tunnel_exited",
                    message="cloudflared exited before URL was available",
                    local_port=self.port,
                    opencode_listening=True,
                    provider=provider,
                )
            url = _parse_tunnel_url("\n".join(self._stderr_buf[-50:]))
            if url:
                break
            time.sleep(0.4)

        self._url = url
        if self.tunnel_token and not url:
            return AccessInfo(
                available=True,
                url=None,
                status="named_tunnel_running",
                message=(
                    "Named Cloudflare tunnel is running. Configure the public hostname "
                    f"in Cloudflare Zero Trust to point at http://127.0.0.1:{self.port}."
                ),
                local_port=self.port,
                opencode_listening=True,
                provider=provider,
                authentication="opencode_basic_auth",
            )

        if not url:
            return AccessInfo(
                available=False,
                status="url_timeout",
                message="Timed out waiting for Cloudflare tunnel URL",
                local_port=self.port,
                opencode_listening=True,
                provider=provider,
            )

        return AccessInfo(
            available=True,
            url=url,
            status="ready",
            message="Open Cloudflare URL on your phone; use OpenCode basic auth from Secrets",
            local_port=self.port,
            opencode_listening=True,
            provider=provider,
            authentication="opencode_basic_auth",
        )

    def _consume_output(self, log_handle) -> None:
        assert self._proc is not None
        stream = self._proc.stdout
        if stream is None:
            return
        try:
            for line in stream:
                safe = line
                if "token" in line.lower() and len(line) > 40:
                    safe = "[redacted tunnel line]\n"
                self._stderr_buf.append(safe)
                if len(self._stderr_buf) > 200:
                    self._stderr_buf = self._stderr_buf[-100:]
                if log_handle:
                    log_handle.write(safe)
                    log_handle.flush()
        except Exception:
            pass
        finally:
            if log_handle:
                try:
                    log_handle.close()
                except Exception:
                    pass

    def stop(self, timeout: float = 5.0) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=3)
        except Exception:
            pass
        self._proc = None

    def status(self) -> dict:
        alive = self._proc is not None and self._proc.poll() is None
        return {
            "running": alive,
            "url": self._url,
            "pid": self._proc.pid if self._proc and alive else None,
        }
