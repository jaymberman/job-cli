import sys
from datetime import date, datetime

from . import storage
from . import company as company_mod
from . import interview
from . import display as display_mod

# Documentation-only: illustrative, not enforced via membership checks anywhere.
RESERVED = {"list", "status", "delete", "search", "sort", "help", "interview", "interviews", "today", "tz", "config", "note", "favorites"}
SORT_FIELDS = {
    "company": "company",
    "title": "title",
    "applied": "applied",
    "status": "status",
    "status-changed": "status_changed",
}

def cmd_lookup(data, company, show_all=False, display_tz=None):
    pool = data if show_all else company_mod.active_records(data)
    norm_key = company_mod.resolve_company_key(pool, company, data=data)
    if norm_key is None:
        print("no applications sent")
        return
    records = company_mod.company_records(pool, norm_key)
    if show_all:
        records.sort(key=lambda r: r["applied"], reverse=True)
    display_mod.print_table(records, show_deleted=show_all, display_tz=display_tz)


def cmd_create(data, company, title, status=None):
    active_key = company_mod.resolve_active(data, company)
    if active_key is not None:
        print(f"{data[active_key]['company']} already has a record:")
        display_mod.print_record(data[active_key])
        print("Use `status` to update it or `delete` to remove it first.")
        return

    declined_pool = company_mod.deleted_records(data)
    declined_key = company_mod.resolve_company_key(declined_pool, company, data=data)
    if declined_key is not None:
        display = company_mod.company_records(declined_pool, declined_key)[0]["company"]
        prompt = f"already applied to {display} (declined). Do you want to proceed with a new record?"
        if not company_mod.confirm(prompt):
            print("Cancelled.")
            return

    today = date.today().isoformat()
    key = storage.new_id(data)
    data[key] = {
        "id": key,
        "company": company,
        "title": title,
        "applied": today,
        "interview": None,
        "interview_tz": None,
        "status": status if status is not None else "sent app",
        "status_changed": today,
        "note": None,
        "is_favorite": False,
        "deleted": False,
        "deleted_at": None,
    }
    storage.save_data(data)
    print(f"Created record for {company}:")
    display_mod.print_record(data[key])


def cmd_status(data, company, new_status, display_tz=None):
    key = company_mod.resolve_active(data, company)
    if key is None:
        print("no applications sent")
        return
    data[key]["status"] = new_status
    data[key]["status_changed"] = date.today().isoformat()
    storage.save_data(data)
    print(f"Updated {data[key]['company']}:")
    display_mod.print_record(data[key], display_tz=display_tz)


def cmd_note(data, company, text, display_tz=None):
    key = company_mod.resolve_active(data, company)
    if key is None:
        print("no applications sent")
        return
    rec = data[key]
    if text.lower() == "clear":
        if rec.get("note") is None:
            print(f"{rec['company']} has no note set.")
            return
        rec["note"] = None
        storage.save_data(data)
        print(f"Cleared {rec['company']}'s note.")
        return
    rec["note"] = text
    storage.save_data(data)
    print(f"Updated {rec['company']}'s note:")
    display_mod.print_record(rec, display_tz=display_tz)


def cmd_favorite(data, company, favorite=True):
    """Sets or clears is_favorite on the active record for `company`. Applies
    immediately, no confirmation -- mirrors status/note rather than delete.
    Idempotent with no special no-op messaging: re-favoriting an already-
    favorited record (or vice versa) just prints the same message again."""
    key = company_mod.resolve_active(data, company)
    if key is None:
        print("no applications sent")
        return
    rec = data[key]
    rec["is_favorite"] = favorite
    storage.save_data(data)
    if favorite:
        print(f"Marked {rec['company']} as a favorite.")
    else:
        print(f"Removed {rec['company']} from favorites.")


def cmd_rename(data, company, new_name):
    """Renames the active record for `company` to `new_name`, cascading to
    every soft-deleted record that shares the old company's normalized name
    (company identity here is purely "records that normalize the same", so
    the whole group has to move together to keep --all and the declined-
    duplicate warning consistent under the new name). Applies immediately,
    no confirmation, unless the new name collides with another company:
    an existing *active* record there is a hard error (mirrors cmd_create's
    duplicate-active guard); existing soft-deleted-only history there prompts
    to confirm merging it in (mirrors cmd_create's declined-duplicate prompt).
    A rename that resolves back to the same company (e.g. just fixing casing/
    spacing) skips both collision checks entirely. Never touches
    status_changed -- this is an identity edit, not a status transition."""
    key = company_mod.resolve_active(data, company)
    if key is None:
        print("no applications sent")
        return
    rec = data[key]
    old_display = rec["company"]
    old_norm = company_mod.normalize(old_display)
    new_norm = company_mod.normalize(new_name)

    if new_norm != old_norm:
        active_key = company_mod.resolve_active(data, new_name)
        if active_key is not None and active_key != key:
            print(f"{data[active_key]['company']} already has a record:")
            display_mod.print_record(data[active_key])
            print("Use `status` to update it or `delete` to remove it first.")
            return

        declined_pool = company_mod.deleted_records(data)
        declined_key = company_mod.resolve_company_key(declined_pool, new_name, data=data)
        if declined_key is not None:
            display = company_mod.company_records(declined_pool, declined_key)[0]["company"]
            prompt = f"already applied to {display} (declined). Do you want to proceed with the rename?"
            if not company_mod.confirm(prompt):
                print("Cancelled.")
                return

    affected = [r for r in data.values() if company_mod.normalize(r["company"]) == old_norm]
    for r in affected:
        r["company"] = new_name
    storage.save_data(data)

    cascaded = len(affected) - 1
    if cascaded > 0:
        print(f"Renamed {old_display} to {new_name} ({cascaded} soft-deleted record(s) also updated).")
    else:
        print(f"Renamed {old_display} to {new_name}.")


def cmd_delete(data, company, hard=False, display_tz=None):
    key = company_mod.resolve_active(data, company)
    if key is not None:
        rec = data[key]
        print("About to delete:")
        display_mod.print_record(rec, display_tz=display_tz)
        prompt = ("This will PERMANENTLY delete this record. This cannot be undone. Are you sure?"
                  if hard else "Are you sure?")
        if not company_mod.confirm(prompt):
            print("Cancelled.")
            return
        if hard:
            del data[key]
            storage.save_data(data)
            print(f"Permanently deleted record for {rec['company']}.")
        else:
            rec["deleted"] = True
            rec["deleted_at"] = date.today().isoformat()
            rec["is_favorite"] = False
            storage.save_data(data)
            print(f"Soft-deleted record for {rec['company']}. "
                  f"It's hidden from result sets but can be viewed with `job {rec['company']} --all`.")
        return

    if not hard:
        print("no applications sent")
        return

    # No active record: a hard delete can still reach into soft-deleted
    # history, since that's the only place left a matching record could be.
    declined_pool = company_mod.deleted_records(data)
    norm_key = company_mod.resolve_company_key(declined_pool, company, data=data)
    if norm_key is None:
        print("no applications sent")
        return
    candidates = company_mod.company_records(declined_pool, norm_key)
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
        if not company_mod.confirm(prompt):
            print("Cancelled.")
            return
        for rec in candidates:
            del data[rec["id"]]
        storage.save_data(data)
        print(f"Permanently deleted {len(candidates)} records for {display}.")
        return

    if answer.isdigit() and 1 <= int(answer) <= len(candidates):
        cmd_delete_hard_one(data, candidates[int(answer) - 1], display_tz=display_tz)
        return

    print("Cancelled.")


def cmd_delete_hard_one(data, rec, display_tz=None):
    print("About to delete:")
    display_mod.print_record(rec, display_tz=display_tz)
    if not company_mod.confirm("This will PERMANENTLY delete this record. This cannot be undone. Are you sure?"):
        print("Cancelled.")
        return
    del data[rec["id"]]
    storage.save_data(data)
    print(f"Permanently deleted record for {rec['company']}.")


def cmd_interview(data, company, tokens):
    key = company_mod.resolve_active(data, company)
    if key is None:
        print("no applications sent")
        return
    if tokens[0].lower() == "cancel":
        if len(tokens) > 1:
            print("`cancel` doesn't take an extra argument.")
            return
        cmd_interview_cancel(data, key)
        return
    result = interview.parse_interview_datetime(tokens)
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
    storage.save_data(data)
    print(f"Cleared {rec['company']}'s interview.")


def cmd_interview_set(data, key, aware_dt, tz_label):
    rec = data[key]
    result = interview.normalize_interview_tz(aware_dt)
    if result is None:
        return
    normalized_dt, normalized_label = result
    new_display = interview.format_interview_dt(normalized_dt, normalized_label)
    if rec.get("interview") is not None:
        prompt = (f"{rec['company']}'s interview is currently {interview.format_interview_display(rec)}. "
                  f"Set it to {new_display} ({normalized_dt.tzinfo.key})?")
    else:
        prompt = f"Set {rec['company']}'s interview to {new_display} ({normalized_dt.tzinfo.key})?"
    if tz_label != normalized_label:
        entered_display = interview.format_interview_dt(aware_dt, tz_label)
        prompt = (f"You entered {entered_display} ({aware_dt.tzinfo.key}) — this converts to "
                  f"{new_display} ({normalized_dt.tzinfo.key}). " + prompt)
    if not company_mod.confirm(prompt):
        print("Cancelled.")
        return
    rec["interview"] = normalized_dt.isoformat()
    rec["interview_tz"] = normalized_label
    rec["status_changed"] = date.today().isoformat()
    storage.save_data(data)
    print(f"Updated {rec['company']}'s interview:")
    display_mod.print_record(rec)


def cmd_config_tz_show():
    _, label = storage.get_default_tz()
    if label is None:
        print("Default timezone: not set yet. Set one with `job config tz <ZONE>`.")
    else:
        print(f"Default timezone: {label}")


def cmd_config_tz_set(data, token):
    iana_zone, label = interview.resolve_tz_token(token)
    if iana_zone is None:
        print(interview.unknown_tz_message(token))
        return

    old_iana, old_label = storage.get_default_tz()
    if old_label == label:
        print(f"Default timezone is already {label}.")
        return

    count = sum(1 for rec in data.values() if rec.get("interview") is not None)
    if old_label is None:
        prompt = f"Set default timezone to {label}?"
    else:
        prompt = f"Change default timezone from {old_label} to {label}?"
    if count:
        prompt += f" This will convert {count} stored interview(s) to {label}."

    if not company_mod.confirm(prompt):
        print("Cancelled.")
        return

    storage.set_default_tz(label)
    if count:
        data = storage.backfill_interview_tz(data)
        storage.save_data(data)
        print(f"Default timezone set to {label}. Converted {count} interview(s).")
    else:
        print(f"Default timezone set to {label}.")


def render_sorted(data, key, reverse=False, show_all=False, display_tz=None):
    pool = data if show_all else company_mod.active_records(data)
    if not pool:
        print("no applications tracked yet")
        return
    records = sorted(pool.values(), key=lambda r: r[key].lower(), reverse=reverse)
    display_mod.print_table(records, show_deleted=show_all, display_tz=display_tz)


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
    pool = data if show_all else company_mod.active_records(data)
    if not pool:
        print("no applications tracked yet")
        return
    norm = company_mod.normalize(keyword)
    fields = ("company", "title", "status")
    best = {
        f: max((company_mod.score(norm, company_mod.normalize(r[f])) for r in pool.values()), default=0.0)
        for f in fields
    }
    field = max(fields, key=lambda f: best[f])

    if field == "company":
        norm_key = company_mod.resolve_company_key(pool, keyword, data=data)
        if norm_key is None:
            print("no matching applications found")
            return
        matches = company_mod.company_records(pool, norm_key)
        if show_all:
            matches.sort(key=lambda r: r["applied"], reverse=True)
        display_mod.print_table(matches, show_deleted=show_all, display_tz=display_tz)
        return

    if best[field] < company_mod.AUTO_THRESHOLD:
        print("no matching applications found")
        return
    matches = [
        r for r in pool.values() if company_mod.score(norm, company_mod.normalize(r[field])) >= company_mod.AUTO_THRESHOLD
    ]
    key = sort_key if sort_key is not None else "status_changed"
    rev = True if reverse is None else reverse
    matches.sort(key=lambda r: r[key].lower(), reverse=rev)
    display_mod.print_table(matches, show_deleted=show_all, display_tz=display_tz)


def cmd_interviews(data, show_all=False, display_tz=None):
    """Default: active records whose interview hasn't crossed the 30-minute-
    past cutoff used for row highlighting (classify_interview_color's "past")
    — i.e. starting in the future, or within the last 30 minutes. --all:
    every interview regardless of date, plus soft-deleted records, shown
    with the extra Deleted column."""
    pool = data if show_all else company_mod.active_records(data)
    matches = [r for r in pool.values() if r.get("interview") is not None]
    if not show_all:
        matches = [r for r in matches if display_mod.classify_interview_color(r) != "past"]
    if not matches:
        print("no interviews scheduled")
        return
    matches.sort(key=lambda r: datetime.fromisoformat(r["interview"]), reverse=True)
    display_mod.print_table(matches, show_deleted=show_all, display_tz=display_tz)


def cmd_today(data, show_all=False, display_tz=None):
    """Records touched today: applied today, status changed today, an
    interview scheduled for today's calendar date (regardless of whether
    that interview's time has already passed today or is still upcoming),
    or — when show_all is set — soft-deleted today."""
    pool = data if show_all else company_mod.active_records(data)
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
    display_mod.print_table(matches, show_deleted=show_all, display_tz=display_tz)


def cmd_favorites(data):
    """Every active record with is_favorite set, sorted by company name (A-Z)
    -- a fixed order, no sort modifier, mirroring interviews/today rather
    than list/search. No --all: a soft-deleted record can never be
    favorited (delete clears the flag), so there's nothing extra to show."""
    matches = [r for r in company_mod.active_records(data).values() if r.get("is_favorite", False)]
    if not matches:
        print("no favorites yet")
        return
    matches.sort(key=lambda r: r["company"].lower())
    display_mod.print_table(matches)


def print_usage():
    print("Usage:")
    print("  job <company>                                     Look up a company (active record only)")
    print("  job <company> --all                               Look up a company, including soft-deleted history")
    print("  job <company> <title>                             Create a new application record")
    print("  job <company> <title> <status>                    Create a new record with a custom initial status")
    print("  job <company> status <new_status>                 Update the status of a record")
    print("  job <company> note <text>                         Set or edit a record's note")
    print("  job <company> note clear                          Clear a record's note")
    print("  job <company> interview <date> <time> [<tz>|tz <tz>]  Set or update the interview date/time")
    print("  job <company> interview cancel                    Clear a scheduled interview")
    print("  job <company> delete                              Soft-delete a record: hidden from result sets, kept for history (asks to confirm)")
    print("  job <company> delete --hard                       Permanently delete a record: cannot be undone (asks to confirm);")
    print("                                                     if there's no active record, targets soft-deleted history instead")
    print("  job <company> --favorite                          Mark a record as a favorite")
    print("  job <company> --remove-favorite                   Remove a record's favorite mark")
    print("  job <company> --rename <new_name>                 Rename a company (cascades to its soft-deleted history)")
    print("  job favorites                                     Show every favorited record (active only, company A-Z)")
    print("  job list [--all] [tz <ZONE>] [sort <field> [asc|desc]]        List all records (default: company, A-Z); --all includes soft-deleted")
    print("  job search <keyword> [--all] [tz <ZONE>] [sort <field> [asc|desc]]  Search company, title, or status (fuzzy); --all includes soft-deleted")
    print("  job interviews [--all] [tz <ZONE>]                Show interviews starting in the future or within the last 30 min, sorted by interview date (desc); --all also includes past interviews and soft-deleted records")
    print("  job today [--all] [tz <ZONE>]                     Show records applied, status-changed, or interviewing today; --all also includes soft-deleted today")
    print("  job config tz <ZONE>                              Set your default timezone (converts stored interviews to match)")
    print("  job config tz                                     Show your currently configured default timezone")
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
    print("Quote company names, titles, statuses, and notes that contain spaces, e.g.:")
    print('  job "Big Corp" "Data Engineer" "Recruiter reached out"')
    print('  job "Big Corp" note "Referred by a friend on the team"')
    print()
    print("A note is freeform text shown alongside every record wherever it's returned (lookup,")
    print("list, search, interviews, today). It's null until set, has no history of past edits or")
    print("when it last changed, and is cleared with `job <company> note clear`.")
    print()
    print("Favorite a record with `job <company> --favorite`, unmark it with `job <company>")
    print("--remove-favorite`, and view all favorites with `job favorites`. Both apply immediately,")
    print("no confirmation needed. Favorite status is never shown anywhere else (no column, no")
    print("highlight) and is cleared automatically whenever a record is deleted.")
    print()
    print("Rename a company with `job <company> --rename <new_name>` — this also renames any soft-deleted")
    print("history sharing the old name, so `--all` and the declined-duplicate warning stay consistent under")
    print("the new name. Applies immediately, no confirmation, unless the new name collides with another")
    print("company: an existing active record blocks the rename (same message as a duplicate `create`); existing")
    print("soft-deleted history at the new name prompts to confirm merging it in instead.")
    print()
    print("If a company name collides with a built-in keyword, use --company, e.g.:")
    print('  job --company list "Data Engineer"                looks up/creates company "list"')
    print()
    print("Interview date/time accepts flexible formats, e.g.:")
    print('  job "Big Corp" interview 2026-07-13 13:00 CT')
    print('  job CompanyName interview 1/1/2027 9pm ET')
    print('  job "Big Corp" interview 2026-07-13 13:00 tz CT')
    print("Defaults to your configured default timezone if no timezone is given (prompting you to set")
    print("one the first time it's needed); always confirms before saving.")
    print()
    print("Set or change your default timezone at any time with `job config tz <ZONE>` (CT/ET/MT/PT/UTC")
    print("+ synonyms) — this converts every stored interview to the new zone. Check it with `job config tz`.")
    print()
    print("Add `tz <ZONE>` to a lookup, list, search, interviews, today, status, note, or delete command to")
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


def print_favorites_help():
    print("Usage: job favorites")
    print()
    print("Shows every active record marked as a favorite (see `job <company> --favorite`),")
    print("sorted by company name (A-Z). Favorite status is never shown anywhere else --")
    print("this is the only place it's surfaced, and even here it's implicit: every row")
    print("listed is a favorite, there's no separate Favorite column.")


def strip_trailing_tz(rest):
    """If `rest` ends with a literal `tz <ZONE>` pair (case-insensitive) AND
    the tokens preceding it form one of the shapes that supports a
    display-tz override -- empty (plain lookup), [`--all`], [`status`,
    <value>], [`note`, <value>], [`delete`], or [`delete`, `--hard`] --
    returns (remaining, tz_token). Otherwise returns (rest, None)
    unchanged, leaving `tz` fully available as ordinary title/status/note
    text everywhere else (notably the 1- and 2-arg `create` shapes).
    Deliberately more conservative than scan_display_flags:
    dispatch_company's remaining tokens can be arbitrary free-form user
    text (a status or note value) that a free-order scanner can't safely
    tell apart from a literal `tz` flag token."""
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
    if n == 2 and remaining[0].lower() in ("status", "note"):
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
    display_tz, ok = interview.resolve_display_tz(tz_token)
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
        elif second.lower() == "--favorite":
            cmd_favorite(data, company, favorite=True)
        elif second.lower() == "--remove-favorite":
            cmd_favorite(data, company, favorite=False)
        elif second.lower() == "status":
            print("Missing new status value. Usage: job <company> status <new_status>")
        elif second.lower() == "note":
            print("Missing note value. Usage:")
            print("  job <company> note <text>")
            print("  job <company> note clear")
        elif second.lower() == "--rename":
            print("Missing new company name. Usage: job <company> --rename <new_name>")
        else:
            cmd_create(data, company, second)
        return

    if len(rest) == 2:
        second, third = rest
        if second.lower() == "status":
            cmd_status(data, company, third, display_tz=display_tz)
            return
        if second.lower() == "note":
            cmd_note(data, company, third, display_tz=display_tz)
            return
        if second.lower() == "--rename":
            cmd_rename(data, company, third)
            return
        if second.lower() == "--favorite":
            print("`--favorite` doesn't take an extra argument.")
            return
        if second.lower() == "--remove-favorite":
            print("`--remove-favorite` doesn't take an extra argument.")
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
    data = storage.load_data()

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

    if args[0].lower() == "config":
        if len(args) == 1:
            print("Usage: job config tz <ZONE>")
            print("       job config tz              (show the current default)")
            return
        if args[1].lower() != "tz":
            print(f"Unknown `config` subcommand '{args[1]}'. Usage: job config tz <ZONE>")
            return
        if len(args) == 2:
            cmd_config_tz_show()
            return
        if len(args) == 3:
            cmd_config_tz_set(data, args[2])
            return
        print("Too many arguments. Usage: job config tz <ZONE>")
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

        display_tz, ok = interview.resolve_display_tz(tz_token)
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

        display_tz, ok = interview.resolve_display_tz(tz_token)
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

        display_tz, ok = interview.resolve_display_tz(tz_token)
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

        display_tz, ok = interview.resolve_display_tz(tz_token)
        if not ok:
            return
        cmd_today(data, show_all=show_all, display_tz=display_tz)
        return

    if args[0].lower() == "favorites":
        if len(args) == 1:
            cmd_favorites(data)
            return
        if len(args) == 2 and args[1].lower() == "help":
            print_favorites_help()
            return
        print("Unrecognized `job favorites` arguments. Usage: job favorites")
        return

    dispatch_company(data, args[0], args[1:])


if __name__ == "__main__":
    main()
