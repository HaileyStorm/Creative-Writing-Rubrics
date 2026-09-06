"""Provider-free preparation and verification of post-qualification Dryad measurement plans."""

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
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
CAMPAIGN_PLAN_PATH = ROOT / "campaign_plan.py"
ADMISSION_PATH = ROOT / "campaign_admission.py"
PROTOCOL_PATH = ROOT / "protocol-v2.json"
RENDER_PATH = ROOT / "measurement_render.py"
CAMPAIGN_PLAN_SHA256 = "208337b99c44aead7ab11614381e44238dcdcd0799a8fcc9f0fa3869a15ee472"
ADMISSION_SHA256 = "f52e99767af43aeab9590a9f4a10fe62d1804c1e5acacc5f0dac8dfb537d77b3"
PROTOCOL_SHA256 = "33e7dde670bf212da0ee7c4cd6cf628f9a43949dc597cea47b0d97aa4e158e2b"
RENDER_SHA256 = "e677c31a22bd11e6f84625a817e10c87da6657234f37fccf1e5f9e56dd919266"
PUBLIC_INPUTS_SHA256 = "6254f58d3366667c9578e2661a1ca0d105a603a0f8affe2d925a767957937c42"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


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


def _load(path: Path, expected: str, name: str) -> ModuleType:
    path = _plain(path, directory=False)
    raw = path.read_bytes()
    require(digest(raw) == expected, f"{name} source pin differs")
    module_name = "_dryad_measurement_" + uuid.uuid4().hex
    module = ModuleType(module_name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[module_name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
        return module
    finally:
        sys.modules.pop(module_name, None)


def _renderer() -> ModuleType:
    path = _plain(RENDER_PATH, directory=False)
    raw = path.read_bytes()
    require(digest(raw) == RENDER_SHA256, "Measurement renderer source pin differs")
    module_name = "_dryad_measurement_render_" + uuid.uuid4().hex
    module = ModuleType(module_name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[module_name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
        return module
    finally:
        sys.modules.pop(module_name, None)


def _inputs(raw: bytes) -> list[dict[str, str]]:
    return _renderer().load_inputs(raw, expected_sha256=PUBLIC_INPUTS_SHA256)


def _sources() -> tuple[dict[Path, bytes], tuple[ModuleType, ModuleType]]:
    captured = {CAMPAIGN_PLAN_PATH: CAMPAIGN_PLAN_PATH.read_bytes(), ADMISSION_PATH: ADMISSION_PATH.read_bytes(), PROTOCOL_PATH: PROTOCOL_PATH.read_bytes(), RENDER_PATH: RENDER_PATH.read_bytes()}
    require(digest(captured[CAMPAIGN_PLAN_PATH]) == CAMPAIGN_PLAN_SHA256 and digest(captured[ADMISSION_PATH]) == ADMISSION_SHA256 and digest(captured[PROTOCOL_PATH]) == PROTOCOL_SHA256, "Measurement dependency source pin differs")
    require(digest(captured[RENDER_PATH]) == RENDER_SHA256, "Measurement renderer source pin differs")
    modules = (_load(CAMPAIGN_PLAN_PATH, CAMPAIGN_PLAN_SHA256, "Campaign plan"), _load(ADMISSION_PATH, ADMISSION_SHA256, "Campaign admission"))
    captured[Path(__file__).resolve()] = Path(__file__).read_bytes()
    return captured, modules


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    require(all(path.read_bytes() == raw for path, raw in captured.items()), "Measurement source changed during operation")


def _admission(admission: ModuleType, public_inputs_path: Path, qualification_plan_root: Path, qualification_execution_root: Path, *, plan_sha256: str, settlement_sha256: str, admission_sha256: str, execution_sha256: str) -> dict[str, Any]:
    require(all(_HASH.fullmatch(value) for value in (plan_sha256, settlement_sha256, admission_sha256, execution_sha256)), "Qualification anchors differ")
    result = admission.admit_campaign(public_inputs_path, qualification_plan_root, qualification_execution_root, expected_plan_sha256=plan_sha256, expected_final_settlement_sha256=settlement_sha256, expected_admission_sha256=admission_sha256, expected_execution_sha256=execution_sha256)
    require(isinstance(result, dict) and result.get("evidence_class") == "complete_native_campaign_admission" and result.get("execution_authority") is False and result.get("provider_calls") == 0 and result.get("cap") in {8, 32}, "Qualification admission differs")
    require(result.get("plan_sha256") == plan_sha256 and result.get("admission_sha256") == admission_sha256 and result.get("execution_source_sha256") == execution_sha256 and result.get("ledger_head", {}).get("settlement_sha256") == settlement_sha256, "Qualification admission anchor differs")
    return result


def _output(public_inputs_path: Path, output_root: Path, qualification_plan_root: Path, qualification_execution_root: Path, *, fresh: bool) -> Path:
    source = _plain(public_inputs_path, directory=False)
    output = _plain(output_root)
    protected = (REPOSITORY, ROOT, source.parent, _plain(qualification_plan_root, directory=True), _plain(qualification_execution_root, directory=True))
    for path in protected:
        require(not output.is_relative_to(path) and not path.is_relative_to(output), "Measurement output overlaps protected evidence")
    if fresh:
        require(not output.exists(), "Measurement output must be fresh")
    return output


def _identity(commit: str | None = None) -> dict[str, Any]:
    paths = (Path(__file__).resolve(), CAMPAIGN_PLAN_PATH, ADMISSION_PATH, PROTOCOL_PATH, RENDER_PATH)
    captured = {path: path.read_bytes() for path in paths}
    if commit is None:
        process = subprocess.run(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], capture_output=True, check=False)
        commit = process.stdout.decode("ascii", errors="strict").strip() if not process.returncode else ""
    require(re.fullmatch(r"[0-9a-f]{40}", commit or "") is not None, "Measurement generator commit is invalid")
    for path, raw in captured.items():
        relative = path.relative_to(REPOSITORY).as_posix()
        process = subprocess.run(["git", "-C", str(REPOSITORY), "show", f"{commit}:{relative}"], capture_output=True, check=False)
        require(not process.returncode and process.stdout == raw, "Measurement preparation requires committed byte-exact source")
    require(all(path.read_bytes() == raw for path, raw in captured.items()), "Measurement generator changed")
    return {"evidence_class": "committed_source", "git_commit": commit, "files": {path.relative_to(REPOSITORY).as_posix(): digest(raw) for path, raw in captured.items()}}


def build_plan(public_inputs_raw: bytes, runtime: Any, admission: Mapping[str, Any], *, generator: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    renderer = _renderer()
    sources = _inputs(public_inputs_raw)
    require(admission.get("cap") in {8, 32}, "Admission cap differs")
    cap = admission["cap"]
    protocol = _json(PROTOCOL_PATH.read_bytes(), "Protocol")
    execution = protocol.get("execution")
    require(isinstance(execution, Mapping), "Protocol execution contract differs")
    rendered, artifacts = renderer.render(
        sources, runtime, batch_size=cap,
        namespace={"logical_sample_prefix": "measurement-", "pass_prefix": "measurement/"},
        purpose="fresh_post_qualification_measurement", protocol=protocol,
        response_schema_mode=execution.get("response_schema_mode"),
    )
    plan = {"schema_version": 1, "evidence_class": "provider_free_dryad_measurement_plan", "execution_authority": False, "provider_calls": 0, "purpose": "fresh_post_qualification_measurement", "namespace": {"measurement_pass_prefix": "measurement/", "measurement_logical_sample_prefix": "measurement-", "disallowed_qualification_pass_prefixes": ["size-"], "disallowed_qualification_logical_sample_prefixes": ["qualification-"]}, "public_inputs_sha256": digest(public_inputs_raw), "generator": dict(generator), "qualification_admission": dict(admission), "cap": cap, "runtime": rendered["runtime"], "response_schema": rendered["response_schema"], "endpoints": {"grok": {"provider": "grok", "model": "grok-4.6", "native_execution_authority": False}, "sol": {"provider": "codex", "model": "gpt-5.6-sol", "native_execution_authority": False}}, "counts": rendered["counts"], "passes": rendered["passes"], "requests": rendered["requests"]}
    if rendered["response_schema_mode"] is not None:
        plan["response_schema_mode"] = rendered["response_schema_mode"]
    artifacts["plan.json"] = _canonical(plan)
    runtime.verify()
    return plan, artifacts


def prepare(public_inputs_path: Path, output_root: Path, qualification_plan_root: Path, qualification_execution_root: Path, *, expected_qualification_plan_sha256: str, expected_settlement_sha256: str, expected_admission_sha256: str, expected_execution_sha256: str) -> dict[str, str]:
    captured, (campaign, admission_module) = _sources()
    public_inputs_path, qualification_plan_root, qualification_execution_root = _plain(public_inputs_path, directory=False), _plain(qualification_plan_root, directory=True), _plain(qualification_execution_root, directory=True)
    output_root = _output(public_inputs_path, output_root, qualification_plan_root, qualification_execution_root, fresh=True)
    admission = _admission(admission_module, public_inputs_path, qualification_plan_root, qualification_execution_root, plan_sha256=expected_qualification_plan_sha256, settlement_sha256=expected_settlement_sha256, admission_sha256=expected_admission_sha256, execution_sha256=expected_execution_sha256)
    generator = _identity()
    runtime = campaign._load_runtime()
    runtime.verify()
    public_raw = public_inputs_path.read_bytes()
    _, artifacts = build_plan(public_raw, runtime, admission, generator=generator)
    runtime.verify()
    require(_admission(admission_module, public_inputs_path, qualification_plan_root, qualification_execution_root, plan_sha256=expected_qualification_plan_sha256, settlement_sha256=expected_settlement_sha256, admission_sha256=expected_admission_sha256, execution_sha256=expected_execution_sha256) == admission, "Qualification admission changed during preparation")
    _unchanged(captured); require(public_inputs_path.read_bytes() == public_raw, "Public inputs changed during preparation")
    output_root = _output(public_inputs_path, output_root, qualification_plan_root, qualification_execution_root, fresh=True)
    _plain(output_root.parent, directory=True)
    output_root.mkdir(parents=True, exist_ok=False)
    for relative, raw in sorted(artifacts.items()):
        path = output_root / relative
        _plain(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        _plain(path.parent, directory=True)
        require(path.is_relative_to(output_root), "Measurement artifact escapes output root")
        with path.open("xb") as stream:
            stream.write(raw)
    runtime.verify(); _unchanged(captured)
    return {relative: digest(raw) for relative, raw in sorted(artifacts.items())}


def verify(public_inputs_path: Path, output_root: Path, qualification_plan_root: Path, qualification_execution_root: Path, **anchors: str) -> dict[str, str]:
    public_inputs_path, qualification_plan_root, qualification_execution_root = _plain(public_inputs_path, directory=False), _plain(qualification_plan_root, directory=True), _plain(qualification_execution_root, directory=True)
    output_root = _output(public_inputs_path, output_root, qualification_plan_root, qualification_execution_root, fresh=False)
    recorded = _json(_plain(output_root / "plan.json", directory=False).read_bytes(), "Measurement plan")
    generator = _identity(recorded.get("generator", {}).get("git_commit"))
    captured, (campaign, admission_module) = _sources()
    admission = _admission(admission_module, public_inputs_path, qualification_plan_root, qualification_execution_root, plan_sha256=anchors["expected_qualification_plan_sha256"], settlement_sha256=anchors["expected_settlement_sha256"], admission_sha256=anchors["expected_admission_sha256"], execution_sha256=anchors["expected_execution_sha256"])
    public_raw = public_inputs_path.read_bytes()
    runtime = campaign._load_runtime()
    runtime.verify()
    _, artifacts = build_plan(public_raw, runtime, admission, generator=generator)
    paths = list(output_root.rglob("*"))
    for path in paths:
        _plain(path)
        require(path.is_file() or path.is_dir(), "Measurement plan contains a special file")
    actual = {path.relative_to(output_root).as_posix(): path for path in paths if path.is_file()}
    require(set(actual) == set(artifacts), "Measurement artifact inventory differs")
    expected_directories = {parent.as_posix() for relative in artifacts for parent in Path(relative).parents if parent != Path(".")}
    actual_directories = {path.relative_to(output_root).as_posix() for path in paths if path.is_dir()}
    require(actual_directories == expected_directories, "Measurement directory inventory differs")
    for relative, raw in artifacts.items():
        require(actual[relative].read_bytes() == raw, f"Measurement artifact byte drift: {relative}")
    require(not (output_root / "runs").exists(), "Measurement plan must not contain results")
    runtime.verify()
    require(_admission(admission_module, public_inputs_path, qualification_plan_root, qualification_execution_root, plan_sha256=anchors["expected_qualification_plan_sha256"], settlement_sha256=anchors["expected_settlement_sha256"], admission_sha256=anchors["expected_admission_sha256"], execution_sha256=anchors["expected_execution_sha256"]) == admission, "Qualification admission changed during verification")
    runtime.verify(); _unchanged(captured); require(public_inputs_path.read_bytes() == public_raw, "Public inputs changed during verification")
    return {relative: digest(raw) for relative, raw in sorted(artifacts.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or verify a provider-free post-qualification Dryad measurement plan.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--public-inputs", required=True, type=Path)
        command.add_argument("--output-root", required=True, type=Path)
        command.add_argument("--qualification-plan-root", required=True, type=Path)
        command.add_argument("--qualification-execution-root", required=True, type=Path)
        command.add_argument("--qualification-plan-sha256", required=True)
        command.add_argument("--settlement-sha256", required=True)
        command.add_argument("--admission-sha256", required=True)
        command.add_argument("--execution-sha256", required=True)
    args = parser.parse_args()
    kwargs = {"expected_qualification_plan_sha256": args.qualification_plan_sha256, "expected_settlement_sha256": args.settlement_sha256, "expected_admission_sha256": args.admission_sha256, "expected_execution_sha256": args.execution_sha256}
    print(json.dumps((prepare if args.command == "prepare" else verify)(args.public_inputs, args.output_root, args.qualification_plan_root, args.qualification_execution_root, **kwargs), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
