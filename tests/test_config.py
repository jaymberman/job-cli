import json

import job


def read_data():
    with open(job.storage.DATA_FILE) as f:
        return json.load(f)


def interview_record(company="Big Corp", interview="2026-07-17T11:00:00-04:00", interview_tz="ET"):
    rec = {
        "id": "abc12345",
        "company": company,
        "title": "Data Engineer",
        "applied": "2026-01-01",
        "interview": interview,
        "interview_tz": interview_tz,
        "status": "sent app",
        "status_changed": "2026-01-01",
        "deleted": False,
        "deleted_at": None,
    }
    return rec


# ---- load_config / save_config / get_default_tz / set_default_tz ----------

def test_load_config_returns_empty_dict_when_unconfigured(clear_default_tz):
    clear_default_tz()
    assert job.storage.load_config() == {}


def test_get_default_tz_none_when_unconfigured(clear_default_tz):
    clear_default_tz()
    assert job.storage.get_default_tz() == (None, None)


def test_get_default_tz_returns_configured_zone():
    # autouse isolate_config_file fixture pre-seeds CT
    assert job.storage.get_default_tz() == ("America/Chicago", "CT")


def test_set_default_tz_persists_across_loads():
    job.storage.set_default_tz("ET")
    assert job.storage.get_default_tz() == ("America/New_York", "ET")
    # Round-trips through a fresh read of the file, not just an in-memory value.
    assert job.storage.load_config()["default_tz"] == "ET"


# ---- resolve_or_prompt_default_tz ------------------------------------------

def test_resolve_or_prompt_returns_configured_value_without_touching_input(monkeypatch):
    def explode(prompt=""):
        raise AssertionError("input() should never be called when already configured")
    monkeypatch.setattr("builtins.input", explode)
    assert job._legacy.resolve_or_prompt_default_tz() == ("America/Chicago", "CT")


def test_resolve_or_prompt_asks_and_persists_when_unconfigured(clear_default_tz, tty, answer_input, capsys):
    clear_default_tz()
    tty(stdin=True)
    answer_input("ET")
    result = job._legacy.resolve_or_prompt_default_tz()
    assert result == ("America/New_York", "ET")
    assert job.storage.get_default_tz() == ("America/New_York", "ET")
    assert "Default timezone set to ET." in capsys.readouterr().out


def test_resolve_or_prompt_shows_the_setup_prompt_text(clear_default_tz, tty, monkeypatch):
    # answer_input's fake input() doesn't echo its prompt argument (that's
    # the real input() builtin's job, not something print() emits) -- to
    # check the actual prompt wording, capture the argument input() was
    # called with directly, the same way other tests capture confirm()'s
    # prompt via a lambda instead of stubbing it away.
    clear_default_tz()
    tty(stdin=True)
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return "ET"
    monkeypatch.setattr("builtins.input", fake_input)

    job._legacy.resolve_or_prompt_default_tz()
    assert prompts == ["You haven't set a default timezone yet. Enter one "
                        "(CT/ET/MT/PT/UTC, or a synonym): "]


def test_resolve_or_prompt_accepts_synonym_and_stores_short_label(clear_default_tz, tty, answer_input):
    clear_default_tz()
    tty(stdin=True)
    answer_input("EASTERN")
    assert job._legacy.resolve_or_prompt_default_tz() == ("America/New_York", "ET")
    assert job.storage.get_default_tz() == ("America/New_York", "ET")


def test_resolve_or_prompt_blank_answer_cancels_without_persisting(clear_default_tz, tty, answer_input, capsys):
    clear_default_tz()
    tty(stdin=True)
    answer_input("")
    assert job._legacy.resolve_or_prompt_default_tz() == (None, None)
    assert job.storage.get_default_tz() == (None, None)
    assert "Cancelled." in capsys.readouterr().out


def test_resolve_or_prompt_eof_cancels_without_persisting(clear_default_tz, tty, eof_input, capsys):
    clear_default_tz()
    tty(stdin=True)
    assert job._legacy.resolve_or_prompt_default_tz() == (None, None)
    assert job.storage.get_default_tz() == (None, None)
    assert "Cancelled." in capsys.readouterr().out


def test_resolve_or_prompt_unrecognized_answer_cancels_without_persisting(clear_default_tz, tty, answer_input, capsys):
    clear_default_tz()
    tty(stdin=True)
    answer_input("XX")
    assert job._legacy.resolve_or_prompt_default_tz() == (None, None)
    assert job.storage.get_default_tz() == (None, None)
    assert "Unknown timezone 'XX'" in capsys.readouterr().out


def test_resolve_or_prompt_non_interactive_errors_without_prompting(clear_default_tz, tty, monkeypatch):
    clear_default_tz()
    tty(stdin=False)

    def explode(prompt=""):
        raise AssertionError("must not call input() when stdin isn't a TTY")
    monkeypatch.setattr("builtins.input", explode)

    result = job._legacy.resolve_or_prompt_default_tz()
    assert result == (None, None)
    assert job.storage.get_default_tz() == (None, None)


def test_resolve_or_prompt_non_interactive_message_names_the_config_command(clear_default_tz, tty, capsys):
    clear_default_tz()
    tty(stdin=False)
    job._legacy.resolve_or_prompt_default_tz()
    out = capsys.readouterr().out
    assert "No default timezone is configured yet." in out
    assert "job config tz" in out


# ---- needs_tz_backfill skips silently when unconfigured --------------------

def test_needs_tz_backfill_false_when_unconfigured_even_with_stale_record(clear_default_tz):
    clear_default_tz()
    assert job.storage.needs_tz_backfill({"abc12345": interview_record()}) is False


def test_load_data_does_not_prompt_or_backfill_when_unconfigured(clear_default_tz, monkeypatch):
    clear_default_tz()
    rec = interview_record()
    job.storage.save_data({rec["id"]: rec})

    def explode(prompt=""):
        raise AssertionError("load_data() must never prompt just to load")
    monkeypatch.setattr("builtins.input", explode)

    loaded = job.storage.load_data()
    (out,) = loaded.values()
    assert out["interview_tz"] == "ET"  # untouched -- no backfill target known


# ---- cmd_config_tz_show -----------------------------------------------------

def test_cmd_config_tz_show_prints_configured_default(capsys):
    job._legacy.cmd_config_tz_show()
    assert "Default timezone: CT" in capsys.readouterr().out


def test_cmd_config_tz_show_prints_not_set_when_unconfigured(clear_default_tz, capsys):
    clear_default_tz()
    job._legacy.cmd_config_tz_show()
    out = capsys.readouterr().out
    assert "not set yet" in out
    assert "job config tz <ZONE>" in out


# ---- cmd_config_tz_set ------------------------------------------------------

def test_cmd_config_tz_set_unknown_zone_errors_and_leaves_config_unchanged(capsys):
    job._legacy.cmd_config_tz_set({}, "XX")
    assert "Unknown timezone 'XX'" in capsys.readouterr().out
    assert job.storage.get_default_tz() == ("America/Chicago", "CT")


def test_cmd_config_tz_set_same_as_current_is_a_noop_no_confirm(monkeypatch, capsys):
    def explode(prompt):
        raise AssertionError("must not confirm when the value is unchanged")
    monkeypatch.setattr(job.company, "confirm", explode)
    job._legacy.cmd_config_tz_set({}, "CT")
    assert "Default timezone is already CT." in capsys.readouterr().out


def test_cmd_config_tz_set_first_time_no_interviews(clear_default_tz, monkeypatch, capsys):
    clear_default_tz()
    prompts = []
    monkeypatch.setattr(job.company, "confirm", lambda prompt: prompts.append(prompt) or True)
    job._legacy.cmd_config_tz_set({}, "PT")
    assert prompts == ["Set default timezone to PT?"]
    out = capsys.readouterr().out
    assert "Default timezone set to PT." in out
    assert "Converted" not in out
    assert job.storage.get_default_tz() == ("America/Los_Angeles", "PT")


def test_cmd_config_tz_set_changes_existing_default_no_interviews(monkeypatch, capsys):
    prompts = []
    monkeypatch.setattr(job.company, "confirm", lambda prompt: prompts.append(prompt) or True)
    job._legacy.cmd_config_tz_set({}, "ET")
    assert prompts == ["Change default timezone from CT to ET?"]
    out = capsys.readouterr().out
    assert "Converted" not in out
    assert job.storage.get_default_tz() == ("America/New_York", "ET")


def test_cmd_config_tz_set_converts_stored_interviews(monkeypatch, capsys):
    prompts = []
    monkeypatch.setattr(job.company, "confirm", lambda prompt: prompts.append(prompt) or True)
    rec = interview_record(interview="2026-07-17T10:00:00-05:00", interview_tz="CT")
    data = {rec["id"]: rec}

    job._legacy.cmd_config_tz_set(data, "ET")

    assert "This will convert 1 stored interview(s) to ET." in prompts[-1]
    out = capsys.readouterr().out
    assert "Default timezone set to ET. Converted 1 interview(s)." in out
    assert data[rec["id"]]["interview_tz"] == "ET"
    assert data[rec["id"]]["interview"] == "2026-07-17T11:00:00-04:00"


def test_cmd_config_tz_set_persists_converted_data_to_disk(stub_confirm):
    stub_confirm(True)
    rec = interview_record(interview="2026-07-17T10:00:00-05:00", interview_tz="CT")
    job.storage.save_data({rec["id"]: rec})
    data = job.storage.load_data()

    job._legacy.cmd_config_tz_set(data, "ET")

    on_disk = read_data()
    (saved,) = on_disk.values()
    assert saved["interview_tz"] == "ET"
    assert saved["interview"] == "2026-07-17T11:00:00-04:00"


def test_cmd_config_tz_set_declined_leaves_config_and_data_untouched(stub_confirm, capsys):
    stub_confirm(False)
    rec = interview_record(interview="2026-07-17T10:00:00-05:00", interview_tz="CT")
    data = {rec["id"]: rec}

    job._legacy.cmd_config_tz_set(data, "ET")

    assert "Cancelled." in capsys.readouterr().out
    assert job.storage.get_default_tz() == ("America/Chicago", "CT")
    assert data[rec["id"]]["interview_tz"] == "CT"


# ---- `job config` CLI dispatch ----------------------------------------------

def test_cli_config_tz_no_args_shows_current(run_cli):
    out = run_cli("config", "tz")
    assert "Default timezone: CT" in out


def test_cli_config_no_subcommand_shows_usage(run_cli):
    out = run_cli("config")
    assert "Usage: job config tz <ZONE>" in out


def test_cli_config_unknown_subcommand_errors(run_cli):
    out = run_cli("config", "bogus")
    assert "Unknown `config` subcommand 'bogus'" in out


def test_cli_config_tz_too_many_args_errors(run_cli):
    out = run_cli("config", "tz", "CT", "extra")
    assert "Too many arguments" in out


def test_cli_config_tz_set_end_to_end(run_cli, stub_confirm):
    stub_confirm(True)
    out = run_cli("config", "tz", "MT")
    assert "Default timezone set to MT." in out
    assert job.storage.get_default_tz() == ("America/Denver", "MT")


# ---- first-run prompt triggered by setting an interview --------------------

def test_interview_set_prompts_for_default_when_unconfigured(run_cli, clear_default_tz, tty, answer_input, freeze_date):
    clear_default_tz()
    tty(stdin=True)
    freeze_date(2026, 1, 1)
    run_cli("Big Corp", "Data Engineer")

    answer_input("ET", "y")  # first answers the tz setup prompt, then the interview confirm
    out = run_cli("Big Corp", "interview", "2026-07-13", "13:00")

    assert "Default timezone set to ET." in out
    assert "Updated Big Corp's interview:" in out
    (rec,) = read_data().values()
    assert rec["interview_tz"] == "ET"
    assert job.storage.get_default_tz() == ("America/New_York", "ET")


def test_interview_set_with_explicit_tz_still_prompts_for_default_at_normalize_time(run_cli, clear_default_tz, tty, answer_input):
    clear_default_tz()
    tty(stdin=True)
    run_cli("Acme", "Data Engineer")

    answer_input("CT", "y")
    out = run_cli("Acme", "interview", "2026-08-01", "9am", "ET")

    assert "Default timezone set to CT." in out
    (rec,) = read_data().values()
    assert rec["interview_tz"] == "CT"
    assert rec["interview"].startswith("2026-08-01T08:00:00")


def test_interview_set_explicit_tz_declines_default_prompt_at_normalize_time_cancels(run_cli, clear_default_tz, tty, answer_input):
    # Unlike the bare-tz case, parsing itself succeeds here (an explicit "ET"
    # was given) -- the default-timezone prompt only fires later, inside
    # normalize_interview_tz/cmd_interview_set, so this exercises that
    # specific failure path rather than parse_interview_datetime's.
    clear_default_tz()
    tty(stdin=True)
    run_cli("Acme", "Data Engineer")

    answer_input("")  # declines the default-tz prompt at normalize time
    out = run_cli("Acme", "interview", "2026-08-01", "9am", "ET")

    assert "Cancelled." in out
    assert job.storage.get_default_tz() == (None, None)
    (rec,) = read_data().values()
    assert rec["interview"] is None


def test_interview_set_declines_default_prompt_cancels_and_saves_nothing(run_cli, clear_default_tz, tty, answer_input):
    clear_default_tz()
    tty(stdin=True)
    run_cli("Big Corp", "Data Engineer")

    answer_input("")
    out = run_cli("Big Corp", "interview", "2026-07-13", "13:00")

    assert "Cancelled." in out
    assert job.storage.get_default_tz() == (None, None)
    (rec,) = read_data().values()
    assert rec["interview"] is None


def test_interview_set_eof_at_default_prompt_cancels(run_cli, clear_default_tz, tty, eof_input):
    clear_default_tz()
    tty(stdin=True)
    run_cli("Big Corp", "Data Engineer")

    out = run_cli("Big Corp", "interview", "2026-07-13", "13:00")

    assert "Cancelled." in out
    assert job.storage.get_default_tz() == (None, None)


def test_interview_set_unrecognized_default_prompt_cancels(run_cli, clear_default_tz, tty, answer_input):
    clear_default_tz()
    tty(stdin=True)
    run_cli("Big Corp", "Data Engineer")

    answer_input("XX")
    out = run_cli("Big Corp", "interview", "2026-07-13", "13:00")

    assert "Unknown timezone 'XX'" in out
    assert job.storage.get_default_tz() == (None, None)
    (rec,) = read_data().values()
    assert rec["interview"] is None


def test_interview_set_non_interactive_with_no_default_is_a_hard_error(run_cli, clear_default_tz, tty):
    clear_default_tz()
    tty(stdin=False)
    run_cli("Big Corp", "Data Engineer")

    out = run_cli("Big Corp", "interview", "2026-07-13", "13:00")

    assert "No default timezone is configured yet." in out
    assert "job config tz" in out
    (rec,) = read_data().values()
    assert rec["interview"] is None
