"""Runtime configuration, read once from environment variables."""
import os
from pathlib import Path


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


DATA_DIR = Path(os.environ.get("PVP_SCANNER_HOME", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("PVP_SCANNER_DB", DATA_DIR / "pvp_scans.sqlite3"))

# Comma-separated list of origins allowed to call the API from a browser.
# "*" is fine when the frontend is served from the same origin (the default deployment).
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("PVP_ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# Abuse limits for a public deployment.
SCANS_PER_IP = _int("PVP_SCANS_PER_IP", 6)                 # scans per IP per window
COMPARES_PER_IP = _int("PVP_COMPARES_PER_IP", 20)
RATE_WINDOW_SECONDS = _int("PVP_RATE_WINDOW_SECONDS", 600)
MAX_CONCURRENT_SCANS = _int("PVP_MAX_CONCURRENT_SCANS", 4)

# AI review (Claude). Disabled automatically when no API key is configured.
AI_MODEL = os.environ.get("PVP_AI_MODEL", "claude-opus-5-5")
AI_EFFORT = os.environ.get("PVP_AI_EFFORT", "medium")
AI_SHORTLIST = _int("PVP_AI_SHORTLIST", 12)
AI_DAILY_BUDGET_USD = _float("PVP_AI_DAILY_BUDGET_USD", 5.0)
AI_CACHE_HOURS = _int("PVP_AI_CACHE_HOURS", 24)
# USD per million tokens, used only for the daily budget estimate.
AI_PRICE_INPUT = _float("PVP_AI_PRICE_INPUT", 4.0)
AI_PRICE_OUTPUT = _float("PVP_AI_PRICE_OUTPUT", 20.0)


def ai_key_present():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
