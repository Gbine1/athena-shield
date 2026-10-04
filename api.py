"""Athena Shield API. Run one worker for in-memory sessions."""
from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

import alerts
import config
import presets
from clients.guard_client import GuardClient
from clients.llm_client import LLMClient
from security.schemas import CheckInput, Result
from security.service import ShieldService
from security.session_shield import SessionCapacityError
from security.compat import legacy


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(follow_redirects=False) as client:
        app.state.service = ShieldService(GuardClient(client), LLMClient(client))
        yield


app = FastAPI(title='Athena Shield', version='2.0.0', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

FRONTEND_DIST = Path(__file__).parent / 'frontend' / 'dist'
STATIC_DIR = Path(__file__).parent / 'static'

if (FRONTEND_DIST / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=str(FRONTEND_DIST / 'assets')), name='assets')


@app.middleware('http')
async def limit_request(request: Request, call_next):
    if request.method == 'POST':
        size = 0
        parts = []
        async for part in request.stream():
            size += len(part)
            if size > 65536:
                return JSONResponse({'error': 'request_too_large'}, status_code=413)
            parts.append(part)
        request._body = b''.join(parts)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'error': 'invalid_request', 'details': [
        {'location': list(e['loc']), 'type': e['type']} for e in exc.errors()]}, status_code=422)


@app.exception_handler(SessionCapacityError)
async def capacity_error(request, exc):
    return JSONResponse({'error': 'session_capacity', 'retryable': True}, status_code=503)


def service(request):
    return request.app.state.service


@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'Athena Shield', 'version': '2.0.0'}


@app.get('/ready')
async def ready():
    gaps = config.missing()
    return JSONResponse({'ready': not gaps, 'missing_config': gaps, 'scope': 'configuration'}, status_code=503 if gaps else 200)


@app.post('/api/v1/athena/check', response_model=Result)
async def check(body: CheckInput, request: Request):
    return await service(request).check(body.text, body.session_id)


@app.post('/api/v1/demo/compare')
async def compare(body: CheckInput, request: Request):
    return await service(request).compare(body.text, body.session_id)


@app.post('/api/v1/athena/chat')
async def chat(body: CheckInput, request: Request):
    return await service(request).chat(body.text, body.session_id)


class SessionInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.-]+$')


@app.post('/api/v1/athena/reset')
@app.post('/api/reset')
async def reset(body: SessionInput, request: Request):
    await service(request).sessions.reset(body.session_id)
    return {'ok': True}


@app.get('/')
@app.get('/index.html')
async def index():
    if (FRONTEND_DIST / 'index.html').is_file():
        return FileResponse(FRONTEND_DIST / 'index.html')
    return FileResponse(STATIC_DIR / 'index.html')


@app.get('/shield.svg')
async def shield_icon():
    svg_path = FRONTEND_DIST / 'shield.svg'
    if svg_path.is_file():
        return FileResponse(svg_path)
    raise HTTPException(404)


@app.get('/api/presets')
async def get_presets():
    return {'presets': presets.PRESETS, 'missing_config': config.missing()}


@app.get('/api/health')
async def guard_health(request: Request):
    return {'guard': await service(request).guard.get('/health'), 'missing_config': config.missing(),
            'fail_open': False, 'model': config.LLM_MODEL}


@app.get('/api/usage')
async def usage(request: Request):
    return await service(request).guard.get('/v1/usage')


class LegacyInput(CheckInput):
    reset: bool = False
    simulate_partial: bool = False
    mode: str = 'both'


async def prepare(body, request):
    sid = body.session_id or uuid4().hex
    if body.reset:
        await service(request).sessions.reset(sid)
    if body.simulate_partial and config.ATHENA_ENV != 'development':
        raise HTTPException(400, 'Simulation is available only in development.')
    return sid


@app.post('/api/guard-only')
async def guard_only(body: CheckInput, request: Request):
    result = await service(request).guard.check(body.text)
    await asyncio.to_thread(alerts.log_event, 'guard-only', 'allowed' if result.get('ok') and result.get('allowed') else 'blocked', result.get('flags'))
    return {'guard': result, 'text': body.text}


@app.post('/api/armored')
async def armored(body: LegacyInput, request: Request):
    sid = await prepare(body, request)
    partial = {'ok': True, 'allowed': True, 'flags': [], 'status': 'partial', 'checks': {},
               'request_id': 'SIMULATED', 'latency_ms': 0} if body.simulate_partial else None
    result = await service(request).check(body.text, sid, raw_result=partial)
    return legacy(result)


@app.post('/api/chat')
async def legacy_chat(body: LegacyInput, request: Request):
    sid = await prepare(body, request)
    if body.mode == 'guard':
        raise HTTPException(400, 'Guard-only comparison is available through /api/v1/demo/compare. Chat requires Athena screening.')
    if body.simulate_partial:
        result = await armored(body, request)
        return {'stage': 'prompt_blocked', 'prompt_check': result, 'answer': None}
    result = await service(request).chat(body.text, sid)
    result['prompt_check'] = legacy(Result.model_validate(result['prompt_check']))
    if result['stage'] == 'review_required':
        result['stage'] = 'prompt_blocked'
    return result


@app.get('/api/logs')
async def logs():
    return {'events': alerts.recent(), 'counts': alerts.counts(), 'owner': config.OWNER_EMAIL,
            'email_enabled': bool(config.SMTP_USER and config.SMTP_PASS)}


class EmailInput(BaseModel):
    email: str = Field(default='', max_length=254, pattern=r'^[^\r\n]*$')


@app.post('/api/alert-email')
async def set_email(body: EmailInput):
    return {'ok': True, 'owner': alerts.set_owner_email(body.email)}


@app.post('/api/email-log')
async def email_log(body: EmailInput):
    return await asyncio.to_thread(alerts.email_daily_log, body.email or None)


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    uvicorn.run(app, host=config.HOST, port=config.PORT, access_log=False)


if __name__ == '__main__':
    main()

