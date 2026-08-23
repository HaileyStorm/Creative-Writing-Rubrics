"""Provider-free entry point for the hash-bound v3 no-go settlement."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

from study import ROOT, load_contract, private_bindings_finalized, sha256_file, validate_public_outcome, verify_package


def load_bound_private_engine(private_root: Path):
    contract = load_contract()
    if not private_bindings_finalized(contract):
        raise PermissionError("Private parent and implementation hash placeholders are not finalized")
    engine = private_root / "private_engine.py"
    freeze_inputs = private_root / "freeze-inputs.json"
    bindings = contract["bindings"]
    if not engine.is_file() or not freeze_inputs.is_file():
        raise FileNotFoundError("Hash-bound private settlement inputs are unavailable")
    if sha256_file(engine) != bindings["private_engine_sha256"] or sha256_file(freeze_inputs) != bindings["private_freeze_inputs_sha256"]:
        raise PermissionError("Private settlement binding drifted")
    spec = importlib.util.spec_from_file_location("hbq_private_dspy_successor_v3", engine)
    if spec is None or spec.loader is None:
        raise ImportError("Private settlement engine cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    if not callable(getattr(module, "execute", None)):
        raise TypeError("Private settlement engine must expose execute(public_root=..., private_root=...)")
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--settle", action="store_true")
    parser.add_argument("--private-root")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "verification": verify_package()}, sort_keys=True))
        return
    if not args.private_root:
        parser.error("--private-root is required for settlement")
    private_root = Path(args.private_root).resolve()
    engine = load_bound_private_engine(private_root)
    print(json.dumps(validate_public_outcome(engine.execute(public_root=ROOT, private_root=private_root)), sort_keys=True))


if __name__ == "__main__":
    main()
