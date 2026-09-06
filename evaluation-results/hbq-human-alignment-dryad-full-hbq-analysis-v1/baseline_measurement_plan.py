"""Render and verify the provider-free fixed batch-8 Dryad baseline plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PROTOCOL_PATH = ROOT / "protocol-v2.json"
CONTRACT_PATH = ROOT / "baseline-measurement-v1.json"
NATIVE_ADMISSION_PATH = ROOT / "native_admission.py"
RENDER_PATH = ROOT / "measurement_render.py"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
CONTRACT_SHA256 = "6ae404e31ecafbeac0ef69814127c5222ac8da5fd24c2700f185ca2f8af5cf37"
NATIVE_ADMISSION_SHA256 = "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
RENDER_SHA256 = "e677c31a22bd11e6f84625a817e10c87da6657234f37fccf1e5f9e56dd919266"
PUBLIC_INPUTS_SHA256 = "6254f58d3366667c9578e2661a1ca0d105a603a0f8affe2d925a767957937c42"
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_INHERITED = ("source", "human_targets", "model_score", "optimization", "comparison", "runtime_bindings")
_PREDECESSORS = (
    ("qualification-v2.json", "a407401ea07b344475e65296fd8eb474d85ec92b3bb909606a382cd62e137c13"),
    ("qualification-attempt-2.json", "90639b16cd68d0a4b36821acdcc8ed802d510122973a8621cc0bbea6cc4a0be8"),
    ("qualification-attempt-1.json", "0a45387965f57a520db1bd2211187e24705fcdfe2ea0f39691b93cfc314a504f"),
    ("terminal-identities-v1.json", "62fe2cc523cf8d22dff7f1010980ae98a19338f881d861bdf371ab5f3e37a52f"),
)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"


def _plain(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "Path contains a link or reparse point")
    result = absolute.resolve()
    if directory is True:
        require(result.is_dir(), "Expected directory")
    if directory is False:
        require(result.is_file(), "Expected file")
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            require(key not in value, f"{label} has duplicate keys")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def _contract() -> tuple[bytes, dict[str, Any]]:
    raw = _plain(CONTRACT_PATH, directory=False).read_bytes()
    require(digest(raw) == CONTRACT_SHA256, "Baseline measurement contract drift")
    contract = _json(raw, "Baseline measurement contract")
    parent = contract.get("parent_protocol")
    execution = contract.get("execution")
    require(set(contract) == {"schema_version", "status", "study_id", "parent_protocol", "predecessor_evidence", "public_inputs_sha256", "execution", "limitations"} and contract.get("schema_version") == 1 and contract.get("status") == "prospective_no_provider_authority" and contract.get("study_id") == "dryad-fixed-batch8-measurement-v1" and contract.get("public_inputs_sha256") == PUBLIC_INPUTS_SHA256 and isinstance(parent, Mapping) and isinstance(execution, Mapping) and isinstance(contract.get("limitations"), list), "Baseline measurement contract differs")
    require(parent == {"path": "protocol-v2.json", "sha256": PROTOCOL_SHA256, "inherited_sections": list(_INHERITED), "excluded_sections": ["execution", "shared_runtime_bindings"]}, "Baseline protocol boundary differs")
    require(contract.get("predecessor_evidence") == [{"path": path, "sha256": digest} for path, digest in _PREDECESSORS], "Baseline predecessor evidence differs")
    require(set(execution) == {"provider_calls_authorized_by_this_file", "dispatch_batch_size", "empirical_batch_cap", "response_schema_mode", "namespace", "purpose", "selection_reason", "qualification_status", "release_qualification_satisfied", "geometry", "schedule", "artifact_identity", "data_policy", "attempt_policy", "native_execution_prerequisites", "provider_transport_authority"} and execution.get("dispatch_batch_size") == 8 and execution.get("empirical_batch_cap") is None and execution.get("response_schema_mode") == "batch_question_ids_v1" and execution.get("namespace") == "baseline8-v1" and execution.get("purpose") == "fresh_fixed_baseline_measurement" and execution.get("provider_calls_authorized_by_this_file") is False and execution.get("release_qualification_satisfied") is False, "Baseline execution boundary differs")
    require(execution.get("geometry") == {"train_stories": 176, "dev_stories": 60, "questions_per_story": 178, "passes_per_story_per_endpoint": 1, "logical_requests_per_endpoint": 5428} and isinstance(execution.get("schedule"), str) and isinstance(execution.get("artifact_identity"), str) and isinstance(execution.get("data_policy"), str) and isinstance(execution.get("attempt_policy"), str) and isinstance(execution.get("provider_transport_authority"), str) and isinstance(execution.get("native_execution_prerequisites"), list), "Baseline geometry or execution disclosures differ")
    return raw, contract


def _predecessors(contract: Mapping[str, Any]) -> tuple[list[dict[str, str]], dict[Path, bytes]]:
    records = contract["predecessor_evidence"]
    require(isinstance(records, list), "Baseline predecessor evidence differs")
    captures: dict[Path, bytes] = {}
    for record, (relative, expected) in zip(records, _PREDECESSORS, strict=True):
        require(record == {"path": relative, "sha256": expected}, "Baseline predecessor evidence differs")
        path = _plain(ROOT / relative, directory=False)
        require(path.parent == ROOT, "Baseline predecessor path differs")
        raw = path.read_bytes()
        require(digest(raw) == expected, f"Baseline predecessor hash drift: {relative}")
        captures[path] = raw
    return [dict(record) for record in records], captures


def _helper() -> tuple[ModuleType, bytes]:
    path = _plain(NATIVE_ADMISSION_PATH, directory=False)
    raw = path.read_bytes()
    require(digest(raw) == NATIVE_ADMISSION_SHA256, "Native admission source pin differs")
    name = "_dryad_baseline_native_" + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - Only hash-pinned repository code is compiled.
        return module, raw
    finally:
        sys.modules.pop(name, None)


def _renderer() -> tuple[ModuleType, bytes]:
    path = _plain(RENDER_PATH, directory=False)
    raw = path.read_bytes()
    require(digest(raw) == RENDER_SHA256, "Measurement renderer source pin differs")
    name = "_dryad_baseline_render_" + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - Only hash-pinned repository code is compiled.
        return module, raw
    finally:
        sys.modules.pop(name, None)


def _runtime(protocol_raw: bytes, response_schema_mode: str | None) -> tuple[Any, dict[Path, bytes]]:
    protocol = _json(protocol_raw, "Protocol")
    require(digest(protocol_raw) == PROTOCOL_SHA256, "Analysis protocol drift")
    bindings = protocol.get("runtime_bindings")
    require(isinstance(bindings, dict) and all(isinstance(path, str) and _HASH.fullmatch(value) for path, value in bindings.items()), "Protocol runtime bindings differ")
    helper, helper_raw = _helper()
    supplementary = getattr(helper, "SUPPLEMENTARY_PINS", None)
    require(isinstance(supplementary, dict) and all(isinstance(path, str) and _HASH.fullmatch(value) for path, value in supplementary.items()), "Supplementary runtime bindings differ")
    captures: dict[Path, bytes] = {PROTOCOL_PATH: protocol_raw, NATIVE_ADMISSION_PATH: helper_raw}
    for relative, expected in {**bindings, **supplementary}.items():
        path = _plain(REPOSITORY / relative, directory=False)
        raw = path.read_bytes()
        require(digest(raw) == expected, f"Runtime hash drift: {relative}")
        captures[path] = raw
    def verify() -> None:
        require(all(path.read_bytes() == raw for path, raw in captures.items()), "Rendering runtime changed during operation")
    hbq = helper._private_modules(REPOSITORY / "src/hbqrs", ("core", "paths", "weights", "runner", "grok_broker_transport"), captures)
    require(hbq["paths"].book_root().resolve() == REPOSITORY.resolve(), "HBQ book root differs from pinned source")
    core = hbq["core"]
    modules = core.load_modules(REPOSITORY / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(REPOSITORY / "bundles/all_bundles.json"), "prose.short_story")
    compiled = core.compile_bundle(modules, bundle)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order[item["role"]])
    require(len(questions) == 178, "Full-HBQ question inventory drift")
    require(response_schema_mode in {None, "batch_question_ids_v1"}, "Baseline schema mode differs")
    verify()
    return SimpleNamespace(runner=hbq["runner"], weights=hbq["weights"], modules=modules, bundle=bundle, compiled=compiled, questions=questions, response_schema_mode=response_schema_mode, verify=verify), captures


def _sources() -> dict[Path, bytes]:
    contract_raw, contract = _contract()
    _, predecessor_captures = _predecessors(contract)
    protocol_raw = _plain(PROTOCOL_PATH, directory=False).read_bytes()
    require(digest(protocol_raw) == PROTOCOL_SHA256, "Analysis protocol drift")
    helper_raw = _plain(NATIVE_ADMISSION_PATH, directory=False).read_bytes()
    require(digest(helper_raw) == NATIVE_ADMISSION_SHA256, "Native admission source pin differs")
    renderer_raw = _plain(RENDER_PATH, directory=False).read_bytes()
    require(digest(renderer_raw) == RENDER_SHA256, "Measurement renderer source pin differs")
    return {Path(__file__).resolve(): Path(__file__).read_bytes(), CONTRACT_PATH: contract_raw, PROTOCOL_PATH: protocol_raw, NATIVE_ADMISSION_PATH: helper_raw, RENDER_PATH: renderer_raw, **predecessor_captures}


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    require(all(path.read_bytes() == raw for path, raw in captured.items()), "Baseline measurement source changed during operation")


def _generator_identity(captured: Mapping[Path, bytes], commit: str | None = None) -> dict[str, Any]:
    if commit is None:
        result = subprocess.run(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], capture_output=True, check=False)
        commit = result.stdout.decode("ascii", errors="strict").strip() if not result.returncode else ""
    require(_COMMIT.fullmatch(commit or "") is not None, "Baseline generator commit is invalid")
    for path, raw in captured.items():
        relative = path.relative_to(REPOSITORY).as_posix()
        result = subprocess.run(["git", "-C", str(REPOSITORY), "show", f"{commit}:{relative}"], capture_output=True, check=False)
        require(not result.returncode and result.stdout == raw, "Baseline preparation requires committed byte-exact generator source")
    _unchanged(captured)
    return {"evidence_class": "committed_source", "git_commit": commit, "files": {path.relative_to(REPOSITORY).as_posix(): digest(raw) for path, raw in captured.items()}}


def _output(public_inputs_path: Path, output_root: Path, *, fresh: bool) -> Path:
    source = _plain(public_inputs_path, directory=False)
    output = _plain(output_root)
    for protected in (REPOSITORY, ROOT, source.parent):
        checked = _plain(protected, directory=True)
        require(not output.is_relative_to(checked) and not checked.is_relative_to(output), "Baseline output overlaps protected source or parent output")
    if fresh:
        require(not output.exists(), "Baseline output directory must be fresh")
    return output


def build_plan(public_inputs_raw: bytes, runtime: Any, *, generator: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    contract_raw, contract = _contract()
    predecessor_evidence, predecessor_captures = _predecessors(contract)
    protocol_raw = _plain(PROTOCOL_PATH, directory=False).read_bytes()
    require(digest(protocol_raw) == PROTOCOL_SHA256, "Analysis protocol drift")
    protocol = _json(protocol_raw, "Protocol")
    require(set(protocol).issuperset(_INHERITED), "Parent protocol differs")
    inherited = {name: protocol[name] for name in _INHERITED}
    renderer, renderer_raw = _renderer()
    sources = renderer.load_inputs(public_inputs_raw, expected_sha256=PUBLIC_INPUTS_SHA256)
    rendered, artifacts = renderer.render(sources, runtime, batch_size=8, namespace={"logical_sample_prefix": "baseline8-v1-", "pass_prefix": "baseline8-v1/"}, purpose="fresh_fixed_baseline_measurement", protocol=protocol, response_schema_mode=contract["execution"]["response_schema_mode"])
    require(rendered["counts"] == {"train_stories": 176, "dev_stories": 60, "stories": 236, "questions_per_story": 178, "logical_requests": 5428}, "Baseline geometry differs")
    plan = {
        "schema_version": 1,
        "evidence_class": "provider_free_fixed_baseline_measurement_plan",
        "native_admission": False,
        "execution_authority": False,
        "provider_calls": 0,
        "purpose": "fresh_fixed_baseline_measurement",
        "namespace": {"name": "baseline8-v1", "pass_prefix": "baseline8-v1/", "logical_sample_prefix": "baseline8-v1-", "disallowed_qualification_pass_prefixes": ["size-", "measurement/"], "disallowed_qualification_logical_sample_prefixes": ["qualification-", "measurement-"]},
        "public_inputs_sha256": digest(public_inputs_raw),
        "generator": dict(generator),
        "baseline_contract": {"path": CONTRACT_PATH.relative_to(REPOSITORY).as_posix(), "sha256": digest(contract_raw)},
        "parent_protocol": {"path": PROTOCOL_PATH.relative_to(REPOSITORY).as_posix(), "sha256": digest(protocol_raw), "inherited_sections": inherited},
        "predecessor_evidence": predecessor_evidence,
        "dispatch_batch_size": 8,
        "empirical_batch_cap": None,
        "runtime": rendered["runtime"],
        "response_schema": rendered["response_schema"],
        "endpoints": {"grok": {"provider": "grok", "model": "grok-4.6", "native_execution_authority": False}, "sol": {"provider": "codex", "model": "gpt-5.6-sol", "native_execution_authority": False}},
        "counts": {**rendered["counts"], "complete_passes_per_endpoint": 236, "logical_requests_per_endpoint": 5428},
        "passes": rendered["passes"],
        "requests": rendered["requests"],
    }
    if rendered["response_schema_mode"] is not None:
        plan["response_schema_mode"] = rendered["response_schema_mode"]
    artifacts["plan.json"] = _canonical(plan)
    runtime.verify()
    require(CONTRACT_PATH.read_bytes() == contract_raw and PROTOCOL_PATH.read_bytes() == protocol_raw and RENDER_PATH.read_bytes() == renderer_raw and all(path.read_bytes() == raw for path, raw in predecessor_captures.items()), "Baseline contract, protocol, renderer, or predecessor changed during rendering")
    return plan, artifacts


def _inventory(output_root: Path, artifacts: Mapping[str, bytes]) -> None:
    paths = list(output_root.rglob("*"))
    for path in paths:
        _plain(path)
        require(path.is_file() or path.is_dir(), "Baseline plan contains a special file")
    actual = {path.relative_to(output_root).as_posix(): path for path in paths if path.is_file()}
    require(set(actual) == set(artifacts), "Baseline artifact inventory differs")
    expected_directories = {parent.as_posix() for relative in artifacts for parent in Path(relative).parents if parent != Path(".")}
    actual_directories = {path.relative_to(output_root).as_posix() for path in paths if path.is_dir()}
    require(actual_directories == expected_directories, "Baseline directory inventory differs")
    for relative, raw in artifacts.items():
        require(actual[relative].read_bytes() == raw, f"Baseline artifact byte drift: {relative}")
    require(not (output_root / "runs").exists(), "Baseline plan must not contain results")


def prepare(public_inputs_path: Path, output_root: Path) -> dict[str, str]:
    public_inputs_path = _plain(public_inputs_path, directory=False)
    output_root = _output(public_inputs_path, output_root, fresh=True)
    captured = _sources()
    generator = _generator_identity(captured)
    runtime, runtime_captures = _runtime(captured[PROTOCOL_PATH], _contract()[1]["execution"]["response_schema_mode"])
    public_raw = public_inputs_path.read_bytes()
    _, artifacts = build_plan(public_raw, runtime, generator=generator)
    runtime.verify(); _unchanged({**captured, **runtime_captures})
    require(public_inputs_path.read_bytes() == public_raw, "Public inputs changed during preparation")
    output_root = _output(public_inputs_path, output_root, fresh=True)
    _plain(output_root.parent, directory=True)
    output_root.mkdir(parents=True, exist_ok=False)
    for relative, raw in sorted(artifacts.items()):
        path = output_root / relative
        _plain(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        _plain(path.parent, directory=True)
        require(path.is_relative_to(output_root), "Baseline artifact escapes output root")
        with path.open("xb") as stream:
            stream.write(raw)
    runtime.verify(); _unchanged({**captured, **runtime_captures})
    require(public_inputs_path.read_bytes() == public_raw, "Public inputs changed after preparation")
    _inventory(output_root, artifacts)
    return {relative: digest(raw) for relative, raw in sorted(artifacts.items())}


def verify(public_inputs_path: Path, output_root: Path) -> dict[str, str]:
    public_inputs_path = _plain(public_inputs_path, directory=False)
    output_root = _output(public_inputs_path, output_root, fresh=False)
    recorded = _json(_plain(output_root / "plan.json", directory=False).read_bytes(), "Baseline plan")
    captured = _sources()
    generator = _generator_identity(captured, recorded.get("generator", {}).get("git_commit"))
    require(recorded.get("generator") == generator, "Baseline generator identity differs")
    runtime, runtime_captures = _runtime(captured[PROTOCOL_PATH], _contract()[1]["execution"]["response_schema_mode"])
    public_raw = public_inputs_path.read_bytes()
    _, artifacts = build_plan(public_raw, runtime, generator=generator)
    _inventory(output_root, artifacts)
    runtime.verify(); _unchanged({**captured, **runtime_captures})
    require(public_inputs_path.read_bytes() == public_raw, "Public inputs changed during verification")
    return {relative: digest(raw) for relative, raw in sorted(artifacts.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free fixed-baseline Dryad measurement plan preparation and verification.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--public-inputs", required=True, type=Path)
        command.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    action = prepare if args.command == "prepare" else verify
    print(json.dumps(action(args.public_inputs, args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
