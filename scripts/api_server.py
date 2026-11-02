"""
Local HTTP wrapper around the fine-tuned model, for the TalentLink Flutter
app's chat feature to call over the network.

Exposes:
    POST /chat   {"message": "..."}   ->   the model's raw parsed JSON
    {action, arguments, needs_clarification, clarification_question,
     refused, refusal_reason}   (see specs/v2/activities.md)

This does NOT talk to the real TalentLink API and does NOT apply any
business-rule mapping (date ranges, scope, employee lookup) — that now
lives in the Flutter app itself (NewMapChatIntentToFilterUseCase), so it
can reuse the app's own NewActivitiesFilter / NewActivitiesFilterData
instead of guessing at the same rules a second time here.

Requires mlx_lm.server to already be running on 8080:
    mlx_lm.server --model mlx-community/Qwen2.5-3B-Instruct-4bit \
        --adapter-path ./adapters/current --host 0.0.0.0 --port 8080

Run:
    python3 scripts/api_server.py        # listens on 0.0.0.0:8090
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_SERVER_URL = "http://localhost:8080/v1/chat/completions"
LISTEN_PORT = 8090

SYSTEM_PROMPT = (
    "You are an HR application assistant for TalentLink's Activities module. "
    "Available actions: get_visits, get_tasks, get_main_activities, get_dashboard. "
    "statusId: 1 Pending, 2 In progress, 3 Cancelled, 4 Completed, 5 Rejected, 7 Partially completed. "
    "priorityId: 1 low, 2 medium, 3 high. scope: all, my_team, my_activities, private. "
    "Never invent a value for a field the user didn't mention. "
    "You can only read/search activities — you cannot create, edit, delete, "
    "approve, reschedule, or change the status of anything. "
    "Always reply with ONLY this JSON shape: "
    '{"action": null, "arguments": null, "needs_clarification": false, '
    '"clarification_question": null, "refused": false, "refusal_reason": null}. '
    "Fill action/arguments when you have enough info. Set needs_clarification true "
    "and fill clarification_question when required info (at least a date range) is "
    "missing. Set refused true and fill refusal_reason for anything outside reading "
    "activities. Reply in the user's language for questions/refusals; keep field "
    "names and values in English."
)


def ask_model(prompt_text: str) -> dict:
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0.0,
        "stop": ["<|im_end|>"],
    }
    req = urllib.request.Request(
        MODEL_SERVER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    content = data["choices"][0]["message"]["content"]
    content = content.replace("<|im_end|>", "").strip()
    return json.loads(content)


class ChatHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/chat":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8")) if raw else {}
            message = (body.get("message") or "").strip()
            if not message:
                self._send_json(400, {"error": "missing 'message'"})
                return
            model_output = ask_model(message)
            self._send_json(200, model_output)
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def log_message(self, fmt, *args):
        print("[api_server]", fmt % args)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), ChatHandler)
    print(f"Chat API listening on http://0.0.0.0:{LISTEN_PORT}/chat")
    print(f"Proxying to model server at {MODEL_SERVER_URL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
