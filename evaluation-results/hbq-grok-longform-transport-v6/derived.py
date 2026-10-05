"""Finite, pinned Grok v6 projections; installed modules remain predecessors."""
from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType

HERE = Path(__file__).resolve().parent
POLICY = "cwr_grok_longform_transport_v6_ast_v1"
CONTRACT_NAME = "grok_nonvisual_history_v6"
ADAPTER_VERSION = 6
CONTRACT = {
    "schema_version": 1, "name": CONTRACT_NAME,
    "prompt_utf8_bytes": 400_000, "request_stdin_bytes": 400_000,
    "prompt_history_line_bytes": 400_000, "first_user_message_chunk_line_bytes": 400_000,
    "other_update_line_bytes": 65_536, "updates_bytes": 600_000,
    "summary_bytes": 65_536, "stdout_bytes": 65_536, "stderr_bytes": 65_536,
}
SOURCE_PINS = {
    "broker.py": "0d3e8428e480145e51320cf1638d3955a2ca30dec87559f1b7df07c5cdc0f106",
    "adapters/grok_exec.py": "4d510d6487b372025fc9c98550de51dc5d03afb72de630de962a2086a70a9b60",
    "arm_grok_routes.py": "c7c82e044242c9ae6b6b83f7e1414d6c848fb9cc8f60274511ec57cb325bb394",
}
PRIVATE = {
    "broker.py": "model_work_queue._cwr_longform_v6_broker",
    "adapters/grok_exec.py": "model_work_queue.adapters._cwr_longform_v6_adapter",
    "arm_grok_routes.py": "model_work_queue._cwr_longform_v6_armer",
}
VERSION_COMPARISONS = {
    "adapter_version in {4, 5}": 4,
    "adapter_version not in ({2, 3} if images is not None else {2, 3, 4, 5})": 1,
    "adapter_version == 5": 1,
    "adapter_version != 5": 1,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_root():
    package = importlib.import_module("model_work_queue")
    locations = list(package.__path__)
    if len(locations) != 1:
        raise ValueError("One explicit installed model_work_queue package is required")
    return Path(locations[0]).resolve()


def pinned_sources(root=None):
    root = source_root() if root is None else Path(root).resolve()
    result = {}
    for name, expected in SOURCE_PINS.items():
        path = root / name
        if not path.is_file():
            raise ValueError(f"Pinned predecessor is absent: {name}")
        raw = path.read_bytes()
        if digest(raw) != expected:
            raise ValueError(f"Pinned predecessor differs: {name}")
        result[name] = raw
    return root, result


def projected_tree(name, raw, *, root=None):
    tree = ast.parse(raw.decode("utf-8"), filename=name)
    assignments = ({
        "GROK_NONVISUAL_TRANSPORT_CAPABILITY": CONTRACT_NAME,
        "GROK_NONVISUAL_TRANSPORT_CONTRACT_NAME": CONTRACT_NAME,
        "GROK_NONVISUAL_TRANSPORT_V5": CONTRACT,
    } if name == "broker.py" else {
        "V5_NONVISUAL_TRANSPORT_CONTRACT": CONTRACT,
        "NONVISUAL_V5_ADAPTER_VERSION": ADAPTER_VERSION,
    } if name == "adapters/grok_exec.py" else {
        "ARMER_VERSION": "12-cwr-longform-v6",
    })
    counts = {key: 0 for key in assignments}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in assignments:
                node.value = ast.parse(repr(assignments[key]), mode="eval").body
                counts[key] += 1
    if counts != {key: 1 for key in assignments}:
        raise ValueError("Named constant transformation count differs")
    if name == "broker.py":
        functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_parse_grok_exec_envelope"]
        if len(functions) != 1:
            raise ValueError("Native envelope parser is absent or duplicated")
        version_counts = {key: 0 for key in VERSION_COMPARISONS}
        for node in ast.walk(functions[0]):
            if isinstance(node, ast.Compare):
                key = ast.unparse(node)
                if key in version_counts:
                    for item in ast.walk(node):
                        if isinstance(item, ast.Constant) and type(item.value) is int and item.value == 5:
                            item.value = ADAPTER_VERSION
                    version_counts[key] += 1
        if version_counts != VERSION_COMPARISONS:
            raise ValueError("Native version transformation count differs")
        counts.update(version_counts)
    if name == "arm_grok_routes.py":
        imports = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "model_work_queue.broker"]
        if len(imports) != 1:
            raise ValueError("Armer broker import differs")
        imports[0].module = PRIVATE["broker.py"]
        counts["private_broker_import"] = 1
        wrappers = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id == "wrapper_command"]
        if len(wrappers) != 1 or not isinstance(wrappers[0].value, ast.List):
            raise ValueError("Armer adapter command differs")
        tools = (source_root() if root is None else Path(root)).resolve().parent
        wrappers[0].value.elts.extend([ast.Constant("--tools-root"), ast.Constant(str(tools))])
        counts["explicit_adapter_tools_root"] = 1
    return ast.fix_missing_locations(tree), counts


def profile_commitment(root=None):
    root, sources = pinned_sources(root)
    projections = {}
    for name, raw in sources.items():
        tree, counts = projected_tree(name, raw, root=root)
        projections[name] = {
            "source_sha256": digest(raw), "transformations": counts,
            "effective_ast_sha256": digest(ast.dump(tree, include_attributes=False).encode("utf-8")),
        }
    result = {"policy": POLICY, "contract": CONTRACT, "adapter_version": ADAPTER_VERSION,
              "loader_sha256": digest(Path(__file__).read_bytes()), "projections": projections}
    result["profile_sha256"] = digest(canonical(result))
    return result


def _load(name):
    root, sources = pinned_sources()
    module_name = PRIVATE[name]
    commitment = profile_commitment(root)
    cached = sys.modules.get(module_name)
    if cached is not None:
        if getattr(cached, "_profile_sha256", None) != commitment["profile_sha256"]:
            raise ValueError("Private projected module has a conflicting commitment")
        return cached
    if name == "arm_grok_routes.py":
        load_broker()
    tree, _ = projected_tree(name, sources[name], root=root)
    module = ModuleType(module_name)
    module.__package__ = "model_work_queue.adapters" if name.startswith("adapters/") else "model_work_queue"
    module.__file__ = str(HERE / "arm.py" if name == "arm_grok_routes.py" else root / name)
    module._profile_sha256 = commitment["profile_sha256"]
    sys.modules[module_name] = module
    try:
        exec(compile(tree, str(root / name), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


def load_broker():
    return _load("broker.py")


def load_adapter():
    return _load("adapters/grok_exec.py")


def load_armer():
    return _load("arm_grok_routes.py")


def verify_entry_loader(expected):
    if digest(Path(__file__).read_bytes()) != expected:
        raise ValueError("Versioned entry loader pin differs")
    return profile_commitment()


def qualify_manifest(path, expected_sha256):
    path = Path(path).resolve()
    raw = path.read_bytes()
    if digest(raw) != expected_sha256:
        raise ValueError("Qualification manifest pin differs")
    rows = [r for r in json.loads(raw)["requests"] if r["endpoint"] == "grok"]
    if len(rows) != 232 or sorted(r["endpoint_ordinal"] for r in rows) != list(range(1, 233)):
        raise ValueError("Frozen P4 Grok geometry differs")
    maxima = {key: 0 for key in ("prompt_utf8_bytes", "request_stdin_bytes",
                                "prompt_history_line_bytes", "first_user_message_chunk_line_bytes")}
    for row in rows:
        prompt_path = (path.parent / row["prompt_path"]).resolve()
        if not prompt_path.is_relative_to(path.parent):
            raise ValueError("Frozen prompt locator escapes its manifest")
        prompt_raw = prompt_path.read_bytes()
        if len(prompt_raw) != row["prompt_bytes"] or digest(prompt_raw) != row["prompt_sha256"]:
            raise ValueError("Frozen prompt bytes differ")
        prompt = prompt_raw.decode("utf-8")
        session = "00000000-0000-4000-8000-000000000000"
        history = {"timestamp": "9999-12-31T23:59:59.999999+00:00", "session_id": session,
                   "prompt": prompt, "is_bash": False}
        user = {"method": "session/update", "params": {
            "_meta": {"agentTimestampMs": (1 << 63) - 1, "eventId": "\U0010ffff" * 1024},
            "sessionId": session, "update": {"sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": prompt},
                "_meta": {"modelId": "grok-4.7", "promptIndex": 0}}},
            "timestamp": 253402300799}
        dimensions = {"prompt_utf8_bytes": len(prompt_raw),
            "request_stdin_bytes": len(canonical({"prompt": prompt})),
            "prompt_history_line_bytes": len(json.dumps(history, ensure_ascii=True).encode("utf-8")),
            "first_user_message_chunk_line_bytes": len(json.dumps(user, ensure_ascii=True).encode("utf-8"))}
        for key, size in dimensions.items():
            if size > CONTRACT[key]:
                raise ValueError(f"Frozen prompt exceeds v6 dimension: {key}")
            maxima[key] = max(maxima[key], size)
    return {"manifest_sha256": expected_sha256, "requests_checked": len(rows), "maxima": maxima,
            "first_user_measurement": "synthetic permitted-wrapper serialization, not observed native delivery",
            "provider_calls": 0, "model_context_capacity_proven": False,
            "whole_body_reading_proven": False, "profile": profile_commitment()}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--qualify-manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(args.tools_root.resolve()))
    if args.qualify_manifest:
        if not args.manifest_sha256:
            parser.error("--manifest-sha256 is required with --qualify-manifest")
        result = qualify_manifest(args.qualify_manifest, args.manifest_sha256)
    else:
        result = profile_commitment()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
