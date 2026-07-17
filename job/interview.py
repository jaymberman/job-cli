import re
import sys
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from . import storage

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

ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
SLASH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")
TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?([AaPp][Mm])?$")
MERIDIEM_RE = re.compile(r"^[AaPp][Mm]$")


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
    """Returns (iana_zone, display_label) for an explicit alias token
    (case-insensitive), or (None, None) if it doesn't match a known alias.
    A `token` of None always returns (None, None) here -- resolving a
    missing token to the user's configured default is
    resolve_or_prompt_default_tz's job, since that may require prompting."""
    if token is None:
        return None, None
    return TZ_ALIASES.get(token.upper(), (None, None))


def resolve_or_prompt_default_tz():
    """Returns (iana_zone, label) for the user's configured default
    timezone. If none is configured yet, interactively prompts for one
    (persisting the answer via set_default_tz for next time) when stdin is
    a TTY -- a single-shot attempt, mirroring confirm_meridiem's AM/PM
    disambiguation: a blank/EOF/unrecognized answer cancels rather than
    retrying. When stdin isn't a TTY (piped/scripted) and nothing is
    configured, prints an error instead of silently guessing a zone.
    Either failure path returns (None, None), the same "can't resolve"
    shape an unrecognized explicit token gets from resolve_tz_token, so
    callers can treat both identically."""
    iana_zone, label = storage.get_default_tz()
    if label is not None:
        return iana_zone, label

    if not sys.stdin.isatty():
        print("No default timezone is configured yet. Set one with `job config tz <ZONE>` "
              "(supported: CT, ET, MT, PT, UTC, also CST/CDT, EST/EDT, MST/MDT, PST/PDT, "
              "CENTRAL/EASTERN/MOUNTAIN/PACIFIC, GMT).")
        return None, None

    try:
        answer = input("You haven't set a default timezone yet. Enter one "
                        "(CT/ET/MT/PT/UTC, or a synonym): ").strip()
    except EOFError:
        answer = ""
    if not answer:
        print("Cancelled.")
        return None, None

    iana_zone, label = resolve_tz_token(answer)
    if iana_zone is None:
        print(unknown_tz_message(answer))
        return None, None

    storage.set_default_tz(label)
    print(f"Default timezone set to {label}.")
    return iana_zone, label


def normalize_interview_tz(aware_dt):
    """Converts aware_dt to the user's configured default timezone,
    preserving the same instant -- prompting for a default first if none is
    configured yet (see resolve_or_prompt_default_tz). Every stored
    interview goes through this so a return set is never a mix of zones
    regardless of what zone it was entered in. Returns None if a default
    couldn't be resolved (prompt declined/EOF/unrecognized, or a
    non-interactive invocation with nothing configured) -- the caller's
    write is expected to abort in that case, same as any other unresolvable
    timezone."""
    default_iana, default_label = resolve_or_prompt_default_tz()
    if default_label is None:
        return None
    return aware_dt.astimezone(ZoneInfo(default_iana)), default_label


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

    if tz_token is None:
        iana_zone, tz_label = resolve_or_prompt_default_tz()
    else:
        iana_zone, tz_label = resolve_tz_token(tz_token)
    if iana_zone is None:
        if tz_token is not None:
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
