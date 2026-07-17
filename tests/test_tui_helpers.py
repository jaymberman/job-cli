import job


# ---- scroll_stops -------------------------------------------------------

def test_scroll_stops_includes_column_boundaries_within_range():
    stops = job._legacy.scroll_stops([0, 10, 25, 40], total_width=60, term_width=20)
    assert stops == [0, 10, 25, 40]


def test_scroll_stops_clamps_columns_beyond_max_offset():
    stops = job._legacy.scroll_stops([0, 50, 55], total_width=60, term_width=20)
    assert stops == [0, 40]


def test_scroll_stops_single_zero_stop_when_table_fits():
    stops = job._legacy.scroll_stops([0, 5], total_width=20, term_width=30)
    assert stops == [0]


# ---- next_stop ------------------------------------------------------------

def test_next_stop_forward_moves_to_next_boundary():
    assert job._legacy.next_stop([0, 10, 25, 40], current=10, direction=1) == 25


def test_next_stop_forward_clamps_at_last_stop():
    assert job._legacy.next_stop([0, 10, 25, 40], current=40, direction=1) == 40


def test_next_stop_backward_moves_to_previous_boundary():
    assert job._legacy.next_stop([0, 10, 25, 40], current=25, direction=-1) == 10


def test_next_stop_backward_clamps_at_first_stop():
    assert job._legacy.next_stop([0, 10, 25, 40], current=0, direction=-1) == 0


# ---- build_scrollbar --------------------------------------------------------

def test_build_scrollbar_length_matches_term_width():
    assert len(job._legacy.build_scrollbar(0, 100, 20)) == 20


def test_build_scrollbar_has_end_caps():
    bar = job._legacy.build_scrollbar(0, 100, 20)
    assert bar[0] == "◄"
    assert bar[-1] == "►"


def test_build_scrollbar_thumb_moves_right_as_offset_increases():
    bar_start = job._legacy.build_scrollbar(0, 100, 20)
    bar_end = job._legacy.build_scrollbar(80, 100, 20)
    assert bar_end.index("█") > bar_start.index("█")


def test_build_scrollbar_zero_max_offset_still_renders_a_thumb():
    bar = job._legacy.build_scrollbar(0, 20, 20)
    assert "█" in bar


def test_build_scrollbar_term_width_one_skips_end_caps():
    bar = job._legacy.build_scrollbar(0, 100, 1)
    assert bar == "█"


# ---- read_key ---------------------------------------------------------------

def test_read_key_regular_character(monkeypatch):
    monkeypatch.setattr(job._legacy.os, "read", lambda fd, n: b"q")
    assert job._legacy.read_key(3) == b"q"


def test_read_key_lone_escape_with_no_followup(monkeypatch):
    monkeypatch.setattr(job._legacy.os, "read", lambda fd, n: b"\x1b")
    monkeypatch.setattr(job._legacy.select, "select", lambda *a, **kw: ([], [], []))
    assert job._legacy.read_key(3) == b"\x1b"


def test_read_key_arrow_sequence(monkeypatch):
    reads = iter([b"\x1b", b"[", b"C"])
    monkeypatch.setattr(job._legacy.os, "read", lambda fd, n: next(reads))
    monkeypatch.setattr(job._legacy.select, "select", lambda *a, **kw: ([3], [], []))
    assert job._legacy.read_key(3) == b"\x1b[C"


def test_read_key_escape_followed_by_non_bracket_is_lone_escape(monkeypatch):
    reads = iter([b"\x1b", b"O"])
    monkeypatch.setattr(job._legacy.os, "read", lambda fd, n: next(reads))
    monkeypatch.setattr(job._legacy.select, "select", lambda *a, **kw: ([3], [], []))
    assert job._legacy.read_key(3) == b"\x1b"
