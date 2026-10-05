"""Pinned v6 nonvisual entry; one turn, 900 seconds, no image mode."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

LOADER_SHA256 = "04b9a590c00d27a1528e40b2b30ddee91a2439b4256dd19beb88a5d726e338dd"


def implementation(tools_root):
    path = Path(__file__).resolve().parents[1] / "derived.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != LOADER_SHA256:
        raise ValueError("Versioned entry loader pin differs")
    sys.path.insert(0, str(Path(tools_root).resolve()))
    spec = importlib.util.spec_from_file_location("cwr_grok_v6_adapter_loader", path)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    loader.verify_entry_loader(LOADER_SHA256)
    return loader, loader.load_adapter()


def run(argv=None, *, stdin=None, stdout=None):
    root_parser = argparse.ArgumentParser(add_help=False)
    root_parser.add_argument("--tools-root", type=Path, required=True)
    root_args, native_args = root_parser.parse_known_args(argv)
    loader, adapter = implementation(root_args.tools_root)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--nonvisual-transport-contract-json")
    parser.add_argument("--nonvisual-max-turns", type=int)
    parser.add_argument("--timeout-seconds", type=int)
    args, _ = parser.parse_known_args(native_args)
    sink = sys.stdout if stdout is None else stdout
    if (args.nonvisual_transport_contract_json != loader.canonical(loader.CONTRACT).decode("utf-8")
            or args.nonvisual_max_turns != 1 or args.timeout_seconds != 900):
        print(json.dumps(adapter._control("definitely_not_contacted", detail="Exact v6 one-turn/900-second profile required"), sort_keys=True), file=sink)
        return 0
    return adapter.run(native_args, stdin=stdin, stdout=stdout)


if __name__ == "__main__":
    raise SystemExit(run())
