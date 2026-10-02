# 🛡 Model Armor — hardening the SecureAI Guard API

**SecureAI Hackathon 2026 · Challenge 3**

Model Armor is a thin, defense-in-depth layer that sits in front of the SecureAI
Guard API (and the LLM). It demonstrates three concrete weaknesses in a *naive*
Guard integration and fixes each one, then wraps the whole thing in a working
Guard → LLM → Guard pipeline with a side-by-side web demo.

```
User ──► [Model Armor pre-hook] ──► Guard /check/prompt ──► LLM API
                                                               │
User ◄── [Model Armor post-hook] ◄── Guard /check/response ◄──┘
```

## The headline weakness (verified live)

**The Guard classifies surface text but does not decode encoded payloads.** We
probed the live Guard and confirmed that malicious content — *including genuinely
harmful content, not just injections* — passes straight through when encoded:

| Vector | Guard verdict on raw text | Armor |
|---|---|---|
| Base64 injection (framed "decode and follow") | ✅ **allowed** | 🛡 blocked |
| Hex-encoded injection (raw) | ✅ **allowed** | 🛡 blocked |
| Decimal char-codes injection | ✅ **allowed** | 🛡 blocked |
| Double / nested base64 | ✅ **allowed** | 🛡 blocked |
| **Harmful content in base64** (bomb-making ask) | ✅ **allowed** | 🛡 blocked |
| Multi-turn **split** base64 (fragment per message) | ✅ **allowed** each | 🛡 blocked on reassembly |
| Plain-text injection (control) | 🚫 blocked | 🛡 blocked |
| Zero-width / homoglyph / base32 / reversed / foreign-language | 🚫 blocked | 🛡 blocked |

So the Guard is actually robust against surface obfuscation (zero-width,
homoglyphs, non-English) — it only falls down when the payload is **encoded into
a different alphabet** it doesn't decode. That is the gap Armor closes.

## The three defense layers

| # | Layer | What it does | Addresses |
|---|---|---|---|
| 1 | **Normalization + decoding** | Strip invisibles, fold homoglyphs (NFKC + confusables), then decode base64 / hex / decimal char-codes / ROT13, recursively for nesting — and check the *revealed* content | the encoding bypass above |
| 2 | **Conversation-aware aggregation** | The Guard's guide says "send only the newest user message", so a payload split across turns is never seen whole. Armor keeps a per-session window, reassembles it, then decodes — catching split-base64 | multi-turn split attacks |
| 3 | **Fail-closed policy** | When the Guard returns `status:"partial"` or is unavailable, Armor blocks by default instead of failing open | insecure default handling |

A small local injection detector runs over the *revealed* text too, so a decoded
payload is caught instantly even if the Guard's own classifier is lenient on it.
Layers 1 (homoglyph/zero-width folding) and the extra normalization are kept as
defense-in-depth even though this particular Guard already catches those — a
different or updated Guard may not.

## Run it

```bash
cd day3-secureai-guard
cp .env.example .env          # then edit .env with the real GUARD_URL / token / LLM key
./run.sh                      # or: ../.venv/bin/python server.py
# open http://127.0.0.1:8000
```

`.env` is git-ignored. **Never commit secrets.** Use your own OpenAI key; treat
the key that was shared in chat as compromised and ask the organizers to rotate it.

## Using the demo

1. **Pick an attack** (presets). Colored bars mark the weakness class.
2. **Compare verdicts** — left panel = Guard alone on raw text (the attack slips
   through); right panel = Guard + Armor (blocked, with a per-layer breakdown).
3. **Run full chat** — end-to-end pipeline: prompt armor → LLM → response armor.
4. For the **multi-turn** preset, use **▶ Run multi-turn sequence** to watch the
   Guard allow each benign fragment while Armor blocks once the attack assembles.
5. The **partial** preset uses `simulate_partial` to show fail-open vs fail-closed
   (clearly labelled as a simulation — the Guard verdict is synthetic there).

## API

| Method | Path | Body | Purpose |
|---|---|---|---|
| POST | `/api/guard-only` | `{text}` | Guard verdict on **raw** text (the naive path) |
| POST | `/api/armored` | `{session_id, text, simulate_partial?}` | Full armor decision + layer report |
| POST | `/api/chat` | `{session_id, text, simulate_partial?}` | End-to-end Guard→LLM→Guard |
| POST | `/api/reset` | `{session_id}` | Clear a conversation window |
| GET | `/api/health` · `/api/usage` · `/api/presets` | — | Status, quota, demo inputs |

## Files

- `config.py` — env/`.env` loading, policy knobs
- `guard.py` — Guard API client (normalized responses, handles 429/5xx/partial)
- `llm.py` — OpenAI-compatible chat client
- `armor.py` — the three layers + orchestration
- `presets.py` — safe, injection-style demo payloads (no real harmful data)
- `server.py` — stdlib HTTP server + routing
- `static/index.html` — the demo UI

## Honesty notes (for the judges)

- Rate limits: ~30 req/min, 1000/day. The compare view makes **2** Guard calls;
  the sequence runner makes 2 per turn. Measured latency is shown per request.
- The local detector is a regex safety net, **not** the main defense — the Guard
  remains the primary classifier; Armor's job is to give it text it can actually read.
- No real personal data is ever sent; all payloads are benign prompt-injection strings.
