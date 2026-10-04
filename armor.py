"""Model Armor compatibility API; Athena is the shared security implementation."""
import asyncio
import guard
from security import normalization_shield, encoding_shield
from security.detection import scan
from security.service import ShieldService
from security.session_shield import Session
from security.compat import legacy

class _SyncGuardAdapter:
    async def check(self, text, response=False):
        return guard.check_response(text) if response else guard.check_prompt(text)

_service = ShieldService(_SyncGuardAdapter())

def normalize(text):
    norm = normalization_shield.inspect(text)
    enc = encoding_shield.inspect(norm['clean'])
    return {'original': text, 'clean': norm['clean'], 'decoded': enc['decoded_variants'],
            'transforms': [t['type'] for t in norm['transformations']] + enc['encoding_types'],
            'inspection_text': chr(10).join([text, norm['clean'], *enc['decoded_variants']])}

def local_injection_scan(text):
    hits = scan(normalization_shield.inspect(text)['clean'])
    return {'flagged': bool(hits), 'matches': hits}

def reset_session(session_id):
    asyncio.run(_service.sessions.reset(session_id))

def armored_check_prompt(session_id, text, simulate_partial=False):
    partial = {'ok': True, 'allowed': True, 'flags': [], 'status': 'partial',
               'checks': {}, 'request_id': 'SIMULATED', 'latency_ms': 0} if simulate_partial else None
    return legacy(asyncio.run(_service.check(text, session_id, raw_result=partial)))

def armored_check_response(text, simulate_partial=False):
    partial = {'ok': True, 'allowed': True, 'flags': [], 'status': 'partial',
               'checks': {}, 'request_id': 'SIMULATED', 'latency_ms': 0} if simulate_partial else None
    r = asyncio.run(_service._evaluate(text, 'response', Session(), response=True, raw_result=partial))
    return {'decision': 'allowed' if r.permitted else 'blocked', 'blocked': not r.permitted,
            'reasons': [f.description for f in r.findings], 'guard': r.guard_result,
            'transforms': [], 'decoded': []}
