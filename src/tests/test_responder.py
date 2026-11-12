from datetime import date

from app import mock_api
from app.agent import build_request
from app.responder import respond

TODAY = date(2026, 11, 12)


def run(action, lang, fail=False, **args):
    req = build_request(action, args, today=TODAY)
    return respond(req, mock_api.call(req, today=TODAY, fail=fail), lang)


def test_list_english_and_arabic():
    en = run("get_visits", "en", dateRange="today")
    assert en.startswith("You have 2 visits today:") and "Site inspection" in en
    ar = run("get_visits", "ar", dateRange="today")
    assert ar.startswith("لديك 2 زيارات اليوم:") and "معلقة" in ar


def test_filters_in_sentence():
    en = run("get_tasks", "en", dateRange="this_month", statusId=2, priorityId=3)
    assert "(in progress, high priority)" in en


def test_empty_list():
    assert run("get_tasks", "en", fromDate="2020-01-01", toDate="2020-01-02") == \
        "No tasks from 2020-01-01 to 2020-01-02."
    assert run("get_visits", "ar", fromDate="2020-01-01", toDate="2020-01-02").startswith("لا توجد زيارات")


def test_dashboard():
    en = run("get_dashboard", "en", dateRange="this_month")
    assert en.startswith("Activities summary this month:") and "- Visits: 7" in en and "- Tasks: 7" in en
    ar = run("get_dashboard", "ar", dateRange="this_month")
    assert "الزيارات: 7" in ar


def test_api_error():
    assert run("get_visits", "en", fail=True).startswith("Sorry, something went wrong")
    assert run("get_visits", "ar", fail=True).startswith("عذراً، حدث خطأ")


def test_more_than_five_items_are_cut():
    en = run("get_tasks", "en", dateRange="this_month")
    assert "... and 2 more." in en


def test_main_typed_noun():
    assert run("get_main_activities", "en", typeId=2).startswith("You have 7 main visits:")


def test_plain_list_main_response():
    req = build_request("get_main_activities", {}, today=TODAY)
    out = respond(req, {"success": True, "statusCode": 200, "data": [{"id": 1, "name": "X", "status": {"id": 1}}]},
                  "en")
    assert out.startswith("You have 1 main activities:")
