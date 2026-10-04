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



def scan(text: str) -> list[str]:
    return [m.group(0) for rx in _INJECTION_RE if (m := rx.search(text))]
