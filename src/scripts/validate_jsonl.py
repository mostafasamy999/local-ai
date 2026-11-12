"""Check the datasets: every line parses, required keys, no duplicates, no train/eval overlap,
every expected/assistant JSON passes app/schema.py, Arabic/English balance, minimum sizes.

    python scripts/validate_jsonl.py        (exit code 1 on any problem)
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.schema import SchemaError, parse_output  # noqa: E402

SPEC = {
    "training/intent_dataset.jsonl": {"keys": {"text", "lang", "intent"}, "min": 200},
    "training/tool_call_dataset.jsonl": {"keys": {"messages"}, "min": 300},
    "training/response_examples.jsonl": {"keys": {"lang", "action", "api_result", "response"}, "min": 60},
    "evaluation/test_questions.jsonl": {"keys": {"id", "lang", "category", "messages"}, "min": 60},
    "evaluation/expected_results.jsonl": {"keys": {"id", "expected"}, "min": 60},
}
INTENTS = {"get_visits", "get_tasks", "get_main_activities", "get_dashboard", "needs_clarification",
           "refused_write", "out_of_scope"}


def norm(text):
    return " ".join(text.strip().lower().rstrip("?؟.!").split())


def is_arabic(text):
    return any("؀" <= c <= "ۿ" for c in text)


def main():
    errors = []
    data = {}
    for rel in sorted({str(p.relative_to(ROOT)) for p in ROOT.glob("training/*.jsonl")} |
                      {str(p.relative_to(ROOT)) for p in ROOT.glob("evaluation/*.jsonl")} | set(SPEC)):
        path = ROOT / rel
        if not path.exists():
            errors.append("%s: missing" % rel)
            continue
        rows, seen = [], Counter()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                errors.append("%s:%d: empty line" % (rel, n))
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append("%s:%d: bad JSON (%s)" % (rel, n, e))
                continue
            spec = SPEC.get(rel)
            if spec and set(row) != spec["keys"]:
                errors.append("%s:%d: keys %s, expected %s" % (rel, n, sorted(row), sorted(spec["keys"])))
            seen[json.dumps(row, sort_keys=True, ensure_ascii=False)] += 1
            rows.append(row)
        dups = sum(c - 1 for c in seen.values() if c > 1)
        if dups:
            errors.append("%s: %d duplicate line(s)" % (rel, dups))
        if rel in SPEC and len(rows) < SPEC[rel]["min"]:
            errors.append("%s: %d lines, need >= %d" % (rel, len(rows), SPEC[rel]["min"]))
        data[rel] = rows

    # ---- tool calls: roles, system prompt, assistant JSON valid, no duplicate conversations
    system = (ROOT / "config" / "system_prompt.txt").read_text(encoding="utf-8").strip()
    train_user = set()
    convs = Counter()
    langs = Counter()
    for n, row in enumerate(data.get("training/tool_call_dataset.jsonl", []), 1):
        msgs = row["messages"]
        roles = [m["role"] for m in msgs]
        if roles[0] != "system" or roles[-1] != "assistant" or len(roles) not in (3, 5) or \
                roles[1:] != ["user", "assistant"] * ((len(roles) - 1) // 2):
            errors.append("tool_call:%d: bad roles %s" % (n, roles))
            continue
        if msgs[0]["content"] != system:
            errors.append("tool_call:%d: system message differs from config/system_prompt.txt" % n)
        for m in msgs[1:]:
            if m["role"] == "assistant":
                try:
                    parse_output(m["content"])
                except SchemaError as e:
                    errors.append("tool_call:%d: invalid assistant JSON (%s)" % (n, e))
            else:
                train_user.add(norm(m["content"]))
        users = tuple(norm(m["content"]) for m in msgs if m["role"] == "user")
        convs[users] += 1
        langs["ar" if is_arabic(msgs[-2]["content"]) else "en"] += 1
    dup_convs = [u for u, c in convs.items() if c > 1]
    if dup_convs:
        errors.append("tool_call: %d repeated user question(s), e.g. %s" % (len(dup_convs), dup_convs[0]))

    # ---- intents
    intent_text = Counter()
    ilangs = Counter()
    for n, row in enumerate(data.get("training/intent_dataset.jsonl", []), 1):
        if row["intent"] not in INTENTS:
            errors.append("intent:%d: unknown intent %r" % (n, row["intent"]))
        if row["lang"] not in ("ar", "en") or (row["lang"] == "ar") != is_arabic(row["text"]):
            errors.append("intent:%d: lang %r does not match the text" % (n, row["lang"]))
        intent_text[norm(row["text"])] += 1
        ilangs[row["lang"]] += 1
        train_user.add(norm(row["text"]))
    if any(c > 1 for c in intent_text.values()):
        errors.append("intent: duplicate texts")

    # ---- response examples
    rlangs = Counter(r["lang"] for r in data.get("training/response_examples.jsonl", []))

    # ---- evaluation: ids match, expected valid, no overlap with training
    tests = data.get("evaluation/test_questions.jsonl", [])
    expected = {r["id"]: r["expected"] for r in data.get("evaluation/expected_results.jsonl", [])}
    ids = [t["id"] for t in tests]
    if len(ids) != len(set(ids)):
        errors.append("evaluation: duplicate ids")
    if set(ids) != set(expected):
        errors.append("evaluation: ids differ between test_questions and expected_results")
    for exp_id, exp in expected.items():
        try:
            parse_output(json.dumps(exp, ensure_ascii=False))
        except SchemaError as e:
            errors.append("expected %s: invalid (%s)" % (exp_id, e))
    overlap = []
    elangs = Counter()
    for t in tests:
        elangs[t["lang"]] += 1
        for m in t["messages"]:
            if m["role"] == "user" and norm(m["content"]) in train_user:
                overlap.append("%s: %r" % (t["id"], m["content"]))
    for item in overlap:
        errors.append("train/eval overlap %s" % item)

    # ---- balance
    for name, c in (("tool_call", langs), ("intent", ilangs), ("response_examples", rlangs), ("evaluation", elangs)):
        total = sum(c.values()) or 1
        share = c["ar"] / total
        print("%-18s ar=%-4d en=%-4d (%.0f%% Arabic)" % (name, c["ar"], c["en"], share * 100))
        if not 0.45 <= share <= 0.55:
            errors.append("%s: not half Arabic / half English (%d ar, %d en)" % (name, c["ar"], c["en"]))

    for rel, rows in sorted(data.items()):
        print("%-40s %d lines" % (rel, len(rows)))
    if errors:
        print("\nFAILED (%d problem(s)):" % len(errors))
        for e in errors[:50]:
            print("  - " + e)
        sys.exit(1)
    print("\nOK: all files valid, no duplicates, no train/eval overlap.")


if __name__ == "__main__":
    main()
