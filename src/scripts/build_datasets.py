"""Generate training/ and evaluation/ datasets from phrase banks.

Deterministic (fixed seed). Training and evaluation use DIFFERENT verbs/phrasings, so no question appears
in both. Run scripts/validate_jsonl.py afterwards.

    python scripts/build_datasets.py
"""
import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import mock_api  # noqa: E402
from app.agent import build_request  # noqa: E402
from app.responder import respond  # noqa: E402
from app.schema import ACTION_ARGS, dumps, parse_output  # noqa: E402

SYSTEM = (ROOT / "config" / "system_prompt.txt").read_text(encoding="utf-8").strip()
FIXED_TODAY = date(2026, 11, 12)

# ---------------------------------------------------------------- output helpers

def act(action, **args):
    a = {k: None for k in ACTION_ARGS[action]}
    for k, v in args.items():
        assert k in a, (action, k)
        a[k] = v
    return {"action": action, "arguments": a, "needs_clarification": False, "clarification_question": None,
            "refused": False, "refusal_reason": None}


CLARIFY = {
    "en": ["Do you want your visits, your tasks, the main list or the dashboard?",
           "Which one do you mean: visits, tasks, the main list or the dashboard?"],
    "ar": ["هل تريد الزيارات أم المهام أم القائمة الرئيسية أم لوحة المتابعة؟",
           "ماذا تقصد: الزيارات أم المهام أم القائمة الرئيسية أم لوحة المتابعة؟"],
}
REFUSE_WRITE = {
    "en": ["I can only show activities. I can't create, change or delete them; please do that from the Activities screen.",
           "I'm read-only: I can show your visits and tasks, but changes have to be made in the Activities screen."],
    "ar": ["أستطيع عرض الأنشطة فقط ولا يمكنني إنشاؤها أو تعديلها أو حذفها. يمكنك فعل ذلك من شاشة الأنشطة.",
           "أنا للقراءة فقط: أعرض لك الزيارات والمهام، أما التعديل فيتم من شاشة الأنشطة."],
}
REFUSE_SCOPE = {
    "en": ["I can only answer questions about your visits and tasks.",
           "Sorry, I only help with Activities (visits and tasks)."],
    "ar": ["أستطيع الإجابة فقط عن الزيارات والمهام.",
           "عذراً، أنا أساعد فقط في الأنشطة (الزيارات والمهام)."],
}


def clarify(lang, rng):
    return {"action": None, "arguments": None, "needs_clarification": True,
            "clarification_question": rng.choice(CLARIFY[lang]), "refused": False, "refusal_reason": None}


def refuse(lang, rng, kind):
    bank = REFUSE_WRITE if kind == "write" else REFUSE_SCOPE
    return {"action": None, "arguments": None, "needs_clarification": False, "clarification_question": None,
            "refused": True, "refusal_reason": rng.choice(bank[lang])}


# ---------------------------------------------------------------- phrase banks
# Each bank has a "train" and an "eval" side where the wording matters.

STATUS = {
    "en": {1: ["pending", "waiting"], 2: ["in progress", "ongoing"], 3: ["cancelled", "canceled"],
           4: ["completed", "done", "finished"], 5: ["rejected"], 7: ["partially completed", "partly completed"]},
    "ar": {1: ["المعلقة", "قيد الانتظار"], 2: ["قيد التنفيذ", "الجارية"], 3: ["الملغاة", "الملغية"],
           4: ["المكتملة", "المنتهية"], 5: ["المرفوضة"], 7: ["المكتملة جزئياً", "المنجزة جزئياً"]},
}
PRIORITY = {
    "en": {1: ["low priority", "low-priority"], 2: ["medium priority", "medium-priority"],
           3: ["high priority", "high-priority"]},
    "ar": {1: ["ذات الأولوية المنخفضة", "بأولوية منخفضة"], 2: ["ذات الأولوية المتوسطة", "بأولوية متوسطة"],
           3: ["ذات الأولوية العالية", "بأولوية عالية"]},
}
DATES = {
    "en": {"today": ["today", "for today"], "yesterday": ["yesterday", "from yesterday"],
           "last_7_days": ["in the last 7 days", "in the last seven days"], "this_week": ["this week"],
           "last_week": ["last week", "from last week"], "this_month": ["this month", "for this month"],
           "current": ["that are upcoming", "from today onwards"], "previous": ["from before today", "in the past"]},
    "ar": {"today": ["اليوم", "لليوم"], "yesterday": ["أمس", "امبارح"],
           "last_7_days": ["خلال آخر 7 أيام", "خلال آخر سبعة أيام"], "this_week": ["هذا الأسبوع", "لهذا الأسبوع"],
           "last_week": ["الأسبوع الماضي"], "this_month": ["هذا الشهر", "لهذا الشهر"],
           "current": ["القادمة", "من اليوم فصاعداً"], "previous": ["السابقة", "قبل اليوم"]},
}
SCOPE = {
    "en": {"my_team": ["of my team", "for my team"], "my_activities": ["that are only mine", "assigned only to me"],
           "private": ["that are private", "marked private"], "all": ["for everyone I can see"]},
    "ar": {"my_team": ["الخاصة بفريقي", "لفريقي"], "my_activities": ["لي أنا فقط", "المسندة لي فقط"],
           "private": ["الخاصة السرية", "المحددة كخاصة"], "all": ["لكل من أستطيع رؤيتهم"]},
}
SEARCH = {
    "en": ["maintenance", "inspection", "audit", "training", "warehouse", "supplier", "contract", "report",
           "meeting", "branch"],
    "ar": ["الصيانة", "التفتيش", "الجرد", "التدريب", "المستودع", "المورد", "العقود", "التقرير", "الاجتماع", "الفرع"],
}
OBJ = {
    "en": {"get_visits": ["visits", "my visits"], "get_tasks": ["tasks", "my tasks"]},
    "ar": {"get_visits": ["الزيارات", "زياراتي"], "get_tasks": ["المهام", "مهامي"]},
}
VERBS = {
    "train": {"en": ["Show", "Show me", "List", "Get", "Give me", "I want to see", "Can you show", "Display"],
              "ar": ["اعرض", "اعرض لي", "أظهر", "ورّيني", "عايز أشوف", "أبغى أشوف", "هات", "أظهر لي"]},
    "eval": {"en": ["Pull up", "Bring up", "Let me see", "Could you list", "I need"],
             "ar": ["ممكن تعرض", "أريد رؤية", "افتح لي", "شوف لي", "طلّع لي"]},
}
EXPLICIT = {
    "train": [("2026-10-01", "2026-10-15"), ("2026-09-01", "2026-09-30"), ("2026-08-10", "2026-08-20"),
              ("2026-07-01", None), (None, "2026-06-30")],
    "eval": [("2026-10-05", "2026-10-12"), ("2026-05-01", None), (None, "2026-03-31")],
}
AR_MONTHS = {1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
             9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"}
EN_MONTHS = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June", 7: "July", 8: "August",
             9: "September", 10: "October", 11: "November", 12: "December"}


def date_words(d, lang, rng):
    y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:])
    if rng.random() < 0.5:
        return d
    return "%d %s %d" % (dd, AR_MONTHS[m], y) if lang == "ar" else "%d %s %d" % (dd, EN_MONTHS[m], y)


def explicit_phrase(frm, to, lang, rng):
    if lang == "en":
        if frm and to:
            return "from %s to %s" % (date_words(frm, lang, rng), date_words(to, lang, rng))
        if frm:
            return "since %s" % date_words(frm, lang, rng)
        return "until %s" % date_words(to, lang, rng)
    if frm and to:
        return "من %s إلى %s" % (date_words(frm, lang, rng), date_words(to, lang, rng))
    if frm:
        return "منذ %s" % date_words(frm, lang, rng)
    return "حتى %s" % date_words(to, lang, rng)


# ---------------------------------------------------------------- list requests

def list_request(lang, split, rng, action=None, n_filters=None):
    action = action or rng.choice(["get_visits", "get_tasks"])
    n = n_filters if n_filters is not None else rng.choice([0, 1, 1, 2, 2, 2, 3])
    kinds = rng.sample(["status", "priority", "date", "scope", "search"], n)
    args, words = {}, {}
    for k in kinds:
        if k == "status":
            sid = rng.choice(list(STATUS[lang]))
            args["statusId"] = sid
            words["status"] = rng.choice(STATUS[lang][sid])
        elif k == "priority":
            pid = rng.choice([1, 2, 3])
            args["priorityId"] = pid
            words["priority"] = rng.choice(PRIORITY[lang][pid])
        elif k == "date":
            if rng.random() < 0.18:
                frm, to = rng.choice(EXPLICIT[split])
                args["fromDate"], args["toDate"] = frm, to
                words["date"] = explicit_phrase(frm, to, lang, rng)
            else:
                dr = rng.choice(list(DATES[lang]))
                args["dateRange"] = dr
                words["date"] = rng.choice(DATES[lang][dr])
        elif k == "scope":
            sc = rng.choice(["my_team", "my_team", "my_activities", "private", "private", "all"])
            args["scope"] = sc
            words["scope"] = rng.choice(SCOPE[lang][sc])
        elif k == "search":
            w = rng.choice(SEARCH[lang])
            args["search"] = w
            words["search"] = w
    for k in ("fromDate", "toDate"):
        if k in args and args[k] is None:
            del args[k]
    verb = rng.choice(VERBS[split][lang])
    obj = rng.choice(OBJ[lang][action])
    if lang == "en" and ("status" in words or "priority" in words):
        obj = OBJ[lang][action][0]   # "pending visits", never "pending my visits"
    if lang == "en":
        parts = [verb]
        if "status" in words:
            parts.append(words["status"])
        if "priority" in words:
            parts.append(words["priority"])
        parts.append(obj)
        if "search" in words:
            parts.append(rng.choice(["about", "with", "mentioning"]) + " " + words["search"])
        if "scope" in words:
            parts.append(words["scope"])
        if "date" in words:
            parts.append(words["date"])
        text = " ".join(parts)
    else:
        parts = [verb, obj]
        if "status" in words:
            parts.append(words["status"])
        if "priority" in words:
            parts.append(words["priority"])
        if "search" in words:
            parts.append(rng.choice(["عن", "التي تخص", "بخصوص"]) + " " + words["search"])
        if "scope" in words:
            parts.append(words["scope"])
        if "date" in words:
            parts.append(words["date"])
        text = " ".join(parts)
    if rng.random() < 0.3:
        text += "?" if lang == "en" else "؟"
    return text, act(action, **args)


QUESTION_FORMS = {
    "train": {
        "en": [("What {obj} do I have {date}?", "date"), ("Which {obj} are {status}?", "status"),
               ("Any {status} {obj}?", "status"), ("What are my {prio} {obj}?", "priority")],
        "ar": [("ما هي {obj} {date}؟", "date"), ("أي {obj} {status}؟", "status"),
               ("هل عندي {obj} {status}؟", "status"), ("ما {obj} {prio}؟", "priority")],
    },
    "eval": {
        "en": [("Do I have any {obj} {date}?", "date"), ("Are there {status} {obj}?", "status"),
               ("Tell me my {prio} {obj}", "priority")],
        "ar": [("في عندي {obj} {date}؟", "date"), ("هل هناك {obj} {status}؟", "status"),
               ("قل لي {obj} {prio}", "priority")],
    },
}
Q_OBJ = {"en": {"get_visits": "visits", "get_tasks": "tasks"}, "ar": {"get_visits": "زيارات", "get_tasks": "مهام"}}


def question_request(lang, split, rng):
    action = rng.choice(["get_visits", "get_tasks"])
    tmpl, kind = rng.choice(QUESTION_FORMS[split][lang])
    obj = Q_OBJ[lang][action]
    args = {}
    fill = {"obj": obj, "date": "", "status": "", "prio": ""}
    if kind == "date":
        dr = rng.choice(list(DATES[lang]))
        args["dateRange"] = dr
        fill["date"] = rng.choice(DATES[lang][dr])
    elif kind == "status":
        sid = rng.choice(list(STATUS[lang]))
        args["statusId"] = sid
        fill["status"] = rng.choice(STATUS[lang][sid])
    else:
        pid = rng.choice([1, 2, 3])
        args["priorityId"] = pid
        fill["prio"] = rng.choice(PRIORITY[lang][pid])
    return tmpl.format(**fill), act(action, **args)


# ---------------------------------------------------------------- main list

MAIN = {
    "train": {
        "en": [("Show the main list", None), ("Open the main activities", None), ("Main list of visits", 2),
               ("Main list of tasks", 1), ("Show the master visits", 2), ("Show the master tasks", 1),
               ("Main activities list", None), ("Go to the main list", None)],
        "ar": [("اعرض القائمة الرئيسية", None), ("افتح الأنشطة الرئيسية", None), ("القائمة الرئيسية للزيارات", 2),
               ("القائمة الرئيسية للمهام", 1), ("اعرض الزيارات الأساسية", 2), ("اعرض المهام الأساسية", 1),
               ("قائمة الأنشطة الرئيسية", None), ("روح للقائمة الرئيسية", None)],
    },
    "eval": {
        "en": [("The main list", None), ("I need the main list of visits", 2), ("Master list for tasks", 1)],
        "ar": [("أعطني القائمة الرئيسية", None), ("أريد القائمة الرئيسية للزيارات", 2), ("القائمة الأساسية للمهام", 1)],
    },
}


def main_request(lang, split, rng):
    text, type_id = rng.choice(MAIN[split][lang])
    args = {}
    if type_id:
        args["typeId"] = type_id
    extras = rng.sample(["status", "priority", "date", "search"], rng.choice([0, 1, 1, 2]))
    for k in extras:
        if k == "status":
            sid = rng.choice(list(STATUS[lang]))
            args["statusId"] = sid
            text += (" " + ("that are " if lang == "en" else "") + rng.choice(STATUS[lang][sid]))
        elif k == "priority":
            pid = rng.choice([1, 2, 3])
            args["priorityId"] = pid
            text += (" with " + rng.choice(PRIORITY[lang][pid]) if lang == "en" else " " + rng.choice(PRIORITY[lang][pid]))
        elif k == "date":
            dr = rng.choice(["today", "this_week", "last_week", "this_month", "yesterday"])
            args["dateRange"] = dr
            text += " " + rng.choice(DATES[lang][dr])
        else:
            w = rng.choice(SEARCH[lang])
            args["search"] = w
            text += (" about " + w) if lang == "en" else (" عن " + w)
    return text, act("get_main_activities", **args)


# ---------------------------------------------------------------- dashboard

DASH = {
    "train": {
        "en": ["How many activities do I have", "How many visits and tasks do I have", "Show the dashboard",
               "Give me a summary", "Count my activities", "How many tasks do I have", "How many visits do I have",
               "Activities overview", "Statistics of my activities", "How many are late"],
        "ar": ["كم عدد أنشطتي", "كم زيارة ومهمة عندي", "اعرض لوحة المتابعة", "أعطني ملخص", "عد أنشطتي",
               "كم مهمة عندي", "كم زيارة عندي", "نظرة عامة على الأنشطة", "إحصائيات أنشطتي", "كم نشاط متأخر"],
    },
    "eval": {
        "en": ["What's my activity count", "Dashboard numbers", "Totals for my visits and tasks"],
        "ar": ["ما هو عدد أنشطتي", "أرقام لوحة المتابعة", "إجمالي الزيارات والمهام"],
    },
}


def dashboard_request(lang, split, rng):
    base = rng.choice(DASH[split][lang])
    args = {}
    extras = rng.sample(["status", "date", "scope"], rng.choice([0, 1, 1, 2]))
    text = base
    for k in extras:
        if k == "status":
            sid = rng.choice(list(STATUS[lang]))
            args["statusId"] = sid
            text += (" for the " + rng.choice(STATUS[lang][sid]) + " ones") if lang == "en" else (
                " للأنشطة " + rng.choice(STATUS[lang][sid]))
        elif k == "date":
            if rng.random() < 0.15:
                frm, to = rng.choice(EXPLICIT[split])
                if frm:
                    args["fromDate"] = frm
                if to:
                    args["toDate"] = to
                text += " " + explicit_phrase(frm, to, lang, rng)
            else:
                dr = rng.choice(["today", "yesterday", "last_7_days", "this_week", "last_week", "this_month"])
                args["dateRange"] = dr
                text += " " + rng.choice(DATES[lang][dr])
        else:
            sc = rng.choice(["my_team", "my_activities", "private"])
            args["scope"] = sc
            text += " " + rng.choice(SCOPE[lang][sc])
    text += "?" if lang == "en" else "؟"
    return text, act("get_dashboard", **args)


def count_with_priority(lang, split, rng):
    """'How many high priority tasks' -> the dashboard has no priority filter, so use the list (it has a total)."""
    action = rng.choice(["get_visits", "get_tasks"])
    pid = rng.choice([1, 2, 3])
    obj = Q_OBJ[lang][action]
    if lang == "en":
        lead = "How many" if split == "train" else "What's the number of"
        tail = " do I have?" if split == "train" else "?"
        text = "%s %s %s%s" % (lead, rng.choice(PRIORITY[lang][pid]), obj, tail)
    else:
        lead = "كم عدد" if split == "train" else "ما عدد"
        text = "%s ال%s %s؟" % (lead, obj, rng.choice(PRIORITY[lang][pid]))
    return text, act(action, priorityId=pid)


# ---------------------------------------------------------------- vague / refusals / out of scope

VAGUE = {
    "train": {
        "en": ["Show me", "What do I have?", "Details please", "Activities", "Anything new?", "Show", "List them",
               "What's there?", "Help", "Open it", "Show everything", "What about my stuff?", "The pending ones",
               "Only high priority", "For today", "Can you check?", "Give me the list", "Status?"],
        "ar": ["اعرض لي", "ماذا لدي؟", "التفاصيل من فضلك", "الأنشطة", "هل يوجد جديد؟", "اعرض", "اعرضها",
               "ايش في؟", "ساعدني", "افتحها", "اعرض كل شيء", "وش عندي؟", "المعلقة", "بس العالية", "لليوم",
               "ممكن تشيك؟", "أعطني القائمة", "الحالة؟"],
    },
    "eval": {
        "en": ["Show stuff", "What's up with my work?", "The completed ones", "Check"],
        "ar": ["وريني حاجة", "إيش أخباري؟", "المكتملة", "شيك"],
    },
}
WRITE = {
    "train": {
        "en": ["Create a new visit for tomorrow", "Add a task called monthly report", "Delete my last task",
               "Cancel today's visit", "Reschedule my visit to next Monday", "Change the status of my task to completed",
               "Mark the inspection task as done", "Approve the pending task", "Reject the branch visit",
               "Assign this task to my colleague", "Edit the title of my visit", "Update the progress to 50%",
               "Check me in to my visit", "Start my task", "Add a note to the visit", "Disable the main activity",
               "Remove all cancelled tasks", "Set the priority of my task to high", "Move my meeting to tomorrow",
               "Complete the audit visit", "Create a private task for me", "Delete the visit to the warehouse"],
        "ar": ["أنشئ زيارة جديدة لبكرة", "أضف مهمة اسمها التقرير الشهري", "احذف آخر مهمة", "ألغِ زيارة اليوم",
               "أعد جدولة زيارتي ليوم الاثنين القادم", "غيّر حالة مهمتي إلى مكتملة", "اجعل مهمة التفتيش منتهية",
               "وافق على المهمة المعلقة", "ارفض زيارة الفرع", "أسند هذه المهمة لزميلي", "عدّل عنوان زيارتي",
               "حدّث نسبة الإنجاز إلى 50%", "سجّل دخولي للزيارة", "ابدأ مهمتي", "أضف ملاحظة على الزيارة",
               "عطّل النشاط الرئيسي", "امسح كل المهام الملغاة", "اجعل أولوية مهمتي عالية", "انقل اجتماعي لبكرة",
               "أنهِ زيارة الجرد", "أنشئ مهمة خاصة لي", "احذف زيارة المستودع"],
    },
    "eval": {
        "en": ["Please create a visit to the supplier", "Cancel all my pending tasks", "Postpone the audit to Sunday",
               "Mark my visit as completed"],
        "ar": ["من فضلك أنشئ زيارة للمورد", "ألغِ كل مهامي المعلقة", "أجّل الجرد ليوم الأحد", "اجعل زيارتي مكتملة"],
    },
}
OUT = {
    "train": {
        "en": ["How many leave days do I have?", "When is payday?", "What's the weather tomorrow?", "Tell me a joke",
               "What time did I check in to work today?", "Request a vacation for next week", "Show my salary slip",
               "Who is my manager?", "What is the company phone number?", "Translate hello to French",
               "How many sick days are left?", "Show my attendance this month", "What's 15 times 4?",
               "Write me an email to HR", "When are the public holidays?", "What's my overtime?"],
        "ar": ["كم يوم إجازة متبقي لي؟", "متى ينزل الراتب؟", "كيف الطقس بكرة؟", "احكِ لي نكتة",
               "متى سجلت حضوري اليوم؟", "اطلب لي إجازة الأسبوع القادم", "اعرض كشف راتبي", "من هو مديري؟",
               "ما رقم هاتف الشركة؟", "ترجم مرحبا للفرنسية", "كم يوم إجازة مرضية باقي؟", "اعرض حضوري هذا الشهر",
               "كم حاصل 15 في 4؟", "اكتب لي إيميل للموارد البشرية", "متى العطل الرسمية؟", "كم ساعات العمل الإضافي؟"],
    },
    "eval": {
        "en": ["How much is my bonus?", "Book a meeting room", "What's the news today?", "Show my leave balance"],
        "ar": ["كم المكافأة حقتي؟", "احجز قاعة اجتماعات", "ما أخبار اليوم؟", "اعرض رصيد إجازاتي"],
    },
}

# ---------------------------------------------------------------- follow-ups

FOLLOW = {
    "train": {
        "en": [("And yesterday?", {"dateRange": "yesterday"}), ("What about last week?", {"dateRange": "last_week"}),
               ("And this month?", {"dateRange": "this_month"}), ("Only the completed ones", {"statusId": 4}),
               ("And the cancelled ones?", {"statusId": 3}), ("Only high priority", {"priorityId": 3}),
               ("What about low priority?", {"priorityId": 1}), ("And for my team?", {"scope": "my_team"}),
               ("Only the private ones", {"scope": "private"}), ("And my tasks?", {"__action": "get_tasks"}),
               ("And my visits?", {"__action": "get_visits"}), ("Now the pending ones", {"statusId": 1})],
        "ar": [("وأمس؟", {"dateRange": "yesterday"}), ("طيب والأسبوع الماضي؟", {"dateRange": "last_week"}),
               ("وهذا الشهر؟", {"dateRange": "this_month"}), ("بس المكتملة", {"statusId": 4}),
               ("وماذا عن الملغاة؟", {"statusId": 3}), ("فقط ذات الأولوية العالية", {"priorityId": 3}),
               ("طيب والأولوية المنخفضة؟", {"priorityId": 1}), ("ولفريقي؟", {"scope": "my_team"}),
               ("بس الخاصة السرية", {"scope": "private"}), ("والمهام؟", {"__action": "get_tasks"}),
               ("والزيارات؟", {"__action": "get_visits"}), ("طب والمعلقة", {"statusId": 1})],
    },
    "eval": {
        "en": [("How about today?", {"dateRange": "today"}), ("Just the in progress ones", {"statusId": 2}),
               ("And medium priority?", {"priorityId": 2}), ("Same for tasks", {"__action": "get_tasks"})],
        "ar": [("وماذا عن اليوم؟", {"dateRange": "today"}), ("بس اللي قيد التنفيذ", {"statusId": 2}),
               ("والأولوية المتوسطة؟", {"priorityId": 2}), ("نفس الشيء للمهام", {"__action": "get_tasks"})],
    },
}
CLARIFY_ANSWER = {
    "train": {"en": [("Visits", "get_visits"), ("My tasks", "get_tasks"), ("The dashboard", "get_dashboard"),
                     ("Tasks please", "get_tasks")],
              "ar": [("الزيارات", "get_visits"), ("مهامي", "get_tasks"), ("لوحة المتابعة", "get_dashboard"),
                     ("المهام لو سمحت", "get_tasks")]},
    "eval": {"en": [("I meant visits", "get_visits"), ("The tasks one", "get_tasks")],
             "ar": [("أقصد الزيارات", "get_visits"), ("المهام طبعاً", "get_tasks")]},
}


def follow_up(lang, split, rng):
    base_action = rng.choice(["get_visits", "get_tasks"])
    while True:
        t1, o1 = list_request(lang, split, rng, action=base_action, n_filters=rng.choice([1, 2]))
        text, change = rng.choice(FOLLOW[split][lang])
        new_action = change.get("__action", base_action)
        if new_action != base_action or any(o1["arguments"].get(k) != v for k, v in change.items()
                                            if not k.startswith("__")):
            break
    a = dict(o1["arguments"])
    if any(k in change for k in ("dateRange", "fromDate", "toDate")):
        a["fromDate"] = a["toDate"] = a["dateRange"] = None
    for k, v in change.items():
        if not k.startswith("__"):
            a[k] = v
    o2 = act(new_action, **{k: v for k, v in a.items() if k in ACTION_ARGS[new_action]})
    return [{"role": "user", "content": t1}, {"role": "assistant", "content": dumps(o1)},
            {"role": "user", "content": text}], o2


def clarify_follow_up(lang, split, rng):
    hints = {
        "train": {"en": {"The pending ones": {"statusId": 1}, "Only high priority": {"priorityId": 3},
                         "For today": {"dateRange": "today"}},
                  "ar": {"المعلقة": {"statusId": 1}, "بس العالية": {"priorityId": 3}, "لليوم": {"dateRange": "today"}}},
        "eval": {"en": {"The cancelled ones": {"statusId": 3}}, "ar": {"الملغاة": {"statusId": 3}}},
    }[split][lang]
    vague = rng.choice(sorted(hints))
    hint = hints[vague]
    answer, action = rng.choice(CLARIFY_ANSWER[split][lang])
    args = {k: v for k, v in hint.items() if k in ACTION_ARGS[action]}
    return [{"role": "user", "content": vague}, {"role": "assistant", "content": dumps(clarify(lang, rng))},
            {"role": "user", "content": answer}], act(action, **args)


# ---------------------------------------------------------------- build

def single(text, out):
    return [{"role": "user", "content": text}], out


def intent_of(out):
    if out["refused"]:
        return None
    if out["needs_clarification"]:
        return "needs_clarification"
    return out["action"]


def build_split(split, counts, rng, seen):
    """Return rows: dicts with lang, category, messages (no system), expected."""
    rows = []
    makers = {
        "list": lambda l: single(*list_request(l, split, rng)),
        "question": lambda l: single(*question_request(l, split, rng)),
        "main": lambda l: single(*main_request(l, split, rng)),
        "dashboard": lambda l: single(*dashboard_request(l, split, rng)),
        "count_priority": lambda l: single(*count_with_priority(l, split, rng)),
        "vague": lambda l: single(rng.choice(VAGUE[split][l]), clarify(l, rng)),
        "refusal": lambda l: single(rng.choice(WRITE[split][l]), refuse(l, rng, "write")),
        "out_of_scope": lambda l: single(rng.choice(OUT[split][l]), refuse(l, rng, "scope")),
        "follow_up": lambda l: follow_up(l, split, rng),
        "clarify_follow_up": lambda l: clarify_follow_up(l, split, rng),
    }
    for lang in ("en", "ar"):
        for cat, n in counts.items():
            made, tries = 0, 0
            while made < n and tries < n * 60:
                tries += 1
                msgs, out = makers[cat](lang)
                key = tuple(m["content"] for m in msgs if m["role"] == "user")
                norm = tuple(k.strip().lower().rstrip("?؟") for k in key)
                if norm in seen:
                    continue
                seen.add(norm)
                parse_output(dumps(out))   # every expected answer must pass our own schema
                rows.append({"lang": lang, "category": cat, "messages": msgs, "expected": out})
                made += 1
    return rows


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    rng = random.Random(20261112)
    seen = set()
    # evaluation first, so its questions are reserved and never generated for training
    eval_counts = {"list": 8, "question": 3, "main": 3, "dashboard": 3, "count_priority": 2, "vague": 4,
                   "refusal": 4, "out_of_scope": 4, "follow_up": 4, "clarify_follow_up": 2}
    eval_rows = build_split("eval", eval_counts, rng, seen)
    train_counts = {"list": 75, "question": 14, "main": 14, "dashboard": 22, "count_priority": 6, "vague": 16,
                    "refusal": 20, "out_of_scope": 15, "follow_up": 18, "clarify_follow_up": 6}
    train_rows = build_split("train", train_counts, rng, seen)

    tool_rows = [{"messages": [{"role": "system", "content": SYSTEM}] + r["messages"] +
                  [{"role": "assistant", "content": dumps(r["expected"])}]} for r in train_rows]
    rng.shuffle(tool_rows)
    write_jsonl(ROOT / "training" / "tool_call_dataset.jsonl", tool_rows)

    intents = []
    for r in train_rows:
        if len(r["messages"]) != 1:
            continue
        intent = intent_of(r["expected"])
        if intent is None:
            intent = "out_of_scope" if r["category"] == "out_of_scope" else "refused_write"
        intents.append({"text": r["messages"][0]["content"], "lang": r["lang"], "intent": intent})
    rng.shuffle(intents)
    write_jsonl(ROOT / "training" / "intent_dataset.jsonl", intents)

    eval_rows.sort(key=lambda r: (r["category"], r["lang"]))
    tests, expected = [], []
    for i, r in enumerate(eval_rows, 1):
        rid = "T%03d" % i
        tests.append({"id": rid, "lang": r["lang"], "category": r["category"], "messages": r["messages"]})
        expected.append({"id": rid, "expected": r["expected"]})
    write_jsonl(ROOT / "evaluation" / "test_questions.jsonl", tests)
    write_jsonl(ROOT / "evaluation" / "expected_results.jsonl", expected)

    write_jsonl(ROOT / "training" / "response_examples.jsonl", response_examples(rng))

    print("tool_call_dataset: %d, intent_dataset: %d, eval: %d" % (len(tool_rows), len(intents), len(tests)))


def response_examples(rng):
    """Final answers built by app/responder.py from app/mock_api.py results (fixed date 2026-11-12)."""
    cases = [
        ("get_visits", {"dateRange": "today"}), ("get_visits", {"dateRange": "this_month", "statusId": 1}),
        ("get_visits", {"dateRange": "this_month", "search": "maintenance"}), ("get_visits", {"dateRange": "yesterday"}),
        ("get_visits", {"scope": "private"}), ("get_visits", {"dateRange": "current"}),
        ("get_visits", {"dateRange": "this_month", "priorityId": 3}), ("get_visits", {"fromDate": "2020-01-01", "toDate": "2020-01-31"}),
        ("get_tasks", {"dateRange": "today"}), ("get_tasks", {"dateRange": "this_month"}),
        ("get_tasks", {"dateRange": "this_month", "statusId": 2}), ("get_tasks", {"dateRange": "previous"}),
        ("get_tasks", {"dateRange": "this_month", "scope": "private"}), ("get_tasks", {"statusId": 5}),
        ("get_tasks", {"dateRange": "last_week"}), ("get_tasks", {"dateRange": "this_week", "priorityId": 1}),
        ("get_main_activities", {}), ("get_main_activities", {"typeId": 2}), ("get_main_activities", {"typeId": 1, "statusId": 1}),
        ("get_main_activities", {"search": "audit"}), ("get_main_activities", {"priorityId": 3, "dateRange": "this_month"}),
        ("get_dashboard", {}), ("get_dashboard", {"dateRange": "today"}), ("get_dashboard", {"dateRange": "this_month"}),
        ("get_dashboard", {"dateRange": "this_month", "statusId": 4}), ("get_dashboard", {"scope": "private", "dateRange": "this_month"}),
        ("get_dashboard", {"fromDate": "2020-01-01", "toDate": "2020-01-31"}),
    ]
    rows = []
    for lang in ("en", "ar"):
        for action, args in cases:
            req = build_request(action, args, today=FIXED_TODAY)
            api = mock_api.call(req, today=FIXED_TODAY)
            rows.append({"lang": lang, "action": action, "api_result": api, "response": respond(req, api, lang)})
        for action in ("get_visits", "get_tasks", "get_dashboard", "get_main_activities"):
            req = build_request(action, {}, today=FIXED_TODAY)
            api = mock_api.call(req, fail=True)
            rows.append({"lang": lang, "action": action, "api_result": api, "response": respond(req, api, lang)})
    return rows


if __name__ == "__main__":
    main()
