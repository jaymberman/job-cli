import json

import job


def read_data():
    with open(job.DATA_FILE) as f:
        return json.load(f)


# ---- cmd_interview dispatch (cancel vs set) --------------------------------

def test_interview_no_active_record_says_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co", "interview", "2026-07-13", "13:00", "CT")
    assert out.strip() == "no applications sent"


def test_interview_set_happy_path(run_cli, stub_confirm, freeze_date):
    freeze_date(2026, 1, 1)
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "interview", "2026-07-13", "13:00", "CT")
    assert "Updated Big Corp's interview:" in out
    (rec,) = read_data().values()
    assert rec["interview"].startswith("2026-07-13T13:00:00")
    assert rec["interview_tz"] == "CT"
    assert rec["status_changed"] == "2026-01-01"


def test_interview_set_declined_leaves_interview_unset(run_cli, stub_confirm):
    stub_confirm(False)
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "interview", "2026-07-13", "13:00", "CT")
    assert "Cancelled." in out
    (rec,) = read_data().values()
    assert rec["interview"] is None


def test_interview_replacing_existing_shows_current_value_in_prompt(run_cli, monkeypatch):
    prompts = []
    monkeypatch.setattr(job, "confirm", lambda prompt: prompts.append(prompt) or True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "interview", "2026-07-13", "13:00", "CT")
    run_cli("Big Corp", "interview", "2026-08-01", "9am", "ET")
    assert "currently 2026-07-13 13:00 CT" in prompts[-1]
    assert "Set it to 2026-08-01 09:00 ET (America/New_York)?" in prompts[-1]
    (rec,) = read_data().values()
    assert rec["interview"].startswith("2026-08-01T09:00:00")
    assert rec["interview_tz"] == "ET"


def test_interview_bad_date_time_prints_error_and_saves_nothing(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "interview", "not-a-date", "13:00")
    assert "Couldn't parse interview date" in out
    (rec,) = read_data().values()
    assert rec["interview"] is None


def test_interview_missing_date_time_after_keyword(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "interview")
    assert "Missing interview date/time." in out


def test_interview_ambiguous_hour_prompts_meridiem(run_cli, stub_confirm, stub_meridiem):
    stub_confirm(True)
    stub_meridiem("pm")
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "interview", "2026-07-13", "9")
    (rec,) = read_data().values()
    assert rec["interview"].startswith("2026-07-13T21:00:00")


# ---- interview cancel -------------------------------------------------------

def test_interview_cancel_clears_fields(run_cli, stub_confirm, freeze_date):
    stub_confirm(True)
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "interview", "2026-07-13", "13:00", "CT")
    freeze_date(2026, 1, 10)
    out = run_cli("Big Corp", "interview", "cancel")
    assert "Cleared Big Corp's interview." in out
    (rec,) = read_data().values()
    assert rec["interview"] is None
    assert rec["interview_tz"] is None
    assert rec["status_changed"] == "2026-01-10"


def test_interview_cancel_needs_no_confirmation(run_cli, stub_confirm, monkeypatch):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "interview", "2026-07-13", "13:00", "CT")

    def explode(prompt):
        raise AssertionError("cancel should never call confirm()")
    monkeypatch.setattr(job, "confirm", explode)
    out = run_cli("Big Corp", "interview", "cancel")
    assert "Cleared Big Corp's interview." in out


def test_interview_cancel_when_none_scheduled_is_friendly_noop(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "interview", "cancel")
    assert "Big Corp has no interview scheduled." in out


def test_interview_cancel_with_extra_argument_is_error(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "interview", "cancel", "please")
    assert "`cancel` doesn't take an extra argument." in out
