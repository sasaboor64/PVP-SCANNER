import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import scanner_core as scanner

app = FastAPI(
    title="PvP Scanner API",
    description="Backend-only Solana token narrative and PvP research scanner. No Telegram integration.",
    version="1.0.0",
)

# Local development defaults. Restrict origins before deploying publicly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class CompareRequest(BaseModel):
    token_a: str = Field(min_length=32, max_length=44)
    token_b: str = Field(min_length=32, max_length=44)

@app.get("/")
def root():
    return {"name": "PvP Scanner API", "status": "running", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "healthy", "database": str(scanner.DB_PATH)}

@app.post("/api/scan/{mint}")
def scan(mint: str) -> dict[str, Any]:
    try:
        return scanner.scan_token(mint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logging.exception("Scan failed for %s", mint)
        raise HTTPException(status_code=502, detail=f"Scan failed: {type(exc).__name__}: {exc}")

@app.post("/api/compare")
def compare(request: CompareRequest):
    if not scanner.CA_RE.fullmatch(request.token_a) or not scanner.CA_RE.fullmatch(request.token_b):
        raise HTTPException(status_code=400, detail="Both values must be valid Solana mint addresses.")
    try:
        a, b = scanner.fetch(request.token_a), scanner.fetch(request.token_b)
        scanner.save(a)
        scanner.save(b)
        evidence = scanner.compare(a, b)
        return {
            "token_a": a,
            "token_b": b,
            "evidence": [{"label": label, "score": score} for label, score in evidence],
            "potential_overlap": bool(evidence),
        }
    except Exception as exc:
        logging.exception("Comparison failed")
        raise HTTPException(status_code=502, detail=f"Comparison failed: {type(exc).__name__}: {exc}")

@app.get("/api/recent")
def get_recent(limit: int = Query(default=25, ge=1, le=500)):
    return {"items": scanner.recent(limit=limit), "count": len(scanner.recent(limit=limit))}
