"""Thin client for the SecureAI Guard API.

Every call returns a normalized dict so the rest of the app never has to care
about HTTP details:

    {
      "ok": bool,          # True if we got a parseable Guard verdict
      "allowed": bool|None,
      "flags": [str],
      "status": "complete"|"partial"|None,
      "checks": {...},
      "request_id": str|None,
      "latency_ms": int|None,
      "http_status": int|None,
      "error": str|None,   # e.g. "rate_limited", "guard_unavailable", "network"
      "retry_after": int|None,
    }
"""
from __future__ import annotations

import requests

import config


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.GUARD_TOKEN}",
        "Content-Type": "application/json",
    }


def _call(path: str, text: str) -> dict:
    url = f"{config.GUARD_URL}{path}"
    try:
        resp = requests.post(
            url, headers=_headers(), json={"text": text},
            timeout=config.HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        return {
            "ok": False, "allowed": None, "flags": [], "status": None,
            "checks": {}, "request_id": None, "latency_ms": None,
            "http_status": None, "error": f"network: {exc.__class__.__name__}",
            "retry_after": None,
        }

    retry_after = resp.headers.get("Retry-After")
    try:
        retry_after = int(retry_after) if retry_after is not None else None
    except ValueError:
        retry_after = None

    # Try to parse JSON regardless of status code.
    try:
        body = resp.json()
    except ValueError:
        body = {}

    if resp.status_code == 200 and isinstance(body, dict) and "allowed" in body:
        return {
            "ok": True,
            "allowed": bool(body.get("allowed")),
            "flags": body.get("flags", []) or [],
            "status": body.get("status"),
            "checks": body.get("checks", {}) or {},
            "request_id": body.get("request_id"),
            "latency_ms": body.get("latency_ms"),
            "http_status": 200,
            "error": None,
            "retry_after": retry_after,
        }

    # Error paths (400/401/413/429/502/503 ...).
    err = None
    if isinstance(body, dict):
        err = body.get("error") or body.get("message")
    err = err or f"http_{resp.status_code}"
    return {
        "ok": False, "allowed": None, "flags": [], "status": None,
        "checks": {}, "request_id": body.get("request_id") if isinstance(body, dict) else None,
        "latency_ms": None, "http_status": resp.status_code, "error": err,
        "retry_after": retry_after,
    }


def check_prompt(text: str) -> dict:
    return _call("/v1/check/prompt", text)


def check_response(text: str) -> dict:
    return _call("/v1/check/response", text)


def usage() -> dict:
    try:
        resp = requests.get(
            f"{config.GUARD_URL}/v1/usage", headers=_headers(),
            timeout=config.HTTP_TIMEOUT,
        )
        return {"ok": resp.ok, "http_status": resp.status_code,
                "data": resp.json() if resp.content else {}}
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def health() -> dict:
    try:
        resp = requests.get(f"{config.GUARD_URL}/health", timeout=config.HTTP_TIMEOUT)
        return {"ok": resp.ok, "http_status": resp.status_code,
                "data": resp.json() if resp.content else {}}
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
