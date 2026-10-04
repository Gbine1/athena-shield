from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Decision(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    REVIEW = "REVIEW"
    SAFE_ANALYSIS = "SAFE_ANALYSIS"
    BLOCK = "BLOCK"


class Finding(BaseModel):
    source: str
    category: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    description: str
    evidence: dict = Field(default_factory=dict)


class CheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    text: str = Field(min_length=1, max_length=3999, strict=True)
    session_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")

    @field_validator("text")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class Context(BaseModel):
    context_type: Literal["EXECUTE", "QUOTE", "ANALYZE", "CLASSIFY", "DOCUMENT", "TEACH", "TRANSFORM", "UNKNOWN"]
    quoted_content_detected: bool
    execution_intent: bool
    analysis_intent: bool
    reason: str
    confidence: float = Field(ge=0, le=1)


class Result(BaseModel):
    request_id: str
    decision: Decision
    risk_score: int = Field(ge=0, le=100)
    original_text: str
    normalized_variants: list[str] = Field(default_factory=list)
    decoded_variants: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    context: Context
    guard_result: dict
    guard_results: list[dict] = Field(default_factory=list)
    session: dict
    latency_ms: int
    permitted: bool
