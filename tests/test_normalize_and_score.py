import pytest

import job


@pytest.mark.parametrize("raw, expected", [
    ("Aretum Consulting", "aretumconsulting"),
    (" aretum  consulting ", "aretumconsulting"),
    ("Aretum-Consulting!", "aretumconsulting"),
    ("Big Corp", "bigcorp"),
    ("", ""),
])
def test_normalize(raw, expected):
    assert job.normalize(raw) == expected


def test_score_exact_match():
    assert job.score("aretumconsulting", "aretumconsulting") == 1.0


def test_score_both_empty_is_exact_match():
    assert job.score("", "") == 1.0


def test_score_containment_short_in_long():
    result = job.score("aretum", "aretumconsulting")
    containment = 0.75 + 0.25 * (len("aretum") / len("aretumconsulting"))
    assert result >= containment


def test_score_containment_long_contains_short_either_order():
    a = job.score("aretum", "aretumconsulting")
    b = job.score("aretumconsulting", "aretum")
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
