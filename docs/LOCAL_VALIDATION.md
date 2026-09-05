# Focused local validation

Use the local runner for small engineering checks. It deliberately runs every selected test module in a fresh pytest process, so a study-specific failure remains isolated and its pytest output is forwarded directly.

Prepare the active interpreter once when the package is not already installed:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

List the maintained lanes, then run only the one that applies to the change:

```powershell
.venv\Scripts\python.exe scripts\check_local.py --list
.venv\Scripts\python.exe scripts\check_local.py --lane core
```

`core` runs release identity, CLI, batch, verification, runner, longform, scoring, and weights modules. `package` runs the separate, slower public-surface module:

```powershell
.venv\Scripts\python.exe scripts\check_local.py --lane package
```

For a study-specific gate, request its explicit module. Multiple `--study` values are allowed; each is a fresh pytest process.

```powershell
.venv\Scripts\python.exe scripts\check_local.py --study tests\test_hbq_human_alignment_optimizer_v17_comparative_native_v1.py
```

These are focused engineering checks, not release proof. Each study still requires its own frozen-data, provenance, and acceptance gates. Local results do not establish native Linux, provider-contact, endpoint-parity, or deployment proof. The runner intentionally has no default all-history sweep and does not invoke hosted CI.
