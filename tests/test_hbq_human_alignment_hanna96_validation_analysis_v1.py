import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"
ANALYZE_PATH = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-analysis-v1" / "analyze.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def projections(schedule, endpoint):
    return [{"endpoint": endpoint, "cell_id": row["cell_id"], "candidate_id": row["candidate_id"], "payload_sha256": row["payload_sha256"], "source_binding_sha256": row["source_binding_sha256"], "target_sha256": row["target_sha256"], "scores": row["target"]} for row in schedule["cells"]]


def write_set(analyzer, root, name, endpoint, schedule, rows):
    value = {"format_version": 1, "study_id": analyzer.STUDY_ID, "kind": "persisted_endpoint_cell_projection_set", "endpoint": endpoint, "executor_binding": analyzer.EXPECTED_EXECUTOR_BINDINGS[endpoint], "schedule_sha256": schedule["schedule_sha256"], "projections": rows}
    value["projection_set_sha256"] = analyzer.sha256(value)
    (root / name).write_bytes(analyzer.canonical(value))


def closed_roots(tmp_path):
    freeze, analyzer = load(FREEZE_PATH, "fresh96_freeze"), load(ANALYZE_PATH, "fresh96_analyzer")
    schedule_root, projection_root = tmp_path / "schedule", tmp_path / "projections"
    schedule = freeze.freeze(schedule_root)
    projection_root.mkdir()
    write_set(analyzer, projection_root, "grok.json", "grok-4.6", schedule, projections(schedule, "grok-4.6"))
    write_set(analyzer, projection_root, "sol.json", "gpt-5.6-sol", schedule, projections(schedule, "gpt-5.6-sol"))
    return freeze, analyzer, schedule_root, projection_root


def test_endpoint_metrics_are_complete_separate_and_safe_to_publish(tmp_path):
    _freeze, analyzer, schedule_root, projection_root = closed_roots(tmp_path)
    result = analyzer.analyze_frozen_roots(schedule_root, projection_root)
    assert [(row["endpoint"], row["cells"]) for row in result["endpoint_metrics"]] == [("gpt-5.6-sol", 64), ("grok-4.6", 64)]
    assert all(metric["equal_group_mae"] == 0 for row in result["endpoint_metrics"] for metric in row["candidates"])
    persisted = {json.loads((projection_root / name).read_text(encoding="utf-8"))["endpoint"]: json.loads((projection_root / name).read_text(encoding="utf-8")) for name in ("grok.json", "sol.json")}
    for endpoint_result in result["endpoint_metrics"]:
        source = persisted[endpoint_result["endpoint"]]
        assert endpoint_result["projection_set_sha256"] == source["projection_set_sha256"]
        assert endpoint_result["executor_binding"] == source["executor_binding"]
    serialized = analyzer.canonical(result).decode("utf-8")
    assert "story" not in serialized and "prompt_group_id" not in serialized and "payload_base64" not in serialized


def test_analyzer_rejects_rehashed_schedule_tamper_out_of_range_and_path_endpoint(tmp_path):
    freeze, analyzer, schedule_root, projection_root = closed_roots(tmp_path)
    schedule_path = schedule_root / "schedule.json"
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    schedule["cells"][0]["target"]["Coherence"] = 4.75
    schedule["cells"][0]["target_sha256"] = freeze.sha256(schedule["cells"][0]["target"])
    body = dict(schedule)
    body.pop("schedule_sha256")
    schedule["schedule_sha256"] = freeze.sha256(body)
    schedule_path.write_bytes(freeze.canonical(schedule))
    with pytest.raises(ValueError, match="pinned public construction"):
        freeze.validate_frozen_root(schedule_root)

    _freeze, analyzer, schedule_root, projection_root = closed_roots(tmp_path / "range")
    grok = json.loads((projection_root / "grok.json").read_text(encoding="utf-8"))
    grok["projections"][0]["scores"]["Coherence"] = 999
    body = dict(grok)
    body.pop("projection_set_sha256")
    grok["projection_set_sha256"] = analyzer.sha256(body)
    (projection_root / "grok.json").write_bytes(analyzer.canonical(grok))
    with pytest.raises(ValueError, match="0..5"):
        analyzer.analyze_frozen_roots(schedule_root, projection_root)

    _freeze, analyzer, schedule_root, projection_root = closed_roots(tmp_path / "endpoint")
    grok = json.loads((projection_root / "grok.json").read_text(encoding="utf-8"))
    grok["endpoint"] = "C:\\private\\path"
    body = dict(grok)
    body.pop("projection_set_sha256")
    grok["projection_set_sha256"] = analyzer.sha256(body)
    (projection_root / "grok.json").write_bytes(analyzer.canonical(grok))
    with pytest.raises(ValueError, match="identity"):
        analyzer.analyze_frozen_roots(schedule_root, projection_root)

    _freeze, analyzer, schedule_root, projection_root = closed_roots(tmp_path / "executor")
    grok = json.loads((projection_root / "grok.json").read_text(encoding="utf-8"))
    grok["executor_binding"]["executor_sha256"] = "0" * 64
    body = dict(grok)
    body.pop("projection_set_sha256")
    grok["projection_set_sha256"] = analyzer.sha256(body)
    (projection_root / "grok.json").write_bytes(analyzer.canonical(grok))
    with pytest.raises(ValueError, match="executor binding"):
        analyzer.analyze_frozen_roots(schedule_root, projection_root)


def test_freeze_rejects_linked_schedule(tmp_path):
    freeze = load(FREEZE_PATH, "fresh96_freeze")
    source = tmp_path / "source"
    freeze.freeze(source)
    linked = tmp_path / "linked"
    linked.mkdir()
    try:
        (linked / "schedule.json").symlink_to(source / "schedule.json")
    except OSError:
        pytest.skip("symlink creation unavailable on this Windows host")
    with pytest.raises(ValueError, match="reparsed"):
        freeze.validate_frozen_root(linked)
