"""Fake responses for the 4 read-only endpoints, shaped like api/response_schemas.json.

The data is made up (generic titles, "Employee 1"), placed around `today` so date filters
return something. It applies the same filters as the real endpoints are described to apply.
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.agent import ActionRequest

FMT = "%Y-%m-%dT%H:%M:%S"
STATUS = {1: ("Pending", "#F5A623"), 2: ("In progress", "#4A90E2"), 3: ("Cancelled", "#9B9B9B"),
          4: ("Completed", "#7ED321"), 5: ("Rejected", "#D0021B"), 7: ("Partially completed", "#BD10E0")}
PRIORITY = {1: "Low", 2: "Medium", 3: "High"}
SELF_ID = 1

# (masterId, typeId, title, day offset from today, start hour, hours, statusId, priorityId, private, userId)
_ROWS = [
    (101, 2, "Site inspection", 0, 9, 2, 1, 3, False, 1),
    (102, 2, "Client meeting", 0, 13, 1, 2, 2, False, 1),
    (103, 1, "Monthly report", 0, 10, 3, 2, 3, False, 1),
    (104, 1, "Update price list", -1, 11, 2, 4, 1, False, 1),
    (105, 2, "Maintenance check", -1, 8, 3, 4, 2, False, 2),
    (106, 1, "Prepare training slides", -2, 14, 2, 1, 2, True, 1),
    (107, 2, "Warehouse audit", -3, 9, 4, 7, 3, False, 2),
    (108, 1, "Review contracts", -4, 10, 2, 3, 1, False, 1),
    (109, 2, "Branch visit", -5, 12, 2, 5, 2, False, 3),
    (110, 1, "Inventory count", -9, 9, 5, 4, 2, False, 1),
    (111, 2, "Supplier visit", 2, 10, 2, 1, 1, False, 1),
    (112, 1, "Quarterly plan", 3, 9, 4, 1, 3, True, 1),
    (113, 2, "Maintenance follow-up", 1, 15, 1, 1, 2, False, 2),
    (114, 1, "Team meeting notes", -1, 16, 1, 2, 1, False, 3),
]


def _items(today: date) -> List[Dict[str, Any]]:
    out = []
    for i, (mid, type_id, title, off, hour, hours, sid, pid, private, uid) in enumerate(_ROWS):
        start = datetime(today.year, today.month, today.day, hour) + timedelta(days=off)
        end = start + timedelta(hours=hours)
        out.append({
            "detailsId": 5000 + i,
            "masterId": mid,
            "typeId": type_id,
            "masterName": title,
            "status": {"id": sid, "name": STATUS[sid][0], "color": STATUS[sid][1]},
            "priorityId": pid,
            "priorityName": PRIORITY[pid],
            "onlyMe": private,
            "userId": uid,
            "userName": "Employee %d" % uid,
            "assignByName": "Manager 1",
            "createdAt": (start - timedelta(days=3)).strftime(FMT),
            "taskExecutionId": 1 if type_id == 2 else None,
            "taskExecutionName": "One time" if type_id == 2 else None,
            "addressText": "Branch %d" % (mid % 3 + 1) if type_id == 2 else "",
            "masterData": {
                "description": "",
                "visitCategoryId": 1 if type_id == 2 else 0,
                "fromDateTime": start.strftime(FMT),
                "endDateTime": end.strftime(FMT),
                "onlyMe": private,
                "companyId": 1,
            },
        })
    return out


def _in_range(item: Dict[str, Any], start: Optional[str], end: Optional[str]) -> bool:
    s = item["masterData"]["fromDateTime"]
    return (start is None or s >= start) and (end is None or s <= end)


def _scope_ok(item: Dict[str, Any], scope: str) -> bool:
    if scope == "private":
        return item["onlyMe"] and item["userId"] == SELF_ID
    if scope == "my_activities":
        return item["userId"] == SELF_ID
    return True   # all / my_team: the mock user sees everyone in the fake data


def _filter(items, f: Dict[str, Any], use_type=True, use_priority=True, use_search=True):
    out = []
    for it in items:
        if use_type and f.get("typeId") and it["typeId"] != f["typeId"]:
            continue
        if f.get("statusId") and it["status"]["id"] != f["statusId"]:
            continue
        if use_priority and f.get("priorityId") and it["priorityId"] != f["priorityId"]:
            continue
        if use_search and f.get("searchValue"):
            q = f["searchValue"].lower()
            if q not in it["masterName"].lower() and q not in it["addressText"].lower():
                continue
        if not _in_range(it, f.get("fromDateTime"), f.get("endDateTime")):
            continue
        if not _scope_ok(it, f.get("scope") or "all"):
            continue
        out.append(it)
    out.sort(key=lambda it: it["masterData"]["fromDateTime"], reverse=True)   # newest first
    return out


def _ok(data: Any) -> Dict[str, Any]:
    return {"success": True, "statusCode": 200, "responseMessage": "", "data": data}


def _dashboard(items, now: datetime) -> Dict[str, Any]:
    today_start = datetime(now.year, now.month, now.day).strftime(FMT)
    today_end = datetime(now.year, now.month, now.day, 23, 59, 59).strftime(FMT)
    now_s = now.strftime(FMT)

    def counts(type_id):
        rows = [i for i in items if i["typeId"] == type_id]
        status_list = [{"statusId": sid, "count": sum(1 for i in rows if i["status"]["id"] == sid)}
                       for sid in STATUS]
        late = sum(1 for i in rows if i["status"]["id"] in (1, 2) and i["masterData"]["endDateTime"] < now_s)
        return rows, status_list, late

    tasks, task_status, tasks_late = counts(1)
    visits, visit_status, visits_late = counts(2)
    return {
        "taskCount": len(tasks),
        "visitCount": len(visits),
        "taskStatusList": task_status,
        "visitStatusList": visit_status,
        "tasksLate": tasks_late,
        "visitsLate": visits_late,
        "taskSummary": {
            "totalTasksToday": sum(1 for t in tasks if today_start <= t["masterData"]["fromDateTime"] <= today_end),
            "totalTasksCurrent": sum(1 for t in tasks if t["masterData"]["fromDateTime"] >= today_start),
            "totalTasksPrevious": sum(1 for t in tasks if t["masterData"]["fromDateTime"] < today_start),
        },
    }


def call(request: ActionRequest, today: Optional[date] = None, now: Optional[datetime] = None,
         fail: bool = False, page: int = 1) -> Dict[str, Any]:
    """Return the envelope the real endpoint would return. fail=True simulates a backend error."""
    if fail:
        return {"success": False, "statusCode": 500, "responseMessage": "Internal server error", "data": None}
    today = today or date.today()
    now = now or datetime(today.year, today.month, today.day, 12, 0, 0)
    items = _items(today)
    f = request.filters
    skip, size = (page - 1) * 10, 10

    if request.action in ("get_visits", "get_tasks"):
        rows = _filter(items, f)
        return _ok({"totalCount": len(rows), "items": rows[skip:skip + size]})

    if request.action == "get_main_activities":
        masters, seen = [], set()
        for it in _filter(items, f):
            if it["masterId"] in seen:
                continue
            seen.add(it["masterId"])
            masters.append({
                "id": it["masterId"], "typeId": it["typeId"], "name": it["masterName"],
                "status": it["status"], "priorityId": it["priorityId"], "priorityName": it["priorityName"],
                "onlyMe": it["onlyMe"], "startDateTime": it["masterData"]["fromDateTime"],
                "endDateTime": it["masterData"]["endDateTime"],
            })
        return _ok({"totalCount": len(masters), "items": masters[skip:skip + size]})

    if request.action == "get_dashboard":
        rows = _filter(items, f, use_type=False, use_priority=False, use_search=False)
        return _ok(_dashboard(rows, now))

    raise ValueError("unknown action %r" % request.action)
