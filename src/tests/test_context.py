import json
from datetime import date

from app.agent import Agent
from app.context import Context, is_follow_up, is_reset, merge_arguments


def out(action, **args):
    return {"action": action, "arguments": args, "needs_clarification": False, "clarification_question": None,
            "refused": False, "refusal_reason": None}


def full(action, **args):
    from app.schema import ACTION_ARGS
    a = {k: None for k in ACTION_ARGS[action]}
    a.update(args)
    return out(action, **a)


def test_follow_up_markers():
    for t in ["and yesterday?", "What about last week", "only the high ones", "و أمس؟", "وأمس؟",
              "طيب والمكتملة", "ماذا عن الأسبوع الماضي"]:
        assert is_follow_up(t), t
    for t in ["Show my visits", "how many tasks", "اعرض زياراتي", "كم مهمة لدي"]:
        assert not is_follow_up(t), t


def test_reset():
    assert is_reset("start over") and is_reset("ابدأ من جديد")
    assert not is_reset("start over and show visits")


def test_merge_changes_only_new_fields_and_dates_replace_each_other():
    prev = {"dateRange": None, "fromDate": "2026-10-01", "toDate": "2026-10-05", "statusId": 1,
            "priorityId": None, "scope": "my_team", "search": None}
    new = {"dateRange": "yesterday", "statusId": None}
    m = merge_arguments(prev, new, "get_visits")
    assert m == {"dateRange": "yesterday", "fromDate": None, "toDate": None, "statusId": 1,
                 "priorityId": None, "scope": "my_team", "search": None}


def test_merge_into_dashboard_drops_keys_it_does_not_have():
    prev = {"dateRange": "today", "statusId": 1, "priorityId": 3, "scope": None, "search": "x",
            "fromDate": None, "toDate": None}
    m = merge_arguments(prev, {}, "get_dashboard")
    assert set(m) == {"dateRange", "fromDate", "toDate", "statusId", "scope"}
    assert m["statusId"] == 1 and m["dateRange"] == "today"


def test_context_follow_up_keeps_previous_arguments():
    ctx = Context()
    ctx.apply("show my pending visits today", full("get_visits", statusId=1, dateRange="today"))
    # model forgot statusId on the follow-up: the context brings it back
    r = ctx.apply("and yesterday?", full("get_visits", dateRange="yesterday"))
    assert r["arguments"]["statusId"] == 1 and r["arguments"]["dateRange"] == "yesterday"
    assert json.loads(ctx.history[1]["content"])["arguments"]["statusId"] == 1


def test_new_topic_replaces_context():
    ctx = Context()
    ctx.apply("show my pending visits today", full("get_visits", statusId=1, dateRange="today"))
    r = ctx.apply("show my tasks", full("get_tasks"))
    assert r["arguments"]["statusId"] is None
    assert ctx.last_action == "get_tasks"


def test_refusal_clears_context():
    ctx = Context()
    ctx.apply("show my visits", full("get_visits"))
    ctx.apply("delete it", {"action": None, "arguments": None, "needs_clarification": False,
                            "clarification_question": None, "refused": True, "refusal_reason": "no"})
    assert ctx.last_action is None and ctx.history == []


def test_agent_retries_once_then_succeeds_and_sends_history():
    calls = []
    replies = iter(["not json", json.dumps(full("get_visits", statusId=1))])

    def fake_chat(messages):
        calls.append(messages)
        return next(replies)

    agent = Agent(fake_chat, today=date(2026, 11, 12))
    r = agent.ask("pending visits")
    assert len(r.raw) == 2 and r.errors
    assert r.request.endpoint.endswith("GetVisitAndTaskAssignedToLoggedInUser")
    assert r.request.filters["typeId"] == 2 and r.request.filters["statusId"] == 1
    assert r.request.filters["fromDateTime"] == "2026-11-06T00:00:00"

    agent.chat_fn = lambda m: (calls.append(m), json.dumps(full("get_visits", dateRange="yesterday")))[1]
    r2 = agent.ask("and yesterday?")
    assert calls[-1][0]["role"] == "user" and calls[-1][1]["role"] == "assistant"
    assert r2.output["arguments"]["statusId"] == 1


def test_agent_gives_up_after_one_retry():
    agent = Agent(lambda m: "nope")
    r = agent.ask("اعرض شيئاً")
    assert r.request is None and len(r.raw) == 2 and r.lang == "ar" and r.text
