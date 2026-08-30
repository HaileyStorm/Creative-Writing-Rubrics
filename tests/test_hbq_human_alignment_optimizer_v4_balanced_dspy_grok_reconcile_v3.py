from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-reconcile-v3"
LIVE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-grok-v3-a1f9467-r4shrink-20260830a")
reconciler = load_module(PACKAGE / "reconciler.py", name="feedback_grok_reconcile_v3")


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


@pytest.fixture()
def terminal_wave(tmp_path: Path) -> Path:
    expected = set(reconciler.SOURCE_INVENTORY_SHA256)
    if not LIVE_ROOT.is_dir() or {item.name for item in LIVE_ROOT.iterdir() if item.is_dir() and "-sample-" in item.name} != expected:
        pytest.skip("exact live v3 terminal roots are unavailable")
    root = tmp_path / "wave"
    for sample in sorted(expected):
        shutil.copytree(LIVE_ROOT / sample, root / sample)
    return root


def _control(cell: Path) -> dict:
    raw = (cell / "adapter-stdout.bin").read_bytes()
    assert raw.endswith(b"\r\n")
    return json.loads(raw[:-2])


def _rebind(cell: Path, control: dict) -> None:
    raw = json.dumps(control, ensure_ascii=False).encode() + b"\r\n"
    (cell / "adapter-stdout.bin").write_bytes(raw)
    terminal = json.loads((cell / "result.json").read_bytes()); terminal["adapter_stdout_sha256"] = reconciler.sha256(raw)
    (cell / "result.json").write_bytes(canonical(terminal))


def test_actual_live_control_uses_crlf_transport_and_adapter_hash_domain(terminal_wave: Path):
    cell = terminal_wave / f"{reconciler.SAMPLE_PREFIX}-sample-01"; raw = reconciler._inventory(cell)
    _prepared, prompt, route, evidence = reconciler._prepared(raw, cell.name)
    control, output, runtime = reconciler._control(raw["adapter-stdout.bin"], prompt, route, evidence)
    assert raw["adapter-stdout.bin"].endswith(b"\r\n") and b", " in raw["adapter-stdout.bin"]
    assert control["control"] == {"state": "completed", "version": 1}
    assert runtime["request_id_hash"] != runtime["session_id_hash"]
    assert reconciler.sha256(reconciler.adapter_canonical(output)) == control["result"]["output_hash"]


def test_partial_reconciliation_is_exact_nine_plus_one(terminal_wave: Path, tmp_path: Path):
    manifest = reconciler.reconcile_partial(source_root=terminal_wave, manifest_path=tmp_path / "partial.json")
    assert (tmp_path / "partial.json").read_bytes() == reconciler.project_canonical(manifest)
    assert len(manifest["samples"]) == 9 and manifest["excluded_terminal"]["sample_id"].endswith("-sample-06")
    assert manifest["completion"]["completed_aggregate_freeze"] is False
    assert all(row["source_terminal"]["kind"] == "reconcile_required_after_process_launch" for row in manifest["samples"])


@pytest.mark.parametrize("kind", ["transport", "nonfinite", "route_remint", "control_swap", "terminal_remint", "extra", "isolated_gates", "incomplete"])
def test_reconciliation_rejects_remint_and_source_drift(terminal_wave: Path, tmp_path: Path, kind: str):
    one = terminal_wave / f"{reconciler.SAMPLE_PREFIX}-sample-01"; two = terminal_wave / f"{reconciler.SAMPLE_PREFIX}-sample-02"
    if kind == "transport":
        raw = (one / "adapter-stdout.bin").read_bytes(); (one / "adapter-stdout.bin").write_bytes(raw[:-2] + b"\n")
    elif kind == "nonfinite":
        raw = (one / "adapter-stdout.bin").read_bytes(); (one / "adapter-stdout.bin").write_bytes(raw.replace(b'"model_cost_usd": 0.01386282', b'"model_cost_usd": 1e309'))
    elif kind == "route_remint":
        prepared = json.loads((one / "prepared.json").read_bytes()); prepared["route"]["model"] = "forged"; prepared["route_evidence"]["route_sha256"] = "0" * 64; (one / "prepared.json").write_bytes(canonical(prepared)); intent = json.loads((one / "launch-intent.json").read_bytes()); intent["prepared_sha256"] = reconciler.sha256((one / "prepared.json").read_bytes()); intent["route_evidence"] = prepared["route_evidence"]; (one / "launch-intent.json").write_bytes(canonical(intent))
    elif kind == "control_swap":
        first, second = (one / "adapter-stdout.bin").read_bytes(), (two / "adapter-stdout.bin").read_bytes(); (one / "adapter-stdout.bin").write_bytes(second); (two / "adapter-stdout.bin").write_bytes(first)
    elif kind == "terminal_remint":
        control = _control(one); control["result"]["runtime"]["request_id_hash"] = "f" * 64; _rebind(one, control)
    elif kind == "extra":
        (one / "orphan.bin").write_bytes(b"x")
    elif kind == "isolated_gates":
        (terminal_wave / ".isolated-gates").mkdir()
    else:
        (terminal_wave / f"{reconciler.SAMPLE_PREFIX}-sample-10").rename(terminal_wave / "omitted")
    with pytest.raises(ValueError):
        reconciler.reconcile_partial(source_root=terminal_wave, manifest_path=tmp_path / f"{kind}.json")


def test_output_race_and_exclusive_target_are_fail_closed(terminal_wave: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "exclusive.json"; target.write_bytes(b"occupied")
    with pytest.raises(ValueError, match="overwrite"):
        reconciler.reconcile_partial(source_root=terminal_wave, manifest_path=target)
    original = reconciler._row; calls = 0
    def raced(cell: Path, sample: str) -> dict:
        nonlocal calls
        calls += 1
        row = original(cell, sample)
        if calls == 9:
            target = terminal_wave / f"{reconciler.SAMPLE_PREFIX}-sample-01" / "adapter-stdout.bin"; target.write_bytes(target.read_bytes() + b" ")
        return row
    monkeypatch.setattr(reconciler, "_row", raced)
    with pytest.raises(ValueError):
        reconciler.reconcile_partial(source_root=terminal_wave, manifest_path=tmp_path / "race.json")


def test_unsafe_output_ancestry_is_rejected_before_creating_missing_parent(terminal_wave: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    unsafe = tmp_path / "unsafe"; unsafe.mkdir(); target_parent = unsafe / "missing-parent"; target = target_parent / "manifest.json"
    original = reconciler._plain
    def guarded(path: Path, *, directory: bool | None = None) -> bool:
        if Path(path) == unsafe:
            return False
        return original(path, directory=directory)
    monkeypatch.setattr(reconciler, "_plain", guarded)
    with pytest.raises(ValueError, match="ancestry"):
        reconciler.reconcile_partial(source_root=terminal_wave, manifest_path=target)
    assert not target_parent.exists()
