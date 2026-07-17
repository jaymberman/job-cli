import json

import job


def read_data():
    with open(job.storage.DATA_FILE) as f:
        return json.load(f)


# ---- note set/edit -----------------------------------------------------------

def test_note_set_happy_path(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "note", "Referred by a friend on the team")
    assert "Updated Big Corp's note:" in out
    assert "Note: Referred by a friend on the team" in out
    (rec,) = read_data().values()
    assert rec["note"] == "Referred by a friend on the team"


def test_note_edit_overwrites_previous_value(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "First note")
    run_cli("Big Corp", "note", "Second note")
    (rec,) = read_data().values()
    assert rec["note"] == "Second note"


def test_note_is_freeform_text_no_validation(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "some totally arbitrary freeform text!! 123 @#$")
    (rec,) = read_data().values()
    assert rec["note"] == "some totally arbitrary freeform text!! 123 @#$"


def test_note_no_active_record_says_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co", "note", "Some note")
    assert out.strip() == "no applications sent"


def test_note_fuzzy_match_resolves(run_cli):
    run_cli("foobar Consulting", "Data Engineer")
    out = run_cli("foobar", "note", "Some note")
    assert "Updated foobar Consulting's note:" in out


def test_note_does_not_touch_status_changed(run_cli, freeze_date):
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")
    freeze_date(2026, 1, 10)
    run_cli("Big Corp", "note", "Some note")
    (rec,) = read_data().values()
    assert rec["status_changed"] == "2026-01-01"
    assert rec["applied"] == "2026-01-01"


def test_note_needs_no_confirmation(run_cli, monkeypatch):
    run_cli("Big Corp", "Data Engineer")

    def explode(prompt):
        raise AssertionError("note should never call confirm()")
    monkeypatch.setattr(job._legacy, "confirm", explode)
    out = run_cli("Big Corp", "note", "Some note")
    assert "Updated Big Corp's note:" in out


def test_note_missing_value_errors(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "note")
    assert "Missing note value." in out


def test_note_as_bare_second_arg_blocks_create_instead_of_using_it_as_title(run_cli):
    out = run_cli("New Co", "note")
    assert "Missing note value." in out
    assert job.storage.load_data() == {}


# ---- note clear ---------------------------------------------------------------

def test_note_clear_clears_field(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "Some note")
    out = run_cli("Big Corp", "note", "clear")
    assert "Cleared Big Corp's note." in out
    (rec,) = read_data().values()
    assert rec["note"] is None


def test_note_clear_does_not_touch_status_changed(run_cli, freeze_date):
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "Some note")
    freeze_date(2026, 1, 10)
    run_cli("Big Corp", "note", "clear")
    (rec,) = read_data().values()
    assert rec["status_changed"] == "2026-01-01"


def test_note_clear_when_nothing_set_is_friendly_noop(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "note", "clear")
    assert "Big Corp has no note set." in out


def test_note_clear_no_active_record_says_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co", "note", "clear")
    assert out.strip() == "no applications sent"


def test_note_clear_is_case_insensitive(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "Some note")
    out = run_cli("Big Corp", "note", "CLEAR")
    assert "Cleared Big Corp's note." in out


# ---- note display: creation default, vertical view, table --------------------

def test_note_defaults_to_null_on_create(run_cli):
    run_cli("Big Corp", "Data Engineer")
    (rec,) = read_data().values()
    assert rec["note"] is None


def test_note_renders_em_dash_when_unset_in_lookup(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp")
    assert "Note" in out
    assert "—" in out


def test_note_shown_in_lookup_after_set(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "Some note")
    out = run_cli("Big Corp")
    assert "Some note" in out


def test_note_shown_as_table_column_in_list(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "Some note")
    out = run_cli("list")
    lines = out.splitlines()
    assert "Note" in lines[0]
    assert "Some note" in lines[2]


def test_note_shown_in_search_results(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "Some note")
    out = run_cli("search", "Big Corp")
    assert "Some note" in out


def test_note_not_settable_at_creation_extra_arg_is_too_many_arguments(run_cli):
    out = run_cli("Big Corp", "Data Engineer", "sent app", "Some note")
    assert "Too many arguments." in out
    assert job.storage.load_data() == {}


# ---- note excluded from search matching ---------------------------------------

def test_note_content_is_not_searchable(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "note", "unique-note-keyword-xyz")
    out = run_cli("search", "unique-note-keyword-xyz")
    assert "no matching applications found" in out


# ---- note + trailing tz override ----------------------------------------------

def test_note_set_with_trailing_tz_converts_interview_display(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "interview", "2026-07-13", "13:00", "CT")
    out = run_cli("Big Corp", "note", "Some note", "tz", "ET")
    assert "14:00 ET" in out
    (rec,) = read_data().values()
    assert rec["note"] == "Some note"


def test_note_set_with_invalid_trailing_tz_errors_and_saves_nothing(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "note", "Some note", "tz", "XX")
    assert "Unknown timezone 'XX'" in out
    (rec,) = read_data().values()
    assert rec["note"] is None
