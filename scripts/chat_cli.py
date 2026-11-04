"""
Interactive terminal chat with the fine-tuned model — no server needed.

Full flow for every message:
    1. model (adapter) -> intent JSON          (what the user wants)
    2. map_to_api.py   -> E2 request body       (plain code)
    3. TalentLink API  -> real visits/tasks     (only if credentials are set)
    4. write_answer()  -> "You have 5 tasks..." (plain code, never the model,
                                                 so the numbers can't be wrong)

Step 3 needs your own login details as environment variables (set them in
your terminal; they are never written to a file):
    TALENTLINK_BASE_URL     e.g. https://test.talentlink360.com/Developmnet/TalentLink_Dev/TalentLink_Dev_API/api/v2/
    TALENTLINK_TOKEN        the Bearer token from a login
    TALENTLINK_USER_ID, TALENTLINK_EMPLOYEE_ID, TALENTLINK_COMPANY_ID, TALENTLINK_SUBSCRIBER_ID
Without them, step 3 uses made-up DEMO items so you can still see the
final answer; every such answer is tagged [DEMO DATA].

Usage:
    cd "/Users/mostafasamy/work/local ai"
    source .venv/bin/activate
    python scripts/chat_cli.py              # uses adapters/v2, shows only the answer
    python scripts/chat_cli.py --debug      # also shows steps ①②③
    python scripts/chat_cli.py v1           # or another adapter version
"""
import os
import re
import sys
import json
import urllib.error
import urllib.request
from collections import Counter

from mlx_lm import load

from evaluate_v2 import MODEL, chat
from map_to_api import SessionContext, Directory, build_e2_request, ClarificationNeeded

DEBUG = "--debug" in sys.argv
_positional = [a for a in sys.argv[1:] if not a.startswith("--")]
VERSION = _positional[0] if _positional else "v2"
ADAPTER = f"./adapters/{VERSION}"

# Same ids as the system prompt — used to label demo items.
STATUS_NAMES = {1: "Pending", 2: "In progress", 3: "Cancelled", 4: "Completed",
                5: "Rejected", 7: "Partially completed"}

ENDPOINT = "Mobile/VisitAndTask/GetVisitAndTaskAssignedToLoggedInUser"
PAGE_SIZE = 50
MAX_PAGES = 20  # safety cap: at most 1000 items per question

ENV_KEYS = [
    "TALENTLINK_BASE_URL", "TALENTLINK_TOKEN", "TALENTLINK_USER_ID",
    "TALENTLINK_EMPLOYEE_ID", "TALENTLINK_COMPANY_ID", "TALENTLINK_SUBSCRIBER_ID",
]


def is_arabic(text):
    return bool(re.search(r"[؀-ۿ]", text))


def load_session():
    """Read login details from env vars. Returns None if any is missing."""
    missing = [k for k in ENV_KEYS if not os.environ.get(k)]
    if missing:
        return None, missing
    session = SessionContext(
        userId=int(os.environ["TALENTLINK_USER_ID"]),
        employeeId=int(os.environ["TALENTLINK_EMPLOYEE_ID"]),
        companyId=int(os.environ["TALENTLINK_COMPANY_ID"]),
        subscriberId=int(os.environ["TALENTLINK_SUBSCRIBER_ID"]),
    )
    return session, []


def call_api(body):
    """POST one page to E2 and return the `result` list."""
    url = os.environ["TALENTLINK_BASE_URL"].rstrip("/") + "/" + ENDPOINT
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['TALENTLINK_TOKEN']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if not data.get("success", True):
        raise RuntimeError(data.get("responseMessage") or data.get("error") or "API returned success=false")
    return data.get("result") or []


def fetch_all(body):
    """Page through E2 until a short page comes back, so the count is the real total."""
    items = []
    body["data"]["pageSize"] = PAGE_SIZE
    for page in range(MAX_PAGES):
        body["data"]["skip"] = page * PAGE_SIZE
        batch = call_api(body)
        items.extend(batch)
        if len(batch) < PAGE_SIZE:
            return items, False
    return items, True  # hit the cap, there may be more


def demo_items(body):
    """Fake API result for offline mode: 3 items that match the request's
    status filter (or a mix if none), dated inside the requested range."""
    data = body["data"]
    status_id = data["statusId"]
    statuses = [status_id] * 3 if status_id else [1, 4, 1]
    day = (data["fromDateTime"] or data["endDateTime"] or "")[:10]
    kind = "Visit" if data["typeId"] == 2 else "Task"
    return [
        {"masterName": f"Demo {kind} {i}", "dateStr": day,
         "status": {"id": s, "name": STATUS_NAMES.get(s, "?")}}
        for i, s in enumerate(statuses, 1)
    ]


def write_answer(action, items, body, arabic, truncated):
    """Turn the API list into a sentence. Counting is done here, not by the model."""
    data = body["data"]
    start = (data["fromDateTime"] or "")[:10] or "…"
    end = (data["endDateTime"] or "")[:10] or "…"
    n = len(items)
    by_status = Counter((it.get("status") or {}).get("name") or "?" for it in items)
    breakdown = ", ".join(f"{count} {name}" for name, count in by_status.most_common())

    if arabic:
        noun = "زيارة" if action == "get_visits" else "مهمة"
        if n == 0:
            text = f"مفيش أي {noun} من {start} لحد {end}."
        else:
            text = f"عندك {n} {noun} من {start} لحد {end}: {breakdown}."
        if truncated:
            text += " (فيه أكتر من كده، دي أول {} بس)".format(n)
    else:
        noun = "visit" if action == "get_visits" else "task"
        plural = noun if n == 1 else noun + "s"
        if n == 0:
            text = f"You have no {plural} between {start} and {end}."
        else:
            text = f"You have {n} {plural} between {start} and {end}: {breakdown}."
        if truncated:
            text += f" (showing the first {n} only — there are more)"

    lines = [text]
    for it in items[:5]:
        status = (it.get("status") or {}).get("name") or ""
        lines.append(f"  • {it.get('dateStr') or it.get('date') or ''}  {it.get('masterName') or ''}  [{status}]")
    if n > 5:
        lines.append(f"  … +{n - 5} more")
    return "\n".join(lines)


def handle(model, tokenizer, user_text, session, directory):
    raw = chat(model, tokenizer, user_text)
    try:
        intent = json.loads(raw)
    except json.JSONDecodeError:
        print("!! Model reply is NOT valid JSON — raw output:")
        print(raw)
        return

    print("① model intent:", json.dumps(intent, ensure_ascii=False))

    if intent.get("refused"):
        print("\nassistant >", intent.get("refusal_reason"))
        return
    if intent.get("needs_clarification"):
        print("\nassistant >", intent.get("clarification_question"))
        return
    if intent.get("action") not in ("get_visits", "get_tasks"):
        print(f"\n(action '{intent.get('action')}' has no API mapping yet — only get_visits / get_tasks do)")
        return

    lookup_session = session or SessionContext(userId=0, employeeId=0, companyId=0, subscriberId=0)
    lookup_session.langId = "ar" if is_arabic(user_text) else "en"
    try:
        body = build_e2_request(intent, lookup_session, directory)
    except ClarificationNeeded as e:
        print("\nassistant >", e.question)
        return

    d = body["data"]
    print(f"② request: typeId={d['typeId']} statusId={d['statusId']} "
          f"from={d['fromDateTime']} to={d['endDateTime']} onlyMe={d['onlyMe']}")

    if session is None:
        print("③ API call skipped (credentials not set). Request body that would be sent:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return

    try:
        items, truncated = fetch_all(body)
    except urllib.error.HTTPError as e:
        print(f"③ API error {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        if e.code == 401:
            print("   → token expired or wrong. Log in again and re-export TALENTLINK_TOKEN.")
        return
    except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
        print("③ API call failed:", e)
        return

    print(f"③ API returned {len(items)} item(s)")
    print("\nassistant >", write_answer(intent["action"], items, body, is_arabic(user_text), truncated))


def main():
    session, missing = load_session()
    if session is None:
        print("Offline mode — missing:", ", ".join(missing))
        print("(model + mapping only; set those env vars to get real answers)\n")
    else:
        print(f"Online mode — calling {os.environ['TALENTLINK_BASE_URL']}\n")

    # Employee-name lookup isn't fetched yet, so "Ahmed's visits" will ask
    # for clarification; "my visits" / team-wide questions work.
    directory = Directory(allowed_companies=[], allowed_employees=[])

    print(f"Loading {MODEL} with adapter {ADAPTER} ...")
    model, tokenizer = load(MODEL, adapter_path=ADAPTER)
    print("Ready. Type a message (empty line or Ctrl+C to quit).\n")

    while True:
        try:
            user_text = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            break
        handle(model, tokenizer, user_text, session, directory)
        print()


if __name__ == "__main__":
    main()
