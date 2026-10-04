"""Conservative quote-scope analysis. Disputed Guard blocks require review."""
import re
from security.schemas import Context
from security.detection import scan

_QUOTES = re.compile(r"```[\s\S]*?```|(?<!\w)'[^'\n]+'|\"[^\"\n]+\"|“[^”]+”|‘[^’]+’")
_NEGATION = re.compile(r"\b(?:do not|don't|never)\s+(?:follow|execute|obey|carry out)\b[^.!?]*(?:[.!?]|$)", re.I)
_ACTION = re.compile(r"\b(?:follow|execute|obey|carry out|apply|perform)\b.{0,65}\b(?:instruction|command|quoted|above|below|decoded|result|it|them)\b", re.I)


def quoted_parts(text):
    return [m.group().strip("'\"`“”‘’") for m in _QUOTES.finditer(text)]


def inspect(text: str) -> Context:
    quoted = bool(_QUOTES.search(text))
    outside = _QUOTES.sub(" [quoted data] ", text)
    explicit_inert = bool(_NEGATION.search(outside))
    commands = _NEGATION.sub(" ", outside)
    execute = bool(scan(commands) or _ACTION.search(commands))
    kind = "UNKNOWN"
    # Scope matters: verbs must occur outside the quoted material.
    for label, pattern in [
        ("CLASSIFY", r"\b(classify|categorize|label)\b"),
        ("ANALYZE", r"\b(explain|analy[sz]e|discuss|evaluate)\b"),
        ("DOCUMENT", r"\b(research paper|documentation|report|appears? .{0,20}example)\b"),
        ("TEACH", r"\b(teach|lesson|spell|educational example)\b"),
        ("TRANSFORM", r"\b(translate|encode|decode|transcribe)\b"),
    ]:
        if re.search(pattern, outside, re.I):
            kind = label
            break
    analysis = quoted and kind in {"CLASSIFY", "ANALYZE", "DOCUMENT", "TEACH"} and not execute
    if kind == "TRANSFORM" and quoted and explicit_inert and not execute:
        analysis = True
    if execute:
        kind = "EXECUTE"
    elif kind == "UNKNOWN" and quoted:
        kind = "QUOTE"
    return Context(context_type=kind, quoted_content_detected=quoted,
                   execution_intent=execute, analysis_intent=analysis,
                   reason=("Quoted material is scoped as analysis; any disputed verdict requires review." if analysis
                           else "Execution intent outside quotes." if execute
                           else "No strong evidence establishing an inert analysis request."),
                   confidence=.95 if execute else .9 if analysis and explicit_inert else .8 if analysis else .5)
