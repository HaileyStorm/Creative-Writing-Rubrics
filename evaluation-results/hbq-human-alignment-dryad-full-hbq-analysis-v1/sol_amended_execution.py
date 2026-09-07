"""Guarded continuation of the approved, observed-prefix Sol collection."""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
BASE_COLLECTOR = ROOT / "sol_measurement_execution.py"
PROPOSAL = ROOT / "sol-sequencing-amendment-proposal-v1.md"
APPROVAL_SHA256 = "699fbb473ee3b781607a12af388b57538f2ca973c60abb775ed56adfeed08cfd"
APPROVAL_RECORDED_AT = "2026-09-07T14:37:32.080521+00:00"
PROPOSAL_SHA256 = "b16d68b1c5be4017287b30ba3f6b1636019759cb814ac360d470e004a472637b"
CUTOFF_SHA256 = "0128ed0fb42c1103a2b22118f818448de87eec14cda204040ddb4bfa29d1a9ce"
BASE_COLLECTOR_SHA256 = "b2ed2aa567bbeab3a933a33cf35ccfad81cb2eb47ec0479a57e52962a3a34a40"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
PREFIX_ORDINAL = 120
_HEX = set("0123456789abcdef")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _hash(value: Any, label: str) -> str:
    _require(type(value) is str and len(value) == 64 and set(value) <= _HEX, f"{label} differs")
    return value


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} differs")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    _require(type(value) is str, f"{label} differs")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _require(parsed.tzinfo is not None, f"{label} differs")
    return parsed.astimezone(timezone.utc)


def _utc(value: Any, label: str) -> datetime:
    _require(type(value) is str and value.endswith(("Z", "+00:00")), f"{label} differs")
    return _timestamp(value, label)


def _pinned(path: Path | str, expected: str, label: str) -> tuple[Path, bytes]:
    checked = Path(path).resolve()
    raw = checked.read_bytes()
    _require(_sha(raw) == _hash(expected, label), f"{label} hash drift")
    return checked, raw


def _same_root(value: Path | str, expected: str, label: str) -> Path:
    checked = Path(value).resolve()
    _require(str(checked).casefold() == expected.casefold(), f"{label} differs")
    return checked


def _approval(path: Path | str) -> tuple[Path, bytes, dict[str, Any]]:
    checked, raw = _pinned(path, APPROVAL_SHA256, "Owner Sol approval")
    value = _json(raw, "Owner Sol approval")
    sol = value.get("sol")
    _require(isinstance(sol, Mapping) and sol == {
        "carry_forward_through_ordinal": PREFIX_ORDINAL,
        "cutoff_sha256": CUTOFF_SHA256,
        "decision": "approve_sequencing_amendment",
        "next_ordinal": PREFIX_ORDINAL + 1,
        "proposal_commit": "e367e2ea7a26aafb848a8f26471240db070a0b74",
        "proposal_sha256": PROPOSAL_SHA256,
        "requires_binding_implementation_and_independent_review": True,
    }, "Owner Sol approval differs")
    _require(_timestamp(value.get("recorded_at"), "Owner Sol approval timestamp")
             == _utc(APPROVAL_RECORDED_AT, "Owner Sol approval timestamp"), "Owner Sol approval timestamp differs")
    return checked, raw, value


def _cutoff(path: Path | str, native_root: Path | str) -> tuple[Path, bytes, dict[str, Any], Path]:
    checked, raw = _pinned(path, CUTOFF_SHA256, "Sol cutoff")
    value = _json(raw, "Sol cutoff")
    root = _same_root(native_root, value.get("native_root"), "Preserved native root")
    _require(value.get("schema_version") == 1 and value.get("last_contacted_ordinal") == PREFIX_ORDINAL
             and value.get("next_ordinal_contact_absent") == PREFIX_ORDINAL + 1
             and value.get("cohort_number") == 12 and value.get("plan_sha256") == PLAN_SHA256
             and value.get("file_count") == 1151 and value.get("total_bytes") == 7666399
             and value.get("files_map_sha256") == "6e5bbbf3b8742c9ea1942009afe37ce5108a0424e6d346ab9e197fbe3b654e3f"
             and isinstance(value.get("files"), Mapping) and len(value["files"]) == value["file_count"],
             "Sol cutoff differs")
    return checked, raw, value, root


def _preserved_prefix(cutoff: Mapping[str, Any], native_root: Path) -> None:
    counted = 0
    total = 0
    for relative, descriptor in cutoff["files"].items():
        _require(type(relative) is str and isinstance(descriptor, Mapping)
                 and set(descriptor) == {"bytes", "sha256"} and type(descriptor["bytes"]) is int,
                 "Sol cutoff inventory differs")
        path = (native_root / relative).resolve()
        _require(path.is_relative_to(native_root) and path.is_file(), "Sol preserved cutoff file differs")
        raw = path.read_bytes()
        may_grow = relative.startswith("runs/baseline8-v1/train/0006/") and relative.endswith("/verdicts.jsonl")
        if may_grow:
            _require(len(raw) >= descriptor["bytes"] and _sha(raw[:descriptor["bytes"]]) == descriptor["sha256"],
                     "Sol sixth-pass verdict prefix differs")
        else:
            _require(len(raw) == descriptor["bytes"] and _sha(raw) == descriptor["sha256"],
                     "Sol preserved cutoff file differs")
        counted += 1
        total += descriptor["bytes"]
    _require(counted == cutoff["file_count"] and total == cutoff["total_bytes"], "Sol cutoff inventory totals differ")


def verify_cutoff_preservation(cutoff_path: Path | str, native_root: Path | str) -> dict[str, Any]:
    """Read and verify the immutable cutoff; only its sixth-pass verdict suffix may grow."""
    _, _, cutoff, root = _cutoff(cutoff_path, native_root)
    _preserved_prefix(cutoff, root)
    return {"cutoff_sha256": CUTOFF_SHA256, "native_root": str(root),
            "file_count": cutoff["file_count"], "files_map_sha256": cutoff["files_map_sha256"]}


def _base_bytes() -> bytes:
    _, raw = _pinned(BASE_COLLECTOR, BASE_COLLECTOR_SHA256, "Frozen Sol collector")
    return raw


def _guard_hash() -> str:
    return _sha(Path(__file__).read_bytes())


def prepare_amendment_envelope(
    envelope_path: Path | str, *, approval_path: Path | str, cutoff_path: Path | str,
    native_root: Path | str,
) -> dict[str, Any]:
    """Create an external, provider-free amendment envelope after full cutoff verification."""
    envelope = Path(envelope_path).resolve()
    _, approval_raw, _ = _approval(approval_path)
    _, cutoff_raw, cutoff, root = _cutoff(cutoff_path, native_root)
    proposal_raw = PROPOSAL.read_bytes()
    _require(_sha(proposal_raw) == PROPOSAL_SHA256, "Approved Sol proposal differs")
    _base_bytes()
    _preserved_prefix(cutoff, root)
    _require(not envelope.is_relative_to(root), "Amendment envelope must remain outside native root")
    value = {
        "schema_version": 1,
        "evidence_class": "approved_sol_sequencing_amendment_precontact_binding",
        "decision": "sequencing_amended_after_partial_sol_observation",
        "approval_sha256": _sha(approval_raw),
        "approval_recorded_at": APPROVAL_RECORDED_AT,
        "proposal_sha256": _sha(proposal_raw),
        "cutoff_sha256": _sha(cutoff_raw),
        "preserved_native_root": str(root),
        "carry_forward_through_ordinal": PREFIX_ORDINAL,
        "next_ordinal": PREFIX_ORDINAL + 1,
        "plan_sha256": PLAN_SHA256,
        "source_bindings": {"base_collector_sha256": BASE_COLLECTOR_SHA256,
                            "amendment_guard_sha256": _guard_hash()},
        "cutoff_inventory": {"file_count": cutoff["file_count"], "total_bytes": cutoff["total_bytes"],
                             "files_map_sha256": cutoff["files_map_sha256"]},
        "execution_authority": False,
        "provider_calls": 0,
    }
    raw = _canonical(value)
    envelope.parent.mkdir(parents=True, exist_ok=True)
    with envelope.open("xb") as output:
        output.write(raw)
    return value | {"sha256": _sha(raw), "path": str(envelope)}


def verify_amendment_envelope(
    envelope_path: Path | str, *, approval_path: Path | str, cutoff_path: Path | str,
    native_root: Path | str,
) -> tuple[Path, bytes, dict[str, Any]]:
    """Verify the cheap immutable anchors which must hold before every attempted contact."""
    path = Path(envelope_path).resolve()
    raw = path.read_bytes(); value = _json(raw, "Sol amendment envelope")
    _, approval_raw, _ = _approval(approval_path)
    _, cutoff_raw, cutoff, root = _cutoff(cutoff_path, native_root)
    _base_bytes()
    expected = {
        "schema_version": 1, "evidence_class": "approved_sol_sequencing_amendment_precontact_binding",
        "decision": "sequencing_amended_after_partial_sol_observation", "approval_sha256": _sha(approval_raw),
        "approval_recorded_at": APPROVAL_RECORDED_AT,
        "proposal_sha256": PROPOSAL_SHA256, "cutoff_sha256": _sha(cutoff_raw),
        "preserved_native_root": str(root), "carry_forward_through_ordinal": PREFIX_ORDINAL,
        "next_ordinal": PREFIX_ORDINAL + 1, "plan_sha256": PLAN_SHA256,
        "source_bindings": {"base_collector_sha256": BASE_COLLECTOR_SHA256,
                            "amendment_guard_sha256": _guard_hash()},
        "cutoff_inventory": {"file_count": cutoff["file_count"], "total_bytes": cutoff["total_bytes"],
                             "files_map_sha256": cutoff["files_map_sha256"]},
        "execution_authority": False, "provider_calls": 0,
    }
    _require(value == expected and _canonical(value) == raw, "Sol amendment envelope differs")
    _require(not path.is_relative_to(root), "Sol amendment envelope is inside native root")
    return path, raw, value


def bind_amended_cohort(
    binding_path: Path | str, *, envelope_path: Path | str, review_path: Path | str,
    expected_review_sha256: str, approval_path: Path | str, cutoff_path: Path | str,
    native_root: Path | str,
) -> dict[str, Any]:
    """Bind one independently reviewed post-prefix cohort before collection starts."""
    binding = Path(binding_path).resolve()
    envelope, envelope_raw, _ = verify_amendment_envelope(
        envelope_path, approval_path=approval_path, cutoff_path=cutoff_path, native_root=native_root)
    review_raw = Path(review_path).read_bytes()
    _require(_sha(review_raw) == _hash(expected_review_sha256, "Sol review anchor"), "Sol review anchor differs")
    review = _json(review_raw, "Sol review")
    cohort, ordinals = review.get("cohort_number"), review.get("ordinals")
    _require(type(cohort) is int and 13 <= cohort <= 543 and isinstance(ordinals, list)
             and ordinals == list(range((cohort - 1) * 10 + 1, min(cohort * 10 + 1, 5429)))
             and min(ordinals) > PREFIX_ORDINAL
             and _utc(review.get("reviewed_at"), "Sol amended review timestamp") >= _utc(APPROVAL_RECORDED_AT, "Owner Sol approval timestamp"),
             "Sol amended cohort differs")
    value = {
        "schema_version": 1, "evidence_class": "approved_sol_amended_cohort_binding",
        "cohort_number": cohort, "ordinals": ordinals, "review_sha256": expected_review_sha256,
        "amendment_manifest_sha256": _sha(envelope_raw), "cutoff_sha256": CUTOFF_SHA256,
        "guard_sha256": _guard_hash(), "plan_sha256": PLAN_SHA256,
    }
    _require(not binding.is_relative_to(Path(native_root).resolve()), "Cohort binding must remain outside native root")
    binding.parent.mkdir(parents=True, exist_ok=True)
    raw = _canonical(value)
    with binding.open("xb") as output:
        output.write(raw)
    return value | {"sha256": _sha(raw), "path": str(binding), "envelope_path": str(envelope)}


def cohort_binding_filename(cohort: int, review_sha256: str) -> str:
    """Name a review-specific companion binding so renewal reviews remain distinct evidence."""
    _require(type(cohort) is int and 13 <= cohort <= 543, "Sol amended cohort differs")
    return f"cohort-{cohort:04d}-{_hash(review_sha256, 'Sol review anchor')}.json"


def verify_amended_cohort_binding(
    binding_path: Path | str, *, envelope_path: Path | str, review_path: Path | str,
    expected_review_sha256: str, approval_path: Path | str, cutoff_path: Path | str,
    native_root: Path | str,
) -> tuple[Path, bytes, dict[str, Any]]:
    envelope, envelope_raw, _ = verify_amendment_envelope(
        envelope_path, approval_path=approval_path, cutoff_path=cutoff_path, native_root=native_root)
    path = Path(binding_path).resolve(); raw = path.read_bytes(); value = _json(raw, "Sol amended cohort binding")
    review_raw = Path(review_path).read_bytes()
    _require(_sha(review_raw) == _hash(expected_review_sha256, "Sol review anchor"), "Sol review anchor differs")
    review = _json(review_raw, "Sol review")
    cohort, ordinals = review.get("cohort_number"), review.get("ordinals")
    expected = {"schema_version": 1, "evidence_class": "approved_sol_amended_cohort_binding",
                "cohort_number": cohort, "ordinals": ordinals, "review_sha256": expected_review_sha256,
                "amendment_manifest_sha256": _sha(envelope_raw), "cutoff_sha256": CUTOFF_SHA256,
                "guard_sha256": _guard_hash(), "plan_sha256": PLAN_SHA256}
    _require(value == expected and _canonical(value) == raw and isinstance(cohort, int)
             and isinstance(ordinals, list) and cohort >= 13 and min(ordinals) > PREFIX_ORDINAL
             and _utc(review.get("reviewed_at"), "Sol amended review timestamp") >= _utc(APPROVAL_RECORDED_AT, "Owner Sol approval timestamp"),
             "Sol amended cohort binding differs")
    _require(not path.is_relative_to(Path(native_root).resolve()) and not envelope.is_relative_to(Path(native_root).resolve()),
             "Sol amendment binding is inside native root")
    return path, raw, value


def _load_base() -> ModuleType:
    raw = _base_bytes()
    name = f"_dryad_sol_amended_base_{uuid.uuid4().hex}"
    module = ModuleType(name); module.__file__ = str(BASE_COLLECTOR)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(BASE_COLLECTOR), "exec"), module.__dict__)  # noqa: S102 - frozen collector bytes only.
    finally:
        sys.modules.pop(name, None)
    return module


def _request_lookup(plan_root: Path, execution_root: Path, context: Mapping[str, Any]) -> int:
    plan = _json((plan_root / "plan.json").read_bytes(), "Sol plan")
    _require(_sha((plan_root / "plan.json").read_bytes()) == PLAN_SHA256, "Frozen Sol plan differs")
    output = Path(context.get("output_dir", "")).resolve()
    batch = context.get("batch")
    _require(isinstance(batch, Mapping) and type(batch.get("number")) is int, "Sol runner context differs")
    passes = {row.get("pass_id"): row for row in plan.get("passes", []) if isinstance(row, Mapping)}
    matches = [row for row in plan.get("requests", []) if isinstance(row, Mapping)
               and row.get("batch_number") == batch["number"] and row.get("pass_id") in passes
               and execution_root / passes[row["pass_id"]]["run_path"] == output]
    _require(len(matches) == 1 and type(matches[0].get("ordinal")) is int, "Sol amended runner context differs")
    return matches[0]["ordinal"]


def collect_amended_cohort(
    plan_root: Path, execution_root: Path, review_path: Path, *, expected_review_sha256: str,
    queue_root: Path, auth_receipt_path: Path, cost_receipt_path: Path, envelope_path: Path | str,
    cohort_binding_path: Path | str, approval_path: Path | str, cutoff_path: Path | str,
    native_root: Path | str,
) -> dict[str, Any]:
    """Forward a reviewed cohort through the frozen collector with amendment checks at both gates."""
    plan_root, execution_root = Path(plan_root).resolve(), Path(execution_root).resolve()
    _require(execution_root == Path(native_root).resolve(), "Sol amended collection must continue the preserved native root")
    verify_cutoff_preservation(cutoff_path, native_root)
    _, envelope_raw, _ = verify_amendment_envelope(envelope_path, approval_path=approval_path, cutoff_path=cutoff_path, native_root=native_root)
    _, _, binding = verify_amended_cohort_binding(
        cohort_binding_path, envelope_path=envelope_path, review_path=review_path,
        expected_review_sha256=expected_review_sha256, approval_path=approval_path,
        cutoff_path=cutoff_path, native_root=native_root)
    base = _load_base()
    _require(_sha(BASE_COLLECTOR.read_bytes()) == BASE_COLLECTOR_SHA256, "Frozen Sol collector changed")
    original_factory, original_adapter = base._private_runner, base._adapter
    active: dict[str, int] = {}

    def cheap_guard() -> None:
        _require(datetime.now(timezone.utc) >= _utc(APPROVAL_RECORDED_AT, "Owner Sol approval timestamp"),
                 "Sol amendment predates owner approval")
        verify_amendment_envelope(envelope_path, approval_path=approval_path, cutoff_path=cutoff_path, native_root=native_root)
        verify_amended_cohort_binding(cohort_binding_path, envelope_path=envelope_path, review_path=review_path,
                                      expected_review_sha256=expected_review_sha256, approval_path=approval_path,
                                      cutoff_path=cutoff_path, native_root=native_root)
        _require(_sha(envelope_raw) == binding["amendment_manifest_sha256"], "Sol amendment manifest changed")

    def factory() -> Any:
        runner = original_factory(); original_run = runner.run_judge
        def run_judge(*args: Any, **kwargs: Any) -> Any:
            original_before = kwargs.get("before_provider_attempt")
            _require(callable(original_before), "Frozen Sol collector gate differs")
            def before(context: dict[str, Any]) -> None:
                original_before(context)
                ordinal = _request_lookup(plan_root, execution_root, context)
                _require(ordinal > PREFIX_ORDINAL and ordinal in binding["ordinals"], "Sol amendment ordinal differs")
                active["ordinal"] = ordinal
                cheap_guard()
            return original_run(*args, **(kwargs | {"before_provider_attempt": before}))
        runner.run_judge = run_judge
        return runner

    def adapter() -> Any:
        subject = original_adapter()
        class GuardedAdapter:
            def call_codex(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
                original_before = kwargs.get("before_provider_attempt")
                _require(callable(original_before), "Frozen Sol adapter gate differs")
                def before() -> None:
                    original_before()
                    _require(active.get("ordinal") in binding["ordinals"], "Sol amendment outer gate missing")
                    cheap_guard()
                return subject.call_codex(**(kwargs | {"before_provider_attempt": before}))
        return GuardedAdapter()

    base._private_runner, base._adapter = factory, adapter
    try:
        return base.collect_cohort(plan_root, execution_root, review_path, expected_review_sha256=expected_review_sha256,
                                   queue_root=queue_root, auth_receipt_path=auth_receipt_path,
                                   cost_receipt_path=cost_receipt_path)
    finally:
        verify_cutoff_preservation(cutoff_path, native_root)
