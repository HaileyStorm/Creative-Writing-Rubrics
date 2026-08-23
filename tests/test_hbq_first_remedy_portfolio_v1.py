from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-first-remedy-portfolio-v1"


def verifier():
    spec = importlib.util.spec_from_file_location("first_remedy_portfolio_v1", ROOT / "verify_portfolio.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def test_exact_partition_geometry_and_public_coverage_bindings():
    report = verifier().verify_manifest(manifest())
    assert report == {
        "status": "frozen_public_coverage_manifest_no_execution_authorized",
        "findings": 77,
        "unique_leaves": 80,
        "initial_calls": 1140,
        "provider_calls": 0,
    }
    packages = manifest()["packages"]
    assert [(item["package_id"], item["finding_count_exact"], item["initial_calls_exact"]) for item in packages] == [
        ("R0", 2, 0), ("L1", 1, 72), ("L2", 3, 216), ("P1", 11, 132), ("S1", 35, 420), ("S2", 25, 300)
    ]
    assert len({finding for package in packages for finding in package["finding_ids"]}) == 77


def test_mutated_partition_or_hash_fails_closed(monkeypatch):
    module = verifier()
    changed = deepcopy(manifest())
    changed["packages"][1]["finding_ids"] = changed["packages"][1]["finding_ids"] + [changed["packages"][2]["finding_ids"][0]]
    monkeypatch.setattr(module, "CANONICAL_PROJECTION_SHA256", module.canonical_projection_sha256(changed))
    with pytest.raises(ValueError, match="Package finding count"):
        module.verify_manifest(changed)
    changed = deepcopy(manifest())
    changed["packages"][1]["finding_ids"] = ["cfe0a7aa2639811ecb8b36b4f507229d929b51e1f8839a4116bfe7847c65c1b9"]
    with pytest.raises(ValueError, match="Canonical manifest projection drifted"):
        module.verify_manifest(changed)
    changed = deepcopy(manifest())
    changed["bindings"]["findings"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Canonical manifest projection drifted"):
        module.verify_manifest(changed)


def test_canonical_projection_rejects_coherent_id_status_and_ancestor_mutations():
    module = verifier()
    changed = deepcopy(manifest())
    changed["packages"][1]["finding_ids"] = ["cfe0a7aa2639811ecb8b36b4f507229d929b51e1f8839a4116bfe7847c65c1b9"]
    ids = [finding for package in changed["packages"] for finding in package["finding_ids"]]
    changed["coverage"]["ordered_finding_ids_sha256"] = hashlib.sha256(("\n".join(ids) + "\n").encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="Canonical manifest projection drifted"):
        module.verify_manifest(changed)
    changed = deepcopy(manifest())
    changed["status"] = "different_but_plausible_status"
    with pytest.raises(ValueError, match="Portfolio status drifted"):
        module.verify_manifest(changed)
    changed = deepcopy(manifest())
    repository_root = Path(module.REPOSITORY_ROOT)
    root_ancestor = subprocess.run(["git", "-C", str(repository_root), "rev-list", "--max-parents=0", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
    assert root_ancestor != module.EXPECTED_CWR_PARENT
    changed["cwr_parent"] = root_ancestor
    with pytest.raises(ValueError, match="CWR parent projection drifted"):
        module.verify_manifest(changed)


def test_compact_geometry_is_derived_for_lexical_and_four_state_packages(monkeypatch):
    module = verifier()
    assert module.LEXICAL_CALLS_PER_FINDING == 12 * 2 * 3 == 72
    assert module.FOUR_STATE_CALLS_PER_FINDING == 4 * 3 == 12
    changed = deepcopy(manifest())
    changed["packages"][3]["initial_calls_exact"] = 131
    monkeypatch.setattr(module, "CANONICAL_PROJECTION_SHA256", module.canonical_projection_sha256(changed))
    with pytest.raises(ValueError, match="Derived package call geometry drifted"):
        module.verify_manifest(changed)


def test_r0_is_settled_no_change_watch_only_with_24_relevant_calls():
    r0 = manifest()["bindings"]["r0_settled_figurative_result"]
    assert r0["decision"] == "NO_GO"
    assert r0["fatigue"] == {"baseline": [12, 12], "scope_rendering_only": [12, 12]}
    assert r0["relevant_calls_exact"] == 24
    assert "no overall treatment or rubric promotion" in r0["interpretation"]


def test_verifier_is_check_only_and_public_package_has_no_private_absolute_paths():
    completed = subprocess.run([sys.executable, str(ROOT / "verify_portfolio.py"), "--check"], text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout)["findings"] == 77
    source = (ROOT / "verify_portfolio.py").read_text(encoding="utf-8")
    assert "requests" not in source.lower()
    assert "--execute" not in source
    forbidden = ("C:\\Users\\", "C:/Users/", "Gray Blood", "api_key", "raw_response", "session_id")
    for path in ROOT.iterdir():
        if path.suffix in {".json", ".md", ".py"}:
            text = path.read_text(encoding="utf-8")
            assert all(fragment not in text for fragment in forbidden)
