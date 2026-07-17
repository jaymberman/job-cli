import pytest

import job


@pytest.mark.parametrize("raw, expected", [
    ("foobar Consulting", "foobarconsulting"),
    (" foobar  consulting ", "foobarconsulting"),
    ("foobar-Consulting!", "foobarconsulting"),
    ("Big Corp", "bigcorp"),
    ("", ""),
])
def test_normalize(raw, expected):
    assert job.normalize(raw) == expected


def test_score_exact_match():
    assert job.score("foobarconsulting", "foobarconsulting") == 1.0


def test_score_both_empty_is_exact_match():
    assert job.score("", "") == 1.0


def test_score_containment_short_in_long():
    result = job.score("foobar", "foobarconsulting")
    containment = 0.75 + 0.25 * (len("foobar") / len("foobarconsulting"))
    assert result >= containment


def test_score_containment_long_contains_short_either_order():
    a = job.score("foobar", "foobarconsulting")
    b = job.score("foobarconsulting", "foobar")
    assert a == b


def test_score_one_side_empty_skips_containment_branch():
    # "" and "abc": a==b is False, and `a and b` is falsy since a=="",
    # so this must fall through to the plain difflib ratio, not containment.
    assert job.score("", "abc") == 0.0


def test_score_no_containment_uses_plain_ratio():
    import difflib
    a, b = "apple", "zebra"
    assert a not in b and b not in a
    assert job.score(a, b) == difflib.SequenceMatcher(None, a, b).ratio()
