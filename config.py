"""Configuration loaded from environment / .env file.

Secrets never live in code. Put real values in `.env` (git-ignored) or export
them in your shell before running. See `.env.example`.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"


load_dotenv(_ENV_PATH, override=False)


# --- Guard API -------------------------------------------------------------
GUARD_URL = os.environ.get("GUARD_URL", "").rstrip("/")
GUARD_TOKEN = os.environ.get("GUARD_TOKEN", "")

# --- LLM API (OpenAI-compatible) ------------------------------------------
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_API_URL = os.environ.get("LLM_API_URL", f"{LLM_BASE_URL}/chat/completions")
ATHENA_ENV = os.environ.get("ATHENA_ENV", "development")
SESSION_TTL_MINUTES = max(1, int(os.environ.get("SESSION_TTL_MINUTES", "60")))
SESSION_MAX_MESSAGES = max(1, min(10, int(os.environ.get("SESSION_MAX_MESSAGES", "10"))))
SESSION_MAX_CHARS = max(3999, int(os.environ.get("SESSION_MAX_CHARS", "12000")))
MAX_SESSIONS = max(1, int(os.environ.get("MAX_SESSIONS", "500")))
GUARD_TEXT_LIMIT = 3999
MAX_GUARD_CALLS = max(1, int(os.environ.get("MAX_GUARD_CALLS", "8")))
MAX_DECODE_DEPTH = 3
MAX_DECODE_VARIANTS = 12
MAX_DECODE_CHARS = 16000

# --- Armor policy ----------------------------------------------------------
# When the Guard returns status="partial" or is unavailable, do we allow (open)
# or block (closed)? The whole point of layer 3 is that secure default = closed.
FAIL_OPEN = os.environ.get("FAIL_OPEN", "false").lower() in ("1", "true", "yes")

# How many recent turns to fold into the "effective intent" for layer 2.
CONVO_WINDOW = int(os.environ.get("CONVO_WINDOW", "6"))

# Network timeout (seconds) for outbound calls.
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "20"))

# --- Alerts / email ---
# Owner email gets an alert when a bad attempt is blocked. Can also be set live
# from the UI. Email only actually sends if SMTP_USER/SMTP_PASS are set.
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
ALERT_MIN_INTERVAL = float(os.environ.get("ALERT_MIN_INTERVAL", "8"))  # seconds between emails

# Server
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))


def missing() -> list[str]:
    """Return a list of required settings that are not configured."""
    gaps = []
    if not GUARD_URL:
        gaps.append("GUARD_URL")
    if not GUARD_TOKEN:
        gaps.append("GUARD_TOKEN")
    if not LLM_API_KEY:
        gaps.append("LLM_API_KEY (or OPENAI_API_KEY)")
    return gaps
