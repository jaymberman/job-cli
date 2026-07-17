from datetime import datetime
from zoneinfo import ZoneInfo

import job


def make_rec(company, title="Data Engineer", applied="2026-01-01", status="sent app",
             status_changed="2026-01-01", interview=None, interview_tz=None,
             note=None, deleted=False, deleted_at=None, id_="11111111"):
    return {
        "id": id_,
        "company": company,
        "title": title,
        "applied": applied,
        "interview": interview,
        "interview_tz": interview_tz,
        "status": status,
        "status_changed": status_changed,
        "note": note,
        "deleted": deleted,
        "deleted_at": deleted_at,
    }


# ---- build_table_lines ------------------------------------------------------

def test_build_table_lines_basic_structure():
    lines, column_starts, row_colors = job.display.build_table_lines([make_rec("Big Corp")])
    assert lines[0].startswith("Company")
    assert "Note" in lines[0]
    assert "Deleted" not in lines[0]
    assert len(lines) == 3
    assert row_colors[:2] == [None, None]
    assert "Big Corp" in lines[2]


def test_build_table_lines_note_column_shows_value():
    lines, _, _ = job.display.build_table_lines([make_rec("Big Corp", note="Referred by a friend")])
    assert "Referred by a friend" in lines[2]


def test_build_table_lines_note_column_is_last_before_deleted():
    lines, _, _ = job.display.build_table_lines([make_rec("Big Corp", deleted=True, deleted_at="2026-02-01")],
                                         show_deleted=True)
    header = lines[0]
    assert header.index("Note") < header.index("Deleted")


def test_build_table_lines_show_deleted_adds_column():
    r = make_rec("Big Corp", deleted=True, deleted_at="2026-02-01")
    lines, _, _ = job.display.build_table_lines([r], show_deleted=True)
    assert "Deleted" in lines[0]
    assert "2026-02-01" in lines[2]


def test_build_table_lines_unset_interview_renders_em_dash():
    lines, _, _ = job.display.build_table_lines([make_rec("Big Corp")])
    assert "—" in lines[2]


def test_row_color_deleted_wins_over_interview_color():
    aware_dt, tz = job.interview.parse_interview_datetime(["2026-01-10", "13:00", "CT"])
    r = make_rec("Big Corp", interview=aware_dt.isoformat(), interview_tz=tz,
                  deleted=True, deleted_at="2026-01-05")
    _, _, row_colors = job.display.build_table_lines([r])
    assert row_colors[2] == "deleted"


def test_row_color_none_when_not_deleted_and_no_interview():
    _, _, row_colors = job.display.build_table_lines([make_rec("Big Corp")])
    assert row_colors[2] is None


def test_build_table_lines_display_tz_converts_interview_cell():
    aware_dt, tz = job.interview.parse_interview_datetime(["2026-01-10", "13:00", "CT"])
    r = make_rec("Big Corp", interview=aware_dt.isoformat(), interview_tz=tz)
    display_tz = job.interview.resolve_tz_token("ET")
    lines, _, _ = job.display.build_table_lines([r], display_tz=display_tz)
    assert "14:00 ET" in lines[2]


# ---- classify_interview_color -----------------------------------------------

def test_classify_interview_color_none_when_unset():
    assert job.display.classify_interview_color(make_rec("Big Corp")) is None


def test_classify_interview_color_today_within_30_min_window(freeze_now, freeze_date):
    aware_dt, tz = job.interview.parse_interview_datetime(["2026-01-10", "13:00", "CT"])
    r = make_rec("Big Corp", interview=aware_dt.isoformat(), interview_tz=tz)
    freeze_date(2026, 1, 10)
    freeze_now(datetime(2026, 1, 10, 13, 10, tzinfo=ZoneInfo("America/Chicago")))
    assert job.display.classify_interview_color(r) == "today"


def test_classify_interview_color_past_after_30_min_cutoff(freeze_now, freeze_date):
    aware_dt, tz = job.interview.parse_interview_datetime(["2026-01-10", "13:00", "CT"])
    r = make_rec("Big Corp", interview=aware_dt.isoformat(), interview_tz=tz)
    freeze_date(2026, 1, 10)
    freeze_now(datetime(2026, 1, 10, 13, 31, tzinfo=ZoneInfo("America/Chicago")))
    assert job.display.classify_interview_color(r) == "past"


def test_classify_interview_color_exactly_at_30_min_cutoff_is_past(freeze_now, freeze_date):
    aware_dt, tz = job.interview.parse_interview_datetime(["2026-01-10", "13:00", "CT"])
    r = make_rec("Big Corp", interview=aware_dt.isoformat(), interview_tz=tz)
    freeze_date(2026, 1, 10)
    freeze_now(datetime(2026, 1, 10, 13, 30, tzinfo=ZoneInfo("America/Chicago")))
    assert job.display.classify_interview_color(r) == "past"


def test_classify_interview_color_future_date(freeze_now, freeze_date):
    aware_dt, tz = job.interview.parse_interview_datetime(["2026-01-11", "13:00", "CT"])
    r = make_rec("Big Corp", interview=aware_dt.isoformat(), interview_tz=tz)
    freeze_date(2026, 1, 10)
    freeze_now(datetime(2026, 1, 10, 13, 0, tzinfo=ZoneInfo("America/Chicago")))
    assert job.display.classify_interview_color(r) == "future"


# ---- colorize ---------------------------------------------------------------

def test_colorize_passthrough_when_no_color_key():
    assert job.display.colorize("hello", None) == "hello"


def test_colorize_wraps_with_forced_text_and_highlight_codes():
    result = job.display.colorize("hello", "today")
    expected = f"\x1b[{job.display.FORCED_TEXT_COLOR};{job.display.ROW_HIGHLIGHTS['today']}mhello\x1b[0m"
    assert result == expected


# ---- print_table dispatch (plain / color / scroll) --------------------------

def test_print_table_plain_when_it_fits(term_size, tty, capsys):
    term_size(200)
    tty(stdout=False, stdin=False)
    job.display.print_table([make_rec("Big Corp")])
    out = capsys.readouterr().out
    assert "Big Corp" in out
    assert "\x1b[" not in out


def test_print_table_applies_color_when_stdout_is_tty(term_size, tty, capsys):
    term_size(200)
    tty(stdout=True, stdin=True)
    r = make_rec("Big Corp", deleted=True, deleted_at="2026-01-01")
    job.display.print_table([r])
    out = capsys.readouterr().out
    assert f"\x1b[{job.display.FORCED_TEXT_COLOR};{job.display.ROW_HIGHLIGHTS['deleted']}m" in out


def test_print_table_dispatches_to_interactive_scroll_when_too_wide(term_size, tty, monkeypatch):
    term_size(10)
    tty(stdout=True, stdin=True)
    called = {}

    def fake_scroll(lines, column_starts, total_width, term_width, term_height, row_colors):
        called["invoked"] = True
        called["term_width"] = term_width

    monkeypatch.setattr(job.display, "scroll_table_interactive", fake_scroll)
    job.display.print_table([make_rec("Big Corp")])
    assert called.get("invoked") is True
    assert called["term_width"] == 10


def test_print_table_falls_back_to_plain_when_too_wide_but_not_both_ttys(term_size, tty, capsys, monkeypatch):
    term_size(10)
    tty(stdout=True, stdin=False)

    def explode(*a, **kw):
        raise AssertionError("scroll_table_interactive should not run without both TTYs")

    monkeypatch.setattr(job.display, "scroll_table_interactive", explode)
    job.display.print_table([make_rec("Big Corp")])
    out = capsys.readouterr().out
    assert "Big Corp" in out
