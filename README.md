# PvP Scanner

Finds Solana tokens that share a ticker, name, links or narrative with a given mint, and has Claude judge the closest ones.

- `backend/`: FastAPI scanner service (see `backend/README.md`)
- `docs/`: static frontend (a single `index.html`, no build step)
- `deploy/`: server setup for AWS Lightsail with Caddy and DuckDNS (see `deploy/README.md`)

## Production

One server serves both the frontend and the API over HTTPS. Follow `deploy/README.md`.

## Local development

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `docs/index.html` from disk. When the page isn't served by the scanner's own server, it calls `http://127.0.0.1:8000`; you can change this under **Server** in the header.

Token metadata is untrusted, so the page only inserts it as text and only links `http(s)` URLs.
