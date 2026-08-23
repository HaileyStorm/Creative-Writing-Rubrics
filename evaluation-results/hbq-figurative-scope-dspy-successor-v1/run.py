"""Fail-closed entry point; DSPy is imported only for explicitly authorized execution."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

from study import FORBIDDEN_REMOTE_ENV, ROOT, verify_package


def preflight_remote(*, allow_remote: bool, owner_zero_incremental_charge: bool, private_root: Path) -> None:
    if not allow_remote or not owner_zero_incremental_charge:
        raise PermissionError("Remote execution requires --allow-remote and --owner-zero-incremental-charge")
    forbidden = [name for name in FORBIDDEN_REMOTE_ENV if os.environ.get(name)]
    if forbidden:
        raise PermissionError(f"Forbidden paid/API route configuration present: {', '.join(forbidden)}")
    status = subprocess.run(["codex", "login", "status"], text=True, encoding="utf-8", capture_output=True, check=False)
    if status.returncode != 0 or "Logged in using ChatGPT" not in status.stdout:
        raise PermissionError("Codex CLI must be logged in using ChatGPT subscription authentication")
    (private_root / "subscription-attestation.json").write_text(json.dumps({"route": "codex_cli_chatgpt_subscription", "status": "Logged in using ChatGPT"}, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--owner-zero-incremental-charge", action="store_true")
    parser.add_argument("--private-root")
    args = parser.parse_args()
    if args.dry_run == args.optimize:
        parser.error("Choose exactly one of --dry-run or --optimize")
    if args.dry_run:
        print(json.dumps({"mode": "dry_run", "verification": verify_package()}, sort_keys=True))
        return
    if not args.private_root:
        parser.error("--private-root is required for optimizer execution")
    engine = Path(args.private_root).resolve() / "private_optimizer.py"
    if not engine.is_file():
        parser.error("private optimizer engine is unavailable")
    metadata_path = engine.parent / "freeze-metadata.json"
    if not metadata_path.is_file():
        parser.error("private optimizer metadata is unavailable")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if hashlib.sha256(engine.read_bytes()).hexdigest() != metadata.get("private_optimizer_sha256"):
        parser.error("private optimizer implementation binding drifted")
    preflight_remote(allow_remote=args.allow_remote, owner_zero_incremental_charge=args.owner_zero_incremental_charge, private_root=engine.parent)
    spec = importlib.util.spec_from_file_location("hbq_private_dspy_optimizer", engine)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    print(json.dumps(module.optimize(public_root=ROOT, private_root=engine.parent), sort_keys=True))


if __name__ == "__main__":
    main()
