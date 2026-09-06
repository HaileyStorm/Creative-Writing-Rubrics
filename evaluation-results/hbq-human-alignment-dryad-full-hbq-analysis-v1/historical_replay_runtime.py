"""Read-only historical v2 runtime loader; it grants no provider authority."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SHARED = Path.home() / ".codex/tools/model_work_queue"
ROLLBACK_BASE = Path.home() / ".codex/state/universal-harness-evidence/model-work-queue-ee1e9eb"
ROLLBACK = ROLLBACK_BASE / "rollback"
MANIFEST = ROLLBACK_BASE / "rollback-manifest.json"
PROTOCOL = ROOT / "protocol-v2.json"
NATIVE = ROOT / "native_admission.py"
MANIFEST_SHA256 = "8526728eb65e2941c7e4244f54c2c49da118538ead29375daa2b38c2093b077a"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
NATIVE_SHA256 = "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
HISTORICAL = {"broker.py": "6f7b4a2c1bf68ac58ccfb68e13e783301d6e73fd9a1f6f2f0355698546c4c77c", "adapters/grok_exec.py": "f870671d90fde2670dd62c155488b004cee9d900b4f5185921b26323034a75f7"}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _plain(path: Path, *, file: bool = True) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try: info = candidate.lstat()
        except FileNotFoundError: continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "Historical storage contains a link or reparse point")
    result = absolute.resolve()
    require(result.is_file() if file else result.is_dir(), "Historical storage path differs")
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"{label} is malformed") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def _read(path: Path, expected: str, captures: dict[Path, bytes]) -> bytes:
    checked = _plain(path); raw = checked.read_bytes()
    require(digest(raw) == expected, "Historical runtime source pin differs")
    _plain(checked); captures[checked] = raw
    return raw


def _native() -> tuple[ModuleType, bytes]:
    raw = _plain(NATIVE).read_bytes(); require(digest(raw) == NATIVE_SHA256, "Native admission source pin differs")
    module = ModuleType("_dryad_historical_native_" + uuid.uuid4().hex); module.__file__, module.__package__ = str(NATIVE), ""
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(NATIVE), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local definitions.
        return module, raw
    finally: sys.modules.pop(module.__name__, None)


def _shared_modules(storage: Mapping[str, Path], captures: Mapping[Path, bytes]) -> dict[str, ModuleType]:
    prefix = "_dryad_historical_shared_" + uuid.uuid4().hex; package = ModuleType(prefix); package.__path__ = []; sys.modules[prefix] = package; loaded: dict[str, ModuleType] = {}
    try:
        for name in ("adapters.json_schema_subset", "image_canary", "grok_usage_evidence", "prepare_grok_evidence", "broker", "adapters.grok_exec"):
            if "." in name:
                parent = prefix + "." + name.rsplit(".", 1)[0]
                if parent not in sys.modules:
                    holder = ModuleType(parent); holder.__path__ = []; sys.modules[parent] = holder; setattr(package, name.split(".")[0], holder)
            path = storage[name]; module = ModuleType(prefix + "." + name); module.__file__, module.__package__ = str(path), module.__name__.rpartition(".")[0]
            sys.modules[module.__name__] = module; setattr(sys.modules[module.__package__], name.rsplit(".", 1)[-1], module)
            exec(compile(captures[path], str(path), "exec"), module.__dict__)  # noqa: S102 - exact historical source commitments.
            loaded[name] = module
        return loaded
    finally:
        for name in list(sys.modules):
            if name == prefix or name.startswith(prefix + "."): sys.modules.pop(name, None)


def load_runtime() -> Any:
    """Load pinned code bytes only; never instantiate, arm, or contact a provider."""
    captures: dict[Path, bytes] = {_plain(Path(__file__)): Path(__file__).read_bytes()}
    protocol_raw = _read(PROTOCOL, PROTOCOL_SHA256, captures); protocol = _json(protocol_raw, "Protocol")
    manifest_raw = _read(MANIFEST, MANIFEST_SHA256, captures); manifest = _json(manifest_raw, "Rollback manifest")
    require(manifest == {"schema_version": 1, "captured_at": manifest["captured_at"], "target_root": str(SHARED), "source_commit_before": manifest["source_commit_before"], "files": {**HISTORICAL, "test_grok_adapter.py": manifest["files"].get("test_grok_adapter.py"), "README.md": manifest["files"].get("README.md")}, "rollback_root": "rollback", "scope": "source_bytes_only_no_runtime_state"} and isinstance(manifest["captured_at"], str) and isinstance(manifest["source_commit_before"], str), "Rollback manifest differs")
    native, native_raw = _native(); captures[_plain(NATIVE)] = native_raw
    execution = protocol.get("execution"); require(isinstance(execution, dict) and execution.get("response_schema_mode") in {None, "batch_question_ids_v1"}, "Protocol execution differs")
    for relative, expected in {**protocol["runtime_bindings"], **native.SUPPLEMENTARY_PINS}.items(): _read(REPOSITORY / relative, expected, captures)
    storage: dict[str, Path] = {}
    for relative, expected in protocol["shared_runtime_bindings"].items():
        path = ROLLBACK / relative if relative in HISTORICAL else SHARED / relative
        storage[relative[:-3].replace("/", ".")] = _plain(path); _read(path, HISTORICAL.get(relative, expected), captures)
    require(set(storage) == {"prepare_grok_evidence", "broker", "adapters.grok_exec", "adapters.json_schema_subset", "image_canary", "grok_usage_evidence"}, "Historical storage map differs")
    def verify() -> None:
        require(all(_plain(path).read_bytes() == raw for path, raw in captures.items()), "Historical runtime changed during replay")
    hbq = native._private_modules(REPOSITORY / "src/hbqrs", ("core", "paths", "weights", "runner", "grok_broker_transport"), captures)
    shared = _shared_modules(storage, captures)
    require(hbq["paths"].book_root().resolve() == REPOSITORY.resolve(), "HBQ root differs")
    core = hbq["core"]; modules = core.load_modules(REPOSITORY / "registry/all_modules.json"); bundle = core.resolve_bundle(core.load_bundles(REPOSITORY / "bundles/all_bundles.json"), "prose.short_story"); compiled = core.compile_bundle(modules, bundle)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}; questions = sorted(core.compiled_questions(compiled), key=lambda item: order[item["role"]]); require(len(questions) == 178, "Question inventory differs")
    verify()
    return SimpleNamespace(core=core, runner=hbq["runner"], weights=hbq["weights"], broker=shared["broker"], transport=hbq["grok_broker_transport"], transport_sha256=protocol["runtime_bindings"]["src/hbqrs/grok_broker_transport.py"], adapter=shared["adapters.grok_exec"], modules=modules, bundle=bundle, compiled=compiled, questions=questions, response_schema_mode=execution["response_schema_mode"], verify=verify, provenance={"evidence_class": "historical_v2_runtime_loader_only", "provider_calls": 0, "native_admission": False, "execution_authority": False, "storage_map": {name: {"logical_path": name.replace(".", "/") + ".py", "storage_path": str(path), "sha256": digest(captures[path])} for name, path in storage.items()}, "source_sha256": {str(path): digest(raw) for path, raw in captures.items()}})
