import json

import job


def read_data():
    with open(job.storage.DATA_FILE) as f:
        return json.load(f)


def rec(company, applied="2026-01-01", id_="11111111", deleted=False, deleted_at=None):
    return {
        "id": id_,
        "company": company,
        "title": "Data Engineer",
        "applied": applied,
        "interview": None,
        "interview_tz": None,
        "status": "sent app",
        "status_changed": applied,
        "deleted": deleted,
        "deleted_at": deleted_at,
    }


# ---- soft delete (plain `delete`) ------------------------------------------

def test_soft_delete_happy_path(run_cli, stub_confirm, freeze_date):
    freeze_date(2026, 3, 1)
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "delete")
    assert ("Soft-deleted record for Big Corp. It's hidden from result sets "
            "but can be viewed with `job Big Corp --all`.") in out
    (record,) = read_data().values()
    assert record["deleted"] is True
    assert record["deleted_at"] == "2026-03-01"


def test_soft_delete_declined_leaves_record_active(run_cli, stub_confirm):
    stub_confirm(False)
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "delete")
    assert "Cancelled." in out
    (record,) = read_data().values()
    assert record["deleted"] is False


def test_soft_delete_no_active_record_says_no_applications_sent_even_with_history(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")  # now only soft-deleted history exists
    out = run_cli("Big Corp", "delete")
    assert out.strip() == "no applications sent"


# ---- hard delete of an active record ---------------------------------------

def test_hard_delete_active_record(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "delete", "--hard")
    assert "Permanently deleted record for Big Corp." in out
    assert read_data() == {}


def test_hard_delete_active_record_declined(run_cli, stub_confirm):
    stub_confirm(False)
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "delete", "--hard")
    assert "Cancelled." in out
    assert len(read_data()) == 1


def test_hard_delete_unknown_company_says_no_applications_sent(run_cli):
    out = run_cli("Nonexistent Co", "delete", "--hard")
    assert out.strip() == "no applications sent"


def test_delete_extra_argument_other_than_hard_is_error(run_cli):
    run_cli("Big Corp", "Data Engineer")
    out = run_cli("Big Corp", "delete", "--soft-ish")
    assert "`delete` doesn't take an extra argument, except `--hard`." in out
    assert len(read_data()) == 1


# ---- hard delete falling back to soft-deleted history -----------------------

def test_hard_delete_single_soft_deleted_candidate(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")
    out = run_cli("Big Corp", "delete", "--hard")
    assert "Permanently deleted record for Big Corp." in out
    assert read_data() == {}


def test_hard_delete_single_soft_deleted_candidate_declined(run_cli, stub_confirm):
    stub_confirm(True)
    run_cli("Big Corp", "Data Engineer")
    run_cli("Big Corp", "delete")

    stub_confirm(False)
    out = run_cli("Big Corp", "delete", "--hard")
    assert "Cancelled." in out
    assert len(read_data()) == 1


def _setup_two_soft_deleted(run_cli, answer_input):
    # Two applications to "Big Corp", both eventually soft-deleted, no
    # active record left -- exercises create's declined-reapply prompt too.
    answer_input("y", "y", "y")
    run_cli("Big Corp", "Data Engineer")            # applied 2026-01-01 (freeze below)
    run_cli("Big Corp", "delete")
    run_cli("Big Corp", "Data Engineer II")          # reapply, confirmed
    run_cli("Big Corp", "delete")


def test_hard_delete_multiple_candidates_all_confirmed(run_cli, answer_input, freeze_date):
    freeze_date(2026, 1, 1)
    _setup_two_soft_deleted(run_cli, answer_input)

    answer_input("all", "y")
    out = run_cli("Big Corp", "delete", "--hard")
    assert "has 2 soft-deleted (declined) records:" in out
    assert "Permanently deleted 2 records for Big Corp." in out
    assert read_data() == {}


def test_hard_delete_multiple_candidates_all_declined(run_cli, answer_input, freeze_date):
    freeze_date(2026, 1, 1)
    _setup_two_soft_deleted(run_cli, answer_input)

    answer_input("all", "n")
    out = run_cli("Big Corp", "delete", "--hard")
    assert "Cancelled." in out
    assert len(read_data()) == 2


def test_hard_delete_multiple_candidates_pick_one_by_number(run_cli, answer_input, freeze_date):
    freeze_date(2026, 1, 1)
    _setup_two_soft_deleted(run_cli, answer_input)

    answer_input("1", "y")
    out = run_cli("Big Corp", "delete", "--hard")
    assert "Permanently deleted record for Big Corp." in out
    remaining = read_data()
    assert len(remaining) == 1


def test_hard_delete_multiple_candidates_blank_answer_cancels(run_cli, answer_input, freeze_date):
    freeze_date(2026, 1, 1)
    _setup_two_soft_deleted(run_cli, answer_input)

    answer_input("")
    out = run_cli("Big Corp", "delete", "--hard")
    assert "Cancelled." in out
    assert len(read_data()) == 2


def test_hard_delete_multiple_candidates_eof_on_number_prompt_cancels(monkeypatch, freeze_date):
    # Constructed directly rather than via run_cli: this isolates the EOF
    # path on the *numbered-choice* prompt specifically, which would
    # otherwise conflict with the "y" answers needed just to set the
    # scenario up through the CLI.
    r1 = rec("Big Corp", applied="2026-01-01", id_="11111111", deleted=True, deleted_at="2026-02-01")
    r2 = rec("Big Corp", applied="2026-01-05", id_="22222222", deleted=True, deleted_at="2026-02-02")
    data = {"11111111": r1, "22222222": r2}

    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    job._legacy.cmd_delete(data, "Big Corp", hard=True)
    assert data == {"11111111": r1, "22222222": r2}


# ---- cmd_delete_hard_one directly -------------------------------------------

def test_cmd_delete_hard_one_confirmed(stub_confirm, capsys):
    stub_confirm(True)
    r = rec("Big Corp", deleted=True, deleted_at="2026-02-01")
    data = {"11111111": r}
    job._legacy.cmd_delete_hard_one(data, r)
    assert data == {}
    assert "Permanently deleted record for Big Corp." in capsys.readouterr().out


def test_cmd_delete_hard_one_declined(stub_confirm, capsys):
    stub_confirm(False)
    r = rec("Big Corp", deleted=True, deleted_at="2026-02-01")
    data = {"11111111": r}
    job._legacy.cmd_delete_hard_one(data, r)
    assert data == {"11111111": r}
    assert "Cancelled." in capsys.readouterr().out
