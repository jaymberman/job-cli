import job


def rec(company, applied="2026-01-01", id_="11111111", deleted=False):
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
        "deleted_at": None,
    }


# ---- resolve_company_key ---------------------------------------------------

def test_exact_normalized_match_short_circuits_without_scoring():
    pool = {"1": rec("foobar Consulting")}
    assert job._legacy.resolve_company_key(pool, "foobar consulting") == "foobarconsulting"


def test_exact_match_case_and_spacing_insensitive():
    pool = {"1": rec("foobar Consulting")}
    assert job._legacy.resolve_company_key(pool, "foobarconsulting") == "foobarconsulting"


def test_empty_pool_returns_none():
    assert job._legacy.resolve_company_key({}, "anything") is None


def test_data_guard_prevents_fuzzy_reinterpretation_across_pools():
    # "Big Corp" exists (soft-deleted) in the full dataset but not in this
    # active-only pool; even though "Bigg Corp" fuzzily resembles a
    # different active company, an exact-elsewhere match must block the
    # fuzzy fallback entirely rather than guessing the unrelated company.
    deleted = rec("Big Corp", id_="deaddead", deleted=True)
    unrelated_active = rec("Bigg Corp", id_="22222222")
    data = {"deaddead": deleted, "22222222": unrelated_active}
    pool = job._legacy.active_records(data)

    assert job._legacy.resolve_company_key(pool, "Big Corp", data=data) is None


def test_auto_accepts_confident_single_candidate():
    pool = {"1": rec("foobar Consulting")}
    assert job._legacy.resolve_company_key(pool, "foobar") == "foobarconsulting"


def test_auto_accept_never_calls_confirm(monkeypatch):
    pool = {"1": rec("foobar Consulting")}
    monkeypatch.setattr(job._legacy, "confirm", lambda prompt: (_ for _ in ()).throw(
        AssertionError("confirm() should not be called on a confident auto-accept")))
    job._legacy.resolve_company_key(pool, "foobar")


def test_confirm_threshold_prompts_and_accepts(monkeypatch):
    pool = {"1": rec("Davita")}
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return "y"

    monkeypatch.setattr("builtins.input", fake_input)
    result = job._legacy.resolve_company_key(pool, "davidoff")
    assert result == "davita"
    assert prompts == ["Did you mean 'Davita'? [y/N] "]


def test_confirm_threshold_prompts_and_declines_returns_none(answer_input):
    pool = {"1": rec("Davita")}
    answer_input("n")
    assert job._legacy.resolve_company_key(pool, "davidoff") is None


def test_below_confirm_threshold_returns_none_without_prompting(monkeypatch):
    pool = {"1": rec("Zzyzx Corp")}
    monkeypatch.setattr(job._legacy, "confirm", lambda prompt: (_ for _ in ()).throw(
        AssertionError("confirm() should not be called below the confirm threshold")))
    assert job._legacy.resolve_company_key(pool, "Qwxyz Industries") is None


def test_close_margin_between_top_two_falls_to_confirm(monkeypatch, answer_input):
    # Two candidates both score >= AUTO_THRESHOLD but less than AUTO_MARGIN
    # apart: auto-accept must be denied even though the top score alone
    # would otherwise qualify, and it should fall through to a confirm.
    pool = {"1": rec("Aaa Corp", id_="11111111"), "2": rec("Aab Corp", id_="22222222")}

    def fake_score(a, b):
        return {"aaacorp": 0.85, "aabcorp": 0.82}.get(b, 0.0)

    monkeypatch.setattr(job._legacy, "score", fake_score)
    answer_input("y")
    assert job._legacy.resolve_company_key(pool, "whatever") == "aaacorp"


# ---- resolve_active ---------------------------------------------------------

def test_resolve_active_finds_record_id_for_matched_company():
    active = rec("Big Corp", id_="11111111")
    data = {"11111111": active}
    assert job._legacy.resolve_active(data, "big corp") == "11111111"


def test_resolve_active_ignores_soft_deleted_records():
    deleted = rec("Big Corp", id_="deaddead", deleted=True)
    data = {"deaddead": deleted}
    assert job._legacy.resolve_active(data, "big corp") is None


def test_resolve_active_no_match_returns_none():
    data = {"11111111": rec("Big Corp", id_="11111111")}
    assert job._legacy.resolve_active(data, "Totally Unrelated Industries") is None


# ---- active_records / deleted_records / company_records --------------------

def test_active_records_excludes_deleted():
    active = rec("Active Co", id_="11111111")
    deleted = rec("Deleted Co", id_="22222222", deleted=True)
    data = {"11111111": active, "22222222": deleted}
    assert job._legacy.active_records(data) == {"11111111": active}


def test_deleted_records_only_deleted():
    active = rec("Active Co", id_="11111111")
    deleted = rec("Deleted Co", id_="22222222", deleted=True)
    data = {"11111111": active, "22222222": deleted}
    assert job._legacy.deleted_records(data) == {"22222222": deleted}


def test_company_records_returns_all_records_sharing_a_company():
    r1 = rec("Big Corp", id_="11111111", applied="2026-01-01")
    r2 = rec("Big Corp", id_="22222222", applied="2025-01-01", deleted=True)
    other = rec("Other Co", id_="33333333")
    pool = {"11111111": r1, "22222222": r2, "33333333": other}
    matches = job._legacy.company_records(pool, job._legacy.normalize("Big Corp"))
    assert {r["id"] for r in matches} == {"11111111", "22222222"}
