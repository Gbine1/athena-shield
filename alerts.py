"""Activity log + email alerts.

Every decision Model Armor makes is logged (in memory + activity.log). When a
request is BLOCKED (a bad attempt), the owner gets an email alert — if SMTP is
configured in .env. The whole log can also be emailed as a daily report.
"""
from __future__ import annotations

import json
import smtplib
import threading
import time
from collections import deque
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import config

LOG_PATH = Path(__file__).resolve().parent / "activity.log"
_EVENTS: deque = deque(maxlen=500)
_LOCK = threading.Lock()
_last_email = 0.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log_event(kind, decision, flags=None, reason="", preview="", decoded="", audit=None):
    """Record one check; fire an alert if it was blocked."""
    ev = {"ts": _now(), "kind": kind, "decision": decision,
          "flags": flags or [], "reason": "See decision metadata.",
          "preview": "[payload omitted]" if preview else "", "decoded": ""}
    if audit:
        ev['audit'] = audit
    with _LOCK:
        _EVENTS.appendleft(ev)
        try:
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev) + "\n")
        except OSError:
            pass
    if decision == "blocked":
        _maybe_alert(ev)
    return ev


def recent(n=60):
    with _LOCK:
        return list(_EVENTS)[:n]


def counts():
    with _LOCK:
        total = len(_EVENTS)
        blocked = sum(1 for e in _EVENTS if e["decision"] == "blocked")
    return {"total": total, "blocked": blocked, "allowed": total - blocked}


def set_owner_email(email):
    config.OWNER_EMAIL = (email or "").strip()
    return config.OWNER_EMAIL


def send_email(subject, body, to) -> bool:
    """Send one email via SMTP. Returns False (quietly) if SMTP isn't set up."""
    if not (config.SMTP_USER and config.SMTP_PASS and to):
        return False
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM or config.SMTP_USER
    msg["To"] = to
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(config.SMTP_USER, config.SMTP_PASS)
            s.sendmail(msg["From"], [to], msg.as_string())
        return True
    except Exception:  # noqa: BLE001 — never let email break a request
        return False


def _maybe_alert(ev):
    global _last_email
    to = config.OWNER_EMAIL
    if not to:
        return
    now = time.time()
    if now - _last_email < config.ALERT_MIN_INTERVAL:
        return  # throttle
    subject = f"[Model Armor] Blocked attempt ({', '.join(ev['flags']) or 'policy'})"
    body = (f"Model Armor blocked a request.\n\n"
            f"Time:   {ev['ts']}\nStage:  {ev['kind']}\nFlags:  {ev['flags']}\n"
            f"Reason: {ev['reason']}\n\nInput preview:\n{ev['preview']}\n")
    if ev["decoded"]:
        body += f"\nDecoded payload:\n{ev['decoded']}\n"
    if send_email(subject, body, to):
        _last_email = now


def email_daily_log(to=None):
    to = (to or config.OWNER_EMAIL).strip()
    if not to:
        return {"ok": False, "error": "no owner email set"}
    evs = recent(500)
    lines = [f"{e['ts']}  {e['decision'].upper():8} {e['kind']:8} "
             f"{','.join(e['flags']) or '-':24} {e['preview']}" for e in evs]
    c = counts()
    body = (f"Model Armor activity log — {len(evs)} events "
            f"({c['blocked']} blocked, {c['allowed']} allowed)\n\n" + "\n".join(lines))
    ok = send_email("[Model Armor] Activity log", body, to)
    return {"ok": ok, "sent_to": to if ok else None, "events": len(evs),
            "note": None if ok else "Set SMTP_USER / SMTP_PASS in .env to actually send email."}
