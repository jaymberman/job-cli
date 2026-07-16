#!/usr/bin/env python3
"""Track job applications: company, title, dates, and status."""

import difflib
import json
import os
import re
import select
import shutil
import sys
import termios
import tty
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "applications.json")

# Documentation-only: illustrative, not enforced via membership checks anywhere.
RESERVED = {"list", "status", "delete", "search", "sort", "help", "interview", "interviews", "today", "tz"}
AUTO_THRESHOLD = 0.80
CONFIRM_THRESHOLD = 0.55
AUTO_MARGIN = 0.12

SORT_FIELDS = {
    "company": "company",
    "title": "title",
    "applied": "applied",
    "status": "status",
    "status-changed": "status_changed",
}

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

# All DST variants of a region map to the same IANA zone; actual DST offset is
# resolved from the parsed date via zoneinfo, and we always redisplay just the
# base abbreviation (e.g. "CT"), never the DST-specific "CDT"/"CST".
TZ_ALIASES = {
    "CT": ("America/Chicago", "CT"), "CST": ("America/Chicago", "CT"),
    "CDT": ("America/Chicago", "CT"), "CENTRAL": ("America/Chicago", "CT"),
    "ET": ("America/New_York", "ET"), "EST": ("America/New_York", "ET"),
    "EDT": ("America/New_York", "ET"), "EASTERN": ("America/New_York", "ET"),
    "MT": ("America/Denver", "MT"), "MST": ("America/Denver", "MT"),
    "MDT": ("America/Denver", "MT"), "MOUNTAIN": ("America/Denver", "MT"),
    "PT": ("America/Los_Angeles", "PT"), "PST": ("America/Los_Angeles", "PT"),
    "PDT": ("America/Los_Angeles", "PT"), "PACIFIC": ("America/Los_Angeles", "PT"),
    "UTC": ("UTC", "UTC"), "GMT": ("UTC", "UTC"),
}
DEFAULT_TZ_ALIAS = "CT"

ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
SLASH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")
TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?([AaPp][Mm])?$")
MERIDIEM_RE = re.compile(r"^[AaPp][Mm]$")


def normalize(name):
    return re.sub(r"[^a-z0-9]", "", name.strip().lower())


def needs_migration(data):
    """True if any record predates the id-keyed, soft-delete-aware schema
    (detected by the absence of the `deleted` field, which every record
    written under the new schema always has, even freshly-created ones)."""
    return any("deleted" not in rec for rec in data.values())


def migrate_legacy_data(data):
    """Converts the old company-normalized-name-keyed schema (one record per
    company, no soft-delete fields) into the new id-keyed schema. Runs once,
    transparently, the next time the old file is loaded."""
    migrated = {}
    for rec in data.values():
        rec = dict(rec)
        rec.setdefault("deleted", False)
        rec.setdefault("deleted_at", None)
        new_key = new_id(migrated)
        rec["id"] = new_key
        migrated[new_key] = rec
    return migrated


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    if needs_migration(data):
        data = migrate_legacy_data(data)
        save_data(data)
    return data


def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def new_id(data):
    while True:
        candidate = uuid.uuid4().hex[:8]
        if candidate not in data:
            return candidate


def active_records(data):
    return {k: v for k, v in data.items() if not v.get("deleted", False)}


def deleted_records(data):
    return {k: v for k, v in data.items() if v.get("deleted", False)}


def company_records(pool, norm_key):
    return [rec for rec in pool.values() if normalize(rec["company"]) == norm_key]


def score(a, b):
    if a == b:
        return 1.0
    if a and b and (a in b or b in a):
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        containment = 0.75 + 0.25 * (len(shorter) / len(longer))
        return max(containment, difflib.SequenceMatcher(None, a, b).ratio())
    return difflib.SequenceMatcher(None, a, b).ratio()


def confirm(prompt):
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def resolve_company_key(pool, query, data=None):
    """Find the normalized company name (fuzzily, if needed) among the
    records in `pool` (an id-keyed dict) matching `query`. Returns the
    normalized company string, or None if there's no match (or the user
    declines a fuzzy guess). Matches against distinct normalized company
    names rather than individual records, since `pool` may legitimately
    contain several records (e.g. declined history) sharing one company.

    If `data` (the full, unfiltered dataset) is given and `query` exactly
    matches some company that exists in `data` but happens to fall outside
    `pool` (e.g. a soft-deleted company being looked up in the active-only
    pool), resolution stops there instead of falling through to a fuzzy
    guess against some unrelated company that *is* in `pool` — a company
    name typed exactly right should never be reinterpreted as a typo of
    something else just because it isn't in this particular pool."""
    norm = normalize(query)

    distinct = {}
    for rec in pool.values():
        key = normalize(rec["company"])
        if key not in distinct or rec["applied"] > distinct[key][1]:
            distinct[key] = (rec["company"], rec["applied"])
    if norm in distinct:
        return norm

    if data is not None and any(normalize(rec["company"]) == norm for rec in data.values()):
        return None
    if not distinct:
        return None

    scored = sorted(
        ((key, score(norm, key)) for key in distinct),
        key=lambda pair: pair[1],
        reverse=True,
    )
    top_key, top_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0

    if top_score >= AUTO_THRESHOLD and (top_score - second_score) >= AUTO_MARGIN:
        return top_key
    if top_score >= CONFIRM_THRESHOLD:
        display = distinct[top_key][0]
        if confirm(f"Did you mean '{display}'?"):
            return top_key
        return None
    return None


def resolve_active(data, query):
    """Fuzzy-resolves `query` to the id of the single active (non-deleted)
    record for that company, or None. Since at most one active record can
    exist per company, this is the resolution used everywhere a command
    targets "the" record for a company: lookup, status, delete, interview."""
    pool = active_records(data)
    norm_key = resolve_company_key(pool, query, data=data)
    if norm_key is None:
        return None
    for key, rec in pool.items():
        if normalize(rec["company"]) == norm_key:
            return key
    return None


def split_interview_tokens(tokens):
    """Split the trailing argv tokens after `interview` into (date_token,
    time_tokens, tz_token). time_tokens is 1 or 2 tokens (a bare/suffixed
    time, or a time + space-separated am/pm). tz_token is None if omitted,
    and can be supplied either as a single bare trailing token (e.g. `ET`)
    or via the `tz <ZONE>` keyword form (e.g. `tz ET`) -- both accepted,
    side by side. Returns (None, None, None) after printing an error if the
    shape is unrecognized."""
    date_token = tokens[0]
    remainder = tokens[1:]

    if len(remainder) == 0:
        print("Missing interview time. Usage: job <company> interview <date> <time> [<tz>|tz <tz>], "
              "e.g. '13:00', '9pm', '9:00 PM'.")
        return None, None, None
    if len(remainder) == 1:
        return date_token, remainder, None
    if len(remainder) == 2:
        if MERIDIEM_RE.match(remainder[1]):
            return date_token, remainder, None
        if remainder[1].lower() == "tz":
            print("Missing timezone value after `tz`. Usage: "
                  "job <company> interview <date> <time> tz <ZONE>")
            return None, None, None
        return date_token, remainder[:1], remainder[1]
    if len(remainder) == 3:
        if MERIDIEM_RE.match(remainder[1]):
            return date_token, remainder[:2], remainder[2]
        if remainder[1].lower() == "tz":
            return date_token, remainder[:1], remainder[2]
    if len(remainder) == 4 and MERIDIEM_RE.match(remainder[1]) and remainder[2].lower() == "tz":
        return date_token, remainder[:2], remainder[3]

    print("Couldn't parse interview date/time. Usage examples:")
    print('  job "Big Corp" interview 2026-07-13 13:00 CT')
    print('  job CompanyName interview 1/1/2027 9pm ET')
    print('  job "Big Corp" interview 2026-07-13 13:00 tz CT')
    return None, None, None


def parse_interview_date_token(token):
    """Returns a `date`, or None if `token` isn't a recognized date format."""
    m = ISO_DATE_RE.match(token)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    m = SLASH_DATE_RE.match(token)
    if m:
        mo, d, y = m.groups()
        mo, d = int(mo), int(d)
        if y is None:
            today = date.today()
            try:
                candidate = date(today.year, mo, d)
            except ValueError:
                return None
            if candidate < today:
                try:
                    candidate = date(today.year + 1, mo, d)
                except ValueError:
                    return None
            return candidate
        y = int(y)
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    return None


def parse_interview_time_token(time_tokens):
    """Returns ("resolved", hour24, minute) for unambiguous times,
    ("ambiguous", hour_1_12, minute) when am/pm is required to disambiguate,
    or None if unparseable."""
    text = time_tokens[0] if len(time_tokens) == 1 else time_tokens[0] + time_tokens[1]
    m = TIME_RE.match(text)
    if not m:
        return None
    hour_str, minute_str, suffix = m.groups()
    hour = int(hour_str)
    minute = int(minute_str) if minute_str is not None else 0
    if minute > 59:
        return None

    if suffix:
        if not (1 <= hour <= 12):
            return None
        hour24 = hour % 12
        if suffix.lower() == "pm":
            hour24 += 12
        return ("resolved", hour24, minute)

    if hour == 24:
        return ("resolved", 0, 0) if minute == 0 else None
    if hour == 0:
        return ("resolved", 0, minute)
    if 13 <= hour <= 23:
        return ("resolved", hour, minute)
    if 1 <= hour <= 12:
        return ("ambiguous", hour, minute)
    return None


def resolve_tz_token(token):
    """Returns (iana_zone, display_label), or (None, None) if `token` doesn't
    match a known alias. A missing token defaults to CT."""
    key = (token or DEFAULT_TZ_ALIAS).upper()
    return TZ_ALIASES.get(key, (None, None))


def unknown_tz_message(token):
    return (f"Unknown timezone '{token}'. Supported: CT, ET, MT, PT, UTC "
            "(also CST/CDT, EST/EDT, MST/MDT, PST/PDT, "
            "CENTRAL/EASTERN/MOUNTAIN/PACIFIC, GMT).")


def resolve_display_tz(tz_token):
    """Resolves a raw `tz <ZONE>` value from a display-side flag (or None,
    meaning no tz flag was given) into a `display_tz` to pass through
    print_table/print_record/format_interview_display. Returns
    (display_tz, ok): (None, True) means no override requested,
    ((iana_zone, tz_label), True) means a valid override, and (None, False)
    means `tz_token` didn't match a known alias (error already printed)."""
    if tz_token is None:
        return None, True
    iana_zone, tz_label = resolve_tz_token(tz_token)
    if iana_zone is None:
        print(unknown_tz_message(tz_token))
        return None, False
    return (iana_zone, tz_label), True


def confirm_meridiem(hour, minute):
    prompt = (f"You entered '{hour}:{minute:02d}' with no AM/PM — did you mean "
              f"{hour}:{minute:02d} AM or {hour}:{minute:02d} PM? [am/pm] ")
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return None
    if answer in ("am", "a"):
        return "am"
    if answer in ("pm", "p"):
        return "pm"
    return None


def parse_interview_datetime(tokens):
    """Parses the trailing argv tokens after `interview` into an aware
    datetime + display tz label, prompting to resolve am/pm ambiguity along
    the way. Returns (aware_dt, tz_label), or None after printing an error
    or "Cancelled." (ambiguity declined)."""
    date_token, time_tokens, tz_token = split_interview_tokens(tokens)
    if date_token is None:
        return None

    interview_date = parse_interview_date_token(date_token)
    if interview_date is None:
        print(f"Couldn't parse interview date '{date_token}'. Accepted formats: "
              "YYYY-MM-DD, M/D/YYYY, M/D/YY, or M/D (rolls to next year if that "
              "date has already passed this year).")
        return None

    time_result = parse_interview_time_token(time_tokens)
    if time_result is None:
        print(f"Couldn't parse interview time '{' '.join(time_tokens)}'. "
              "Accepted formats: '13:00', '9', '9pm', '9:00pm', '9:00 PM'.")
        return None

    kind, hour, minute = time_result
    if kind == "ambiguous":
        answer = confirm_meridiem(hour, minute)
        if answer is None:
            print("Cancelled.")
            return None
        hour = hour % 12
        if answer == "pm":
            hour += 12

    iana_zone, tz_label = resolve_tz_token(tz_token)
    if iana_zone is None:
        print(unknown_tz_message(tz_token))
        return None

    aware_dt = datetime.combine(interview_date, time(hour, minute), tzinfo=ZoneInfo(iana_zone))
    return aware_dt, tz_label


def format_interview_dt(aware_dt, tz_label):
    return f"{aware_dt.strftime('%Y-%m-%d %H:%M')} {tz_label}"


def format_interview_display(rec, display_tz=None):
    """Renders rec's interview time, or "—" if none is scheduled. By
    default renders in the zone it was stored in (rec["interview_tz"]);
    if `display_tz` (an (iana_zone, tz_label) pair) is given, converts the
    stored moment into that zone for display instead, without touching
    storage."""
    if rec.get("interview") is None:
        return "—"
    aware_dt = datetime.fromisoformat(rec["interview"])
    if display_tz is not None:
        iana_zone, tz_label = display_tz
        aware_dt = aware_dt.astimezone(ZoneInfo(iana_zone))
        return format_interview_dt(aware_dt, tz_label)
    return format_interview_dt(aware_dt, rec.get("interview_tz") or "")


def print_record(rec, display_tz=None):
    print(f"Company: {rec['company']}")
    print(f"Title: {rec['title']}")
    print(f"Applied: {rec['applied']}")
    print(f"Interview: {format_interview_display(rec, display_tz=display_tz)}")
    print(f"Status: {rec['status']}")
    print(f"Status changed: {rec['status_changed']}")


def cmd_lookup(data, company, show_all=False, display_tz=None):
    pool = data if show_all else active_records(data)
    norm_key = resolve_company_key(pool, company, data=data)
    if norm_key is None:
        print("no applications sent")
        return
    records = company_records(pool, norm_key)
    if show_all:
        records.sort(key=lambda r: r["applied"], reverse=True)
    print_table(records, show_deleted=show_all, display_tz=display_tz)


def cmd_create(data, company, title, status=None):
    active_key = resolve_active(data, company)
    if active_key is not None:
        print(f"{data[active_key]['company']} already has a record:")
        print_record(data[active_key])
        print("Use `status` to update it or `delete` to remove it first.")
        return

    declined_pool = deleted_records(data)
    declined_key = resolve_company_key(declined_pool, company, data=data)
    if declined_key is not None:
        display = company_records(declined_pool, declined_key)[0]["company"]
        prompt = f"already applied to {display} (declined). Do you want to proceed with a new record?"
        if not confirm(prompt):
            print("Cancelled.")
            return

    today = date.today().isoformat()
    key = new_id(data)
    data[key] = {
        "id": key,
        "company": company,
        "title": title,
        "applied": today,
        "interview": None,
        "interview_tz": None,
        "status": status if status is not None else "sent app",
        "status_changed": today,
        "deleted": False,
        "deleted_at": None,
    }
    save_data(data)
    print(f"Created record for {company}:")
    print_record(data[key])


def cmd_status(data, company, new_status, display_tz=None):
    key = resolve_active(data, company)
    if key is None:
        print("no applications sent")
        return
    data[key]["status"] = new_status
    data[key]["status_changed"] = date.today().isoformat()
    save_data(data)
    print(f"Updated {data[key]['company']}:")
    print_record(data[key], display_tz=display_tz)


def cmd_delete(data, company, hard=False, display_tz=None):
    key = resolve_active(data, company)
    if key is not None:
        rec = data[key]
        print("About to delete:")
        print_record(rec, display_tz=display_tz)
        prompt = ("This will PERMANENTLY delete this record. This cannot be undone. Are you sure?"
                  if hard else "Are you sure?")
        if not confirm(prompt):
            print("Cancelled.")
            return
        if hard:
            del data[key]
            save_data(data)
            print(f"Permanently deleted record for {rec['company']}.")
        else:
            rec["deleted"] = True
            rec["deleted_at"] = date.today().isoformat()
            save_data(data)
            print(f"Soft-deleted record for {rec['company']}. "
                  f"It's hidden from result sets but can be viewed with `job {rec['company']} --all`.")
        return

    if not hard:
        print("no applications sent")
        return

    # No active record: a hard delete can still reach into soft-deleted
    # history, since that's the only place left a matching record could be.
    declined_pool = deleted_records(data)
    norm_key = resolve_company_key(declined_pool, company, data=data)
    if norm_key is None:
        print("no applications sent")
        return
    candidates = company_records(declined_pool, norm_key)
    candidates.sort(key=lambda r: r["applied"], reverse=True)

    if len(candidates) == 1:
        cmd_delete_hard_one(data, candidates[0], display_tz=display_tz)
        return

    display = candidates[0]["company"]
    print(f"{display} has {len(candidates)} soft-deleted (declined) records:")
    for i, rec in enumerate(candidates, 1):
        print(f"  [{i}] {rec['title']} — applied {rec['applied']}, deleted {rec['deleted_at']}")
    try:
        answer = input(f"Enter a number to delete one, 'all' to delete all "
                        f"{len(candidates)}, or press Enter to cancel: ").strip().lower()
    except EOFError:
        answer = ""

    if answer == "all":
        prompt = (f"This will PERMANENTLY delete all {len(candidates)} soft-deleted records "
                  f"for {display}. This cannot be undone. Are you sure?")
        if not confirm(prompt):
            print("Cancelled.")
            return
        for rec in candidates:
            del data[rec["id"]]
        save_data(data)
        print(f"Permanently deleted {len(candidates)} records for {display}.")
        return

    if answer.isdigit() and 1 <= int(answer) <= len(candidates):
        cmd_delete_hard_one(data, candidates[int(answer) - 1], display_tz=display_tz)
        return

    print("Cancelled.")


def cmd_delete_hard_one(data, rec, display_tz=None):
    print("About to delete:")
    print_record(rec, display_tz=display_tz)
    if not confirm("This will PERMANENTLY delete this record. This cannot be undone. Are you sure?"):
        print("Cancelled.")
        return
    del data[rec["id"]]
    save_data(data)
    print(f"Permanently deleted record for {rec['company']}.")


def cmd_interview(data, company, tokens):
    key = resolve_active(data, company)
    if key is None:
        print("no applications sent")
        return
    if tokens[0].lower() == "cancel":
        if len(tokens) > 1:
            print("`cancel` doesn't take an extra argument.")
            return
        cmd_interview_cancel(data, key)
        return
    result = parse_interview_datetime(tokens)
    if result is None:
        return
    cmd_interview_set(data, key, *result)


def cmd_interview_cancel(data, key):
    rec = data[key]
    if rec.get("interview") is None:
        print(f"{rec['company']} has no interview scheduled.")
        return
    rec["interview"] = None
    rec["interview_tz"] = None
    rec["status_changed"] = date.today().isoformat()
    save_data(data)
    print(f"Cleared {rec['company']}'s interview.")


def cmd_interview_set(data, key, aware_dt, tz_label):
    rec = data[key]
    new_display = format_interview_dt(aware_dt, tz_label)
    if rec.get("interview") is not None:
        prompt = (f"{rec['company']}'s interview is currently {format_interview_display(rec)}. "
                  f"Set it to {new_display} ({aware_dt.tzinfo.key})?")
    else:
        prompt = f"Set {rec['company']}'s interview to {new_display} ({aware_dt.tzinfo.key})?"
    if not confirm(prompt):
        print("Cancelled.")
        return
    rec["interview"] = aware_dt.isoformat()
    rec["interview_tz"] = tz_label
    rec["status_changed"] = date.today().isoformat()
    save_data(data)
    print(f"Updated {rec['company']}'s interview:")
    print_record(rec)


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
    classify_interview_color's highlighting are untouched."""
    headers = ["Company", "Title", "Applied", "Interview", "Status Changed", "Status"]
    if show_deleted:
        headers = headers + ["Deleted"]
    rows = []
    for r in records:
        row = [r["company"], r["title"], r["applied"],
               format_interview_display(r, display_tz=display_tz),
               r["status_changed"], r["status"]]
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


def scroll_table_interactive(lines, column_starts, total_width, term_width, term_height, row_colors):
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


def render_sorted(data, key, reverse=False, show_all=False, display_tz=None):
    pool = data if show_all else active_records(data)
    if not pool:
        print("no applications tracked yet")
        return
    records = sorted(pool.values(), key=lambda r: r[key].lower(), reverse=reverse)
    print_table(records, show_deleted=show_all, display_tz=display_tz)


def parse_sort_field_order(field_arg, order_arg):
    """Validate a `sort <field> [order]` modifier. Returns (internal_key, reverse)
    on success, or (None, None) after printing an error."""
    field_key = field_arg.lower()
    if field_key not in SORT_FIELDS:
        valid = ", ".join(SORT_FIELDS)
        print(f"Unknown sort field '{field_arg}'. Valid fields: {valid}")
        return None, None

    order = "asc" if order_arg is None else order_arg.lower()
    if order not in ("asc", "desc"):
        print(f"Unknown sort order '{order_arg}'. Valid orders: asc, desc")
        return None, None

    return SORT_FIELDS[field_key], order == "desc"


_FLAG_STARTERS = ("--all", "tz")   # tokens that can never double as a sort-order value


def scan_display_flags(tokens, allow_sort=False):
    """Scans `tokens` for `--all`, `tz <ZONE>`, and (if allow_sort) `sort
    <field> [asc|desc]`, freely mixed in any order. Consumes recognized
    flag tokens; everything else is returned, in original order, in
    `leftover` for the caller to turn into a usage/error message exactly
    as it does today for any malformed trailing arguments.

    Returns (show_all, tz_token, sort_field, sort_order, leftover):
      - show_all: bool
      - tz_token: the raw token after `tz`, or None if `tz` wasn't given
        (unvalidated -- caller runs it through resolve_display_tz)
      - sort_field / sort_order: raw tokens after `sort`, or None/None if
        `sort` wasn't given (unvalidated -- caller runs them through
        parse_sort_field_order); sort_order is None when the field was
        given with no explicit order
      - leftover: unrecognized tokens; a dangling `sort`/`tz` with nothing
        after it also lands here as the single-element list ["sort"] or
        ["tz"], so callers can special-case those two exact shapes

    Duplicate flags: last occurrence wins. The token immediately after a
    sort field is consumed as the order value UNLESS it's a flag-starter
    (`--all`/`tz`, case-insensitive) -- that's what lets `sort applied tz
    PT` and `sort applied --all` parse as "no explicit order" instead of
    feeding `tz`/`--all` into parse_sort_field_order as a bogus order
    value."""
    show_all = False
    tz_token = None
    sort_field = None
    sort_order = None
    leftover = []

    i, n = 0, len(tokens)
    while i < n:
        low = tokens[i].lower()
        if low == "--all":
            show_all = True
            i += 1
        elif low == "tz":
            if i + 1 < n:
                tz_token = tokens[i + 1]
                i += 2
            else:
                leftover.append(tokens[i])
                i += 1
        elif allow_sort and low == "sort":
            if i + 1 >= n:
                leftover.append(tokens[i])
                i += 1
                continue
            sort_field = tokens[i + 1]
            i += 2
            if i < n and tokens[i].lower() not in _FLAG_STARTERS:
                sort_order = tokens[i]
                i += 1
        else:
            leftover.append(tokens[i])
            i += 1

    return show_all, tz_token, sort_field, sort_order, leftover


def cmd_list(data, sort_key="company", reverse=False, show_all=False, display_tz=None):
    render_sorted(data, sort_key, reverse=reverse, show_all=show_all, display_tz=display_tz)


def cmd_search(data, keyword, sort_key=None, reverse=None, show_all=False, display_tz=None):
    pool = data if show_all else active_records(data)
    if not pool:
        print("no applications tracked yet")
        return
    norm = normalize(keyword)
    fields = ("company", "title", "status")
    best = {
        f: max((score(norm, normalize(r[f])) for r in pool.values()), default=0.0)
        for f in fields
    }
    field = max(fields, key=lambda f: best[f])

    if field == "company":
        norm_key = resolve_company_key(pool, keyword, data=data)
        if norm_key is None:
            print("no matching applications found")
            return
        matches = company_records(pool, norm_key)
        if show_all:
            matches.sort(key=lambda r: r["applied"], reverse=True)
        print_table(matches, show_deleted=show_all, display_tz=display_tz)
        return

    if best[field] < AUTO_THRESHOLD:
        print("no matching applications found")
        return
    matches = [
        r for r in pool.values() if score(norm, normalize(r[field])) >= AUTO_THRESHOLD
    ]
    key = sort_key if sort_key is not None else "status_changed"
    rev = True if reverse is None else reverse
    matches.sort(key=lambda r: r[key].lower(), reverse=rev)
    print_table(matches, show_deleted=show_all, display_tz=display_tz)


def cmd_interviews(data, show_all=False, display_tz=None):
    """Default: active records whose interview hasn't crossed the 30-minute-
    past cutoff used for row highlighting (classify_interview_color's "past")
    — i.e. starting in the future, or within the last 30 minutes. --all:
    every interview regardless of date, plus soft-deleted records, shown
    with the extra Deleted column."""
    pool = data if show_all else active_records(data)
    matches = [r for r in pool.values() if r.get("interview") is not None]
    if not show_all:
        matches = [r for r in matches if classify_interview_color(r) != "past"]
    if not matches:
        print("no interviews scheduled")
        return
    matches.sort(key=lambda r: datetime.fromisoformat(r["interview"]), reverse=True)
    print_table(matches, show_deleted=show_all, display_tz=display_tz)


def cmd_today(data, show_all=False, display_tz=None):
    """Records touched today: applied today, status changed today, an
    interview scheduled for today's calendar date (regardless of whether
    that interview's time has already passed today or is still upcoming),
    or — when show_all is set — soft-deleted today."""
    pool = data if show_all else active_records(data)
    today = date.today()
    today_iso = today.isoformat()
    matches = [
        r for r in pool.values()
        if r["applied"] == today_iso
        or r["status_changed"] == today_iso
        or (r.get("interview") is not None and datetime.fromisoformat(r["interview"]).date() == today)
        or (show_all and r.get("deleted_at") == today_iso)
    ]
    if not matches:
        print("no activity today")
        return
    matches.sort(key=lambda r: r["company"].lower())
    print_table(matches, show_deleted=show_all, display_tz=display_tz)


def print_usage():
    print("Usage:")
    print("  job <company>                                     Look up a company (active record only)")
    print("  job <company> --all                               Look up a company, including soft-deleted history")
    print("  job <company> <title>                             Create a new application record")
    print("  job <company> <title> <status>                    Create a new record with a custom initial status")
    print("  job <company> status <new_status>                 Update the status of a record")
    print("  job <company> interview <date> <time> [<tz>|tz <tz>]  Set or update the interview date/time")
    print("  job <company> interview cancel                    Clear a scheduled interview")
    print("  job <company> delete                              Soft-delete a record: hidden from result sets, kept for history (asks to confirm)")
    print("  job <company> delete --hard                       Permanently delete a record: cannot be undone (asks to confirm);")
    print("                                                     if there's no active record, targets soft-deleted history instead")
    print("  job list [--all] [tz <ZONE>] [sort <field> [asc|desc]]        List all records (default: company, A-Z); --all includes soft-deleted")
    print("  job search <keyword> [--all] [tz <ZONE>] [sort <field> [asc|desc]]  Search company, title, or status (fuzzy); --all includes soft-deleted")
    print("  job interviews [--all] [tz <ZONE>]                Show interviews starting in the future or within the last 30 min, sorted by interview date (desc); --all also includes past interviews and soft-deleted records")
    print("  job today [--all] [tz <ZONE>]                     Show records applied, status-changed, or interviewing today; --all also includes soft-deleted today")
    print("  job help                                          Show this help text")
    print("  job --company <name> ...                          Force <name> to be treated as a company, even if it")
    print("                                                     matches a keyword like `list`, `today`, or `search`")
    print()
    print("Deleting a record is a soft delete by default: it stops appearing in list/search/today/")
    print("lookup results, but is kept around so re-applying to that company can warn you (\"already")
    print("applied to SomeCompany (declined). Do you want to proceed with a new record?\") and so")
    print("`--all` can still surface it. Use `delete --hard` to remove a record permanently — if there's")
    print("no active record left, `--hard` targets soft-deleted history instead (prompting you to pick")
    print("which one, or all of them, if a company has more than one soft-deleted record).")
    print()
    print("Quote company names, titles, and statuses that contain spaces, e.g.:")
    print('  job "Big Corp" "Data Engineer" "Recruiter reached out"')
    print()
    print("If a company name collides with a built-in keyword, use --company, e.g.:")
    print('  job --company list "Data Engineer"                looks up/creates company "list"')
    print()
    print("Interview date/time accepts flexible formats, e.g.:")
    print('  job "Big Corp" interview 2026-07-13 13:00 CT')
    print('  job CompanyName interview 1/1/2027 9pm ET')
    print('  job "Big Corp" interview 2026-07-13 13:00 tz CT')
    print("Defaults to Central time (CT) if no timezone is given; always confirms before saving.")
    print()
    print("Add `tz <ZONE>` to a lookup, list, search, interviews, today, status, or delete command to")
    print("view its Interview time converted to a different zone (CT/ET/MT/PT + synonyms, same as above)")
    print("without changing how or where it's stored, e.g.:")
    print("  job list tz PT")
    print('  job "Big Corp" status "phone screen" tz ET')
    print("For list/search/interviews/today, `--all`, `tz <ZONE>`, and `sort` can be combined in any order.")
    print()
    print("On an interactive terminal, table rows with a scheduled interview are highlighted:")
    print("  today = blue, future = green, past = yellow (unscheduled rows: no highlight).")
    print("  Soft-deleted rows (--all output) are always highlighted red instead, regardless of interview date.")


def print_list_help():
    print("Usage: job list [--all] [tz <ZONE>] [sort <field> [asc|desc]]")
    print()
    print("Lists every tracked application (active records only, by default).")
    print("Add `--all` to also include soft-deleted records, shown with an extra Deleted column.")
    print("Default sort: company name (A-Z).")
    print("Add `sort <field> [asc|desc]` to list in a different order, e.g.:")
    print("  job list sort status-changed desc")
    print("  job list --all sort status-changed desc")
    print("Add `tz <ZONE>` (CT/ET/MT/PT + synonyms) to view the Interview column converted to a")
    print("different zone, without changing how it's stored, e.g. `job list tz PT`.")
    print("`--all`, `tz <ZONE>`, and `sort` can be combined in any order.")
    print("Rows with a scheduled interview are highlighted (today = blue, future = green, past = yellow);")
    print("soft-deleted rows are always highlighted red instead.")


def print_search_help():
    print("Usage: job search <keyword> [--all] [tz <ZONE>] [sort <field> [asc|desc]]")
    print()
    print("Fuzzy-matches <keyword> against company, title, and status (active records only, by default).")
    print("Add `--all` to also include soft-deleted records, shown with an extra Deleted column.")
    print("Default sort: status-changed date (newest first).")
    print("Add `sort <field> [asc|desc]` to change the order, e.g.:")
    print('  job search "Data Engineer" sort title asc')
    print('  job search "Data Engineer" --all sort title asc')
    print("Add `tz <ZONE>` (CT/ET/MT/PT + synonyms) to view the Interview column converted to a")
    print("different zone, without changing how it's stored, e.g. `job search \"Data Engineer\" tz PT`.")
    print("`--all`, `tz <ZONE>`, and `sort` can be combined in any order.")
    print("Rows with a scheduled interview are highlighted (today = blue, future = green, past = yellow);")
    print("soft-deleted rows are always highlighted red instead.")


def print_interviews_help():
    print("Usage: job interviews [--all] [tz <ZONE>]")
    print()
    print("Shows every active record with an interview starting in the future, or within the last")
    print("30 minutes — the same cutoff used for the yellow 'past' row highlight below — sorted by")
    print("interview date (desc).")
    print("Add `--all` to also include past interviews and soft-deleted records, shown with an extra Deleted column.")
    print("Add `tz <ZONE>` (CT/ET/MT/PT + synonyms) to view the Interview column converted to a")
    print("different zone, without changing how it's stored, e.g. `job interviews tz PT`.")
    print("`--all` and `tz <ZONE>` can be combined in any order.")
    print("Rows are highlighted the same way as `list`/`search`: today = blue, future = green, past = yellow;")
    print("soft-deleted rows are always highlighted red instead.")


def print_today_help():
    print("Usage: job today [--all] [tz <ZONE>]")
    print()
    print("Shows every active record with activity today: applied today, status changed today,")
    print("or an interview scheduled for today (whether it already happened earlier today")
    print("or is still coming up later today). Sorted by company name (A-Z).")
    print("Add `--all` to also include records soft-deleted today, shown with an extra Deleted column.")
    print("Add `tz <ZONE>` (CT/ET/MT/PT + synonyms) to view the Interview column converted to a")
    print("different zone, without changing how it's stored, e.g. `job today tz PT`.")
    print("`--all` and `tz <ZONE>` can be combined in any order.")
    print("Rows are highlighted the same way as `list`/`search`: today = blue, future = green, past = yellow;")
    print("soft-deleted rows are always highlighted red instead.")


def strip_trailing_tz(rest):
    """If `rest` ends with a literal `tz <ZONE>` pair (case-insensitive) AND
    the tokens preceding it form one of the shapes that supports a
    display-tz override -- empty (plain lookup), [`--all`], [`status`,
    <value>], [`delete`], or [`delete`, `--hard`] -- returns (remaining,
    tz_token). Otherwise returns (rest, None) unchanged, leaving `tz`
    fully available as ordinary title/status text everywhere else
    (notably the 1- and 2-arg `create` shapes). Deliberately more
    conservative than scan_display_flags: dispatch_company's remaining
    tokens can be arbitrary free-form user text (a status value) that a
    free-order scanner can't safely tell apart from a literal `tz` flag
    token."""
    if len(rest) < 2 or rest[-2].lower() != "tz":
        return rest, None
    remaining, tz_token = rest[:-2], rest[-1]
    n = len(remaining)
    if n == 0:
        return remaining, tz_token
    if n == 1 and remaining[0].lower() in ("--all", "delete"):
        return remaining, tz_token
    if n == 2 and remaining[0].lower() == "delete" and remaining[1].lower() == "--hard":
        return remaining, tz_token
    if n == 2 and remaining[0].lower() == "status":
        return remaining, tz_token
    return rest, None


def dispatch_company(data, company, rest):
    if rest and rest[0].lower() == "interview":
        if len(rest) == 1:
            print("Missing interview date/time. Usage:")
            print("  job <company> interview <date> <time> [<tz>|tz <tz>]")
            print("  job <company> interview cancel")
            return
        cmd_interview(data, company, rest[1:])
        return

    rest, tz_token = strip_trailing_tz(rest)
    display_tz, ok = resolve_display_tz(tz_token)
    if not ok:
        return

    if len(rest) == 0:
        cmd_lookup(data, company, display_tz=display_tz)
        return

    if len(rest) == 1:
        second = rest[0]
        if second.lower() == "delete":
            cmd_delete(data, company, display_tz=display_tz)
        elif second.lower() == "--all":
            cmd_lookup(data, company, show_all=True, display_tz=display_tz)
        elif second.lower() == "status":
            print("Missing new status value. Usage: job <company> status <new_status>")
        else:
            cmd_create(data, company, second)
        return

    if len(rest) == 2:
        second, third = rest
        if second.lower() == "status":
            cmd_status(data, company, third, display_tz=display_tz)
            return
        if second.lower() == "delete":
            if third.lower() == "--hard":
                cmd_delete(data, company, hard=True, display_tz=display_tz)
            else:
                print("`delete` doesn't take an extra argument, except `--hard`.")
            return
        cmd_create(data, company, second, third)
        return

    print("Too many arguments. If a title or status has spaces, quote it, e.g.:")
    print('  job "Big Corp" "Data Engineer" "Recruiter reached out"')
    print()
    print_usage()


def main():
    args = sys.argv[1:]
    data = load_data()

    if len(args) == 0:
        print_usage()
        return

    if args[0].lower() == "--company":
        if len(args) < 2:
            print("Missing company name after --company. Usage: job --company <name> ...")
            return
        dispatch_company(data, args[1], args[2:])
        return

    if len(args) == 1 and args[0].lower() == "help":
        print_usage()
        return

    if args[0].lower() == "sort":
        print("`sort` must follow `list` or `search <keyword>`. Usage:")
        print("  job list [--all] [tz <ZONE>] sort <field> [asc|desc]")
        print("  job search <keyword> [--all] [tz <ZONE>] sort <field> [asc|desc]")
        return

    if args[0].lower() == "interview":
        print("`interview` must follow a company name. Usage:")
        print("  job <company> interview <date> <time> [<tz>|tz <tz>]")
        print("  job <company> interview cancel")
        return

    if args[0].lower() == "list":
        if len(args) == 1:
            cmd_list(data)
            return
        if len(args) == 2 and args[1].lower() == "help":
            print_list_help()
            return

        show_all, tz_token, sort_field, sort_order, leftover = scan_display_flags(args[1:], allow_sort=True)
        lowered_leftover = [t.lower() for t in leftover]
        if lowered_leftover == ["sort"]:
            print("Missing sort field. Usage: job list [--all] [tz <ZONE>] sort <field> [asc|desc]")
            return
        if lowered_leftover == ["tz"]:
            print("Missing timezone value after `tz`. Usage: "
                  "job list [--all] [tz <ZONE>] [sort <field> [asc|desc]], e.g. tz ET")
            return
        if leftover:
            print("Unrecognized `job list` arguments. Usage: job list [--all] [tz <ZONE>] [sort <field> [asc|desc]]")
            return

        display_tz, ok = resolve_display_tz(tz_token)
        if not ok:
            return
        if sort_field is None:
            cmd_list(data, show_all=show_all, display_tz=display_tz)
        else:
            key, reverse = parse_sort_field_order(sort_field, sort_order)
            if key is not None:
                cmd_list(data, key, reverse, show_all=show_all, display_tz=display_tz)
        return

    if args[0].lower() == "search":
        if len(args) == 1:
            print("Missing search keyword. Usage: job search <keyword> [--all] [tz <ZONE>] [sort <field> [asc|desc]]")
            return
        if len(args) == 2 and args[1].lower() == "help":
            print_search_help()
            return
        keyword = args[1]

        show_all, tz_token, sort_field, sort_order, leftover = scan_display_flags(args[2:], allow_sort=True)
        lowered_leftover = [t.lower() for t in leftover]
        if lowered_leftover == ["sort"]:
            print("Missing sort field. Usage: job search <keyword> [--all] [tz <ZONE>] sort <field> [asc|desc]")
            return
        if lowered_leftover == ["tz"]:
            print("Missing timezone value after `tz`. Usage: "
                  "job search <keyword> [--all] [tz <ZONE>] [sort <field> [asc|desc]], e.g. tz ET")
            return
        if leftover:
            print("Too many arguments for search. Quote multi-word keywords, e.g.:")
            print('  job search "Data Engineer"')
            return

        display_tz, ok = resolve_display_tz(tz_token)
        if not ok:
            return
        if sort_field is None:
            cmd_search(data, keyword, show_all=show_all, display_tz=display_tz)
        else:
            key, reverse = parse_sort_field_order(sort_field, sort_order)
            if key is not None:
                cmd_search(data, keyword, key, reverse, show_all=show_all, display_tz=display_tz)
        return

    if args[0].lower() == "interviews":
        if len(args) == 1:
            cmd_interviews(data)
            return
        if len(args) == 2 and args[1].lower() == "help":
            print_interviews_help()
            return

        show_all, tz_token, _, _, leftover = scan_display_flags(args[1:], allow_sort=False)
        lowered_leftover = [t.lower() for t in leftover]
        if lowered_leftover == ["tz"]:
            print("Missing timezone value after `tz`. Usage: job interviews [--all] [tz <ZONE>], e.g. tz ET")
            return
        if leftover:
            print("Unrecognized `job interviews` arguments. Usage: job interviews [--all] [tz <ZONE>]")
            return

        display_tz, ok = resolve_display_tz(tz_token)
        if not ok:
            return
        cmd_interviews(data, show_all=show_all, display_tz=display_tz)
        return

    if args[0].lower() == "today":
        if len(args) == 1:
            cmd_today(data)
            return
        if len(args) == 2 and args[1].lower() == "help":
            print_today_help()
            return

        show_all, tz_token, _, _, leftover = scan_display_flags(args[1:], allow_sort=False)
        lowered_leftover = [t.lower() for t in leftover]
        if lowered_leftover == ["tz"]:
            print("Missing timezone value after `tz`. Usage: job today [--all] [tz <ZONE>], e.g. tz ET")
            return
        if leftover:
            print("Unrecognized `job today` arguments. Usage: job today [--all] [tz <ZONE>]")
            return

        display_tz, ok = resolve_display_tz(tz_token)
        if not ok:
            return
        cmd_today(data, show_all=show_all, display_tz=display_tz)
        return

    dispatch_company(data, args[0], args[1:])


if __name__ == "__main__":
    main()
