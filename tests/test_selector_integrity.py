"""Real runner admission and historical replay with invented, offline inputs."""
import hashlib
import json
import socket
import subprocess

import pytest

from hbqrs import core, runner
from hbqrs.selector_integrity import EXACT, HISTORICAL
from test_longform_runner import _catalog, _questions


@pytest.mark.parametrize("field", ["include_question_ids", "include_group_ids"])
def test_runner_rejects_selector_typos_before_provider_and_preserves_historical_resume(tmp_path, monkeypatch, field):
    registry, bundles = _catalog(tmp_path)
    modules = json.loads(registry.read_bytes())
    question_id = modules[0]["tree"][0]["id"]
    modules[0]["tree"] = [{
        "id": "group.synthetic", "type": "group", "title": "Synthetic group",
        "score_mode": "weighted_mean", "weight": 1.0, "children": modules[0]["tree"],
    }]
    registry.write_text(json.dumps(modules), encoding="utf-8")
    catalog = json.loads(bundles.read_bytes())
    known = question_id if field == "include_question_ids" else "group.synthetic"
    catalog[0]["domains"][0]["components"][0][field] = [known, "invented.selector.typo"]
    bundles.write_text(json.dumps(catalog), encoding="utf-8")
    artifact = tmp_path / "story.txt"
    artifact.write_bytes(b"A short test scene.\n")
    output = tmp_path / "run"
    calls = []

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected provider, process or network boundary")

    for name in ("_call_codex", "_call_openai", "_call_grok", "_call_nous"):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    options = dict(
        artifact_path=artifact, artifact_id="synthetic-story", bundle_id="prose.synthetic",
        registry=registry, bundles=bundles, output_dir=output, provider="codex",
        model="gpt-5.6-sol", reasoning="high", batch_size=32, batch_attempts=1, allow_remote=True,
    )
    with pytest.raises(core.HBQError, match=f"unknown {field}"):
        runner.run_judge(**options)
    assert not (output / "run.json").exists()

    def invented_binary(**kwargs):
        ids = [row["question_id"] for row in _questions(kwargs["prompt"])]
        calls.append(ids)
        return json.dumps({"verdicts": [{
            "question_id": qid, "verdict": "YES", "confidence": 0.8,
            "evidence": [{"kind": "exact_quote", "reference": "invented source",
                          "exact_quote": "A short test scene.", "summary": None}],
            "note": "Invented observation.",
        } for qid in ids]}), {"reported": {
            "provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high",
            "session_id": "invented-selector-session",
        }}

    monkeypatch.setattr(runner, "_call_codex", invented_binary)
    runner.run_judge(**options, selector_policy=HISTORICAL)
    assert calls == [[question_id]]
    manifest_path = output / "run.json"
    frozen_manifest = manifest_path.read_bytes()
    assert json.loads(frozen_manifest)["configuration"]["selector_policy"] == HISTORICAL
    monkeypatch.setattr(runner, "_call_codex", forbidden)
    runner.run_judge(**options, resume=True)
    assert manifest_path.read_bytes() == frozen_manifest
    assert calls == [[question_id]]
    with pytest.raises(core.HBQError, match="selector policy changed"):
        runner.run_judge(**options, resume=True, selector_policy=EXACT)
    assert manifest_path.read_bytes() == frozen_manifest

    # Model an old manifest whose configuration predates selector policies.
    legacy = json.loads(frozen_manifest)
    del legacy["configuration"]["selector_policy"]
    legacy["config_sha256"] = hashlib.sha256(runner._json_bytes(legacy["configuration"])).hexdigest()
    manifest_path.write_text(json.dumps(legacy), encoding="utf-8")
    unmarked = manifest_path.read_bytes()
    runner.run_judge(**options, resume=True)
    runner.run_judge(**options, resume=True, selector_policy=HISTORICAL)
    assert manifest_path.read_bytes() == unmarked
    assert calls == [[question_id]]
    with pytest.raises(core.HBQError, match="selector policy changed"):
        runner.run_judge(**options, resume=True, selector_policy=EXACT)
    assert manifest_path.read_bytes() == unmarked
