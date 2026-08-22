from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "batch-curve-codex-remainder-v2"


def _module():
    spec = importlib.util.spec_from_file_location("batch_curve_codex_remainder_v2", ROOT / "batch_recovery.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    if argv[:2] == ["git", "rev-parse"]:
        return subprocess.CompletedProcess(argv, 0, "a" * 40 + "\n", "")
    if argv[:2] == ["git", "status"]:
        return subprocess.CompletedProcess(argv, 0, "", "")
    if argv[:2] == ["git", "ls-files"]:
        return subprocess.CompletedProcess(argv, 0, argv[-1] + "\n", "")
    if argv[-1] == "--version":
        return subprocess.CompletedProcess(argv, 0, "codex test\n", "")
    raise AssertionError(argv)


def _prepare(module, tmp_path: Path) -> tuple[Path, Path]:
    work, private = tmp_path / "work", tmp_path / "private"
    module.prepare(work, private, subprocess_run=_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"))
    module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(tmp_path / "codex.exe"), now=datetime.fromisoformat("2026-08-27T19:22:00-06:00"), invoke=lambda **_: ("{\"ready\":true}", {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "native-capacity"}}))
    return work, private


def _external_temp() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="cwr-batch-remainder-v2-", dir=str(ROOT.parents[3]))


def _preflight_response(**_kwargs: object):
    return "{\"ready\":true}", {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "native-capacity"}}


def _fake_unit(module, calls: list[int]):
    def run(private: Path, row: dict, _executable: str) -> dict:
        calls.append(row["sequence"])
        destination = module._unit_path(private, row); destination.mkdir(parents=True); (destination / "raw.txt").write_text(str(row["sequence"]), encoding="utf-8")
        digest = f"{row['sequence']:064x}"
        return {"run_sha256": "a" * 64, "score_sha256": "b" * 64, "score_v2_sha256": "c" * 64, "verdict_count": row["question_count"], "sessions": [{"session_id_sha256": digest}]}
    return run


def test_exact_current_stack_and_47_unit_schedule() -> None:
    module = _module(); value, rows = module.contract(), module.plan()
    assert value["current_stack"]["runner"]["bytes"] == 124714
    assert value["current_stack"]["runner"]["sha256"] == "0a22bf30781d6bbbde4c9b6a6e214891fe95aefddade6f955f5634f6accde4d2"
    assert len(rows) == 47
    assert rows[0]["parent_cell"] == 36 and rows[0]["batch"] == 32
    assert rows[-1]["parent_cell"] == 39 and rows[-1]["batch"] == 4
    assert not any(row["parent_cell"] == 36 and row["batch"] <= 31 for row in rows)


def test_clean_checkout_bytes_bind_plan_prepare_and_reject_altered_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); value = module.contract()
    for name, binding in value["current_stack"].items():
        path = module._stack(name)
        assert path.stat().st_size == binding["bytes"] and module._sha_path(path) == binding["sha256"]
    assert len(module.plan()) == 47
    with _external_temp() as outer:
        work, private = Path(outer) / "work", Path(outer) / "private"
        receipt = module.prepare(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"))
        assert receipt["schedule"] == module.plan()
    altered_path = tmp_path / "altered-modules.json"
    altered_path.write_bytes(module._stack("registry").read_bytes() + b"\n")
    altered = json.loads(json.dumps(value)); altered["current_stack"]["registry"]["path"] = str(altered_path)
    monkeypatch.setattr(module, "contract", lambda: altered)
    with pytest.raises(ValueError, match="Bound bytes drifted"):
        module.plan()


def test_prepare_rejects_dirty_or_untracked_or_untracked_self_source(tmp_path: Path) -> None:
    module = _module()
    with pytest.raises(ValueError, match="clean committed pushed"):
        module._git_state(lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "x\n" if argv[:2] == ["git", "status"] else "a" * 40 + "\n", ""))
    def untracked_self(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["git", "ls-files"]:
            return subprocess.CompletedProcess(argv, 1, "", "missing")
        return _run(argv)
    with pytest.raises(ValueError, match="tracked"):
        module._git_state(untracked_self)


def test_native_preflight_is_not_caller_authored_and_is_fresh_and_bound(tmp_path: Path) -> None:
    module = _module()
    with _external_temp() as outer:
        work, private = _prepare(module, Path(outer))
        current = module._active_preflight(work, private, 1, datetime.fromisoformat("2026-08-27T19:23:00-06:00"), subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"))
        assert current["native_argv"] == ["exec", "--model", "gpt-5.6-sol"] and current["model"] == "gpt-5.6-sol"
        assert module._active_preflight(work, private, 1, datetime.fromisoformat("2026-08-27T19:38:00-06:00"), subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe")) is None
        module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), now=datetime.fromisoformat("2026-08-27T19:39:00-06:00"), invoke=_preflight_response)
        assert module._active_preflight(work, private, 1, datetime.fromisoformat("2026-08-27T19:40:00-06:00"), subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"))["refresh"] == 2
        public = work / "preflights" / "epoch-0001" / "refresh-0002.json"
        tampered = json.loads(public.read_text(encoding="utf-8")); tampered["model"] = "other"; public.write_text(json.dumps(tampered), encoding="utf-8")
        with pytest.raises(ValueError, match="mismatched|shape"):
            module._active_preflight(work, private, 1, datetime.fromisoformat("2026-08-27T19:40:00-06:00"), subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"))


def test_cap_one_unit_does_not_resend_malformed_2xx(tmp_path: Path) -> None:
    module = _module(); row = module.plan()[0]; calls = 0
    def malformed(**_kwargs: object):
        nonlocal calls
        calls += 1
        return "{not json", {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "only-attempt"}}
    with pytest.raises(ValueError, match="malformed"):
        module._run_unit(tmp_path, row, "fake", invoke=malformed)
    assert calls == 1
    with pytest.raises(ValueError, match="already exists"):
        module._run_unit(tmp_path, row, "fake", invoke=malformed)
    assert calls == 1


def test_schedule_receipt_is_the_actual_prepared_schedule_not_a_post_prepare_monkeypatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    with _external_temp() as outer:
        work, private = _prepare(module, Path(outer))
        original = module.plan
        monkeypatch.setattr(module, "plan", lambda: original()[:1])
        with pytest.raises(ValueError, match="not current pushed source/runtime"):
            module._validate_prepared(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"))


def test_historical_exclusion_includes_rejected_batch32_hashes() -> None:
    module = _module(); values = module._historical_session_hashes()
    assert {
        "890a8709675a6ea06974bf3ce8d27ed0dd375291c9ac1698ca7191b01880df35",
        "693a5a4bf0fa8f7b32ced792b9d3ffdaf5006082528948d1591f5d3e3c38ca65",
        "8f2e9adf7a160642a1d2a867743fbe0ea996c524a7cf9bbe7e730cd0d389f8fd",
    } <= values


def test_completed_prefix_resumes_without_requiring_a_current_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_historical_session_hashes", lambda: set())
    with _external_temp() as outer:
        work, private = _prepare(module, Path(outer)); calls: list[int] = []
        first = module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: datetime.fromisoformat("2026-08-27T19:23:00-06:00"), unit_runner=_fake_unit(module, calls), verifier=lambda private, row, exe: _fake_unit(module, []) and {"run_sha256": "a" * 64, "score_sha256": "b" * 64, "score_v2_sha256": "c" * 64, "verdict_count": row["question_count"], "sessions": [{"session_id_sha256": f"{row['sequence']:064x}"}]}, max_scored_units=1)
        assert first["completed_units"] == 1 and calls == [1]
        second = module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: datetime.fromisoformat("2026-08-27T19:40:00-06:00"), unit_runner=_fake_unit(module, calls), verifier=lambda private, row, exe: {"run_sha256": "a" * 64, "score_sha256": "b" * 64, "score_v2_sha256": "c" * 64, "verdict_count": row["question_count"], "sessions": [{"session_id_sha256": f"{row['sequence']:064x}"}]}, preflight_invoke=_preflight_response, max_scored_units=1)
        assert second["completed_units"] == 2 and second["preflight_provider_calls_this_invocation"] == 1 and calls == [1, 2]


def test_expiring_clock_stops_before_contact_then_appends_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_historical_session_hashes", lambda: set())
    with _external_temp() as outer:
        work, private = _prepare(module, Path(outer)); calls: list[int] = []; times = iter([datetime.fromisoformat("2026-08-27T19:23:00-06:00"), datetime.fromisoformat("2026-08-27T19:39:00-06:00")])
        with pytest.raises(ValueError, match="expired before scored-unit contact"):
            module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: next(times), unit_runner=_fake_unit(module, calls), max_scored_units=1)
        assert calls == [] and not (work / "cells" / "cell-36-batch-0032.json").exists()
        result = module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: datetime.fromisoformat("2026-08-27T19:40:00-06:00"), unit_runner=_fake_unit(module, calls), preflight_invoke=_preflight_response, max_scored_units=1)
        assert result["preflight_provider_calls_this_invocation"] == 1 and calls == [1]


def test_source_receipt_failure_before_marker_is_resumable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); monkeypatch.setattr(module, "_historical_session_hashes", lambda: set())
    with _external_temp() as outer:
        work, private = _prepare(module, Path(outer)); calls: list[int] = []; original = module._receipt; seen = 0
        def receipt(*args, **kwargs):
            nonlocal seen
            seen += 1
            return original(*args, **kwargs) if seen == 1 else {"drift": True}
        monkeypatch.setattr(module, "_receipt", receipt)
        monkeypatch.setattr(module, "_active_preflight", lambda *args, **kwargs: {"active": True})
        with pytest.raises(ValueError, match="Exact pushed source/runtime changed"):
            module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: datetime.fromisoformat("2026-08-27T19:23:00-06:00"), unit_runner=_fake_unit(module, calls), max_scored_units=1)
        assert calls == [] and not (work / "cells" / "cell-36-batch-0032.json").exists()


def test_failed_preflight_is_counted_and_next_refresh_advances(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); monkeypatch.setattr(module, "_historical_session_hashes", lambda: set())
    with _external_temp() as outer:
        work, private = _prepare(module, Path(outer)); calls: list[int] = []
        def fail(**_kwargs: object):
            raise module.shared._ProviderAttemptFailure("quota", retryable=False, content="", provider_record={"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "failed-preflight"}})
        with pytest.raises(ValueError, match="capacity preflight failed"):
            module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: datetime.fromisoformat("2026-08-27T19:40:00-06:00"), preflight_invoke=fail, unit_runner=_fake_unit(module, calls), max_scored_units=1)
        failed = work / "preflights" / "epoch-0001" / "refresh-0002.json"
        assert json.loads(failed.read_text(encoding="utf-8"))["status"] == "failed" and calls == []
        result = module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: datetime.fromisoformat("2026-08-27T19:41:00-06:00"), preflight_invoke=_preflight_response, unit_runner=_fake_unit(module, calls), max_scored_units=1)
        assert result["recorded_preflight_provider_calls"] == 3 and result["preflight_provider_calls_this_invocation"] == 1 and calls == [1]


def test_epoch_transition_and_preflight_collision_are_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_historical_session_hashes", lambda: set())
    with _external_temp() as outer:
        work, private = _prepare(module, Path(outer)); calls: list[int] = []
        verifier = lambda private, row, exe: {"run_sha256": "a" * 64, "score_sha256": "b" * 64, "score_v2_sha256": "c" * 64, "verdict_count": row["question_count"], "sessions": [{"session_id_sha256": f"{row['sequence']:064x}"}]}
        module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: datetime.fromisoformat("2026-08-27T19:23:00-06:00"), unit_runner=_fake_unit(module, calls), verifier=verifier, max_scored_units=8)
        next_epoch = module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), clock=lambda: datetime.fromisoformat("2026-08-27T19:24:00-06:00"), unit_runner=_fake_unit(module, calls), verifier=verifier, preflight_invoke=_preflight_response, max_scored_units=1)
        assert next_epoch["preflight_provider_calls_this_invocation"] == 1 and calls[-1] == 9
        collision = work / "preflights" / "epoch-0003" / "refresh-0002.json"; collision.parent.mkdir(parents=True); collision.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="gap or collision"):
            module.native_preflight(work, private, epoch=3, subprocess_run=_run, executable_resolver=lambda _: str(work.parent / "codex.exe"), now=datetime.fromisoformat("2026-08-27T19:25:00-06:00"), invoke=_preflight_response)


def test_private_only_terminal_preflight_is_settled_without_resend(tmp_path: Path) -> None:
    module = _module()
    with _external_temp() as outer:
        root = Path(outer); work, private = root / "work", root / "private"; invoked: list[str] = []
        module.prepare(work, private, subprocess_run=_run, executable_resolver=lambda _: str(root / "codex.exe"))
        def failed(**_kwargs: object):
            invoked.append("failed")
            raise module.shared._ProviderAttemptFailure("transport", retryable=False, content="", provider_record=None)
        with pytest.raises(ValueError, match="capacity preflight failed"):
            module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(root / "codex.exe"), now=datetime.fromisoformat("2026-08-27T19:22:00-06:00"), invoke=failed)
        public_one = work / "preflights" / "epoch-0001" / "refresh-0001.json"
        public_one.unlink()
        def valid(**_kwargs: object):
            invoked.append("valid")
            return _preflight_response()
        recovered = module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(root / "codex.exe"), now=datetime.fromisoformat("2026-08-27T19:23:00-06:00"), invoke=valid)
        assert invoked == ["failed", "valid"] and recovered["refresh"] == 2
        assert json.loads(public_one.read_text(encoding="utf-8"))["status"] == "failed"
        assert module._preflight_attempt_count(work, private) == 2
