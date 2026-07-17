from datetime import date, datetime

from . import storage
from . import company as company_mod
from . import interview
from . import display as display_mod


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
