#!/usr/bin/env python3
"""Regenerates README.md's colored terminal demo (assets/demo.svg plus the
plain-text fallback) by driving the real CLI against frozen, isolated
scratch storage. Running this script is the entire regeneration workflow.

Requires `rich` (see requirements-dev.txt) -- not a job/ runtime dependency.
"""
import contextlib
import io
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import job  # noqa: E402

from rich.ansi import AnsiDecoder  # noqa: E402
from rich.console import Console  # noqa: E402

ASSET_PATH = REPO_ROOT / "assets" / "demo.svg"
README_PATH = REPO_ROOT / "README.md"
START_MARKER = "<!-- DEMO:START -->"
END_MARKER = "<!-- DEMO:END -->"

NY = ZoneInfo("America/New_York")
FROZEN_TODAY = date(2026, 7, 16)
FROZEN_NOW = datetime(2026, 7, 16, 9, 0, tzinfo=NY)

# (prompt text, argv) -- one continuous captured terminal session.
COMMANDS = [
    ('job "Big Corp" "Data Engineer"', ["job", "Big Corp", "Data Engineer"]),
    ('job "big corp"', ["job", "big corp"]),
    ('job "big corp" "Product Manager - Data"', ["job", "big corp", "Product Manager - Data"]),
    ('job "Big Corp" note "Referred by a friend on the team"',
     ["job", "Big Corp", "note", "Referred by a friend on the team"]),
    ("job list", ["job", "list"]),
    ('job "big corp" interview 7/20 9am ET', ["job", "big corp", "interview", "7/20", "9am", "ET"]),
    ("job interviews", ["job", "interviews"]),
    ('job "Big Corp5" delete', ["job", "Big Corp5", "delete"]),
    ("job list --all", ["job", "list", "--all"]),
]

# Hidden seed rows (created directly, bypassing cmd_create) so `job list`/
# `job interviews` have pre-existing history with backdated applied/
# status-changed dates -- exactly like the old README's un-created rows.
# interview=None means no interview; otherwise a tz-aware datetime.
SEED_RECORDS = [
    # company,     applied,      status,      status_changed, interview
    ("Big Corp2", "2026-07-10", "whatever",  "2026-07-12", datetime(2026, 7, 14, 10, 0, tzinfo=NY)),  # past -> yellow
    ("Big Corp3", "2026-07-11", "status",    "2026-07-13", datetime(2026, 7, 16, 11, 0, tzinfo=NY)),  # today -> blue
    ("Big Corp4", "2026-07-12", "you want",  "2026-07-14", datetime(2026, 7, 17, 15, 0, tzinfo=NY)),  # future -> green
    ("Big Corp5", "2026-07-16", "sent app",  "2026-07-16", None),  # soft-deleted live -> red
    ("Big Corp6", "2026-07-16", "sent app",  "2026-07-16", None),
    ("Big Corp7", "2026-07-16", "sent app",  "2026-07-16", None),
]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def freeze_time():
    """Mirrors tests/conftest.py's freeze_date/freeze_now fixtures: patches
    date.today() in job.commands/job.interview/job.display, and
    datetime.now() in job.display (its only call site)."""
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return FROZEN_TODAY

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_NOW

    job.commands.date = FrozenDate
    job.interview.date = FrozenDate
    job.display.date = FrozenDate
    job.display.datetime = FrozenDateTime


def isolate_storage():
    """CLAUDE.md's mandatory safe-smoke-test pattern: monkeypatch the
    already-resolved module-level path variables after import, since this
    script is itself a manual invocation and must never touch real data."""
    scratch = Path(tempfile.mkdtemp(prefix="job-cli-demo-"))
    job.storage.DATA_DIR = str(scratch / "data")
    job.storage.DATA_FILE = str(scratch / "data" / "applications.json")
    job.storage._XDG_CONFIG_DIR = str(scratch / "config")
    job.storage.CONFIG_FILE = str(scratch / "config" / "config.json")
    assert str(REPO_ROOT) not in job.storage.DATA_FILE, \
        "refusing to run: storage isolation did not take effect"
    # Every confirm() prompt in this narrative should be accepted (interview-set,
    # delete) *except* the fuzzy "Did you mean 'Big CorpN'?" suggestion that fires
    # when creating "Big Corp" itself -- the seeded Big Corp2..7 rows are similar
    # enough that company.score() flags them as likely typos of "Big Corp", and a
    # real user would decline that suggestion to create a genuinely new company.
    job.company.confirm = lambda prompt: not prompt.startswith("Did you mean")
    job.storage.set_default_tz("ET")


def seed_data():
    data = job.storage.load_data()
    for company, applied, status, status_changed, interview_dt in SEED_RECORDS:
        key = job.storage.new_id(data)
        data[key] = {
            "id": key,
            "company": company,
            "title": "Data Engineer",
            "applied": applied,
            "interview": None if interview_dt is None else interview_dt.isoformat(),
            "interview_tz": None if interview_dt is None else "ET",
            "status": status,
            "status_changed": status_changed,
            "note": None,
            "is_favorite": False,
            "deleted": False,
            "deleted_at": None,
        }
    job.storage.save_data(data)


def capture_transcript():
    """Drives every command in COMMANDS through one continuous redirected
    stdout buffer (not per-command captures stitched together), so the
    result is a single coherent terminal session with one piece of chrome."""
    buf = io.StringIO()
    buf.isatty = lambda: True  # print_table's color path is gated on this
    sys.stdin.isatty = lambda: False  # belt-and-suspenders: never take the interactive scroll branch
    job.display.shutil.get_terminal_size = lambda fallback=(80, 24): os.terminal_size((200, 50))

    with contextlib.redirect_stdout(buf):
        for i, (prompt_text, argv) in enumerate(COMMANDS):
            if i:
                print()
            print(f"$ {prompt_text}")
            job.dispatch.sys.argv = argv
            job.dispatch.main()
        print()  # trailing blank line before the closing fence

    full_text = buf.getvalue()
    plain_text = ANSI_RE.sub("", full_text)
    return full_text, plain_text


def render_svg(full_text, plain_text):
    width = max(len(line) for line in plain_text.splitlines())
    console = Console(record=True, width=width, color_system="truecolor")
    for text in AnsiDecoder().decode(full_text):
        console.print(text)
    ASSET_PATH.parent.mkdir(exist_ok=True)
    console.save_svg(str(ASSET_PATH), title="")


def update_readme(plain_text):
    readme = README_PATH.read_text()
    if START_MARKER not in readme or END_MARKER not in readme:
        raise SystemExit(
            f"README.md is missing {START_MARKER}/{END_MARKER} -- add the marker pair once, manually."
        )
    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER)
    body = (
        "\n\n"
        "![job-cli demo: creating and tracking applications, with color-coded "
        "interview rows (overdue/today/upcoming) and a soft-deleted record view]"
        "(assets/demo.svg)\n\n"
        "<details>\n<summary>Plain-text transcript (no color)</summary>\n\n"
        "```\n" + plain_text + "```\n\n"
        "</details>\n\n"
    )
    README_PATH.write_text(readme[:start] + body + readme[end:])


def main():
    isolate_storage()
    freeze_time()
    seed_data()
    full_text, plain_text = capture_transcript()
    render_svg(full_text, plain_text)
    update_readme(plain_text)
    print(f"Wrote {ASSET_PATH.relative_to(REPO_ROOT)} and updated README.md")


if __name__ == "__main__":
    main()
