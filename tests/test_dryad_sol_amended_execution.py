"""Synthetic, provider-free contract tests for the approved Sol amendment guard."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_amended_execution.py"
APPROVAL = Path(r"C:\Users\Haile\Documents\cwr-owner-resume-authorizations-20260907-r1.json")
CUTOFF = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol8-sequencing-cutoff-20260907-r1.json")
NATIVE = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol8-native-20260907-r1")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _module():
    spec = importlib.util.spec_from_file_location("dryad_sol_amended_execution_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def prepared(tmp_path: Path):
    """Uses the immutable production cutoff read-only; generated review data is synthetic."""
    subject = _module()
    envelope = tmp_path / "external" / "amendment.json"
    subject.prepare_amendment_envelope(envelope, approval_path=APPROVAL, cutoff_path=CUTOFF, native_root=NATIVE)
    review = tmp_path / "review.json"
    review.write_bytes(_canonical({"cohort_number": 13, "ordinals": list(range(121, 131)),
                                   "reviewed_at": "2026-09-07T14:37:32.080521Z"}))
    review_sha = _sha(review.read_bytes())
    binding = tmp_path / "external" / subject.cohort_binding_filename(13, review_sha)
    subject.bind_amended_cohort(binding, envelope_path=envelope, review_path=review,
                                expected_review_sha256=review_sha, approval_path=APPROVAL,
                                cutoff_path=CUTOFF, native_root=NATIVE)
    return SimpleNamespace(subject=subject, envelope=envelope, review=review, review_sha=review_sha,
                           binding=binding, native=NATIVE)


def test_real_cutoff_prefix_is_read_only_and_envelope_binds_approval(prepared):
    evidence = prepared.subject.verify_cutoff_preservation(CUTOFF, prepared.native)
    assert evidence["cutoff_sha256"] == prepared.subject.CUTOFF_SHA256
    _, raw, manifest = prepared.subject.verify_amendment_envelope(
        prepared.envelope, approval_path=APPROVAL, cutoff_path=CUTOFF, native_root=prepared.native)
    assert manifest["approval_sha256"] == prepared.subject.APPROVAL_SHA256
    assert manifest["source_bindings"]["amendment_guard_sha256"] == _sha(SOURCE.read_bytes())
    assert _sha(raw) == _sha(prepared.envelope.read_bytes())


def test_wrong_owner_approval_or_cutoff_root_reject_before_preparation(tmp_path: Path, prepared):
    bad = tmp_path / "bad-approval.json"; bad.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="approval"):
        prepared.subject.prepare_amendment_envelope(tmp_path / "bad.json", approval_path=bad,
                                                    cutoff_path=CUTOFF, native_root=prepared.native)
    with pytest.raises(ValueError, match="native root"):
        prepared.subject.verify_cutoff_preservation(CUTOFF, tmp_path / "wrong-root")


def test_binding_rejects_prefix_ordinal_and_missing_binding_before_base_load(prepared, monkeypatch):
    early = prepared.review.with_name("early.json")
    early.write_bytes(_canonical({"cohort_number": 12, "ordinals": list(range(111, 121)),
                                  "reviewed_at": "2026-09-07T14:37:32.080521Z"}))
    with pytest.raises(ValueError, match="amended cohort"):
        prepared.subject.bind_amended_cohort(early.with_suffix(".binding.json"), envelope_path=prepared.envelope,
                                             review_path=early, expected_review_sha256=_sha(early.read_bytes()),
                                             approval_path=APPROVAL, cutoff_path=CUTOFF, native_root=prepared.native)
    prepared.binding.unlink()
    monkeypatch.setattr(prepared.subject, "_load_base", lambda: (_ for _ in ()).throw(AssertionError("base loaded")))
    with pytest.raises(FileNotFoundError):
        prepared.subject.collect_amended_cohort(Path("unused"), prepared.native, prepared.review,
                                                expected_review_sha256=prepared.review_sha, queue_root=Path("unused"),
                                                auth_receipt_path=Path("unused"), cost_receipt_path=Path("unused"),
                                                envelope_path=prepared.envelope, cohort_binding_path=prepared.binding,
                                                approval_path=APPROVAL, cutoff_path=CUTOFF, native_root=prepared.native)


def test_valid_post_prefix_guard_wraps_both_frozen_seams_without_cli(prepared, monkeypatch):
    events: list[str] = []

    def factory():
        runner = SimpleNamespace()
        def run_judge(*_args, **kwargs):
            kwargs["before_provider_attempt"]({"output_dir": str(prepared.native), "batch": {"number": 1}})
            adapter = fake_base._adapter()
            adapter.call_codex(before_provider_attempt=lambda: events.append("base-inner"))
            return {"status": "PAUSED"}
        runner.run_judge = run_judge
        return runner

    class FakeAdapter:
        def call_codex(self, **kwargs):
            kwargs["before_provider_attempt"]()
            events.append("fake-cli-seam")
            return "", {}

    def collect(*_args, **_kwargs):
        runner = fake_base._private_runner()
        return runner.run_judge(before_provider_attempt=lambda _context: events.append("base-outer"))

    fake_base = SimpleNamespace(_private_runner=factory, _adapter=lambda: FakeAdapter(), collect_cohort=collect)
    monkeypatch.setattr(prepared.subject, "_load_base", lambda: fake_base)
    monkeypatch.setattr(prepared.subject, "_request_lookup", lambda *_args: 121)
    result = prepared.subject.collect_amended_cohort(
        Path("unused"), prepared.native, prepared.review, expected_review_sha256=prepared.review_sha,
        queue_root=Path("unused"), auth_receipt_path=Path("unused"), cost_receipt_path=Path("unused"),
        envelope_path=prepared.envelope, cohort_binding_path=prepared.binding, approval_path=APPROVAL,
        cutoff_path=CUTOFF, native_root=prepared.native)
    assert result["status"] == "PAUSED"
    assert events == ["base-outer", "base-inner", "fake-cli-seam"]


def test_outer_guard_rejects_early_ordinal_before_fake_cli(prepared, monkeypatch):
    events: list[str] = []
    def factory():
        runner = SimpleNamespace()
        runner.run_judge = lambda *_args, **kwargs: kwargs["before_provider_attempt"]({"output_dir": str(prepared.native), "batch": {"number": 1}})
        return runner
    fake_base = SimpleNamespace(_private_runner=factory, _adapter=lambda: SimpleNamespace(call_codex=lambda **_kwargs: events.append("cli")),
                                collect_cohort=lambda *_args, **_kwargs: fake_base._private_runner().run_judge(before_provider_attempt=lambda _context: None))
    monkeypatch.setattr(prepared.subject, "_load_base", lambda: fake_base)
    monkeypatch.setattr(prepared.subject, "_request_lookup", lambda *_args: 120)
    with pytest.raises(ValueError, match="ordinal"):
        prepared.subject.collect_amended_cohort(Path("unused"), prepared.native, prepared.review,
                                                expected_review_sha256=prepared.review_sha, queue_root=Path("unused"),
                                                auth_receipt_path=Path("unused"), cost_receipt_path=Path("unused"),
                                                envelope_path=prepared.envelope, cohort_binding_path=prepared.binding,
                                                approval_path=APPROVAL, cutoff_path=CUTOFF, native_root=prepared.native)
    assert events == []


def test_renewed_cohort_review_uses_a_distinct_companion_binding(prepared, tmp_path: Path):
    before = tmp_path / "before-approval-review.json"
    before.write_bytes(_canonical({"cohort_number": 13, "ordinals": list(range(121, 131)),
                                   "reviewed_at": "2026-09-07T14:37:32.080520Z"}))
    with pytest.raises(ValueError, match="amended cohort"):
        prepared.subject.bind_amended_cohort(
            before.with_suffix(".binding.json"), envelope_path=prepared.envelope, review_path=before,
            expected_review_sha256=_sha(before.read_bytes()), approval_path=APPROVAL,
            cutoff_path=CUTOFF, native_root=prepared.native)
    renewed = tmp_path / "renewed-review.json"
    renewed.write_bytes(_canonical({"cohort_number": 13, "ordinals": list(range(121, 131)),
                                    "reviewed_at": "2026-09-07T14:38:00Z"}))
    renewed_sha = _sha(renewed.read_bytes())
    renewed_binding = prepared.binding.parent / prepared.subject.cohort_binding_filename(13, renewed_sha)
    prepared.subject.bind_amended_cohort(renewed_binding, envelope_path=prepared.envelope, review_path=renewed,
                                         expected_review_sha256=renewed_sha, approval_path=APPROVAL,
                                         cutoff_path=CUTOFF, native_root=prepared.native)
    assert renewed_binding != prepared.binding
    for binding, review, review_sha in ((prepared.binding, prepared.review, prepared.review_sha),
                                        (renewed_binding, renewed, renewed_sha)):
        _, _, value = prepared.subject.verify_amended_cohort_binding(
            binding, envelope_path=prepared.envelope, review_path=review, expected_review_sha256=review_sha,
            approval_path=APPROVAL, cutoff_path=CUTOFF, native_root=prepared.native)
        assert value["review_sha256"] == review_sha
