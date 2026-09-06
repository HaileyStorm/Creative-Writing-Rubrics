"""Prepare and replay-check the provider-free Dryad batch qualification plan."""

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
QUALIFICATION_PATH = ROOT / "qualification.json"
PROTOCOL_PATH = ROOT / "protocol.json"
NATIVE_ADMISSION_PATH = ROOT / "native_admission.py"
PROTOCOL_SHA256 = "f6cf28247f8759a8a823bbdfb7f94e0af33a2661b9ffeb0ce17a1099662c7441"
QUALIFICATION_SHA256 = "18e2b199bafdf49328402d78a7f9f7b83d408c6140acccb2e35993c046a11989"
PUBLIC_INPUTS_SHA256 = "6254f58d3366667c9578e2661a1ca0d105a603a0f8affe2d925a767957937c42"
NATIVE_ADMISSION_SHA256 = "e061d768449adfaab96b15c62a8ebe213d6de10e9ec6d7755e52d911a57b71ac"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"


def _plain(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Path contains a link or reparse point")
    return absolute.resolve()


def _read_exact(path: Path, expected: str, label: str) -> bytes:
    raw = path.read_bytes()
    require(digest(raw) == expected, f"{label} hash drift")
    return raw


def _load_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def _load_runtime() -> Any:
    raw = _read_exact(NATIVE_ADMISSION_PATH, NATIVE_ADMISSION_SHA256, "Native admission")
    name = "_dryad_campaign_native_" + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__ = str(NATIVE_ADMISSION_PATH)
    module.__package__ = ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(NATIVE_ADMISSION_PATH), "exec"), module.__dict__)
        runtime = module.load_runtime()
        runtime.verify()
        require(NATIVE_ADMISSION_PATH.read_bytes() == raw, "Native admission changed during runtime load")
        return runtime
    finally:
        sys.modules.pop(name, None)


def _load_inputs(raw: bytes, qualification: Mapping[str, Any]) -> list[dict[str, Any]]:
    require(digest(raw) == PUBLIC_INPUTS_SHA256, "Public inputs hash drift")
    value = _load_json(raw, "Public inputs")
    require(set(value) == {"TRAIN", "DEV"}, "Public input partition drift")
    train, development = value["TRAIN"], value["DEV"]
    require(isinstance(train, list) and isinstance(development, list), "Public input partition shape differs")
    records: dict[str, str] = {}
    for partition, rows in (("TRAIN", train), ("DEV", development)):
        for row in rows:
            require(isinstance(row, dict) and set(row) == {"opaque_story_id", "story_text"}, "Public input row shape differs")
            story_id, text = row["opaque_story_id"], row["story_text"]
            require(isinstance(story_id, str) and story_id and isinstance(text, str), "Public input story identity differs")
            require(story_id not in records, "Public input story identity is duplicated")
            records[story_id] = text
    selection = qualification.get("selection")
    cohort = qualification.get("cohort")
    require(isinstance(selection, dict) and isinstance(cohort, list) and len(cohort) == 3, "Qualification cohort shape differs")
    require(selection.get("partition") == "TRAIN" and selection.get("count") == 3 and isinstance(selection.get("seed"), str), "Qualification selection differs")
    train_by_id = {row["opaque_story_id"]: row["story_text"] for row in train}
    selected = sorted(
        ((digest((selection["seed"] + "\0" + story_id).encode("utf-8")), story_id) for story_id in train_by_id),
        key=lambda item: (item[0], item[1]),
    )[:3]
    require(len(selected) == 3, "Public inputs do not contain the qualification cohort")
    sources = []
    for expected, (selection_hash, story_id) in zip(cohort, selected, strict=True):
        require(isinstance(expected, dict) and expected.get("opaque_story_id") == story_id, "Qualification selection order differs")
        text = train_by_id[story_id]
        encoded = text.encode("utf-8")
        require(expected.get("selection_sha256") == selection_hash and expected.get("story_text_sha256") == digest(encoded), "Qualification story commitment differs")
        sources.append({"opaque_story_id": story_id, "story_text": text, "raw": encoded, "selection_sha256": selection_hash})
    return sources


def _runtime_identity(runtime: Any, protocol: Mapping[str, Any]) -> dict[str, Any]:
    runtime.verify()
    bindings = protocol.get("runtime_bindings")
    require(isinstance(bindings, dict), "Protocol runtime bindings differ")
    checked: dict[str, str] = {}
    for relative, expected in bindings.items():
        require(isinstance(relative, str) and isinstance(expected, str), "Protocol runtime binding shape differs")
        raw = (REPOSITORY / relative).read_bytes()
        require(digest(raw) == expected, f"Runtime hash drift: {relative}")
        checked[relative] = expected
    require(len(runtime.questions) == 178, "Canonical question count differs")
    question_ids = [item["question"]["id"] for item in runtime.questions]
    require(len(question_ids) == len(set(question_ids)) == 178, "Canonical question identities differ")
    return {
        "runtime_bindings": checked,
        "registry_sha256": checked["registry/all_modules.json"],
        "compiled_bundle_sha256": digest(runtime.runner._json_bytes(runtime.compiled)),
        "question_payload_sha256": digest(runtime.runner._json_bytes(runtime.runner._question_payload(runtime.questions))),
        "question_ids": question_ids,
    }


def build_plan(public_inputs_raw: bytes, runtime: Any) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build the complete 18-pass/261-request plan without contacting a provider."""
    qualification_raw = _read_exact(QUALIFICATION_PATH, QUALIFICATION_SHA256, "Qualification")
    native_admission_raw = _read_exact(NATIVE_ADMISSION_PATH, NATIVE_ADMISSION_SHA256, "Native admission")
    protocol_raw = _read_exact(PROTOCOL_PATH, PROTOCOL_SHA256, "Analysis protocol")
    qualification = _load_json(qualification_raw, "Qualification")
    protocol = _load_json(protocol_raw, "Protocol")
    require(qualification.get("public_inputs_sha256") == PUBLIC_INPUTS_SHA256, "Qualification public-input commitment differs")
    require(protocol.get("execution", {}).get("qualification_protocol_sha256") == digest(qualification_raw), "Qualification commitment differs")
    sources = _load_inputs(public_inputs_raw, qualification)
    identity = _runtime_identity(runtime, protocol)
    schema = runtime.runner._response_schema()
    schema_raw = runtime.runner._json_bytes(schema)
    binary_raw = (REPOSITORY / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes()
    binary = binary_raw.decode("utf-8-sig").strip()
    require(digest(binary_raw) == protocol["runtime_bindings"]["prompts/judge/BINARY_EVALUATION_PROMPT.md"], "Binary prompt hash drift")
    artifacts: dict[str, bytes] = {"response.schema.json": schema_raw}
    passes: list[dict[str, Any]] = []
    all_requests: list[dict[str, Any]] = []
    ordinal = 0
    for batch_size in (8, 32):
        for repetition in range(1, 4):
            for source in sources:
                pass_id = f"size-{batch_size:04d}/repetition-{repetition:02d}/{source['opaque_story_id']}"
                requests = []
                for batch_number, start in enumerate(range(0, 178, batch_size), start=1):
                    ordinal += 1
                    chunk = runtime.questions[start:start + batch_size]
                    question_ids = [item["question"]["id"] for item in chunk]
                    prompt = runtime.runner._render_prompt(
                        binary_prompt=binary,
                        artifact={"name": f"{source['opaque_story_id']}.txt", "text": source["story_text"]},
                        contexts=[], bundle_id="prose.short_story", artifact_id=source["opaque_story_id"],
                        questions=chunk, provider="grok", model="grok-4.6",
                    ).encode("utf-8")
                    sol_prompt = runtime.runner._render_prompt(
                        binary_prompt=binary,
                        artifact={"name": f"{source['opaque_story_id']}.txt", "text": source["story_text"]},
                        contexts=[], bundle_id="prose.short_story", artifact_id=source["opaque_story_id"],
                        questions=chunk, provider="codex", model="gpt-5.6-sol",
                    ).encode("utf-8")
                    require(prompt == sol_prompt, "Sol prompt rendering differs from Grok")
                    prompt_path = f"prompts/request-{ordinal:04d}.txt"
                    artifacts[prompt_path] = prompt
                    requests.append({
                        "ordinal": ordinal, "pass_id": pass_id, "batch_number": batch_number,
                        "question_ids": question_ids, "prompt_path": prompt_path,
                        "prompt_sha256": digest(prompt), "prompt_bytes": len(prompt),
                        "schema_path": "response.schema.json", "schema_sha256": digest(schema_raw), "schema_bytes": len(schema_raw),
                    })
                passes.append({
                    "pass_id": pass_id, "batch_size": batch_size, "repetition": repetition,
                    "opaque_story_id": source["opaque_story_id"], "input_path": f"inputs/{source['opaque_story_id']}.txt",
                    "source_sha256": digest(source["raw"]), "source_bytes": len(source["raw"]),
                    "run_path": f"runs/{pass_id}",
                })
                all_requests.extend(requests)
    require(len(passes) == 18 and ordinal == 261, "Qualification plan geometry differs")
    for source in sources:
        artifacts[f"inputs/{source['opaque_story_id']}.txt"] = source["raw"]
    plan = {
        "schema_version": 1,
        "evidence_class": "provider_free_dryad_hbq_qualification_plan",
        "execution_authority": False,
        "provider_calls": 0,
        "public_inputs_sha256": digest(public_inputs_raw),
        "qualification": {"path": QUALIFICATION_PATH.relative_to(REPOSITORY).as_posix(), "sha256": digest(qualification_raw)},
        "protocol": {"path": PROTOCOL_PATH.relative_to(REPOSITORY).as_posix(), "sha256": digest(protocol_raw)},
        "native_admission": {"path": NATIVE_ADMISSION_PATH.relative_to(REPOSITORY).as_posix(), "sha256": digest(native_admission_raw)},
        "source": {"path": Path(__file__).resolve().relative_to(REPOSITORY).as_posix(), "sha256": digest(Path(__file__).read_bytes())},
        "runtime": identity,
        "response_schema": {"path": "response.schema.json", "sha256": digest(schema_raw), "bytes": len(schema_raw)},
        "counts": {"complete_passes": 18, "logical_requests": 261},
        "schedule": {"batch_sizes": [8, 32], "repetitions": [1, 2, 3], "cohort_order": [source["opaque_story_id"] for source in sources]},
        "passes": passes,
        "requests": all_requests,
    }
    artifacts["plan.json"] = runtime.runner._json_bytes(plan)
    runtime.verify()
    require(QUALIFICATION_PATH.read_bytes() == qualification_raw and PROTOCOL_PATH.read_bytes() == protocol_raw, "Qualification inputs changed during plan build")
    return plan, artifacts


def _generator_identity(commit: str | None = None) -> dict[str, Any]:
    files = (Path(__file__).resolve(), QUALIFICATION_PATH, PROTOCOL_PATH, NATIVE_ADMISSION_PATH)
    captured = {path: path.read_bytes() for path in files}
    if commit is None:
        result = subprocess.run(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], capture_output=True, check=False)
        commit = result.stdout.decode("ascii", errors="strict").strip() if not result.returncode else ""
    require(re.fullmatch(r"[0-9a-f]{40}", commit or "") is not None, "Invalid recorded generator commit")
    for path, raw in captured.items():
        relative = path.relative_to(REPOSITORY).as_posix()
        result = subprocess.run(["git", "-C", str(REPOSITORY), "show", f"{commit}:{relative}"], capture_output=True, check=False)
        require(not result.returncode and result.stdout == raw, "Preparation requires generator, qualification, protocol, and native admission committed byte-exactly at HEAD")
    require(all(path.read_bytes() == raw for path, raw in captured.items()), "Generator inputs changed during identity verification")
    return {"evidence_class": "committed_source", "git_commit": commit, "files": {path.relative_to(REPOSITORY).as_posix(): digest(raw) for path, raw in captured.items()}}


def _external_output(public_inputs_path: Path, output_root: Path, *, fresh: bool = True) -> Path:
    source = _plain(public_inputs_path)
    require(source.is_file(), "Public inputs path is not a file")
    destination = _plain(output_root)
    for protected in (REPOSITORY, ROOT, public_inputs_path.parent):
        checked = _plain(protected)
        require(not destination.is_relative_to(checked) and not checked.is_relative_to(destination), "Output must be disjoint from repository and public-input source directories")
    if fresh:
        require(not destination.exists(), "Output directory must be fresh")
    return destination


def prepare(public_inputs_path: Path, output_root: Path) -> dict[str, str]:
    """Write the immutable plan package into one fresh external directory."""
    public_inputs_path = _plain(public_inputs_path)
    output_root = _external_output(public_inputs_path, output_root)
    generator = _generator_identity()
    runtime = _load_runtime()
    public_inputs_raw = public_inputs_path.read_bytes()
    plan, artifacts = build_plan(public_inputs_raw, runtime)
    plan = {**plan, "generator": generator}
    artifacts = {**artifacts, "plan.json": runtime.runner._json_bytes(plan)}
    require(_generator_identity(generator["git_commit"]) == generator, "Generator changed during preparation")
    require(public_inputs_path.read_bytes() == public_inputs_raw, "Public inputs changed during preparation")
    _external_output(public_inputs_path, output_root)
    output_root.mkdir(parents=True, exist_ok=False)
    for relative, raw in sorted(artifacts.items()):
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    return {relative: digest(raw) for relative, raw in sorted(artifacts.items())}


def verify(public_inputs_path: Path, output_root: Path) -> dict[str, str]:
    """Verify inventory, committed identity, and every regenerated plan artifact."""
    public_inputs_path, output_root = _plain(public_inputs_path), _external_output(public_inputs_path, output_root, fresh=False)
    plan_path = _plain(output_root / "plan.json")
    try:
        recorded = _load_json(plan_path.read_bytes(), "Plan")
        commit = recorded["generator"]["git_commit"]
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Plan provenance is malformed") from error
    require(re.fullmatch(r"[0-9a-f]{40}", commit or "") is not None, "Plan generator commit is invalid")
    generator = _generator_identity(commit)
    require(recorded.get("generator") == generator, "Recorded generator identity differs")
    runtime = _load_runtime()
    public_inputs_raw = public_inputs_path.read_bytes()
    expected_plan, artifacts = build_plan(public_inputs_raw, runtime)
    expected_plan = {**expected_plan, "generator": generator}
    artifacts["plan.json"] = runtime.runner._json_bytes(expected_plan)
    paths = list(output_root.rglob("*"))
    for path in paths:
        _plain(path)
        require(path.is_file() or path.is_dir(), "Plan contains a special file")
    actual = {path.relative_to(output_root).as_posix(): path for path in paths if path.is_file()}
    require(set(actual) == set(artifacts), "Plan artifact inventory drift")
    allowed_directories = {parent.as_posix() for relative in artifacts for parent in Path(relative).parents if parent != Path(".")}
    actual_directories = {path.relative_to(output_root).as_posix() for path in paths if path.is_dir()}
    require(actual_directories == allowed_directories, "Plan directory inventory drift")
    for relative, raw in artifacts.items():
        require(actual[relative].read_bytes() == raw, f"Plan artifact byte drift: {relative}")
    require(not (output_root / "runs").exists(), "Prepared plan must not create run directories")
    require(_generator_identity(commit) == generator, "Generator changed during verification")
    require(public_inputs_path.read_bytes() == public_inputs_raw, "Public inputs changed during verification")
    return {relative: digest(raw) for relative, raw in sorted(artifacts.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free Dryad full-HBQ qualification-plan preparation and verification.")
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
