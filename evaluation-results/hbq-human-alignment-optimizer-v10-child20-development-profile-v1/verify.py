"""Verify the literal child20 opt-in development profile."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v10-child20-development-profile-v1"
V10_COMMIT = "1c10bae"
V10_STUDY_RELATIVE = "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1/study.py"
V10_STUDY_SHA256 = "38ea9c9c0cf96dfc0ca32b64ee6639515600bc01b93e204cdd397bae393b2a6f"
V10_CONTRACT_RELATIVE = "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1/study-contract.json"
V10_CONTRACT_SHA256 = "acf8fbf0f3ef5937d963e53fecf286ae3a606eb62302b0e918468e74b17d9348"
CHILD = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
CHILD_SHA256 = "572d5e6b96251eacf19951a10574aaefb811beb9d7890e9f702b524d3c5465bb"
INSTRUCTION_SHA256 = "e172abcab5284fe415d82cff30e1851f08c6ba8d4baccc764eeccf788a6e036d"
PROFILE_SHA256 = "07cd3652f4792aef082a0e2d9d615229013663b14599abd011637daf8f185a20"
PROFILE_FILE_SHA256 = "b6e16200e6b7fd8f3a8605c0dd53c39a964f0314a0b7e2f9c7b1a909f0d99585"
PUBLIC_FILES = {"README.md", "profile.json", "study-contract.json", "verify.py"}
AUTHORITY = {"status": "development_recommendation_only", "runtime": "none", "selection": "none", "promotion": "none", "generalization": "none", "linux": "none"}
RESULT_PINS = {
    "grok_confirmation": {"commit": "fa24f3b", "relative_path": "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-result-v1/result.json", "sha256": "e94055aeb3993785a3bee1ba09f4a00ba8e6eeb0b48d065d5c983a7097b07c18"},
    "sol_confirmation": {"commit": "e70883d", "relative_path": "evaluation-results/hbq-human-alignment-optimizer-v10-fresh96-confirmation-sol-result-v1/result.json", "sha256": "ecb42d5f1f18786602983a115269493afac8dedabf3d246023882c99adf355e5"},
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    before = path.lstat()
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe artifact")
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, before.st_size)
    if identity != (opened.st_dev, opened.st_ino, opened.st_size) or identity != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("artifact changed while read")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def blob(commit: str, relative: str) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git blob is absent")
    return result.stdout


def pinned(relative: str, commit: str, digest: str, label: str) -> bytes:
    raw = stable(REPO / relative)
    if sha256(raw) != digest or blob(commit, relative) != raw:
        raise ValueError(f"pinned {label} drifted")
    return raw


def load_v10() -> ModuleType:
    path = REPO / V10_STUDY_RELATIVE
    raw = pinned(V10_STUDY_RELATIVE, V10_COMMIT, V10_STUDY_SHA256, "V10 constructor")
    pinned(V10_CONTRACT_RELATIVE, V10_COMMIT, V10_CONTRACT_SHA256, "V10 contract")
    spec = importlib.util.spec_from_file_location("_child20_v10_constructor", path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned V10 constructor cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if stable(path) != raw:
        raise ValueError("pinned V10 constructor changed during load")
    module.contract()
    return module


def reconstruct_child() -> Mapping[str, Any]:
    v10 = load_v10()
    validation = v10._module(v10.VALIDATION, v10.VALIDATION_SHA256, "_child20_profile_validation")
    child = next((row for row in v10._panel(validation) if row.get("candidate_id") == CHILD), None)
    if not isinstance(child, Mapping):
        raise TypeError("V10 panel omitted child20")
    if (child.get("candidate_sha256"), child.get("instruction_sha256"), child.get("profile_sha256")) != (CHILD_SHA256, INSTRUCTION_SHA256, PROFILE_SHA256):
        raise ValueError("child20 constructor identity drifted")
    return child


def verify_literal(profile: Mapping[str, Any]) -> None:
    if set(profile) != {"format_version", "instruction", "instruction_sha256", "profile", "profile_sha256"}:
        raise ValueError("literal profile envelope drifted")
    child = reconstruct_child()
    instruction, profile_raw = child.get("instruction"), child.get("profile_raw")
    if not isinstance(instruction, bytes) or not isinstance(profile_raw, bytes) or len(instruction) != 794 or len(profile_raw) != 1644:
        raise ValueError("child20 literal byte length drifted")
    if profile.get("format_version") != 1 or profile.get("instruction") != instruction.decode("utf-8") or profile.get("profile") != strict(profile_raw + b"\n", "child20 profile"):
        raise ValueError("literal child20 bytes differ from pinned constructor")
    profile_bytes = json.dumps(profile["profile"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if (profile.get("instruction_sha256"), profile.get("profile_sha256"), sha256(instruction), sha256(profile_bytes)) != (INSTRUCTION_SHA256, PROFILE_SHA256, INSTRUCTION_SHA256, PROFILE_SHA256):
        raise ValueError("literal child20 hash drifted")


def verify_result_pins() -> None:
    for name, pin in RESULT_PINS.items():
        raw = pinned(pin["relative_path"], pin["commit"], pin["sha256"], f"{name} result")
        result = strict(raw, f"{name} result")
        if result.get("comparison", {}).get("child_candidate_id") != CHILD:
            raise ValueError(f"{name} result does not measure child20")
    if strict(pinned(RESULT_PINS["grok_confirmation"]["relative_path"], RESULT_PINS["grok_confirmation"]["commit"], RESULT_PINS["grok_confirmation"]["sha256"], "Grok result"), "Grok result").get("endpoint") != "grok_primary":
        raise ValueError("Grok endpoint pin drifted")
    sol = strict(pinned(RESULT_PINS["sol_confirmation"]["relative_path"], RESULT_PINS["sol_confirmation"]["commit"], RESULT_PINS["sol_confirmation"]["sha256"], "Sol result"), "Sol result")
    if sol.get("endpoint") != "sol_later" or sol.get("judge") != {"provider_attested": False, "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high"}:
        raise ValueError("Sol endpoint or judge pin drifted")


def expected_contract() -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "format_version": 1,
        "kind": "literal_public_development_profile_with_pinned_v10_constructor_binding",
        "pins": {"v10_candidate_constructor": {"commit": V10_COMMIT, "contract_relative_path": V10_CONTRACT_RELATIVE, "contract_sha256": V10_CONTRACT_SHA256, "study_relative_path": V10_STUDY_RELATIVE, "study_sha256": V10_STUDY_SHA256}, **RESULT_PINS},
        "profile_file_sha256": PROFILE_FILE_SHA256,
        "prohibitions": ["no provider calls, process launches, queue dispatch, DSPy, or Optuna runtime", "no runtime wiring, endpoint pooling, selection, promotion, generalization, or Linux claim"],
        "study_id": STUDY_ID,
    }


def validate_package(root: Path = HERE) -> dict[str, Any]:
    root = Path(root)
    if {path.name for path in root.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("public package inventory drifted")
    profile_raw = stable(root / "profile.json")
    profile = strict(profile_raw, "literal profile")
    if sha256(profile_raw) != PROFILE_FILE_SHA256:
        raise ValueError("profile file drifted")
    verify_literal(profile)
    contract = strict(stable(root / "study-contract.json"), "study contract")
    if contract != expected_contract():
        raise ValueError("study contract envelope drifted")
    verify_result_pins()
    return {"authority": AUTHORITY["status"], "instruction_sha256": INSTRUCTION_SHA256, "profile_sha256": PROFILE_SHA256, "study_id": STUDY_ID}


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(json.dumps(validate_package(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
