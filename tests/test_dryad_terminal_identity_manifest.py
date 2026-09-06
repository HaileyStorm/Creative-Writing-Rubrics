from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/terminal_identity_manifest.py"


def load():
    spec = importlib.util.spec_from_file_location("dryad_terminal_identity_manifest", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_rejects_invalid_commit_after_pinned_source_capture() -> None:
    subject = load()
    captures, _ = subject._sources()
    with pytest.raises(ValueError, match="generator commit"):
        subject._generator(captures, "synthetic-invalid-commit")


def test_pinned_dependency_drift_rejects_before_manifest_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    target = subject.ROOT / "identity_exclusion.py"
    original_read_bytes = Path.read_bytes

    def drift(path: Path) -> bytes:
        value = original_read_bytes(path)
        return value + b" " if path.resolve() == target.resolve() else value

    monkeypatch.setattr(Path, "read_bytes", drift)
    with pytest.raises(ValueError, match="dependency"):
        subject._sources()


def test_recorded_predecessor_without_pinned_sources_cannot_create_manifest_or_claim_contact_28(tmp_path: Path) -> None:
    subject = load()
    prior, snapshot, plan = (tmp_path / name for name in ("prior", "snapshot", "plan"))
    for root in (prior, snapshot, plan):
        root.mkdir()
    with pytest.raises(ValueError, match="committed byte-exact"):
        subject.build_manifest(prior, snapshot, plan, generator_commit="a120e05103ccf9e947b305e4dd3b6a2850fda35b")
    assert all(not any(root.iterdir()) for root in (prior, snapshot, plan))


def test_unsettled_contacts_require_the_exact_third_cohort_route() -> None:
    subject = load()
    prepared_sha256, authorization_sha256, route_sha256 = "a" * 64, "b" * 64, "c" * 64
    review = {"reviewed_at": "2026-09-06T00:00:00Z", "expires_at": "2026-09-06T00:10:00Z"}
    contact = {"cohort_number": 3, "prepared_sha256": prepared_sha256, "review_sha256": authorization_sha256,
               "route_sha256": route_sha256, "admitted_at": "2026-09-06T00:05:00Z"}
    subject._unsettled_contact(contact, review, prepared_sha256=prepared_sha256,
                               authorization_sha256=authorization_sha256, route_sha256=route_sha256)
    with pytest.raises(ValueError, match="authorization or route"):
        subject._unsettled_contact({**contact, "route_sha256": "d" * 64}, review,
                                   prepared_sha256=prepared_sha256, authorization_sha256=authorization_sha256,
                                   route_sha256=route_sha256)
