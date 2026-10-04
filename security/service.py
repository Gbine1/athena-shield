"""Orchestrates four shields, Guard checks and gated conversation delivery."""
import hashlib
import asyncio
import json
import logging
import time
from uuid import uuid4

import config
from clients.guard_client import failure
from security import normalization_shield, encoding_shield, context_adjudicator, session_shield
from security.detection import scan
from security.risk_engine import decide
from security.schemas import Finding, Result, Decision
from security.session_shield import SessionStore, Session

log = logging.getLogger("athena.audit")


def chunks(text):
    if len(text) <= config.GUARD_TEXT_LIMIT:
        return [text]
    step = config.GUARD_TEXT_LIMIT - 200
    return [text[i:i + config.GUARD_TEXT_LIMIT] for i in range(0, len(text), step)]


class ShieldService:
    def __init__(self, guard, llm=None, sessions=None):
        self.guard = guard
        self.llm = llm
        self.sessions = sessions or SessionStore()

    async def check(self, text, session_id=None, raw_result=None):
        sid = session_id or uuid4().hex
        async with self.sessions.acquire(sid) as state:
            return await self._evaluate(text, sid, state, raw_result=raw_result)

    async def _evaluate(self, text, sid, state, response=False, raw_result=None):
        start = time.perf_counter()
        findings = []
        def add(source, category, severity, description, evidence=None, confidence=.95):
            findings.append(Finding(source=source, category=category, severity=severity,
                                    confidence=confidence, description=description, evidence=evidence or {}))

        norm = normalization_shield.inspect(text)
        context = context_adjudicator.inspect(norm['clean'])
        session = session_shield.inspect(state, text) if not response else {
            'combined': text, 'summary': '', 'dangerous_composition': False, 'turns_considered': 1}
        # Raw, normalized, decoded and session representations each receive complete inspection.
        normalized = list(norm['variants'])
        variants = [text, *normalized]
        transformations = list(norm['transformations'])
        if session['combined'] != text:
            variants.append(session['combined'])
        if session['summary']:
            variants.append(session['summary'])
        decoded = []
        decode_evidence = []
        for candidate in list(variants):
            enc = encoding_shield.inspect(candidate)
            if enc['limit_exceeded']:
                add('encoding_shield', 'inspection_limit', 'high', 'Decoding inspection budget exceeded; refusing incomplete screening.')
            for value in enc['decoded_variants']:
                if value not in decoded:
                    decoded.append(value)
            decode_evidence.extend(enc['evidence'])
        if len(decoded) > config.MAX_DECODE_VARIANTS or sum(map(len, decoded)) > config.MAX_DECODE_CHARS:
            add('encoding_shield', 'inspection_limit', 'high', 'Combined decoding budget exceeded.')
        for value in decoded:
            variants.append(value)
            n = normalization_shield.inspect(value)
            normalized.extend(x for x in n['variants'] if x not in normalized)
            variants.extend(n['variants'])
            transformations.extend(n['transformations'])
        # Normalize aggregate too, to catch transformations spread across turns.
        n = normalization_shield.inspect(session['combined'])
        variants.extend(n['variants'])
        normalized.extend(x for x in n['variants'] if x not in normalized)
        if transformations:
            add('normalization_shield', 'obfuscation', 'low', 'Generated normalized inspection representations.', {'transformations': transformations})
        if decoded:
            add('encoding_shield', 'encoding', 'low', 'Decoded content inspected as data.', {'representations': decode_evidence})
        if session['dangerous_composition']:
            add('session_shield', 'session_injection', 'high', 'Current request assembles an instruction override from earlier fragments.')
        elif any(q.lower() in {'ignore', 'previous instructions', 'system prompt', 'disregard'}
                 for q in context_adjudicator.quoted_parts(norm['clean'])) and not context.analysis_intent:
            add('session_shield', 'intent_fragment', 'low', 'Retained an instruction-related fragment for later composition checks.', confidence=.6)
        local_attack = False
        analysis_only = context.analysis_intent
        for candidate in dict.fromkeys(variants):
            hits = scan(candidate)
            if hits:
                local_attack = True
                scoped = context_adjudicator.inspect(candidate)
                if not scoped.analysis_intent or scoped.execution_intent:
                    analysis_only = False
        if context.execution_intent:
            local_attack = True
            analysis_only = False
        if local_attack:
            add('context_adjudicator' if analysis_only else 'local_detector',
                'quoted_injection' if analysis_only else 'injection',
                'medium' if analysis_only else 'high',
                'Injection language is quoted for analysis; review required.' if analysis_only else 'Instruction override detected in an inspected representation.')
        if response:
            from llm import CANARY
            if any(CANARY.split('=', 1)[1] in v for v in variants):
                add('response_shield', 'secret_leak', 'critical', 'Planted demo secret detected in model output.')
        submissions = list(dict.fromkeys(part for v in variants for part in chunks(v) if part.strip()))
        results = []
        if len(submissions) > config.MAX_GUARD_CALLS:
            add('policy', 'inspection_limit', 'high', 'Guard call budget exceeded; refusing incomplete screening.')
            results = [raw_result or failure('inspection_limit')]
        else:
            for i, candidate in enumerate(submissions):
                verdict = raw_result if i == 0 and raw_result is not None else await self.guard.check(candidate, response=response)
                results.append(verdict)
                if not verdict.get('ok') or verdict.get('status') != 'complete':
                    break
        decision, score = decide(findings, results, context, local_attack, analysis_only)
        if any(not r.get('ok') or r.get('status') != 'complete' for r in results):
            add('policy', 'guard_unavailable', 'high', 'Fail-closed: Guard screening was unavailable, malformed or incomplete.')
        elif any(r.get('allowed') is False for r in results):
            add('guard', 'guard_flag', 'high', 'Guard flagged an inspected representation.',
                {'flags': sorted({f for r in results for f in r.get('flags', [])})})
        if not response:
            state.record(text, score, decision.value, [t['type'] for t in transformations])
        snapshot = state.snapshot()
        snapshot.update(session_id=sid, turns_considered=session['turns_considered'],
                        security_summary=session['summary'] or snapshot['security_summary'])
        result = Result(request_id=uuid4().hex, decision=decision, risk_score=score, original_text=text,
                        normalized_variants=list(dict.fromkeys(normalized)), decoded_variants=decoded,
                        findings=findings, context=context, guard_result=results[0], guard_results=results,
                        session=snapshot, latency_ms=round((time.perf_counter()-start)*1000),
                        permitted=decision in {Decision.ALLOW, Decision.WARN})
        audit = {'request_id': result.request_id, 'decision': decision.value,
            'risk_score': score, 'categories': sorted({f.category for f in findings}),
            'guard_request_ids': [r.get('request_id') for r in results],
            'guard_latency_ms': sum(r.get('latency_ms') or 0 for r in results),
            'athena_latency_ms': result.latency_ms, 'session_hash': hashlib.sha256(sid.encode()).hexdigest()[:16]}
        log.info(json.dumps(audit))
        import alerts
        await asyncio.to_thread(alerts.log_event, 'response' if response else 'prompt',
                                'allowed' if result.permitted else 'blocked', audit['categories'], '', '', '', audit)
        return result

    async def compare(self, text, session_id=None):
        raw = await self.guard.check(text)
        result = await self.check(text, session_id, raw_result=raw)
        return {'guard_only': raw, 'athena': result.model_dump(mode='json')}

    async def chat(self, text, session_id=None):
        sid = session_id or uuid4().hex
        async with self.sessions.acquire(sid) as state:
            prompt = await self._evaluate(text, sid, state)
            base = {'session_id': sid, 'prompt_check': prompt.model_dump(mode='json'), 'answer': None}
            if not prompt.permitted:
                return {**base, 'stage': 'review_required' if prompt.decision == Decision.REVIEW else 'prompt_blocked'}
            completion = await self.llm.complete(text, history=list(state.history))
            if not completion['ok']:
                return {**base, 'stage': 'llm_error', 'error': completion['error']}
            answer = completion['text']
            output = await self._evaluate(answer, sid, Session(), response=True)
            # Output inspection evidence can itself contain the secret. Return metadata only.
            response_report = {'decision': output.decision.value, 'risk_score': output.risk_score,
                'blocked': not output.permitted, 'request_id': output.request_id,
                'reasons': [f.description for f in output.findings],
                'categories': sorted({f.category for f in output.findings}), 'guard': output.guard_result}
            if not output.permitted:
                return {**base, 'stage': 'response_blocked', 'response_check': response_report}
            state.remember_chat(text, answer)
            return {**base, 'stage': 'delivered', 'answer': answer, 'response_check': response_report}
