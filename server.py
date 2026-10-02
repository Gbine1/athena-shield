"""Model Armor demo server (standard library only).

Routes
  GET  /                   -> web UI
  GET  /api/presets        -> demo attack presets
  GET  /api/health         -> Guard /health + our config status
  GET  /api/usage          -> Guard /v1/usage (quota)
  POST /api/guard-only     -> {text}                 Guard verdict on RAW text
  POST /api/armored        -> {session_id, text, simulate_partial?}  full armor
  POST /api/chat           -> {session_id, text, simulate_partial?}  end-to-end
  POST /api/reset          -> {session_id}            clear a conversation window
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import armor
import config
import guard
import llm
import presets

STATIC_DIR = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    server_version = "ModelArmor/1.0"

    # -- helpers -----------------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt, *args):  # quieter console
        pass

    # -- routing -----------------------------------------------------------
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        if self.path == "/api/presets":
            return self._send_json({"presets": presets.PRESETS,
                                    "missing_config": config.missing()})
        if self.path == "/api/health":
            return self._send_json({
                "guard": guard.health(),
                "missing_config": config.missing(),
                "fail_open": config.FAIL_OPEN,
                "model": config.LLM_MODEL,
            })
        if self.path == "/api/usage":
            return self._send_json(guard.usage())
        return self._send_json({"error": "not_found"}, 404)

    def do_POST(self):
        body = self._read_json()
        if self.path == "/api/guard-only":
            text = (body.get("text") or "").strip()
            if not text:
                return self._send_json({"error": "text_required"}, 400)
            # The "naive" integration: send raw user text straight to the Guard.
            return self._send_json({"guard": guard.check_prompt(text), "text": text})

        if self.path == "/api/armored":
            text = (body.get("text") or "").strip()
            if not text:
                return self._send_json({"error": "text_required"}, 400)
            sid = body.get("session_id") or "default"
            sim = bool(body.get("simulate_partial"))
            return self._send_json(armor.armored_check_prompt(sid, text, sim))

        if self.path == "/api/chat":
            return self._handle_chat(body)

        if self.path == "/api/reset":
            armor.reset_session(body.get("session_id") or "default")
            return self._send_json({"ok": True})

        return self._send_json({"error": "not_found"}, 404)

    # -- end-to-end pipeline ----------------------------------------------
    def _handle_chat(self, body: dict):
        text = (body.get("text") or "").strip()
        if not text:
            return self._send_json({"error": "text_required"}, 400)
        sid = body.get("session_id") or "default"
        sim = bool(body.get("simulate_partial"))

        # 1) Armor the inbound prompt.
        prompt_check = armor.armored_check_prompt(sid, text, sim)
        if prompt_check["blocked"]:
            return self._send_json({
                "stage": "prompt_blocked",
                "prompt_check": prompt_check,
                "answer": None,
                "response_check": None,
            })

        # 2) Call the LLM.
        completion = llm.complete(text)
        if not completion["ok"]:
            return self._send_json({
                "stage": "llm_error",
                "prompt_check": prompt_check,
                "answer": None,
                "error": completion["error"],
                "response_check": None,
            })

        # 3) Armor the outbound response.
        response_check = armor.armored_check_response(completion["text"], sim)
        return self._send_json({
            "stage": "response_blocked" if response_check["blocked"] else "delivered",
            "prompt_check": prompt_check,
            "answer": None if response_check["blocked"] else completion["text"],
            "raw_answer": completion["text"],
            "response_check": response_check,
        })


def main():
    gaps = config.missing()
    print("=" * 64)
    print(" Model Armor  —  SecureAI Guard hardening layer")
    print("=" * 64)
    print(f" Serving UI at   http://{config.HOST}:{config.PORT}")
    print(f" Guard URL       {config.GUARD_URL or '(not set)'}")
    print(f" LLM model       {config.LLM_MODEL}")
    print(f" Fail policy     {'FAIL-OPEN (insecure)' if config.FAIL_OPEN else 'FAIL-CLOSED (secure)'}")
    if gaps:
        print(f" ⚠  Missing config: {', '.join(gaps)} — set them in .env")
    print("=" * 64)
    httpd = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
