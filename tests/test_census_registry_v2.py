import copy
import importlib.util
import json
from pathlib import Path
import tempfile

import pytest


PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-census-pass-b-dispositions-v1/registry_v2.py"
spec = importlib.util.spec_from_file_location("tested_census_registry_v2", PATH)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def test_overlap_and_nonvoting_edges_do_not_become_votes_or_independent_roots():
    edges = [
        {"source_type": "original_record", "source": "ancestor", "relationship": "excluded_ancestor", "census": "proof"},
        {"source_type": "declaration_package", "source": "public", "relationship": "nonvoting_output", "census": "proof"},
        {"source_type": "declaration_package", "source": "unmatched", "relationship": "unresolved_locator", "census": None},
    ]
    assert r.coverage_edges(edges, {"ancestor"}, {"proof"}, {"public", "unmatched"}) == edges
    assert "private_locator" not in edges[-1]
    with pytest.raises(ValueError, match="Duplicate coverage"):
        r.coverage_edges(edges + [copy.deepcopy(edges[0])], {"ancestor"}, {"proof"}, {"public", "unmatched"})
    with pytest.raises(ValueError, match="outside frozen"):
        r.coverage_edges([{**edges[1], "census": "guessed"}], {"ancestor"}, {"proof"}, {"public"})
    joined = {"source_type": "original_record", "source": "ancestor", "relationship": "joins_existing_positions", "census": "proof"}
    assert r.coverage_edges([edges[0], joined], {"ancestor"}, {"proof"}, set()) == [edges[0], joined]
    with pytest.raises(ValueError, match="Excluded attempt"):
        r.coverage_edges([joined], {"ancestor"}, {"proof"}, set(), excluded_attempts={"ancestor"})
    binding = {"expected": {"source_aggregate_sha256": "a" * 64}}
    r.declaration_binding(b'{"source_aggregate_sha256":"' + b'a' * 64 + b'","outcomes":"\\uZZZZ"}', binding)
    with pytest.raises(ValueError, match="source binding differs"):
        r.declaration_binding(b'{"source_aggregate_sha256":"' + b'b' * 64 + b'","outcomes":"\\uZZZZ"}', binding)


def test_saved_receipt_binding_and_lexical_outcome_boundary():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        def pin(name, raw):
            (root / name).write_bytes(raw)
            return {"root": "control", "locator": name, "bytes": len(raw), "sha256": r.sha(raw)}

        implementation = pin("old.py", b"historical implementation")
        prior = pin("prior.json", b'{"sealed":"\\uZZZZ"}')
        records = [{"id": f"record-{i}", "disposition": "declaration_only"} for i in range(22)]
        refs = [{"id": f"ref-{i}", **prior} for i in range(7)]
        original = pin("old-recipe.json", r.canonical({"records": records, "prior_censuses": refs}))
        report = pin("old-report.json", (json.dumps({"recipe_file_sha256": original["sha256"],
            "implementation_sha256": implementation["sha256"], "records": [{"id": a["id"]} for a in records],
            "prior_censuses": [{"id": a["id"]} for a in refs]})[:-1] + ',"outcomes":"\\uZZZZ"}').encode())
        saved_recipe = pin("saved-recipe.json", b'{"sealed":"\\uZZZZ"}')
        saved_report = pin("saved-report.json", b'{"human_target":"\\uZZZZ"}')
        terminal_raw = (json.dumps({"state": "completed", "recipe_file_sha256": saved_recipe["sha256"],
            "report_sha256": saved_report["sha256"]})[:-1] + ',"metrics":"\\uZZZZ"}').encode()
        terminal = pin("terminal.json", terminal_raw)
        recipe = {"policy": r.POLICY, "ancestor": {"implementation": implementation, "recipe": original, "report": report},
                  "completed_censuses": [{"id": "proof", "recipe": saved_recipe, "report": saved_report,
                    "receipt": terminal, "receipt_kind": "completed_terminal"}],
                  "declaration_packages": [], "coverage_edges": [], "retained_sources": [], "relationship_semantics": {}}
        output, _ = r.run(recipe, {"control": root})
        assert output["original_records"] == records and output["original_references"] == refs
        assert output["provider_calls_made"] == output["new_provider_votes"] == 0
        assert output["physical_contact_cardinality"] is None
        assert "metrics" not in output and "outcomes" not in output
        wrong = terminal_raw.replace(saved_report["sha256"].encode(), b"0" * 64)
        recipe["completed_censuses"][0]["receipt"] = pin("wrong-terminal.json", wrong)
        with pytest.raises(ValueError, match="receipt binding differs"):
            r.run(recipe, {"control": root})
