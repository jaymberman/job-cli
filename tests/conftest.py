import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import job
from datetime import date, datetime


@pytest.fixture(autouse=True)
def isolate_data_file(tmp_path, monkeypatch):
    """Every test gets its own scratch data dir -- the real
    data/applications.json is never touched, even if a test crashes."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(job, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(job, "DATA_FILE", str(data_dir / "applications.json"))


@pytest.fixture
def freeze_date(monkeypatch):
    """freeze_date(2026, 7, 16) makes job.date.today() return that date,
    while job.date(...) construction and all other `date` behavior stays
    real (FrozenDate is a plain subclass)."""
    def _freeze(year, month, day):
        fixed = date(year, month, day)

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return fixed

        monkeypatch.setattr(job, "date", FrozenDate)
        return fixed
    return _freeze


@pytest.fixture
def freeze_now(monkeypatch):
    """freeze_now(some_aware_datetime) makes job.datetime.now() return that
    instant. Comparisons of aware datetimes are instant-based regardless of
    what local zone .astimezone() later relabels them with, so this is safe
    independent of the host machine's configured timezone."""
    def _freeze(aware_dt):
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return aware_dt

        monkeypatch.setattr(job, "datetime", FrozenDateTime)
        return aware_dt
    return _freeze


@pytest.fixture
def stub_confirm(monkeypatch):
    """stub_confirm(True) or stub_confirm(False) makes every job.confirm()
    call resolve without touching input(); use answer_input instead for
    tests specifically about the y/n prompt-parsing logic itself."""
    def _set(value=True):
        monkeypatch.setattr(job, "confirm", lambda prompt: value)
    return _set


@pytest.fixture
def stub_meridiem(monkeypatch):
    """stub_meridiem('am') / ('pm') / (None) makes every
    job.confirm_meridiem() call resolve without touching input()."""
    def _set(value):
        monkeypatch.setattr(job, "confirm_meridiem", lambda hour, minute: value)
    return _set


@pytest.fixture
def answer_input(monkeypatch):
    """Feeds a fixed queue of canned answers to input(). Raises if a test
    calls input() more times than it supplied answers for, so a test can't
    silently pass by relying on default EOFError behavior it didn't intend."""
    def _set(*answers):
        it = iter(answers)

        def fake_input(prompt=""):
            try:
                return next(it)
            except StopIteration:
                raise AssertionError(
                    f"input() called with no canned answer left; prompt was: {prompt!r}"
                )

        monkeypatch.setattr("builtins.input", fake_input)
    return _set


@pytest.fixture
def eof_input(monkeypatch):
    """Makes input() raise EOFError, as it would on a closed/redirected stdin."""
    def fake_input(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", fake_input)


@pytest.fixture
def term_size(monkeypatch):
    """Pins shutil.get_terminal_size()'s result so table-width/scroll-dispatch
    logic doesn't depend on the actual terminal running the test suite."""
    def _set(columns, lines=24):
        monkeypatch.setattr(
            job.shutil, "get_terminal_size",
            lambda fallback=(80, 24): os.terminal_size((columns, lines)),
        )
    return _set


@pytest.fixture
def tty(monkeypatch):
    """tty(stdout=True, stdin=True) makes sys.stdout/stdin.isatty() report
    the given values, independent of however pytest is actually capturing
    output for this run."""
    def _set(stdout=True, stdin=True):
        monkeypatch.setattr(job.sys.stdout, "isatty", lambda: stdout, raising=False)
        monkeypatch.setattr(job.sys.stdin, "isatty", lambda: stdin, raising=False)
    return _set


@pytest.fixture
def run_cli(monkeypatch, capsys):
    """Drives the CLI the way a real invocation would: sets sys.argv, calls
    job.main(), and returns captured stdout."""
    def _run(*argv):
        monkeypatch.setattr(job.sys, "argv", ["job"] + list(argv))
        job.main()
        return capsys.readouterr().out
    return _run
