"""Analysis variants; original user text is never rewritten for the LLM."""
import re
import unicodedata

# Invisible / zero-width / bidi-control characters used to split keywords.
_INVISIBLE = {
    "​", "‌", "‍", "⁠", "﻿", "­", "᠎",
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩",
}

# A small, high-value confusables map (Cyrillic / Greek -> Latin look-alikes).
_CONFUSABLES = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "і": "i", "І": "I", "ѕ": "s", "һ": "h",
    "Α": "A", "Β": "B", "Ε": "E", "Η": "H", "Ι": "I",
    "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P",
    "Τ": "T", "Χ": "X", "ο": "o", "α": "a",
}

# Conservative leetspeak map, applied only to a copy used for detection.
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
                       "7": "t", "@": "a", "$": "s"})

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


_WORDS = ("ignore", "previous", "instructions", "disregard", "system", "reveal",
          "override", "bypass", "disable", "safety", "prompt", "password", "secret",
          "forget", "rules", "restrictions", "developer", "unfiltered")
_SEPARATED = [(word, re.compile(r"(?<!\w)" + r"[\s._/\-]+".join(word) + r"(?!\w)", re.I))
              for word in _WORDS]
_LEET_ALTS = {"i": "[i1!]", "l": "[l1]", "o": "[o0]", "e": "[e3]", "a": "[a4@]",
              "s": "[s5$]", "t": "[t7]"}
_LEET_WORDS = [(word, re.compile(r"(?<!\w)" + "".join(_LEET_ALTS.get(c, c) for c in word) + r"(?!\w)", re.I))
               for word in _WORDS]


def inspect(text: str) -> dict:
    clean, changes = _clean_text(text)
    transformations = [{"type": change} for change in changes]
    for word, rx in _SEPARATED:
        def reconstruct(m):
            transformations.append({"type": "character_separator_reconstruction", "before": m.group(), "after": word})
            return word
        clean = rx.sub(reconstruct, clean)
    for word, rx in _LEET_WORDS:
        def deleet(m):
            if m.group().lower() == word:
                return m.group()
            transformations.append({"type": "contextual_leetspeak", "before": m.group(), "after": word})
            return word
        clean = rx.sub(deleet, clean)
    compact = re.sub(r"\s+", " ", clean).strip()
    if compact != clean:
        transformations.append({"type": "whitespace_normalization"})
    return {"original": text, "clean": compact,
            "variants": [compact] if compact != text else [], "transformations": transformations}


