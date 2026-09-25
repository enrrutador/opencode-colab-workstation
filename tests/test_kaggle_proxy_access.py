"""Unit tests for native Kaggle Jupyter Proxy access."""

from __future__ import annotations

from opencode_cloud.access import (
    KaggleProxyAccess,
    build_kaggle_proxy_url,
    format_workstation_banner,
    parse_kernel_token_from_base_url,
    redact_proxy_url,
)


def test_parse_kernel_token():
    k, t = parse_kernel_token_from_base_url("/k/12345/eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4.abc/")
    assert k == "12345"
    assert t.startswith("eyJ")


def test_parse_empty():
    assert parse_kernel_token_from_base_url("") == (None, None)


def test_build_url():
    url = build_kaggle_proxy_url(kernel="99", token="tok", port=4096)
    assert url == "https://kkb-production.jupyter-proxy.kaggle.net/k/99/tok/proxy/proxy/4096"


def test_redact_url():
    url = "https://kkb-production.jupyter-proxy.kaggle.net/k/1/eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4Q0JD.xxx.yyy/proxy/proxy/4096"
    r = redact_proxy_url(url)
    assert r is not None
    assert "REDACTED" in r
    assert "4096" in r


def test_resolve_no_jupyter(monkeypatch):
    from opencode_cloud import access as m

    monkeypatch.setattr(m, "wait_for_port", lambda *a, **k: True)
    info = KaggleProxyAccess(4096, servers_fn=lambda: []).resolve()
    assert info.available is False
    assert info.status == "jupyter_server_not_found"


def test_resolve_success(monkeypatch):
    from opencode_cloud import access as m

    monkeypatch.setattr(m, "wait_for_port", lambda *a, **k: True)
    servers = [{"base_url": "/k/42/secrettoken123/"}]
    info = KaggleProxyAccess(4096, servers_fn=lambda: servers).resolve()
    assert info.available is True
    assert info.provider == "kaggle_jupyter_proxy"
    assert info.url and "proxy/proxy/4096" in info.url


def test_resolve_not_listening(monkeypatch):
    from opencode_cloud import access as m

    monkeypatch.setattr(m, "wait_for_port", lambda *a, **k: False)
    info = KaggleProxyAccess(59999, servers_fn=lambda: [{"base_url": "/k/1/t/"}]).resolve()
    assert info.status == "opencode_not_listening"


def test_banner_accessible():
    from opencode_cloud.access import AccessInfo

    info = AccessInfo(
        available=True,
        url="https://example/k/1/tok/proxy/proxy/4096",
        status="ready",
        opencode_listening=True,
        provider="kaggle_jupyter_proxy",
    )
    text = format_workstation_banner(recovery="FRESH", opencode_status="RUNNING", access=info)
    assert "ACCESSIBLE" in text


def test_banner_not_accessible():
    from opencode_cloud.access import AccessInfo

    info = AccessInfo(
        available=False,
        status="jupyter_server_not_found",
        opencode_listening=True,
        provider="kaggle_jupyter_proxy",
    )
    text = format_workstation_banner(recovery="FRESH", opencode_status="RUNNING", access=info)
    assert "NOT_ACCESSIBLE" in text


def test_no_token_in_redacted_log_path():
    url = build_kaggle_proxy_url(kernel="7", token="SUPERSECRETTOKEN", port=8000)
    r = redact_proxy_url(url)
    assert "SUPERSECRETTOKEN" not in (r or "")
