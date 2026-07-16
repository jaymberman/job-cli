# job-cli

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#requirements)
[![Platform: Linux | macOS](https://img.shields.io/badge/platform-linux%20%7C%20macos-lightgrey.svg)](#requirements)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](requirements.txt)

A fast, zero-dependency command-line tool for tracking the jobs you've applied to — company, title, dates, status, and interviews — without resorting to a spreadsheet.

```
$ job "Big Corp" "Data Engineer"
Created record for Big Corp.

$ job "big corp"
Company        Title           Applied      Interview  Status Changed  Status
Big Corp       Data Engineer   2026-07-16   —          2026-07-16      sent app
```

## Features

- **One record per company, forever** — create, look up, and update with a single short command from any shell prompt.
- **Typo-tolerant** — company names are matched case-insensitively and fuzzily (`aretum`, `aretumconsulting`, and `aretum consulzing` all resolve to "Aretum Consulting"), with a confirmation prompt whenever a match is uncertain.
- **Soft delete by default** — deleting a record hides it from everyday views but keeps its history, so reapplying to a company you were once declined by doesn't erase the past. `delete --hard` is there when you really want something gone.
- **Freeform status** — status is just text. No enum to fight with.
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

`install.sh` adds a `job` alias to `~/.bash_aliases` pointing at this checkout's `job.py` — no `PATH` symlink, no `chmod +x` needed, and no elevated permissions required. Re-running it (e.g. after moving the checkout) safely updates the existing alias instead of adding a duplicate.

You're now set up — try `job help` to see the full command list.

### Forking / local development

```bash
git clone https://github.com/<you>/job-cli.git
cd job-cli
python3 -m venv .venv
source .venv/bin/activate
```

There's nothing to `pip install` today — `job.py` is pure standard library — so the virtual environment above is optional hygiene: it just keeps your working copy isolated in case that ever changes. Run your changes directly with:

```bash
python3 job.py <args>
```

## Usage

Company names, titles, and statuses are each passed as a single shell argument — quote any value that contains spaces.

| Command | Example | Description |
|---|---|---|
| Look up a company | `job "Big Corp"` | Shows the active record (or `no applications sent`) |
| Look up, including history | `job "Big Corp" --all` | Also shows soft-deleted records for that company |
| Create a record | `job "Big Corp" "Data Engineer"` | Applied date and status (`sent app`) are set automatically |
| Create with a custom status | `job "Big Corp" "Data Engineer" "Recruiter reached out"` | Same as above, with your own initial status |
| Update status | `job "Big Corp" status "Interviewing"` | Also updates the status-changed date |
| Schedule an interview | `job "Big Corp" interview 2026-07-13 13:00 CT` | Flexible date/time formats; always confirms before saving |
| Schedule with `tz` keyword | `job "Big Corp" interview 1/1/2027 9pm tz ET` | Same as above; `tz <ZONE>` is an explicit alternative to a bare trailing zone |
| Cancel an interview | `job "Big Corp" interview cancel` | Clears the scheduled interview, no confirmation needed |
| Soft-delete | `job "Big Corp" delete` | Hides the record from normal views; history is kept (asks to confirm) |
| Permanently delete | `job "Big Corp" delete --hard` | Irreversible; targets soft-deleted history if there's no active record (asks to confirm) |
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

Application records live in `data/applications.json` inside this checkout, in plain JSON. That file is listed in `.gitignore` — it's never committed, so cloning or forking this repo never exposes what you're tracking, and nothing is ever sent anywhere else.

## License

[MIT](LICENSE)
