# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`job-cli` — a single-file, zero-dependency Python 3 CLI (`job.py`) for tracking job applications: company, title, dates, status, and interviews, invoked as `job` via a bash alias. See `README.md` for the full user-facing command reference.

## Commands

```bash
# Dev setup (optional — job.py itself has zero runtime dependencies)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Run the full test suite with the branch-coverage gate
coverage run -m pytest
coverage report -m          # fails if branch coverage drops below 90% (.coveragerc)

# Run a single test file / single test
pytest tests/test_note.py
pytest tests/test_note.py::test_clear_note -v
```

There is no build step, linter, formatter, or type checker configured in this repo — `job.py` is plain stdlib Python with no tooling beyond pytest/coverage.

**Never run `python3 job.py ...` directly** to smoke-test a change — see "Never touch real production data" below for the safe way to do this.

## Never touch real production data

`data/applications.json` (gitignored) is the user's **real, personal job-search data** — never a fixture, never disposable. Treat it as off-limits for any ad hoc/manual command.

`job.py`'s data-path resolution checks for this legacy in-repo path *before* anything else:

```python
if os.path.exists(_LEGACY_DATA_FILE):
    # Pre-existing checkouts keep using their in-repo data file untouched.
    DATA_DIR = _LEGACY_DATA_DIR
    DATA_FILE = _LEGACY_DATA_FILE
else:
    DATA_DIR = _XDG_DATA_DIR
    DATA_FILE = os.path.join(DATA_DIR, "applications.json")
```

This check wins **even if `XDG_DATA_HOME`/`XDG_CONFIG_HOME` env vars are set** before running `python3 job.py ...` — since the file already exists in this checkout, every direct invocation silently reads and writes the real file. Setting the env var and running the script as a subprocess is **not sufficient isolation**.

### Safe way to smoke-test manually

Never run `python3 job.py ...` directly from a shell to smoke-test a change. Instead, monkeypatch the already-resolved module-level variables *after* import — this bypasses the legacy-path check entirely, since it overrides the result rather than the input:

```python
import sys, job
job.DATA_DIR = "/tmp/scratch/data"
job.DATA_FILE = "/tmp/scratch/data/applications.json"
job._XDG_CONFIG_DIR = "/tmp/scratch/config"
job.CONFIG_FILE = "/tmp/scratch/config/config.json"
sys.argv = ["job", "SomeCorp", "Data Engineer"]
job.main()
```

### The automated test suite is already safe

`tests/conftest.py` has autouse fixtures (`isolate_data_file`, `isolate_config_file`) that redirect `job.DATA_DIR`/`DATA_FILE`/`CONFIG_FILE` to a fresh pytest `tmp_path` for *every single test* — `pytest` never touches the real data/config files. This rule is about **manual/ad hoc CLI invocations only**, not the test suite.

## Architecture

Single file, no packages: everything lives in `job.py` (~1,700 lines). Roughly top to bottom:

- **Storage & migration** — `load_data`/`save_data`; `needs_migration`/`migrate_legacy_data` transparently upgrades the pre-soft-delete schema on load; `needs_tz_backfill`/`backfill_interview_tz` re-normalizes stored interview timestamps whenever the configured default timezone changes. Config (currently just the default timezone) lives in its own file, separate from application data (`load_config`/`save_config`, `get_default_tz`/`set_default_tz`), so wiping one never affects the other.
- **Company resolution** — `normalize()` + `score()` (stdlib `difflib`-based fuzzy matching) + `resolve_company_key`/`resolve_active` is the shared engine behind lookup, `status`, `delete`, `note`, `--favorite`, `--rename`, create's duplicate-detection, and the company-classified branch of `search`. Any command that targets "a company" funnels through this rather than reimplementing matching, and shares the same auto-accept / confirm-prompt / no-match thresholds (`AUTO_THRESHOLD`, `CONFIRM_THRESHOLD`).
- **Interview date/time parsing** — `split_interview_tokens` → `parse_interview_date_token`/`parse_interview_time_token`/`resolve_tz_token` → `parse_interview_datetime`, backed by the `TZ_ALIASES` table. Accepts flexible shorthand (`7/13 3pm`, `2026-07-13 13:00 CT`, ...) and always confirms interactively before saving (`confirm_meridiem` for ambiguous bare hours, a final "Set X's interview to..." confirmation).
- **Command handlers** — one `cmd_*` function per subcommand (`cmd_create`, `cmd_status`, `cmd_delete`, `cmd_rename`, `cmd_interview`, `cmd_list`, `cmd_search`, `cmd_favorites`, ...), each taking the already-loaded `data` dict and mutating + saving it.
- **Dispatch** — `dispatch_company` + `main()` parse `sys.argv` positionally by argument count plus a set of reserved first/second-argument keywords (`list`, `search`, `status`, `delete`, `interview`, `note`, `tz`, `--all`, `--hard`, `--rename`, `--favorite`, ...). There's no argument-parsing library involved; the exact precedence rules (e.g. why `job list foo` never falls through to creating a company named "list") are spelled out in `product.md`'s "Argument grammar" section.
- **Table rendering & TUI** — `build_table_lines`/`print_table` build plain-text tables; row highlighting (`classify_interview_color`/`colorize`/`ROW_HIGHLIGHTS`) is gated on `sys.stdout.isatty()`. When a table is wider than the terminal and both stdout/stdin are TTYs, `scroll_table_interactive` takes over with a raw-mode (`termios`/`tty`), alternate-screen-buffer scrolling widget with independent horizontal/vertical scroll state — this function is marked `# pragma: no cover` and is tested only manually (see Testing).

**Data model**: records are keyed by a generated id (`uuid4().hex[:8]`), not by company name, because a company can accumulate soft-deleted history over multiple application attempts — deleting a record sets `deleted`/`deleted_at` rather than removing it, and at most one *active* record per company is enforced at create/rename time via the resolution engine above.

`product.md` (gitignored, present only in local checkouts, not part of a fresh clone) is the authoritative PRD — every command's exact argument grammar, edge cases, and the reasoning behind them is spelled out there in more detail than is worth duplicating here. Consult it when a dispatch or parsing edge case isn't obvious from `job.py` alone.

## Testing

- A large suite (390+ tests) under `tests/`, split by feature area (`test_create.py`, `test_delete.py`, `test_interview_parsing.py`, `test_dispatch_and_main.py`, ...), with shared fixtures in `tests/conftest.py`.
- Data and config isolation is automatic: autouse fixtures redirect `job.DATA_DIR`/`DATA_FILE`/`CONFIG_FILE` to a fresh `tmp_path` for every test, and pre-seed a default timezone (CT) so most tests don't need to know about the first-run timezone-setup prompt.
- Useful fixtures: `run_cli` (drives `main()` via a monkeypatched `sys.argv`, returns captured stdout — the primary test seam), `stub_confirm`/`stub_meridiem` (bypass interactive y/n and AM/PM prompts), `answer_input`/`eof_input` (script `input()` directly, for tests about prompt text/ordering itself), `freeze_date`/`freeze_now` (pin "today"/"now"), `term_size`, `tty` (pin terminal size / isatty results).
- Coverage: `branch = True`, `fail_under = 90` in `.coveragerc`. `scroll_table_interactive` (the raw-terminal scroll widget) is excluded via `# pragma: no cover` since faking a live raw-mode tty in a test runner isn't practical — verify it manually if you change it.
