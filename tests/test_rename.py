import json

import job


def read_data():
    with open(job.storage.DATA_FILE) as f:
        return json.load(f)


# ---- happy path: no collision ----------------------------------------------

def test_rename_happy_path_updates_company_and_prints_summary(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "--rename", "Vantage Systems")
    assert out.strip() == "Renamed Big Corp to Vantage Systems."
    (rec,) = read_data().values()
    assert rec["company"] == "Vantage Systems"


def test_rename_does_not_touch_status_changed(run_cli, freeze_date):
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")
    before = read_data()
    (rec_before,) = before.values()
    assert rec_before["status_changed"] == "2026-01-01"

    freeze_date(2026, 6, 1)
    run_cli("Big Corp", "--rename", "Vantage Systems")
    (rec_after,) = read_data().values()
    assert rec_after["status_changed"] == "2026-01-01"


def test_rename_needs_no_confirmation_when_no_collision(run_cli, monkeypatch):
    run_cli("Big Corp", "Data Engineer")

    def explode(prompt):
        raise AssertionError("a no-collision rename should never call confirm()")
    monkeypatch.setattr(job._legacy, "confirm", explode)
    out = run_cli("Big Corp", "--rename", "Vantage Systems")
    assert "Renamed Big Corp to Vantage Systems." in out


def test_rename_is_case_insensitive_flag(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "--RENAME", "Vantage Systems")
    assert "Renamed Big Corp to Vantage Systems." in out


def test_rename_fuzzy_resolves_old_name(run_cli):
    run_cli("foobar Consulting", "Data Engineer")
    out = run_cli("foobar", "--rename", "Vantage Systems")
    assert "Renamed foobar Consulting to Vantage Systems." in out


def test_rename_preserves_note_favorite_and_interview_fields(run_cli):
    run_cli("Big Corp", "Data Engineer")
    data = job.storage.load_data()
    (key,) = data.keys()
    data[key]["note"] = "Referred by a friend"
    data[key]["is_favorite"] = True
    data[key]["interview"] = "2026-07-13T13:00:00-05:00"
    data[key]["interview_tz"] = "CT"
    job.storage.save_data(data)

    run_cli("Big Corp", "--rename", "Vantage Systems")

    (rec,) = read_data().values()
    assert rec["company"] == "Vantage Systems"
    assert rec["note"] == "Referred by a friend"
    assert rec["is_favorite"] is True
    assert rec["interview"] == "2026-07-13T13:00:00-05:00"
    assert rec["interview_tz"] == "CT"


# ---- cascade to soft-deleted history ----------------------------------------

def _setup_active_plus_two_soft_deleted(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")           # 1st soft-deleted record
    run_cli("Big Corp", "Data Engineer II")  # reapply (declined-dup prompt)
    run_cli("Big Corp", "delete")           # 2nd soft-deleted record
    run_cli("Big Corp", "Data Engineer III")  # reapply again, left active


def test_rename_cascades_to_soft_deleted_history(run_cli, stub_confirm):
    _setup_active_plus_two_soft_deleted(run_cli, stub_confirm)
    out = run_cli("Big Corp", "--rename", "Vantage Systems")
    assert out.strip() == "Renamed Big Corp to Vantage Systems (2 soft-deleted record(s) also updated)."

    data = read_data()
    assert len(data) == 3
    assert all(rec["company"] == "Vantage Systems" for rec in data.values())


def test_rename_cascade_all_lookup_shows_merged_history_under_new_name(run_cli, stub_confirm):
    _setup_active_plus_two_soft_deleted(run_cli, stub_confirm)
    run_cli("Big Corp", "--rename", "Vantage Systems")
    out = run_cli("Vantage Systems", "--all")
    lines = [l for l in out.splitlines() if "Vantage Systems" in l]
    assert len(lines) == 3


# ---- active-name collision ---------------------------------------------------

def test_rename_active_collision_is_hard_error(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Zenoport", "Data Engineer")
    out = run_cli("Big Corp", "--rename", "Zenoport")
    assert "Zenoport already has a record:" in out
    assert "Use `status` to update it or `delete` to remove it first." in out

    data = read_data()
    companies = sorted(rec["company"] for rec in data.values())
    assert companies == ["Big Corp", "Zenoport"]


def test_rename_active_collision_does_not_mutate_anything(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Zenoport", "Data Engineer")
    before = read_data()
    run_cli("Big Corp", "--rename", "Zenoport")
    assert read_data() == before


# ---- soft-deleted-only collision: confirm to merge ---------------------------

def test_rename_declined_only_collision_prompts_and_merges_on_confirm(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Vantage Systems", "Data Engineer")
    run_cli("Vantage Systems", "delete")  # now soft-deleted-only, no active

    out = run_cli("Big Corp", "--rename", "Vantage Systems")
    assert "Renamed Big Corp to Vantage Systems." in out

    data = read_data()
    assert len(data) == 2
    assert all(rec["company"] == "Vantage Systems" for rec in data.values())


def test_rename_declined_only_collision_prompt_wording(run_cli, stub_confirm, monkeypatch):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Vantage Systems", "Data Engineer")
    run_cli("Vantage Systems", "delete")

    seen = {}
    def capture(prompt):
        seen["prompt"] = prompt
        return True
    monkeypatch.setattr(job._legacy, "confirm", capture)
    run_cli("Big Corp", "--rename", "Vantage Systems")
    assert seen["prompt"] == "already applied to Vantage Systems (declined). Do you want to proceed with the rename?"


def test_rename_declined_only_collision_declined_cancels(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Vantage Systems", "Data Engineer")
    run_cli("Vantage Systems", "delete")
    before = read_data()

    stub_confirm(False)
    out = run_cli("Big Corp", "--rename", "Vantage Systems")
    assert out.strip() == "Cancelled."
    assert read_data() == before


# ---- self-rename: fixing casing/spacing of the same company -----------------

def test_self_rename_fixes_casing_with_no_collision_error(run_cli):
    run_cli("bigcorp", "Data Engineer")
    out = run_cli("bigcorp", "--rename", "Big Corp")
    assert out.strip() == "Renamed bigcorp to Big Corp."
    (rec,) = read_data().values()
    assert rec["company"] == "Big Corp"


def test_self_rename_needs_no_confirmation(run_cli, monkeypatch):
    run_cli("bigcorp", "Data Engineer")

    def explode(prompt):
        raise AssertionError("a self-rename should never call confirm()")
    monkeypatch.setattr(job._legacy, "confirm", explode)
    run_cli("bigcorp", "--rename", "Big Corp")


# ---- no active record --------------------------------------------------------

def test_rename_unknown_company_says_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co", "--rename", "New Name")
    assert out.strip() == "no applications sent"
    assert job.storage.load_data() == {}


def test_rename_soft_deleted_only_old_company_says_no_applications_sent(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")  # now only soft-deleted history exists
    before = read_data()

    out = run_cli("Big Corp", "--rename", "Vantage Systems")
    assert out.strip() == "no applications sent"
    assert read_data() == before


# ---- argument grammar --------------------------------------------------------

def test_rename_missing_new_name_prints_usage(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "--rename")
    assert "Missing new company name. Usage: job <company> --rename <new_name>" in out
    (rec,) = read_data().values()
    assert rec["company"] == "Big Corp"


def test_rename_extra_argument_falls_through_to_too_many_arguments(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "--rename", "Vantage Systems", "extra")
    assert "Too many arguments." in out
    (rec,) = read_data().values()
    assert rec["company"] == "Big Corp"
