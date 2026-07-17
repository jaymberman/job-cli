import pytest

import job


def test_resolve_tz_token_none_returns_none_pair():
    # Resolving a missing token to the user's configured default is
    # resolve_or_prompt_default_tz's job, not resolve_tz_token's -- see
    # test_config.py.
    assert job._legacy.resolve_tz_token(None) == (None, None)


@pytest.mark.parametrize("token, expected", [
    ("ET", ("America/New_York", "ET")),
    ("et", ("America/New_York", "ET")),
    ("EST", ("America/New_York", "ET")),
    ("EDT", ("America/New_York", "ET")),
    ("EASTERN", ("America/New_York", "ET")),
    ("CDT", ("America/Chicago", "CT")),
    ("MST", ("America/Denver", "MT")),
    ("PACIFIC", ("America/Los_Angeles", "PT")),
    ("UTC", ("UTC", "UTC")),
    ("GMT", ("UTC", "UTC")),
])
def test_resolve_tz_token_aliases(token, expected):
    assert job._legacy.resolve_tz_token(token) == expected


def test_resolve_tz_token_unknown_returns_none_pair():
    assert job._legacy.resolve_tz_token("XX") == (None, None)


def test_unknown_tz_message_names_the_bad_token_and_supported_list():
    msg = job._legacy.unknown_tz_message("XX")
    assert "XX" in msg
    assert "CT" in msg and "ET" in msg and "MT" in msg and "PT" in msg and "UTC" in msg


def test_resolve_display_tz_none_means_no_override():
    display_tz, ok = job._legacy.resolve_display_tz(None)
    assert display_tz is None
    assert ok is True


def test_resolve_display_tz_valid_token():
    display_tz, ok = job._legacy.resolve_display_tz("PT")
    assert display_tz == ("America/Los_Angeles", "PT")
    assert ok is True


def test_resolve_display_tz_unknown_token_prints_error_and_fails(capsys):
    display_tz, ok = job._legacy.resolve_display_tz("XX")
    assert display_tz is None
    assert ok is False
    out = capsys.readouterr().out
    assert "Unknown timezone 'XX'" in out
