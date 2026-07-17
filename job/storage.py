import json
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LEGACY_DATA_DIR = os.path.join(SCRIPT_DIR, "data")
_LEGACY_DATA_FILE = os.path.join(_LEGACY_DATA_DIR, "applications.json")
_XDG_DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"),
    "job-cli",
)
_XDG_CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"),
    "job-cli",
)
CONFIG_FILE = os.path.join(_XDG_CONFIG_DIR, "config.json")

if os.path.exists(_LEGACY_DATA_FILE):
    # Pre-existing checkouts keep using their in-repo data file untouched.
    DATA_DIR = _LEGACY_DATA_DIR
    DATA_FILE = _LEGACY_DATA_FILE
else:
    DATA_DIR = _XDG_DATA_DIR
    DATA_FILE = os.path.join(DATA_DIR, "applications.json")


def needs_migration(data):
    """True if any record predates the id-keyed, soft-delete-aware schema
    (detected by the absence of the `deleted` field, which every record
    written under the new schema always has, even freshly-created ones)."""
    return any("deleted" not in rec for rec in data.values())


def migrate_legacy_data(data):
    """Converts the old company-normalized-name-keyed schema (one record per
    company, no soft-delete fields) into the new id-keyed schema. Runs once,
    transparently, the next time the old file is loaded."""
    migrated = {}
    for rec in data.values():
        rec = dict(rec)
        rec.setdefault("deleted", False)
        rec.setdefault("deleted_at", None)
        new_key = new_id(migrated)
        rec["id"] = new_key
        migrated[new_key] = rec
    return migrated


def needs_tz_backfill(data):
    """True if a default timezone is configured AND some record's stored
    interview isn't already expressed in it -- e.g. a record written before
    the configured default was changed, or before this feature existed at
    all. Silently reports nothing to do when no default is configured yet,
    since load_data() must never force the interactive setup prompt just to
    run a command that has nothing to do with timezones."""
    _, default_label = get_default_tz()
    if default_label is None:
        return False
    return any(
        rec.get("interview") is not None and rec.get("interview_tz") != default_label
        for rec in data.values()
    )


def backfill_interview_tz(data):
    """Converts every stored interview datetime to the configured default
    timezone, in place -- same instant, re-expressed in one zone so every
    record is mutually comparable. Only ever called after needs_tz_backfill
    (or a `job config tz` change) has confirmed a default is configured, so
    this never needs to prompt. Idempotent: once every record matches the
    current default, needs_tz_backfill is False and this never runs again."""
    default_iana, default_label = get_default_tz()
    for rec in data.values():
        if rec.get("interview") is None:
            continue
        aware_dt = datetime.fromisoformat(rec["interview"]).astimezone(ZoneInfo(default_iana))
        rec["interview"] = aware_dt.isoformat()
        rec["interview_tz"] = default_label
    return data


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    changed = False
    if needs_migration(data):
        data = migrate_legacy_data(data)
        changed = True
    if needs_tz_backfill(data):
        data = backfill_interview_tz(data)
        changed = True
    if changed:
        save_data(data)
    return data


def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_config(config):
    os.makedirs(_XDG_CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, sort_keys=True)


def get_default_tz():
    """Returns (iana_zone, label) for the user's configured default
    timezone, or (None, None) if none is configured yet."""
    from . import interview  # deferred: avoids a load-time cycle with interview.py

    label = load_config().get("default_tz")
    if label is None:
        return None, None
    return interview.TZ_ALIASES.get(label, (None, None))


def set_default_tz(label):
    config = load_config()
    config["default_tz"] = label
    save_config(config)


def new_id(data):
    while True:
        candidate = uuid.uuid4().hex[:8]
        if candidate not in data:
            return candidate
