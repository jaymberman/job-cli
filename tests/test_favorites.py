import json

import job


def read_data():
    with open(job.storage.DATA_FILE) as f:
        return json.load(f)


# ---- --favorite / --remove-favorite: happy path --------------------------------

def test_favorite_sets_flag_and_prints_message(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "--favorite")
    assert out.strip() == "Marked Big Corp as a favorite."
    (rec,) = read_data().values()
    assert rec["is_favorite"] is True


def test_remove_favorite_clears_flag_and_prints_message(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("Big Corp", "--remove-favorite")
    assert out.strip() == "Removed Big Corp from favorites."
    (rec,) = read_data().values()
    assert rec["is_favorite"] is False


def test_favorite_is_case_insensitive(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "--FAVORITE")
    assert out.strip() == "Marked Big Corp as a favorite."


def test_remove_favorite_is_case_insensitive(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("Big Corp", "--Remove-Favorite")
    assert out.strip() == "Removed Big Corp from favorites."


def test_favorite_fuzzy_match_resolves(run_cli):
    run_cli("foobar Consulting", "Data Engineer")
    out = run_cli("foobar", "--favorite")
    assert "Marked foobar Consulting as a favorite." in out


def test_favorite_defaults_to_false_on_create(run_cli):
    run_cli("Big Corp", "Data Engineer")
    (rec,) = read_data().values()
    assert rec["is_favorite"] is False


# ---- idempotency: no special no-op messaging ------------------------------------

def test_favoriting_an_already_favorited_record_reprints_same_message(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("Big Corp", "--favorite")
    assert out.strip() == "Marked Big Corp as a favorite."
    (rec,) = read_data().values()
    assert rec["is_favorite"] is True


def test_removing_favorite_on_non_favorite_reprints_same_message(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "--remove-favorite")
    assert out.strip() == "Removed Big Corp from favorites."
    (rec,) = read_data().values()
    assert rec["is_favorite"] is False


# ---- no confirmation prompt -----------------------------------------------------

def test_favorite_needs_no_confirmation(run_cli, monkeypatch):
    run_cli("Big Corp", "Data Engineer")

    def explode(prompt):
        raise AssertionError("--favorite should never call confirm()")
    monkeypatch.setattr(job.company, "confirm", explode)
    out = run_cli("Big Corp", "--favorite")
    assert "Marked Big Corp as a favorite." in out


def test_remove_favorite_needs_no_confirmation(run_cli, monkeypatch):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")

    def explode(prompt):
        raise AssertionError("--remove-favorite should never call confirm()")
    monkeypatch.setattr(job.company, "confirm", explode)
    out = run_cli("Big Corp", "--remove-favorite")
    assert "Removed Big Corp from favorites." in out


# ---- no active record ------------------------------------------------------------

def test_favorite_no_active_record_says_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co", "--favorite")
    assert out.strip() == "no applications sent"


def test_remove_favorite_no_active_record_says_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co", "--remove-favorite")
    assert out.strip() == "no applications sent"


# ---- regression: must never be misread as a create ------------------------------

def test_favorite_on_unknown_company_never_creates_a_record(run_cli):
    out = run_cli("Nonexistent Co", "--favorite")
    assert out.strip() == "no applications sent"
    assert job.storage.load_data() == {}


def test_remove_favorite_on_unknown_company_never_creates_a_record(run_cli):
    out = run_cli("Nonexistent Co", "--remove-favorite")
    assert out.strip() == "no applications sent"
    assert job.storage.load_data() == {}


def test_favorite_extra_argument_errors_and_does_not_create(run_cli):
    out = run_cli("New Co", "--favorite", "extra")
    assert "`--favorite` doesn't take an extra argument." in out
    assert job.storage.load_data() == {}


def test_remove_favorite_extra_argument_errors_and_does_not_create(run_cli):
    out = run_cli("New Co", "--remove-favorite", "extra")
    assert "`--remove-favorite` doesn't take an extra argument." in out
    assert job.storage.load_data() == {}


# ---- favorite status shows as a plain ♥ marker in every table view --------------

def test_favorite_shown_in_lookup(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("Big Corp")
    assert "Big Corp ♥" in out
    assert "is_favorite" not in out.lower()


def test_favorite_not_shown_for_unfavorited_record_in_lookup(run_cli):
    run_cli("Small Co", "Marketing Manager")
    out = run_cli("Small Co")
    assert "♥" not in out


def test_favorite_shown_as_table_marker_in_list(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("list")
    assert "Big Corp ♥" in out
    assert "Favorite" not in out.splitlines()[0]


def test_favorite_shown_in_search_results(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("search", "Big Corp")
    assert "Big Corp ♥" in out


# ---- job favorites ----------------------------------------------------------------

def test_favorites_shows_only_favorited_active_records(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Small Co", "Marketing Manager")
    run_cli("Big Corp", "--favorite")
    out = run_cli("favorites")
    assert "Big Corp" in out
    assert "Small Co" not in out


def test_favorites_excludes_unfavorited_after_removal(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    run_cli("Big Corp", "--remove-favorite")
    out = run_cli("favorites")
    assert out.strip() == "no favorites yet"


def test_favorites_empty_message(run_cli):
    out = run_cli("favorites")
    assert out.strip() == "no favorites yet"


def test_favorites_sorted_by_company_name_ascending(run_cli):
    run_cli("Zeta Co", "Data Engineer")
    run_cli("Alpha Co", "Data Engineer")
    run_cli("Zeta Co", "--favorite")
    run_cli("Alpha Co", "--favorite")
    out = run_cli("favorites")
    lines = out.splitlines()
    data_lines = lines[2:]
    assert data_lines[0].startswith("Alpha Co")
    assert data_lines[1].startswith("Zeta Co")


def test_favorites_table_has_no_favorite_column(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("favorites")
    header = out.splitlines()[0]
    assert "Favorite" not in header
    assert header.split() == ["Company", "Title", "Applied", "Interview", "Status", "Changed", "Status", "Note"]


def test_favorites_no_deleted_column_ever(run_cli):
    # No --all support: a soft-deleted record can never be favorited, since
    # deletion clears the flag, so there's nothing extra for --all to surface.
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("favorites", "--all")
    assert "Unrecognized `job favorites` arguments." in out


def test_favorites_help(run_cli):
    out = run_cli("favorites", "help")
    assert "Usage: job favorites" in out


def test_favorites_unrecognized_extra_arguments_error(run_cli):
    out = run_cli("favorites", "bogus")
    assert "Unrecognized `job favorites` arguments." in out


def test_favorites_ignores_legacy_records_missing_is_favorite_field(run_cli):
    # Records predating this feature have no is_favorite key at all;
    # cmd_favorites must treat that as not-favorited via .get(..., False),
    # not crash or misclassify it as favorited.
    data = job.storage.load_data()
    data["11111111"] = {
        "id": "11111111",
        "company": "Legacy Co",
        "title": "Data Engineer",
        "applied": "2026-01-01",
        "interview": None,
        "interview_tz": None,
        "status": "sent app",
        "status_changed": "2026-01-01",
        "note": None,
        "deleted": False,
        "deleted_at": None,
    }
    job.storage.save_data(data)
    out = run_cli("favorites")
    assert out.strip() == "no favorites yet"


# ---- deletion clears favorite status ---------------------------------------------

def test_soft_delete_clears_favorite_status(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    run_cli("Big Corp", "delete")
    (rec,) = read_data().values()
    assert rec["is_favorite"] is False


def test_soft_delete_message_unchanged_when_record_was_favorited(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    out = run_cli("Big Corp", "delete")
    assert ("Soft-deleted record for Big Corp. It's hidden from result sets "
            "but can be viewed with `job Big Corp --all`.") in out
    assert "favorite" not in out.lower()


def test_favorited_record_drops_out_of_favorites_after_soft_delete(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    run_cli("Big Corp", "delete")
    out = run_cli("favorites")
    assert out.strip() == "no favorites yet"


def test_hard_delete_removes_favorited_record_entirely(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "--favorite")
    run_cli("Big Corp", "delete", "--hard")
    assert read_data() == {}
