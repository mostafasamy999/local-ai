"""Run evaluation/test_questions.jsonl through the model and write evaluation/baseline_report.md.

Single shot per question (no retry, no context merging): this measures the model itself.

    python scripts/evaluate.py                         # base model
    python scripts/evaluate.py --adapter adapters/v1   # later, after fine-tuning (not done yet)
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.llm import LLM, load_config  # noqa: E402
from app.schema import SchemaError, extract_json, parse_output  # noqa: E402


def kind(out):
    if out.get("refused"):
        return "refused"
    if out.get("needs_clarification"):
        return "clarify"
    return out.get("action")


def pct(a, b):
    return "%.1f%% (%d/%d)" % (100.0 * a / b, a, b) if b else "n/a (0/0)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", default="evaluation/baseline_report.md")
    ap.add_argument("--outputs", default="evaluation/baseline_outputs.jsonl")
    args = ap.parse_args()

    tests = [json.loads(l) for l in (ROOT / "evaluation" / "test_questions.jsonl").read_text(encoding="utf-8").splitlines()]
    expected = {}
    for l in (ROOT / "evaluation" / "expected_results.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(l)
        expected[r["id"]] = r["expected"]
    if args.limit:
        tests = tests[:args.limit]

    config = load_config()
    t0 = time.time()
    llm = LLM(config, adapter_path=args.adapter)
    load_s = time.time() - t0

    stats = defaultdict(lambda: defaultdict(int))
    rows = []
    gen_s = 0.0
    for i, t in enumerate(tests, 1):
        exp = expected[t["id"]]
        s = time.time()
        text = llm.chat(t["messages"])
        gen_s += time.time() - s

        json_ok, schema_ok, act_ok, args_ok, err = False, False, False, None, ""
        pred = None
        try:
            extract_json(text)
            json_ok = True
            pred = parse_output(text).to_dict()
            schema_ok = True
        except SchemaError as e:
            err = str(e)
        if pred is not None:
            act_ok = kind(pred) == kind(exp)
            if exp["action"] is not None:
                args_ok = act_ok and pred["arguments"] == exp["arguments"]
        elif exp["action"] is not None:
            args_ok = False

        for group in ("all", t["lang"], "cat:" + t["category"]):
            g = stats[group]
            g["n"] += 1
            g["json"] += json_ok
            g["schema"] += schema_ok
            g["action"] += act_ok
            if args_ok is not None:
                g["args_n"] += 1
                g["args"] += args_ok
        rows.append({"id": t["id"], "lang": t["lang"], "category": t["category"], "raw": text,
                     "json_ok": json_ok, "schema_ok": schema_ok, "action_ok": act_ok, "args_ok": args_ok,
                     "error": err, "expected": exp, "predicted": pred})
        print("[%d/%d] %s %s json=%s schema=%s action=%s args=%s" % (
            i, len(tests), t["id"], t["lang"], json_ok, schema_ok, act_ok, args_ok), flush=True)

    with open(ROOT / args.outputs, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def line(name, g):
        return "| %s | %d | %s | %s | %s | %s |" % (name, g["n"], pct(g["json"], g["n"]), pct(g["schema"], g["n"]),
                                                    pct(g["action"], g["n"]), pct(g["args"], g["args_n"]))

    model = config["model"]["name"] + (" + adapter " + args.adapter if args.adapter else " (base, no fine-tuning)")
    out = [
        "# Baseline evaluation report",
        "",
        "- Date: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "- Model: %s" % model,
        "- Decoding: temperature %s, max_tokens %s, system prompt = config/system_prompt.txt" % (
            config["model"]["temperature"], config["model"]["max_tokens"]),
        "- Questions: %d (evaluation/test_questions.jsonl). Single shot, no retry, no context merging." % len(tests),
        "- Load time %.1f s, generation %.1f s total (%.2f s per question)." % (load_s, gen_s, gen_s / max(len(tests), 1)),
        "",
        "## Metrics",
        "",
        "- **Valid JSON**: the reply contains a parseable JSON object.",
        "- **Schema valid**: it also passes `app/schema.py` (known action, allowed values, consistent flags).",
        "- **Action accuracy**: the right outcome: same action, or refused / clarification when expected.",
        "- **Argument accuracy**: for questions whose expected answer has an action, all arguments match exactly"
        " (every key, nulls included).",
        "",
        "| Group | N | Valid JSON | Schema valid | Action accuracy | Argument accuracy |",
        "|---|---|---|---|---|---|",
        line("All", stats["all"]),
        line("Arabic", stats["ar"]),
        line("English", stats["en"]),
        "",
        "## By category",
        "",
        "| Category | N | Valid JSON | Schema valid | Action accuracy | Argument accuracy |",
        "|---|---|---|---|---|---|",
    ]
    for k in sorted(x for x in stats if x.startswith("cat:")):
        out.append(line(k[4:], stats[k]))
    out += ["", "## Failures (first 25)", ""]
    fails = [r for r in rows if not (r["schema_ok"] and r["action_ok"] and r["args_ok"] in (True, None))]
    for r in fails[:25]:
        q = [m["content"] for m in next(t for t in tests if t["id"] == r["id"])["messages"] if m["role"] == "user"]
        out.append("- **%s** (%s, %s) `%s`" % (r["id"], r["lang"], r["category"], " → ".join(q)))
        out.append("  - expected: `%s`" % json.dumps(r["expected"], ensure_ascii=False))
        out.append("  - got: `%s`%s" % (r["raw"].replace("\n", " ")[:400], ("  (error: %s)" % r["error"]) if r["error"] else ""))
    out += ["", "Raw outputs: `%s`." % args.outputs, ""]
    (ROOT / args.report).write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:22]))


if __name__ == "__main__":
    main()
