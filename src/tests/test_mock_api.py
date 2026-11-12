from datetime import date

from app import mock_api
from app.agent import build_request

TODAY = date(2026, 11, 12)


def call(action, **args):
    return mock_api.call(build_request(action, args, today=TODAY), today=TODAY)


def test_envelope_and_visits_are_type_2():
    r = call("get_visits", dateRange="this_month")
    assert r["success"] and r["statusCode"] == 200
    items = r["data"]["items"]
    assert items and all(i["typeId"] == 2 for i in items)
    assert r["data"]["totalCount"] == len(items)
    for key in ("detailsId", "masterId", "masterName", "status", "priorityId", "onlyMe", "masterData"):
        assert key in items[0]


def test_filters_status_priority_search():
    r = call("get_tasks", dateRange="this_month", statusId=2)
    assert all(i["status"]["id"] == 2 for i in r["data"]["items"])
    r = call("get_visits", dateRange="this_month", search="maintenance")
    assert {i["masterName"] for i in r["data"]["items"]} == {"Maintenance check", "Maintenance follow-up"}


def test_today_only_returns_today():
    r = call("get_visits", dateRange="today")
    assert all(i["masterData"]["fromDateTime"].startswith("2026-11-12") for i in r["data"]["items"])


def test_private_scope():
    r = call("get_tasks", dateRange="this_month", scope="private")
    assert r["data"]["items"] and all(i["onlyMe"] for i in r["data"]["items"])


def test_main_list_shape_and_no_date_by_default():
    r = call("get_main_activities", typeId=1)
    items = r["data"]["items"]
    assert items and all("id" in i and "name" in i and i["typeId"] == 1 for i in items)
    assert r["data"]["totalCount"] == 7   # all tasks, no date filter on Main by default


def test_dashboard_counts_both_types():
    d = call("get_dashboard", dateRange="this_month")["data"]
    assert d["taskCount"] + d["visitCount"] == 14
    assert sum(s["count"] for s in d["taskStatusList"]) == d["taskCount"]
    assert "totalTasksToday" in d["taskSummary"]


def test_empty_and_failure():
    assert call("get_visits", fromDate="2020-01-01", toDate="2020-01-02")["data"]["items"] == []
    r = mock_api.call(build_request("get_visits", {}, today=TODAY), fail=True)
    assert not r["success"] and r["responseMessage"]
