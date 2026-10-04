# Backend engineering report

## Existing work retained

The original Model Armor decoder, Unicode cleanup, Guard/LLM clients, planted fake
canary, CLI interfaces, presets and optional alert workflow were the starting point.
Useful detection logic was moved into dedicated modules. `armor.py` now adapts the
shared Athena policy to the old result shape, and `server.py` remains the entry point.
The user's `attack_tests.md` and `attack_solutions.md` were not modified.

## Created

- `api.py`: async FastAPI backend and compatibility routes.
- `clients/`: async Guard and LLM clients.
- `security/`: encoding, normalization, context and session modules, plus schemas,
  detection, policy, orchestration and compatibility adapter.
- `tests/unit`, `tests/integration`, `tests/live`, `tests/conftest.py`, `pytest.ini`.
- `requirements.txt`, `architecture.md`, `slides.md`.
- `docs/FINDINGS.md`, this report, and historical README/demo provenance documents.

## Modified

`armor.py`, `guard.py`, `llm.py`, `server.py`, `config.py`, `alerts.py`, `presets.py`,
`demo.py`, `.env.example`, `.gitignore`, `README.md`, `DEMO_COMMANDS.md`.
The frontend file was not changed. No commit or push was performed.

## Implemented findings

1. Bounded encoding inspection, preserving original input.
2. Conservative character-separator and leetspeak reconstruction.
3. Quote-aware context classification and REVIEW without unrestricted execution.
4. Bounded session inspection, fragment composition, risk decay and real chat history.

Also repaired truncation, blocked-output disclosure, malformed verdict handling,
the standalone Dan false positive, unsafe legacy chat bypass and raw payload logging.
The historical CLI example's screened and forwarded payloads now match; the current
four-finding CLI uses safe comparisons rather than unprotected model execution.

## Endpoints

`GET /health`, `GET /ready`, `POST /api/v1/athena/check`,
`POST /api/v1/athena/chat`, `POST /api/v1/athena/reset`,
`POST /api/v1/demo/compare`; existing compatibility/status/log routes remain.

## Validation

- `69 passed, 1 skipped` in the final pytest run. The skipped test requires
  `RUN_LIVE_GUARD_TESTS=1` and valid Guard credentials.
- Real server process started; local `/health` returned Athena Shield 2.0.0.
- Offline demo exercised all four findings with explicitly simulated Guard results.
- All 28 Python source/test files parsed successfully at the syntax checkpoint.
- Credential-pattern scan found no apparent real token/key in project source/docs.
- `git diff --check` passed. No live Guard or LLM calls were made during implementation.

## Remaining scope

Live end-to-end validation needs valid local Guard and LLM configuration. Context
decisions use conservative heuristics; REVIEW holds execution rather than supplying
an automatic analysis answer. State is process-local, and session IDs have no user
ownership binding. The default loopback server is intended for the local demo.
The UI remains the previous version and will be updated separately.

## Run and demonstrate

```powershell
.venv/Scripts/python server.py
.venv/Scripts/python -m pytest -q -p no:cacheprovider
.venv/Scripts/python demo.py --offline --auto
```

With Guard credentials configured, demonstrate each finding separately:

```powershell
.venv/Scripts/python demo.py --act 1 --auto
.venv/Scripts/python demo.py --act 2 --auto
.venv/Scripts/python demo.py --act 3 --auto
.venv/Scripts/python demo.py --act 4 --auto
```

Exact PowerShell API requests, including a benign full Guard–LLM–Guard chat, are in
`DEMO_COMMANDS.md`. Architecture and presentation content are in the two requested
root files, `architecture.md` and `slides.md`.
