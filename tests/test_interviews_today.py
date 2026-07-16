from datetime import datetime
from zoneinfo import ZoneInfo

import job


# ---- cmd_interviews / job interviews ----------------------------------------

def test_interviews_empty_says_no_interviews_scheduled(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("interviews")
    assert out.strip() == "no interviews scheduled"


def test_interviews_default_excludes_past_and_includes_future(run_cli, stub_confirm, freeze_date, freeze_now):
    # "Nimbus Systems"/"Vertex Robotics" are deliberately fuzzy-dissimilar
    # (score well under CONFIRM_THRESHOLD) so that create's own duplicate-
    # active fuzzy check can't accidentally collide the two companies.
    stub_confirm(True)
    freeze_date(2026, 1, 10)
    run_cli("Nimbus Systems", "Data Engineer")
    run_cli("Nimbus Systems", "interview", "2026-01-09", "13:00", "CT")
    run_cli("Vertex Robotics", "Data Engineer")
    run_cli("Vertex Robotics", "interview", "2026-01-11", "13:00", "CT")

    freeze_now(datetime(2026, 1, 10, 13, 0, tzinfo=ZoneInfo("America/Chicago")))
    out = run_cli("interviews")
    assert "Vertex Robotics" in out
    assert "Nimbus Systems" not in out


def test_interviews_all_includes_past_and_soft_deleted(run_cli, stub_confirm, freeze_date, freeze_now):
    stub_confirm(True)
    freeze_date(2026, 1, 10)
    run_cli("Nimbus Systems", "Data Engineer")
    run_cli("Nimbus Systems", "interview", "2026-01-09", "13:00", "CT")
    run_cli("Halcyon Group", "Data Engineer")
    run_cli("Halcyon Group", "interview", "2026-01-09", "14:00", "CT")
    run_cli("Halcyon Group", "delete")

    freeze_now(datetime(2026, 1, 10, 13, 0, tzinfo=ZoneInfo("America/Chicago")))
    out = run_cli("interviews", "--all")
    assert "Nimbus Systems" in out
    assert "Halcyon Group" in out
    assert "Deleted" in out


def test_interviews_sorted_by_datetime_descending(run_cli, stub_confirm, freeze_date, freeze_now):
    stub_confirm(True)
    freeze_date(2026, 1, 1)
    run_cli("Aurora Dynamics", "Data Engineer")
    run_cli("Aurora Dynamics", "interview", "2026-02-01", "13:00", "CT")
    run_cli("Zephyr Analytics", "Data Engineer")
    run_cli("Zephyr Analytics", "interview", "2026-03-01", "13:00", "CT")

    freeze_now(datetime(2026, 1, 5, 13, 0, tzinfo=ZoneInfo("America/Chicago")))
    out = run_cli("interviews")
    assert out.index("Zephyr Analytics") < out.index("Aurora Dynamics")


def test_interviews_unrecognized_argument_errors(run_cli):
    out = run_cli("interviews", "bogus")
    assert "Unrecognized `job interviews` arguments" in out


def test_interviews_help(run_cli):
    out = run_cli("interviews", "help")
    assert "Usage: job interviews" in out


# ---- cmd_today / job today ---------------------------------------------------

def test_today_includes_applied_today(run_cli, freeze_date):
    freeze_date(2026, 1, 10)
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("today")
    assert "Big Corp" in out


def test_today_includes_status_changed_today(run_cli, freeze_date):
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")
    freeze_date(2026, 1, 10)
    run_cli("Big Corp", "status", "Interviewing")
    out = run_cli("today")
    assert "Big Corp" in out


def test_today_includes_interview_scheduled_today_even_if_already_passed(run_cli, stub_confirm, freeze_date):
    stub_confirm(True)
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "interview", "2026-01-10", "13:00", "CT")
    freeze_date(2026, 1, 10)
    out = run_cli("today")
    assert "Big Corp" in out


def test_today_excludes_unrelated_records(run_cli, freeze_date):
    freeze_date(2026, 1, 1)
    run_cli("Old Corp", "Data Engineer")
    freeze_date(2026, 1, 10)
    out = run_cli("today")
    assert out.strip() == "no activity today"


def test_today_all_includes_records_deleted_today(run_cli, stub_confirm, freeze_date):
    stub_confirm(True)
    freeze_date(2026, 1, 1)
    run_cli("Old Corp", "Data Engineer")
    freeze_date(2026, 1, 10)
    run_cli("Old Corp", "delete")

    out_default = run_cli("today")
    assert out_default.strip() == "no activity today"
    out_all = run_cli("today", "--all")
    assert "Old Corp" in out_all


def test_today_sorted_by_company_name_ascending(run_cli, freeze_date):
    freeze_date(2026, 1, 10)
    run_cli("Zeta Co", "Data Engineer")
    run_cli("Alpha Co", "Data Engineer")
    out = run_cli("today")
    assert out.index("Alpha Co") < out.index("Zeta Co")


def test_today_help(run_cli):
    out = run_cli("today", "help")
    assert "Usage: job today" in out


def test_today_unrecognized_argument_errors(run_cli):
    out = run_cli("today", "bogus")
    assert "Unrecognized `job today` arguments" in out
