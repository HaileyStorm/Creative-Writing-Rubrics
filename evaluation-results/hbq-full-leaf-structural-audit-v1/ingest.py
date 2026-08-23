#!/usr/bin/env python3
"""Ingest and verify the bound public Sol semantic-triage review."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator


PACKAGE = Path(__file__).resolve().parent


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_bytes(payload: bytes, label: str) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Source is not UTF-8: {label}") from exc
    rows = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL in {label} line {line_number}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"Non-object record in {label} line {line_number}")
        rows.append(record)
    return rows


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return read_jsonl_bytes(path.read_bytes(), path.name)


def triage_config(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    config = contract.get("bound_semantic_triage")
    if not isinstance(config, Mapping):
        raise ValueError("Audit contract has no bound semantic-triage configuration")
    return config


def audit_module():
    spec = importlib.util.spec_from_file_location("full_leaf_structural_audit_v1", PACKAGE / "generate.py")
    if not spec or not spec.loader:
        raise RuntimeError("Cannot load structural audit validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_part_records(source_dir: Path, contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = triage_config(contract)
    source_policy = config["private_ingest"]
    records: list[dict[str, Any]] = []
    commitments = config["source_part_commitments"]
    for commitment in commitments:
        filename = str(commitment["part"])
        start, end = commitment["findings"]
        path = source_dir / filename
        payload = path.read_bytes()
        if sha256_bytes(payload) != commitment["sha256"]:
            raise ValueError(f"Source commitment mismatch: {filename}")
        rows = read_jsonl_bytes(payload, filename)
        expected_scope = f"findings-{start}-{end}"
        if len(rows) != commitment["record_count"] or len(rows) != end - start + 1:
            raise ValueError(f"Unexpected row count in {filename}")
        for row in rows:
            if set(row) != {"finding_id", "status", "rationale", "reviewer_model", "review_scope", "input_commit"}:
                raise ValueError(f"Unexpected source fields in {filename}")
            if row["status"] not in config["decision_binding"]:
                raise ValueError(f"Unexpected triage status in {filename}")
            if row["reviewer_model"] != source_policy["expected_reviewer_model"]:
                raise ValueError(f"Unexpected reviewer model in {filename}")
            if row["input_commit"] not in source_policy["accepted_input_commits"]:
                raise ValueError(f"Unexpected input binding in {filename}")
            if row["review_scope"] != expected_scope:
                raise ValueError(f"Unexpected review scope in {filename}")
            if not isinstance(row["finding_id"], str) or len(row["finding_id"]) != 64:
                raise ValueError(f"Invalid finding id in {filename}")
            if not isinstance(row["rationale"], str) or not row["rationale"].strip():
                raise ValueError(f"Missing rationale in {filename}")
        records.extend(rows)
    return records, list(commitments)


def build(source_dir: Path) -> tuple[bytes, bytes]:
    contract = read_json(PACKAGE / "audit-contract.json")
    config = triage_config(contract)
    findings = read_jsonl(PACKAGE / "findings.jsonl")
    source_records, source_commitments = source_part_records(source_dir, contract)
    finding_ids = [str(record["finding_id"]) for record in findings]
    source_ids = [str(record["finding_id"]) for record in source_records]
    if len(source_ids) != len(finding_ids) or source_ids != finding_ids or len(set(source_ids)) != len(source_ids):
        raise ValueError("Triage records must be an exact ordered partition of findings.jsonl")
    reviews = [{
        "audit": contract["audit_id"],
        "finding_id": source["finding_id"],
        "reviewer": config["public_binding"]["review_identity"]["reviewer"],
        "decision": config["decision_binding"][source["status"]],
        "audit_input_hashes": contract["frozen_input_hashes"],
        "evidence_hashes": [],
        "evidence_scope": source["review_scope"],
        "rationale": source["rationale"],
    } for source in source_records]
    validate_records(reviews, contract, finding_ids)
    status_counts = dict(sorted(Counter(record["status"] for record in source_records).items()))
    decision_counts = {**Counter(record["decision"] for record in reviews), "propose_change": 0}
    if status_counts != config["expected_status_counts"] or dict(sorted(decision_counts.items())) != config["expected_decision_counts"]:
        raise ValueError("Unexpected semantic-triage counts")
    summary = {
        "format": "hbq-full-leaf-structural-audit-sol-triage-summary-v1",
        "audit": contract["audit_id"],
        "review_identity": config["public_binding"]["review_identity"],
        "input_commit": config["public_binding"]["input_commit"],
        "record_count": len(reviews),
        "status_counts": status_counts,
        "decision_counts": dict(sorted(decision_counts.items())),
        "decision_binding": config["decision_binding"],
        "source_part_commitments": source_commitments,
        "bindings": {
            "audit_input_hashes": contract["frozen_input_hashes"],
            "finding_order": "findings.jsonl canonical order",
            "evidence_hashes": "empty for every record",
            "repair_authorization": config["repair_authorization"],
        },
    }
    return b"".join(canonical_json(review) for review in reviews), canonical_json(summary)


def validate_records(records: Iterable[Mapping[str, Any]], contract: Mapping[str, Any] | None = None, finding_ids: list[str] | None = None) -> None:
    binding = contract or read_json(PACKAGE / "audit-contract.json")
    config = triage_config(binding)
    validator = Draft202012Validator(read_json(PACKAGE / "sol-review.schema.json"))
    expected_ids = finding_ids or [record["finding_id"] for record in read_jsonl(PACKAGE / "findings.jsonl")]
    observed_ids = []
    module = audit_module()
    for record in records:
        errors = list(validator.iter_errors(record))
        if errors:
            raise ValueError(f"Sol review schema failure: {errors[0].message}")
        module.validate_review_record(record, binding)
        if record["reviewer"] != config["public_binding"]["review_identity"]["reviewer"] or record["evidence_hashes"] or record["decision"] == config["prohibited_decision"]:
            raise ValueError("Published triage exceeds its bound review contract")
        observed_ids.append(record["finding_id"])
    if observed_ids != expected_ids or len(set(observed_ids)) != len(observed_ids):
        raise ValueError("Published triage is not the exact ordered finding inventory")


def validate_published_bytes(triage_payload: bytes, summary_payload: bytes, contract: Mapping[str, Any] | None = None) -> None:
    binding = contract or read_json(PACKAGE / "audit-contract.json")
    config = triage_config(binding)
    if sha256_bytes(triage_payload) != config["record_sha256"]:
        raise ValueError("Published triage record SHA-256 mismatch")
    if sha256_bytes(summary_payload) != config["summary_sha256"]:
        raise ValueError("Published triage summary SHA-256 mismatch")
    records = read_jsonl_bytes(triage_payload, config["record_file"])
    try:
        summary = json.loads(summary_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Published triage summary is not UTF-8 JSON") from exc
    validate_records(records, binding)
    expected = {
        "audit": binding["audit_id"],
        "review_identity": config["public_binding"]["review_identity"],
        "input_commit": config["public_binding"]["input_commit"],
        "record_count": len(records),
        "status_counts": config["expected_status_counts"],
        "decision_counts": config["expected_decision_counts"],
        "decision_binding": config["decision_binding"],
        "source_part_commitments": config["source_part_commitments"],
    }
    if any(summary.get(key) != value for key, value in expected.items()):
        raise ValueError("Published triage summary binding mismatch")
    bindings = summary.get("bindings")
    if not isinstance(bindings, Mapping) or bindings.get("audit_input_hashes") != binding["frozen_input_hashes"] or bindings.get("repair_authorization") != config["repair_authorization"]:
        raise ValueError("Published triage frozen-input or repair binding mismatch")


def validate_published() -> None:
    contract = read_json(PACKAGE / "audit-contract.json")
    config = triage_config(contract)
    validate_published_bytes((PACKAGE / config["record_file"]).read_bytes(), (PACKAGE / config["summary_file"]).read_bytes(), contract)


def write_or_check(path: Path, payload: bytes, check: bool) -> None:
    if check:
        if not path.exists() or path.read_bytes() != payload:
            raise ValueError(f"Generated output drift: {path.name}")
        return
    path.write_bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, help="directory containing the six bound triage JSONL parts")
    parser.add_argument("--check", action="store_true", help="verify the supplied source reproduces the published outputs")
    arguments = parser.parse_args()
    if arguments.source_dir is None:
        if arguments.check:
            validate_published()
            return
        parser.error("--source-dir is required to generate triage outputs")
    triage, summary = build(arguments.source_dir)
    write_or_check(PACKAGE / "sol-triage.jsonl", triage, arguments.check)
    write_or_check(PACKAGE / "sol-triage-summary.json", summary, arguments.check)
    validate_published()


if __name__ == "__main__":
    main()
