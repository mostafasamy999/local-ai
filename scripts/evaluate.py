"""
Compare the base model vs the fine-tuned adapter on a fixed set of
test prompts. Some prompts are close to training examples (sanity
check), others are deliberately phrased differently (generalization
check) or outside what v1 supports (refusal check).

Usage:
    cd "/Users/mostafasamy/work/local ai"
    source .venv/bin/activate
    python scripts/evaluate.py
"""

from mlx_lm import load, generate

MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"
ADAPTER = "./adapters/v1"

SYSTEM_PROMPT = (
    "You are an HR application assistant for TalentLink's Activities module. "
    "Available actions: get_visits, get_tasks, get_main_activities, get_dashboard. "
    "statusId: 1 Pending, 2 In progress, 3 Cancelled, 4 Completed, 5 Rejected, 7 Partially completed. "
    "priorityId: 1 low, 2 medium, 3 high. scope: all, my_team, my_activities, private. "
    "Never invent a value. Ask when required information is missing. "
    "You can only read/search activities — refuse create, edit, delete or status-change requests. "
    "When ready, reply with ONLY a JSON object: "
    '{"action": "...", "arguments": {...}, "needs_clarification": false}. '
    "When missing info, reply with ONLY a short plain-text question."
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
    # --- multi-turn context (single-shot prompt simulating it) ---
    ("Show Ahmed's visits. What date range? Last week.", "context-handling"),
    # --- visit-only filter applied to a task: should drop it silently ---
    ("Show my tasks in the Maintenance category this week", "silent-drop-filter"),
    # --- unsupported / destructive: should refuse ---
    ("Cancel all of Sara's pending tasks", "refusal"),
    ("Approve this visit for me", "refusal"),
    # --- Arabic ---
    ("اعرض المهام العاجلة بتاعة الأسبوع ده", "arabic-generalization"),
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

    print("Loading fine-tuned model (adapter v1)...")
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
