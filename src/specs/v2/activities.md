# HR Assistant — Activities domain (v2)

Supersedes v1. Same domain and IDs; this version fixes the output
contract after evaluating v1 (see changelog below).

## What changed from v1

1. **One JSON schema, always** — no more switching between plain-text
   questions and JSON objects. v1's 3B model couldn't reliably hold two
   output modes with only 47 examples; collapsing to one schema removes
   that failure mode and is also easier for a backend to parse.
2. **Every training example now includes the same system message**
   the app will send at inference time. v1 trained with none and was
   evaluated with one — that mismatch explains most of v1's regressions.
3. **Far more refusal examples**, covering different destructive verbs
   (cancel, delete, approve, reschedule, reassign, mark complete, edit,
   change priority) so the model learns the *principle* ("I only read
   data"), not specific sentences.
4. **Systematic null-filling.** Every example only fills the fields the
   user actually mentioned and leaves the rest `null` — generated across
   many combinations so "never invent a value" is reinforced structurally,
   not by a handful of hand-picked examples.

## Output schema (always this shape, never prose)

```json
{
  "action": "get_visits | get_tasks | get_main_activities | get_dashboard | null",
  "arguments": { "...": "null for any field not mentioned by the user" },
  "needs_clarification": false,
  "clarification_question": null,
  "refused": false,
  "refusal_reason": null
}
```

- `needs_clarification: true` → `action`/`arguments` are `null`, and
  `clarification_question` holds a short question in the user's language.
- `refused: true` → `action`/`arguments` are `null`, and `refusal_reason`
  holds a short explanation in the user's language.
- Otherwise → `action`/`arguments` are filled, the other three stay at
  their default (`false`/`null`).

## Field values (unchanged from v1 — never invent others)

| Field | Values |
|---|---|
| `typeId` | 1 = Task, 2 = Visit |
| `statusId` | 1 Pending, 2 In progress, 3 Cancelled, 4 Completed, 5 Rejected, 7 Partially completed |
| `priorityId` | 1 low, 2 medium, 3 high |
| `scope` | all (default), my_team, my_activities, private |
| `dateRange` | today, yesterday, last_7_days, this_week, last_week, this_month, current, previous — or explicit `fromDate`/`toDate` |

`get_visits` arguments: `dateRange`/`fromDate`/`toDate`, `statusId`, `priorityId`, `categoryId`, `scope`, `search`.
`get_tasks` arguments: same minus `categoryId` (tasks have no category).
`get_main_activities` arguments: `typeId`, `statusId`, `categoryId`, `priorityId`.
`get_dashboard` arguments: `dateRange`, `statusId`, `categoryId`, `scope`.

## Rules (unchanged principles from v1)

1. Never invent a value for a field the user didn't mention — leave it `null`.
2. There's no category-name lookup available to the assistant — if the user
   names a category, don't guess an ID; just don't filter by it.
3. "Main" list is for editing/masters — only use it when the user explicitly
   asks for "the main list", "the masters", or to manage/edit activities.
4. Scope defaults to "all" unless the user says "my", "private", "my team's".
5. Carry context across turns — combine a clarification answer with the
   original request.
6. Refuse any create/edit/delete/status-change/approval request — v2 is
   still read-only. State that plainly via `refused`/`refusal_reason`.
7. Respond in the user's language (Arabic or English) inside
   `clarification_question`/`refusal_reason`; field names and values in
   `arguments` stay in English regardless of the conversation language.
