# CLAUDE.md

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
