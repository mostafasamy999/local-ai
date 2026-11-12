"""API result -> one Arabic or English answer, from templates. No LLM here."""
from typing import Any, Dict, List, Optional

from app.agent import ActionRequest

STATUS = {
    "en": {1: "pending", 2: "in progress", 3: "cancelled", 4: "completed", 5: "rejected", 7: "partially completed"},
    "ar": {1: "معلقة", 2: "قيد التنفيذ", 3: "ملغاة", 4: "مكتملة", 5: "مرفوضة", 7: "مكتملة جزئياً"},
}
PRIORITY = {"en": {1: "low", 2: "medium", 3: "high"}, "ar": {1: "منخفضة", 2: "متوسطة", 3: "عالية"}}
NOUN = {
    "en": {"get_visits": "visits", "get_tasks": "tasks", "get_main_activities": "main activities"},
    "ar": {"get_visits": "زيارات", "get_tasks": "مهام", "get_main_activities": "أنشطة رئيسية"},
}
MAX_LINES = 5


def _period(req: ActionRequest, lang: str) -> str:
    a, f = req.arguments, req.filters
    names = {
        "en": {"today": "today", "yesterday": "yesterday", "last_7_days": "in the last 7 days",
               "this_week": "this week", "last_week": "last week", "this_month": "this month",
               "current": "from today on", "previous": "before today"},
        "ar": {"today": "اليوم", "yesterday": "أمس", "last_7_days": "خلال آخر 7 أيام",
               "this_week": "هذا الأسبوع", "last_week": "الأسبوع الماضي", "this_month": "هذا الشهر",
               "current": "من اليوم فصاعداً", "previous": "قبل اليوم"},
    }[lang]
    if a.get("fromDate") or a.get("toDate"):
        frm, to = a.get("fromDate"), a.get("toDate")
        if lang == "ar":
            return "من %s إلى %s" % (frm or "البداية", to or "الآن")
        return "from %s to %s" % (frm or "the start", to or "now")
    if f.get("fromDateTime") is None and f.get("endDateTime") is None:
        return ""
    return names.get(a.get("dateRange") or "last_7_days", "")


def _filters_text(req: ActionRequest, lang: str) -> str:
    a = req.arguments
    parts = []
    if a.get("statusId"):
        parts.append(STATUS[lang][a["statusId"]])
    if a.get("priorityId"):
        parts.append(("أولوية " if lang == "ar" else "") + PRIORITY[lang][a["priorityId"]]
                     + ("" if lang == "ar" else " priority"))
    if a.get("search"):
        parts.append(("تطابق \"%s\"" if lang == "ar" else "matching \"%s\"") % a["search"])
    return (" (" + "، ".join(parts) + ")") if lang == "ar" and parts else (" (" + ", ".join(parts) + ")" if parts else "")


def _line(item: Dict[str, Any], lang: str) -> str:
    title = item.get("masterName") or item.get("name") or ("بدون عنوان" if lang == "ar" else "untitled")
    sid = (item.get("status") or {}).get("id")
    status = STATUS[lang].get(sid, "")
    start = (item.get("masterData") or {}).get("fromDateTime") or item.get("startDateTime") or ""
    when = start.replace("T", " ")[:16]
    return "- %s — %s%s" % (title, status, (" — " + when) if when else "")


def _list_answer(req: ActionRequest, data: Any, lang: str) -> str:
    if isinstance(data, list):
        items, total = data, len(data)
    else:
        items = (data or {}).get("items") or (data or {}).get("data") or []
        total = (data or {}).get("totalCount", len(items))
    noun = NOUN[lang][req.action]
    if req.action == "get_main_activities" and req.arguments.get("typeId"):
        noun = {"en": {1: "main tasks", 2: "main visits"}, "ar": {1: "مهام رئيسية", 2: "زيارات رئيسية"}}[lang][
            req.arguments["typeId"]]
    period = _period(req, lang)
    filt = _filters_text(req, lang)
    if not items:
        if lang == "ar":
            return "لا توجد %s%s%s." % (noun, filt, (" " + period) if period else "")
        return "No %s%s%s." % (noun, filt, (" " + period) if period else "")
    if lang == "ar":
        head = "لديك %d %s%s%s:" % (total, noun, filt, (" " + period) if period else "")
    else:
        head = "You have %d %s%s%s:" % (total, noun, filt, (" " + period) if period else "")
    lines = [_line(i, lang) for i in items[:MAX_LINES]]
    if total > MAX_LINES:
        lines.append(("... و %d أخرى." if lang == "ar" else "... and %d more.") % (total - MAX_LINES))
    return "\n".join([head] + lines)


def _count(status_list: List[Dict[str, Any]], sid: int) -> int:
    for row in status_list or []:
        if row.get("statusId") == sid:
            return int(row.get("count") or 0)
    return 0


def _dashboard_answer(req: ActionRequest, d: Dict[str, Any], lang: str) -> str:
    d = d or {}
    period = _period(req, lang)
    v, t = int(d.get("visitCount") or 0), int(d.get("taskCount") or 0)
    vs, ts = d.get("visitStatusList") or [], d.get("taskStatusList") or []
    vl, tl = int(d.get("visitsLate") or 0), int(d.get("tasksLate") or 0)
    filt = _filters_text(req, lang)
    if v == 0 and t == 0:
        return ("لا توجد أنشطة%s%s." % (filt, (" " + period) if period else "")) if lang == "ar" else \
            ("No activities%s%s." % (filt, (" " + period) if period else ""))
    if lang == "ar":
        return "\n".join([
            "ملخص الأنشطة%s%s:" % (filt, (" " + period) if period else ""),
            "- الزيارات: %d (مكتملة %d، قيد التنفيذ %d، معلقة %d، متأخرة %d)" % (
                v, _count(vs, 4), _count(vs, 2), _count(vs, 1), vl),
            "- المهام: %d (مكتملة %d، قيد التنفيذ %d، معلقة %d، متأخرة %d)" % (
                t, _count(ts, 4), _count(ts, 2), _count(ts, 1), tl),
        ])
    return "\n".join([
        "Activities summary%s%s:" % (filt, (" " + period) if period else ""),
        "- Visits: %d (completed %d, in progress %d, pending %d, late %d)" % (
            v, _count(vs, 4), _count(vs, 2), _count(vs, 1), vl),
        "- Tasks: %d (completed %d, in progress %d, pending %d, late %d)" % (
            t, _count(ts, 4), _count(ts, 2), _count(ts, 1), tl),
    ])


def respond(req: ActionRequest, api_result: Optional[Dict[str, Any]], lang: str) -> str:
    """Turn an API envelope into the sentence the user sees."""
    if not api_result or not api_result.get("success") or api_result.get("statusCode") != 200:
        msg = (api_result or {}).get("responseMessage") or ""
        if lang == "ar":
            return "عذراً، حدث خطأ أثناء جلب البيانات." + ((" (" + msg + ")") if msg else "") + " حاول مرة أخرى."
        return "Sorry, something went wrong while loading the data." + ((" (" + msg + ")") if msg else "") + \
            " Please try again."
    data = api_result.get("data")
    if req.action == "get_dashboard":
        return _dashboard_answer(req, data, lang)
    return _list_answer(req, data, lang)
