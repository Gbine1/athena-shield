"""Bounded decoding adapted from Model Armor; decoded strings are inspection data."""
import base64
import binascii
import codecs
import re
from urllib.parse import unquote

import config
from security.detection import scan

_B64 = re.compile(r"(?<![\w+/=-])[A-Za-z0-9+/_-]{16,}={0,2}(?![\w+/=-])")
_HEX = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}[\s:]?){8,}(?![0-9a-fA-F])")
_CODES = re.compile(r"(?:\b\d{1,3}\b[\s,]+){8,}\b\d{1,3}\b")


def textual(raw: bytes) -> str | None:
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if s and sum(c.isprintable() or c.isspace() for c in s) / len(s) > .85 and any(c.isalpha() for c in s):
        return s.strip()
    return None


def candidates(text):
    runs = [m.group() for m in _B64.finditer(text)]
    blobs = [("base64", x) for x in runs]
    if len(runs) > 1:
        blobs.append(("split_base64", "".join(runs)))
    for kind, blob in blobs:
        try:
            decoded = textual(base64.b64decode(blob + "=" * (-len(blob) % 4), altchars=b"-_", validate=True))
            if decoded:
                yield kind, decoded
        except (ValueError, binascii.Error):
            pass
    for m in _HEX.finditer(text):
        try:
            decoded = textual(bytes.fromhex(re.sub(r"[\s:]", "", m.group())))
            if decoded:
                yield "hex", decoded
        except ValueError:
            pass
    for m in _CODES.finditer(text):
        nums = [int(n) for n in re.findall(r"\d+", m.group())]
        if all(9 <= n <= 126 for n in nums):
            decoded = textual(bytes(nums))
            if decoded:
                yield "charcodes", decoded
    if re.search(r"(?:%[0-9a-fA-F]{2})", text):
        decoded = unquote(text, errors="strict")
        if decoded != text:
            yield "url", decoded
    rot = codecs.decode(text, "rot_13")
    if rot != text and scan(rot):
        yield "rot13", rot


def inspect(text: str) -> dict:
    seen = {text}
    queue = [(text, 0)]
    variants, evidence = [], []
    total = 0
    exceeded = False
    while queue:
        current, depth = queue.pop(0)
        try:
            for kind, value in candidates(current):
                if value in seen:
                    continue
                if depth >= config.MAX_DECODE_DEPTH or len(variants) >= config.MAX_DECODE_VARIANTS or total + len(value) > config.MAX_DECODE_CHARS:
                    exceeded = True
                    continue
                seen.add(value)
                variants.append(value)
                total += len(value)
                evidence.append({"type": kind, "depth": depth + 1, "decoded_chars": len(value)})
                queue.append((value, depth + 1))
        except UnicodeDecodeError:
            continue
    return {"encoding_detected": bool(variants), "encoding_types": sorted({e['type'] for e in evidence}),
            "decoded_variants": variants, "evidence": evidence, "limit_exceeded": exceeded}
