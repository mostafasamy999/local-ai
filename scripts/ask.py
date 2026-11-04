"""
One-shot question with everything the app would send, in one JSON file:
    message  - what the user typed
    session  - the request envelope (userId, subscriberId, companyId, langId,
               device fields) + employeeId
    lookups  - categories / priorities / statuses, exactly as the app gets
               them from GetCategoryList / GetPriorityList / GetTaskStatusList
See examples/chat_request.json.

The lookups are used by plain code, not added to the model's prompt: the
model was trained on one fixed system prompt, and changing it would make
its output unreliable. Instead the code:
    - drops a statusId / priorityId the model gave that isn't in the lookups
    - finds a category the user named (visits only) by matching its name
    - uses the lookup's own (localized) status names in the answer

The API call uses "auth": {"baseUrl", "token"} from the file (env vars
TALENTLINK_BASE_URL / TALENTLINK_TOKEN override it). If the token is
missing or the API rejects it (401, e.g. SESSION_REPLACED after the app
logs in again), the script asks for a new one, reads it from the
clipboard, saves it back to the file and retries.

Usage:
    cd "/Users/mostafasamy/work/local ai"
    source .venv/bin/activate
    python scripts/ask.py my_request.json
    python scripts/ask.py my_request.json --debug     # show steps ①②③
    python scripts/ask.py my_request.json --offline   # demo data, no API call
"""
import os
import re
import sys
import json
import base64
import subprocess
import urllib.error
from datetime import datetime

from mlx_lm import load

from evaluate_v2 import MODEL, chat
from map_to_api import SessionContext, Directory, build_e2_request, ClarificationNeeded
from chat_cli import debug, is_arabic, fetch_all, demo_items, write_answer

ADAPTER = "./adapters/v2"
ENVELOPE_KEYS = ["userId", "subscriberId", "companyId", "langId", "deviceTypeCode",
                 "deviceToken", "deviceSerial", "appVersion", "oSVersion"]


def by_id(items):
    return {it["id"]: it.get("name") or "" for it in items or [] if it.get("id") is not None}


def apply_lookups(intent, message, lookups):
    """Check the model's ids against the app's lookups, and fill a category the
    user named. Never invents: anything unknown is dropped, not guessed."""
    args = intent.get("arguments") or {}
    statuses, priorities = by_id(lookups.get("statuses")), by_id(lookups.get("priorities"))

    if args.get("statusId") is not None and statuses and args["statusId"] not in statuses:
        debug(f"   statusId {args['statusId']} not in status lookup → dropped")
        args["statusId"] = None
    if args.get("priorityId") is not None and priorities and args["priorityId"] not in priorities:
        debug(f"   priorityId {args['priorityId']} not in priority lookup → dropped")
        args["priorityId"] = None

    # Tasks have no category (specs/v2/activities.md), so only visits get one.
    if intent.get("action") == "get_visits" and not args.get("categoryId"):
        text = message.lower()
        hits = [c for c in lookups.get("categories") or []
                if c.get("name") and c["name"].strip().lower() in text]
        if len(hits) == 1:
            args["categoryId"] = hits[0]["id"]
            debug(f"   category '{hits[0]['name']}' found in message → categoryId {hits[0]['id']}")

    intent["arguments"] = args
    return intent


def clean_token(token):
    token = (token or "").strip()
    return token[len("Bearer "):].strip() if token.startswith("Bearer ") else token


def token_expiry(token):
    """Read `exp` from the JWT payload (no signature check — just for a hint)."""
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(int(data["exp"]))
    except (IndexError, KeyError, ValueError):
        return None


def ask_for_token(reason):
    """Ask the user for a new token. Read from the clipboard, because macOS
    cuts pasted terminal lines at 1024 chars and the token is ~1900."""
    print(f"\n🔑 {reason}")
    print("   Copy the token from the app log (the part after 'Bearer', or with it),")
    input("   then press Enter here to read it from the clipboard… ")
    text = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    # Copied straight from the log, the token is wrapped over many lines like
    # "I/flutter (17663): ║ QgICAg…" — drop those prefixes, line breaks and spaces.
    text = re.sub(r"I/flutter \(\d+\):", "", text).replace("║", "")
    token = "".join(clean_token(text.strip()).split())
    token = clean_token(token.replace("Bearer", "Bearer ", 1))
    if token.count(".") != 2:
        print("   ✗ Clipboard doesn't look like a token (expected xxx.yyy.zzz). Try again.")
        return None
    exp = token_expiry(token)
    if exp and exp < datetime.now():
        print(f"   ✗ This token expired at {exp}. Copy a newer one.")
        return None
    print(f"   ✓ Token read ({len(token)} chars, valid until {exp or 'unknown'})")
    return token


def save_token(path, request, token):
    """Keep the new token in the request file (gitignored) for the next run."""
    request.setdefault("auth", {})["token"] = token
    with open(path, "w", encoding="utf-8") as f:
        json.dump(request, f, ensure_ascii=False, indent=2)
    print(f"   ✓ Saved to {path}")


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not paths:
        print("Usage: python scripts/ask.py <request.json> [--debug]")
        sys.exit(1)
    with open(paths[0], encoding="utf-8") as f:
        request = json.load(f)

    message = request["message"]
    envelope = request.get("session") or {}
    lookups = request.get("lookups") or {}

    # Server + token: env vars win; otherwise take them from the file's "auth".
    # With a server but no token, ask for one (--offline skips this → demo data).
    auth = request.get("auth") or {}
    if auth.get("baseUrl"):
        os.environ.setdefault("TALENTLINK_BASE_URL", auth["baseUrl"])
    if auth.get("token"):
        os.environ.setdefault("TALENTLINK_TOKEN", clean_token(auth["token"]))
    if os.environ.get("TALENTLINK_BASE_URL") and not os.environ.get("TALENTLINK_TOKEN") \
            and "--offline" not in sys.argv:
        token = None
        while not token:
            token = ask_for_token("No token in the file.")
        os.environ["TALENTLINK_TOKEN"] = token
        save_token(paths[0], request, token)

    online = bool(os.environ.get("TALENTLINK_BASE_URL") and os.environ.get("TALENTLINK_TOKEN")) \
        and "--offline" not in sys.argv
    print("Online — calling", os.environ["TALENTLINK_BASE_URL"] if online
          else "Offline — answers use DEMO DATA (set TALENTLINK_BASE_URL and TALENTLINK_TOKEN for real ones)")

    print(f"Loading {MODEL} with adapter {ADAPTER} ...")
    model, tokenizer = load(MODEL, adapter_path=ADAPTER)

    print("\nyou >", message)
    raw = chat(model, tokenizer, message)
    try:
        intent = json.loads(raw)
    except json.JSONDecodeError:
        print("!! Model reply is NOT valid JSON — raw output:")
        print(raw)
        return
    debug("① model intent:", json.dumps(intent, ensure_ascii=False))

    if intent.get("refused"):
        print("assistant >", intent.get("refusal_reason"))
        return
    if intent.get("needs_clarification"):
        print("assistant >", intent.get("clarification_question"))
        return
    if intent.get("action") not in ("get_visits", "get_tasks"):
        print(f"assistant > (action '{intent.get('action')}' has no API mapping yet — only visits and tasks do)")
        return

    intent = apply_lookups(intent, message, lookups)

    session = SessionContext(
        userId=envelope.get("userId", 0),
        employeeId=envelope.get("employeeId", 0),
        companyId=envelope.get("companyId", 0),
        subscriberId=envelope.get("subscriberId", 0),
        langId=envelope.get("langId", "en"),
    )
    try:
        body = build_e2_request(intent, session, Directory(allowed_companies=[], allowed_employees=[]))
    except ClarificationNeeded as e:
        print("assistant >", e.question)
        return
    # Send the envelope exactly as the app has it (device fields included).
    body.update({k: envelope[k] for k in ENVELOPE_KEYS if k in envelope})

    d = body["data"]
    debug(f"② request: typeId={d['typeId']} statusId={d['statusId']} priorityId={d['priorityId']} "
          f"categoryId={d['categoryId']} from={d['fromDateTime']} to={d['endDateTime']} onlyMe={d['onlyMe']}")

    arabic = is_arabic(message)
    # Lookup names come in the session's language (langId), so only use them
    # when the answer is in that language; otherwise keep the built-in names.
    same_language = (envelope.get("langId", "en") == "ar") == arabic
    status_names = (by_id(lookups.get("statuses")) or None) if same_language else None

    if not online:
        debug("③ no credentials — using demo items instead of the API")
        items = demo_items(body)
        if status_names:
            for it in items:
                it["status"]["name"] = status_names.get(it["status"]["id"], it["status"]["name"])
        print("assistant > [DEMO DATA]", write_answer(intent["action"], items, body, arabic, False, status_names))
        return

    # On 401, ask for a fresh token and retry (up to 3 times). The model's
    # answer is already computed, so a retry doesn't reload or re-run it.
    for attempt in range(3):
        try:
            items, truncated = fetch_all(body)
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            if e.code != 401:
                print(f"③ API error {e.code}: {detail[:300]}")
                return
            reason = ("Session replaced — the app logged in again after this token was taken."
                      if "SESSION_REPLACED" in detail else "Token rejected (401).")
            token = ask_for_token(f"{reason} Paste a token from your latest login.")
            if not token:
                continue
            os.environ["TALENTLINK_TOKEN"] = token
            save_token(paths[0], request, token)
        except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
            print("③ API call failed:", e)
            return
    else:
        print("③ Still no valid token after 3 tries — stopping.")
        return

    debug(f"③ API returned {len(items)} item(s)")
    print("assistant >", write_answer(intent["action"], items, body, arabic, truncated, status_names))


if __name__ == "__main__":
    main()
