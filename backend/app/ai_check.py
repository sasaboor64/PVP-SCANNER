"""Check the Claude setup from the server: python -m app.ai_check

Sends one tiny review request (costs well under one cent) and prints the verdicts.
"""
import json
import logging

from . import ai, db, settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    if not settings.ai_key_present():
        raise SystemExit("ANTHROPIC_API_KEY is not set for this process.")
    db.init()
    target = {"ca": "T", "name": "Moo Deng", "symbol": "MOODENG",
              "description": "The viral baby pygmy hippo from Khao Kheow Open Zoo in Thailand."}
    candidates = [
        {"ca": "A", "name": "Baby Hippo Deng", "symbol": "DENG",
         "description": "Tribute to Moo Deng, the bouncy pygmy hippo of Khao Kheow zoo."},
        {"ca": "B", "name": "Moo Deng", "symbol": "MOODENG", "description": "AI agent trading bot on Solana."},
        {"ca": "C", "name": "Solana Cat", "symbol": "SCAT", "description": "The best cat on Solana."},
    ]
    ai.PROMPT_VERSION = "selftest"  # keep self-test results out of the real cache namespace
    verdicts, status = ai.review(target, candidates)
    print("status:", status, "| model:", settings.AI_MODEL)
    print(json.dumps(verdicts, indent=2))
    print("spent today (est.): $%.4f" % ai.spent_today())
    if status not in ("ok", "cached"):
        raise SystemExit(1)
