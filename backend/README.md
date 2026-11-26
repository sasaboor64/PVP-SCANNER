# PvP Scanner backend

FastAPI service that looks up a Solana token, searches live market indexes for rival tokens built on the same ticker, name, links or narrative, and ranks them. The closest candidates are reviewed by Claude (optional).

## How a scan works

1. **Target lookup** (in parallel): Shrine metadata, DexScreener pairs, the token's metadata URI, and the text of its linked X post.
2. **Discovery**: up to 10 DexScreener searches (ticker, name, distinctive words, short phrases) plus the latest token-profile feed.
3. **Keyword scoring**: shared narrative terms, X-post overlap, name/ticker similarity, shared links → 0-100.
4. **Claude review**: the top 12 candidates go to Claude in one call, which returns a classification, a 0-100 narrative fit and a one-sentence reason for each. Final score = 35% keyword + 65% Claude fit. Claude can demote pure ticker collisions as well as promote real matches.
5. **History**: matches against tokens previously scanned on this server.

If Claude is not configured, over budget or failing, step 4 is skipped and keyword scores are used; scans never fail because of AI.

## Safety for a public deployment

- Token metadata URIs are attacker-controlled. They are fetched only if every resolved IP is public, the connection is pinned to the checked IP, and each redirect is checked again (`app/net.py`).
- Per-IP rate limits, a concurrent-scan cap, and a daily AI budget (`app/settings.py`).
- Token text is sent to Claude as untrusted data inside `<token_data>`; the reply is constrained by a JSON schema and clamped.
- Error responses never include internal exception text.

## Layout

| File | Purpose |
|---|---|
| `app/main.py` | HTTP API, rate limiting |
| `app/scanner_core.py` | lookup, discovery, scoring |
| `app/ai.py` | Claude review, verdict cache, daily budget |
| `app/net.py` | trusted and untrusted HTTP fetches, TTL cache |
| `app/xposts.py` | X post text via the syndication endpoint |
| `app/db.py` | SQLite schema |
| `app/settings.py` | environment-variable settings |
| `app/ai_check.py` | `python -m app.ai_check`: one tiny Claude request to verify setup |

## Run locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # optional; omit for keyword-only scoring
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open `docs/index.html` from disk; it talks to `http://127.0.0.1:8000`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests run offline with canned market data and a fake Claude client.

## API

- `POST /api/scan/{mint}`: scan a token
- `POST /api/compare`: `{"token_a": "...", "token_b": "..."}`
- `GET /api/recent?limit=25`: recently scanned tokens
- `GET /api/health`: status, and whether AI review is on

Settings are listed in `deploy/pvp-scanner.env.example`. For deployment see `deploy/README.md`.
