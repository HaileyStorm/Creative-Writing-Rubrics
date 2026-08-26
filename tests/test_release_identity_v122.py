"""Clone-portable coherence contract for package and rubric identities."""

from __future__ import annotations

import json

import yaml

from hbqrs import __version__, book_root, load_bundles, load_modules, walk_tree


def test_runtime_package_release_is_distinct_from_the_unchanged_rubric_standard() -> None:
    root = book_root()
    expected_standard = {"id": "HBQ-RS", "version": "1.2.1"}
    modules = load_modules(root / "registry" / "all_modules.json")
    bundles = load_bundles(root / "bundles" / "all_bundles.json")
    authored_modules = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted((root / "registry" / "modules").glob("*.yaml"))
    ]
    authored_bundles = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted((root / "bundles").glob("*.yaml"))
        if path.name != "all_bundles.yaml"
    ]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    citation = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))

    assert __version__ == "1.2.2"
    assert 'version = "1.2.2"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert citation["cff-version"] == "1.2.0"
    assert citation["version"] == __version__
    assert citation["date-released"] == "2026-08-25"
    assert "Creative-Writing-Rubrics 1.2.2" in citation["abstract"]
    assert "HBQ-RS 1.2.1" in citation["abstract"]

    assert manifest["standard"] == expected_standard
    assert len(modules) == 278
    assert len(bundles) == 85
    assert sum(1 for module in modules for _ in walk_tree(module["tree"])) == 2145
    assert authored_modules == modules
    assert authored_bundles == bundles
    assert all(module["standard"] == expected_standard for module in modules)
    assert all(bundle["standard"] == expected_standard for bundle in bundles)
