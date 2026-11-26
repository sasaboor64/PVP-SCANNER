import pytest

from app import ai, db, settings
from app import scanner_core as sc
from tests.fakes import (NAMESAKE, RIVAL, TARGET, UNRELATED, FakeMessages, fake_client,
                         fake_get_json, fake_safe_get_json)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    db.init()
    with db.connect() as con:
        con.execute("DELETE FROM ai_verdicts")
        con.execute("DELETE FROM ai_usage")
        con.execute("DELETE FROM tokens")
    monkeypatch.setattr(sc, "get_json", fake_get_json)
    monkeypatch.setattr(sc, "safe_get_json", fake_safe_get_json)
    monkeypatch.setattr("app.xposts.get_json", fake_get_json)


@pytest.mark.parametrize("value,ok", [
    (TARGET, True), (RIVAL, True), ("11111111111111111111111111111111", True),
    ("So1111111111111111111111111111111111111111", False),   # decodes to 31 bytes
    ("0OIl" * 10, False), ("", False), (None, False), ("x" * 45, False),
])
def test_is_mint(value, ok):
    assert sc.is_mint(value) is ok


def test_scan_without_ai(monkeypatch):
    monkeypatch.setattr(settings, "ai_key_present", lambda: False)
    result = sc.scan_token(TARGET)
    assert result["target"]["name"] == "Moo Deng"
    assert result["target"]["narrative_text"].startswith("Moo Deng the pygmy hippo")
    assert result["ai"]["status"] == "disabled"
    cas = [m["token"]["ca"] for m in result["matches"]]
    assert TARGET not in cas
    assert cas[0] == RIVAL                       # real narrative overlap ranks first
    assert NAMESAKE in cas                       # ticker collision kept as context
    assert UNRELATED not in cas                  # nothing in common: dropped
    assert all(m["ai"] is None for m in result["matches"])


def test_scan_with_ai_reranks_and_caches(monkeypatch):
    monkeypatch.setattr(settings, "ai_key_present", lambda: True)
    msgs = FakeMessages({"Hippo Deng": ("strong_match", 92), "Moo Deng Agent": ("not_a_match", 10),
                         "Solana Cat": ("not_a_match", 0)})
    monkeypatch.setattr(ai, "_get_client", lambda: fake_client(msgs))

    first = sc.scan_token(TARGET)
    assert first["ai"]["status"] == "ok"
    top = first["matches"][0]
    assert top["token"]["ca"] == RIVAL and top["ai"]["classification"] == "strong_match"
    assert top["relevance_score"] > top["heuristic_score"]
    namesake = next(m for m in first["matches"] if m["token"]["ca"] == NAMESAKE)
    assert namesake["relevance_score"] < namesake["heuristic_score"]  # AI demoted the pure ticker collision

    call = msgs.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "<token_data>" in call["messages"][0]["content"]
    assert "thinking" not in call and "temperature" not in call

    second = sc.scan_token(TARGET)
    assert second["ai"]["status"] == "cached" and len(msgs.calls) == 1
    assert ai.spent_today() == pytest.approx(6000 / 1e6 * 4 + 2000 / 1e6 * 20)


def test_ai_budget_cap(monkeypatch):
    monkeypatch.setattr(settings, "ai_key_present", lambda: True)
    monkeypatch.setattr(settings, "AI_DAILY_BUDGET_USD", 0.0)
    msgs = FakeMessages({})
    monkeypatch.setattr(ai, "_get_client", lambda: fake_client(msgs))
    result = sc.scan_token(TARGET)
    assert result["ai"]["status"] == "daily_budget_reached" and not msgs.calls
    assert result["matches"]  # still returns heuristic results


@pytest.mark.parametrize("stop_reason,status", [("refusal", "refused"), ("max_tokens", "error")])
def test_ai_unusable_response_falls_back(monkeypatch, stop_reason, status):
    monkeypatch.setattr(settings, "ai_key_present", lambda: True)
    monkeypatch.setattr(ai, "_get_client", lambda: fake_client(FakeMessages({}, stop_reason)))
    result = sc.scan_token(TARGET)
    assert result["ai"]["status"] == status
    assert result["matches"][0]["token"]["ca"] == RIVAL


def test_ai_exception_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "ai_key_present", lambda: True)
    def broken():
        raise RuntimeError("network down")
    monkeypatch.setattr(ai, "_get_client", broken)
    assert sc.scan_token(TARGET)["ai"]["status"] == "error"


def test_ignores_bad_ai_ids_and_clamps_fit(monkeypatch):
    out = ai._clean({"classification": "strong_match", "fit": 250, "reason": "x" * 999, "evidence_terms": list("abcdefgh")})
    assert out["fit"] == 100 and len(out["reason"]) == 300 and len(out["evidence_terms"]) == 6


def test_compare_tokens():
    out = sc.compare_tokens(TARGET, RIVAL)
    labels = {e["label"] for e in out["evidence"]}
    assert "Exact ticker" in labels and out["potential_overlap"]
    with pytest.raises(ValueError):
        sc.compare_tokens(TARGET, "bad")
