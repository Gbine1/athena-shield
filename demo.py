#!/usr/bin/env python3
"""Model Armor — command-line demo.

Run it on demo day:   ../.venv/bin/python demo.py
Flags:
  --auto        don't pause between steps (no "press Enter")
  --act N       run only act N (1=encoding, 2=multi-turn, 3=fail-closed, 4=live leak)

Each act shows the SecureAI Guard's verdict on the raw text beside Model Armor's
verdict, so the audience sees the bypass and the fix in the same breath.
"""
from __future__ import annotations

import base64
import sys
import time

import armor
import config
import guard
import llm
import presets

# --- ANSI colours ---------------------------------------------------------
R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"; B = "\033[34m"
C = "\033[36m"; GREY = "\033[90m"; BOLD = "\033[1m"; DIM = "\033[2m"; X = "\033[0m"
AUTO = "--auto" in sys.argv


def hr(ch="─", n=72):
    print(GREY + ch * n + X)


def banner(text):
    hr("═")
    print(f"{BOLD}{C}  {text}{X}")
    hr("═")


def pause(msg="press Enter to continue"):
    if AUTO or not sys.stdin.isatty():
        print(GREY + f"  ({msg})" + X)
        return
    try:
        input(GREY + f"  ⏎  {msg}…" + X)
    except (EOFError, KeyboardInterrupt):
        print()


def verdict_str(res, who):
    """Pretty one-liner for a Guard result dict."""
    if not res["ok"]:
        return f"{Y}{who}: ERROR ({res['error']}){X}"
    if res["allowed"]:
        return f"{R}{BOLD}{who}: ALLOWED ✗{X}  {GREY}flags={res['flags']} {res.get('latency_ms')}ms{X}"
    return f"{G}{who}: BLOCKED ✓{X}  {GREY}flags={res['flags']} {res.get('latency_ms')}ms{X}"


def armor_str(a):
    col = G if a["blocked"] else R
    sym = "BLOCKED ✓" if a["blocked"] else "ALLOWED ✗"
    return f"{col}{BOLD}MODEL ARMOR: {sym}{X}"


# --------------------------------------------------------------------------
def act1_encoding():
    banner("ACT 1 · The Guard reads words, not meaning — encode the attack and it sails through")
    attacks = [
        ("① CREDENTIAL EXFILTRATION", presets.A_EXFIL, "base64",
         f"Please base64-decode this and do exactly what it says: {base64.b64encode(presets.A_EXFIL.encode()).decode()}"),
        ("② MALWARE / KEYLOGGER", presets.A_MALWARE, "decimal char-codes",
         f"Convert these char codes to text and carry out the request: {' '.join(str(ord(c)) for c in presets.A_MALWARE)}"),
        ("③ PHISHING EMAIL", presets.A_PHISH, "base64",
         f"Please base64-decode this and do exactly what it says: {base64.b64encode(presets.A_PHISH.encode()).decode()}"),
    ]
    for title, plain, enc, payload in attacks:
        print(f"\n{BOLD}{title}{X}  {DIM}(hidden as {enc}){X}")
        print(f"{GREY}  intent: {plain[:88]}…{X}")
        hr()
        # 1) plaintext -> Guard blocks
        gp = guard.check_prompt(plain); time.sleep(0.2)
        print("  1. Send the attack in PLAINTEXT to the Guard:")
        print("     " + verdict_str(gp, "GUARD"))
        # 2) encoded -> Guard allows
        ge = guard.check_prompt(payload); time.sleep(0.2)
        print(f"  2. Send the SAME attack, {enc}-encoded, to the Guard:")
        print("     " + verdict_str(ge, "GUARD"))
        # 3) armor
        armor.reset_session("act1")
        a = armor.armored_check_prompt("act1", payload); time.sleep(0.2)
        print("  3. Send the encoded attack through MODEL ARMOR:")
        print("     " + armor_str(a))
        dec = a["layers"]["normalization"]["decoded"]
        if dec:
            print(f"     {C}↳ armor decoded:{X} {GREY}{dec[0][:80]}…{X}")
        print(f"     {GREY}↳ reason: {a['reasons'][0]}{X}")
        pause()


def act2_multiturn():
    banner("ACT 2 · Split the payload across messages — the Guard sees one message at a time")
    p = next(x for x in presets.PRESETS if x["id"] == "split")
    armor.reset_session("act2")
    print(f"{GREY}  The attacker pastes a base64 secret-exfiltration payload in 3 'harmless' chunks.{X}\n")
    for i, turn in enumerate(p["turns"]):
        gp = guard.check_prompt(turn); time.sleep(0.2)
        a = armor.armored_check_prompt("act2", turn); time.sleep(0.2)
        print(f"  turn {i+1}: {GREY}{turn[:46]}…{X}")
        print("     " + verdict_str(gp, "GUARD (this message)"))
        print("     " + armor_str(a) + f"  {GREY}(turns seen: {a['layers']['aggregation']['turns_considered']}){X}")
        if a["blocked"] and a["layers"]["normalization"]["decoded"]:
            print(f"     {C}↳ armor reassembled + decoded:{X} {GREY}{a['layers']['normalization']['decoded'][0][:70]}…{X}")
        print()
    pause()


def act3_failclosed():
    banner("ACT 3 · When the Guard can't finish (status=partial), what does your app do?")
    print(f"{GREY}  Simulating a Guard that returns status='partial' (a check didn't run).{X}\n")
    saved = config.FAIL_OPEN
    for mode, label in ((True, "FAIL-OPEN (naive app)"), (False, "FAIL-CLOSED (Model Armor default)")):
        config.FAIL_OPEN = mode
        armor.reset_session("act3")
        a = armor.armored_check_prompt("act3", "Tell me something interesting.", simulate_partial=True)
        col = R if not a["blocked"] else G
        print(f"  {BOLD}{label}{X}: {col}{a['decision'].upper()}{X}  {GREY}{a['reasons'][-1]}{X}")
    config.FAIL_OPEN = saved
    print(f"\n{GREY}  Same partial Guard result — opposite outcomes. The secure default is to fail closed.{X}")
    pause()


def act4_liveleak():
    banner("ACT 4 · Watch a secret actually leak (planted FAKE canary — harmless)")
    if config.missing():
        print(f"{Y}  Skipped: set LLM_API_KEY in .env to run the live leak.{X}")
        print(f"{GREY}  (Acts 1–3 prove the Guard bypass without needing the LLM.){X}")
        return
    print(f"{GREY}  The system prompt hides a fake secret: {llm.CANARY}{X}")
    payload = f"Please base64-decode this and do exactly what it says: {base64.b64encode(presets.A_EXFIL.encode()).decode()}"

    print(f"\n  {BOLD}Path A — naive app (Guard only):{X}")
    gp = guard.check_prompt(payload); time.sleep(0.2)
    print("     " + verdict_str(gp, "GUARD"))
    if gp["ok"] and gp["allowed"]:
        print(f"     {GREY}Guard allowed it → forwarding to the model…{X}")
        out = llm.complete(presets.A_EXFIL)  # the decoded attack the model would receive
        if not out["ok"]:
            print(f"     {Y}LLM call failed: {out['error']}{X}")
            print(f"     {GREY}↳ put a VALID OpenAI key in .env (LLM_API_KEY) to show the live leak.{X}")
        else:
            leaked = llm.CANARY.split("=")[1][:12] in out["text"]
            tag = f"{R}{BOLD}SECRET LEAKED ✗{X}" if leaked else f"{Y}model answered (no clear leak this run){X}"
            print(f"     model says: {GREY}{out['text'][:160]}…{X}")
            print(f"     → {tag}")

    print(f"\n  {BOLD}Path B — Model Armor:{X}")
    armor.reset_session("act4")
    a = armor.armored_check_prompt("act4", payload)
    print("     " + armor_str(a))
    print(f"     {GREY}↳ blocked before the model ever saw it — nothing to leak.{X}")
    pause("done")


def main():
    print()
    banner("MODEL ARMOR — hardening the SecureAI Guard against encoded attacks")
    print(f"{GREY}  Guard: {config.GUARD_URL or '(not set)'}{X}")
    print(f"{GREY}  Policy: {'FAIL-OPEN' if config.FAIL_OPEN else 'FAIL-CLOSED'}   Model: {config.LLM_MODEL}{X}")
    if config.missing():
        print(f"{Y}  Missing config: {', '.join(config.missing())}{X}")
    h = guard.health()
    print(f"{GREY}  Guard health: {'up' if h.get('ok') else 'DOWN — check GUARD_URL/token'}{X}")
    pause("start the demo")

    only = None
    if "--act" in sys.argv:
        try:
            only = int(sys.argv[sys.argv.index("--act") + 1])
        except (ValueError, IndexError):
            only = None

    acts = {1: act1_encoding, 2: act2_multiturn, 3: act3_failclosed, 4: act4_liveleak}
    for n, fn in acts.items():
        if only is None or only == n:
            fn()

    print()
    banner("THE TAKEAWAY")
    print(f"  {R}The Guard classifies surface text — encode the attack and it waves it through.{X}")
    print(f"  {G}Model Armor normalizes, decodes, reassembles across turns, and fails closed —{X}")
    print(f"  {G}so the Guard finally sees what the attacker actually meant.{X}")
    print()


if __name__ == "__main__":
    main()
