"""Untouched-suffix selection preserves conditions and excludes every prefix attempt."""
from copy import deepcopy
import json
from pathlib import Path
import uuid

import pytest

import continue_manifest as continuation
from prepare import canonical, digest


def write(path: Path, value: dict) -> bytes:
    payload = canonical(value)
    path.write_bytes(payload)
    return payload


def settled_sample(results: Path, row: dict, artifacts: dict[str, bytes], *, accepted: bool) -> None:
    sample = results / f"{row['endpoint_ordinal']:04d}-{row['logical_sample_id'][:12]}"
    sample.mkdir(exist_ok=True)
    session = str(uuid.UUID(int=row["endpoint_ordinal"]))
    write(sample / "condition.json", row)
    (sample / "schema.json").write_bytes(artifacts[row["schema_path"]])
    write(sample / "native-identity.json", {"session_id": session, "logical_sample_id": row["logical_sample_id"]})
    write(sample / "attempt-started.json", {"session_id": session, "no_resend": True, "state": "before_contact"})
    terminal = {"state": "accepted" if accepted else "ambiguous", "accepted": accepted, "no_resend": True}
    native = {"state": "completed" if accepted else "ambiguous", "result": None}
    if accepted:
        response = {"answer": "Synthetic response."}
        envelope_raw = write(sample / "native-envelope.json", {"structuredOutput": response, "sessionId": session})
        native["result"] = {
            "output": response, "output_hash": digest(canonical(response)[:-1]),
            "request_hash": digest(canonical({"prompt": artifacts[row["prompt_path"]].decode()})[:-1]),
            "native_envelope_artifact": {"sha256": digest(envelope_raw), "byte_length": len(envelope_raw)},
            "runtime": {"session_id_hash": digest(session.encode()), "requested_model": "grok-4.7",
                        "reported_model": "grok-4.7-build",
                        "execution_contract": {"output_schema_hash": digest(canonical(json.loads(artifacts[row["schema_path"]]))[:-1])}},
        }
        terminal["response_sha256"] = digest(write(sample / "response.json", response))
        terminal["acceptance_sha256"] = digest(write(sample / "acceptance.json", {"accepted": True, "abstention": False, "errors": []}))
        terminal["native_result_sha256"] = digest(canonical(native))
    write(sample / "native-result.json", native)
    write(sample / "terminal.json", terminal)


@pytest.fixture
def frozen(tmp_path):
    root, results = tmp_path / "frozen", tmp_path / "prefix"
    root.mkdir(); results.mkdir()
    artifacts = {"prompt.txt": b"Synthetic story.\n", "schema.json": canonical({"type": "object"}),
                 "input.txt": b"Synthetic story.", "context.txt": b"Frozen context.", "REGISTRATION.md": b"Frozen registration.\n"}
    for name, payload in artifacts.items():
        (root / name).write_bytes(payload)
    rows = []
    for ordinal in range(1, 9):
        for endpoint in ("grok", "sol"):
            row = {"endpoint": endpoint, "endpoint_ordinal": ordinal, "ordinal": len(rows) + 1,
                   "logical_sample_id": f"{ordinal:064x}", "arm": "hbq", "repeat": int(ordinal == 8),
                   "question_ids": ["synthetic-question"], "sources": [{"id": "story", "input_path": "input.txt", "sha256": digest(artifacts["input.txt"])}],
                   "prompt_path": "prompt.txt", "prompt_sha256": digest(artifacts["prompt.txt"]), "prompt_bytes": len(artifacts["prompt.txt"]),
                   "schema_path": "schema.json", "schema_sha256": digest(artifacts["schema.json"]), "schema_bytes": len(artifacts["schema.json"])}
            row["request_sha256"] = digest(canonical(row))
            rows.append(row)
    manifest = {"schema_version": 1, "requests": rows, "execution_authority": False,
                "counts": {"requests_total": 16}, "bytes": {"unique_artifacts_total": sum(map(len, artifacts.values()))},
                "artifacts": {name: {"sha256": digest(payload), "bytes": len(payload)} for name, payload in artifacts.items()}}
    manifest["manifest_content_sha256"] = digest(canonical(manifest))
    manifest_path = root / "manifest.json"
    raw_manifest = write(manifest_path, manifest)
    write(results / "job.json", {"endpoint": "grok", "manifest_sha256": digest(raw_manifest), "model": "grok-4.7",
                                  "route": {"reported_model": "grok-4.7-build", "timeout_seconds": 300}})
    grok = [row for row in rows if row["endpoint"] == "grok"]
    for row in grok[:6]:
        settled_sample(results, row, artifacts, accepted=row["endpoint_ordinal"] != 6)
    return manifest_path, results, manifest, artifacts, grok


def test_suffix_preserves_all_conditions_repeat_identity_and_exact_source_bytes(frozen):
    path, results, original, source_artifacts, grok = frozen
    before = deepcopy(original)
    descendant, artifacts = continuation.build(path, results)
    assert descendant["requests"] == grok[6:]
    assert [row["endpoint_ordinal"] for row in descendant["requests"]] == [7, 8]
    assert descendant["requests"][1]["repeat"] == 1
    assert descendant["historical_registration"]["counts"] == original["counts"]
    assert descendant["counts"]["requests_total"] == 2
    assert descendant["counts"]["initial_requests_per_endpoint"] == 1
    assert descendant["continuation"]["prefix_receipts"][-1]["native_state"] == "ambiguous"
    assert descendant["continuation"]["requested_runtime_timeout_seconds"] == 900
    assert artifacts["lineage/parent-manifest.json"] == path.read_bytes()
    assert all(artifacts[name] == payload for name, payload in source_artifacts.items())
    assert original == before


def test_prefix_outcomes_never_change_suffix_selection(frozen):
    path, results, _, artifacts, grok = frozen
    previous, _ = continuation.build(path, results)
    settled_sample(results, grok[5], artifacts, accepted=True)
    changed, _ = continuation.build(path, results)
    assert previous["requests"] == changed["requests"] == grok[6:]
    assert previous["continuation"]["prefix_receipts"] != changed["continuation"]["prefix_receipts"]


def test_unsettled_prefix_blocks_continuation(frozen):
    path, results, _, _, grok = frozen
    (results / f"0006-{grok[5]['logical_sample_id'][:12]}" / "terminal.json").unlink()
    with pytest.raises(ValueError, match="unsettled"):
        continuation.build(path, results)


def test_any_suffix_attempt_prevents_reselection_even_without_terminal(frozen):
    path, results, _, _, grok = frozen
    (results / f"0007-{grok[6]['logical_sample_id'][:12]}").mkdir()
    with pytest.raises(ValueError, match="suffix already contains an attempt"):
        continuation.build(path, results)


@pytest.mark.parametrize("damage", ["condition", "artifact", "native", "manifest"])
def test_changed_retained_evidence_blocks_preparation(frozen, damage):
    path, results, _, _, grok = frozen
    sample = results / f"0001-{grok[0]['logical_sample_id'][:12]}"
    if damage == "condition":
        changed = deepcopy(grok[0]); changed["repeat"] = 2
        write(sample / "condition.json", changed)
    elif damage == "artifact":
        (path.parent / "input.txt").write_bytes(b"Changed source.")
    elif damage == "native":
        write(sample / "native-result.json", {"state": "ambiguous", "result": None})
    else:
        value = json.loads(path.read_bytes()); value["counts"]["requests_total"] = 15
        write(path, value)
    with pytest.raises(ValueError):
        continuation.build(path, results)


def test_output_must_be_fresh_and_outside_repo_or_retained_inputs(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    for output in (source / "descendant", source, continuation.REPO / "private-evidence"):
        with pytest.raises(ValueError):
            continuation.fresh_private_output(output, source)
    occupied = tmp_path / "occupied"; occupied.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        continuation.fresh_private_output(occupied, source)
