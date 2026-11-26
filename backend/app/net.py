"""Outbound HTTP helpers.

Two kinds of fetch:
  * get_json(url)      - fixed, trusted API hosts (DexScreener, Shrine, X syndication).
  * safe_get_json(url) - URLs that come from token metadata. Anyone can create a token,
                         so these URLs are attacker-controlled: only public IPs are allowed,
                         the connection is pinned to the checked IP (no DNS rebinding), and
                         every redirect is checked again.
"""
import http.client
import ipaddress
import json
import logging
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "PvP-Scanner/2.0", "Accept": "application/json"}
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3

log = logging.getLogger("pvp.net")


class FetchError(Exception):
    pass


# ---------- small TTL cache shared by all fetches ----------
_cache = {}
_cache_lock = threading.Lock()


def _cached(key, ttl, fn):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = fn()  # exceptions propagate and are not cached
    with _cache_lock:
        if len(_cache) > 5000:
            for k in [k for k, (exp, _) in _cache.items() if exp <= now]:
                del _cache[k]
            if len(_cache) > 5000:
                _cache.clear()
        _cache[key] = (now + ttl, value)
    return value


def _read_json(resp):
    body = resp.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise FetchError("response too large")
    return json.loads(body)


def get_json(url, timeout=6, ttl=60):
    """GET JSON from a trusted, hard-coded API host. Cached for `ttl` seconds."""
    def go():
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _read_json(resp)
    return _cached(("trusted", url), ttl, go)


# ---------- untrusted URLs ----------
def is_public_ip(ip_text):
    try:
        ip = ipaddress.ip_address(ip_text.split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def resolve_public(host, port):
    """Resolve host and return one address, or raise if ANY address is non-public."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"cannot resolve {host}") from exc
    addrs = sorted({info[4][0] for info in infos})
    if not addrs:
        raise FetchError(f"cannot resolve {host}")
    for addr in addrs:
        if not is_public_ip(addr):
            raise FetchError(f"{host} resolves to a non-public address")
    return addrs[0]


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def check_url(url):
    """Validate scheme/host of an untrusted URL. Returns the parsed URL."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("only http(s) URLs are allowed")
    if parts.username or parts.password:
        raise FetchError("credentials in URL are not allowed")
    return parts


def safe_get_json(url, timeout=5, ttl=600):
    """GET JSON from an attacker-controlled URL without reaching private networks."""
    def go():
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            parts = check_url(current)
            port = parts.port or (443 if parts.scheme == "https" else 80)
            ip = resolve_public(parts.hostname, port)
            conn_cls = _PinnedHTTPS if parts.scheme == "https" else _PinnedHTTP
            conn = conn_cls(parts.hostname, ip, port, timeout)
            try:
                path = urllib.parse.urlunsplit(("", "", parts.path or "/", parts.query, ""))
                conn.request("GET", path, headers=HEADERS)
                resp = conn.getresponse()
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.getheader("Location")
                    if not location:
                        raise FetchError("redirect without location")
                    current = urllib.parse.urljoin(current, location)
                    continue
                if resp.status != 200:
                    raise FetchError(f"HTTP {resp.status}")
                return _read_json(resp)
            finally:
                conn.close()
        raise FetchError("too many redirects")
    return _cached(("untrusted", url), ttl, go)
