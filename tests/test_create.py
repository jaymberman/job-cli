import json

import job


def read_data():
    with open(job.DATA_FILE) as f:
        return json.load(f)


def test_create_sets_defaults(run_cli, freeze_date):
    freeze_date(2026, 7, 16)
    out = run_cli("Big Corp", "Data Engineer")
    assert "Created record for Big Corp:" in out
    data = read_data()
    assert len(data) == 1
    (rec,) = data.values()
    assert rec["company"] == "Big Corp"
    assert rec["title"] == "Data Engineer"
    assert rec["applied"] == "2026-07-16"
    assert rec["status"] == "sent app"
    assert rec["status_changed"] == "2026-07-16"
    assert rec["interview"] is None
    assert rec["interview_tz"] is None
    assert rec["note"] is None
    assert rec["deleted"] is False
    assert rec["deleted_at"] is None
    assert rec["id"] == list(data.keys())[0]


def test_create_with_custom_status(run_cli):
    run_cli("Big Corp", "Data Engineer", "Recruiter reached out")
    (rec,) = read_data().values()
    assert rec["status"] == "Recruiter reached out"


def test_create_title_and_status_preserved_exactly_as_typed(run_cli):
    run_cli("Big Corp", "Sr. Data Engineer II", "Phone Screen: Tues")
    (rec,) = read_data().values()
    assert rec["title"] == "Sr. Data Engineer II"
    assert rec["status"] == "Phone Screen: Tues"


def test_create_duplicate_active_is_hard_error(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "Data Engineer II")
    assert "Big Corp already has a record:" in out
    assert "Use `status` to update it or `delete` to remove it first." in out
    data = read_data()
    assert len(data) == 1
    assert next(iter(data.values()))["title"] == "Data Engineer"


def test_create_duplicate_fuzzy_active_is_hard_error(run_cli):
    run_cli("foobar Consulting", "Data Engineer")
    out = run_cli("foobar", "Data Engineer II")
    assert "foobar Consulting already has a record:" in out
    assert len(read_data()) == 1


def test_create_after_soft_delete_prompts_and_accepts(run_cli, monkeypatch):
    prompts = []
    monkeypatch.setattr(job, "confirm", lambda prompt: prompts.append(prompt) or True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")
    run_cli("Big Corp", "Data Engineer II")
    assert ("already applied to Big Corp (declined). "
            "Do you want to proceed with a new record?") in prompts
    data = read_data()
    assert len(data) == 2
    active = [r for r in data.values() if not r["deleted"]]
    assert len(active) == 1
    assert active[0]["title"] == "Data Engineer II"


def test_create_after_soft_delete_declined_creates_nothing(run_cli, monkeypatch):
    answers = iter([True, False])  # accept the soft-delete, decline the reapply
    monkeypatch.setattr(job, "confirm", lambda prompt: next(answers))
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")
    out = run_cli("Big Corp", "Data Engineer II")
    assert "Cancelled." in out
    data = read_data()
    assert len(data) == 1
    assert next(iter(data.values()))["deleted"] is True
