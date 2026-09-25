"""Tests for external access layer (Cloudflare Tunnel)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_parse_tunnel_url():
    from opencode_cloud.access import _parse_tunnel_url

    text = "INF | https://abc-def-123.trycloudflare.com |\n"
    assert _parse_tunnel_url(text) == "https://abc-def-123.trycloudflare.com"
    assert _parse_tunnel_url("no urls here") is None


def test_wait_for_port_timeout():
    from opencode_cloud.access import wait_for_port

    assert wait_for_port("127.0.0.1", 1, timeout=0.3) is False


def test_access_layer_opencode_not_listening():
    from opencode_cloud.access import AccessLayer

    layer = AccessLayer(port=59999)
    info = layer.start(wait_url_timeout=1.0)
    assert info.available is False
    assert info.status == "opencode_not_listening"
    assert info.opencode_listening is False


def test_access_layer_cloudflared_missing(monkeypatch):
    from opencode_cloud import access as access_mod
    from opencode_cloud.access import AccessLayer

    def boom(*a, **k):
        raise RuntimeError("no binary")

    monkeypatch.setattr(access_mod, "ensure_cloudflared", boom)
    monkeypatch.setattr(access_mod, "wait_for_port", lambda *a, **k: True)

    layer = AccessLayer(port=4096)
    info = layer.start(wait_url_timeout=1.0)
    assert info.available is False
    assert info.status == "cloudflared_unavailable"


def test_access_layer_stop_idempotent():
    from opencode_cloud.access import AccessLayer

    layer = AccessLayer(port=4096)
    layer.stop()


def test_access_info_to_dict_no_secrets():
    from opencode_cloud.access import AccessInfo

    info = AccessInfo(
        available=True,
        url="https://x.trycloudflare.com",
        authentication="opencode_basic_auth",
        provider="cloudflare_quick_tunnel",
        status="ready",
        message="ok",
        local_port=4096,
        opencode_listening=True,
    )
    d = info.to_dict()
    dumped = str(d).lower()
    assert "token" not in dumped
    assert d["url"].startswith("https://")


def test_no_shell_true_in_access():
    import re

    text = (Path(__file__).resolve().parents[1] / "src/opencode_cloud/access.py").read_text()
    assert not re.search(r"shell\s*=\s*True", text)
    assert "bash -c" not in text
    assert not re.search(r"curl[^\n]*\|\s*bash", text)
