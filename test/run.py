"""
Read the app log in test/logs.txt and pull out the LATEST Bearer token as
one string, so you can copy it without the wrapped log lines.

    1. Paste the app console output into test/logs.txt (replace everything).
    2. python test/run.py
    3. The token is printed, written to test/token.txt, and copied to your
       clipboard — at ask.py's 🔑 prompt just press Enter.

Only the latest token matters: every app login or token renewal creates a
new session and the server rejects the older ones (SESSION_REPLACED).
"""
import os
import re
import json
import base64
import subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, "logs.txt")
TOKEN = os.path.join(HERE, "token.txt")


def read_log_lines():
    with open(LOGS, encoding="utf-8") as f:
        # "I/flutter (17663): ║ ..." -> "║ ..."
        return [re.sub(r"^I/flutter \(\d+\): ", "", l.rstrip("\n")) for l in f]


def tokens_in_order(lines):
    """Every Bearer token in the log, oldest first. A token is wrapped over
    many '║ ...' lines after '║ Bearer ...'."""
    found = []
    for i, line in enumerate(lines):
        if not line.startswith("║ Bearer "):
            continue
        token = line[len("║ Bearer "):]
        for nxt in lines[i + 1:]:
            if not nxt.startswith("║ "):
                break
            token += nxt[2:]
        token = "".join(token.split())
        if token not in found:
            found.append(token)
    return found


def claims(token):
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def when(value):
    return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S") if value else "?"


def main():
    if not os.path.exists(LOGS) or os.path.getsize(LOGS) == 0:
        print("test/logs.txt is empty — paste the app console output into it first.")
        return

    lines = read_log_lines()
    requests = [re.search(r"api/v2/(\S+)", lines[i + 1]).group(1)
                for i, l in enumerate(lines)
                if "Request ║" in l and i + 1 < len(lines) and "api/v2/" in lines[i + 1]]
    print(f"Log: {len(lines)} lines, {len(requests)} request(s)")
    for name in dict.fromkeys(requests):
        print(f"  • {name}  ×{requests.count(name)}")

    tokens = tokens_in_order(lines)
    if not tokens:
        print("\nNo 'Bearer' token found in test/logs.txt.")
        return

    print(f"\nTokens found: {len(tokens)} (oldest first)")
    for t in tokens:
        c = claims(t)
        print(f"  • issued {when(c.get('iat'))}  expires {when(c.get('exp'))}  session {c.get('sid', '?')[:8]}")

    token = tokens[-1]
    c = claims(token)
    expired = int(c.get("exp", 0)) < datetime.now().timestamp()
    with open(TOKEN, "w", encoding="utf-8") as f:
        f.write(token)
    subprocess.run(["pbcopy"], input=token, text=True)

    print(f"\nLatest token — user {c.get('nameid')}, employee {c.get('employeeId')}, "
          f"company {c.get('selectedCompanyId')}, expires {when(c.get('exp'))}"
          + ("  ⚠️ EXPIRED" if expired else ""))
    print("Saved to test/token.txt and copied to the clipboard.\n")
    print(token)


if __name__ == "__main__":
    main()
