"""HTTP API for the Activities assistant, for the TalentLink Flutter app on the same Wi-Fi.

Same contract as the old prototype that the app's ActivitiesChatApiService already calls:

    POST /chat   {"message": "...", "session_id": "optional"}
    ->  {"action", "arguments", "needs_clarification", "clarification_question", "refused", "refusal_reason",
         "answer", "request", "lang"}

The first 6 keys are the validated model JSON (what the app maps to its own filter).
Extra keys: "answer" = the sentence built from MOCK data (app/mock_api.py), "request" = endpoint + filters.
Follow-ups ("and yesterday?") work per session_id; without one, per client IP.

    POST /reset  {"session_id": "optional"}  -> clears that conversation
    GET  /health                             -> {"status": "ok", ...}

Run (from src/), one command, the model is loaded inside this process:
    ../.venv/bin/python scripts/api_server.py --adapter adapters/v1
"""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import mock_api  # noqa: E402
from app.agent import Agent  # noqa: E402
from app.llm import LLM, load_config  # noqa: E402
from app.responder import respond  # noqa: E402

KEYS = ("action", "arguments", "needs_clarification", "clarification_question", "refused", "refusal_reason")
MAX_SESSIONS = 200


class State:
    def __init__(self, llm, retries):
        self.llm = llm
        self.retries = retries
        self.lock = threading.Lock()      # one model call at a time (MLX is not thread-safe)
        self.sessions = {}                # session id -> Agent (holds the follow-up context)

    def agent(self, sid):
        if sid not in self.sessions:
            if len(self.sessions) >= MAX_SESSIONS:
                self.sessions.pop(next(iter(self.sessions)))
            self.sessions[sid] = Agent(self.llm.chat, retries=self.retries)
        return self.sessions[sid]


STATE = None
MODEL_INFO = {}


def handle_chat(message, sid):
    with STATE.lock:
        result = STATE.agent(sid).ask(message)
    out = {k: result.output.get(k) for k in KEYS} if result.output else {
        "action": None, "arguments": None, "needs_clarification": True,
        "clarification_question": result.text, "refused": False, "refusal_reason": None}
    if result.request is not None:
        api = mock_api.call(result.request)
        out["answer"] = respond(result.request, api, result.lang)
        out["request"] = {"endpoint": result.request.endpoint, "filters": result.request.filters}
    else:
        out["answer"] = result.text
        out["request"] = None
    out["lang"] = result.lang
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._send(200, dict(status="ok", sessions=len(STATE.sessions), **MODEL_INFO))
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._body()
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"error": "body must be JSON"})
            return
        sid = str(body.get("session_id") or self.client_address[0])
        if self.path == "/reset":
            STATE.sessions.pop(sid, None)
            self._send(200, {"status": "reset", "session_id": sid})
            return
        if self.path != "/chat":
            self._send(404, {"error": "not found"})
            return
        message = (body.get("message") or "").strip()
        if not message:
            self._send(400, {"error": "missing 'message'"})
            return
        t0 = time.time()
        try:
            out = handle_chat(message, sid)
        except Exception as e:   # never crash the server on one bad request
            self._send(500, {"error": str(e)})
            return
        print("[chat] %s %.1fs %r -> %s" % (sid, time.time() - t0, message[:60],
                                           out.get("action") or ("refused" if out.get("refused") else "clarify")),
              flush=True)
        self._send(200, out)

    def log_message(self, fmt, *args):
        pass   # one clean line per chat is printed above


def main():
    global STATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=None, help="LoRA adapter folder, e.g. adapters/v1 (none = base model)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()

    config = load_config()
    print("Loading %s %s ..." % (config["model"]["name"], ("+ " + args.adapter) if args.adapter else "(base)"), flush=True)
    STATE = State(LLM(config, adapter_path=args.adapter), int(config["agent"]["retries_on_invalid"]))
    MODEL_INFO.update(model=config["model"]["name"], adapter=args.adapter, data="mock")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Activities API on http://%s:%d  (POST /chat, POST /reset, GET /health). Data: MOCK." % (
        args.host, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
