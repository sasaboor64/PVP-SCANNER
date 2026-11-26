import pytest
from fastapi.testclient import TestClient

from app import main
from app import scanner_core as sc
from tests.fakes import RIVAL, TARGET


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "scan_limiter", main.RateLimiter(2, 600))
    return TestClient(main.app)


def test_health_hides_internals(client):
    body = client.get("/api/health").json()
    assert body["status"] == "healthy" and "database" not in body
    assert body["ai"] == {"enabled": False, "model": None}


def test_invalid_mint(client):
    assert client.post("/api/scan/not-a-mint").status_code == 400


def test_scan_rate_limit_and_error_hiding(client, monkeypatch):
    def boom(ca):
        raise RuntimeError("secret internal path /opt/x")
    monkeypatch.setattr(sc, "scan_token", boom)
    for _ in range(2):
        r = client.post(f"/api/scan/{TARGET}")
        assert r.status_code == 502 and "secret" not in r.text
    r = client.post(f"/api/scan/{TARGET}")
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_compare_validation(client):
    r = client.post("/api/compare", json={"token_a": TARGET, "token_b": "1" * 40})
    assert r.status_code == 400


def test_recent(client):
    r = client.get("/api/recent?limit=5")
    assert r.status_code == 200 and "items" in r.json()
