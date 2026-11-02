"""
Sanity-check the running mlx_lm.server with the EXACT system prompt
used in training (see dataset-build/build_v2.py).

Usage:
    python scripts/test_server.py "Show my pending visits yesterday"
"""
import sys
import json
import urllib.request

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


def ask(prompt_text):
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
    return content.replace("<|im_end|>", "").strip()


if __name__ == "__main__":
    prompt_text = " ".join(sys.argv[1:]) or "Show my pending visits yesterday"
    print("PROMPT:", prompt_text)
    print("REPLY :", ask(prompt_text))
