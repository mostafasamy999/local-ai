# hr-local-ai: Activities assistant (Qwen, local, read-only)

A local assistant for the TalentLink360 **Activities** module (Visits and Tasks). The user asks in Arabic or
English. The model (`mlx-community/Qwen2.5-3B-Instruct-4bit`) answers with **one JSON object** that names a
read-only action and its filters. Python code validates it, resolves dates, calls the API (a mock for now),
and writes the answer from templates.

```
user text ──► app/llm.py (Qwen) ──► JSON ──► app/schema.py (validate, retry once)
          ──► app/context.py (follow-ups) ──► app/agent.py build_request (dates, endpoint)
          ──► app/mock_api.py (fake endpoint) ──► app/responder.py (AR/EN templates) ──► answer
```

Source of truth: `specs-talentlink/specs/001-activities` (Doc v2.0, CL-10). Nothing here is fine-tuned yet.

## Output contract

```json
{"action": "get_visits | get_tasks | get_main_activities | get_dashboard | null",
 "arguments": {...},
 "needs_clarification": false, "clarification_question": null,
 "refused": false, "refusal_reason": null}
```

| Action | Endpoint (POST) | Arguments |
|---|---|---|
| get_visits | `Mobile/VisitAndTask/GetVisitAndTaskAssignedToLoggedInUser`, typeId 2 | dateRange, fromDate, toDate, statusId, priorityId, scope, search |
| get_tasks | same, typeId 1, no category | same as get_visits |
| get_main_activities | `Mobile/VisitAndTask/GetVisitAndTaskList` | typeId + the get_visits arguments |
| get_dashboard | `Mobile/VisitAndTask/GetTaskAndVisitDashboard` | dateRange, fromDate, toDate, statusId, scope |

The full rules are in [config/system_prompt.txt](config/system_prompt.txt),
[agent/action_definitions.json](agent/action_definitions.json) and
[agent/conversation_rules.md](agent/conversation_rules.md).

## Layout

| Folder | What |
|---|---|
| `config/` | `model_config.yaml` (model, decoding, future LoRA settings), `system_prompt.txt` |
| `knowledge/` | `attendance_rules.md` = the Activities rules from the specs. The other 3 files have no source yet |
| `api/` | The 4 endpoints: contracts, paths, response shapes. Unknown fields are marked `unconfirmed (Qnn)` |
| `agent/` | Intents with examples, action → endpoint/arguments, conversation rules |
| `training/` | `tool_call_dataset.jsonl` (chat format for mlx-lm LoRA), `intent_dataset.jsonl`, `response_examples.jsonl` |
| `evaluation/` | `test_questions.jsonl` + `expected_results.jsonl` (same ids), `baseline_report.md` |
| `app/` | llm, schema, agent, context, dates, mock_api, responder |
| `scripts/` | `chat.py`, `evaluate.py`, `validate_jsonl.py`, `build_datasets.py` |
| `tests/` | pytest, no model needed |

## Setup

Uses the existing virtualenv one level up (`../.venv`, Python 3.9). mlx, mlx-lm, transformers and PyYAML are
already there.

```bash
cd "/Users/mostafasamy/work/local ai/src"
../.venv/bin/python -m pip install -r requirements.txt
```

The base model must already be in `~/.cache/huggingface/hub/models--mlx-community--Qwen2.5-3B-Instruct-4bit/`.
`app/llm.py` sets `HF_HUB_OFFLINE=1`, so nothing is downloaded. On a new Mac, download it once with
`HF_HUB_OFFLINE=0` (about 1.6 GB).

## Run

```bash
../.venv/bin/python scripts/chat.py --debug
```

`--debug` prints the raw model text, the validated JSON and the request filters. `--fail-api` simulates a
backend error. Questions can also be piped in, one per line:

```bash
printf 'show my pending visits today\nand yesterday?\n' | ../.venv/bin/python scripts/chat.py --debug
```

## Test

```bash
../.venv/bin/python -m pytest -q
```

Tests cover schema, dates, context (follow-ups, retry), mock API and responder. They don't load the model.

## Datasets

```bash
../.venv/bin/python scripts/build_datasets.py     # regenerate (deterministic, fixed seed)
../.venv/bin/python scripts/validate_jsonl.py     # must print OK
```

- Half Arabic, half English. They include short, vague, follow-up, refusal and out-of-scope questions, plus
  "how many high priority …" (routed to the list, because the dashboard has no priority filter).
- Training and evaluation are built from **different phrase lists** (verbs, wordings, dates), and the validator
  fails if any user message from evaluation appears in training.
- Every assistant message passes `app/schema.py`. The system message in every training row is exactly
  `config/system_prompt.txt`, the same prompt used at inference time.
- Most `tool_call_dataset` rows are `[system, user, assistant]`. Follow-up rows carry one previous turn:
  `[system, user, assistant, user, assistant]`. That's the same history `app/context.py` sends at run time.

## Evaluate

```bash
../.venv/bin/python scripts/evaluate.py                         # base model -> evaluation/baseline_report.md
../.venv/bin/python scripts/evaluate.py --adapter <folder> --report evaluation/finetuned_report.md \
    --outputs evaluation/finetuned_outputs.jsonl                # after fine-tuning (later)
```

Each question gets a single shot (no retry, no context merge), so the report measures the model alone.
The metrics are valid JSON, schema-valid, action accuracy and exact argument match, split by Arabic/English
and by category.

## Fine-tuning (not done, waiting for dataset approval)

When the dataset is approved, the settings in `config/model_config.yaml → lora` are meant for `mlx_lm.lora`
with `training/tool_call_dataset.jsonl` split into `train.jsonl` / `valid.jsonl`. Nothing in this folder runs
training.

## What the model never does

It never fills employee ids, company ids, tokens or timestamps. Code fills them. `scope` → `onlyMe` +
company/employee ids happens in the backend from the session (see `api/api_contracts.yaml → scope_mapping`).
`dateRange` → `fromDateTime`/`endDateTime` happens in `app/dates.py`.
