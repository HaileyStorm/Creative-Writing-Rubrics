"""Provider-free HANNA deployment preflight and exact one-cell disclosure preview."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping

from execution_freeze import ROUTES, validate_execution_freeze
from executor import prepare_cell, preview_cell_disclosure
from study import CONTRACT, _read_bytes_checked, _exact, checked_output_path, checked_path, read_json, require_disjoint_paths, sha256


STUDY_ID = CONTRACT["study_id"]
TrustedRootVerifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _route_availability(*, verifier: TrustedRootVerifier, route: Mapping[str, Any], request_sha256: str, endpoint: str | None, grok_bin: Path | None) -> dict[str, Any]:
    executable = None
    if route["provider"] == "xai":
        if grok_bin is None:
            raise ValueError("HANNA Grok executable is required")
        candidate = checked_path(grok_bin, must_exist=True)
        raw = _read_bytes_checked(candidate)
        executable = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    elif route["provider"] == "openai":
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("HANNA Sol endpoint is required")
    else:
        raise ValueError("HANNA provider is unsupported")
    request = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "trusted_route_availability",
        "route": dict(route),
        "request_sha256": request_sha256,
        "endpoint": endpoint if route["provider"] == "openai" else None,
        "executable": executable,
        "required_proofs": {"authorization": "proved", "zero_spend": "proved", "paid_api": False},
    }
    try:
        verdict = dict(verifier(request))
    except (TypeError, ValueError) as error:
        raise ValueError("HANNA trusted-root verifier rejected route availability") from error
    _exact(verdict, {"format_version", "study_id", "kind", "provider", "model", "reasoning_effort", "paid_api", "request_sha256", "endpoint", "executable", "authorization_proved", "zero_spend_proved", "trusted_root_id", "verified"}, "trusted route availability")
    if verdict != {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "trusted_route_availability",
        "provider": route["provider"],
        "model": route["model"],
        "reasoning_effort": route["reasoning_effort"],
        "paid_api": False,
        "request_sha256": request_sha256,
        "endpoint": endpoint if route["provider"] == "openai" else None,
        "executable": executable,
        "authorization_proved": True,
        "zero_spend_proved": True,
        "trusted_root_id": verdict["trusted_root_id"],
        "verified": True,
    } or not isinstance(verdict["trusted_root_id"], str) or not verdict["trusted_root_id"].strip():
        raise ValueError("HANNA route authorization or zero-spend availability is unproved")
    return verdict


def _exact_cell(freeze: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    if not isinstance(cell_id, str):
        raise ValueError("HANNA cell ID is invalid")
    matches = [dict(cell) for cell in freeze.get("schedule", []) if cell.get("cell_id") == cell_id]
    if len(matches) != 1 or matches[0].get("partition") not in {"train", "development"}:
        raise ValueError("HANNA preflight accepts only an exact scheduled train/development cell")
    return matches[0]


def preview_preflight_cell(*, freeze_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, cell_id: str, attempt_root: Path, acknowledgement_path: Path, zero_charge_route_receipt_path: Path, trusted_root_verifier: TrustedRootVerifier, endpoint: str | None = None, grok_bin: Path | None = None) -> dict[str, Any]:
    """Validate one externally gated cell and persist its nonpromotable pre-contact disclosure."""
    require_disjoint_paths(freeze_path, frozen_successor_path, hanna_csv_path, attempt_root, acknowledgement_path, zero_charge_route_receipt_path, *( [grok_bin] if grok_bin is not None else []))
    disclosure_preview = preview_cell_disclosure(freeze_path=freeze_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, cell_id=cell_id, endpoint=endpoint, grok_bin=grok_bin)
    freeze = read_json(freeze_path)
    cell = _exact_cell(freeze, cell_id)
    route = ROUTES.get(cell["model"])
    if route is None or cell["provider"] != route["provider"]:
        raise ValueError("HANNA scheduled route drifted")
    availability = _route_availability(verifier=trusted_root_verifier, route=route, request_sha256=disclosure_preview["artifacts_leaving_machine"]["provider_ready_task"]["sha256"], endpoint=endpoint, grok_bin=grok_bin)
    prepared = prepare_cell(
        freeze_path=freeze_path,
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
        cell_id=cell_id,
        output_root=checked_output_path(attempt_root),
        acknowledgement_path=acknowledgement_path,
        zero_charge_route_receipt_path=zero_charge_route_receipt_path,
        trusted_gate_verifier=trusted_root_verifier,
        endpoint=endpoint,
        grok_bin=grok_bin,
    )
    root = checked_path(attempt_root / cell_id, must_exist=True)
    disclosure = read_json(root / "disclosure.json")
    if disclosure != disclosure_preview:
        raise ValueError("HANNA persisted disclosure is not the exact scheduled task")
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "development_transport_preflight_preview",
        "state": "prepared_not_dispatched",
        "provider_calls_made": 0,
        "promotable": False,
        "selector_eligible": False,
        "transport_evidence_class": "development_transport_evidence_only",
        "cell": cell,
        "route_availability": availability,
        "disclosure": disclosure,
        "prepared_cell_sha256": sha256(prepared),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-freeze", required=True, type=Path)
    parser.add_argument("--frozen-successor-contract", required=True, type=Path)
    parser.add_argument("--hanna-csv", required=True, type=Path)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--attempt-root", required=True, type=Path)
    parser.add_argument("--acknowledgement", required=True, type=Path)
    parser.add_argument("--zero-charge-route-receipt", required=True, type=Path)
    parser.error("CLI cannot supply the independently trusted root verifier; call preview_preflight_cell from an approved local deployment integration")


if __name__ == "__main__":
    raise SystemExit(main())
