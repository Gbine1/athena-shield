"""One benign live request; opt in explicitly to spend quota."""
import asyncio
import os
import httpx
import pytest
import config
from clients.guard_client import GuardClient


@pytest.mark.live
@pytest.mark.skipif(os.getenv('RUN_LIVE_GUARD_TESTS') != '1', reason='Live API tests require RUN_LIVE_GUARD_TESTS=1')
def test_guard_benign():
    if not config.GUARD_URL or not config.GUARD_TOKEN:
        pytest.fail('Live tests require GUARD_URL and GUARD_TOKEN')
    async def scenario():
        async with httpx.AsyncClient() as http:
            r=await GuardClient(http).check('What is the capital of Ghana?')
            assert r['ok'] and r['status']=='complete'
    asyncio.run(scenario())
