# Athena Shield

Athena Shield extends the team's Model Armor backend for SecureAI Hackathon Challenge 3.
It protects meaning across representations, quoted context, and conversations.
The backend is Python 3.11+, FastAPI, Pydantic v2 and async httpx. The existing
browser page remains available; a UI redesign is a separate task.

## Four protections

| Module | What it adds |
|---|---|
| Encoding Shield | Base64 (including URL-safe and nested), hex, decimal character codes, URL and selected ROT13 decoding. Size/depth/count limits; original and revealed representations are screened. |
| Normalization Shield | Unicode NFKC, invisible-character removal, inherited confusable mapping, conservative character-separated instruction words, contextual leetspeak and whitespace normalization. |
| Context Adjudicator | Examines quotation boundaries, analytical framing, negation and execution intent outside quotations. Injection-only research disputes return REVIEW. |
| Session Shield | Bounded recent messages, intent fragments, combined inspection, decaying risk, TTL and delivered LLM conversation history. Per-session locks serialize checks and chat. |

A shared policy aggregates findings and Guard verdicts. The application fails closed
on partial checks, malformed responses, timeouts, quota errors and inspection limits.
`FAIL_OPEN` cannot weaken the new policy or the compatibility API.

```text
User text + bounded session state
  -> original / decoded / normalized representations
  -> context and session analysis
  -> SecureAI Guard prompt checks + shared policy
  -> permitted original user text and delivered history -> LLM
  -> Guard response checks + Athena output inspection
  -> screened answer, or metadata-only refusal
```

Decoded instructions are inspection data. They never replace the original user
message sent to the LLM. Blocked output is omitted from the response and history.

## Evidence

See [docs/FINDINGS.md](docs/FINDINGS.md) and the unchanged `attack_tests.md`.
Your transcript establishes separator/leetspeak bypasses, context false positives,
and individually allowed session fragments. It also shows that the tested Base64,
hex, URL, zero-width and full-width prompts were **blocked**. The earlier teammate
encoding observations remain in `docs/MODEL_ARMOR_ORIGINAL.md` and
`presets.LEGACY_PRESETS`. No claim is made that every encoding bypasses the Guard.

## Install and run

Backend (Python 3.11+). Use `.venv/Scripts/python` on Windows, `.venv/bin/python` on Unix.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env     # add GUARD_URL, GUARD_TOKEN, LLM_API_KEY (+ optional SMTP)
.venv/bin/python server.py            # serves UI + API on http://127.0.0.1:8000
```

Frontend: the backend serves the pre-built `frontend/dist/`. Only rebuild if you change it:

```bash
cd frontend && npm install && npm run build
```

- UI: http://127.0.0.1:8000 · API docs: http://127.0.0.1:8000/docs
- One worker only (sessions are in memory). Docker: `docker build -t athena . && docker run -p 8000:8000 --env-file .env athena`.
- **Email alerts**: set the owner address and send the log from the **Event Stream** page. Real delivery needs SMTP in `.env`; otherwise alerts are recorded in the UI.

Configuration:

- `GUARD_URL`, `GUARD_TOKEN`: supplied Guard endpoint and team token.
- `LLM_API_KEY`: completion credentials; `OPENAI_API_KEY` remains a fallback.
- `LLM_API_URL`: optional full chat-completions endpoint. Otherwise use
  `LLM_BASE_URL` (default `https://api.openai.com/v1`) plus `/chat/completions`.
- `LLM_MODEL`: defaults to the teammate's `gpt-4o-mini` setting.
- `ATHENA_ENV=development`: permits the legacy partial-check simulation.
- `SESSION_TTL_MINUTES=60`, `SESSION_MAX_MESSAGES=10`, `SESSION_MAX_CHARS=12000`.
- `MAX_SESSIONS=500`, `MAX_GUARD_CALLS=8`, `HTTP_TIMEOUT=20`.
- Optional SMTP settings retain the existing owner-alert and email-log functionality.

Environment variables override `.env`. Never commit `.env`.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Local liveness, no network call |
| GET | `/ready` | Configuration readiness (503 if required settings are absent) |
| POST | `/api/v1/athena/check` | Evaluate `{text, session_id?}` |
| POST | `/api/v1/demo/compare` | Raw Guard verdict and Athena result, reusing the raw check |
| POST | `/api/v1/athena/chat` | Gated completion with screened output and conversation history |
| POST | `/api/v1/athena/reset` | Clear security and chat state for `{session_id}` |
| GET | `/api/health`, `/api/usage`, `/api/presets` | Guard health, quota and synthetic examples |

The check response includes `decision`, `permitted`, `risk_score`, original text,
normalized and decoded variants, typed findings, context evidence, all Guard results,
request IDs, session summary and measured latency. Inspection endpoints intentionally
return submitted content to the caller; application audit logs do not.

Decisions:

- `ALLOW`: required checks cleared without additional signals.
- `WARN`: checks cleared, but transformations or intent fragments deserve visibility.
- `REVIEW`: analytical injection dispute or ambiguous risk; completion is held.
- `BLOCK`: detected attack, Guard rejection, incomplete screening or resource limit.
- `SAFE_ANALYSIS`: reserved schema value. This release uses REVIEW, and does not
  implement a restricted analysis execution mode or an approval endpoint.

Only ALLOW and WARN can call the LLM. A request never becomes executable through
an API-supplied mode, system prompt, or simulated verdict. The application exposes
no tools to the model. The old `/api/armored`, `/api/chat`, `/api/reset`, logs and
email routes remain available. Legacy Guard-only chat is disabled; use the safe
comparison endpoint. Legacy UI labels do not yet distinguish REVIEW from BLOCK.

## Tests and demos

```powershell
.venv/Scripts/python -m pytest -q -p no:cacheprovider
.venv/Scripts/python demo.py --offline --auto
```

Normal tests use mocked Guard/LLM clients and forbid network calls. Unit tests,
integration tests and live tests are separated. Live tests are skipped by default:

```powershell
$env:RUN_LIVE_GUARD_TESTS='1'
.venv/Scripts/python -m pytest tests/live -q -p no:cacheprovider
Remove-Item Env:RUN_LIVE_GUARD_TESTS
```

That opt-in test makes one benign Guard request. To compare the four findings live,
run `demo.py --act 1 --auto` through `--act 4 --auto`; see
[DEMO_COMMANDS.md](DEMO_COMMANDS.md) for exact API commands. `--offline` prominently
labels simulated results and is not evidence of a live bypass.

## Logging and limits

Audit records contain request IDs, decisions, risk, finding categories, Guard/Athena
latencies and a session hash. The compatibility activity log contains metadata only;
email alerts likewise omit prompt and response contents. History is in memory and
expires; the local activity file is an append-only demo log, without rotation.

The supplied guide lists a limit below 4,000 characters, 30 requests/minute and
1,000/day. Each different representation may require a Guard call. The comparator
reuses the raw result; `Retry-After` establishes a cooldown instead of a retry storm.
The API accepts up to 3,999 characters per user message. Larger internal inspection
representations are checked in overlapping chunks, with a bounded call budget.
If full screening cannot fit that budget, the request is blocked explicitly.

## Known limitations

This is a local hackathon prototype, not a complete security guarantee. Quote-scope
and fragment composition detection are deterministic heuristics. Common encodings
are supported; arbitrary ciphers and all semantic attacks are not. Context false
positives are held for review rather than automatically answered. Large/complex
histories may exhaust the screening budget. Risk decays with time and benign turns;
it is explanatory evidence and never overrides a current malicious finding.

Sessions are bounded, expire after inactivity and are lost on restart. This release
has no authentication or ownership binding for user-chosen session IDs; keep the
server on loopback. Authentication, shared storage and operational log retention are
future deployment work. Current live bypass rates and LLM compliance need explicit
live validation with valid credentials. The UI and historical pitch notes will be
updated separately.

## Source map

- `api.py`, `server.py`: FastAPI routes, startup and legacy compatibility.
- `security/`: four protection modules, schemas, policy, orchestration and adapter.
- `clients/`: async Guard and LLM clients.
- `armor.py`, `guard.py`, `llm.py`: retained compatibility interfaces and planted demo canary.
- `alerts.py`, `config.py`, `presets.py`: configuration, metadata logs and demo inputs.
- `tests/`: offline regressions plus explicit opt-in live smoke test.
