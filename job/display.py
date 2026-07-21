import os
import select
import shutil
import sys
import termios
import tty
from datetime import date, datetime, timedelta

from . import interview

# Vivid background highlights for table rows with a scheduled interview, keyed
# by classify_interview_color()'s return value. Paired with a forced dark-gray
# foreground so highlighted rows stay readable regardless of terminal theme.
ROW_HIGHLIGHTS = {
    "today": "48;2;100;181;246",   # vivid blue
    "future": "48;2;129;199;132",  # vivid green
    "past": "48;2;255;224;102",    # vivid yellow
    "deleted": "48;2;229;115;115", # vivid red
}
FORCED_TEXT_COLOR = "38;2;51;51;51"  # dark gray


def print_record(rec, display_tz=None):
    print(f"Company: {rec['company']}")
    print(f"Title: {rec['title']}")
    print(f"Applied: {rec['applied']}")
    print(f"Interview: {interview.format_interview_display(rec, display_tz=display_tz)}")
    print(f"Status: {rec['status']}")
    print(f"Status changed: {rec['status_changed']}")
    print(f"Note: {rec.get('note') or '—'}")


def classify_interview_color(rec):
    """Returns None (no interview scheduled), "today", "future", or "past".
    "past" fires once 30 minutes have elapsed since the interview's start
    time, per the local clock of the machine running the CLI — even if that
    start time was earlier today. Otherwise falls back to the same
    naive-local-date convention the rest of the codebase uses (applied/
    status-changed dates), not the interview's own stored UTC offset, to
    split "today" from "future"."""
    if rec.get("interview") is None:
        return None
    interview_dt = datetime.fromisoformat(rec["interview"])
    now = datetime.now().astimezone()
    if now >= interview_dt + timedelta(minutes=30):
        return "past"
    return "today" if interview_dt.date() == date.today() else "future"


def colorize(text, color_key):
    """Wraps `text` in the SGR sequence for `color_key` (a key of
    ROW_HIGHLIGHTS) plus the forced dark-gray foreground, then a reset.
    Returns `text` unchanged if `color_key` is None. Callers are responsible
    for only invoking this when stdout is a TTY."""
    if color_key is None:
        return text
    return f"\x1b[{FORCED_TEXT_COLOR};{ROW_HIGHLIGHTS[color_key]}m{text}\x1b[0m"


def build_table_lines(records, show_deleted=False, display_tz=None):
    """Returns (lines, column_starts, row_colors): `lines` is a list of
    equal-length, plain/uncolored strings (header, separator, one per row)
    since every cell is `ljust`-padded including the last column;
    `column_starts` is the sorted character offset where each column begins,
    used for scroll-snapping. `row_colors` is parallel to `lines` (None for
    header/separator, else "deleted" for a soft-deleted row, else
    classify_interview_color(r) — deleted always wins over interview color)
    — kept out of `lines` itself so ANSI codes never corrupt the width/
    scroll-offset math. `show_deleted` appends a trailing Deleted column
    (deleted_at, or — for active records) — only ever requested by --all
    output, since ordinary list/search/today/lookup results are always
    active-only already. `display_tz`, if given, converts every row's
    Interview cell into that zone for display only — row selection and
    classify_interview_color's highlighting are untouched. A favorited
    record gets a plain "♥" appended to its Company cell (one space
    separator, no ANSI color) — folded into the cell string itself, before
    width/padding math, rather than a separate column, so it's just more
    text as far as ljust/scrolling are concerned."""
    headers = ["Company", "Title", "Applied", "Interview", "Status Changed", "Status", "Note"]
    if show_deleted:
        headers = headers + ["Deleted"]
    rows = []
    for r in records:
        company_cell = r["company"] + (" ♥" if r.get("is_favorite", False) else "")
        row = [company_cell, r["title"], r["applied"],
               interview.format_interview_display(r, display_tz=display_tz),
               r["status_changed"], r["status"], r.get("note") or "—"]
        if show_deleted:
            row.append(r.get("deleted_at") or "—")
        rows.append(row)
    widths = [
        max(len(h), max((len(row[i]) for row in rows), default=0))
        for i, h in enumerate(headers)
    ]
    column_starts, offset = [], 0
    for w in widths:
        column_starts.append(offset)
        offset += w + 2  # 2-space separator, matches fmt_row's "  ".join

    def fmt_row(row):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = [fmt_row(headers), fmt_row(["-" * w for w in widths])]
    lines += [fmt_row(row) for row in rows]
    row_colors = [None, None] + [
        "deleted" if r.get("deleted") else classify_interview_color(r) for r in records
    ]
    return lines, column_starts, row_colors


def print_table(records, show_deleted=False, display_tz=None):
    lines, column_starts, row_colors = build_table_lines(
        records, show_deleted=show_deleted, display_tz=display_tz)
    total_width = max((len(line) for line in lines), default=0)
    term_size = shutil.get_terminal_size(fallback=(80, 24))
    term_width, term_height = term_size.columns, term_size.lines

    def print_plain():
        color_ok = sys.stdout.isatty()
        for line, color in zip(lines, row_colors):
            print(colorize(line, color) if color_ok else line)

    if total_width <= term_width:
        print_plain()
        return
    if sys.stdout.isatty() and sys.stdin.isatty():
        scroll_table_interactive(lines, column_starts, total_width, term_width, term_height, row_colors)
    else:
        print_plain()


def scroll_stops(column_starts, total_width, term_width):
    """Horizontal offsets the view is allowed to snap to: 0, each column's
    start (clamped so it can't scroll past the right edge), and the max
    offset itself (so the last column can always be scrolled fully into
    view even if it doesn't land on a clamped column boundary)."""
    max_offset = max(0, total_width - term_width)
    return sorted(set([0, max_offset] + [min(s, max_offset) for s in column_starts]))


def next_stop(stops, current, direction):
    if direction > 0:
        return next((s for s in stops if s > current), stops[-1])
    return next((s for s in reversed(stops) if s < current), stops[0])


def build_scrollbar(offset, total_width, term_width):
    thumb_width = max(1, round(term_width * (term_width / total_width)))
    max_offset = total_width - term_width
    thumb_pos = 0 if max_offset == 0 else round((term_width - thumb_width) * (offset / max_offset))
    bar = ["░"] * term_width
    for i in range(thumb_pos, min(thumb_pos + thumb_width, term_width)):
        bar[i] = "█"
    if term_width >= 2:
        bar[0], bar[-1] = "◄", "►"
    return "".join(bar)


def read_key(fd):
    """Reads one logical keypress: a single byte, or a 3-byte arrow-key
    escape sequence. A lone ESC keypress won't have a follow-up byte arrive
    within the short select() window, whereas a real arrow key sends its
    whole sequence as one burst - that's how the two are told apart."""
    ch = os.read(fd, 1)
    if ch != b"\x1b":
        return ch
    if not select.select([fd], [], [], 0.05)[0]:
        return b"\x1b"
    if os.read(fd, 1) != b"[":
        return b"\x1b"
    return b"\x1b[" + os.read(fd, 1)


def scroll_table_interactive(lines, column_starts, total_width, term_width, term_height, row_colors):  # pragma: no cover
    """Inline, independently-2D-scrollable table view, rendered on the
    terminal's alternate screen buffer (restored to whatever was on screen
    before on exit, like a pager) — this is what keeps every redraw correct
    regardless of table/terminal size, unlike the old in-place cursor-up
    approach which broke once the table had more rows than the terminal had
    lines. The header and separator rows stay pinned at the top; only data
    rows scroll underneath them. Left/Right snap horizontally between column
    boundaries; Up/Down move vertically one data row at a time; the two axes
    are tracked and clamped independently, so scrolling one never moves the
    other. 'q'/'Q' exits. row_colors is parallel to lines; each visible slice
    is colorized after slicing, never before, so ANSI codes are never cut
    mid-escape-sequence. This only runs when stdout/stdin are already
    confirmed TTYs, so coloring here is unconditional."""
    fd = sys.stdin.fileno()
    stops = scroll_stops(column_starts, total_width, term_width)
    header_lines, header_colors = lines[:2], row_colors[:2]
    data_lines, data_colors = lines[2:], row_colors[2:]
    visible_rows = max(0, term_height - 4)  # scrollbar + instructions + header + separator
    max_row_offset = max(0, len(data_lines) - visible_rows)
    col_offset = row_offset = 0
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?1049h\x1b[2J")
        while True:
            frame = [build_scrollbar(col_offset, total_width, term_width),
                     "(↑/↓/←/→ to scroll, q to exit)"]
            visible = list(zip(header_lines, header_colors)) + list(zip(
                data_lines[row_offset:row_offset + visible_rows],
                data_colors[row_offset:row_offset + visible_rows],
            ))
            frame += [
                colorize(line[col_offset:col_offset + term_width], color)
                for line, color in visible
            ]
            sys.stdout.write("\x1b[H")
            for line in frame:
                sys.stdout.write("\x1b[K" + line + "\n")
            sys.stdout.flush()

            key = read_key(fd)
            if key == b"\x1b[C":
                col_offset = next_stop(stops, col_offset, 1)
            elif key == b"\x1b[D":
                col_offset = next_stop(stops, col_offset, -1)
            elif key == b"\x1b[B":
                row_offset = min(row_offset + 1, max_row_offset)
            elif key == b"\x1b[A":
                row_offset = max(row_offset - 1, 0)
            elif key.lower() == b"q":
                break
    finally:
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
