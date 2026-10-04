import asyncio
import json
import httpx
import pytest
import config
from clients.guard_client import GuardClient, parse_verdict, retry_seconds
from clients.llm_client import LLMClient
from conftest import verdict


@pytest.mark.parametrize('change', [ {'allowed':'false'}, {'status':'unexpected'}, {'checks':{}},
    {'flags':'injection'}, {'allowed':True,'flags':['injection']}, {'allowed':None}])
def test_bad_verdicts_rejected(change):
    assert not parse_verdict({**verdict(), **change})['ok']


def test_check_not_run_invalidates_complete():
    v=verdict();v['checks']['injection']['ran']=False
    assert not parse_verdict(v)['ok']


@pytest.mark.parametrize('status,error', [(401,'unauthorized'),(413,'text_too_long'),(429,'rate_limited'),(502,'guard_unavailable'),(503,'service_busy')])
def test_http_errors_and_ids(status,error):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(status,json={'request_id':'retained'},headers={'Retry-After':'2'}))) as http:
            r=await GuardClient(http).check('Hello')
            assert r['error']==error and r['request_id']=='retained' and r['retry_after']==2
    asyncio.run(scenario())


def test_cooldown_no_retry_storm():
    async def scenario():
        calls=[]
        def respond(r):
            calls.append(r);return httpx.Response(429,json={'error':'rate_limited'},headers={'Retry-After':'60'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            guard=GuardClient(http)
            await guard.check('Hello');r=await guard.check('Hello again')
            assert len(calls)==1 and r['retry_after']>0
    asyncio.run(scenario())


def test_network_timeout_and_bad_json():
    async def scenario():
        def timeout(request): raise httpx.ReadTimeout('secret should never appear')
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
            r=await GuardClient(http).check('Hello')
            assert r['error']=='timeout' and 'secret' not in str(r)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,text='broken'))) as http:
            assert not (await GuardClient(http).check('Hello'))['ok']
    asyncio.run(scenario())


def test_llm_original_text_history_and_no_tools():
    async def scenario():
        def respond(request):
            data=json.loads(request.content)
            assert data['messages'][-1]['content']=='Original text'
            assert data['messages'][1]['content']=='Prior safe question'
            assert 'tools' not in data
            return httpx.Response(200,json={'choices':[{'message':{'content':'Safe reply'}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            r=await LLMClient(http).complete('Original text',[{'role':'user','content':'Prior safe question'}])
            assert r['ok']
    asyncio.run(scenario())


def test_retry_after_date():
    assert retry_seconds('invalid') is None
    assert retry_seconds('-1')==0
    assert retry_seconds('Wed, 21 Oct 2099 07:28:00 GMT')>0
