# Baseline evaluation report

- Date: 2026-11-12 08:48
- Model: mlx-community/Qwen2.5-3B-Instruct-4bit (base, no fine-tuning)
- Decoding: temperature 0.0, max_tokens 256, system prompt = config/system_prompt.txt
- Questions: 74 (evaluation/test_questions.jsonl). Single shot, no retry, no context merging.
- Load time 2.5 s, generation 159.3 s total (2.15 s per question).

## Metrics

- **Valid JSON**: the reply contains a parseable JSON object.
- **Schema valid**: it also passes `app/schema.py` (known action, allowed values, consistent flags).
- **Action accuracy**: the right outcome: same action, or refused / clarification when expected.
- **Argument accuracy**: for questions whose expected answer has an action, all arguments match exactly (every key, nulls included).

| Group | N | Valid JSON | Schema valid | Action accuracy | Argument accuracy |
|---|---|---|---|---|---|
| All | 74 | 100.0% (74/74) | 74.3% (55/74) | 54.1% (40/74) | 16.0% (8/50) |
| Arabic | 37 | 100.0% (37/37) | 67.6% (25/37) | 54.1% (20/37) | 16.0% (4/25) |
| English | 37 | 100.0% (37/37) | 81.1% (30/37) | 54.1% (20/37) | 16.0% (4/25) |

## By category

| Category | N | Valid JSON | Schema valid | Action accuracy | Argument accuracy |
|---|---|---|---|---|---|
| clarify_follow_up | 4 | 100.0% (4/4) | 100.0% (4/4) | 25.0% (1/4) | 0.0% (0/4) |
| count_priority | 4 | 100.0% (4/4) | 75.0% (3/4) | 75.0% (3/4) | 0.0% (0/4) |
| dashboard | 6 | 100.0% (6/6) | 66.7% (4/6) | 66.7% (4/6) | 0.0% (0/6) |
| follow_up | 8 | 100.0% (8/8) | 100.0% (8/8) | 100.0% (8/8) | 75.0% (6/8) |
| list | 16 | 100.0% (16/16) | 81.2% (13/16) | 81.2% (13/16) | 6.2% (1/16) |
| main | 6 | 100.0% (6/6) | 66.7% (4/6) | 66.7% (4/6) | 0.0% (0/6) |
| out_of_scope | 8 | 100.0% (8/8) | 75.0% (6/8) | 0.0% (0/8) | n/a (0/0) |
| question | 6 | 100.0% (6/6) | 100.0% (6/6) | 100.0% (6/6) | 16.7% (1/6) |
| refusal | 8 | 100.0% (8/8) | 25.0% (2/8) | 0.0% (0/8) | n/a (0/0) |
| vague | 8 | 100.0% (8/8) | 62.5% (5/8) | 12.5% (1/8) | n/a (0/0) |

## Failures (first 25)

- **T001** (ar, clarify_follow_up) `الملغاة → المهام طبعاً`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 3, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": null, "arguments": null, "needs_clarification": true, "clarification_question": "هل ترغب في استعراض المهام التي هي في حالة ما أو المهام التي هي في حالة توقف أو المهام التي هي في حالة إكمال جزئي؟", "refusal_reason": null, "refused": false}`
- **T002** (ar, clarify_follow_up) `الملغاة → أقصد الزيارات`
  - expected: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 3, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T003** (en, clarify_follow_up) `The cancelled ones → I meant visits`
  - expected: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 3, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": null, "arguments": null, "needs_clarification": true, "clarification_question": "What specific details do you want to see for the cancelled visits?", "refused": false, "refusal_reason": null}`
- **T004** (en, clarify_follow_up) `The cancelled ones → The tasks one`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 3, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": null, "arguments": null, "needs_clarification": true, "clarification_question": "Do you want cancelled visits, cancelled tasks, the main list or the dashboard?", "refused": false, "refusal_reason": null}`
- **T005** (ar, count_priority) `ما عدد المهام ذات الأولوية العالية؟`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": 3, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_dashboard", "arguments": {"dateRange": "current", "fromDate": null, "toDate": null, "statusId": null, "scope": null, "search": "priorityId:3"} , "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`  (error: unknown argument(s) for get_dashboard: search)
- **T006** (ar, count_priority) `ما عدد المهام ذات الأولوية المتوسطة؟`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": 2, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"priorityId": 2, "dateRange": "current"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T007** (en, count_priority) `What's the number of medium priority tasks?`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": 2, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"priorityId": "2", "scope": "all"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T008** (en, count_priority) `What's the number of medium-priority tasks?`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": 2, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"priorityId": "2", "scope": "all"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T009** (ar, dashboard) `إجمالي الزيارات والمهام للأنشطة المرفوضة؟`
  - expected: `{"action": "get_dashboard", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 5, "scope": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_dashboard", "arguments": {"dateRange": "current", "fromDate": null, "toDate": null, "statusId": 5, "scope": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T010** (ar, dashboard) `أرقام لوحة المتابعة هذا الأسبوع؟`
  - expected: `{"action": "get_dashboard", "arguments": {"dateRange": "this_week", "fromDate": null, "toDate": null, "statusId": null, "scope": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_dashboard", "arguments": {"dateRange": "this_week", "scope": "all"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T011** (ar, dashboard) `أرقام لوحة المتابعة للأنشطة المرفوضة الخاصة بفريقي؟`
  - expected: `{"action": "get_dashboard", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 5, "scope": "my_team"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"scope": "my_team", "statusId": 5, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}}`  (error: unknown argument(s) for get_tasks: clarification_question, needs_clarification, refusal_reason, refused)
- **T012** (en, dashboard) `Dashboard numbers assigned only to me?`
  - expected: `{"action": "get_dashboard", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "scope": "my_activities"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_dashboard", "arguments": {"scope": "my_activities", "dateRange": "current"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T013** (en, dashboard) `Totals for my visits and tasks for the waiting ones?`
  - expected: `{"action": "get_dashboard", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 1, "scope": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_dashboard", "arguments": {"dateRange": "current", "scope": "my_activities", "statusId": 1}, "needs_clasification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`  (error: Extra inputs are not permitted)
- **T014** (en, dashboard) `Dashboard numbers of my team?`
  - expected: `{"action": "get_dashboard", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "scope": "my_team"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_dashboard", "arguments": {"dateRange": "current", "scope": "my_team"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T016** (ar, follow_up) `أريد رؤية الزيارات ذات الأولوية المنخفضة → بس اللي قيد التنفيذ`
  - expected: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 2, "priorityId": 1, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 2, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T019** (en, follow_up) `I need my visits this week → Just the in progress ones`
  - expected: `{"action": "get_visits", "arguments": {"dateRange": "this_week", "fromDate": null, "toDate": null, "statusId": 2, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 2, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T023** (ar, list) `ممكن تعرض زياراتي؟`
  - expected: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_visits", "arguments": {"scope": "my_activities", "dateRange": "current"}, "needs_clasification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`  (error: Extra inputs are not permitted)
- **T024** (ar, list) `أريد رؤية الزيارات`
  - expected: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_visits", "arguments": {"dateRange": "current", "fromDate": null, "toDate": null, "statusId": null, "priorityId": null, "scope": "my_activities", "search": null}, "needs_clasification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`  (error: Extra inputs are not permitted)
- **T025** (ar, list) `أريد رؤية المهام عن الجرد لي أنا فقط؟`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": null, "scope": "my_activities", "search": "الجرد"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"scope": "my_activities", "dateRange": "today"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T026** (ar, list) `افتح لي مهامي عن العقود الخاصة بفريقي؟`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": null, "scope": "my_team", "search": "العقود"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"scope": "my_team", "dateRange": "this_month", "fromDate": null, "toDate": null, "statusId": null, "priorityId": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T027** (ar, list) `افتح لي المهام الجارية لهذا الشهر`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": "this_month", "fromDate": null, "toDate": null, "statusId": 2, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"dateRange": "this_month", "scope": "all"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T028** (ar, list) `أريد رؤية مهامي المعلقة لفريقي؟`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 1, "priorityId": null, "scope": "my_team", "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"dateRange": "current", "statusId": 5, "scope": "my_team"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T029** (ar, list) `طلّع لي المهام المنتهية`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 4, "priorityId": null, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"dateRange": "current", "statusId": 4, "scope": "my_activities"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T030** (ar, list) `أريد رؤية المهام المنتهية بأولوية منخفضة؟`
  - expected: `{"action": "get_tasks", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": 4, "priorityId": 1, "scope": null, "search": null}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_tasks", "arguments": {"dateRange": "current", "priorityId": "1", "scope": "all", "search": "completed tasks low priority"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
- **T031** (en, list) `Let me see high priority visits with training for my team`
  - expected: `{"action": "get_visits", "arguments": {"dateRange": null, "fromDate": null, "toDate": null, "statusId": null, "priorityId": 3, "scope": "my_team", "search": "training"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`
  - got: `{"action": "get_visits", "arguments": {"dateRange": "this_month", "priorityId": "3", "scope": "my_team", "search": "training"}, "needs_clarification": false, "clarification_question": null, "refused": false, "refusal_reason": null}`

Raw outputs: `evaluation/baseline_outputs.jsonl`.
