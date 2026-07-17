# job-cli

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#requirements)
[![Platform: Linux | macOS](https://img.shields.io/badge/platform-linux%20%7C%20macos-lightgrey.svg)](#requirements)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](requirements.txt)

🚀🚀🚀 A fast, zero-dependency command-line tool for tracking the jobs you've applied to — company, title, dates, status — and scheduling interviews — without resorting to a spreadsheet.

<div align="center">
  <kbd>
    <i>"Ugh, I have so many applications and interviews to track, but I'm not a phone calendar guy!"</i>
    <br>
    <i>- The guy who made this cli</i>
    <br><br>
  </kbd>
</div>

```
$ job "Big Corp" "Data Engineer"
Created record for Big Corp.

$ job "big corp"
Company        Title           Applied      Interview  Status Changed  Status    Note
Big Corp       Data Engineer   2026-07-16   —          2026-07-16      sent app  —

$ job "big corp" "Product Manager - Data"
Big Corp already has a record

$ job "Big Corp" note "Referred by a friend on the team"
Updated Big Corp's note:
Company: Big Corp
Title: Data Engineer
Applied: 2026-07-16
Interview: —
Status: sent app
Status changed: 2026-07-16
Note: Referred by a friend on the team

$ job list
Company        Title           Applied      Interview             Status Changed  Status    Note
Big Corp       Data Engineer   2026-07-16   —                     2026-07-16      sent app  Referred by a friend on the team
Big Corp5      Data Engineer   2026-07-16   —                     2026-07-16      sent app  —
Big Corp6      Data Engineer   2026-07-16   —                     2026-07-16      sent app  —
Big Corp7      Data Engineer   2026-07-16   —                     2026-07-16      sent app  —
Big Corp2      Data Engineer   2026-07-10   2026-07-17 10:00 ET   2026-07-12      whatever  —
Big Corp3      Data Engineer   2026-07-11   2026-07-17 11:00 ET   2026-07-13      status    —
Big Corp4      Data Engineer   2026-07-12   2026-07-17 15:00 ET   2026-07-14      you want  —

$ job "big corp" interview 7/20 9am ET

$ job interviews
Company        Title           Applied      Interview             Status Changed  Status    Note
Big Corp       Data Engineer   2026-07-16   2026-07-20 09:00 ET   2026-07-16      sent app  Referred by a friend on the team
Big Corp2      Data Engineer   2026-07-10   2026-07-17 10:00 ET   2026-07-12      whatever  —
Big Corp3      Data Engineer   2026-07-11   2026-07-17 11:00 ET   2026-07-13      status    —
Big Corp4      Data Engineer   2026-07-12   2026-07-17 15:00 ET   2026-07-14      you want  —

```

## Features

- **One record per company, forever** — create, look up, and update with a single short command from any shell prompt.
- **Typo-tolerant** — company names are matched case-insensitively and fuzzily (`BigCorp`, `BigCorpconsulting`, and `BigCorp consulzing` all resolve to "BigCorp Consulting"), with a confirmation prompt whenever a match is uncertain.
- **Soft delete by default** — deleting a record hides it from everyday views but keeps its history, so reapplying to a company you were once declined by doesn't erase the past. `delete --hard` is there when you really want something gone.
- **Freeform status** — status is just text. No enum to fight with.
- **Notes on every record** — attach freeform context to any record, shown wherever that record is returned; edit or clear it any time, with no history of past edits.
- **Favorites** — mark arbitrarily many active applications as favorites (`job <company> --favorite`) and pull them up in one place with `job favorites`. Applies instantly, no confirmation, and is never shown as a column or highlight anywhere else. Deleting a record clears its favorite status.
- **Rename a company** — fix a typo or update a company's name (`job <company> --rename <new_name>`) without losing its status, note, favorite, interview, or declined history. Cascades to any soft-deleted records sharing the old name; blocked if the new name already has an active record, confirms if it only has soft-deleted history there.
- **Interview scheduling with real timezone handling** — type interview times in whatever shorthand you'd naturally use (`2026-07-13 13:00 CT`, `1/1/2027 9pm ET`, `7/13 3pm`); ambiguous hours are always confirmed, never guessed.
- **Color-coded, scrollable tables** — interview rows are highlighted (blue = today, green = future, yellow = past, red = soft-deleted), and tables wider or taller than your terminal scroll in place instead of wrapping.
- **Search across everything** — one fuzzy keyword against company, title, or status.
- **Your data stays yours** — everything lives in a local JSON file that's gitignored by default (see [Your data](#your-data)).

## Requirements

- Linux or macOS (or WSL on Windows) — the interactive scrolling table uses POSIX terminal APIs (`termios`/`tty`) and has no native Windows support.
- Python 3.9 or newer (for `zoneinfo`).
- No third-party packages — see [`requirements.txt`](requirements.txt).

## Installation

Install from source:

```bash
git clone https://github.com/jaymberman/job-cli.git
cd job-cli
./install.sh
source ~/.bash_aliases   # or just open a new shell
```

`install.sh` adds a `job` alias to `~/.bash_aliases` that runs `python3 -m job` with `PYTHONPATH` set to this checkout — no `PATH` symlink, no `chmod +x` needed, and no elevated permissions required. Re-running it (e.g. after moving the checkout) safely updates the existing alias instead of adding a duplicate.

You're now set up — try `job help` to see the full command list.

### Forking / local development

```bash
git clone https://github.com/<you>/job-cli.git
cd job-cli
python3 -m venv .venv
source .venv/bin/activate
```

There's nothing to `pip install` today — the `job` package is pure standard library — so the virtual environment above is optional hygiene: it just keeps your working copy isolated in case that ever changes. Run your changes directly with:

```bash
python3 -m job <args>
```

### Running tests

The test suite (pytest) and coverage tooling are dev-only dependencies, kept out of `requirements.txt` so that file stays an accurate zero-dependency signal for the shipped tool:

```bash
pip install -r requirements-dev.txt
coverage run -m pytest
coverage report -m
```

`.coveragerc` enforces a 90% branch-coverage gate (`coverage report` exits non-zero below it). Tests never touch your real `data/applications.json` — every test runs against an isolated scratch data file. The one deliberate gap is the raw-mode interactive scroll widget (`scroll_table_interactive`, used for tables wider than your terminal), which is excluded from coverage and verified manually, since faking a live terminal in a test runner isn't practical.

## Usage

Company names, titles, statuses, and notes are each passed as a single shell argument — quote any value that contains spaces.

| Command | Example | Description |
|---|---|---|
| Look up a company | `job "Big Corp"` | Shows the active record (or `no applications sent`) |
| Look up, including history | `job "Big Corp" --all` | Also shows soft-deleted records for that company |
| Create a record | `job "Big Corp" "Data Engineer"` | Applied date and status (`sent app`) are set automatically; note starts out unset |
| Create with a custom status | `job "Big Corp" "Data Engineer" "Recruiter reached out"` | Same as above, with your own initial status |
| Update status | `job "Big Corp" status "Interviewing"` | Also updates the status-changed date |
| Set or edit a note | `job "Big Corp" note "Referred by a friend"` | Applies immediately, no confirmation; shown wherever the record is returned |
| Clear a note | `job "Big Corp" note clear` | Resets the note back to unset |
| Schedule an interview | `job "Big Corp" interview 2026-07-13 13:00 CT` | Flexible date/time formats; always confirms before saving |
| Schedule with `tz` keyword | `job "Big Corp" interview 1/1/2027 9pm tz ET` | Same as above; `tz <ZONE>` is an explicit alternative to a bare trailing zone |
| Cancel an interview | `job "Big Corp" interview cancel` | Clears the scheduled interview, no confirmation needed |
| Soft-delete | `job "Big Corp" delete` | Hides the record from normal views; history is kept (asks to confirm) |
| Permanently delete | `job "Big Corp" delete --hard` | Irreversible; targets soft-deleted history if there's no active record (asks to confirm) |
| Mark a favorite | `job "Big Corp" --favorite` | Applies immediately, no confirmation; cleared automatically on delete |
| Remove a favorite | `job "Big Corp" --remove-favorite` | Applies immediately, no confirmation |
| Rename a company | `job "Big Corp" --rename "Big Corp Inc"` | Also renames any soft-deleted history sharing the old name; blocked if the new name already has an active record, confirms if it only has soft-deleted history |
| List favorites | `job favorites` | Every favorited active record, sorted by company name (A-Z); favorite status is never shown as a column anywhere |
| List everything | `job list` | Sorted by company name (A-Z) by default |
| List, sorted | `job list sort status-changed desc` | Valid fields: `company`, `title`, `applied`, `status`, `status-changed` |
| List, including history | `job list --all` | Adds a trailing Deleted column |
| Search | `job search "Data Engineer"` | Fuzzy-matches company, title, or status; same table format as `list` |
| Search, sorted | `job search "Data Engineer" sort title asc` | Same `sort` options as `list` |
| Upcoming interviews | `job interviews` | Future interviews, plus anything within the last 30 minutes |
| All interviews | `job interviews --all` | Includes past interviews and soft-deleted records |
| Today's activity | `job today` | Anything applied, status-changed, or interviewing today |
| View in another timezone | `job list tz PT` | Converts only the displayed Interview column; storage is untouched |
| Force company interpretation | `job --company list "Data Engineer"` | Looks up/creates a company literally named `list` (or any other reserved word) |
| Help | `job help`, `job list help`, `job search help` | Command-specific usage |

`--all`, `tz <ZONE>`, and (for `list`/`search`) `sort <field> [asc|desc]` can be combined in any order. Run `job help` at any time for the full, authoritative usage text straight from the tool itself.

## Your data

Application records live in `~/.local/share/job-cli/applications.json` (or `$XDG_DATA_HOME/job-cli/applications.json` if you've set that), in plain JSON. This is a fixed per-user location, so `job` reads and writes the same data no matter what directory you run it from. Nothing is ever sent anywhere else.

If `data/applications.json` already exists inside this checkout (from before this change, or from an existing installation), it's used instead — so upgrading in place never orphans your existing records. That path is listed in `.gitignore` and never committed.

## License

[MIT](LICENSE)
