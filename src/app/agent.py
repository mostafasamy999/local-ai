"""User text -> validated action request.

call the llm -> parse JSON -> validate -> if invalid, retry once with the error -> merge with context.
The model never fills ids, tokens or timestamps: build_request() turns its arguments into the
endpoint filters (dates resolved by app/dates.py). Session ids are added by the backend, not here.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from app import dates
from app.context import Context, is_reset
from app.schema import SchemaError, dumps, parse_output

ENDPOINTS = {
    "get_visits": "Mobile/VisitAndTask/GetVisitAndTaskAssignedToLoggedInUser",
    "get_tasks": "Mobile/VisitAndTask/GetVisitAndTaskAssignedToLoggedInUser",
    "get_main_activities": "Mobile/VisitAndTask/GetVisitAndTaskList",
    "get_dashboard": "Mobile/VisitAndTask/GetTaskAndVisitDashboard",
}
FIXED_TYPE = {"get_visits": 2, "get_tasks": 1}

_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-z]")

FALLBACK = {
    "ar": "عذراً، لم أفهم طلبك. هل تريد الزيارات أم المهام أم القائمة الرئيسية أم لوحة المتابعة؟",
    "en": "Sorry, I didn't understand. Do you want your visits, tasks, the main list or the dashboard?",
}
RESET_TEXT = {"ar": "تم. اسألني من جديد.", "en": "Done. Ask me something new."}


def detect_lang(text: str) -> str:
    return "ar" if len(_ARABIC.findall(text)) >= len(_LATIN.findall(text)) and _ARABIC.search(text) else "en"


@dataclass
class ActionRequest:
    action: str
    endpoint: str
    arguments: Dict[str, Any]
    filters: Dict[str, Any]


@dataclass
class AgentResult:
    lang: str
    output: Dict[str, Any]                    # the final (validated, merged) JSON
    request: Optional[ActionRequest] = None   # set when there is an action to call
    raw: List[str] = field(default_factory=list)   # raw model texts (1 or 2 with the retry)
    errors: List[str] = field(default_factory=list)
    text: Optional[str] = None                # refusal / clarification / fallback text


def build_request(action: str, arguments: Dict[str, Any], today: Optional[date] = None) -> ActionRequest:
    """Model arguments -> endpoint filters. Scope ids/onlyMe and paging are added by the backend."""
    a = arguments
    date_range = a.get("dateRange")
    if action == "get_main_activities" and date_range in ("current", "previous"):
        date_range = None   # Main ignores Current/Previous (SC-11)
    if action == "get_main_activities" and date_range is None and not a.get("fromDate") and not a.get("toDate"):
        start, end = None, None   # Main uses a date range only if one was set (SC-11)
    else:
        start, end = dates.resolve(date_range, a.get("fromDate"), a.get("toDate"), today=today)
    filters = {
        "typeId": FIXED_TYPE.get(action, a.get("typeId")),
        "statusId": a.get("statusId"),
        "priorityId": a.get("priorityId"),
        "searchValue": a.get("search"),
        "scope": a.get("scope") or "all",
        "fromDateTime": start,
        "endDateTime": end,
    }
    if action == "get_dashboard":
        filters.pop("typeId")
        filters.pop("priorityId")
        filters.pop("searchValue")
    return ActionRequest(action=action, endpoint=ENDPOINTS[action], arguments=dict(a), filters=filters)


class Agent:
    def __init__(self, chat_fn: Callable[[List[Dict[str, str]]], str], retries: int = 1,
                 today: Optional[date] = None) -> None:
        self.chat_fn = chat_fn
        self.retries = retries
        self.today = today
        self.context = Context()

    def ask(self, user_text: str) -> AgentResult:
        lang = detect_lang(user_text)
        if is_reset(user_text):
            self.context.clear()
            return AgentResult(lang=lang, output={}, text=RESET_TEXT[lang])

        messages = self.context.messages_for(user_text)
        raw, errors = [], []
        parsed = None
        for attempt in range(self.retries + 1):
            text = self.chat_fn(messages)
            raw.append(text)
            try:
                parsed = parse_output(text)
                break
            except SchemaError as e:
                errors.append(str(e))
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "That reply was invalid (%s). Reply again with ONE valid JSON "
                                                "object only, following the schema and allowed values." % e},
                ]

        if parsed is None:
            return AgentResult(lang=lang, output={}, raw=raw, errors=errors, text=FALLBACK[lang])

        output = self.context.apply(user_text, parsed.to_dict())
        result = AgentResult(lang=lang, output=output, raw=raw, errors=errors)
        if output.get("refused"):
            result.text = output["refusal_reason"]
        elif output.get("needs_clarification"):
            result.text = output["clarification_question"]
        else:
            result.request = build_request(output["action"], output["arguments"], today=self.today)
        return result

    @staticmethod
    def debug_json(result: AgentResult) -> str:
        return dumps(result.output)
