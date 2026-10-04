import asyncio
import copy
import pytest
import httpx
import requests
import alerts
import config


def verdict(allowed=True, flags=None, status='complete'):
    flags = flags or []
    return {'ok': True, 'allowed': allowed, 'flags': flags, 'status': status,
            'checks': {k: {'ran': True, 'flagged': k in flags} for k in
                       ['injection', 'harmful_content', 'sensitive_data', 'unsafe_links', 'prohibited_content']},
            'request_id': 'test-request', 'latency_ms': 1, 'error': None}


class FakeGuard:
    def __init__(self, decide=None):
        self.calls = []
        self.decide = decide or (lambda text, response: verdict())

    async def check(self, text, response=False):
        self.calls.append((text, response))
        return copy.deepcopy(self.decide(text, response))

    async def get(self, path):
        return {'ok': True, 'data': {'status': 'ok'}}


class FakeLLM:
    def __init__(self, answer='Accra is the capital of Ghana.'):
        self.calls = []
        self.answer = answer

    async def complete(self, text, history=None):
        self.calls.append((text, copy.deepcopy(history)))
        return {'ok': True, 'text': self.answer}


@pytest.fixture(autouse=True)
def offline_by_default(monkeypatch, request):
    if request.node.get_closest_marker('live'):
        return
    def deny(*args, **kwargs):
        raise AssertionError('Network access is forbidden in offline tests')
    async def deny_async(*args, **kwargs):
        deny()
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', deny_async)
    monkeypatch.setattr(requests.sessions.Session, 'request', deny)
    monkeypatch.setattr(alerts, 'log_event', lambda *a, **k: None)
    monkeypatch.setattr(config, 'GUARD_URL', 'https://guard.test')
    monkeypatch.setattr(config, 'GUARD_TOKEN', 'test-placeholder')
    monkeypatch.setattr(config, 'LLM_API_KEY', 'test-placeholder')
    monkeypatch.setattr(config, 'LLM_API_URL', 'https://llm.test/chat/completions')
