import json

import job


def legacy_record(company="Big Corp", title="Data Engineer"):
    return {
        "company": company,
        "title": title,
        "applied": "2026-01-01",
        "interview": None,
        "status": "sent app",
        "status_changed": "2026-01-01",
    }


def new_record(company="Big Corp"):
    return {
        "id": "abc12345",
        "company": company,
        "title": "Data Engineer",
        "applied": "2026-01-01",
        "interview": None,
        "interview_tz": None,
        "status": "sent app",
        "status_changed": "2026-01-01",
        "deleted": False,
        "deleted_at": None,
    }


def test_needs_migration_empty_data():
    assert job.needs_migration({}) is False


def test_needs_migration_false_when_all_records_have_deleted_field():
    assert job.needs_migration({"abc12345": new_record()}) is False


def test_needs_migration_true_when_any_record_missing_deleted_field():
    data = {"bigcorp": legacy_record()}
    assert job.needs_migration(data) is True


def test_migrate_legacy_data_adds_soft_delete_fields_and_ids():
    data = {"bigcorp": legacy_record()}
    migrated = job.migrate_legacy_data(data)
    assert len(migrated) == 1
    (key, rec), = migrated.items()
    assert rec["id"] == key
    assert rec["deleted"] is False
    assert rec["deleted_at"] is None
    assert rec["company"] == "Big Corp"
    assert rec["title"] == "Data Engineer"
    assert len(key) == 8


def test_migrate_legacy_data_preserves_existing_deleted_at_if_present():
    # setdefault() shouldn't clobber a deleted_at that's already there, even
    # though 'deleted' itself (the migration trigger) is still missing.
    rec = legacy_record()
    rec["deleted_at"] = "2026-02-01"
    data = {"bigcorp": rec}
    migrated = job.migrate_legacy_data(data)
    (_, out), = migrated.items()
    assert out["deleted"] is False
    assert out["deleted_at"] == "2026-02-01"


def test_load_data_returns_empty_dict_when_file_missing():
    assert job.load_data() == {}


def test_load_data_returns_current_schema_unchanged():
    rec = new_record()
    job.save_data({rec["id"]: rec})
    loaded = job.load_data()
    assert loaded == {rec["id"]: rec}


def test_load_data_migrates_legacy_file_in_place():
    legacy = {"bigcorp": legacy_record()}
    job.os.makedirs(job.DATA_DIR, exist_ok=True)
    with open(job.DATA_FILE, "w") as f:
        json.dump(legacy, f)

    loaded = job.load_data()
    (key, rec), = loaded.items()
    assert rec["deleted"] is False
    assert rec["id"] == key

    # The migration must have been persisted, not just returned in memory.
    with open(job.DATA_FILE) as f:
        on_disk = json.load(f)
    assert on_disk == loaded


def test_save_data_creates_data_dir_and_round_trips():
    assert not job.os.path.exists(job.DATA_DIR)
    rec = new_record()
    job.save_data({rec["id"]: rec})
    assert job.os.path.exists(job.DATA_FILE)
    with open(job.DATA_FILE) as f:
        on_disk = json.load(f)
    assert on_disk == {rec["id"]: rec}


def test_new_id_is_eight_hex_chars_and_unique():
    data = {}
    key = job.new_id(data)
    assert len(key) == 8
    int(key, 16)  # raises if not hex
    assert key not in data


def test_new_id_retries_on_collision(monkeypatch):
    colliding = job.uuid.uuid4()
    fresh = job.uuid.uuid4()
    calls = iter([colliding, colliding, fresh])
    monkeypatch.setattr(job.uuid, "uuid4", lambda: next(calls))

    data = {colliding.hex[:8]: new_record()}
    key = job.new_id(data)
    assert key == fresh.hex[:8]


def test_active_and_deleted_records_split_pool():
    active = new_record("Active Co")
    deleted = new_record("Deleted Co")
    deleted["id"] = "deadbeef"
    deleted["deleted"] = True
    data = {active["id"]: active, deleted["id"]: deleted}

    assert job.active_records(data) == {active["id"]: active}
    assert job.deleted_records(data) == {deleted["id"]: deleted}


def test_company_records_matches_by_normalized_company():
    rec1 = new_record("Big Corp")
    rec1["id"] = "11111111"
    rec2 = new_record("big corp")
    rec2["id"] = "22222222"
    other = new_record("Other Co")
    other["id"] = "33333333"
    pool = {r["id"]: r for r in (rec1, rec2, other)}

    matches = job.company_records(pool, job.normalize("Big Corp"))
    assert {r["id"] for r in matches} == {"11111111", "22222222"}
