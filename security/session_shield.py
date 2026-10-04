"""Bounded in-memory security and chat state with TTL, decay and per-session locks."""
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import asyncio
import time
import re

import config
from security.context_adjudicator import quoted_parts
from security.normalization_shield import inspect as normalize
from security.detection import scan


class SessionCapacityError(Exception):
    pass


@dataclass
class Session:
    recent: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    risk_score: float = 0
    suspicious_turns: int = 0
    transformations: list[str] = field(default_factory=list)
    trajectory: list[int] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0

    def snapshot(self):
        fragments = [q for text in self.recent for q in quoted_parts(text)][:20]
        return {"risk_score": round(self.risk_score), "suspicious_turns": self.suspicious_turns,
                "turns_considered": len(self.recent), "detected_intent_fragments": fragments,
                "prior_transformations": self.transformations[-20:], "risk_trajectory": self.trajectory[-10:],
                "last_activity": self.last_activity,
                "security_summary": "Recent user fragments retained for composition checks." if fragments else "No stored instruction fragments."}

    def record(self, text, score, decision, transformations):
        self.risk_score = min(100, max(score, self.risk_score * .8 + score * .35))
        self.suspicious_turns = self.suspicious_turns + 1 if score >= 30 else max(0, self.suspicious_turns - 1)
        self.trajectory = (self.trajectory + [round(self.risk_score)])[-10:]
        self.transformations = (self.transformations + transformations)[-20:]
        self.last_activity = time.time()
        # Rejected requests cannot become executable chat memory or poison future checks.
        if decision in {"ALLOW", "WARN"}:
            self.recent.append(text)
            while len(self.recent) > config.SESSION_MAX_MESSAGES or sum(map(len, self.recent)) > config.SESSION_MAX_CHARS:
                self.recent.pop(0)

    def remember_chat(self, text, answer):
        self.history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": answer}])
        while len(self.history) > config.SESSION_MAX_MESSAGES * 2 or sum(len(x['content']) for x in self.history) > config.SESSION_MAX_CHARS:
            del self.history[:2]


class SessionStore:
    def __init__(self):
        self.sessions: dict[str, Session] = {}

    @asynccontextmanager
    async def acquire(self, sid):
        now = time.time()
        for key, value in list(self.sessions.items()):
            if not value.users and now - value.last_activity >= config.SESSION_TTL_MINUTES * 60:
                del self.sessions[key]
        if sid not in self.sessions:
            if len(self.sessions) >= config.MAX_SESSIONS:
                raise SessionCapacityError("Session capacity reached")
            self.sessions[sid] = Session()
        state = self.sessions[sid]
        state.users += 1
        try:
            async with state.lock:
                now = time.time()
                elapsed = max(0, now - state.last_activity)
                state.risk_score *= .5 ** (elapsed / 900)
                if elapsed >= 900:
                    state.suspicious_turns = max(0, state.suspicious_turns - int(elapsed // 900))
                state.last_activity = now
                yield state
        finally:
            state.users -= 1

    async def reset(self, sid):
        async with self.acquire(sid) as state:
            state.recent.clear()
            state.history.clear()
            state.risk_score = 0
            state.suspicious_turns = 0
            state.transformations.clear()
            state.trajectory.clear()


def inspect(state: Session, text: str) -> dict:
    # Keep the current message complete. History is bounded at insertion, never head-truncated.
    # Include every message that will reach the LLM, even if check-only calls have
    # displaced it from the separate security window.
    prior = list(dict.fromkeys([*(m['content'] for m in state.history), *state.recent]))
    combined = "\n".join([*prior, text])
    fragments = [q for message in prior for q in quoted_parts(normalize(message)['clean'])]
    compose = bool(re.search(r"\b(combine|assemble|concatenate|join)\b", text, re.I))
    reconstructed = " ".join(fragments)
    dangerous = compose and bool(scan(reconstructed))
    summary = ("Previous turns contain fragments combining into an instruction override. "
               "Current message asks to combine them. Reconstructed instruction: " + reconstructed) if dangerous else ""
    return {"combined": combined, "summary": summary, "dangerous_composition": dangerous,
            "fragments": fragments, "turns_considered": len(prior) + 1}
