import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import ai, db, settings
from . import scanner_core as scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pvp.api")
db.init()

app = FastAPI(
    title="PvP Scanner API",
    description="Solana token narrative-overlap scanner with optional Claude review.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class RateLimiter:
    """Sliding-window limit per client IP, kept in memory."""

    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key):
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return int(q[0] + self.window - now) + 1
            q.append(now)
            if len(self.hits) > 10000:  # drop idle keys
                for k in [k for k, v in self.hits.items() if not v]:
                    del self.hits[k]
            return 0


scan_limiter = RateLimiter(settings.SCANS_PER_IP, settings.RATE_WINDOW_SECONDS)
compare_limiter = RateLimiter(settings.COMPARES_PER_IP, settings.RATE_WINDOW_SECONDS)
scan_slots = threading.BoundedSemaphore(settings.MAX_CONCURRENT_SCANS)


def client_ip(request: Request):
    # uvicorn runs with --proxy-headers behind Caddy, so this is the real client address.
    return request.client.host if request.client else "unknown"


def enforce(limiter, request, what):
    wait = limiter.check(client_ip(request))
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many {what} from your address. Try again in {max(1, wait // 60 + (wait % 60 > 0))} min.",
            headers={"Retry-After": str(wait)},
        )


class CompareRequest(BaseModel):
    token_a: str = Field(min_length=32, max_length=44)
    token_b: str = Field(min_length=32, max_length=44)


@app.get("/api")
def root():
    return {"name": "PvP Scanner API", "status": "running"}


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "healthy", "ai": ai.status()}


@app.post("/api/scan/{mint}")
def scan(mint: str, request: Request):
    if not scanner.is_mint(mint):
        raise HTTPException(status_code=400, detail="That is not a valid Solana mint address.")
    enforce(scan_limiter, request, "scans")
    if not scan_slots.acquire(timeout=20):
        raise HTTPException(status_code=503, detail="The scanner is busy right now. Please try again in a minute.")
    try:
        return scanner.scan_token(mint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        log.exception("Scan failed for %s", mint)
        raise HTTPException(status_code=502, detail="Scan failed while contacting market data sources. Please retry.")
    finally:
        scan_slots.release()


@app.post("/api/compare")
def compare(body: CompareRequest, request: Request):
    if not scanner.is_mint(body.token_a) or not scanner.is_mint(body.token_b):
        raise HTTPException(status_code=400, detail="Both values must be valid Solana mint addresses.")
    enforce(compare_limiter, request, "comparisons")
    try:
        return scanner.compare_tokens(body.token_a, body.token_b)
    except Exception:
        log.exception("Comparison failed")
        raise HTTPException(status_code=502, detail="Comparison failed while contacting market data sources. Please retry.")


@app.get("/api/recent")
def get_recent(limit: int = Query(default=25, ge=1, le=200)):
    items = scanner.recent(limit=limit)
    return {"items": items, "count": len(items)}
