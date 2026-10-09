"""Fail-closed measurement handoff through the frozen full-chain release gates.

The caller must supply independently built, scientifically admitted inputs and
explicit release authority. This module supplies neither a contemporary chain
builder nor native verification. It reads pinned code only until the unchanged
release chain permits label loading; it never runs the standalone analyzer CLI.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import analysis_chain_v5 as boundary
import analysis_measurements_v1 as measurements

POLICY = "matched_ttcw_qualified_measurement_release_v1"
PINS = {
    "analysis.py": "c843cb8bfb54a3cc27955c911c1a8e5aa053d6a2f25a9f4dd3b67479fa22ae19",
    "analysis_chain.py": "96de810dc955c5aac086990aa052b1980079fa67b7a825062045a2dc9805a229",
    "analysis_chain_v3.py": "c9faf4653cde6f5c272e4c0065270b73536e15dfe2c6e4f2c34a6d4c090bb088",
    "analysis_chain_v4.py": "c8f6aad7b238950495204bd6389b89507bf101dfd3d480c14518be564e7106be",
    "analysis_chain_v5.py": "29e1cd82c9944bbe8f219c52e079a7a382bedd267f40b61c92245a498c4f4500",
    "analysis_measurements_v1.py": "7a3ae197cb9f54c36a5e220b29bad4a94160a4f84e7ee55cefc49d839eea169b",
    "measurement_diagnostics_v1.py": "3111b30345c81a6a0fe1b16a0ba03be5e2cd70731f980698322df91d61648364",
}


def release_labels(config, report, joined, endpoints, manifest, loaded, chain, labels, *, explicit_release=False):
    """Require strict supplied qualification, then delegate the existing gates."""
    if explicit_release is not True:
        raise ValueError("Explicit authorized postprediction label release required")
    modules = [loaded["analysis"], chain, loaded["analysis_v3"], loaded["analysis_v4"], boundary, measurements]
    for module in modules:
        path = Path(module.__file__)
        if path.name not in PINS or hashlib.sha256(path.read_bytes()).hexdigest() != PINS[path.name]:
            raise ValueError("Pinned release implementation differs")
    helper = Path(measurements.__file__).with_name("measurement_diagnostics_v1.py")
    if hashlib.sha256(helper.read_bytes()).hexdigest() != PINS[helper.name]:
        raise ValueError("Pinned measurement helper differs")

    originals = chain.planned_rows(manifest)
    chain.label_release_gate(joined)
    if joined.keys() != originals.keys():
        raise ValueError("Joined ledger differs from all original logical slots")
    admitted = {"sol": {}, "grok": {}}
    for identity, record in joined.items():
        if record["request"] != originals[identity] or record.get("terminal_evidence_verified") is not True:
            raise ValueError("Explicit original request and verified terminal evidence required")
        if record["state"] in {"accepted", "semantic_rejected", "completed_schema_rejected"}:
            if record.get("native_evidence_verified") is not True:
                raise ValueError("Explicit completed native verification required")
            index = record.get("source_index")
            if type(index) is not int or not 0 <= index < len(config["sources"]):
                raise ValueError("Completed observation requires its own valid source index")
            if config["sources"][index]["endpoint"] != record["request"]["endpoint"]:
                raise ValueError("Completed observation source endpoint differs")
        if record["state"] == "accepted":
            if record.get("qualified_startup_command_verified") is not True or record.get("accepted") is None:
                raise ValueError("Accepted observation requires verified collection tools disabled")
            if record["accepted"]["request"] != record["request"]:
                raise ValueError("Accepted vote changes its original request")
            admitted[identity[0]][identity[1]] = record["accepted"]
        elif record.get("accepted") is not None:
            raise ValueError("Unaccepted disposition cannot supply a vote")
    if endpoints != admitted:
        raise ValueError("Analysis endpoints differ from qualified accepted ledger")

    base = loaded["analysis"]

    def analyze(manifest, targets, ballots, endpoints, hbq, reps=2000):
        return measurements.analyze(base, manifest, targets, ballots, endpoints, hbq, reps)

    # Preserve the original loaders and all gate bindings. Only the eventual
    # analysis handoff changes in this private copy; historical modules remain.
    private = {**loaded, "analysis": SimpleNamespace(**{**vars(base), "analyze": analyze})}
    result = boundary.release_labels(config, report, joined, endpoints, manifest, private, chain, labels,
                                     explicit_release=True)
    result["measurement_release_extension"] = {
        "policy": POLICY, "source_pins": dict(PINS), "qualification_fields_required": True,
        "contemporary_builder_supplied": False, "native_verification_established_by_adapter": False,
        "release_authority_established_by_adapter": False, "promotion_established": False,
    }
    return result
