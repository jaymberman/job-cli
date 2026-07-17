import json

import job


def read_data():
    with open(job.storage.DATA_FILE) as f:
        return json.load(f)


def test_status_updates_and_persists(run_cli, freeze_date):
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")
    freeze_date(2026, 1, 5)
    out = run_cli("Big Corp", "status", "Interviewing")
    assert "Updated Big Corp:" in out
    (rec,) = read_data().values()
    assert rec["status"] == "Interviewing"
    assert rec["status_changed"] == "2026-01-05"
    assert rec["applied"] == "2026-01-01"


def test_status_no_match_prints_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co", "status", "Interviewing")
    assert out.strip() == "no applications sent"


def test_status_fuzzy_match_resolves(run_cli):
    run_cli("foobar Consulting", "Data Engineer")
    out = run_cli("foobar", "status", "Interviewing")
    assert "Updated foobar Consulting:" in out


def test_status_is_freeform_text_no_validation(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "status", "some totally arbitrary freeform text!!")
    (rec,) = read_data().values()
    assert rec["status"] == "some totally arbitrary freeform text!!"
