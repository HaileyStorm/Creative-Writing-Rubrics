"""Explicit v6 arm; root-owned fresh evidence and shared-gate quiescence required."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

LOADER_SHA256 = "04b9a590c00d27a1528e40b2b30ddee91a2439b4256dd19beb88a5d726e338dd"


def implementation():
    path = Path(__file__).resolve().parent / "derived.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != LOADER_SHA256:
        raise ValueError("Versioned entry loader pin differs")
    spec = importlib.util.spec_from_file_location("cwr_grok_v6_armer_loader", path)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    loader.verify_entry_loader(LOADER_SHA256)
    return loader, loader.load_armer()


def arm(root, *, subscription_evidence, grok_executable=None, ttl_seconds=86_400,
        env=None, runner=None, grok_host_gate_path=None):
    loader, armer = implementation()
    evidence = json.loads(Path(subscription_evidence).read_bytes())
    if (evidence.get("schema_version") != 1 or evidence.get("allowance_evidence") not in {
            "owner_attested_current_subscription_allowance_v1", "grok_settings_usage_v1"}):
        raise ValueError("V6 needs fresh reviewed evidence; historical standing/incident geometry is not reusable")
    kwargs = {} if runner is None else {"runner": runner}
    result = armer.arm(root, subscription_evidence=subscription_evidence,
        grok_executable=grok_executable, ttl_seconds=ttl_seconds, env=env,
        grok_host_gate_path=grok_host_gate_path, max_concurrency=10,
        nonvisual_max_turns=1, nonvisual_history_v5=True, timeout_seconds=900,
        image_canary_result=None, **kwargs)
    result.pop("nonvisual_history_v5")
    result["nonvisual_history_v6"] = True
    result["derived_profile"] = loader.profile_commitment()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--subscription-evidence", type=Path, required=True)
    parser.add_argument("--grok-exe", type=Path, required=True)
    parser.add_argument("--ttl-seconds", type=int, default=86_400)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(args.tools_root.resolve()))
    try:
        result = arm(args.root, subscription_evidence=args.subscription_evidence,
                     grok_executable=args.grok_exe, ttl_seconds=args.ttl_seconds)
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"error_class": type(exc).__name__, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
