# Conversation rules

How the assistant handles more than one message. The model does the language part; `app/context.py`
and `app/agent.py` enforce the rules in code so a mistake by the model can't break them.

## 1. Every reply is one JSON object

The model never writes prose. The sentence the user sees is built by `app/responder.py` from templates,
after the (mock) API call. Refusals and clarification questions are the only text the model writes,
and they go in `refusal_reason` / `clarification_question`.

## 2. Follow-ups reuse the last request

A **follow-up** is a short message that only changes a filter of the previous request:

| User | Assistant does |
|---|---|
| "Show my pending visits today" | `get_visits`, statusId 1, dateRange today |
| "and yesterday?" | `get_visits`, statusId 1, dateRange **yesterday** |
| "only the high ones" | `get_visits`, statusId 1, dateRange yesterday, priorityId **3** |
| "و المكتملة؟" | same action, statusId **4**, everything else kept |

Rules:
- The action stays the same, unless the user names another one ("and my tasks?" switches to `get_tasks` and keeps the filters).
- Only the fields the user just mentioned change. All other arguments are copied from the previous request.
- A new date replaces the old date: a `dateRange` clears `fromDate`/`toDate`, and explicit dates clear `dateRange`.
- The model sees the previous user message and its JSON (one turn of history). `app/context.py` then merges:
  when the message looks like a follow-up and the model kept the same action, every argument the model left
  `null` is taken from the previous request.

Follow-up markers: English "and …", "what about …", "how about …", "only …", "also …", "same …", "now …";
Arabic "و…", "وماذا عن …", "طيب …", "طب …", "بس …", "فقط …", "نفس …", "والـ…".

## 3. A new topic clears the context

- A message that names its own action and does not start like a follow-up is a new request. Context is replaced.
- A refusal (write action or out of scope) clears the context.
- "start over", "new question", "ابدأ من جديد" clears the context (handled in code, no model call).

## 4. Clarification

- Ask only when no action can be chosen ("show me", "what do I have?"). Don't ask about optional filters:
  a missing date or status is fine, code uses the defaults (last 7 days, scope all).
- One short question, in the user's language. Offer the choices: visits, tasks, the main list or the dashboard.
- While a question is open, the vague message and the question stay in the history. The user's answer ("visits") is read together with
  the original message, so "the pending ones" + "visits" → `get_visits`, statusId 1.

## 5. Refusals

- Write actions (create, edit, delete, cancel, reschedule, change status, mark done, approve, reject, assign,
  add a note, update progress, check in/out, start, complete, enable/disable) → `refused: true`.
  The reason says the assistant can only read activities and the user can do it from the Activities screen.
- Outside Activities (leave, payroll, attendance, weather, chit-chat) → `refused: true`.
  The reason says the assistant only answers about visits and tasks.
- A refusal is in the user's language.

## 6. Language

- Arabic message → Arabic `clarification_question` / `refusal_reason` and an Arabic answer from the responder.
- English message → English.
- Mixed → the language with more letters in the message.
- `arguments` keys and values are always English. Dates use English digits (Arabic digits are converted).

## 7. Defaults (applied by code, not the model)

| Missing | Code uses |
|---|---|
| dateRange and fromDate/toDate | last 7 days (6 days ago 00:00 → today 23:59:59) |
| scope | all |
| statusId, priorityId, search, typeId | no filter |
