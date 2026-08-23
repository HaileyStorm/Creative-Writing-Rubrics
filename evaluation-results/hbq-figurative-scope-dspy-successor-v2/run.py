"""Fail-closed v2 entry point; private code loads only after explicit authorization."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from study import FORBIDDEN_REMOTE_ENV, ROOT, load_contract, sha256_file, validate_public_outcome, verify_package


def preflight_remote(*, allow_remote: bool, owner_zero_incremental_charge: bool, private_root: Path) -> None:
    if not allow_remote or not owner_zero_incremental_charge:
        raise PermissionError("Remote execution requires --allow-remote and --owner-zero-incremental-charge")
    forbidden = [name for name in FORBIDDEN_REMOTE_ENV if os.environ.get(name)]
    if forbidden:
        raise PermissionError(f"Forbidden paid/API route configuration present: {', '.join(forbidden)}")
    status = subprocess.run(["codex", "login", "status"], text=True, encoding="utf-8", capture_output=True, check=False)
    if status.returncode != 0 or "Logged in using ChatGPT" not in "\n".join((status.stdout, status.stderr)):
        raise PermissionError("Codex CLI must use ChatGPT subscription authentication")
    (private_root / "subscription-attestation.json").write_text(
        json.dumps({"route": "codex_cli_chatgpt_subscription", "status": "Logged in using ChatGPT"}, sort_keys=True),
        encoding="utf-8",
    )


def load_bound_private_engine(private_root: Path):
    contract = load_contract()
    bindings = contract["bindings"]
    report = verify_package()
    if not report["private_bindings_finalized"]:
        raise PermissionError("Private implementation hash placeholders are not finalized")
    engine = private_root / "private_engine.py"
    freeze_inputs = private_root / "freeze-inputs.json"
    if not engine.is_file() or not freeze_inputs.is_file():
        raise FileNotFoundError("Hash-bound private engine or freeze inputs are unavailable")
    if sha256_file(engine) != bindings["private_engine_sha256"] or sha256_file(freeze_inputs) != bindings["private_freeze_inputs_sha256"]:
        raise PermissionError("Private engine or freeze-input binding drifted")
    spec = importlib.util.spec_from_file_location("hbq_private_dspy_successor_v2", engine)
    if spec is None or spec.loader is None:
        raise ImportError("Private engine cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    if not callable(getattr(module, "execute", None)):
        raise TypeError("Private engine must expose execute(public_root=..., private_root=...)")
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--owner-zero-incremental-charge", action="store_true")
    parser.add_argument("--private-root")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "verification": verify_package()}, sort_keys=True))
        return
    if not args.private_root:
        parser.error("--private-root is required for execution")
    private_root = Path(args.private_root).resolve()
    preflight_remote(
        allow_remote=args.allow_remote,
        owner_zero_incremental_charge=args.owner_zero_incremental_charge,
        private_root=private_root,
    )
    engine = load_bound_private_engine(private_root)
    outcome = engine.execute(public_root=ROOT, private_root=private_root)
    print(json.dumps(validate_public_outcome(outcome), sort_keys=True))


if __name__ == "__main__":
    main()
