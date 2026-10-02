#!/usr/bin/env python3
"""Ad-hoc checker: run any text through the Guard alone and through Model Armor.

    ../.venv/bin/python check.py "some text to test"
    echo "some text" | ../.venv/bin/python check.py

Great for live Q&A on demo day — type whatever a judge suggests and show both
verdicts side by side.
"""
import sys

import armor
import guard

R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"; C = "\033[36m"; GREY = "\033[90m"; B = "\033[1m"; X = "\033[0m"


def main():
    text = " ".join(sys.argv[1:]).strip() or sys.stdin.read().strip()
    if not text:
        print("usage: check.py \"text to test\"")
        return
    print(f"{GREY}input:{X} {text[:120]}{'…' if len(text) > 120 else ''}\n")

    g = guard.check_prompt(text)
    if not g["ok"]:
        print(f"{Y}GUARD alone : ERROR ({g['error']}){X}")
    elif g["allowed"]:
        print(f"{R}{B}GUARD alone : ALLOWED{X}  {GREY}flags={g['flags']} {g.get('latency_ms')}ms{X}")
    else:
        print(f"{G}{B}GUARD alone : BLOCKED{X}  {GREY}flags={g['flags']} {g.get('latency_ms')}ms{X}")

    armor.reset_session("check")
    a = armor.armored_check_prompt("check", text)
    col = G if a["blocked"] else R
    print(f"{col}{B}MODEL ARMOR : {a['decision'].upper()}{X}")
    dec = a["layers"]["normalization"]["decoded"]
    if dec:
        print(f"{C}  ↳ decoded:{X} {GREY}{dec[0][:100]}{X}")
    for r in a["reasons"]:
        print(f"{GREY}  ↳ {r}{X}")


if __name__ == "__main__":
    main()
