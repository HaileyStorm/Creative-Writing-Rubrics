"""Load exact prospective baseline runtime sources without provider authority."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SHARED = Path.home() / ".codex/tools/model_work_queue"
LOADER = ROOT / "historical_replay_runtime.py"
LOADER_SHA256 = "d98686761c4af296c4132a477bc54c3bcdfc3bb8b0140ffd2681919652fe81f9"
PROTOCOL = ROOT / "protocol-v2.json"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
BRIDGE = "src/hbqrs/grok_broker_transport_v2.py"
SHARED_PATHS = frozenset({"prepare_grok_evidence.py", "broker.py", "adapters/grok_exec.py", "adapters/json_schema_subset.py", "image_canary.py", "grok_usage_evidence.py"})


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _loader() -> tuple[ModuleType, bytes]:
    for path in (LOADER, *LOADER.parents):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "Runtime helper path contains a link or reparse point")
    raw = LOADER.read_bytes()
    require(digest(raw) == LOADER_SHA256, "Runtime helper source differs")
    helper = ModuleType("_dryad_baseline_runtime_helper")
    helper.__file__ = str(LOADER)
    exec(compile(raw, str(LOADER), "exec"), helper.__dict__)  # noqa: S102 - exact hash-pinned local definitions.
    require(helper._plain(LOADER).read_bytes() == raw, "Runtime helper changed while loading")
    return helper, raw


def _manifest(raw: bytes) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Runtime manifest duplicate key")
            result[key] = value
        return result
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite runtime manifest")))
    expected = {"schema_version", "evidence_class", "baseline_plan_sha256", "parent_protocol_sha256", "bridge_path", "bridge_sha256", "shared_runtime_bindings", "adapter_version", "execution_policy", "tools"}
    require(isinstance(value, dict) and set(value) == expected and type(value["schema_version"]) is int and value["schema_version"] == 1 and value["evidence_class"] == "baseline_runtime_source_bindings", "Runtime manifest schema differs")
    require(value["baseline_plan_sha256"] == PLAN_SHA256 and value["parent_protocol_sha256"] == PROTOCOL_SHA256 and value["bridge_path"] == BRIDGE, "Runtime manifest study binding differs")
    require(type(value["adapter_version"]) is int and value["adapter_version"] == 4 and value["execution_policy"] == "bounded_nonvisual_deny_wins_attested" and value["tools"] == "deny_wins_none_attested", "Runtime manifest execution contract differs")
    bindings = value["shared_runtime_bindings"]
    require(isinstance(bindings, dict) and set(bindings) == SHARED_PATHS and all(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha) for sha in [value["bridge_sha256"], *bindings.values()]), "Runtime manifest source inventory differs")
    return value


def load_runtime(manifest_path: Path, *, expected_manifest_sha256: str) -> Any:
    """Verify source bindings only; the caller separately authenticates review/route.

    No manifest field or successful load constitutes a canary, native admission,
    current allowance observation, route arming, or authorization to execute.
    """
    require(isinstance(expected_manifest_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) is not None, "Runtime manifest anchor differs")
    helper, helper_raw = _loader()
    captures = {LOADER: helper_raw}
    raw = helper._read(Path(manifest_path), expected_manifest_sha256, captures)
    manifest = _manifest(raw)
    protocol = helper._json(helper._read(PROTOCOL, PROTOCOL_SHA256, captures), "Protocol")
    native, native_raw = helper._native()
    captures[helper._plain(helper.NATIVE)] = native_raw
    own = helper._plain(Path(__file__))
    captures[own] = own.read_bytes()
    for relative, expected in {**protocol["runtime_bindings"], **native.SUPPLEMENTARY_PINS}.items():
        helper._read(REPOSITORY / relative, expected, captures)
    helper._read(REPOSITORY / BRIDGE, manifest["bridge_sha256"], captures)
    storage = {}
    for relative, expected in manifest["shared_runtime_bindings"].items():
        path = SHARED / relative
        helper._read(path, expected, captures)
        storage[relative[:-3].replace("/", ".")] = helper._plain(path)

    def verify() -> None:
        require(all(helper._plain(path).read_bytes() == data for path, data in captures.items()), "Baseline runtime source changed during operation")

    hbq = native._private_modules(REPOSITORY / "src/hbqrs", ("core", "paths", "weights", "runner", "grok_broker_transport", "grok_broker_transport_v2"), captures)
    shared = helper._shared_modules(storage, captures)
    require(hbq["paths"].book_root().resolve() == REPOSITORY.resolve(), "Baseline runtime book root differs")
    core = hbq["core"]
    modules = core.load_modules(REPOSITORY / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(REPOSITORY / "bundles/all_bundles.json"), "prose.short_story")
    compiled = core.compile_bundle(modules, bundle)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order[item["role"]])
    require(len(questions) == 178, "Baseline runtime question inventory differs")
    verify()
    return SimpleNamespace(core=core, runner=hbq["runner"], weights=hbq["weights"], broker=shared["broker"], adapter=shared["adapters.grok_exec"], transport=hbq["grok_broker_transport_v2"], transport_sha256=manifest["bridge_sha256"], modules=modules, bundle=bundle, compiled=compiled, questions=questions, response_schema_mode="batch_question_ids_v1", verify=verify, provenance={"evidence_class": "prospective_baseline_runtime_source_binding", "manifest_sha256": expected_manifest_sha256, "source_sha256": {str(path): digest(data) for path, data in captures.items()}, "provider_calls": 0, "native_admission": False, "execution_authority": False})
