"""Fresh-run duplicate admission and retained synthetic resume compatibility."""
import json
import importlib
import importlib.util
from pathlib import Path
import sys

import pytest

from test_longform_runner import _catalog


# The shared virtualenv can have an editable install of a different checkout,
# and conftest may already have imported it. Keep this focused witness bound to
# its sibling production sources without replacing the suite's hbqrs modules.
_source = Path(__file__).resolve().parents[1] / "src" / "hbqrs"
_package_name = "_duplicate_question_guard_checkout"
_spec = importlib.util.spec_from_file_location(
    _package_name, _source / "__init__.py", submodule_search_locations=[str(_source)]
)
assert _spec is not None and _spec.loader is not None
_package = importlib.util.module_from_spec(_spec)
sys.modules[_package_name] = _package
_spec.loader.exec_module(_package)
core = importlib.import_module(f"{_package_name}.core")
runner = importlib.import_module(f"{_package_name}.runner")
assert Path(runner.__file__).resolve() == (_source / "runner.py").resolve()


def _fixture(tmp_path, monkeypatch):
    registry, bundles = _catalog(tmp_path)
    artifact = tmp_path / "story.txt"
    artifact.write_text("An invented scene.", encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Provider boundary reached")

    for name in ("_call_openai", "_call_codex", "_call_grok", "_call_nous"):
        monkeypatch.setattr(runner, name, forbidden)
    return dict(artifact_path=artifact, bundle_id="prose.synthetic", provider="openai",
                model="synthetic", output_dir=tmp_path / "run", registry=registry, bundles=bundles)


def _add_overlapping_penalty(bundles):
    catalog = json.loads(bundles.read_bytes())
    catalog[0]["penalty_modules"] = [{"module_id": "craft.synthetic", "cap_points": 5}]
    bundles.write_text(json.dumps(catalog), encoding="utf-8")


@pytest.mark.parametrize("mode", [None, "batch_question_ids_v1"])
def test_duplicate_roles_reject_before_dispatch_or_output(tmp_path, monkeypatch, mode):
    opts = _fixture(tmp_path, monkeypatch)
    _add_overlapping_penalty(opts["bundles"])
    with pytest.raises(core.HBQError, match="Compiled bundle has duplicate question IDs: craft.synthetic.clear"):
        runner.run_judge(**opts, response_schema_mode=mode)
    assert not opts["output_dir"].exists()


def test_unique_fresh_run_and_resume_keep_configuration(tmp_path, monkeypatch):
    opts = _fixture(tmp_path, monkeypatch)
    assert runner.run_judge(**opts, dry_run=True)["question_count"] == 1
    manifest = opts["output_dir"] / "run.json"
    before = manifest.read_bytes()
    assert runner.run_judge(**opts, dry_run=True, resume=True)["question_count"] == 1
    assert manifest.read_bytes() == before


def test_existing_duplicate_manifest_keeps_historical_resume_semantics(tmp_path, monkeypatch):
    opts = _fixture(tmp_path, monkeypatch)
    runner.run_judge(**opts, dry_run=True)
    manifest_path = opts["output_dir"] / "run.json"
    manifest = json.loads(manifest_path.read_bytes())
    _add_overlapping_penalty(opts["bundles"])
    # Construct a pre-guard synthetic dry-run manifest with the exact duplicate
    # compilation and its original configuration digest. No actual run is read.
    compiled = core.compile_bundle(core.load_modules(opts["registry"]),
                                   core.load_bundles(opts["bundles"])[0])
    questions = core.compiled_questions(compiled)
    config = manifest["configuration"]
    config["question_ids"] = [row["question"]["id"] for row in questions]
    config["questions_sha256"] = runner._sha256_bytes(runner._json_bytes(runner._question_payload(questions)))
    config["compiled_bundle_sha256"] = runner._sha256_bytes(runner._json_bytes(compiled))
    manifest["config_sha256"] = runner._sha256_bytes(runner._json_bytes(config))
    manifest_path.write_bytes(runner._json_bytes(manifest))
    before = manifest_path.read_bytes()
    result = runner.run_judge(**opts, dry_run=True, resume=True)
    assert result["question_count"] == 2
    assert result["config_sha256"] == manifest["config_sha256"]
    assert manifest_path.read_bytes() == before
