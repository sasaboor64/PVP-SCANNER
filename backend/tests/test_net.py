import socket

import pytest

from app import net


@pytest.mark.parametrize("ip,ok", [
    ("8.8.8.8", True), ("2606:4700::1111", True),
    ("127.0.0.1", False), ("10.1.2.3", False), ("172.16.0.1", False), ("192.168.1.1", False),
    ("169.254.169.254", False), ("100.64.0.1", False), ("0.0.0.0", False), ("::1", False),
    ("fe80::1%eth0", False), ("::ffff:127.0.0.1", False), ("fd00::1", False), ("224.0.0.1", False),
])
def test_is_public_ip(ip, ok):
    assert net.is_public_ip(ip) is ok


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x", "gopher://x", "http://user:pw@example.com/",
    "http://127.0.0.1:8000/health", "http://169.254.169.254/latest/meta-data/", "http://localhost/",
    "http://[::1]/", "http://0x7f000001/",
])
def test_safe_get_rejects_internal_targets(url):
    with pytest.raises(net.FetchError):
        net.safe_get_json(url)


def test_safe_get_rejects_hostname_resolving_to_private(monkeypatch):
    def fake_getaddrinfo(host, port, type=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(net.FetchError, match="non-public"):
        net.safe_get_json("https://metadata.evil.example/token.json")


def test_safe_get_rechecks_redirect_target(monkeypatch):
    """A public host that redirects to an internal address must be refused."""
    monkeypatch.setattr(net, "resolve_public",
                        lambda host, port: "93.184.216.34" if host == "public.example" else
                        (_ for _ in ()).throw(net.FetchError("non-public")))

    class FakeResp:
        status = 302
        def getheader(self, name):
            return "http://internal.example/secret"
        def read(self, n):
            return b""

    class FakeConn:
        def __init__(self, *a, **k): pass
        def request(self, *a, **k): pass
        def getresponse(self): return FakeResp()
        def close(self): pass

    monkeypatch.setattr(net, "_PinnedHTTP", FakeConn)
    with pytest.raises(net.FetchError, match="non-public"):
        net.safe_get_json("http://public.example/meta.json")


def test_cache_does_not_store_failures():
    calls = []
    def boom():
        calls.append(1)
        raise ValueError("x")
    for _ in range(2):
        with pytest.raises(ValueError):
            net._cached(("t", "fail"), 60, boom)
    assert len(calls) == 2
    assert net._cached(("t", "ok"), 60, lambda: 5) == 5
    assert net._cached(("t", "ok"), 60, lambda: 6) == 5
