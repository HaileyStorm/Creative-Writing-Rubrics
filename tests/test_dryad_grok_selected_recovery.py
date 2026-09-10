from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1" / "baseline_grok_selected_recovery.py"
PARENT = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1" / "baseline_grok_v5_suffix.py"


def load(path: Path = SOURCE) -> Any:
    spec = importlib.util.spec_from_file_location("dryad_grok_selected_recovery_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def hashes(prefix: str, count: int = 89) -> list[dict[str, str]]:
    return [{"request_id_hash": sha(f"{prefix}-request-{item}".encode()), "session_id_hash": sha(f"{prefix}-session-{item}".encode())}
            for item in range(count)]


def fake_parent(value: Any, source: Path) -> Any:
    real_spec = importlib.util.spec_from_file_location("real_parent_for_recovery", PARENT)
    assert real_spec and real_spec.loader
    real = importlib.util.module_from_spec(real_spec)
    real_spec.loader.exec_module(real)
    pending = [*range(81, 1611), *range(4049, 4739)]
    epoch = {
        "executor_source": {"sha256": "e" * 64}, "remaining_request_ordinals": pending,
        "execution_mode": "ten_concurrent_grok_v5_waves", "max_concurrency": 10,
        "runtime_manifest": {"sha256": "m" * 64}, "runtime_package": {"manifest_sha256": "k" * 64},
        "v3_source": {"sha256": "v" * 64}, "selected_schedule": {"sha256": "s" * 64}, "plan_sha256": "p" * 64,
    }
    requests = {ordinal: {"ordinal": ordinal, "pass_id": "pass", "batch_number": ordinal, "question_ids": ["q"]}
                for ordinal in pending}
    epoch_raw = value._canonical(epoch)

    class Transport:
        def bind_grok_broker_transport(self, *, before_contact: Any, **_kwargs: Any) -> Any:
            def call(context: Any) -> tuple[str, dict[str, str]]:
                before_contact(context)
                ordinal = context["ordinal"]
                return "{}", {"request_id_sha256": sha(f"new-request-{ordinal}".encode()),
                                "session_id_sha256": sha(f"new-session-{ordinal}".encode())}
            return call

    runtime = SimpleNamespace(
        transport=Transport(), verify=lambda: None,
        runner=SimpleNamespace(_validate_grok_transport_evidence=lambda *_args: None, _parse_model_json=lambda *_args: {},
                               _normalize_batch=lambda *_args, **_kwargs: [{"question_id": "q", "verdict": "YES"}],
                               EVIDENCE_NORMALIZATION_POLICY={}),
    )

    def attempt_path(root: Path, ordinal: int, name: str) -> Path:
        return root / "attempts" / f"request-{ordinal:04d}" / name

    def prepare(**kwargs: Any) -> dict[str, Any]:
        ordinal = kwargs["ordinal"]
        context = {"ordinal": ordinal, "run": {"run_id": f"run-{ordinal}"}}
        start = {
            "ordinal": ordinal, "epoch_sha256": kwargs["epoch_sha256"], "context_sha256": sha(value._canonical(context)),
            "pass_id": "pass", "batch_number": ordinal, "question_ids": ["q"], "prompt_sha256": "a" * 64,
            "schema_sha256": "b" * 64, "wave": {"start_ordinal": kwargs["wave_start_ordinal"], "wave_size": len(kwargs["wave_ordinals"]),
                "slot_index": kwargs["slot_index"], "ordinals": list(kwargs["wave_ordinals"])},
            "review": {"path": str(kwargs["review_path"]), "sha256": kwargs["review_sha256"]}, "route_sha256": "r" * 64,
            "gate_sha256": "g" * 64,
        }
        return {"runtime": runtime, "row": requests[ordinal], "passed": {"id": "pass"}, "source": {"sha256": "z" * 64,
                "opaque_story_id": "story", "story_text": "text"}, "context": context, "run_root": kwargs["root"] / "runs" / str(ordinal),
                "question_ids": ["q"], "start": start, "start_path": attempt_path(kwargs["root"], ordinal, "attempt-start.json")}

    def terminal(**kwargs: Any) -> None:
        payload = {"ordinal": kwargs["ordinal"], "status": kwargs["status"], "contact_admitted": kwargs["contact_admitted"],
                   "provider_metadata": dict(kwargs.get("metadata") or {}), "verdicts": list(kwargs.get("verdicts") or [])}
        path = attempt_path(kwargs["root"], kwargs["ordinal"], "terminal.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value._canonical(payload))

    def settlement(root: Path, *, wave_ordinals: list[int], wave_start_sha256: str, **_kwargs: Any) -> dict[str, Any]:
        rows = []
        for ordinal in wave_ordinals:
            path = attempt_path(root, ordinal, "terminal.json")
            terminal_value = json.loads(path.read_bytes())
            row = {"ordinal": ordinal, "status": terminal_value["status"], "contact_admitted": terminal_value["contact_admitted"],
                   "terminal_sha256": sha(path.read_bytes())}
            if terminal_value["status"] == "completed":
                row["native_identity"] = {"request_id_hash": terminal_value["provider_metadata"]["request_id_sha256"],
                                          "session_id_hash": terminal_value["provider_metadata"]["session_id_sha256"]}
            rows.append(row)
        return {"epoch_sha256": "e" * 64, "ordinals": wave_ordinals, "wave_start_sha256": wave_start_sha256, "rows": rows}

    def wave_start(root: Path, *, start_ordinal: int, wave_size: int, **_kwargs: Any) -> tuple[dict[str, Any], bytes]:
        path = real._wave_path(root, start_ordinal, wave_size, "start")
        return json.loads(path.read_bytes()), path.read_bytes()

    return SimpleNamespace(
        _load_epoch=lambda *_args: (epoch, epoch_raw), _epoch_integrity=lambda *_args: (source / "plan", source / "old", source / "prefix", requests),
        _attempt_path=attempt_path, _wave_path=real._wave_path, _prepare_wave_cell=prepare, _terminal=terminal,
        _wave_settlement=settlement, _wave_start=wave_start, _broker=lambda *_args: object(), _runtime_from_epoch=lambda *_args: runtime,
        _plan=lambda *_args: ({"passes": []}, b"plan"), _pass_index=lambda *_args: {"pass": {"id": "pass"}},
        _source_for_pass=lambda *_args: {"sha256": "z" * 64, "opaque_story_id": "story", "story_text": "text"},
        _replay_suffix_terminal=lambda **kwargs: ([{"question_id": "q"}], {"request_id_hash": sha(f"new-request-{kwargs['row']['ordinal']}".encode()),
                                                                      "session_id_hash": sha(f"new-session-{kwargs['row']['ordinal']}".encode())}),
        _review=lambda *_args, **_kwargs: {"route": {"name": "route"}, "route_sha256": "r" * 64, "gate_sha256": "g" * 64},
    )


def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Path, Path, Path, list[dict[str, str]]]:
    value = load()
    source = tmp_path / "old-v5"
    failed = source / "attempts" / "request-0088"
    failed.mkdir(parents=True)
    start = {"ordinal": 88, "context_sha256": "c" * 64, "prompt_sha256": "a" * 64, "schema_sha256": "b" * 64}
    (failed / "attempt-start.json").write_bytes(value._canonical(start))
    (failed / "contact-admission.json").write_bytes(value._canonical({"ordinal": 88, "attempt_start_sha256": sha((failed / "attempt-start.json").read_bytes()), "context_sha256": "c" * 64}))
    (failed / "terminal.json").write_bytes(value._canonical({"status": "ambiguous", "contact_admitted": True}))
    protected = hashes("protected")
    monkeypatch.setattr(value, "PROTECTED_COMMITMENT", value._identity_commitment(protected))
    partial = tmp_path / "partial.json"
    partial.write_bytes(value._canonical({"counts": {"recognized_logical_requests": 90, "recognized_native_identities": 89, "recognized_verdicts": 702},
        "partial_wave": {"gap_ordinal": 88, "completed_ordinals": [82, 83, 84, 85, 86, 87, 89, 90, 91]},
        "identity_boundary": {"combined_native_count": 89, "combined_native_identity_commitment_sha256": value.PROTECTED_COMMITMENT,
                              "request_ids_unique": True, "session_ids_unique": True}}))
    monkeypatch.setattr(value, "PARTIAL_REPLAY_SHA256", sha(partial.read_bytes()))
    parent = fake_parent(value, source)
    monkeypatch.setattr(value, "_load_parent", lambda *_args: parent)
    root = tmp_path / "recovery"
    value.prepare_recovery(recovery_root=root, inner_epoch_root=source, expected_inner_epoch_sha256="e" * 64,
                           expected_parent_sha256=value.PARENT_SHA256, partial_replay_path=partial,
                           expected_partial_replay_sha256=sha(partial.read_bytes()), protected_native_identities=protected)
    return value, root, source, partial, protected


def approvals(value: Any, root: Path, source: Path, path: Path) -> tuple[Path, str, Path, str]:
    manifest = json.loads((root / "recovery-manifest.json").read_bytes())
    failed = manifest["failed_ordinal_88"]
    adoption = path / "adoption.json"
    adoption.write_bytes(value._canonical({"schema_version": 1, "decision": "approved_exactly_one_replacement_ordinal_88",
        "proposal_sha256": sha(value._canonical(manifest)), "replacement_ordinal": 88, "maximum_new_attempts_per_ordinal": 1,
        "old_failed_attempt_start_sha256": failed["attempt_start_sha256"], "old_failed_terminal_sha256": failed["terminal_sha256"],
        "prompt_sha256": failed["prompt_sha256"], "schema_sha256": failed["schema_sha256"], "execution_authority": True}))
    review = path / "parent-review.json"; review.write_text("parent")
    controller = path / "controller-review.json"
    now = datetime.now(timezone.utc)
    controller.write_bytes(value._canonical({"schema_version": 1, "decision": "approved_dryad_grok_selected_recovery_controller",
        "controller_sha256": manifest["controller_sha256"], "parent_sha256": manifest["parent_source"]["sha256"],
        "recovery_manifest_sha256": sha((root / "recovery-manifest.json").read_bytes()), "inner_epoch_sha256": manifest["inner_epoch"]["sha256"],
        "partial_replay_sha256": manifest["partial_replay"]["sha256"], "protected_identity_file_sha256": manifest["protected_native_identities"]["sha256"],
        "protected_identity_commitment_sha256": manifest["protected_native_identities"]["combined_commitment_sha256"], "adoption_sha256": sha(adoption.read_bytes()),
        "parent_review_sha256": "q" * 64, "route_sha256": "r" * 64, "gate_sha256": "g" * 64,
        "reviewed_at": now.isoformat(), "expires_at": (now + timedelta(minutes=10)).isoformat()}))
    return adoption, sha(adoption.read_bytes()), controller, sha(controller.read_bytes())


def dispatch_args(root: Path, adoption: Path, adoption_sha: str, controller: Path, controller_sha: str, tmp_path: Path) -> dict[str, Any]:
    review = tmp_path / "parent-review.json"
    return {"recovery_root": root, "adoption_path": adoption, "expected_adoption_sha256": adoption_sha,
            "reviewed_path": review, "expected_review_sha256": "q" * 64, "controller_review_path": controller,
            "expected_controller_review_sha256": controller_sha, "queue_root": tmp_path / "queue"}


def test_real_parent_contract_and_provider_free_prepare_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_spec = importlib.util.spec_from_file_location("real_grok_parent", PARENT)
    assert real_spec and real_spec.loader
    parent = importlib.util.module_from_spec(real_spec)
    real_spec.loader.exec_module(parent)
    assert set(inspect.signature(parent._prepare_wave_cell).parameters) >= {"root", "epoch_sha256", "review", "wave_ordinals"}
    assert set(inspect.signature(parent._terminal).parameters) >= {"contact_admitted", "metadata", "verdicts"}
    assert parent._wave_path(Path("x"), 92, 2, "start").name == "wave-0092-slots-02-start.json"
    value, root, source, _partial, protected = install(tmp_path, monkeypatch)
    assert (root / "suffix-epoch.json").read_bytes() == value._canonical(fake_parent(value, source)._load_epoch(None, None)[0])
    manifest = json.loads((root / "recovery-manifest.json").read_bytes())
    assert manifest["source_epoch"]["root"] == str(source.resolve())
    assert manifest["protected_native_identities"]["sha256"] == sha((root / "protected-native-identities.json").read_bytes())
    assert len(protected) == 89 and manifest["failed_ordinal_88"]["terminal_sha256"] == sha((source / "attempts/request-0088/terminal.json").read_bytes())


def test_actual_partial_proof_and_two_key_identity_commitment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    evidence = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-selected100-v5-20260910-r1")
    partial_path = evidence / "partial-wave82-native-replay.json"
    assert sha(partial_path.read_bytes()) == value.PARTIAL_REPLAY_SHA256
    value._partial(partial_path, value.PARTIAL_REPLAY_SHA256)
    old = json.loads((evidence / "protected-old-native-identities.json").read_bytes())["protected_native_identities"]
    partial = json.loads(partial_path.read_bytes())
    identities = old + [partial["bindings"]["canary81_native_replay"]["native_identity"]] + [
        item["native_identity"] for item in partial["partial_wave"]["per_request_replay"]
    ]
    two_key = [{"request_id_hash": item["request_id_hash"], "session_id_hash": item["session_id_hash"]} for item in identities]
    assert value._identity_commitment(two_key) == value.PROTECTED_COMMITMENT
    wrong = [*two_key]
    wrong[-1] = {**wrong[-1], "session_id_hash": "0" * 64}
    assert value._identity_commitment(wrong) != value.PROTECTED_COMMITMENT
    fixture = hashes("well-formed")
    monkeypatch.setattr(value, "PROTECTED_COMMITMENT", value._identity_commitment(fixture))
    identity_path = tmp_path / "identities.json"
    identity_path.write_bytes(value._canonical(fixture))
    assert value._identity_file(identity_path) == fixture
    altered = [*fixture]
    altered[-1] = {**altered[-1], "session_id_hash": sha(b"different-but-well-formed")}
    identity_path.write_bytes(value._canonical(altered))
    with pytest.raises(ValueError, match="commitment"):
        value._identity_file(identity_path)


def test_frozen_parent_terminal_and_contact_admission_artifact_contract(tmp_path: Path) -> None:
    value = load()
    spec = importlib.util.spec_from_file_location("real_grok_parent_artifacts", PARENT)
    assert spec and spec.loader
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    root, ordinal, context = tmp_path / "outer", 92, {"run": {"run_id": "fixture"}}
    start = parent._attempt_path(root, ordinal, "attempt-start.json")
    start.parent.mkdir(parents=True)
    start.write_bytes(value._canonical({"ordinal": ordinal}))
    contact = {
        "format_version": 1, "ordinal": ordinal, "epoch_sha256": "e" * 64,
        "attempt_start_sha256": sha(start.read_bytes()), "context_sha256": sha(value._canonical(context)),
        "route_sha256": "r" * 64, "gate_sha256": "g" * 64, "admitted_at": "2026-09-10T00:00:00Z",
    }
    parent._attempt_path(root, ordinal, "contact-admission.json").write_bytes(value._canonical(contact))
    parent._terminal(root=root, ordinal=ordinal, epoch_sha256="e" * 64, start_path=start, status="completed", run_root=root / "runs",
                     contact_admitted=True, context=context, content="{}", metadata={"request_id_sha256": "r" * 64}, verdicts=[])
    terminal = json.loads(parent._attempt_path(root, ordinal, "terminal.json").read_bytes())
    assert set(contact) == {"format_version", "ordinal", "epoch_sha256", "attempt_start_sha256", "context_sha256", "route_sha256", "gate_sha256", "admitted_at"}
    assert terminal["contact_admitted"] is True and terminal["attempt_start_sha256"] == sha(start.read_bytes())


def test_prepare_dispatch_settlement_and_replay_then_exact_next(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, source, _partial, protected = install(tmp_path, monkeypatch)
    adoption, adoption_sha, controller, controller_sha = approvals(value, root, source, tmp_path)
    kwargs = dispatch_args(root, adoption, adoption_sha, controller, controller_sha, tmp_path)
    replacement = value.dispatch_replacement(**kwargs)
    assert replacement["state"] == "completed_pending_replay" and replacement["provider_calls_made"] == 1
    start = root / "waves/wave-0088-slots-01-start.json"
    settlement = root / "waves/wave-0088-slots-01-settlement.json"
    assert start.is_file() and settlement.is_file() and json.loads(start.read_bytes())["ordinals"] == [88]
    with pytest.raises(ValueError, match="requires replay"):
        value.dispatch_wave(start_ordinal=92, wave_size=1, **kwargs)
    replay = value.replay_wave(recovery_root=root, start_ordinal=88, wave_size=1, approved_v5_routes={}, protected_native_identities=protected)
    assert replay["provider_calls_made"] == 0 and (root / "replays/wave-0088-slots-01.json").is_file()
    wave = value.dispatch_wave(start_ordinal=92, wave_size=2, **kwargs)
    assert wave["ordinals"] == [92, 93]
    assert json.loads((root / "waves/wave-0092-slots-02-start.json").read_bytes())["rows"][1]["ordinal"] == 93


def test_replayed_recovery_identity_is_protected_for_the_next_wave(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, source, _partial, protected = install(tmp_path, monkeypatch)
    adoption, adoption_sha, controller, controller_sha = approvals(value, root, source, tmp_path)
    kwargs = dispatch_args(root, adoption, adoption_sha, controller, controller_sha, tmp_path)
    value.dispatch_replacement(**kwargs)
    value.replay_wave(recovery_root=root, start_ordinal=88, wave_size=1, approved_v5_routes={}, protected_native_identities=protected)
    parent = value._load_parent(value.PARENT_SHA256)
    runtime = parent._runtime_from_epoch({})

    def prior_duplicate(*, before_contact: Any, **_kwargs: Any) -> Any:
        return lambda context: (before_contact(context), ("{}", {"request_id_sha256": sha(b"new-request-88"),
                                                        "session_id_sha256": sha(b"new-session-92")}))[1]

    runtime.transport.bind_grok_broker_transport = prior_duplicate
    result = value.dispatch_wave(start_ordinal=92, wave_size=1, **kwargs)
    assert result["state"] == "stopped_no_retry" and result["contact_started_ordinals"] == [92]


def test_scaled_history_validates_each_replay_receipt_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    replay_root = tmp_path / "replays"
    replay_root.mkdir()
    count, seen = 128, []
    for ordinal in range(1, count + 1):
        (replay_root / f"wave-{ordinal:04d}-slots-01.json").write_bytes(b"{}")

    def receipt(_root: Path, _parent: Any, _manifest: Any, _raw: bytes, _epoch: Any, path: Path) -> dict[str, Any]:
        ordinal = int(path.name.split("-")[1])
        seen.append(ordinal)
        return {"ordinals": [ordinal], "native_identities": [{"request_id_hash": sha(f"request-{ordinal}".encode()),
                                                                  "session_id_hash": sha(f"session-{ordinal}".encode())}]}

    monkeypatch.setattr(value, "_replay_receipt", receipt)
    completed, identities = value._validated_replay_chain(tmp_path, object(), {}, b"manifest", {})
    records = {ordinal: {"status": "completed"} for ordinal in range(1, count + 1)}
    assert completed == set(records) and len(identities) == count
    assert value._next_pending(records, [*range(1, count + 2)], completed) == count + 1
    assert len(seen) == count and sorted(seen) == list(range(1, count + 1))


def test_schedule_boundary_and_no_skip_or_resend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, source, _partial, _protected = install(tmp_path, monkeypatch)
    manifest = json.loads((root / "recovery-manifest.json").read_bytes())
    assert manifest["pending_ordinals"][:3] == [88, 92, 93]
    assert manifest["pending_ordinals"][1519:1522] == [1610, 4049, 4050]
    adoption, adoption_sha, controller, controller_sha = approvals(value, root, source, tmp_path)
    kwargs = dispatch_args(root, adoption, adoption_sha, controller, controller_sha, tmp_path)
    with pytest.raises(ValueError, match="exact next"):
        value.dispatch_wave(start_ordinal=93, wave_size=1, **kwargs)
    replacement = value.dispatch_replacement(**kwargs)
    assert replacement["provider_calls_made"] == 1
    with pytest.raises(ValueError, match="requires replay"):
        value.dispatch_replacement(**kwargs)


def test_absent_or_drifted_authorization_blocks_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, source, _partial, _protected = install(tmp_path, monkeypatch)
    adoption, adoption_sha, controller, controller_sha = approvals(value, root, source, tmp_path)
    kwargs = dispatch_args(root, adoption, adoption_sha, controller, controller_sha, tmp_path)
    with pytest.raises(ValueError, match="replacement adoption"):
        value.dispatch_replacement(**{**kwargs, "expected_adoption_sha256": "0" * 64})
    adoption.write_bytes(b"drift")
    with pytest.raises(ValueError, match="replacement adoption"):
        value.dispatch_replacement(**kwargs)


def test_callback_controller_drift_and_duplicate_identity_stop_wave(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, source, _partial, protected = install(tmp_path, monkeypatch)
    adoption, adoption_sha, controller, controller_sha = approvals(value, root, source, tmp_path)
    kwargs = dispatch_args(root, adoption, adoption_sha, controller, controller_sha, tmp_path)
    original_review, calls = value._controller_review, []

    def drift(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("controller review drift")
        return original_review(*args, **kwargs)

    monkeypatch.setattr(value, "_controller_review", drift)
    stopped = value.dispatch_replacement(**kwargs)
    assert stopped["state"] == "stopped_no_retry" and stopped["provider_calls_made"] == 0
    assert (root / "attempts/request-0088/terminal.json").is_file()
    assert calls == [1, 1] and not (root / "controller-authorizations/request-0088.json").exists()

    value, root, source, _partial, protected = install(tmp_path / "duplicate", monkeypatch)
    adoption, adoption_sha, controller, controller_sha = approvals(value, root, source, tmp_path / "duplicate")
    parent = value._load_parent(value.PARENT_SHA256)
    runtime = parent._runtime_from_epoch({})

    def duplicate_transport(*, before_contact: Any, **_kwargs: Any) -> Any:
        return lambda context: (before_contact(context), ("{}", {"request_id_sha256": protected[0]["request_id_hash"],
                                                        "session_id_sha256": sha(b"new-session-88")}))[1]

    runtime.transport.bind_grok_broker_transport = duplicate_transport
    duplicate = value.dispatch_replacement(**dispatch_args(root, adoption, adoption_sha, controller, controller_sha, tmp_path / "duplicate"))
    assert duplicate["state"] == "stopped_no_retry" and duplicate["provider_calls_made"] == 1
