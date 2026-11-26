"""Canned DexScreener / Shrine / X responses and a fake Claude client."""
import json
from types import SimpleNamespace

TARGET = "So11111111111111111111111111111111111111112"
RIVAL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NAMESAKE = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
UNRELATED = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


def pair(ca, name, symbol, desc=None, liq=1000, x=None):
    info = {"description": desc}
    if x:
        info["socials"] = [{"type": "twitter", "url": x}]
    return {"chainId": "solana", "url": f"https://dexscreener.com/solana/{ca}", "baseToken":
            {"address": ca, "name": name, "symbol": symbol}, "liquidity": {"usd": liq},
            "marketCap": liq * 10, "info": info}


PAIRS = [
    pair(RIVAL, "Hippo Deng", "HDENG", "Moo Deng the pygmy hippo from Khao Kheow zoo, bouncy baby", 5000,
         x="https://x.com/hippo/status/1849112312437182717"),
    pair(NAMESAKE, "Moo Deng Agent", "MOODENG", "Autonomous trading agent", 800),
    pair(UNRELATED, "Solana Cat", "SCAT", "The best cat", 100),
]


def fake_get_json(url, timeout=6, ttl=60):
    if "shrine" in url:
        return {"name": "Moo Deng", "symbol": "MOODENG",
                "description": "Moo Deng is the viral pygmy hippo from Khao Kheow zoo in Thailand",
                "uri": "https://arweave.example/meta.json"}
    if "/latest/dex/tokens/" in url:
        return {"pairs": [pair(TARGET, "Moo Deng", "MOODENG", liq=900000)]}
    if "/latest/dex/search" in url:
        return {"pairs": PAIRS + [pair(TARGET, "Moo Deng", "MOODENG")]}
    if "token-profiles" in url:
        return []
    if "syndication" in url:
        return {"text": "Moo Deng the pygmy hippo is bouncing again at Khao Kheow"}
    raise AssertionError("unexpected url " + url)


def fake_safe_get_json(url, timeout=5, ttl=600):
    return {"twitter": "https://x.com/moodeng/status/1849000000000000000"}


class FakeMessages:
    def __init__(self, verdicts, stop_reason="end_turn"):
        self.verdicts, self.stop_reason, self.calls = verdicts, stop_reason, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        data = json.loads(kwargs["messages"][0]["content"].split("<token_data>\n", 1)[1].split("\n</token_data>", 1)[0])
        results = []
        for c in data["candidates"]:
            v = self.verdicts.get(c["name"], ("not_a_match", 5))
            results.append({"id": c["id"], "classification": v[0], "fit": v[1],
                            "reason": f"verdict for {c['name']}", "evidence_terms": ["hippo"]})
        return SimpleNamespace(
            stop_reason=self.stop_reason, model=kwargs["model"], stop_details=None,
            usage=SimpleNamespace(input_tokens=6000, output_tokens=2000, cache_creation_input_tokens=0,
                                  cache_read_input_tokens=0),
            content=[SimpleNamespace(type="thinking", thinking=""),
                     SimpleNamespace(type="text", text=json.dumps({"results": results}))])


def fake_client(messages):
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))
