"""Strict async Guard client. Retries are caller-driven to conserve team quota."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

import config


class Check(BaseModel):
    model_config = ConfigDict(extra="allow")
    ran: StrictBool
    flagged: StrictBool


class Verdict(BaseModel):
    model_config = ConfigDict(extra="ignore")
    allowed: StrictBool
    flags: list[str]
    status: Literal["complete", "partial"]
    checks: dict[str, Check]
    request_id: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)


def failure(error: str, **extra) -> dict:
    return {"ok": False, "allowed": None, "flags": [], "status": None,
            "checks": {}, "request_id": None, "latency_ms": None,
            "http_status": None, "error": error, "retry_after": None, **extra}


def retry_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        try:
            return max(0, int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            return None


def parse_verdict(body, http_status=200, retry_after=None, elapsed=0) -> dict:
    rid = body.get("request_id") if isinstance(body, dict) else None
    extra = {"http_status": http_status, "retry_after": retry_after,
             "request_id": rid if isinstance(rid, str) else None, "latency_ms": elapsed}
    if http_status != 200:
        code = {400: "text_required", 401: "unauthorized", 413: "text_too_long",
                429: "rate_limited", 502: "guard_unavailable", 503: "service_busy"}.get(http_status, "http_error")
        if isinstance(body, dict) and body.get("error") == "daily_quota_exceeded":
            code = "daily_quota_exceeded"
        return failure(code, **extra)
    try:
        verdict = Verdict.model_validate(body)
    except ValidationError:
        return failure("invalid_verdict", **extra)
    required = {"injection", "harmful_content", "sensitive_data", "unsafe_links", "prohibited_content"}
    if verdict.status == "complete" and (not required.issubset(verdict.checks) or
            any(not c.ran for c in verdict.checks.values())):
        return failure("incomplete_verdict", **extra)
    if verdict.allowed and (verdict.flags or any(c.flagged for c in verdict.checks.values())):
        return failure("inconsistent_verdict", **extra)
    return {"ok": True, **verdict.model_dump(), "http_status": 200,
            "error": None, "retry_after": retry_after,
            "latency_ms": verdict.latency_ms if verdict.latency_ms is not None else elapsed}


class GuardClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.cooldown_until = 0.0

    async def check(self, text: str, response: bool = False) -> dict:
        if not text.strip() or len(text) > config.GUARD_TEXT_LIMIT:
            return failure("text_required" if not text.strip() else "text_too_long")
        if not config.GUARD_URL or not config.GUARD_TOKEN:
            return failure("not_configured")
        remaining = self.cooldown_until - time.monotonic()
        if remaining > 0:
            return failure("rate_limited", retry_after=max(1, int(remaining + 1)))
        start = time.perf_counter()
        try:
            res = await self.client.post(
                f"{config.GUARD_URL}/v1/check/{'response' if response else 'prompt'}",
                headers={"Authorization": f"Bearer {config.GUARD_TOKEN}"},
                json={"text": text}, timeout=config.HTTP_TIMEOUT)
        except httpx.TimeoutException:
            return failure("timeout")
        except httpx.HTTPError:
            return failure("network")
        try:
            body = res.json()
        except ValueError:
            body = None
        retry = retry_seconds(res.headers.get("Retry-After"))
        if res.status_code == 429:
            self.cooldown_until = time.monotonic() + (retry if retry is not None else 60)
        return parse_verdict(body, res.status_code, retry, round((time.perf_counter() - start) * 1000))

    async def get(self, path: str) -> dict:
        if not config.GUARD_URL:
            return {"ok": False, "error": "not_configured"}
        headers = {"Authorization": f"Bearer {config.GUARD_TOKEN}"} if path != "/health" else {}
        try:
            res = await self.client.get(config.GUARD_URL + path, headers=headers, timeout=config.HTTP_TIMEOUT)
            return {"ok": res.is_success, "http_status": res.status_code, "data": res.json()}
        except (httpx.HTTPError, ValueError):
            return {"ok": False, "error": "guard_unavailable"}
