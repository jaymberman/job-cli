import json

import job


def read_data():
    with open(job.storage.DATA_FILE) as f:
        return json.load(f)


# ---- strip_trailing_tz (direct unit tests) -----------------------------------

def test_strip_trailing_tz_too_short_unchanged():
    assert job._legacy.strip_trailing_tz(["status"]) == (["status"], None)


def test_strip_trailing_tz_no_tz_marker_unchanged():
    rest = ["status", "Interviewing"]
    assert job._legacy.strip_trailing_tz(rest) == (rest, None)


def test_strip_trailing_tz_bare_lookup_shape():
    assert job._legacy.strip_trailing_tz(["tz", "CT"]) == ([], "CT")


def test_strip_trailing_tz_all_shape():
    assert job._legacy.strip_trailing_tz(["--all", "tz", "CT"]) == (["--all"], "CT")


def test_strip_trailing_tz_delete_shape():
    assert job._legacy.strip_trailing_tz(["delete", "tz", "ET"]) == (["delete"], "ET")


def test_strip_trailing_tz_unrecognized_single_token_unchanged():
    rest = ["somefield", "tz", "CT"]
    assert job._legacy.strip_trailing_tz(rest) == (rest, None)


def test_strip_trailing_tz_delete_hard_shape():
    result = job._legacy.strip_trailing_tz(["delete", "--hard", "tz", "MT"])
    assert result == (["delete", "--hard"], "MT")


def test_strip_trailing_tz_status_shape():
    result = job._legacy.strip_trailing_tz(["status", "Interviewing", "tz", "PT"])
    assert result == (["status", "Interviewing"], "PT")


def test_strip_trailing_tz_note_shape():
    result = job._legacy.strip_trailing_tz(["note", "Some note", "tz", "PT"])
    assert result == (["note", "Some note"], "PT")


def test_strip_trailing_tz_delete_with_non_hard_third_token_unchanged():
    rest = ["delete", "--soft-ish", "tz", "CT"]
    assert job._legacy.strip_trailing_tz(rest) == (rest, None)


def test_strip_trailing_tz_too_many_preceding_tokens_unchanged():
    rest = ["a", "b", "c", "tz", "CT"]
    assert job._legacy.strip_trailing_tz(rest) == (rest, None)


# ---- dispatch_company branches (via run_cli) --------------------------------

def test_lookup_plain_company(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp")
    assert "Big Corp" in out
    assert "Data Engineer" in out


def test_lookup_unknown_company_says_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co")
    assert out.strip() == "no applications sent"


def test_lookup_with_all_flag_shows_history(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")
    out = run_cli("Big Corp", "--all")
    assert "Deleted" in out
    assert "Big Corp" in out


def test_status_missing_value_errors(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "status")
    assert "Missing new status value" in out


def test_interview_first_token_missing_datetime_errors(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "interview")
    assert "Missing interview date/time." in out


def test_too_many_arguments_errors_and_shows_usage(run_cli):
    out = run_cli("Big Corp", "a", "b", "c")
    assert "Too many arguments." in out
    assert "Usage:" in out


def test_dispatch_lookup_with_valid_trailing_tz(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "interview", "2026-07-13", "13:00", "CT")
    out = run_cli("Big Corp", "tz", "ET")
    assert "14:00 ET" in out


def test_dispatch_lookup_with_invalid_trailing_tz_errors_and_prints_nothing_else(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "tz", "XX")
    assert out.strip() == job.interview.unknown_tz_message("XX")


def test_dispatch_status_with_invalid_trailing_tz(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "status", "Interviewing", "tz", "XX")
    assert "Unknown timezone 'XX'" in out
    (rec,) = read_data().values()
    assert rec["status"] == "sent app"  # unchanged: the tz error short-circuited the update


# ---- main(): top-level routing -----------------------------------------------

def test_no_args_prints_usage(run_cli):
    out = run_cli()
    assert "Usage:" in out


def test_help_prints_usage(run_cli):
    out = run_cli("help")
    assert "Usage:" in out


def test_company_flag_forces_reserved_word_as_company(run_cli):
    out = run_cli("--company", "list", "Data Engineer")
    assert "Created record for list:" in out
    (rec,) = read_data().values()
    assert rec["company"] == "list"


def test_company_flag_missing_name_errors(run_cli):
    out = run_cli("--company")
    assert "Missing company name after --company." in out


def test_bare_sort_as_first_arg_errors(run_cli):
    out = run_cli("sort", "company")
    assert "`sort` must follow `list` or `search <keyword>`." in out


def test_bare_interview_as_first_arg_errors(run_cli):
    out = run_cli("interview", "2026-07-13", "13:00")
    assert "`interview` must follow a company name." in out


# ---- main(): list ------------------------------------------------------------

def test_list_help_via_main(run_cli):
    out = run_cli("list", "help")
    assert "Usage: job list" in out


def test_list_dangling_sort_errors(run_cli):
    out = run_cli("list", "sort")
    assert "Missing sort field." in out


def test_list_dangling_tz_errors(run_cli):
    out = run_cli("list", "tz")
    assert "Missing timezone value after `tz`" in out


def test_list_invalid_tz_errors(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("list", "tz", "XX")
    assert "Unknown timezone 'XX'" in out


# ---- main(): search ------------------------------------------------------------

def test_search_help_via_main(run_cli):
    out = run_cli("search", "help")
    assert "Usage: job search" in out


def test_search_dangling_sort_errors(run_cli):
    out = run_cli("search", "Data Engineer", "sort")
    assert "Missing sort field." in out


def test_search_dangling_tz_errors(run_cli):
    out = run_cli("search", "Data Engineer", "tz")
    assert "Missing timezone value after `tz`" in out


def test_search_unrecognized_trailing_args_errors(run_cli):
    out = run_cli("search", "Data Engineer", "bogus")
    assert "Too many arguments for search." in out


def test_search_invalid_tz_errors(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("search", "Data Engineer", "tz", "XX")
    assert "Unknown timezone 'XX'" in out


# ---- main(): interviews --------------------------------------------------------

def test_interviews_dangling_tz_errors(run_cli):
    out = run_cli("interviews", "tz")
    assert "Missing timezone value after `tz`" in out


def test_interviews_invalid_tz_errors(run_cli):
    out = run_cli("interviews", "tz", "XX")
    assert "Unknown timezone 'XX'" in out


# ---- main(): today --------------------------------------------------------------

def test_today_dangling_tz_errors(run_cli):
    out = run_cli("today", "tz")
    assert "Missing timezone value after `tz`" in out


def test_today_invalid_tz_errors(run_cli):
    out = run_cli("today", "tz", "XX")
    assert "Unknown timezone 'XX'" in out
