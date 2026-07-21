import sys

from . import storage
from . import interview
from . import commands

# Documentation-only: illustrative, not enforced via membership checks anywhere.
RESERVED = {"list", "status", "delete", "search", "sort", "help", "interview", "interviews", "today", "tz", "config", "note", "favorites"}
SORT_FIELDS = {
    "company": "company",
    "title": "title",
    "applied": "applied",
    "status": "status",
    "status-changed": "status_changed",
}


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
    print("no confirmation needed. A favorited record shows a ♥ next to its company name in every")
    print("table view, and favorite status is cleared automatically whenever a record is deleted.")
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
    print("sorted by company name (A-Z). Favorited records also show a ♥ next to their company")
    print("name in every table view (list, search, lookup, interviews, today, and here) --")
    print("there's no separate Favorite column.")


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
        commands.cmd_interview(data, company, rest[1:])
        return

    rest, tz_token = strip_trailing_tz(rest)
    display_tz, ok = interview.resolve_display_tz(tz_token)
    if not ok:
        return

    if len(rest) == 0:
        commands.cmd_lookup(data, company, display_tz=display_tz)
        return

    if len(rest) == 1:
        second = rest[0]
        if second.lower() == "delete":
            commands.cmd_delete(data, company, display_tz=display_tz)
        elif second.lower() == "--all":
            commands.cmd_lookup(data, company, show_all=True, display_tz=display_tz)
        elif second.lower() == "--favorite":
            commands.cmd_favorite(data, company, favorite=True)
        elif second.lower() == "--remove-favorite":
            commands.cmd_favorite(data, company, favorite=False)
        elif second.lower() == "status":
            print("Missing new status value. Usage: job <company> status <new_status>")
        elif second.lower() == "note":
            print("Missing note value. Usage:")
            print("  job <company> note <text>")
            print("  job <company> note clear")
        elif second.lower() == "--rename":
            print("Missing new company name. Usage: job <company> --rename <new_name>")
        else:
            commands.cmd_create(data, company, second)
        return

    if len(rest) == 2:
        second, third = rest
        if second.lower() == "status":
            commands.cmd_status(data, company, third, display_tz=display_tz)
            return
        if second.lower() == "note":
            commands.cmd_note(data, company, third, display_tz=display_tz)
            return
        if second.lower() == "--rename":
            commands.cmd_rename(data, company, third)
            return
        if second.lower() == "--favorite":
            print("`--favorite` doesn't take an extra argument.")
            return
        if second.lower() == "--remove-favorite":
            print("`--remove-favorite` doesn't take an extra argument.")
            return
        if second.lower() == "delete":
            if third.lower() == "--hard":
                commands.cmd_delete(data, company, hard=True, display_tz=display_tz)
            else:
                print("`delete` doesn't take an extra argument, except `--hard`.")
            return
        commands.cmd_create(data, company, second, third)
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
            commands.cmd_config_tz_show()
            return
        if len(args) == 3:
            commands.cmd_config_tz_set(data, args[2])
            return
        print("Too many arguments. Usage: job config tz <ZONE>")
        return

    if args[0].lower() == "list":
        if len(args) == 1:
            commands.cmd_list(data)
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
            commands.cmd_list(data, show_all=show_all, display_tz=display_tz)
        else:
            key, reverse = parse_sort_field_order(sort_field, sort_order)
            if key is not None:
                commands.cmd_list(data, key, reverse, show_all=show_all, display_tz=display_tz)
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
            commands.cmd_search(data, keyword, show_all=show_all, display_tz=display_tz)
        else:
            key, reverse = parse_sort_field_order(sort_field, sort_order)
            if key is not None:
                commands.cmd_search(data, keyword, key, reverse, show_all=show_all, display_tz=display_tz)
        return

    if args[0].lower() == "interviews":
        if len(args) == 1:
            commands.cmd_interviews(data)
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
        commands.cmd_interviews(data, show_all=show_all, display_tz=display_tz)
        return

    if args[0].lower() == "today":
        if len(args) == 1:
            commands.cmd_today(data)
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
        commands.cmd_today(data, show_all=show_all, display_tz=display_tz)
        return

    if args[0].lower() == "favorites":
        if len(args) == 1:
            commands.cmd_favorites(data)
            return
        if len(args) == 2 and args[1].lower() == "help":
            print_favorites_help()
            return
        print("Unrecognized `job favorites` arguments. Usage: job favorites")
        return

    dispatch_company(data, args[0], args[1:])
