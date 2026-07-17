import pytest
from datetime import date

import job


# ---- split_interview_tokens ----------------------------------------------

def test_split_missing_time_errors(capsys):
    result = job.interview.split_interview_tokens(["2026-07-13"])
    assert result == (None, None, None)
    assert "Missing interview time" in capsys.readouterr().out


def test_split_bare_time_only():
    result = job.interview.split_interview_tokens(["2026-07-13", "13:00"])
    assert result == ("2026-07-13", ["13:00"], None)


def test_split_time_plus_meridiem_two_tokens():
    result = job.interview.split_interview_tokens(["7/13", "9", "pm"])
    assert result == ("7/13", ["9", "pm"], None)


def test_split_time_plus_bare_tz_two_tokens():
    result = job.interview.split_interview_tokens(["2026-07-13", "13:00", "CT"])
    assert result == ("2026-07-13", ["13:00"], "CT")


def test_split_dangling_tz_keyword_errors(capsys):
    result = job.interview.split_interview_tokens(["2026-07-13", "13:00", "tz"])
    assert result == (None, None, None)
    assert "Missing timezone value after `tz`" in capsys.readouterr().out


def test_split_meridiem_plus_tz_three_tokens():
    result = job.interview.split_interview_tokens(["7/13", "9", "pm", "ET"])
    assert result == ("7/13", ["9", "pm"], "ET")


def test_split_time_plus_tz_keyword_three_tokens():
    result = job.interview.split_interview_tokens(["2026-07-13", "13:00", "tz", "CT"])
    assert result == ("2026-07-13", ["13:00"], "CT")


def test_split_meridiem_plus_tz_keyword_four_tokens():
    result = job.interview.split_interview_tokens(["7/13", "9", "pm", "tz", "ET"])
    assert result == ("7/13", ["9", "pm"], "ET")


def test_split_three_tokens_unrecognized_shape_errors(capsys):
    result = job.interview.split_interview_tokens(["2026-07-13", "9", "garbage", "CT"])
    assert result == (None, None, None)
    assert "Couldn't parse interview date/time" in capsys.readouterr().out


def test_split_four_tokens_not_matching_meridiem_tz_shape_errors(capsys):
    result = job.interview.split_interview_tokens(["7/13", "9", "am", "foo", "bar"])
    assert result == (None, None, None)
    assert "Couldn't parse interview date/time" in capsys.readouterr().out


# ---- parse_interview_date_token -------------------------------------------

def test_parse_date_iso():
    assert job.interview.parse_interview_date_token("2026-07-13") == date(2026, 7, 13)


def test_parse_date_iso_invalid_returns_none():
    assert job.interview.parse_interview_date_token("2026-13-01") is None


def test_parse_date_slash_full_year():
    assert job.interview.parse_interview_date_token("7/13/2026") == date(2026, 7, 13)


def test_parse_date_slash_two_digit_year():
    assert job.interview.parse_interview_date_token("7/13/26") == date(2026, 7, 13)


def test_parse_date_slash_no_year_future_stays_this_year(freeze_date):
    freeze_date(2026, 1, 1)
    assert job.interview.parse_interview_date_token("7/13") == date(2026, 7, 13)


def test_parse_date_slash_no_year_today_does_not_roll(freeze_date):
    today = freeze_date(2026, 7, 13)
    assert job.interview.parse_interview_date_token("7/13") == today


def test_parse_date_slash_no_year_past_rolls_to_next_year(freeze_date):
    freeze_date(2026, 12, 1)
    assert job.interview.parse_interview_date_token("1/1") == date(2027, 1, 1)


def test_parse_date_slash_invalid_day_returns_none():
    assert job.interview.parse_interview_date_token("2/30") is None


def test_parse_date_slash_explicit_year_invalid_day_returns_none():
    # Distinct from the no-year roll-forward path: this is the plain
    # "year was given explicitly" branch's own try/except.
    assert job.interview.parse_interview_date_token("2/30/2026") is None


def test_parse_date_slash_no_year_invalid_even_after_roll_returns_none(freeze_date):
    # Feb 29 2028 is valid (leap year); freezing "today" to just after it
    # forces a roll to 2029, which isn't leap -- so the *second* try/except
    # (post-roll) must also catch and return None.
    freeze_date(2028, 3, 1)
    assert job.interview.parse_interview_date_token("2/29") is None


def test_parse_date_unrecognized_format_returns_none():
    assert job.interview.parse_interview_date_token("not-a-date") is None
    assert job.interview.parse_interview_date_token("13-2026-07") is None


# ---- parse_interview_time_token -------------------------------------------

def test_parse_time_military_resolved():
    assert job.interview.parse_interview_time_token(["13:00"]) == ("resolved", 13, 0)


def test_parse_time_bare_hour_ambiguous():
    assert job.interview.parse_interview_time_token(["9"]) == ("ambiguous", 9, 0)


def test_parse_time_am_suffix_single_token():
    assert job.interview.parse_interview_time_token(["9am"]) == ("resolved", 9, 0)


def test_parse_time_pm_suffix_single_token():
    assert job.interview.parse_interview_time_token(["9pm"]) == ("resolved", 21, 0)


def test_parse_time_pm_suffix_noon_wraps_correctly():
    assert job.interview.parse_interview_time_token(["12pm"]) == ("resolved", 12, 0)


def test_parse_time_am_suffix_midnight_hour_wraps_correctly():
    assert job.interview.parse_interview_time_token(["12am"]) == ("resolved", 0, 0)


def test_parse_time_two_tokens_time_plus_meridiem():
    assert job.interview.parse_interview_time_token(["9:00", "PM"]) == ("resolved", 21, 0)


def test_parse_time_minute_over_59_is_none():
    assert job.interview.parse_interview_time_token(["13:75"]) is None


def test_parse_time_midnight_2400_resolves_to_0000():
    assert job.interview.parse_interview_time_token(["24:00"]) == ("resolved", 0, 0)


def test_parse_time_2400_with_nonzero_minute_is_none():
    assert job.interview.parse_interview_time_token(["24:30"]) is None


def test_parse_time_hour_zero_resolved():
    assert job.interview.parse_interview_time_token(["0:30"]) == ("resolved", 0, 30)


def test_parse_time_suffix_with_military_hour_is_none():
    assert job.interview.parse_interview_time_token(["13pm"]) is None


def test_parse_time_out_of_range_hour_is_none():
    assert job.interview.parse_interview_time_token(["25:00"]) is None


def test_parse_time_unparseable_text_is_none():
    assert job.interview.parse_interview_time_token(["whenever"]) is None


# ---- parse_interview_datetime (integration) -------------------------------

def test_parse_interview_datetime_full_flow_no_ambiguity():
    result = job.interview.parse_interview_datetime(["2026-07-13", "13:00", "CT"])
    aware_dt, tz_label = result
    assert tz_label == "CT"
    assert aware_dt.year == 2026 and aware_dt.month == 7 and aware_dt.day == 13
    assert aware_dt.hour == 13
    assert aware_dt.tzinfo.key == "America/Chicago"


def test_parse_interview_datetime_bad_shape_short_circuits(capsys):
    assert job.interview.parse_interview_datetime(["2026-07-13"]) is None
    assert "Missing interview time" in capsys.readouterr().out


def test_parse_interview_datetime_bad_date_errors(capsys):
    assert job.interview.parse_interview_datetime(["not-a-date", "13:00"]) is None
    assert "Couldn't parse interview date" in capsys.readouterr().out


def test_parse_interview_datetime_bad_time_errors(capsys):
    assert job.interview.parse_interview_datetime(["2026-07-13", "whenever"]) is None
    assert "Couldn't parse interview time" in capsys.readouterr().out


def test_parse_interview_datetime_ambiguous_resolved_pm(stub_meridiem):
    stub_meridiem("pm")
    aware_dt, tz_label = job.interview.parse_interview_datetime(["2026-07-13", "9"])
    assert aware_dt.hour == 21


def test_parse_interview_datetime_ambiguous_resolved_am(stub_meridiem):
    stub_meridiem("am")
    aware_dt, tz_label = job.interview.parse_interview_datetime(["2026-07-13", "9"])
    assert aware_dt.hour == 9


def test_parse_interview_datetime_ambiguous_declined_cancels(stub_meridiem, capsys):
    stub_meridiem(None)
    assert job.interview.parse_interview_datetime(["2026-07-13", "9"]) is None
    assert "Cancelled." in capsys.readouterr().out


def test_parse_interview_datetime_bad_tz_errors(capsys):
    assert job.interview.parse_interview_datetime(["2026-07-13", "13:00", "XX"]) is None
    assert "Unknown timezone 'XX'" in capsys.readouterr().out


def test_parse_interview_datetime_defaults_to_ct_when_tz_omitted():
    aware_dt, tz_label = job.interview.parse_interview_datetime(["2026-07-13", "13:00"])
    assert tz_label == "CT"
    assert aware_dt.tzinfo.key == "America/Chicago"


# ---- format_interview_dt / format_interview_display -----------------------

def test_format_interview_dt():
    aware_dt, tz_label = job.interview.parse_interview_datetime(["2026-07-13", "13:00", "CT"])
    assert job.interview.format_interview_dt(aware_dt, tz_label) == "2026-07-13 13:00 CT"


def test_format_interview_display_none_is_em_dash():
    rec = {"interview": None}
    assert job.interview.format_interview_display(rec) == "—"


def test_format_interview_display_uses_stored_tz_label_by_default():
    aware_dt, tz_label = job.interview.parse_interview_datetime(["2026-07-13", "13:00", "CT"])
    rec = {"interview": aware_dt.isoformat(), "interview_tz": tz_label}
    assert job.interview.format_interview_display(rec) == "2026-07-13 13:00 CT"


def test_format_interview_display_missing_tz_label_defaults_to_empty_string():
    aware_dt, _ = job.interview.parse_interview_datetime(["2026-07-13", "13:00", "CT"])
    rec = {"interview": aware_dt.isoformat()}
    assert job.interview.format_interview_display(rec) == "2026-07-13 13:00 "


def test_format_interview_display_converts_to_override_zone():
    aware_dt, tz_label = job.interview.parse_interview_datetime(["2026-07-13", "13:00", "CT"])
    rec = {"interview": aware_dt.isoformat(), "interview_tz": tz_label}
    display_tz = job.interview.resolve_tz_token("ET")
    result = job.interview.format_interview_display(rec, display_tz=display_tz)
    assert result == "2026-07-13 14:00 ET"
