from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_successor_collection_replay.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("successor_collection_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def identity(number: int) -> dict[str, str]:
    return {"request_id_hash": sha(f"request-{number}".encode()), "session_id_hash": sha(f"session-{number}".encode())}


def _fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, fault: str | None = None) -> tuple[Any, dict[str, Any], list[tuple[int, Path]]]:
    value = load()
    questions = [f"q-{number:03d}" for number in range(value.QUESTION_COUNT)]
    plan_root, old_root, recovery_root, first_root, second_root = (tmp_path / name for name in ("plan", "old", "recovery", "first", "second"))
    for root in (plan_root, old_root, recovery_root, first_root, second_root):
        root.mkdir()
    passes = []
    requests: list[dict[str, Any]] = []
    for index in range(206):
        record = {"pass_id": f"pass-{index:03d}", "partition": "TRAIN" if index < 70 else "DEV",
                  "opaque_story_id": f"story-{index:03d}", "source_sha256": sha(f"source-{index}".encode()), "source_bytes": index}
        passes.append(record)
        for batch in range(23):
            start = batch * 8
            requests.append({"ordinal": index * 23 + batch + 1, "pass_id": record["pass_id"], "batch_number": batch + 1,
                             "question_ids": questions[start:start + (8 if batch < 22 else 2)]})
    by_ordinal = {row["ordinal"]: row for row in requests}
    selected_schedule = [*range(1, 1611), *range(4049, 4739)]
    runtime = SimpleNamespace(core=SimpleNamespace(score_bundle=lambda *_args, **_kwargs: {"final_score": {"observed": 50}, "coverage": .9}),
                              modules={}, bundle={}, transport_sha256="t" * 64)
    calls: list[tuple[int, Path]] = []

    def attempt_path(root: Path, ordinal: int, _name: str) -> Path:
        partial_terminal = root / "attempts" / f"request-{ordinal:04d}" / "terminal.json"
        if partial_terminal.is_file():
            return partial_terminal
        if root.name == "local-continuation":
            path = root / "synthetic-native-terminal.json"
            if not path.exists():
                path.write_bytes(b"local-continuation")
            return path
        path = root / "synthetic-native-terminal.json"
        if not path.exists():
            path.write_bytes(root.name.encode())
        return path

    def replay_terminal(*, root: Path, row: Mapping[str, Any], **_kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        calls.append((row["ordinal"], root))
        return ([{"question_id": question, "verdict": "YES"} for question in row["question_ids"]], identity(row["ordinal"]))

    suffix = SimpleNamespace(__file__="synthetic-suffix", _runtime_from_epoch=lambda _epoch: runtime,
                             _attempt_path=attempt_path, _replay_suffix_terminal=replay_terminal)
    context = SimpleNamespace(
        suffix=suffix, old_runtime=runtime,
        old_passes=[{"pass_id": record["pass_id"], "run_root": str(old_root / record["pass_id"])} for record in passes[:3]],
        epoch={"selected_request_ordinals": selected_schedule, "selected_schedule": {"sha256": "s" * 64},
               "selected_schedule_source": {"sha256": "u" * 64}, "recovered_study_source": {"path": "recovered", "sha256": "r" * 64},
               "old_prefix_run_root": str(old_root / "prefix"), "recovered_study_manifest": {"sha256": "m" * 64},
               "recovery_adoption_sha256": "a" * 64, "recovery_amendment_sha256": "z" * 64},
    )
    historical = [identity(10_000 + number) for number in range(33)]
    historical_path = tmp_path / "historical.json"
    historical_raw = canonical({"records": historical})
    historical_path.write_bytes(historical_raw)
    predecessor = {"identity_exclusion": {"path": str(historical_path), "sha256": sha(historical_raw)}}

    def old_admit(_context: Any, *, pass_record: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any]:
        index = passes.index(pass_record)
        return {"verdicts": [{"question_id": question, "verdict": "YES"} for question in questions],
                "native_identities": [{**identity(ordinal), "observed_turns": 1} for ordinal in range(index * 23 + 1, index * 23 + 24)],
                "run_manifest_sha256": "d" * 64, "checkpoint_head_sha256": "e" * 64}

    class Recovered:
        @staticmethod
        def admit_prefix(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            verdicts = [verdict for ordinal in range(70, 81) for verdict in
                        [{"question_id": question, "verdict": "YES"} for question in by_ordinal[ordinal]["question_ids"]]]
            return {"verdicts": verdicts, "native_identities": [identity(ordinal) for ordinal in range(71, 81)],
                    "run_manifest_sha256": "f" * 64, "checkpoint_head_sha256": "g" * 64, "recovered_manifest_sha256": "m" * 64}

    composite = SimpleNamespace(
        _predecessor=lambda *_args: (b"predecessor", predecessor),
        _actual_replay_context=lambda **_kwargs: context,
        _plan=lambda *_args: ({"requests": requests, "passes": passes}, b"plan", passes, {record["pass_id"]: record for record in passes}, questions),
        _actual_old_admit=old_admit, _load_module=lambda *_args: Recovered(),
        _measurement_source=lambda *_args: {"opaque_story_id": "story-003", "story_text": "", "artifact_path": ""},
    )
    recovery_ordinals = {88, *range(92, 202)}
    first_partial_ordinals, first_failed = [202, 204, 206, 207, 208, 209, 210], [203, 205, 211]
    first_ordinals = {203, 205, 211, *range(212, 252)}
    second_partial_ordinals, second_failed = [252, 253, 255, 256, 257, 258, 259, 260, 261], [254]
    second_ordinals = {254, *range(262, 1611), *range(4049, 4739)}
    if fault == "gap":
        second_ordinals.remove(4738)
    if fault == "overlap":
        first_ordinals.add(88)
    recovery_manifest = {"controller_sha256": value.RECOVERY_SHA256, "parent_source": {"sha256": value.SUFFIX_SHA256},
                         "inner_epoch": {"sha256": "e" * 64}, "pending_ordinals": sorted(value.SUCCESSOR_SCHEDULE),
                         "protected_native_identities": {"path": str(tmp_path / "protected.json"), "sha256": "p" * 64},
                         "source_epoch": {"sha256": "x" * 64}, "source_epoch_inventory": {"sha256": "i" * 64}, "partial_replay": {"sha256": "r" * 64}}
    recovery_raw = canonical(recovery_manifest)
    (recovery_root / "recovery-manifest.json").write_bytes(recovery_raw)
    recovery = SimpleNamespace(
        _load_parent=lambda _hash: suffix,
        _inner=lambda *_args: ({"plan_sha256": "p" * 64}, b"epoch", plan_root, by_ordinal),
        _source_guard=lambda *_args: None,
        _validated_replay_chain=lambda *_args: (recovery_ordinals, [identity(ordinal) for ordinal in sorted(recovery_ordinals)]),
        _identity_file=lambda *_args: [],
    )

    manifests: dict[Path, tuple[dict[str, Any], bytes, set[int]]] = {}
    partials: dict[Path, dict[str, Any]] = {}

    def partial(source: Path, completed: list[int], failed: list[int], controller_sha: str, manifest_sha: str) -> dict[str, Any]:
        records = []
        for ordinal in completed:
            terminal_path = source / "attempts" / f"request-{ordinal:04d}" / "terminal.json"
            terminal_path.parent.mkdir(parents=True, exist_ok=True)
            terminal_raw = canonical({"status": "completed", "provider_metadata": {"request_id_sha256": identity(ordinal)["request_id_hash"], "session_id_sha256": identity(ordinal)["session_id_hash"]}})
            terminal_path.write_bytes(terminal_raw)
            records.append({"ordinal": ordinal, "terminal_sha256": sha(terminal_raw), "native_identity": identity(ordinal)})
        failed_attempts = []
        for ordinal in failed:
            attempt = source / "attempts" / f"request-{ordinal:04d}"
            attempt.mkdir(parents=True, exist_ok=True)
            start = {"ordinal": ordinal, "prompt_sha256": "p" * 64, "schema_sha256": "s" * 64, "question_ids": by_ordinal[ordinal]["question_ids"]}
            start_raw = canonical(start); contact_raw = canonical({"contact": ordinal}); terminal_raw = canonical({"status": "ambiguous"})
            (attempt / "attempt-start.json").write_bytes(start_raw)
            (attempt / "contact-admission.json").write_bytes(contact_raw)
            (attempt / "terminal.json").write_bytes(terminal_raw)
            failed_attempts.append({"ordinal": ordinal, "attempt_start_sha256": sha(start_raw), "contact_admission_sha256": sha(contact_raw),
                                    "terminal_sha256": sha(terminal_raw), "prompt_sha256": "p" * 64, "schema_sha256": "s" * 64,
                                    "question_ids": by_ordinal[ordinal]["question_ids"], "retained_complete_answer": False})
        identities = [identity(ordinal) for ordinal in completed]
        return {"schema_version": 1, "evidence_class": "source_bound_partial_recovery_wave_replay_v1", "controller_sha256": controller_sha,
                "recovery_manifest_sha256": manifest_sha, "inner_epoch_sha256": "e" * 64, "prior_logical_count": 1,
                "recognized_logical_count": 1 + len(completed), "recognized_native_identity_count": len(identities),
                "partial_criterion_verdict_count": len(completed), "failed_wave_admitted": False, "resend_authority": False,
                "provider_calls_made": 0, "completed_ordinals": completed, "failed_ordinals": failed, "failed_attempts": failed_attempts,
                "records": records, "native_identities": identities, "all_protected_native_identities": identities,
                "all_protected_native_identity_commitment_sha256": sha(canonical(identities)), "wave_start_sha256": "w" * 64,
                "settlement_sha256": "z" * 64}

    for root, ordinals, prior, completed, failed in ((first_root, first_ordinals, recovery_root, first_partial_ordinals, first_failed),
                                                       (second_root, second_ordinals, first_root, second_partial_ordinals, second_failed)):
        raw = canonical({"root": root.name, "ordinals": sorted(ordinals)})
        manifest = {"prior_root": str(prior), "partial_202": {"path": str(tmp_path / f"partial-{root.name}.json"), "sha256": "q" * 64},
                    "prior_controller_sha256": "y" * 64, "pending_ordinals": sorted(ordinals),
                    "predecessor_root_ownership": {"successor_replacements": [203, 205, 211] if root == first_root else [400]},
                    "controller_sha256": value.SUCCESSOR_SHA256, "inner_epoch": {"sha256": "e" * 64},
                    "prior_manifest_sha256": "h" * 64, "parent_sha256": value.SUFFIX_SHA256,
                    "prior_inventory": {"sha256": "v" * 64}, "protected_native_identities": {"sha256": "w" * 64}}
        if fault == "lineage" and root == first_root:
            manifest["prior_root"] = str(tmp_path / "wrong")
        manifests[root] = (manifest, raw, ordinals)
        partials[Path(manifest["partial_202"]["path"])] = partial(prior, completed, failed, manifest["prior_controller_sha256"], manifest["prior_manifest_sha256"])

    def verify_partial(source: Path, item: Mapping[str, Any], manifest_sha: str, controller_sha: str, _requests: Mapping[int, Any]) -> None:
        assert item["controller_sha256"] == controller_sha and item["recovery_manifest_sha256"] == manifest_sha
        for record in item["records"]:
            terminal = source / "attempts" / f"request-{record['ordinal']:04d}" / "terminal.json"
            payload = json.loads(terminal.read_bytes())
            assert record["terminal_sha256"] == sha(terminal.read_bytes())
            assert record["native_identity"] == {"request_id_hash": payload["provider_metadata"]["request_id_sha256"], "session_id_hash": payload["provider_metadata"]["session_id_sha256"]}

    controller = SimpleNamespace(
        PRIOR=tmp_path / "unused-prior.py", PRIOR_SHA="n" * 64,
        _manifest=lambda root: manifests[root][:2], _partial=lambda path, *_args: partials[Path(path)], _verify_partial_source=verify_partial,
        _source_guard=lambda *_args: ({"plan_sha256": "p" * 64}, b"epoch", plan_root, by_ordinal),
        _validated_replays=lambda root, *_args: (manifests[root][2], [identity(ordinal) for ordinal in sorted(manifests[root][2])]),
    )
    modules = {value.COMPOSITE: composite, value.SUFFIX: suffix, value.RECOVERY: recovery, value.SUCCESSOR: controller}
    monkeypatch.setattr(value, "_module", lambda path, *_args: modules[path])
    descriptors = [{"root": str(root), "manifest_sha256": sha(raw)} for root, (_manifest, raw, _ordinals) in manifests.items()]
    inputs = {"plan_root": plan_root, "predecessor_path": tmp_path / "predecessor", "old_suffix_root": old_root, "recovery_root": recovery_root,
              "expected_plan_sha256": "p" * 64, "expected_predecessor_sha256": "b" * 64, "expected_old_epoch_sha256": "o" * 64,
              "expected_suffix_source_sha256": value.SUFFIX_SHA256, "expected_recovery_controller_sha256": value.RECOVERY_SHA256,
              "expected_recovery_manifest_sha256": sha(recovery_raw), "approved_v4_routes": {}, "approved_v5_routes": {}, "successor_roots": descriptors}
    if fault == "identity":
        first_identity = identity(88)
        controller._validated_replays = lambda root, *_args: (manifests[root][2], [first_identity if ordinal == 203 else identity(ordinal) for ordinal in sorted(manifests[root][2])])
    return value, inputs, calls


def test_full_synthetic_orchestration_assembles_every_story_and_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    value, inputs, calls = _fixture(monkeypatch, tmp_path)
    result = value.read_selected_successor_collection(**inputs)
    assert result["counts"] == {"stories": 100, "logical_requests": 2300, "native_requests": 2299,
                                "study_recovered_requests": 1, "criterion_verdicts": 17800}
    assert len(result["rows"]) == 100 and len(result["normalized_verdict_rows"]) == 17800
    assert len(result["native_identities"]) == 2299 and len(result["historical_excluded_native_identities"]) == 33
    assert result["coverage_failures"] == [] and result["provider_calls_made"] == 0 and result["full_study_admitted"] is False
    roots = dict(calls)
    chain = result["successor_root_chain"]
    assert roots[81].name == "old" and roots[88].name == "recovery" and roots[203] == Path(chain[0]["root"])
    assert roots[202].name == "recovery" and roots[252] == Path(chain[0]["root"])
    assert roots[254] == Path(chain[1]["root"]) and roots[4049] == Path(chain[1]["root"])
    assert result["root_chain_ordinal_owners"][88]["kind"] == "first_recovery"
    assert result["root_chain_ordinal_owners"][202]["kind"] == "partial_predecessor_peer"
    assert result["root_chain_ordinal_owners"][202]["root"] == str(tmp_path / "recovery")
    assert result["root_chain_ordinal_owners"][252]["kind"] == "partial_predecessor_peer"
    assert result["root_chain_ordinal_owners"][252]["root"] == str(tmp_path / "first")
    assert result["input_commitments"]["successor_root_chain_sha256"] == sha(canonical(chain))


@pytest.mark.parametrize("fault, message", [("gap", "incomplete"), ("overlap", "ownership collision"), ("lineage", "lineage"), ("identity", "identity")])
def test_root_chain_rejects_gaps_overlaps_lineage_and_identity_collisions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fault: str, message: str) -> None:
    value, inputs, _calls = _fixture(monkeypatch, tmp_path, fault=fault)
    with pytest.raises(ValueError, match=message):
        value.read_selected_successor_collection(**inputs)


def test_identity_and_descriptor_guards() -> None:
    value = load()
    with pytest.raises(ValueError, match="duplicate"):
        value._unique([identity(1), identity(1)])
    with pytest.raises(ValueError, match="descriptor"):
        value._descriptor({"root": "."})


def _local_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, fault: str | None = None) -> tuple[Any, dict[str, Any], list[tuple[int, Path]]]:
    value, inputs, calls = _fixture(monkeypatch, tmp_path)
    continuation_root = tmp_path / "local-continuation"
    continuation_root.mkdir()
    successor = inputs["successor_roots"][0]
    controller_hash = "c" * 64
    manifest_hash = "b" * 64
    local_identity = {"kind": "local_schema_projection", "ordinal": 254,
                      "projection_sha256": value.LOCAL_PROJECTION_SHA256,
                      "identity_sha256": sha(canonical({"kind": "local_schema_projection", "ordinal": 254,
                                                          "projection_sha256": value.LOCAL_PROJECTION_SHA256}))}
    if fault == "projection":
        local_identity["projection_sha256"] = "d" * 64
    source = {"root": str(continuation_root), "manifest_sha256": manifest_hash, "controller_sha256": controller_hash,
              "successor_root": successor["root"], "successor_manifest_sha256": successor["manifest_sha256"],
              "partial_sha256": "889429a738d3b7724abc7652518d5fab46041b5db4db1c4fb3ae9db85752a1e2", "inner_epoch_sha256": "e" * 64}
    if fault == "source":
        source["successor_root"] = str(tmp_path / "wrong")
    expected = [*range(262, 1611), *range(4049, 4739)]
    native_identities = [identity(ordinal) for ordinal in expected]
    if fault == "identity":
        native_identities[0] = identity(203)
    provenance = {"proposal_sha256": "a" * 64, "adoption_sha256": value.LOCAL_ADOPTION_SHA256,
                  "independent_review_sha256": "r" * 64, "standing_authority_sha256": "s" * 64,
                  "original_message_sha256": "o" * 64, "projected_message_sha256": value.LOCAL_PROJECTION_SHA256,
                  "source_story_sha256": "f" * 64, "ordinary_native_admission": False, "new_provider_attempts_authorized": 0}
    peer_ordinals = [252, 253, 255, 256, 257, 258, 259, 260, 261]
    peer_records = []
    for ordinal in peer_ordinals:
        terminal = Path(successor["root"]) / "attempts" / f"request-{ordinal:04d}" / "terminal.json"
        peer_records.append({"ordinal": ordinal, "criterion_verdict_count": len([f"q-{number:03d}" for number in range(8)]),
                             "native_identity": identity(ordinal), "terminal_sha256": sha(terminal.read_bytes()),
                             "controller_authorization_sha256": sha(f"partial-authorization-{ordinal}".encode())})
    protected_paths = {"continuation_root": {"path": str(continuation_root), "inventory_sha256": "i" * 64},
                       "continuation_manifest": {"path": str(continuation_root / "local-continuation-manifest.json"), "sha256": manifest_hash},
                       "controller": {"path": str(value.LOCAL_CONTINUATION.resolve()), "sha256": controller_hash},
                       "successor_root": {"path": successor["root"], "inventory_sha256": "i" * 64},
                       "successor_manifest": {"path": str(Path(successor["root"]) / "successor-manifest.json"), "sha256": successor["manifest_sha256"]},
                       "partial": {"path": str(tmp_path / "partial-second.json"), "sha256": source["partial_sha256"]},
                       "proposal": {"path": "proposal", "sha256": "a" * 64}, "adoption": {"path": "adoption", "sha256": value.LOCAL_ADOPTION_SHA256},
                       "independent_review": {"path": "review", "sha256": "r" * 64}, "standing_authority": {"path": "standing", "sha256": "s" * 64},
                       "local_projection": {"path": "projection", "sha256": value.LOCAL_PROJECTION_SHA256},
                       "protected_native_identities": {"path": "identities", "sha256": "n" * 64}, "inner_epoch": {"path": "epoch", "sha256": "e" * 64}}
    local = {"ordinal": 254, "evidence_class": "owner_adopted_local_session_schema_recovery",
             "verdicts": [{"question_id": f"q-{number:03d}", "verdict": "YES"} for number in range(8)],
             "local_identity": local_identity, "local_provenance": provenance,
             "ownership": {"protected_native_identity_count": 259, "local_recovery_ordinals": [70, 254], "never_contact_ordinals": [254]},
             "source": source, "protected_paths": protected_paths, "partial_peer_records": peer_records,
             "partial_peer_source": {"root": successor["root"], "successor_manifest_sha256": successor["manifest_sha256"],
                                     "inner_epoch_sha256": "e" * 64, "partial": {"path": str(tmp_path / "partial-second.json"), "sha256": source["partial_sha256"]}},
             "provider_calls_made": 0, "full_original_study_admitted": False,
             "review_decision": "GO_for_explicit_LOCAL_schema_recovered_adoption", "standing_authority_kind": "standing"}
    native = {"untouched_replay_ordinals": expected, "untouched_native_identities": native_identities,
              "untouched_terminals": [{"ordinal": ordinal, "terminal_sha256": sha(b"local-continuation"),
                                       "controller_authorization_sha256": sha(f"authorization-{ordinal}".encode())} for ordinal in expected],
              "provider_calls_made": 0, "protected_native_identity_count": 259}
    continuation = SimpleNamespace(
        verify_local_continuation=lambda **_kwargs: local,
        verify_untouched_replay_chain=lambda **_kwargs: native,
    )
    prior_loader = value._module
    monkeypatch.setattr(value, "_module", lambda path, *args: continuation if path == value.LOCAL_CONTINUATION else prior_loader(path, *args))
    inputs["successor_roots"] = [successor]
    inputs["local_continuation"] = {"root": str(continuation_root), "manifest_sha256": manifest_hash, "controller_sha256": controller_hash}
    inputs["allow_legacy_local_v2_fixture"] = True
    return value, inputs, calls


def test_local_continuation_owns_254_without_a_native_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    value, inputs, calls = _local_fixture(monkeypatch, tmp_path)
    result = value.read_selected_successor_collection(**inputs)
    assert result["evidence_class"] == "selected100_grok_successor_local_schema_recovery_replay_only_v2"
    assert result["counts"] == {"stories": 100, "logical_requests": 2300, "native_requests": 2298,
                                "study_recovered_requests": 1, "criterion_verdicts": 17800, "local_recovered_requests": 1}
    assert result["recovered_ordinals"] == [70, 254] and 254 not in dict(calls)
    assert result["root_chain_ordinal_owners"][254]["kind"] == "local_schema_recovery"
    assert result["root_chain_ordinal_owners"][252]["kind"] == "partial_predecessor_peer"
    assert result["root_chain_ordinal_owners"][262]["kind"] == "local_continuation_native"
    assert result["local_recovery_identity"]["kind"] == "local_schema_projection"
    assert result["local_recovery_identity"] not in result["native_identities"]
    assert result["local_recovery_protected_paths"]["controller"]["sha256"] == inputs["local_continuation"]["controller_sha256"]
    assert result["rows"][11]["verdict_rows"][:8] == [{"question_id": f"q-{number:03d}", "verdict": "YES"} for number in range(8)]


def _candidate_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Any, dict[str, Any], list[tuple[int, Path]]]:
    value, inputs, calls = _local_fixture(monkeypatch, tmp_path)
    inputs.pop("allow_legacy_local_v2_fixture")
    root = tmp_path / "standing-v6"; root.mkdir()
    manifest_hash, controller_hash = "b" * 64, "c" * 64
    expected = [*range(262, 1611), *range(4049, 4739)]
    local_root = inputs["local_continuation"]["root"]

    def questions(ordinal: int) -> list[str]:
        batch = (ordinal - 1) % 23
        return [f"q-{number:03d}" for number in range(batch * 8, batch * 8 + (8 if batch < 22 else 2))]

    candidate = {"root": "candidate-root", "manifest_sha256": "d" * 64}
    packet, standing = {"path": "packet", "sha256": "e" * 64}, {"path": "standing", "sha256": "f" * 64}
    verified = {"evidence_class": "dryad_grok_standing_v6_prospective_continuation_v1", "pending_ordinals": expected,
                "prefix": {"source": {"root": local_root}}, "candidate": candidate, "packet": packet,
                "standing_source": standing, "protected_paths": {"controller": {"path": "controller", "sha256": controller_hash}}, "provider_calls_made": 0}
    replay = {"candidate_native_replay_ordinals": expected, "candidate_native_identities": [identity(ordinal) for ordinal in expected],
              "candidate_native_terminals": [{"ordinal": ordinal, "terminal_sha256": sha(f"candidate-{ordinal}".encode()), "native_identity": identity(ordinal)} for ordinal in expected],
              "candidate_native_verdicts": {ordinal: {"terminal_sha256": sha(f"candidate-{ordinal}".encode()), "question_ids": questions(ordinal),
                                                   "verdicts": [{"question_id": question, "verdict": "YES"} for question in questions(ordinal)]} for ordinal in expected},
              "candidate": candidate, "packet": packet, "standing_source": standing,
              "queue": {"path": "queue", "root_hash": "a" * 64, "path_sha256": "a" * 64}, "provider_calls_made": 0}
    controller = SimpleNamespace(verify_standing_v6_continuation=lambda **_kwargs: verified,
                                 verify_standing_v6_replay_chain=lambda **_kwargs: replay)
    prior_loader = value._module
    monkeypatch.setattr(value, "_module", lambda path, *args: controller if path == value.STANDING_V6_CONTINUATION else prior_loader(path, *args))
    inputs["candidate_native_continuation"] = {"root": str(root), "manifest_sha256": manifest_hash, "controller_sha256": controller_hash}
    return value, inputs, calls


def test_candidate_v6_replay_replaces_obsolete_v2_native_suffix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    value, inputs, calls = _candidate_fixture(monkeypatch, tmp_path)
    result = value.read_selected_successor_collection(**inputs)
    assert result["schema_version"] == 3 and result["historical_prototype_only"] is False
    assert result["evidence_class"] == "selected100_grok_successor_standing_v6_candidate_replay_only_v3"
    assert result["counts"]["native_requests"] == 2298 and len(result["native_identities"]) == 2298
    assert result["root_chain_ordinal_owners"][262]["kind"] == "standing_v6_candidate_native"
    assert result["standing_v6_candidate_protected_paths"] == {"controller": {"path": "controller", "sha256": "c" * 64}}
    assert 254 not in dict(calls) and 262 not in dict(calls)


def test_local_v2_requires_candidate_unless_explicitly_private(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    value, inputs, _calls = _local_fixture(monkeypatch, tmp_path)
    inputs.pop("allow_legacy_local_v2_fixture")
    with pytest.raises(ValueError, match="standing v6"):
        value.read_selected_successor_collection(**inputs)


@pytest.mark.parametrize("fault, message", [("projection", "identity"), ("source", "source binding"), ("identity", "duplicate")])
def test_local_continuation_rejects_projection_source_and_native_identity_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fault: str, message: str) -> None:
    value, inputs, _calls = _local_fixture(monkeypatch, tmp_path, fault=fault)
    with pytest.raises(ValueError, match=message):
        value.read_selected_successor_collection(**inputs)
