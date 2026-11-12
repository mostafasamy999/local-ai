"""The JSON the model must return, and its validation.

Anything not listed here is rejected: unknown actions, unknown argument keys, values outside the
allowed sets, bad dates. Missing argument keys are filled with null (the model may drop them).
"""
import json
import re
from datetime import date
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

ACTIONS = ("get_visits", "get_tasks", "get_main_activities", "get_dashboard")

_LIST_ARGS = ("dateRange", "fromDate", "toDate", "statusId", "priorityId", "scope", "search")
ACTION_ARGS = {
    "get_visits": _LIST_ARGS,
    "get_tasks": _LIST_ARGS,
    "get_main_activities": ("typeId",) + _LIST_ARGS,
    "get_dashboard": ("dateRange", "fromDate", "toDate", "statusId", "scope"),
}

TYPE_IDS = {1: "Task", 2: "Visit"}
STATUS_IDS = {1: "Pending", 2: "In progress", 3: "Cancelled", 4: "Completed", 5: "Rejected", 7: "Partially completed"}
PRIORITY_IDS = {1: "low", 2: "medium", 3: "high"}
SCOPES = ("all", "my_team", "my_activities", "private")
DATE_RANGES = ("today", "yesterday", "last_7_days", "this_week", "last_week", "this_month", "current", "previous")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class SchemaError(ValueError):
    """The model output is not a valid action JSON."""


def _as_int(value: Any, allowed: Dict[int, str], name: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("%s must be a number, got %r" % (name, value))
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int) or value not in allowed:
        raise ValueError("%s must be one of %s, got %r" % (name, sorted(allowed), value))
    return value


def _as_choice(value: Any, allowed, name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or value not in allowed:
        raise ValueError("%s must be one of %s, got %r" % (name, list(allowed), value))
    return value


def _as_date(value: Any, name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("%s must be a yyyy-MM-dd string, got %r" % (name, value))
    value = value.strip().translate(_ARABIC_DIGITS)
    if not _DATE_RE.match(value):
        raise ValueError("%s must be yyyy-MM-dd, got %r" % (name, value))
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("%s is not a real date: %r" % (name, value))
    return value


def validate_arguments(action: str, arguments: Any) -> Dict[str, Any]:
    """Return a clean argument dict with every key of the action (null when absent)."""
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object for action %s" % action)
    allowed_keys = ACTION_ARGS[action]
    unknown = [k for k in arguments if k not in allowed_keys]
    if unknown:
        raise ValueError("unknown argument(s) for %s: %s" % (action, ", ".join(sorted(unknown))))

    out = {k: arguments.get(k) for k in allowed_keys}
    if "typeId" in out:
        out["typeId"] = _as_int(out["typeId"], TYPE_IDS, "typeId")
    out["statusId"] = _as_int(out["statusId"], STATUS_IDS, "statusId")
    if "priorityId" in out:
        out["priorityId"] = _as_int(out["priorityId"], PRIORITY_IDS, "priorityId")
    out["scope"] = _as_choice(out["scope"], SCOPES, "scope")
    out["dateRange"] = _as_choice(out["dateRange"], DATE_RANGES, "dateRange")
    out["fromDate"] = _as_date(out["fromDate"], "fromDate")
    out["toDate"] = _as_date(out["toDate"], "toDate")
    if "search" in out and out["search"] is not None:
        if not isinstance(out["search"], str):
            raise ValueError("search must be text, got %r" % (out["search"],))
        out["search"] = out["search"].strip() or None

    if out["dateRange"] is not None and (out["fromDate"] or out["toDate"]):
        raise ValueError("use dateRange OR fromDate/toDate, not both")
    if out["fromDate"] and out["toDate"] and out["toDate"] < out["fromDate"]:
        raise ValueError("toDate is before fromDate")
    return out


class ActionOutput(BaseModel):
    """One model reply."""

    model_config = ConfigDict(extra="forbid")

    action: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    refused: bool = False
    refusal_reason: Optional[str] = None

    @field_validator("action")
    @classmethod
    def _known_action(cls, v):
        if v is not None and v not in ACTIONS:
            raise ValueError("unknown action %r" % v)
        return v

    @model_validator(mode="after")
    def _consistent(self):
        if self.refused and self.needs_clarification:
            raise ValueError("refused and needs_clarification can't both be true")
        if self.refused or self.needs_clarification:
            if self.action is not None or self.arguments not in (None, {}):
                raise ValueError("action and arguments must be null when refusing or asking")
            self.arguments = None
            text = self.refusal_reason if self.refused else self.clarification_question
            if not text or not text.strip():
                raise ValueError("a refusal needs refusal_reason; a clarification needs clarification_question")
            if self.refused and self.clarification_question is not None:
                raise ValueError("clarification_question must be null when refusing")
            if self.needs_clarification and self.refusal_reason is not None:
                raise ValueError("refusal_reason must be null when asking")
            return self
        if self.action is None:
            raise ValueError("action is null but the request is neither refused nor a clarification")
        if self.clarification_question is not None or self.refusal_reason is not None:
            raise ValueError("clarification_question and refusal_reason must be null for an action")
        self.arguments = validate_arguments(self.action, self.arguments if self.arguments is not None else {})
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "arguments": self.arguments,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
        }


def extract_json(text: str) -> Dict[str, Any]:
    """Find the first JSON object in the model text (tolerates ``` fences and extra text)."""
    if text is None:
        raise SchemaError("empty model output")
    start = text.find("{")
    if start < 0:
        raise SchemaError("no JSON object in model output")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except json.JSONDecodeError as e:
                    raise SchemaError("invalid JSON: %s" % e)
                if not isinstance(obj, dict):
                    raise SchemaError("JSON is not an object")
                return obj
    raise SchemaError("unterminated JSON object")


def parse_output(text: str) -> ActionOutput:
    """Model text -> validated ActionOutput, or SchemaError with a short reason."""
    obj = extract_json(text)
    try:
        return ActionOutput(**obj)
    except ValidationError as e:
        reasons = "; ".join(err["msg"].replace("Value error, ", "") for err in e.errors())
        raise SchemaError(reasons)
    except TypeError as e:
        raise SchemaError(str(e))


def dumps(output: Dict[str, Any]) -> str:
    """The exact text form used in training data and prompts."""
    return json.dumps(output, ensure_ascii=False)
