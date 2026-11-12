"""
End-to-end pipeline: user message -> fine-tuned model (via mlx_lm.server)
-> map_to_api.py -> ready-to-send E2 request body.

This does NOT call the real TalentLink API (no network from here) — it
stops right before that, printing the exact request body you'd POST to
GetVisitAndTaskAssignedToLoggedInUser. Wire the final requests.post(...)
call in yourself once you're ready to go live (see bottom of file).

Usage:
    python3 scripts/run_pipeline.py "Show my pending visits yesterday"
    python3 scripts/run_pipeline.py "Show visits for Ahmed last week"
"""
import sys
import json
import urllib.request

from map_to_api import (
    SessionContext,
    Directory,
    build_e2_request,
    ClarificationNeeded,
)

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
    """Call the local mlx_lm.server and parse its JSON reply."""
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0.0,
        "stop": ["<|im_end|>"],
    }
    req = urllib.request.Request(
        "http://localhost:8080/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    content = data["choices"][0]["message"]["content"]
    content = content.replace("<|im_end|>", "").strip()
    return json.loads(content)


# ---------------------------------------------------------------------------
# Sample lookup data + session (swap for the real ones when wiring to the app)
# ---------------------------------------------------------------------------
def default_directory() -> Directory:
    return Directory(
        allowed_companies=[
            {"companyId": 1, "parentId": 0, "companyName": "الشركة الرئيسية"},
            {"companyId": 3, "parentId": 1, "companyName": "شركه اى ليد"},
            {"companyId": 6, "parentId": 1, "companyName": "حلول جالاكسي الذكية"},
        ],
        allowed_employees=[
            {"companyId": 3, "employeeId": 12, "employeeName": "Ahmed Anwar "},
            {"companyId": 6, "employeeId": 316, "employeeName": "Yousef Galaxy "},
            {"companyId": 6, "employeeId": 160, "employeeName": "kiro eissa "},
            {"companyId": 6, "employeeId": 331, "employeeName": "Ahmed Adel Shawky"},
            {"companyId": 6, "employeeId": 333, "employeeName": "Ahmed Sayed Saleh"},
        ],
    )


def default_session() -> SessionContext:
    return SessionContext(userId=52, employeeId=600, companyId=10, subscriberId=1)


def main():
    prompt_text = " ".join(sys.argv[1:]) or "Show my pending visits yesterday"
    print("USER MESSAGE:", prompt_text)

    model_output = ask_model(prompt_text)
    print("\nMODEL OUTPUT:")
    print(json.dumps(model_output, ensure_ascii=False, indent=2))

    if model_output.get("refused"):
        print("\n-> Refused:", model_output.get("refusal_reason"))
        return
    if model_output.get("needs_clarification"):
        print("\n-> Needs clarification:", model_output.get("clarification_question"))
        return
    if model_output.get("action") in ("get_main_activities", "get_dashboard"):
        print(f"\n-> '{model_output['action']}' doesn't map to E2 yet (needs its own endpoint mapper).")
        return

    directory = default_directory()
    session = default_session()

    try:
        request_body = build_e2_request(model_output, session, directory)
    except ClarificationNeeded as e:
        print("\n-> Needs clarification (from mapping layer):", e.question)
        return

    print("\nREADY-TO-SEND API REQUEST BODY:")
    print(json.dumps(request_body, ensure_ascii=False, indent=2))

    # --- To actually call the real API, uncomment and fill in a real token: ---
    # import requests
    # resp = requests.post(
    #     "https://main.talentlink360.com/IleadCom_HR_API/api/v2/Mobile/VisitAndTask/GetVisitAndTaskAssignedToLoggedInUser",
    #     json=request_body,
    #     headers={"Authorization": "Bearer <REAL_TOKEN_FROM_LOGIN>"},
    # )
    # print(resp.status_code, resp.text)


if __name__ == "__main__":
    main()
