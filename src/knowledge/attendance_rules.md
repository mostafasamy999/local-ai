# Activities rules (from the specs)

> The file name is fixed by the project layout. Its content is about the **Activities** module only,
> taken from `specs-talentlink/specs/001-activities` (Doc v2.0, 2026-10-27, synced to changelog CL-10).
> Nothing here is about attendance (check-in to work). Rules marked ⚠ are not confirmed by the backend.

## Words

- **Activity**: a Visit or a Task. A **Visit** happens at a place and has a category, an execution type
  (repeat pattern), a location, and optionally a contact and check-in/out. A **Task** has none of these.
- **Occurrence**: one scheduled instance of an activity assigned to one person. The normal list shows occurrences.
- **Main (master) activity**: the activity itself, which may have many occurrences. The **Main** list shows these.
- **Open status**: Pending or In progress. **Closed status**: Cancelled, Completed or Rejected.
  Partially completed is neither open nor closed.

## Type

| typeId | Type |
|---|---|
| 1 | Task |
| 2 | Visit |

A local constant, not a lookup. An unknown `typeId` from the backend is shown as a Task.

## Statuses

| statusId | Status |
|---|---|
| 1 | Pending |
| 2 | In progress |
| 3 | Cancelled |
| 4 | Completed |
| 5 | Rejected |
| 7 | Partially completed |

Names and colors come from `GetTaskStatusList`; these IDs are hardcoded for logic. There is no status 6 in the specs.

## Priorities

| priorityId | Priority |
|---|---|
| 1 | Low |
| 2 | Medium |
| 3 | High |

An unknown priority from the backend is shown as Low.

## Scopes

| Scope | Who can pick it | Whose activities |
|---|---|---|
| all (default) | everyone | everyone the user can see, plus the user's own, including private ones |
| my_team | team users only | the picked departments/employees, or all of them if none are picked |
| my_activities | everyone | only the user's own |
| private | everyone | only the user's private activities |

Scope is turned into `onlyMe` + company/employee ID lists by code, never by the model:
All → `onlyMe true`, Private → `onlyMe true`, My team → `false`, My activities → `false`.
⚠ Whether All should send `onlyMe true` is unconfirmed (Q16). Whether the list returns team members'
activities when sent team IDs is unconfirmed (Q28). Departments travel as `companyId[]` (Q15).

## Date ranges

- Wire format: `fromDateTime` / `endDateTime` as `yyyy-MM-ddTHH:mm:ss`, English digits. Either end can be null (open).
  ⚠ The format (date only vs date and time) is unconfirmed (Q23).
- **Default** (no date given): 6 days ago 00:00 → today 23:59.
- **Current**: today 00:00 → open.
- **Previous**: open → before today 00:00 (the agreed rule). ⚠ The app today ends it at yesterday 00:00 (gap DEF-06).
  Until Q14 (inclusive or exclusive end) is answered, the fallback is "end inclusive, today 00:00 minus 1 s".
- Week days in the app run Saturday → Friday (1 = Saturday … 7 = Friday). This project uses Saturday as the
  first day of a week for `this_week` / `last_week` (an assumption based on that ordering).
- `today`, `yesterday`, `last_7_days`, `this_week`, `last_week`, `this_month` are presets of this assistant,
  resolved by `app/dates.py`. Only Default, Current and Previous are presets in the app itself.

## Which list or count

| Need | Endpoint | Notes |
|---|---|---|
| Assigned visits / tasks (occurrences) | `GetVisitAndTaskAssignedToLoggedInUser` (E2) | paged, 10 per page, `totalCount` returned |
| Main list (masters) | `GetVisitAndTaskList` (E3) | response shape unconfirmed (Q18) |
| Counts | `GetTaskAndVisitDashboard` (E1) | always counts both types |

- The dashboard follows status, category, execution type, dates and scope.
  ⚠ It ignores priority, search and the Main chip (Q25, Q26), so its numbers can differ from the list.
- Search applies to the lists only. ⚠ Which fields search matches is unconfirmed (Q19).
- Sort is by scheduled start, newest first by default.

## What the assistant may not do

The module also lets users create, edit, reschedule, change status, add notes, update progress,
check in/out, start, complete and enable/disable activities. This assistant is **read-only** and refuses all of these.
