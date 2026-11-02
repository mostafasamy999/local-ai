"""
Deterministic mapping layer: model's intermediate JSON -> the real
GetVisitAndTaskAssignedToLoggedInUser (E2) request body.

This is plain code, NOT the LLM's job. The model only ever produces
{action, arguments: {dateRange, statusId, priorityId, scope, search}, ...}
(see specs/v2/activities.md). Everything here resolves that into real
IDs and real datetimes using:
  - a lookup of allowedCompanies / allowedEmployees (passed in — this
    sample is swapped for the real list fetched from the backend)
  - the session context of the logged-in user (userId, companyId,
    subscriberId — never from the chat message)
  - the business rules documented in specs/001-activities/api-contracts.md

Usage:
    python scripts/map_to_api.py
(runs the built-in demo at the bottom; wire in real model output + real
lookup data to use for real)
"""
from __future__ import annotations
import json
import difflib
from datetime import datetime, timedelta
from dataclasses import dataclass, field


# ----------------------------------------------------------------------------
# 1. Session context — comes from the logged-in user's session, never from
#    the chat message or the model.
# --------------------------------------------------------------------------
@dataclass
class SessionContext:
    userId: int
    employeeId: int
    companyId: int           # the logged-in company (top-level "companyId" in the envelope)
    subscriberId: int
    langId: str = "en"
    is_team_user: bool = True  # False for a "solo user" (no team to see)


# ---------------------------------------------------------------------------
# 2. Employee / company lookup + fuzzy name resolution
# ---------------------------------------------------------------------------
class Directory:
    def __init__(self, allowed_companies: list[dict], allowed_employees: list[dict]):
        self.companies = allowed_companies
        self.employees = allowed_employees

    def find_employees_by_name(self, query: str, limit: int = 5, cutoff: float = 0.55):
        """Fuzzy-match a free-text name against allowedEmployees.
        Returns a list of {employeeId, employeeName, companyId} matches,
        best first. Caller decides what to do with 0 / 1 / many matches —
        this function never guesses, it just reports."""
        if not query:
            return []
        names = [e["employeeName"].strip() for e in self.employees]
        query_norm = query.strip().lower()

        scored = []
        for emp, name in zip(self.employees, names):
            name_norm = name.lower()
            if query_norm == name_norm:
                score = 1.0
            elif query_norm in name_norm.split():
                score = 0.9  # exact first/last-name token match (e.g. "Ahmed" in "Ahmed Anwar")
            else:
                score = difflib.SequenceMatcher(None, query_norm, name_norm).ratio()
            if score >= cutoff:
                scored.append((score, emp))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [emp for _, emp in scored[:limit]]

    def all_allowed_company_ids(self):
        return [c["companyId"] for c in self.companies]


# ----------------------------------------------------------------------------
# 3. dateRange -> fromDateTime / endDateTime
#    Rule (api-contracts.md §4): yyyy-MM-ddTHH:mm:ss, open end = null.
#    Default (nothing specified) = today-6 00:00 -> today 23:59.
#    Week runs Saturday -> Friday (user-scenarios-rules.md).
# ---------------------------------------------------------------------------
def _day_start(d):
    return d.strftime("%Y-%m-%dT00:00:00")


def _day_end(d):
    return d.strftime("%Y-%m-%dT23:59:59")


def _week_start(d):
    # Saturday = start of week. Python weekday(): Mon=0..Sun=6, Sat=5.
    offset = (d.weekday() - 5) % 7
    return d - timedelta(days=offset)


def resolve_date_range(dateRange, fromDate, toDate, today=None):
    today = today or datetime.now()

    if fromDate or toDate:
        # explicit dates win over any dateRange keyword
        start = f"{fromDate}T00:00:00" if fromDate else None
        end = f"{toDate}T23:59:59" if toDate else None
        return start, end

    if dateRange is None:
        dateRange = "last_7_days"

    if dateRange == "today":
        return _day_start(today), _day_end(today)
    if dateRange == "yesterday":
        y = today - timedelta(days=1)
        return _day_start(y), _day_end(y)
    if dateRange == "last_7_days":
        start = today - timedelta(days=6)
        return _day_start(start), _day_end(today)
    if dateRange == "this_week":
        start = _week_start(today)
        end = start + timedelta(days=6)
        return _day_start(start), _day_end(end)
    if dateRange == "last_week":
        this_start = _week_start(today)
        start = this_start - timedelta(days=7)
        end = this_start - timedelta(days=1)
        return _day_start(start), _day_end(end)
    if dateRange == "this_month":
        start = today.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        end = next_month - timedelta(days=1)
        return _day_start(start), _day_end(end)
    if dateRange == "current":
        return _day_start(today), None  # open-ended going forward
    if dateRange == "previous":
        y = today - timedelta(days=1)
        return None, _day_start(y)  # open start, before yesterday 00:00

    # unknown keyword: fall back to the documented default rather than guess
    start = today - timedelta(days=6)
    return _day_start(start), _day_end(today)


# ---------------------------------------------------------------------------
# 4. scope -> onlyMe + companyId[] / employeeId[]
#    Rule (api-contracts.md §4, Q16 flagged as unconfirmed in the real
#    code — we match the CURRENT app behavior, not the "intuitive" one):
#      all          -> onlyMe: true   (yes, really — matches current code)
#      private      -> onlyMe: true
#      my_team      -> onlyMe: false
#      my_activities-> onlyMe: false
#    IDs (api-contracts.md §4):
#      my_activities / private -> the user's own company + self
#      all / my_team           -> named employee/company if the user
#                                  mentioned one, else every allowed one
# ---------------------------------------------------------------------------
class ClarificationNeeded(Exception):
    def __init__(self, question):
        self.question = question


def resolve_scope(scope, search_text, session: SessionContext, directory: Directory):
    scope = scope or "all"

    # Rule 1 (onlyMe): {all, private} -> true · {my_team, my_activities} -> false.
    # Yes, "all" maps to true — that's the documented current-code behavior,
    # not a typo. It's flagged as questionable in the original spec (Q16),
    # but we match the real app rather than the "intuitive" reading.
    only_me = scope in ("all", "private")

    # Rule 2 (company/employee IDs): a DIFFERENT grouping than rule 1.
    # {my_activities, private} -> the user's own company + self.
    if scope in ("my_activities", "private"):
        return only_me, [session.companyId], [session.employeeId]

    # {all, my_team} -> named employee/company if mentioned, else every allowed one.
    if search_text:
        matches = directory.find_employees_by_name(search_text)
        if len(matches) == 0:
            raise ClarificationNeeded(
                f"I couldn't find anyone named \"{search_text}\" in your directory — "
                "could you check the spelling or give a last name?"
            )
        if len(matches) > 1:
            names = ", ".join(m["employeeName"].strip() for m in matches[:5])
            raise ClarificationNeeded(
                f"There's more than one match for \"{search_text}\": {names}. Which one did you mean?"
            )
        emp = matches[0]
        return only_me, [emp["companyId"]], [emp["employeeId"]]

    # nothing named -> every allowed company/employee (send empty lists,
    # per api-contracts.md "Any/no filter" rule for E2)
    return only_me, [], []


# --------------------------------------------------------------------------
# 5. Full request builder for E2 (GetVisitAndTaskAssignedToLoggedInUser)
# ---------------------------------------------------------------------------
def build_e2_request(model_output: dict, session: SessionContext, directory: Directory,
                      direction="desc", skip=0, pageSize=10):
    if model_output.get("refused") or model_output.get("needs_clarification"):
        # nothing to map — the chat layer should have already surfaced
        # the refusal_reason / clarification_question to the user
        return None

    action = model_output["action"]
    args = model_output["arguments"] or {}

    if action not in ("get_visits", "get_tasks"):
        raise ValueError(f"{action} doesn't map to E2 — see note below for get_main_activities/get_dashboard")

    typeId = 2 if action == "get_visits" else 1

    fromDateTime, endDateTime = resolve_date_range(
        args.get("dateRange"), args.get("fromDate"), args.get("toDate")
    )

    only_me, companyIds, employeeIds = resolve_scope(
        args.get("scope"), args.get("search"), session, directory
    )

    priorityId = args.get("priorityId")
    categoryId = args.get("categoryId")  # get_tasks never has this; get_visits may

    return {
        "userId": session.userId,
        "subscriberId": session.subscriberId,
        "companyId": session.companyId,
        "langId": session.langId,
        "deviceTypeCode": 0,
        "deviceToken": "string",
        "deviceSerial": "SAMSUNGNOTE",
        "appVersion": "string",
        "oSVersion": "string",
        "data": {
            "typeId": typeId,
            "statusId": args.get("statusId"),
            "currentOrOld": None,
            "fromDateTime": fromDateTime,
            "endDateTime": endDateTime,
            "categoryId": [categoryId] if categoryId else [],
            "masterId": 0,
            "userId": 0,
            "employeeId": employeeIds,
            "companyId": companyIds,
            "priorityId": [priorityId] if priorityId else [],
            "onlyMe": only_me,
            "executionTypeId": None,
            "searchValue": None,  # free-text search the user typed (not an employee name) would go here — see note
            "direction": direction,
            "skip": skip,
            "pageSize": pageSize,
        },
    }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # --- sample lookup data (swap for the real lists fetched from the app) ---
    directory = Directory(
        allowed_companies=[
            {"companyId": 1, "parentId": 0, "companyName": "الشركة الرئيسية"},
            {"companyId": 3, "parentId": 1, "companyName": "شركه اى ليد"},
            {"companyId": 6, "parentId": 1, "companyName": "حلول جالاأسي الذكية"},
        ],
        allowed_employees=[
            {"companyId": 3, "employeeId": 12, "employeeName": "Ahmed Anwar "},
            {"companyId": 6, "employeeId": 316, "employeeName": "Yousef Galaxy "},
            {"companyId": 6, "employeeId": 160, "employeeName": "kiro eissa "},
            {"companyId": 6, "employeeId": 331, "employeeName": "Ahmed Adel Shawky"},
            {"companyId": 6, "employeeId": 333, "employeeName": "Ahmed Sayed Saleh"},
        ],
    )

    # --- session context (would come from the logged-in user's token) ---
    session = SessionContext(userId=52, employeeId=600, companyId=10, subscriberId=1)

    # --- example model outputs (what the fine-tuned model actually returns) ---
    examples = [
        {"action": "get_visits", "arguments": {"dateRange": "yesterday", "statusId": 1, "priorityId": None, "categoryId": None, "scope": "all", "search": None}, "needs_clarification": False, "refused": False},
        {"action": "get_tasks", "arguments": {"dateRange": "this_week", "statusId": 4, "priorityId": None, "scope": "my_activities", "search": None}, "needs_clarification": False, "refused": False},
        {"action": "get_visits", "arguments": {"dateRange": "last_week", "statusId": None, "priorityId": None, "categoryId": None, "scope": "all", "search": "Ahmed"}, "needs_clarification": False, "refused": False},
    ]

    for i, model_output in enumerate(examples, 1):
        print("=" * 80)
        print(f"Model output #{i}:", json.dumps(model_output, ensure_ascii=False))
        try:
            request_body = build_e2_request(model_output, session, directory)
            print("Mapped API request:")
            print(json.dumps(request_body, ensure_ascii=False, indent=2))
        except ClarificationNeeded as e:
            print("Needs clarification before calling the API:", e.question)
