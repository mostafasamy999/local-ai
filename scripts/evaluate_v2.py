"""
Evaluate the v2 adapter. The SYSTEM_PROMPT below is copied verbatim
from dataset-build/build_v2.py — it MUST match what the model was
trained with, or results are meaningless (this is exactly what went
wrong when evaluating v1).

Usage:
    cd "/Users/mostafasamy/work/local ai"
    source .venv/bin/activate
    python scripts/evaluate_v2.py
"""

from mlx_lm import load, generate

MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"
ADAPTER = "./adapters/v2"

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

TEST_CASES = [
    # --- close to training examples (sanity check) ---
    ("Show my pending visits yesterday", "seen-pattern"),
    ("Show completed tasks for today", "seen-pattern"),
    # --- generalization: same pattern, different wording ---
    ("Can I see the visits that are still pending from yesterday?", "generalization"),
    ("What tasks got marked done today?", "generalization"),
    ("I need to check high priority visits for the past week", "generalization"),
    # --- missing info: should ask, not guess ---
    ("Show visits", "clarification"),
    ("Show tasks for my team", "clarification (date missing)"),
    # --- multi-turn context ---
    ("Show Ahmed's visits. What date range? Last week.", "context-handling"),
    # --- visit-only filter mentioned on a task: should drop it silently ---
    ("Show my tasks in the Maintenance category this week", "never-invent / silent-drop"),
    # --- unsupported / destructive: should refuse ---
    ("Cancel all of Sara's pending tasks", "refusal"),
    ("Approve this visit for me", "refusal"),
    ("Reassign Ahmed's tasks to Mona", "refusal (unseen verb)"),
    # --- Arabic ---
    ("اعرض المهام العاجلة بتاعة الأسبوع ده", "arabic-generalization"),
    ("وافق على المهمة دي", "arabic-refusal (unseen phrasing)"),
    # --- main list vs normal list distinction ---
    ("I want to edit some visits, show me the main list", "main-list"),
    ("Show my visits for this week", "NOT main-list (should be get_visits)"),
]


def chat(model, tokenizer, user_text):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )
    return generate(model, tokenizer, prompt=prompt, max_tokens=200, verbose=False)


def main():
    print("Loading base model (no adapter)...")
    base_model, tokenizer = load(MODEL)

    print("Loading fine-tuned model (adapter v2)...")
    tuned_model, _ = load(MODEL, adapter_path=ADAPTER)

    for prompt, tag in TEST_CASES:
        print("=" * 90)
        print(f"[{tag}]")
        print(f"PROMPT: {prompt}")
        print("-" * 90)
        base_out = chat(base_model, tokenizer, prompt)
        print("BASE  :", base_out.replace("\n", " ")[:400])
        tuned_out = chat(tuned_model, tokenizer, prompt)
        print("TUNED :", tuned_out.replace("\n", " ")[:400])
        print()


if __name__ == "__main__":
    main()
