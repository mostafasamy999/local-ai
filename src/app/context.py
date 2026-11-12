"""Conversation context: the last action + arguments, and follow-up merging.

See agent/conversation_rules.md.
"""
import re
from typing import Any, Dict, List, Optional

from app.schema import ACTION_ARGS, dumps

_EN_FOLLOW = re.compile(
    r"^\s*(and|what about|how about|only|just|also|same|now|but|then|ok and|okay and)\b", re.IGNORECASE)
_AR_FOLLOW = re.compile(r"^\s*(وماذا عن|ماذا عن|وماذا|طيب|طب|بس|فقط|نفس|كمان|وال|و\s|و(?=[؀-ۿ]))")
_RESET = re.compile(r"^\s*(start over|new question|reset|clear|ابدأ من جديد|سؤال جديد|امسح)\s*[.!؟?]*\s*$",
                    re.IGNORECASE)
_DATE_KEYS = ("dateRange", "fromDate", "toDate")


def is_follow_up(text: str) -> bool:
    return bool(_EN_FOLLOW.match(text) or _AR_FOLLOW.match(text))


def is_reset(text: str) -> bool:
    return bool(_RESET.match(text))


def merge_arguments(previous: Dict[str, Any], new: Dict[str, Any], action: str) -> Dict[str, Any]:
    """Keep the previous values, overwrite only what the new turn set (non-null)."""
    keys = ACTION_ARGS[action]
    merged = {k: previous.get(k) for k in keys}
    new_sets_date = any(new.get(k) is not None for k in _DATE_KEYS)
    if new_sets_date:
        for k in _DATE_KEYS:
            merged[k] = None
    for k in keys:
        if new.get(k) is not None:
            merged[k] = new[k]
    return merged


class Context:
    def __init__(self) -> None:
        self.last_action: Optional[str] = None
        self.last_arguments: Optional[Dict[str, Any]] = None
        self.history: List[Dict[str, str]] = []   # last user + assistant JSON pair
        self.pending_question = False

    def clear(self) -> None:
        self.last_action = None
        self.last_arguments = None
        self.history = []
        self.pending_question = False

    @property
    def active(self) -> bool:
        return self.last_action is not None or self.pending_question

    def messages_for(self, user_text: str) -> List[Dict[str, str]]:
        """History (if any) + the new user message. The system prompt is added by the llm."""
        return list(self.history) + [{"role": "user", "content": user_text}]

    def apply(self, user_text: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """Merge the model output with the context, update the context, return the final output."""
        follow = is_follow_up(user_text)
        result = dict(output)

        if output.get("refused"):
            self.clear()
            return result

        if output.get("needs_clarification"):
            # The vague message starts a new topic; the model reads the answer together with it (history).
            self.last_action = None
            self.last_arguments = None
            self.pending_question = True
            self.history = [{"role": "user", "content": user_text}, {"role": "assistant", "content": dumps(result)}]
            return result

        action = output["action"]
        args = output["arguments"] or {}
        if follow and self.last_action is not None and self.last_arguments is not None:
            args = merge_arguments(self.last_arguments, args, action)
            result["arguments"] = args

        self.last_action = action
        self.last_arguments = dict(args)
        self.pending_question = False
        # The history keeps the merged JSON, so the next follow-up sees the full current request.
        self.history = [{"role": "user", "content": user_text}, {"role": "assistant", "content": dumps(result)}]
        return result
