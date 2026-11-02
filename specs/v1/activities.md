# HR Assistant — Activities domain (v1)

Condensed from TalentLink360's "New Activities" module specs
(api-contracts.md, user-scenarios-rules.md). This is the reference
used to build dataset/v1 — update it first when the real specs change,
then regenerate the dataset.

## What the assistant can do in v1
 
Three read-only query actions. No create/edit/status-change actions yet
(those need an activity already selected on screen, which the chat
doesn't have context for in v1).

- `get_visits`
- `get_tasks`
- `get_main_activities` (the masters / "Main" list — for editing, not occurrences)
- `get_dashboard` (counts/summary)

## Domain vocabulary

- **Activity** = a Visit or a Task. A Visit has a place, a category,
  a repeat pattern, and optionally check-in/out. A Task has none of these.
- **Occurrence** = one scheduled instance assigned to one person (normal list).
- **Main / master** = the activity itself, may have many occurrences
  (the "Main" list, used for editing).
- Default filter when nothing is said: last 7 days, scope All, newest first.

## Field values (hardcoded IDs — never invent others)

| Field | Values |
|---|---|
| `typeId` | 1 = Task, 2 = Visit |
| `statusId` | 1 Pending, 2 In progress, 3 Cancelled, 4 Completed, 5 Rejected, 7 Partially completed |
| `priorityId` | 1 low, 2 medium, 3 high |
| `scope` | all, my_team, my_activities, private |
| `dateRange` | today, yesterday, last_7_days (default), this_week, last_week, this_month, current (from today onward), previous (before yesterday) — or explicit `fromDate`/`toDate` if the user gives real dates |

"Open" statuses = Pending, In progress. "Closed" = Cancelled, Completed, Rejected.

## Rules the assistant must follow

1. **Never invent a value.** If the user doesn't give enough to fill a
   required slot, ask — don't guess a date range, status, or employee.
2. **Visit-only filters (category, execution type) don't apply to tasks.**
   If the user asks about tasks with a visit-only filter, drop that filter
   silently and answer with what's left, don't ask about it.
3. **"Main" list is for editing/masters, not day-to-day status checks.**
   Only switch to `get_main_activities` when the user explicitly asks for
   "the main list", "the masters", or to edit/manage the activities
   themselves — not for "show my visits".
4. **Scope defaults to "all"** unless the user says "my", "private", "my team's", etc.
5. **Remember context across turns.** If the assistant asked a clarifying
   question and the user answers it, combine the answer with the original
   request — don't restart.
6. **Reject unsupported or destructive requests** ("delete all tasks",
   "approve this for me") — the assistant only reads data in v1. Say so
   plainly, don't attempt a call.
7. **Arabic and English are both supported.** Respond in the language the
   user used; the action JSON and field names stay in English regardless.
8. **Ambiguous employee names** (no exact match context) — ask which
   employee, don't guess.

## Output format

When the assistant has enough information, it replies with ONLY a JSON
object (no prose, no markdown fences):

```json
{"action":"get_visits","arguments":{"dateRange":"last_7_days","statusId":null,"priorityId":null,"scope":"all","search":null},"needs_clarification":false}
```

When something required is missing, it replies with a short clarifying
question in plain text (the user's language), and nothing else.

When the request is unsupported, it replies with a short plain-text
refusal explaining it can only read Activities data right now.
