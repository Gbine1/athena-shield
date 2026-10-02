"""Model Armor: a defense-in-depth wrapper around the SecureAI Guard API.

It addresses three weaknesses a naive Guard integration has:

  Layer 1 - Normalization / de-obfuscation
      The Guard classifies the *literal* text it receives. Attackers hide an
      injection inside base64, ROT13, leetspeak, unicode homoglyphs or
      zero-width characters, so the harmful intent is invisible to the Guard.
      We decode / normalize the text and feed the *revealed* content back to
      the Guard (and to a local detector).

  Layer 2 - Conversation-aware aggregation
      The Guard's own guide says to send "only the newest user message". So an
      injection split across several benign-looking turns is never seen whole.
      We keep a per-session window and build an "effective intent" from the
      recent turns, so the reassembled attack gets checked.

  Layer 3 - Fail-closed policy
      When the Guard returns status="partial" or is unavailable, *your app*
      decides what to do. Failing open silently lets content through. The
      secure default is to fail closed (block) unless explicitly allowed.
"""
from __future__ import annotations

import base64
import codecs
import re
import unicodedata
from collections import deque

import config
import guard

# ---------------------------------------------------------------------------
# Layer 1: normalization / de-obfuscation
# ---------------------------------------------------------------------------

# Invisible / zero-width / bidi-control characters used to split keywords.
_INVISIBLE = {
    "​", "‌", "‍", "⁠", "﻿", "­", "᠎",
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩",
}

# A small, high-value confusables map (Cyrillic / Greek -> Latin look-alikes).
_CONFUSABLES = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "і": "i", "ѕ": "s", "һ": "h",
    "Α": "A", "Β": "B", "Ε": "E", "Η": "H", "Ι": "I",
    "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P",
    "Τ": "T", "Χ": "X", "ο": "o", "α": "a",
}

# Conservative leetspeak map, applied only to a copy used for detection.
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
                       "7": "t", "@": "a", "$": "s"})

_B64_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
_HEX_RE = re.compile(r"(?:[0-9a-fA-F]{2}[\s:]?){16,}")
_CHARCODE_RE = re.compile(r"(?:\b\d{1,3}\b[\s,]+){8,}\b\d{1,3}\b")

# Injection patterns we look for in the *revealed* text. The Guard is still the
# primary detector; this local net just makes the demo self-contained and
# catches decoded payloads immediately.
_INJECTION_PATTERNS = [
    r"ignore (all |your |the )?(previous|above|prior|earlier) (instructions|prompts?|rules?)",
    r"disregard (all |your |the )?(previous|above|prior|system)",
    r"forget (your|all|the|everything)",
    r"you are now (?:a|an|in|dan|developer)",
    r"developer mode",
    r"\bDAN\b",
    r"(reveal|show|print|repeat|leak|expose) (your |the )?(system prompt|instructions|rules|secrets?|api[_ ]?key|password)",
    r"(override|bypass|turn off|disable) (your |the )?(safety|guard|filter|rules|restrictions)",
    r"act as (?:a|an)? ?(?:unfiltered|jailbroken|uncensored)",
    r"pretend (you are|to be) (?:unfiltered|jailbroken|uncensored|free)",
    r"do anything now",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def _looks_textual(data: bytes) -> bool:
    if not data:
        return False
    try:
        s = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(c.isprintable() or c in "\n\r\t " for c in s)
    return printable / len(s) > 0.85 and any(c.isalpha() for c in s)


def _clean_text(text: str) -> tuple[str, list[str]]:
    """Strip invisibles, fold homoglyphs, NFKC-normalize."""
    transforms: list[str] = []
    stripped = "".join(ch for ch in text if ch not in _INVISIBLE)
    if stripped != text:
        transforms.append(f"removed {len(text) - len(stripped)} invisible/zero-width char(s)")
    folded = "".join(_CONFUSABLES.get(ch, ch) for ch in stripped)
    if folded != stripped:
        transforms.append("folded unicode homoglyphs to ASCII look-alikes")
    nfkc = unicodedata.normalize("NFKC", folded)
    if nfkc != folded:
        transforms.append("applied unicode NFKC normalization")
    return nfkc, transforms


def _try_b64(blob: str) -> str | None:
    blob = blob.strip()
    if len(blob) < 16 or len(blob) % 4 != 0:
        return None
    try:
        raw = base64.b64decode(blob, validate=True)
    except (ValueError, Exception):  # noqa: BLE001
        return None
    return raw.decode("utf-8", "replace").strip() if _looks_textual(raw) else None


def _decode_payloads(text: str, _depth: int = 0) -> tuple[list[str], list[str]]:
    """Reveal payloads hidden by encoding. Returns (decoded_texts, transforms).

    Handles the vectors this Guard was observed to miss: base64 (incl. framed,
    nested, and split-across-fragments), hex, and decimal char-codes. Recurses
    so double-encodings unwrap, too.
    """
    decoded: list[str] = []
    transforms: list[str] = []
    if _depth > 3:
        return decoded, transforms

    # --- base64 (individual blobs) ---
    b64_runs = [m.group(0) for m in _B64_RE.finditer(text)]
    for blob in b64_runs:
        payload = _try_b64(blob)
        if payload:
            decoded.append(payload)
            transforms.append("decoded base64 payload")

    # --- base64 split across turns/fragments: concatenate all runs & retry ---
    if len(b64_runs) > 1:
        joined = "".join(b64_runs)
        payload = _try_b64(joined)
        if payload and payload not in decoded:
            decoded.append(payload)
            transforms.append(f"reassembled {len(b64_runs)} base64 fragments and decoded")

    # --- hex ---
    for m in _HEX_RE.finditer(text):
        hx = re.sub(r"[\s:]", "", m.group(0))
        if len(hx) % 2 != 0:
            hx = hx[:-1]
        try:
            raw = bytes.fromhex(hx)
        except ValueError:
            continue
        if _looks_textual(raw):
            decoded.append(raw.decode("utf-8", "replace").strip())
            transforms.append("decoded hex payload")

    # --- decimal char-codes ---
    for m in _CHARCODE_RE.finditer(text):
        nums = [int(n) for n in re.findall(r"\d{1,3}", m.group(0))]
        chars = [chr(n) for n in nums if 9 <= n <= 126]
        if len(chars) >= 8:
            payload = "".join(chars).strip()
            if any(c.isalpha() for c in payload):
                decoded.append(payload)
                transforms.append("decoded decimal char-codes")

    # --- ROT13 (cheap; keep only if it reveals injection wording) ---
    try:
        rot = codecs.decode(text, "rot_13")
        if rot != text and any(rx.search(rot) for rx in _INJECTION_RE):
            decoded.append(rot.strip())
            transforms.append("decoded ROT13 payload")
    except Exception:  # noqa: BLE001
        pass

    # --- recurse: a decoded payload may itself be encoded (nesting) ---
    for payload in list(decoded):
        sub, sub_t = _decode_payloads(payload, _depth + 1)
        for s in sub:
            if s not in decoded:
                decoded.append(s)
                transforms.append("unwrapped nested encoding")

    return decoded, transforms


def normalize(text: str) -> dict:
    """Clean + decode a single piece of text (used for response checks).

    {
      "clean": str,              # invisibles stripped, confusables folded, NFKC
      "decoded": [str],          # payloads revealed from base64/hex/charcodes/...
      "transforms": [str],       # human-readable list of what we did
      "inspection_text": str,    # clean + decoded, for Guard / detector
    }
    """
    clean, transforms = _clean_text(text)
    decoded, dec_transforms = _decode_payloads(clean)
    transforms += dec_transforms

    inspection_text = clean
    if decoded:
        inspection_text = clean + "\n[decoded] " + "\n[decoded] ".join(decoded)

    return {
        "clean": clean,
        "original": text,
        "decoded": decoded,
        "transforms": _dedupe(transforms),
        "inspection_text": inspection_text[:3900],
    }


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def local_injection_scan(text: str) -> dict:
    """Lightweight local injection detector over revealed text."""
    probe = unicodedata.normalize("NFKC", text).translate(_LEET)
    hits = []
    for rx in _INJECTION_RE:
        m = rx.search(probe)
        if m:
            hits.append(m.group(0).strip())
    return {"flagged": bool(hits), "matches": hits}


# ---------------------------------------------------------------------------
# Layer 2: conversation-aware aggregation
# ---------------------------------------------------------------------------

_SESSIONS: dict[str, deque] = {}


def _session(session_id: str) -> deque:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = deque(maxlen=config.CONVO_WINDOW)
    return _SESSIONS[session_id]


def aggregate(session_id: str, clean_text: str) -> dict:
    """Append the new (cleaned) turn and build the effective intent."""
    buf = _session(session_id)
    prior = list(buf)
    buf.append(clean_text)
    effective = " ".join(list(buf))
    return {
        "prior_turns": prior,
        "effective_intent": effective[:3900],
        "turns_considered": len(buf),
    }


def reset_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def armored_check_prompt(session_id: str, text: str,
                         simulate_partial: bool = False) -> dict:
    """Run the full armor over a user prompt and return a decision report."""
    # Layer 1a: clean the new turn. Layer 2: fold it into the session window.
    clean, clean_transforms = _clean_text(text)
    agg = aggregate(session_id, clean)

    # Layer 1b: decode on the AGGREGATE, so payloads split across turns (e.g.
    # base64 fragments) are reassembled and revealed before checking.
    effective = agg["effective_intent"]
    decoded, dec_transforms = _decode_payloads(effective)
    transforms = _dedupe(clean_transforms + dec_transforms)

    submitted = effective
    if decoded:
        submitted = (effective + "\n[decoded] " + "\n[decoded] ".join(decoded))[:3900]

    if simulate_partial:
        guard_result = {
            "ok": True, "allowed": True, "flags": [], "status": "partial",
            "checks": {"injection": {"ran": False}}, "request_id": "SIMULATED",
            "latency_ms": 0, "http_status": 200, "error": None, "retry_after": None,
        }
    else:
        guard_result = guard.check_prompt(submitted)

    local = local_injection_scan(submitted)

    # Decision -------------------------------------------------------------
    reasons: list[str] = []
    blocked = False

    guard_unavailable = (not guard_result["ok"]) or guard_result.get("error")
    guard_partial = guard_result.get("status") == "partial"

    if guard_result.get("allowed") is False:
        blocked = True
        reasons.append(f"Guard flagged reassembled/decoded text: {guard_result.get('flags')}")

    if local["flagged"]:
        blocked = True
        reasons.append(f"Local injection detector matched: {local['matches']}")

    if guard_partial or guard_unavailable:
        if config.FAIL_OPEN:
            reasons.append("Guard was partial/unavailable; FAIL_OPEN=true so NOT blocking (insecure).")
        else:
            blocked = True
            why = "partial checks" if guard_partial else f"unavailable ({guard_result.get('error')})"
            reasons.append(f"Fail-closed: Guard returned {why}; blocking by policy.")

    if not blocked and not reasons:
        reasons.append("All layers clear: normalized text passed Guard and local checks.")

    return {
        "decision": "blocked" if blocked else "allowed",
        "blocked": blocked,
        "reasons": reasons,
        "layers": {
            "normalization": {
                "transforms": transforms,
                "decoded": decoded,
                "clean_preview": clean[:300],
            },
            "aggregation": {
                "turns_considered": agg["turns_considered"],
                "prior_turns": agg["prior_turns"],
                "effective_intent_preview": agg["effective_intent"][:300],
            },
            "policy": {
                "fail_open": config.FAIL_OPEN,
                "guard_partial": guard_partial,
                "guard_unavailable": bool(guard_unavailable),
            },
            "local_detector": local,
        },
        "guard_on_submitted": guard_result,
        "submitted_text_preview": submitted[:300],
    }


def armored_check_response(text: str, simulate_partial: bool = False) -> dict:
    """Run normalization + fail-closed over a model response (no aggregation)."""
    norm = normalize(text)
    if simulate_partial:
        guard_result = {
            "ok": True, "allowed": True, "flags": [], "status": "partial",
            "checks": {}, "request_id": "SIMULATED", "latency_ms": 0,
            "http_status": 200, "error": None, "retry_after": None,
        }
    else:
        guard_result = guard.check_response(norm["inspection_text"])

    reasons: list[str] = []
    blocked = False
    guard_unavailable = (not guard_result["ok"]) or guard_result.get("error")
    guard_partial = guard_result.get("status") == "partial"

    if guard_result.get("allowed") is False:
        blocked = True
        reasons.append(f"Guard flagged response: {guard_result.get('flags')}")
    if guard_partial or guard_unavailable:
        if config.FAIL_OPEN:
            reasons.append("Response check partial/unavailable; FAIL_OPEN=true (insecure).")
        else:
            blocked = True
            reasons.append("Fail-closed: response check partial/unavailable; blocking.")
    if not blocked and not reasons:
        reasons.append("Response cleared normalization + Guard.")

    return {
        "decision": "blocked" if blocked else "allowed",
        "blocked": blocked,
        "reasons": reasons,
        "transforms": norm["transforms"],
        "decoded": norm["decoded"],
        "guard": guard_result,
    }
