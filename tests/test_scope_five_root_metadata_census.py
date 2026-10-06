import importlib.util
import json
from pathlib import Path
import tempfile

import pytest


PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-scope-five-root-metadata-census-v1/census.py"
spec = importlib.util.spec_from_file_location("tested_five_root_metadata", PATH)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def test_lexical_skip_and_repeated_prompt_preserve_dual_ordered_identities():
    condition = {name: "metadata" for name in (*c.CONDITION, "question_sha256")}
    condition["leaf_id"] = "scope.passage.status"
    rows = [{"slot_id": f"slot-{i}", "logical_sample_id": f"manifest-{i}", "repeat": i,
             "leaf_id": "scope.passage.status", "fixture_commitment_sha256": "a" * 64,
             "condition": condition} for i in (1, 2)]
    raw = (json.dumps({"study_id": "synthetic", "planned_slots": 2, "slots": rows})[:-1] +
           ',"artifact_text":"\\uZZZZ","expected_verdict":"\\uZZZZ","evidence":"\\uZZZZ"}').encode()
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    manifest = c.projection("semantic", "manifest", raw)
    runtime = {"slots": [{**row, "logical_sample_id": f"runtime-{i}", "rendered_prompt_sha256": "b" * 64}
                         for i, row in enumerate(rows, 1)]}
    item = {"id": "semantic", "geometry": {"planned_slots": 2, "logical_id_mismatches": 2}}
    ledger, observed = c.membership(item, manifest, runtime)
    assert len(ledger) == 2 and observed["distinct_runtime_prompt_commitments"] == 1
    assert observed["repeat_membership"] == {"1": 1, "2": 1}
    assert ledger[0]["manifest"]["logical_sample_id"] == "manifest-1"
    assert ledger[0]["runtime"]["logical_sample_id"] == "runtime-1"
    assert observed["joins"]["manifest_logical_ids_sha256"] != observed["joins"]["runtime_logical_ids_sha256"]
    assert observed["current_admission_verified"] is False and observed["physical_contact_cardinality"] is None
    with pytest.raises(ValueError, match="Ordered slot"):
        c.membership(item, manifest, {"slots": list(reversed(runtime["slots"]))})


def test_reuse_is_not_new_membership_and_clean_terminal_is_only_opaque():
    rows = [{"slot_id": f"new-{i}", "logical_sample_id": f"manifest-{i}", "repeat": i,
             "leaf_id": "scope.passage.status"} for i in (1, 2)]
    manifest = {"slots": rows, "planned_new_calls": 2, "reused_accepted_calls": 6}
    runtime = {"slots": [{**row, "logical_sample_id": f"runtime-{i}", "rendered_prompt_sha256": "x"}
                         for i, row in enumerate(rows, 1)]}
    item = {"id": "treatment", "geometry": {"planned_slots": 2, "logical_id_mismatches": 2,
                                               "reused_predecessor_declarations": 6}}
    ledger, observed = c.membership(item, manifest, runtime)
    assert len(ledger) == observed["planned_new_positions"] == 2
    assert observed["reused_predecessor_declarations_excluded_from_new_positions"] == 6
    assert observed["exact_reuse_binding"] == "unresolved_not_inspected"
    clean_rows = [{"opaque_slot_id": "opaque", "logical_sample_id": "original", "repeat": 1,
                   "condition": {"leaf_id": "form.poetry.free_verse.repetition"}}]
    clean = {"id": "clean", "geometry": {"planned_slots": 1}}
    terminal = c.projection("clean", "terminal_opaque_membership",
                            b'[{"opaque_slot_id":"opaque","verdict":"\\uZZZZ","note":"\\uZZZZ"}]')
    _, selected = c.membership(clean, {"slots": clean_rows, "planned_slots": 1}, terminal)
    assert selected["native_request_run_ancestry"] == "unresolved"
    assert selected["joins"]["terminal_opaque_ids_equal_in_order"] is True
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "source"
        path.write_bytes(b"original")
        with pytest.raises(ValueError, match="Pinned source"):
            c.checked(path, {"sha256": c.sha(b"changed"), "bytes": 8})
