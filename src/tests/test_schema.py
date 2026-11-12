import json

import pytest

from app.schema import ACTION_ARGS, SchemaError, extract_json, parse_output


def ok(action, **args):
    return json.dumps({"action": action, "arguments": args, "needs_clarification": False,
                       "clarification_question": None, "refused": False, "refusal_reason": None})


def test_valid_action_fills_missing_keys_with_null():
    out = parse_output(ok("get_visits", statusId=1, dateRange="today"))
    assert out.action == "get_visits"
    assert set(out.arguments) == set(ACTION_ARGS["get_visits"])
    assert out.arguments["statusId"] == 1
    assert out.arguments["priorityId"] is None


def test_digit_string_is_accepted():
    assert parse_output(ok("get_tasks", priorityId="3")).arguments["priorityId"] == 3


@pytest.mark.parametrize("bad", [
    ok("get_leave"),
    ok("get_visits", statusId=6),
    ok("get_visits", priorityId=4),
    ok("get_visits", scope="everyone"),
    ok("get_visits", dateRange="next_year"),
    ok("get_visits", categoryId=1),
    ok("get_tasks", typeId=1),
    ok("get_dashboard", priorityId=1),
    ok("get_dashboard", search="x"),
    ok("get_visits", fromDate="2026-13-01"),
    ok("get_visits", fromDate="01/10/2026"),
    ok("get_visits", dateRange="today", fromDate="2026-10-01"),
    ok("get_visits", fromDate="2026-10-10", toDate="2026-10-01"),
    ok("get_visits", statusId=True),
])
def test_unknown_values_are_rejected(bad):
    with pytest.raises(SchemaError):
        parse_output(bad)


def test_refusal_needs_reason_and_null_action():
    good = {"action": None, "arguments": None, "needs_clarification": False, "clarification_question": None,
            "refused": True, "refusal_reason": "I can only read activities."}
    assert parse_output(json.dumps(good)).refused
    with pytest.raises(SchemaError):
        parse_output(json.dumps(dict(good, refusal_reason=None)))
    with pytest.raises(SchemaError):
        parse_output(json.dumps(dict(good, action="get_visits")))


def test_clarification():
    good = {"action": None, "arguments": None, "needs_clarification": True,
            "clarification_question": "Visits or tasks?", "refused": False, "refusal_reason": None}
    assert parse_output(json.dumps(good)).needs_clarification
    with pytest.raises(SchemaError):
        parse_output(json.dumps(dict(good, refused=True)))


def test_null_action_without_reason_is_rejected():
    with pytest.raises(SchemaError):
        parse_output(ok(None))


def test_unknown_top_level_key_is_rejected():
    obj = json.loads(ok("get_visits"))
    obj["employeeId"] = 5
    with pytest.raises(SchemaError):
        parse_output(json.dumps(obj))


def test_extract_json_handles_fences_and_text():
    text = 'Sure:\n```json\n{"a": "x}y", "b": {"c": 1}}\n```'
    assert extract_json(text) == {"a": "x}y", "b": {"c": 1}}
    with pytest.raises(SchemaError):
        extract_json("no json here")
    with pytest.raises(SchemaError):
        extract_json('{"a": 1')


def test_arabic_digits_in_dates():
    out = parse_output(ok("get_visits", fromDate="٢٠٢٦-١٠-٠١"))
    assert out.arguments["fromDate"] == "2026-10-01"
