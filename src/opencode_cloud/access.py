"""Access layer for OpenCode Web inside Kaggle (and local testing).

Primary mechanism (Kaggle native):
  jupyter_server.serverapp.list_running_servers() → base_url
  → https://kkb-production.jupyter-proxy.kaggle.net/k/<kernel>/<token>/proxy/proxy/<PORT>

Pattern used by official Kaggle Agents course notebooks (ADK web UI).
JWT/token in the path is ephemeral — never write to Dataset/Git/checkpoints;
redact in logs.
"""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Optional

from .ports import DEFAULT_OPENCODE_PORT, get_opencode_port

KAGGLE_JUPYTER_PROXY_HOST = "https://kkb-production.jupyter-proxy.kaggle.net"

_JWT_LIKE = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]*\.[A-Za-z0-9_\-]*")
_TOKEN_SEGMENT = re.compile(r"/k/(\d+)/([^/]+)/")


@dataclass
class AccessInfo:
    available: bool
    url: Optional[str] = None
    authentication: str = "jupyter_session"
    provider: str = "none"
    status: str = "unavailable"
    message: str = ""
    local_port: int = DEFAULT_OPENCODE_PORT
    opencode_listening: bool = False
    url_redacted: Optional[str] = None

    def to_dict(self, *, include_url: bool = True) -> dict:
        d = {
            "available": self.available,
            "authentication": self.authentication,
            "provider": self.provider,
            "status": self.status,
            "message": self.message,
            "local_port": self.local_port,
            "opencode_listening": self.opencode_listening,
            "url_redacted": self.url_redacted or redact_proxy_url(self.url),
        }
        if include_url:
            d["url"] = self.url
        return d


def redact_proxy_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    redacted = _JWT_LIKE.sub("<REDACTED_JWT>", url)
    redacted = _TOKEN_SEGMENT.sub(r"/k/\1/<REDACTED>/", redacted)
    return redacted


def wait_for_port(host: str, port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def list_jupyter_servers() -> list[dict[str, Any]]:
    try:
        from jupyter_server.serverapp import list_running_servers  # type: ignore

        return list(list_running_servers())
    except Exception:
        try:
            from notebook.notebookapp import list_running_servers  # type: ignore

            return list(list_running_servers())
        except Exception:
            return []


def parse_kernel_token_from_base_url(base_url: str) -> tuple[Optional[str], Optional[str]]:
    if not base_url:
        return None, None
    parts = [p for p in base_url.strip("/").split("/") if p]
    if len(parts) >= 3 and parts[0] == "k":
        return parts[1], parts[2]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, None


def build_kaggle_proxy_url(
    *,
    kernel: str,
    token: str,
    port: int,
    proxy_host: str = KAGGLE_JUPYTER_PROXY_HOST,
) -> str:
    host = proxy_host.rstrip("/")
    return f"{host}/k/{kernel}/{token}/proxy/proxy/{int(port)}"


class KaggleProxyAccess:
    """Native Kaggle Jupyter Proxy access detector (no external tunnel)."""

    def __init__(
        self,
        port: Optional[int] = None,
        *,
        proxy_host: str = KAGGLE_JUPYTER_PROXY_HOST,
        servers_fn=None,
    ):
        self.port = int(port if port is not None else get_opencode_port())
        self.proxy_host = proxy_host
        self._servers_fn = servers_fn or list_jupyter_servers

    def resolve(self) -> AccessInfo:
        listening = wait_for_port("127.0.0.1", self.port, timeout=5.0)
        if not listening:
            return AccessInfo(
                available=False,
                status="opencode_not_listening",
                message=f"Nothing is listening on 127.0.0.1:{self.port}",
                local_port=self.port,
                opencode_listening=False,
                provider="kaggle_jupyter_proxy",
            )

        servers = self._servers_fn()
        if not servers:
            return AccessInfo(
                available=False,
                status="jupyter_server_not_found",
                message=(
                    "No running Jupyter server found via list_running_servers(). "
                    "Kaggle proxy URL cannot be built outside a notebook runtime."
                ),
                local_port=self.port,
                opencode_listening=True,
                provider="kaggle_jupyter_proxy",
            )

        base_url = str(servers[0].get("base_url") or "")
        kernel, token = parse_kernel_token_from_base_url(base_url)
        if not kernel or not token:
            return AccessInfo(
                available=False,
                status="base_url_unparseable",
                message="Could not parse kernel/token from Jupyter base_url",
                local_port=self.port,
                opencode_listening=True,
                provider="kaggle_jupyter_proxy",
            )

        url = build_kaggle_proxy_url(
            kernel=kernel,
            token=token,
            port=self.port,
            proxy_host=self.proxy_host,
        )
        return AccessInfo(
            available=True,
            url=url,
            url_redacted=redact_proxy_url(url),
            status="ready",
            message=(
                "Kaggle Jupyter Proxy URL built from running server base_url. "
                "Open it while this Kaggle session is active. URL is ephemeral."
            ),
            local_port=self.port,
            opencode_listening=True,
            provider="kaggle_jupyter_proxy",
            authentication="jupyter_session",
        )


def resolve_web_access(
    port: Optional[int] = None,
    *,
    prefer_kaggle_proxy: bool = True,
    allow_cloudflare_fallback: bool = False,
    tunnel_token: Optional[str] = None,
) -> AccessInfo:
    port = int(port if port is not None else get_opencode_port())
    if prefer_kaggle_proxy:
        info = KaggleProxyAccess(port).resolve()
        if info.available or not allow_cloudflare_fallback:
            return info
    if allow_cloudflare_fallback:
        try:
            from .access_cloudflare import CloudflareAccessLayer

            return CloudflareAccessLayer(port, tunnel_token=tunnel_token).start()
        except Exception as e:
            return AccessInfo(
                available=False,
                status="fallback_failed",
                message=f"Proxy unavailable and Cloudflare fallback failed: {type(e).__name__}",
                local_port=port,
                provider="none",
            )
    return AccessInfo(
        available=False,
        status="access_unavailable",
        message="No access provider succeeded",
        local_port=port,
    )


def format_workstation_banner(
    *,
    recovery: str,
    opencode_status: str,
    access: AccessInfo,
) -> str:
    lines = [
        "========================================",
        "OpenCode Workstation",
        "========================================",
        f"Workspace: {recovery}",
        f"OpenCode: {opencode_status}",
    ]
    if access.available and access.url:
        lines.append("OpenCode Web: ACCESSIBLE")
        lines.append("Abrí esta URL desde tu teléfono:")
        lines.append(access.url)
        lines.append("Importante: esta URL pertenece al runtime actual.")
        lines.append("Si el runtime se reinicia, se generará una nueva URL.")
    elif access.opencode_listening:
        lines.append("OpenCode Web: NOT_ACCESSIBLE")
        lines.append("OpenCode está corriendo dentro del runtime,")
        lines.append("pero no se pudo construir la URL del proxy Kaggle.")
        lines.append(f"Motivo: {access.status}")
    else:
        lines.append("OpenCode Web: NOT_RUNNING")
        lines.append(f"Motivo: {access.status}")
    lines.append("========================================")
    return "\n".join(lines)
