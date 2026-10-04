"""Async completion client. No tools or caller-supplied system messages."""
import httpx
import config
from llm import SYSTEM_PROMPT


class LLMClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def complete(self, text, history=None):
        if not config.LLM_API_KEY:
            return {"ok": False, "text": "", "error": "llm_not_configured"}
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *(history or []), {"role": "user", "content": text}]
        try:
            res = await self.client.post(config.LLM_API_URL,
                headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                json={"model": config.LLM_MODEL, "messages": messages, "temperature": .3, "max_tokens": 400},
                timeout=config.HTTP_TIMEOUT)
            if not res.is_success:
                return {"ok": False, "text": "", "error": f"llm_http_{res.status_code}"}
            content = res.json()['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Invalid content")
            return {"ok": True, "text": content, "error": None}
        except httpx.TimeoutException:
            return {"ok": False, "text": "", "error": "llm_timeout"}
        except httpx.HTTPError:
            return {"ok": False, "text": "", "error": "llm_network"}
        except (ValueError, KeyError, IndexError, TypeError):
            return {"ok": False, "text": "", "error": "llm_invalid_response"}
