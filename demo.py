"""Four-finding comparison demo. Live by default; --offline explicitly mocks Guard."""
import argparse
import asyncio
import json
from uuid import uuid4
import httpx
import presets
from clients.guard_client import GuardClient
from security.service import ShieldService

class DemoGuard:
    async def check(self, text, response=False):
        # Explicit simulation: approximate the recorded finding to demonstrate policy.
        blocked = "Ignore previous instructions" in text and ("Explain why" in text or "base64" not in text)
        flags = ['injection'] if blocked else []
        return {'ok': True, 'allowed': not blocked, 'flags': flags, 'status': 'complete',
                'checks': {}, 'request_id': 'SIMULATED-OFFLINE', 'latency_ms': 0, 'error': None}

async def main_async(args):
    async with httpx.AsyncClient() as http:
        shield = ShieldService(DemoGuard() if args.offline else GuardClient(http))
        print('SIMULATION: all Guard verdicts are mocked.' if args.offline else 'LIVE: uses your team Guard quota; does not call the LLM.')
        for p in presets.PRESETS:
            n=p.get('finding')
            if not n or p['id']=='split' or (args.act and args.act != n):
                continue
            print('\n'+p['label'])
            sid=uuid4().hex
            for text in p['turns']:
                r=await shield.compare(text,sid)
                a=r['athena'];g=r['guard_only']
                print(json.dumps({'guard_allowed':g.get('allowed'), 'guard_error':g.get('error'),
                    'guard_request_id':g.get('request_id'), 'athena':a['decision'],
                    'risk':a['risk_score'], 'session_risk':a['session']['risk_score'],
                    'reasons':[f['description'] for f in a['findings']]},indent=2))
                if not args.auto and not args.offline:
                    input('Press Enter for the next step...')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--act',type=int,choices=[1,2,3,4])
    parser.add_argument('--auto',action='store_true')
    parser.add_argument('--offline',action='store_true')
    asyncio.run(main_async(parser.parse_args()))
