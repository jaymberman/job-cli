import job


# ---- parse_sort_field_order --------------------------------------------------

def test_parse_sort_field_order_defaults_to_asc():
    key, reverse = job.parse_sort_field_order("company", None)
    assert key == "company"
    assert reverse is False


def test_parse_sort_field_order_desc():
    key, reverse = job.parse_sort_field_order("status-changed", "desc")
    assert key == "status_changed"
    assert reverse is True


def test_parse_sort_field_order_case_insensitive():
    key, reverse = job.parse_sort_field_order("COMPANY", "ASC")
    assert key == "company"
    assert reverse is False


def test_parse_sort_field_order_unknown_field(capsys):
    key, reverse = job.parse_sort_field_order("bogus", None)
    assert (key, reverse) == (None, None)
    assert "Unknown sort field 'bogus'" in capsys.readouterr().out


def test_parse_sort_field_order_unknown_order(capsys):
    key, reverse = job.parse_sort_field_order("company", "sideways")
    assert (key, reverse) == (None, None)
    assert "Unknown sort order 'sideways'" in capsys.readouterr().out


# ---- scan_display_flags -------------------------------------------------------

def test_scan_display_flags_empty():
    assert job.scan_display_flags([]) == (False, None, None, None, [])


def test_scan_display_flags_all():
    assert job.scan_display_flags(["--all"]) == (True, None, None, None, [])


def test_scan_display_flags_tz():
    assert job.scan_display_flags(["tz", "PT"]) == (False, "PT", None, None, [])


def test_scan_display_flags_dangling_tz_is_leftover():
    assert job.scan_display_flags(["tz"]) == (False, None, None, None, ["tz"])


def test_scan_display_flags_duplicate_tz_last_wins():
    result = job.scan_display_flags(["tz", "CT", "tz", "ET"])
    assert result == (False, "ET", None, None, [])


def test_scan_display_flags_sort_field_only():
    result = job.scan_display_flags(["sort", "company"], allow_sort=True)
    assert result == (False, None, "company", None, [])


def test_scan_display_flags_sort_field_and_order():
    result = job.scan_display_flags(["sort", "company", "desc"], allow_sort=True)
    assert result == (False, None, "company", "desc", [])


def test_scan_display_flags_sort_order_that_is_actually_a_flag_starter_is_not_consumed():
    result = job.scan_display_flags(["sort", "company", "--all"], allow_sort=True)
    assert result == (True, None, "company", None, [])


def test_scan_display_flags_dangling_sort_is_leftover():
    assert job.scan_display_flags(["sort"], allow_sort=True) == (False, None, None, None, ["sort"])


def test_scan_display_flags_sort_not_allowed_becomes_leftover():
    result = job.scan_display_flags(["sort", "company"], allow_sort=False)
    assert result == (False, None, None, None, ["sort", "company"])


def test_scan_display_flags_unrecognized_token_is_leftover():
    assert job.scan_display_flags(["bogus"]) == (False, None, None, None, ["bogus"])


def test_scan_display_flags_mixed_order():
    tokens = ["tz", "ET", "--all", "sort", "status", "desc"]
    result = job.scan_display_flags(tokens, allow_sort=True)
    assert result == (True, "ET", "status", "desc", [])


# ---- cmd_list / job list -------------------------------------------------------

def test_list_default_sort_is_company_ascending(run_cli):
    run_cli("Zeta Co", "Data Engineer")
    run_cli("Alpha Co", "Data Engineer")
    out = run_cli("list")
    assert out.index("Alpha Co") < out.index("Zeta Co")


def test_list_empty_says_no_applications_tracked_yet(run_cli):
    out = run_cli("list")
    assert out.strip() == "no applications tracked yet"


def test_list_sort_applied_desc(run_cli, freeze_date):
    freeze_date(2026, 1, 1)
    run_cli("Old Co", "Data Engineer")
    freeze_date(2026, 6, 1)
    run_cli("New Co", "Data Engineer")
    out = run_cli("list", "sort", "applied", "desc")
    assert out.index("New Co") < out.index("Old Co")


def test_list_all_includes_deleted_with_deleted_column(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")
    out_default = run_cli("list")
    assert out_default.strip() == "no applications tracked yet"
    out_all = run_cli("list", "--all")
    assert "Big Corp" in out_all
    assert "Deleted" in out_all


def test_list_unknown_sort_field_errors(run_cli):
    out = run_cli("list", "sort", "bogus")
    assert "Unknown sort field 'bogus'" in out


def test_list_unknown_sort_order_errors(run_cli):
    out = run_cli("list", "sort", "company", "sideways")
    assert "Unknown sort order 'sideways'" in out


# ---- cmd_search / job search ----------------------------------------------

def test_search_company_field_delegates_to_lookup_resolution(run_cli):
    run_cli("Aretum Consulting", "Data Engineer")
    out = run_cli("search", "aretum")
    assert "Aretum Consulting" in out


def test_search_title_field_wins_and_applies_auto_threshold(run_cli):
    run_cli("Big Corp", "Data Engineer")
    run_cli("Small Co", "Marketing Manager")
    out = run_cli("search", "Data Engineer")
    assert "Big Corp" in out
    assert "Small Co" not in out


def test_search_status_field_wins_and_applies_auto_threshold(run_cli):
    run_cli("Big Corp", "Data Engineer", "phone screen scheduled")
    run_cli("Small Co", "Marketing Manager", "sent app")
    out = run_cli("search", "phone screen scheduled")
    assert "Big Corp" in out
    assert "Small Co" not in out


def test_search_below_auto_threshold_says_no_matching_applications_found(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("search", "Completely Unrelated Keyword Text")
    assert out.strip() == "no matching applications found"


def test_search_empty_pool_says_no_applications_tracked_yet(run_cli):
    out = run_cli("search", "anything")
    assert out.strip() == "no applications tracked yet"


def test_search_default_sort_is_status_changed_descending(run_cli, freeze_date):
    freeze_date(2026, 1, 1)
    run_cli("Old Co", "Data Engineer")
    freeze_date(2026, 6, 1)
    run_cli("New Co", "Data Engineer")
    out = run_cli("search", "Data Engineer")
    assert out.index("New Co") < out.index("Old Co")


def test_search_sort_override(run_cli):
    run_cli("Zeta Co", "Data Engineer")
    run_cli("Alpha Co", "Data Engineer")
    out = run_cli("search", "Data Engineer", "sort", "company", "asc")
    assert out.index("Alpha Co") < out.index("Zeta Co")


def test_search_all_flag_includes_deleted(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")
    out_default = run_cli("search", "Data Engineer")
    # No active records at all -> the pool-emptiness check fires before any
    # field scoring happens, so this is "tracked yet", not "no matching".
    assert out_default.strip() == "no applications tracked yet"
    out_all = run_cli("search", "Data Engineer", "--all")
    assert "Big Corp" in out_all
    assert "Deleted" in out_all


def test_search_missing_keyword_errors(run_cli):
    out = run_cli("search")
    assert "Missing search keyword" in out


def test_search_company_field_wins_but_resolution_is_declined(run_cli, answer_input):
    run_cli("Davita", "Marketing Manager")
    answer_input("n")
    out = run_cli("search", "davidoff")
    assert out.strip() == "no matching applications found"


def test_search_company_field_with_all_sorts_history_by_applied_desc(run_cli, stub_confirm, freeze_date):
    stub_confirm(True)
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")
    freeze_date(2026, 6, 1)
    run_cli("Big Corp", "Data Engineer II")
    out = run_cli("search", "Big Corp", "--all")
    assert out.index("2026-06-01") < out.index("2026-01-01")


def test_list_unrecognized_arguments_errors(run_cli):
    out = run_cli("list", "bogus")
    assert "Unrecognized `job list` arguments" in out


def test_search_sort_unknown_field_does_not_call_search(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("search", "Data Engineer", "sort", "bogus")
    assert "Unknown sort field 'bogus'" in out
    assert "Big Corp" not in out
