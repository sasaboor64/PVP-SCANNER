# PvP Scanner

Finds Solana tokens that share a ticker, name, links or narrative with a given mint.

- `backend/` — FastAPI scanner service (see `backend/README.md`)
- `docs/` — static web frontend (single `index.html`, no build step), served by GitHub Pages

## Running it

1. Start the backend on your machine:
   ```bash
   cd backend
   python -m pip install -r requirements.txt
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. Open the frontend, either the GitHub Pages URL or `docs/index.html` straight from disk.
   It calls `http://127.0.0.1:8000` by default; change the API field in the header to point elsewhere.

The page reads untrusted token metadata, so it only ever inserts it as text and only links `http(s)` URLs.

## GitHub Pages

Settings → Pages → Source: "Deploy from a branch", choose the branch and the `/docs` folder.

The hosted page is https and the backend is local http. Chrome, Edge and Firefox allow calls to
`127.0.0.1` from an https page (Chrome may ask permission to access the local network); Safari does not.
