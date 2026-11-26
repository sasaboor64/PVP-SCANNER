"""SQLite storage: scanned tokens, cached AI verdicts and daily AI spend."""
import contextlib
import sqlite3

from .settings import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
  ca TEXT PRIMARY KEY, name TEXT, symbol TEXT, description TEXT, metadata_uri TEXT,
  source_url TEXT, socials_json TEXT, first_seen INTEGER NOT NULL, last_scanned INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ai_verdicts (
  key TEXT PRIMARY KEY, result_json TEXT NOT NULL, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ai_usage (
  day TEXT PRIMARY KEY, calls INTEGER NOT NULL, input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL, cost_usd REAL NOT NULL);
"""


@contextlib.contextmanager
def connect():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def init():
    with connect() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
