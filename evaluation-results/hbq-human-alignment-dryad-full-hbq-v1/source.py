"""Provider-free preparation, verification, and prompt preview for Dryad full-HBQ work."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import types
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[2]
CONTRACT_PATH = Path(__file__).resolve().with_name("study-contract.json")
CONTRACT_SHA256 = "e0a46597c39737860c06a7204baa094382292ee63e38b8318e5db82d2f8ed9ff"
DRYAD_SOURCE = REPOSITORY / "evaluation-results" / "hbq-human-alignment-dryad-pilot-v1" / "source.py"
DRYAD_SOURCE_SHA256 = "ebe3792f8f8255d18528e55a7a5ae5749a1a0f811e841181fbffa45562024d63"
RUNTIME_FILES = (
    "src/hbqrs/core.py",
    "src/hbqrs/runner.py",
    "src/hbqrs/paths.py",
    "src/hbqrs/weights.py",
    "registry/all_modules.json",
    "bundles/all_bundles.json",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_contract() -> dict[str, Any]:
    raw = CONTRACT_PATH.read_bytes()
    if sha256_bytes(raw) != CONTRACT_SHA256:
        raise ValueError("Study contract hash drift")
    contract = json.loads(raw)
    if CONTRACT_PATH.read_bytes() != raw:
        raise ValueError("Study contract changed during load")
    if contract.get("status") != "provider_free_packet_only" or contract.get("execution", {}).get("execution_authority") is not False:
        raise ValueError("Study contract execution boundary drift")
    return contract


def verify_runtime(contract: dict[str, Any]) -> None:
    bindings = contract["runtime_bindings"]
    if set(bindings) != set(RUNTIME_FILES):
        raise ValueError("Runtime binding inventory drift")
    for relative, expected in bindings.items():
        if sha256_file(REPOSITORY / relative) != expected:
            raise ValueError(f"Runtime hash drift: {relative}")


def load_dryad_source() -> Any:
    raw = DRYAD_SOURCE.read_bytes()
    if sha256_bytes(raw) != DRYAD_SOURCE_SHA256:
        raise ValueError("Pinned Dryad public-loader source drift")
    spec = importlib.util.spec_from_file_location("dryad_pilot_source", DRYAD_SOURCE)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot import pinned Dryad public loader")
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(DRYAD_SOURCE), "exec"), module.__dict__)
    if DRYAD_SOURCE.read_bytes() != raw:
        raise ValueError("Dryad public-loader source changed during import")
    return module


def load_hbq() -> tuple[Any, Any]:
    contract = load_contract()
    namespace = "_dryad_verified_" + uuid.uuid4().hex
    package = types.ModuleType(namespace)
    package.__path__ = []  # Only explicitly verified modules may resolve here.
    loaded = {}
    sys.modules[namespace] = package
    try:
        for name in ("core", "paths", "weights", "runner"):
            relative = f"src/hbqrs/{name}.py"
            path = REPOSITORY / relative
            raw = path.read_bytes()
            if sha256_bytes(raw) != contract["runtime_bindings"][relative]:
                raise ValueError(f"Runtime hash drift: {relative}")
            module = types.ModuleType(f"{namespace}.{name}")
            module.__file__ = str(path)
            module.__package__ = namespace
            sys.modules[module.__name__] = module
            setattr(package, name, module)
            exec(compile(raw, str(path), "exec"), module.__dict__)
            if path.read_bytes() != raw:
                raise ValueError(f"Runtime changed during import: {relative}")
            loaded[name] = module
        verify_runtime(contract)
        return loaded["core"], loaded["runner"]
    finally:
        for name in ("core", "paths", "weights", "runner"):
            sys.modules.pop(f"{namespace}.{name}", None)
        sys.modules.pop(namespace, None)


def compiled_question_bank(contract: dict[str, Any]) -> dict[str, Any]:
    verify_runtime(contract)
    core, _ = load_hbq()
    modules = core.load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundles = core.load_bundles(REPOSITORY / "bundles" / "all_bundles.json")
    compiled = core.compile_bundle(modules, core.resolve_bundle(bundles, contract["rubric"]["bundle_id"]))
    if compiled.get("task_contract") is not None:
        raise ValueError("Unexpected task contract or dynamic goal")
    questions = core.compiled_questions(compiled)
    question_ids = [str(item["question"]["id"]) for item in questions]
    counts = Counter(str(item["role"]) for item in questions)
    role_counts = {role: counts[role] for role in ("domain", "penalty", "supplemental", "hard_gate")}
    expected = contract["rubric"]
    if len(questions) != expected["question_count"] or role_counts != expected["role_counts"]:
        raise ValueError("Complete question-bank cardinality drift")
    if sha256_bytes(("\n".join(question_ids) + "\n").encode("utf-8")) != expected["ordered_question_ids_sha256"]:
        raise ValueError("Ordered question-ID drift")
    verify_runtime(contract)
    return {"bundle_id": compiled["bundle_id"], "questions": questions, "ordered_question_ids": question_ids}


def public_story_index(freeze_root: Path, contract: dict[str, Any]) -> list[dict[str, str]]:
    dryad = load_dryad_source()
    public = dryad.load_public_inputs(freeze_root, contract["source_freeze"]["expected_provenance_sha256"])
    expected_counts = contract["source_freeze"]["open_partitions"]
    if set(public) != set(expected_counts):
        raise ValueError("Dryad public partition drift")
    rows: list[dict[str, str]] = []
    for partition in ("TRAIN", "DEV"):
        stories = public[partition]
        if len(stories) != expected_counts[partition]:
            raise ValueError("Dryad public story count drift")
        for story in stories:
            if set(story) != {"opaque_story_id", "story_text"}:
                raise ValueError("Dryad public-input schema drift")
            rows.append({"opaque_story_id": str(story["opaque_story_id"]), "partition": partition, "story_text_sha256": sha256_bytes(str(story["story_text"]).encode("utf-8"))})
    if len(rows) != 236 or len({row["opaque_story_id"] for row in rows}) != 236 or len({row["story_text_sha256"] for row in rows}) != 236:
        raise ValueError("Dryad public story identity drift")
    return sorted(rows, key=lambda row: row["opaque_story_id"])


def _generator_identity(commit: str | None = None) -> dict[str, str]:
    if commit is None:
        commit = subprocess.run(["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], capture_output=True, check=True).stdout.decode("ascii").strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("Invalid generator commit")
    source_path = Path(__file__).resolve()
    captured = {path: path.read_bytes() for path in (source_path, CONTRACT_PATH, DRYAD_SOURCE)}
    for path, raw in captured.items():
        relative = path.relative_to(REPOSITORY).as_posix()
        blob = subprocess.run(["git", "-C", str(REPOSITORY), "show", f"{commit}:{relative}"], capture_output=True, check=False)
        if blob.returncode or blob.stdout != raw:
            raise ValueError("Generator, contract, and parent loader must match the recorded Git commit")
    if any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("Generator identity files changed during verification")
    return {"evidence_class": "committed_source", "git_commit": commit,
            "source_path": Path(__file__).resolve().relative_to(REPOSITORY).as_posix(),
            "source_sha256": sha256_bytes(captured[source_path]),
            "contract_path": CONTRACT_PATH.relative_to(REPOSITORY).as_posix(), "contract_sha256": sha256_bytes(captured[CONTRACT_PATH])}


def expected_artifacts(freeze_root: Path, *, generator_commit: str | None = None) -> dict[str, bytes]:
    contract = load_contract()
    bank = compiled_question_bank(contract)
    stories = public_story_index(freeze_root, contract)
    question_bytes = canonical_json_bytes(bank)
    story_bytes = canonical_json_bytes({"stories": stories})
    provenance = {
        "schema_version": 1,
        "evidence_class": "provider_free_full_hbq_packet",
        "generator": _generator_identity(generator_commit),
        "source_freeze": {"provenance_sha256": contract["source_freeze"]["expected_provenance_sha256"],
                          "public_story_count": len(stories), "loader_path": DRYAD_SOURCE.relative_to(REPOSITORY).as_posix(),
                          "loader_sha256": DRYAD_SOURCE_SHA256},
        "runtime_bindings": contract["runtime_bindings"],
        "rubric": {
            "bundle_id": contract["rubric"]["bundle_id"],
            "question_count": len(bank["questions"]),
            "ordered_question_ids_sha256": contract["rubric"]["ordered_question_ids_sha256"],
        },
        "artifacts": {
            "question-bank.json": {"sha256": sha256_bytes(question_bytes), "bytes": len(question_bytes)},
            "story-index.json": {"sha256": sha256_bytes(story_bytes), "bytes": len(story_bytes)},
        },
        "execution": contract["execution"],
        "non_claims": contract["non_claims"],
    }
    return {"question-bank.json": question_bytes, "story-index.json": story_bytes, "provenance.json": canonical_json_bytes(provenance)}


def prepare(freeze_root: Path, output_root: Path) -> dict[str, str]:
    if output_root.exists():
        raise FileExistsError("Packet output root already exists; refusing overwrite")
    artifacts = expected_artifacts(freeze_root)
    output_root.mkdir(parents=True)
    for name, value in artifacts.items():
        with (output_root / name).open("xb") as stream:
            stream.write(value)
    return {name: sha256_bytes(value) for name, value in artifacts.items()}


def verify(freeze_root: Path, output_root: Path) -> dict[str, str]:
    provenance = json.loads((output_root / "provenance.json").read_bytes())
    expected = expected_artifacts(freeze_root, generator_commit=provenance["generator"]["git_commit"])
    if not output_root.is_dir() or {path.name for path in output_root.iterdir()} != set(expected):
        raise ValueError("Packet artifact inventory drift")
    actual: dict[str, str] = {}
    for name, value in expected.items():
        path = output_root / name
        if not path.is_file() or path.read_bytes() != value:
            raise ValueError(f"Packet artifact byte drift: {name}")
        actual[name] = sha256_bytes(value)
    return actual


def preview_story(freeze_root: Path, opaque_story_id: str) -> bytes:
    contract = load_contract()
    bank = compiled_question_bank(contract)
    dryad = load_dryad_source()
    public = dryad.load_public_inputs(freeze_root, contract["source_freeze"]["expected_provenance_sha256"])
    matches = [story for stories in public.values() for story in stories if story["opaque_story_id"] == opaque_story_id]
    if len(matches) != 1:
        raise ValueError("Unknown or non-public Dryad story ID")
    _, runner = load_hbq()
    binary = (REPOSITORY / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8")
    kwargs = {
        "binary_prompt": binary,
        "artifact": {"name": "Dryad short story", "text": matches[0]["story_text"]},
        "contexts": [],
        "bundle_id": contract["rubric"]["bundle_id"],
        "artifact_id": opaque_story_id,
        "questions": bank["questions"],
    }
    grok = runner._render_prompt(**kwargs, provider="grok", model="grok-4.6")
    sol = runner._render_prompt(**kwargs, provider="codex", model="gpt-5.6-sol")
    if grok.encode("utf-8") != sol.encode("utf-8"):
        raise ValueError("Grok and Sol preview bytes diverged")
    verify_runtime(contract)
    return grok.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free Dryad full-HBQ packet tools only; never dispatches a judge.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        command = subcommands.add_parser(name)
        command.add_argument("--freeze-root", type=Path, required=True)
        command.add_argument("--output-root", type=Path, required=True)
    preview = subcommands.add_parser("preview", help="Unbatched preview only; it is not execution authority.")
    preview.add_argument("--freeze-root", type=Path, required=True)
    preview.add_argument("--opaque-story-id", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.freeze_root, args.output_root), sort_keys=True))
    elif args.command == "verify":
        print(json.dumps(verify(args.freeze_root, args.output_root), sort_keys=True))
    else:
        sys.stdout.buffer.write(preview_story(args.freeze_root, args.opaque_story_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
