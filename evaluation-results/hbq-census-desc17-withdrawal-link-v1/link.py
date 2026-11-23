"""Link a published withdrawal to its original result using public bytes only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
AUDIT = "hbq-human-alignment-optimizer-v8-desc17-input-fidelity-audit-v1"
ORIGINAL = "hbq-human-alignment-optimizer-v8-desc17-generalization-grok-result-v1"
AUDIT_FILES = {
    "public-result.json": "915ffabdcc0abb01ac6b68bf752899dfe7d3bbd846c57df9502e61df0e19e1f5",
    "study-contract.json": "315b8626e0f37e2b859946e34f1ed388156bfd8b402cc2be89b00b6c050b8fe5",
    "audit.py": "40383ffc99631e9d6c6d4ef8b8a0369364a0adaa8849282f9d4161abd1cb48b6",
    "README.md": "f6b497745a9d355ebc7cf43f3f4153b1e5c11b22ec90b98e0237f7a01842f9a5",
}
PINS = {
    **{f"evaluation-results/{AUDIT}/{name}": digest for name, digest in AUDIT_FILES.items()},
    f"evaluation-results/{ORIGINAL}/result.json": "efe6d5a9a505784e0e5281014a212546fc68cacb786cc548d2b287138eff9260",
    f"evaluation-results/{ORIGINAL}/publication-manifest.json": "8f9a0043aa479209079ce802fb4fea91e5be0ee7618354b23a610ace6058f81f",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def check_pins(raws: dict[str, bytes]) -> None:
    require(set(raws) == set(PINS), "public source inventory differs")
    for relative, digest in PINS.items():
        require(hashlib.sha256(raws[relative]).hexdigest() == digest, "public source bytes differ")


def generate() -> dict:
    raws = {name: (REPO / name).read_bytes() for name in PINS}
    check_pins(raws)
    # Execute only the admitted public source bytes. Its package validator reads
    # public contract/result files; the private collector entrypoint is not used.
    name = f"evaluation-results/{AUDIT}/audit.py"
    module = types.ModuleType("public_desc17_audit")
    module.__file__ = str(REPO / name)
    exec(compile(raws[name], module.__file__, "exec"), module.__dict__)
    public = module.validate_package()
    require(public["kind"] == "desc17_input_fidelity_audit_withdrawal", "withdrawal kind differs")
    require(public["study_id"] == AUDIT, "withdrawal identity differs")
    require(public["authority"] == {
        "desc17_generalization": "withdrawn", "desc17_semantic_conclusion": "withdrawn",
        "promotion": "none", "runtime": "none"}, "withdrawal authority differs")
    original = public["original_result"]
    require(original["study_id"] == ORIGINAL and original["file_sha256"] == PINS[original["path"]],
            "original result binding differs")
    require(json.loads(raws[original["path"]])["study_id"] == ORIGINAL, "original identity differs")
    check_pins({name: (REPO / name).read_bytes() for name in PINS})
    return {
        "policy": "public_census_withdrawal_relationship_v1",
        "sources": [{"path": name, "sha256": digest} for name, digest in sorted(PINS.items())],
        "relationships": [
            {"package": AUDIT, "relationship": "public_withdrawal_record_validated"},
            {"package": ORIGINAL, "relationship": "semantic_use_withdrawn_by_public_audit", "audit_package": AUDIT},
        ],
        "withdrawn_uses": ["desc17_semantic_conclusion", "desc17_generalization"],
        "historical_unresolved_reference": 54,
        "unresolved_count_recomputed": False,
        "registry_mutated": False,
        "private_locators_resolved": 0,
        "new_native_admissions": 0,
        "new_leaf_admissions": 0,
        "new_votes": 0,
        "provider_calls": 0,
        "limitations": [
            "Validates a published withdrawal declaration and its public result-byte relationship.",
            "Does not replay the private collector or independently reproduce the reported input-fidelity findings.",
            "Does not verify the withdrawal's cited historical Git commit; current public bytes are hash-bound.",
            "Leaves private locators and historical census dispositions unresolved; the reference count is unchanged.",
            "Does not confer native authenticity, runtime, promotion or full research completion authority.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="compare the saved aggregate with public-source regeneration")
    parser.add_argument("--self-test", action="store_true", help="reject a changed public input without filesystem mutation")
    args = parser.parse_args()
    output = canonical(generate())
    if args.self_test:
        raws = {name: (REPO / name).read_bytes() for name in PINS}
        raws[next(iter(PINS))] += b" "
        try:
            check_pins(raws)
        except ValueError:
            print("Changed public input rejected")
        else:
            raise ValueError("changed public input was admitted")
    elif args.verify:
        require((HERE / "aggregate.json").read_bytes() == output, "saved aggregate differs")
        print("Public withdrawal relationship reproduced")
    else:
        sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
