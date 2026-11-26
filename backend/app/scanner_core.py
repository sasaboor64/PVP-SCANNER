"""Scanner engine: look up a Solana token, find rivals, and score narrative overlap."""
import json
import logging
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from . import ai, settings
from .db import connect
from .net import get_json, safe_get_json
from .xposts import fetch_tweet_text, tweet_id_from_url

log = logging.getLogger("pvp.scan")
CA_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
POOL = ThreadPoolExecutor(max_workers=24, thread_name_prefix="fetch")

MAX_QUERIES = 10
MAX_TWEET_FETCHES = 25   # per scan, for the most promising candidates
MAX_RESULTS = 8


# ---------- validation ----------
def is_mint(value):
    """A mint is a base58 string that decodes to 32 bytes."""
    if not isinstance(value, str) or not CA_RE.fullmatch(value):
        return False
    n = 0
    for ch in value:
        n = n * 58 + _B58.index(ch)
    pad = len(value) - len(value.lstrip("1"))
    return pad + (n.bit_length() + 7) // 8 == 32


def is_url(s):
    return isinstance(s, str) and s.startswith(("https://", "http://"))


def norm(s):
    s = (s or "").casefold()
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


# ---------- token lookup ----------
def _empty_token(ca):
    return {"ca": ca, "name": None, "symbol": None, "description": None, "metadata_uri": None,
            "source_url": None, "socials": {}, "market_cap": None, "liquidity": None,
            "pair_url": None, "narrative_text": None}


def _shrine(ca):
    try:
        return get_json("https://sol.shrine.trade/metadata?mint=" + urllib.parse.quote(ca), 4, ttl=300)
    except Exception as exc:
        log.info("Shrine lookup unavailable for %s: %s", ca, exc)
        return None


def _dex_token(ca):
    try:
        return get_json("https://api.dexscreener.com/latest/dex/tokens/" + urllib.parse.quote(ca), 5, ttl=60)
    except Exception as exc:
        log.info("DexScreener lookup unavailable for %s: %s", ca, exc)
        return None


def _socials_from_pair(pair):
    info = pair.get("info") or {}
    socials = {}
    for w in info.get("websites") or []:
        if isinstance(w, dict) and is_url(w.get("url")):
            socials.setdefault("Website", w["url"])
    for s in info.get("socials") or []:
        if not isinstance(s, dict) or not is_url(s.get("url")):
            continue
        kind = str(s.get("type") or "").casefold()
        label = {"twitter": "X/Twitter", "x": "X/Twitter", "telegram": "Telegram",
                 "discord": "Discord", "reddit": "Reddit", "instagram": "Instagram"}.get(kind)
        if label:
            socials.setdefault(label, s["url"])
    return socials


def fetch(ca):
    t = _empty_token(ca)
    shrine_f, dex_f = POOL.submit(_shrine, ca), POOL.submit(_dex_token, ca)

    d = shrine_f.result()
    if isinstance(d, dict):
        sources = [d] + [d[k] for k in ("metadata", "token", "data", "socials", "links") if isinstance(d.get(k), dict)]
        for s in sources:
            t["name"] = t["name"] or s.get("name") or s.get("token_name")
            t["symbol"] = t["symbol"] or s.get("symbol") or s.get("ticker")
            t["description"] = t["description"] or s.get("description")
            t["metadata_uri"] = t["metadata_uri"] or s.get("uri") or s.get("metadata_uri")
            t["source_url"] = t["source_url"] or s.get("source_url")
            for label, keys in {"Website": ("website", "website_url"), "X/Twitter": ("twitter", "x", "twitter_url", "x_url"),
                                "Telegram": ("telegram", "telegram_url")}.items():
                for k in keys:
                    if is_url(s.get(k)):
                        t["socials"].setdefault(label, s[k])

    d = dex_f.result()
    pairs = (d.get("pairs") or []) if isinstance(d, dict) else []
    pairs = [p for p in pairs if isinstance(p, dict)]
    pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), reverse=True)
    if pairs:
        p = pairs[0]
        base = p.get("baseToken") or {}
        t["name"] = t["name"] or base.get("name")
        t["symbol"] = t["symbol"] or base.get("symbol")
        t["market_cap"] = p.get("marketCap") or p.get("fdv")
        t["liquidity"] = (p.get("liquidity") or {}).get("usd")
        t["pair_url"] = p.get("url")
        for label, url in _socials_from_pair(p).items():
            t["socials"].setdefault(label, url)

    if is_url(t["metadata_uri"]):
        try:
            m = safe_get_json(t["metadata_uri"], 4)
            if isinstance(m, dict):
                t["name"] = t["name"] or m.get("name")
                t["symbol"] = t["symbol"] or m.get("symbol")
                t["description"] = t["description"] or m.get("description")
                for label, keys in {"Website": ("website", "external_url"), "X/Twitter": ("twitter", "twitter_url"),
                                    "Telegram": ("telegram", "telegram_url")}.items():
                    for k in keys:
                        if is_url(m.get(k)):
                            t["socials"].setdefault(label, m[k])
        except Exception as exc:
            log.info("Metadata URI unavailable for %s: %s", ca, exc)

    t["name"] = str(t["name"] or "").strip()[:200] or None
    t["symbol"] = str(t["symbol"] or "").strip().lstrip("$")[:40] or None
    t["description"] = str(t["description"] or "").strip()[:4000] or None
    x_url = t["socials"].get("X/Twitter")
    t["narrative_text"] = fetch_tweet_text(x_url) if x_url else None
    return t


# ---------- discovery ----------
STOP = {
    "the", "and", "for", "with", "this", "that", "from", "your", "its", "are", "was", "has", "have", "will", "not", "you",
    "our", "about", "https", "http", "com", "twitter", "telegram", "agent", "agents", "ai", "crypto", "memecoin",
    "memecoins", "launch", "launched", "token", "tokens", "sol", "solana", "pump", "pumpfun", "fun", "official",
    "community", "project", "account", "follow", "link", "post", "posts", "today", "just", "new", "real", "one", "can",
    "get", "got", "via", "use", "using", "join", "here", "there", "they", "them", "their", "what", "when", "where",
    "which", "who", "how", "why", "into", "over", "more", "most", "some", "any", "all", "out", "yourself", "were",
    "been", "being", "would", "could", "should", "than", "then", "also", "only", "very", "much", "many",
}


def narrative_terms(token):
    """Distinctive terms from name, ticker, description and linked X post.

    Longer words rank first (they tend to be more specific), then more frequent ones."""
    raw = " ".join(str(token.get(k) or "") for k in ("name", "symbol", "description", "narrative_text"))
    raw = re.sub(r"https?://\S+", " ", raw)
    counts = {}
    for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", raw.casefold()):
        if w not in STOP and len(w) >= 4:
            counts[w] = counts.get(w, 0) + 1
    return sorted(counts, key=lambda w: (-min(len(w), 14), -counts[w], w))[:35]


def narrative_score(a, b):
    """Explainable keyword overlap score in [0, 1] and the shared terms."""
    aw, bw = set(narrative_terms(a)), set(narrative_terms(b))
    if not aw or not bw:
        return 0.0, []
    common = sorted(aw & bw, key=lambda w: (-len(w), w))
    score = len(common) / max(1, min(len(aw), len(bw)))
    if len(common) >= 2 and any(len(w) >= 5 for w in common):
        score = min(1.0, score + 0.15)
    return score, common[:8]


def build_queries(target):
    queries = []
    seen = set()

    def add(q):
        if q and q.casefold() not in seen:
            seen.add(q.casefold())
            queries.append(q)

    add(target.get("symbol"))
    add(target.get("name"))
    for word in narrative_terms(target)[:7]:
        add(word)
    source_text = " ".join(str(target.get(k) or "") for k in ("name", "description", "narrative_text"))
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", source_text) if w.casefold() not in STOP]
    phrases = 0
    for i in range(len(words) - 1):
        phrase = words[i] + " " + words[i + 1]
        if len(phrase) >= 9 and phrase.casefold() not in seen:
            add(phrase)
            phrases += 1
            if phrases >= 3:
                break
    return queries[:MAX_QUERIES]


def dex_search(query):
    if not query or len(query.strip()) < 2:
        return []
    url = "https://api.dexscreener.com/latest/dex/search?" + urllib.parse.urlencode({"q": query.strip()[:80]})
    try:
        data = get_json(url, 7, ttl=120)
    except Exception as exc:
        log.info("DexScreener search failed for %r: %s", query, exc)
        return []
    pairs = (data.get("pairs") or []) if isinstance(data, dict) else []
    return [p for p in pairs if isinstance(p, dict) and p.get("chainId") == "solana"]


def latest_profiles():
    try:
        data = get_json("https://api.dexscreener.com/token-profiles/latest/v1", 7, ttl=120)
    except Exception as exc:
        log.info("DexScreener recent profiles unavailable: %s", exc)
        return []
    return [x for x in data if isinstance(x, dict) and x.get("chainId") == "solana"] if isinstance(data, list) else []


def candidate_from_pair(pair):
    base = pair.get("baseToken") or {}
    info = pair.get("info") or {}
    return {
        "ca": base.get("address") or "", "name": base.get("name"),
        "symbol": str(base.get("symbol") or "").lstrip("$") or None,
        "description": info.get("description"), "narrative_text": None, "socials": _socials_from_pair(pair),
        "market_cap": pair.get("marketCap") or pair.get("fdv"),
        "liquidity": (pair.get("liquidity") or {}).get("usd"),
        "pair_url": pair.get("url"), "source_url": pair.get("url"),
    }


def profile_links(profile):
    socials = {}
    for item in profile.get("links") or []:
        if not isinstance(item, dict) or not is_url(item.get("url")):
            continue
        kind = str(item.get("type") or item.get("label") or "").casefold()
        if "twitter" in kind or kind == "x":
            socials.setdefault("X/Twitter", item["url"])
        elif "telegram" in kind:
            socials.setdefault("Telegram", item["url"])
        elif "website" in kind or "web" in kind:
            socials.setdefault("Website", item["url"])
    return socials


def enrich_from_profile(candidate, profile):
    for label, url in profile_links(profile).items():
        candidate.setdefault("socials", {}).setdefault(label, url)
    desc = str(profile.get("description") or "").strip()
    if desc and not candidate.get("description"):
        candidate["description"] = desc
    if profile.get("url"):
        candidate["pair_url"] = candidate.get("pair_url") or profile["url"]
        candidate["source_url"] = candidate.get("source_url") or profile["url"]
    return candidate


def _same_url(a, b):
    return bool(a and b and a.rstrip("/").casefold() == b.rstrip("/").casefold())


def heuristic_rank(target, candidate):
    """Cheap pre-ranking used to choose what to enrich and what to send to the AI."""
    score = 0.0
    if target.get("symbol") and candidate.get("symbol") and target["symbol"].casefold() == candidate["symbol"].casefold():
        score += 10
    if target.get("name") and candidate.get("name"):
        a, b = norm(target["name"]), norm(candidate["name"])
        if a and b:
            score += 8 if a == b else 4 * SequenceMatcher(None, a, b).ratio()
    for label in ("X/Twitter", "Telegram", "Website"):
        if _same_url(target.get("socials", {}).get(label), candidate.get("socials", {}).get(label)):
            score += 8
    _, shared = narrative_score(target, candidate)
    score += min(4, len(shared))
    if target.get("narrative_text") and candidate.get("narrative_text"):
        _, tweet_shared = narrative_score({"description": target["narrative_text"]}, {"description": candidate["narrative_text"]})
        score += min(6, len(tweet_shared) * 1.5)
    return score


def discover(target):
    """Search live indexes for candidate rivals. Returns (candidates, query_count)."""
    queries = build_queries(target)
    profiles_f = POOL.submit(latest_profiles)
    found = {}
    for pairs in POOL.map(dex_search, queries):
        for pair in pairs:
            cand = candidate_from_pair(pair)
            ca = cand["ca"]
            if not ca or ca == target["ca"]:
                continue
            old = found.get(ca)
            if not old or float(cand.get("liquidity") or 0) > float(old.get("liquidity") or 0):
                if old:
                    for label, url in old.get("socials", {}).items():
                        cand["socials"].setdefault(label, url)
                found[ca] = cand

    profiles = profiles_f.result()
    profile_by_ca = {p.get("tokenAddress"): p for p in profiles if p.get("tokenAddress")}
    for ca, cand in found.items():
        if ca in profile_by_ca:
            enrich_from_profile(cand, profile_by_ca[ca])

    # Recent profiles with distinctive narrative overlap, even if search missed them.
    target_terms = set(narrative_terms(target))
    if target_terms:
        for profile in profiles:
            ca = profile.get("tokenAddress")
            if not ca or ca == target["ca"]:
                continue
            desc = str(profile.get("description") or "")
            if len(target_terms & set(narrative_terms({"description": desc}))) >= 2:
                cand = found.get(ca) or {**_empty_token(ca), "description": desc,
                                         "pair_url": profile.get("url"), "source_url": profile.get("url")}
                found[ca] = enrich_from_profile(cand, profile)

    candidates = list(found.values())
    # Fetch linked X posts for the most promising candidates only.
    with_x = [c for c in candidates if c.get("socials", {}).get("X/Twitter")]
    with_x.sort(key=lambda c: heuristic_rank(target, c), reverse=True)
    with_x = with_x[:MAX_TWEET_FETCHES]
    for cand, text in zip(with_x, POOL.map(lambda c: fetch_tweet_text(c["socials"]["X/Twitter"]), with_x)):
        cand["narrative_text"] = text
    return candidates, len(queries)


# ---------- scoring ----------
def heuristic_evidence(target, cand):
    """Evidence list and 0-100 heuristic relevance for one candidate."""
    why = []
    ticker = bool(target.get("symbol") and cand.get("symbol") and target["symbol"].casefold() == cand["symbol"].casefold())
    if ticker:
        why.append({"label": "Ticker collision", "score": 0.0, "detail": target["symbol"]})
    name_ratio = 0.0
    if target.get("name") and cand.get("name"):
        a, b = norm(target["name"]), norm(cand["name"])
        if a and b:
            name_ratio = SequenceMatcher(None, a, b).ratio()
            if a == b:
                why.append({"label": "Same token name", "score": 0.0, "detail": cand["name"]})
            elif name_ratio >= .78:
                why.append({"label": "Similar name", "score": 0.0, "detail": cand["name"]})
    shared_url = False
    for label in ("Website", "X/Twitter", "Telegram"):
        y = cand.get("socials", {}).get(label)
        if _same_url(target.get("socials", {}).get(label), y):
            shared_url = True
            why.append({"label": f"Same {label} URL", "score": 0.0, "detail": y})
    score, shared = narrative_score(target, cand)
    distinctive = [w for w in shared if len(w) >= 5]
    if score >= .30 and len(distinctive) >= 2:
        why.append({"label": "Shared narrative terms", "score": round(score, 2), "detail": ", ".join(distinctive[:6])})
    tweet_score, tweet_shared = narrative_score({"description": target.get("narrative_text") or ""},
                                                {"description": cand.get("narrative_text") or ""})
    tweet_distinctive = [w for w in tweet_shared if len(w) >= 5]
    if tweet_score >= .20 and len(tweet_distinctive) >= 2:
        why.append({"label": "Linked X-post overlap", "score": round(tweet_score, 2), "detail": ", ".join(tweet_distinctive[:6])})
    tx, cx = target.get("socials", {}).get("X/Twitter"), cand.get("socials", {}).get("X/Twitter")
    same_post = bool(tweet_id_from_url(tx) and tweet_id_from_url(tx) == tweet_id_from_url(cx))
    if same_post:
        why.append({"label": "Same source X post", "score": 1.0, "detail": "identical post URL"})

    relevance = 100 * (min(1.0, score) * 0.40 + min(1.0, tweet_score) * 0.35
                       + min(1.0, max(name_ratio, 0.65 if ticker else 0.0)) * 0.10
                       + (0.15 if same_post else 0.08 if shared_url else 0.0))
    weak = score == 0 and tweet_score == 0 and not same_post and not shared_url and name_ratio < .45 and not ticker
    return why, round(min(100, relevance)), weak


def blend(heuristic, verdict):
    """Final 0-100 score. With an AI verdict, Claude's narrative fit dominates."""
    if not verdict:
        return heuristic
    return round(0.35 * heuristic + 0.65 * verdict["fit"])


def rank(target, candidates):
    """Score candidates, ask Claude about the shortlist, and return (matches, ai_status)."""
    scored = []
    for cand in candidates:
        why, h, weak = heuristic_evidence(target, cand)
        scored.append({"cand": cand, "why": why, "h": h, "weak": weak, "pre": heuristic_rank(target, cand)})
    scored.sort(key=lambda s: (s["pre"], s["h"]), reverse=True)

    # Claude sees the top of the cheap ranking, including candidates the keyword rules
    # call weak: it can catch a shared story told in different words.
    shortlist = [s["cand"] for s in scored[:settings.AI_SHORTLIST]]
    verdicts, ai_status = ai.review(target, shortlist)

    matches = []
    for s in scored:
        verdict = verdicts.get(s["cand"]["ca"])
        if s["weak"] and not (verdict and verdict["classification"] != "not_a_match"):
            continue
        if not s["why"] and not verdict:
            continue
        matches.append({
            "token": s["cand"],
            "relevance_score": blend(s["h"], verdict),
            "heuristic_score": s["h"],
            "ai": verdict,
            "evidence": s["why"],
        })
    matches.sort(key=lambda m: (m["relevance_score"], m["heuristic_score"]), reverse=True)
    return matches[:MAX_RESULTS], ai_status


# ---------- history ----------
def compare(a, b):
    out = []
    if a["ca"] == b["ca"]:
        out.append(("Same CA", 1.0))
    if a.get("symbol") and b.get("symbol") and a["symbol"].casefold() == b["symbol"].casefold():
        out.append(("Exact ticker", 1.0))
    if a.get("name") and b.get("name"):
        x, y = norm(a["name"]), norm(b["name"])
        if x and y and x == y:
            out.append(("Exact name", 1.0))
        elif x and y:
            r = SequenceMatcher(None, x, y).ratio()
            if r >= .72:
                out.append(("Similar name", round(r, 2)))
    x, y = norm(a.get("description"))[:1500], norm(b.get("description"))[:1500]
    if x and y:
        r = SequenceMatcher(None, x, y).ratio()
        if r >= .70:
            out.append(("Similar description", round(r, 2)))
    for label in ("Website", "X/Twitter", "Telegram"):
        if _same_url(a.get("socials", {}).get(label), b.get("socials", {}).get(label)):
            out.append((f"Same {label} URL", 1.0))
    return out


def save(t):
    now = int(time.time())
    with connect() as c:
        c.execute(
            "INSERT INTO tokens VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(ca) DO UPDATE SET name=excluded.name, "
            "symbol=excluded.symbol, description=excluded.description, metadata_uri=excluded.metadata_uri, "
            "source_url=excluded.source_url, socials_json=excluded.socials_json, last_scanned=excluded.last_scanned",
            (t["ca"], t.get("name"), t.get("symbol"), t.get("description"), t.get("metadata_uri"),
             t.get("source_url") or t.get("pair_url"), json.dumps(t.get("socials") or {}), now, now))


def recent(exclude=None, limit=500):
    with connect() as c:
        rows = c.execute("SELECT * FROM tokens ORDER BY last_scanned DESC LIMIT ?", (limit,)).fetchall()
    return [{"ca": r["ca"], "name": r["name"], "symbol": r["symbol"], "description": r["description"],
             "source_url": r["source_url"], "socials": json.loads(r["socials_json"] or "{}"),
             "last_scanned": r["last_scanned"]}
            for r in rows if r["ca"] != exclude]


# ---------- entry points ----------
def scan_token(ca):
    if not is_mint(ca):
        raise ValueError("Invalid Solana token mint address")
    started = time.monotonic()
    target = fetch(ca)
    save(target)
    candidates, query_count = discover(target)
    matches, ai_status = rank(target, candidates)

    history = []
    for other in recent(exclude=ca):
        found = compare(target, other)
        if found:
            history.append({"token": other, "evidence": [{"label": l, "score": s} for l, s in found]})
    history.sort(key=lambda item: max(x["score"] for x in item["evidence"]), reverse=True)

    log.info("Scanned %s: %d candidates, %d matches, ai=%s, %.1fs",
             ca, len(candidates), len(matches), ai_status, time.monotonic() - started)
    return {
        "target": target,
        "matches": matches,
        "candidate_count": len(candidates),
        "query_count": query_count,
        "history_matches": history[:3],
        "ai": {"status": ai_status, "model": settings.AI_MODEL if ai_status in ("ok", "cached") else None},
        "disclaimer": "Matches are research leads, not proof of copying. New or unindexed tokens may be missing.",
    }


def compare_tokens(ca_a, ca_b):
    if not is_mint(ca_a) or not is_mint(ca_b):
        raise ValueError("Both values must be valid Solana mint addresses.")
    a, b = fetch(ca_a), fetch(ca_b)  # each fetch is already parallel inside; don't nest pool tasks
    save(a)
    save(b)
    evidence = compare(a, b)
    return {"token_a": a, "token_b": b,
            "evidence": [{"label": label, "score": score} for label, score in evidence],
            "potential_overlap": bool(evidence)}
