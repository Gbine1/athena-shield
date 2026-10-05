"""Conservative local injection safety net, inherited from Model Armor."""
import re

_INJECTION_PATTERNS = [
    r"ignore (all |your |the )?(previous|above|prior|earlier) (instructions|prompts?|rules?)",
    r"disregard (all |your |the )?(previous|above|prior|system)",
    r"forget (your|all|the|everything)",
    r"you are now (?:a|an|in|dan|developer)",
    r"developer mode",
    r"(reveal|show|print|repeat|leak|expose) (your |the )?(system prompt|instructions|rules|secrets?|api[_ ]?key|password)",
    r"(override|bypass|turn off|disable) (your |the )?(safety|guard|filter|rules|restrictions)",
    r"act as (?:a|an)? ?(?:unfiltered|jailbroken|uncensored)",
    r"pretend (you are|to be) (?:unfiltered|jailbroken|uncensored|free)",
    r"do anything now",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Credential extraction is its own finding: a request for API keys can be
# sensitive even when it does not contain an instruction-override phrase.
# Normalization runs first, so forms such as "a-p-i keys" arrive as "api keys".
_SENSITIVE_OBJECT = r"(?:api\s+keys?|keys?|credentials?|tokens?|passwords?|secrets?)"
_CREDENTIAL_REQUEST_PATTERNS = [
    # Directly asking the assistant for another party's credential material.
    re.compile(
        r"\b(?:give|send|show|tell|share)\s+(?:me|us)\s+"
        r"(?:(?:your|their|the|any|all)\s+)?" + _SENSITIVE_OBJECT + r"\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:provide|list)\s+(?:(?:me|us)\s+)?(?:with\s+)?"
        r"(?:(?:your|their|the|any|all)\s+)?" + _SENSITIVE_OBJECT + r"\b",
        re.IGNORECASE,
    ),
    # These verbs are explicit extraction/disclosure requests; allow brief context.
    re.compile(
        r"\b(?:reveal|expose|print|return|disclose|dump|extract|hand\s+over)\b"
        r".{0,48}\b" + _SENSITIVE_OBJECT + r"\b",
        re.IGNORECASE | re.DOTALL,
    ),
]
_NEGATED_REQUEST_RE = re.compile(
    r"\b(?:do\s+not|don't|never|must\s+not|should\s+not|shouldn't|avoid|"
    r"no\s+need\s+to)\b",
    re.IGNORECASE,
)


def _negated(text: str, start: int) -> bool:
    """Ignore an explicit nearby refusal/prevention within the same sentence."""
    prefix = text[max(0, start - 72):start]
    matches = list(_NEGATED_REQUEST_RE.finditer(prefix))
    if not matches:
        return False
    tail = prefix[matches[-1].end():]
    return not re.search(r"[.!?;\n]", tail)



def scan(text: str) -> list[str]:
    hits = [m.group(0) for rx in _INJECTION_RE if (m := rx.search(text))]
    for pattern in _CREDENTIAL_REQUEST_PATTERNS:
        credential = pattern.search(text)
        if credential and not _negated(text, credential.start()):
            hits.append(credential.group(0))
    return hits
