from copy import deepcopy
import json

import pytest

from hbqrs import HBQError, book_root
from hbqrs.cli import main
from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.longform import normalize_score_result
from hbqrs.readiness import workflow_scorer_readiness
from test_html_report import _report


def test_saved_scorer_readiness_is_distinct_from_gate_and_preserves_report(tmp_path, capsys):
    root = book_root()
    modules = load_modules(root / "registry/all_modules.json")
    bundle = resolve_bundle(load_bundles(root / "bundles/all_bundles.json"), "prose.scene")
    rows = compiled_questions(compile_bundle(modules, bundle))
    for sparse, expected in ((True, "PROVISIONAL"), (False, "SCORED")):
        domain_count = 0
        verdicts = []
        for row in rows:
            role = row["role"]
            verdict = "NO" if role == "penalty" else "YES"
            if role == "domain":
                domain_count += 1
                if sparse and domain_count > 1:
                    verdict = "CANNOT_ASSESS"
            verdicts.append({"question_id": row["question"]["id"], "verdict": verdict,
                             "note": "Synthetic", "confidence": 1.0, "evidence": []})
        score = score_bundle(modules, bundle, verdicts, artifact_id="synthetic")
        assert score["hard_gate_status"] == "VALID" and score["status"] == expected
        report = _report(with_hierarchy=False)
        report["artifact"]["artifact_id"] = "synthetic"
        report["route"]["global_bundle_id"] = bundle["bundle_id"]
        report["global_result"] = normalize_score_result(score, scope_id="work", label="Whole work")
        directory = tmp_path / expected
        source = directory / ".private/evaluations/global/score.json"
        source.parent.mkdir(parents=True)
        report_path = directory / "report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        source.write_text(json.dumps(score), encoding="utf-8")
        before = report_path.read_bytes(), source.read_bytes()
        assert main(["workflow-readiness", str(directory)]) == 0
        view = json.loads(capsys.readouterr().out)
        assert view["scopes"][0]["control_state"] == "VALID"
        assert view["scopes"][0]["scorer_status"] == expected
        assert view["scopes"][1]["reason"] == "source_score_missing"
        assert (report_path.read_bytes(), source.read_bytes()) == before
        report["global_result"].pop("weight_profile", None)
        report["global_result"].pop("confidence_diagnostics", None)
        report_path.write_text(json.dumps(report), encoding="utf-8")
        assert workflow_scorer_readiness(directory)["scopes"][0]["scorer_status"] == expected
        report_path.write_bytes(before[0])
        spoofed = deepcopy(score)
        spoofed.update(deepcopy(json.loads(before[0])["global_result"]))
        spoofed["final_score"] = {"observed": 1, "lower": 1, "upper": 1}
        source.write_text(json.dumps(spoofed), encoding="utf-8")
        with pytest.raises(HBQError, match="differs from workflow report"):
            workflow_scorer_readiness(directory)
        del score["status"]
        source.write_text(json.dumps(score), encoding="utf-8")
        assert workflow_scorer_readiness(directory)["scopes"][0]["reason"] == "scorer_status_missing"
        score["status"] = "INELIGIBLE"
        source.write_text(json.dumps(score), encoding="utf-8")
        with pytest.raises(HBQError, match="conflicts"):
            workflow_scorer_readiness(directory)
        score["status"] = {"unexpected": True}
        source.write_text(json.dumps(score), encoding="utf-8")
        with pytest.raises(HBQError, match="conflicts"):
            workflow_scorer_readiness(directory)
        score["status"] = expected
        score["artifact_id"] = "different"
        source.write_text(json.dumps(score), encoding="utf-8")
        with pytest.raises(HBQError, match="identity differs"):
            workflow_scorer_readiness(directory)
        score["artifact_id"] = "synthetic"
        score["coverage"] = 0.5
        source.write_text(json.dumps(score), encoding="utf-8")
        with pytest.raises(HBQError, match="differs from workflow report"):
            workflow_scorer_readiness(directory)
        source.write_text("{invalid", encoding="utf-8")
        with pytest.raises(HBQError, match="Invalid saved JSON"):
            workflow_scorer_readiness(directory)
