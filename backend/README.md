# PvP Scanner Backend (Telegram-free)

This package extracts the scanner engine from the previously developed PvP Scanner v7 rules implementation and exposes it as a JSON REST API.

## Included
- Solana mint metadata lookup via Shrine metadata endpoint
- DexScreener token/pair discovery
- Token profile enrichment and social-link collection
- Linked public X-post text enrichment when available
- Narrative-term overlap and similarity scoring
- Ticker/name collision evidence (not treated as proof of narrative copying)
- Scan history stored in SQLite
- Direct token-to-token comparison
- Recent scan history endpoint

## Explicitly excluded
- Telegram bot polling, commands, notifications and bot-token configuration
- AI API calls (the source implementation is deterministic / AI disabled)

## Requirements
- Python 3.10+
- Internet access for public metadata and market-index APIs

## Setup (Windows PowerShell)
```powershell
cd PvP-Scanner-Backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Setup (Linux/macOS)
```bash
cd PvP-Scanner-Backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## API
- `GET /` - service information
- `GET /health` - health check
- `POST /api/scan/{mint}` - scan a Solana token mint address
- `POST /api/compare` - compare two token mint addresses
- `GET /api/recent?limit=25` - retrieve recent scans
- `GET /docs` - interactive Swagger API documentation

### Example requests
```bash
curl -X POST http://127.0.0.1:8000/api/scan/YOUR_SOLANA_MINT_ADDRESS
```

```bash
curl -X POST http://127.0.0.1:8000/api/compare ^
  -H "Content-Type: application/json" ^
  -d "{\"token_a\":\"MINT_ADDRESS_A\",\"token_b\":\"MINT_ADDRESS_B\"}"
```

## Database
SQLite database is created automatically as `pvp_scans.sqlite3` in the project directory.
Set `PVP_SCANNER_DB` to use a different database path, or `PVP_SCANNER_HOME` to change the data directory.

## Notes
- Public API availability, indexing coverage and rate limits can affect scan results.
- Newly launched or unindexed tokens may not appear in discovery results.
- Shared narratives and social links are evidence signals, not proof of copying or wrongdoing.
- CORS is permissive for local prototype use. Restrict allowed origins before any public deployment.
