"""Provider-free S1 successor with four carriers repeated in twelve opaque slots."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v3"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V2_ROOT = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2"
V2_EXECUTION_ROOT = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v2"
V2_BINDINGS = {
    "study_sha256": "a6e209d4ddf4e6626876e2f102476d7c6ce9fcb14bb229b7af48e6cb43fcdcc8",
    "study_contract_sha256": "1edff0402ade56aea742c3c5a9dcc99423d9b490f37d9c9ad5ae50d575bb779c",
    "public_corpus_sha256": "1feb7dd0a392b2fa6e97936cbd3e492e5fc3e886010e63e5f117f8a19031567f",
    "predecessor_bindings_sha256": "0243d54f2d10bdd1c25bc9124bf364f4aa25ace8d99423f3c2220ae277801e1c",
    "run_sha256": "98ff20cef31266984bd63091ac76cb7250393abe50185b52f1b79404395d2fe0",
}
LEAF_ID = "form.poetry.free_verse.repetition"
BUNDLE_ID = "poetry_free_verse_repetition_singleton_v2"
WORK_ROOT: Path | None = None

sys.path.insert(0, str(REPOSITORY / "src"))
from hbqrs import core, runner  # noqa: E402
from hbqrs.weights import materialize_weight_profile  # noqa: E402


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def write_once(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Write-once artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Module is unavailable: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _v2_execution() -> Any:
    for filename, digest in V2_BINDINGS.items():
        names = {
            "study_sha256": "study.py", "study_contract_sha256": "study-contract.json",
            "public_corpus_sha256": "public-synthetic-corpus.json",
            "predecessor_bindings_sha256": "predecessor-bindings.json", "run_sha256": "run.py",
        }
        if sha(V2_EXECUTION_ROOT / names[filename]) != digest:
            raise ValueError("Execution-v2 public binding drifted")
    return _module("s1_v2_execution_v3_predecessor", V2_EXECUTION_ROOT / "study.py")


def _base_v2() -> Any:
    return _v2_execution()._v2()


def corpus() -> list[dict[str, str]]:
    cases = load(ROOT / "public-synthetic-corpus.json").get("cases")
    if not isinstance(cases, list) or len(cases) != 4 or not all(isinstance(row, Mapping) and set(row) == {"case_id", "text"} and isinstance(row["case_id"], str) and isinstance(row["text"], str) for row in cases):
        raise ValueError("Four-carrier corpus is invalid")
    result = [{"case_id": str(row["case_id"]), "text": str(row["text"])} for row in cases]
    if len({row["case_id"] for row in result}) != 4 or len({hashlib.sha256(row["text"].encode("utf-8")).hexdigest() for row in result}) != 4:
        raise ValueError("Carrier identities or texts are not distinct")
    return result


def slots() -> list[dict[str, str]]:
    plan = (
        ("u-8c13", "s1v-6a28", 2), ("u-5af1", "s1v-c834", 1), ("u-d462", "s1v-b5f1", 3),
        ("u-190e", "s1v-73ac", 2), ("u-a7d9", "s1v-6a28", 1), ("u-63c4", "s1v-c834", 3),
        ("u-f08b", "s1v-b5f1", 1), ("u-2e76", "s1v-73ac", 3), ("u-c951", "s1v-6a28", 3),
        ("u-71bd", "s1v-c834", 2), ("u-4f2a", "s1v-b5f1", 2), ("u-9e35", "s1v-73ac", 1),
    )
    if len(plan) != 12 or len({slot for slot, _, _ in plan}) != 12 or {(case, repeat) for _, case, repeat in plan} != {(row["case_id"], repeat) for row in corpus() for repeat in (1, 2, 3)}:
        raise ValueError("Fresh repeated schedule drifted")
    return [{"slot_id": slot, "case_id": case, "repeat": repeat} for slot, case, repeat in plan]


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", text.casefold()))


def _family(text: str) -> str:
    lines = [line.strip().casefold() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)
    if "[" in text and "stanza" in joined:
        return "bracketed_future_stanza_direction"
    if "margin direction" in joined:
        return "cross_page_margin_direction"
    if "planned winter sections" in joined:
        return "future_section_closure_direction"
    if "northing" in joined and "easting" in joined:
        return "coordinate_restatement"
    if "wire length" in joined and "ruler" in joined:
        return "measurement_restatement"
    if "coordinates for" in joined and "=" in joined:
        return "equation_coordinate_restatement"
    if joined.count("light") >= 3:
        return "endword_polysemy_light"
    if joined.count("home") >= 3:
        return "endword_polysemy_home"
    if joined.count("wake") >= 3:
        return "endword_polysemy_wake"
    if len(lines) == 1 and lines[0].startswith("rain darkens an abandoned glove beside"):
        return "nonrecurrent_compound_observation"
    if len(lines) == 2 and lines[0].startswith("beside nettles"):
        return "nonrecurrent_lyric_couplet"
    if len(lines) == 1 and lines[0].startswith("juniper smoke"):
        return "nonrecurrent_lyric_sentence"
    if len(lines) == 3 and all("." in line for line in lines):
        return "nonrecurrent_lyric_triad"
    return "other"


def _ngrams(text: str, width: int = 4) -> set[tuple[str, ...]]:
    tokens = _tokens(text)
    return {tokens[index:index + width] for index in range(max(0, len(tokens) - width + 1))}


def _prior_texts() -> list[str]:
    v2 = _base_v2()
    v1 = v2._v1()
    execution = load(V2_EXECUTION_ROOT / "public-synthetic-corpus.json").get("cases")
    if not isinstance(execution, list):
        raise ValueError("Execution-v2 public corpus is invalid")
    rows = [*v1.corpus(), *v2.corpus(), *execution]
    if not all(isinstance(row, Mapping) and isinstance(row.get("text"), str) for row in rows):
        raise ValueError("Prior public corpus contains invalid text")
    return [str(row["text"]) for row in rows]


def motif_template_audit() -> dict[str, Any]:
    prior = _prior_texts()
    current = corpus()
    prior_families = {_family(text) for text in prior}
    prior_ngrams = set().union(*(_ngrams(text) for text in prior))
    current_families = [_family(row["text"]) for row in current]
    if len(current_families) != len(set(current_families)):
        raise ValueError("Fresh carriers reuse a structural family")
    if any(family in prior_families for family in current_families):
        raise ValueError("Fresh carriers reuse a predecessor structural family")
    if any(_ngrams(row["text"]) & prior_ngrams for row in current):
        raise ValueError("Fresh carriers reuse a predecessor normalized motif")
    if any(re.search(r"\b(refrain|single|only|occurrence)\b", row["text"], flags=re.IGNORECASE) for row in current):
        raise ValueError("Carrier prose contains answer-key gloss language")
    return {"algorithm": "s1_structural_family_and_normalized_ngram_v1", "prior_texts": len(prior), "current_texts": len(current), "families": len(current_families), "status": "disjoint"}


def contract() -> dict[str, Any]:
    return load(ROOT / "study-contract.json")


def expected_contract() -> dict[str, Any]:
    freshness = {key: False for key in ("prior_fixture_identity_reuse", "prior_carrier_prose_reuse", "prior_motif_reuse", "prior_template_reuse", "prior_distinctive_phrase_reuse", "prior_answer_key_language_reuse", "prior_logical_sample_reuse")}
    return {"format_version": 1, "study_id": STUDY_ID, "status": "provider_free_four_carrier_repeatability_successor", "source_checkout": {"commit": SOURCE_HEAD, "tree": SOURCE_TREE}, "candidate_semantics": "v2_wording_unchanged", "predecessor": {"package": V2_EXECUTION_ROOT.name, "classification": "provider_free_no_go_template_reuse", "bindings": V2_BINDINGS}, "freshness": freshness, "geometry": {"independent_carriers": 4, "repeats_per_carrier": 3, "repeated_logical_samples": True, "opaque_slots": 12}, "motif_audit": {"commitment_sha256": sha(ROOT / "motif-audit-commitment.json"), "public_inventory": "omitted"}, "execution": {"provider_calls": 0, "claim": "unavailable_until_independent_semantic_review", "live_execution": "unavailable", "one_attempt": True, "retry_or_resume": "forbidden", "normalization_or_settlement_repair": "forbidden"}, "promotion": "none"}


def set_work_root(path: str | Path) -> Path:
    root = Path(path).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("External work root is required")
    global WORK_ROOT
    WORK_ROOT = root
    return root


def dry_root() -> Path:
    if WORK_ROOT is None:
        raise ValueError("An explicit external work root is required")
    return WORK_ROOT / "execution-v3-dry"


def _head() -> tuple[str, str]:
    values = []
    for value in ("HEAD", f"{SOURCE_HEAD}^{{tree}}"):
        result = subprocess.run(["git", "rev-parse", value], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
        if result.returncode:
            raise ValueError("CWR source binding is unavailable")
        values.append(result.stdout.strip())
    return values[0], values[1]


def validate_package() -> dict[str, Any]:
    if contract() != expected_contract():
        raise ValueError("Execution-v3 contract drifted")
    if load(ROOT / "predecessor-bindings.json") != V2_BINDINGS:
        raise ValueError("Execution-v2 binding drifted")
    if _head() != (SOURCE_HEAD, SOURCE_TREE):
        raise ValueError("Exact CWR source binding drifted")
    base = _base_v2()
    if hashlib.sha256(base.canonical_json(base.candidate_leaf())).hexdigest() != "b8b874772e62965042bc75c8171a933bc3d85e3d785da911019d52cbfd268219":
        raise ValueError("Candidate wording drifted")
    audit = motif_template_audit()
    previous_slots = [*base._v1().slots(), *base.slots(), *_v2_execution().slots()]
    if {row["case_id"] for row in slots()} & {str(row["case_id"]) for row in previous_slots} or {row["slot_id"] for row in slots()} & {str(row["slot_id"]) for row in previous_slots}:
        raise ValueError("Prior carrier or logical sample identity was reused")
    return {"study_id": STUDY_ID, "provider_calls": 0, "slots": 12, "motif_audit": audit["status"], "promotion": "none"}


def _render(slot: Mapping[str, Any], root: Path) -> str:
    return _v2_execution()._render(slot, root)


def frozen_command(slot: Mapping[str, Any], root: Path) -> list[str]:
    return _v2_execution().frozen_command(slot, root)


def _snapshot(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha(path) for path in sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.as_posix())}


def dry_freeze() -> dict[str, Any]:
    audit = motif_template_audit(); validate_package(); root = dry_root()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Fresh dry root already exists")
    root.mkdir(parents=True, exist_ok=False)
    base = _base_v2(); inherited = _v2_execution()
    base.overlay(root)
    base.write_once(root / "catalog" / "candidate-registry.json", base.canonical_json(base.candidate_registry()))
    base.write_once(root / "catalog" / "bundles.json", base.canonical_json(base.bundle()))
    by_case = {row["case_id"]: row for row in corpus()}
    prompts: dict[str, dict[str, Any]] = {}
    for slot in slots():
        slot_id = str(slot["slot_id"])
        base.write_once(root / "inputs" / f"{slot_id}.txt", by_case[str(slot["case_id"])]["text"].encode("utf-8"))
        task = base.task(slot)
        base.write_once(root / "contracts" / f"{slot_id}.json", base.canonical_json(task))
        base.write_once(root / "overrides" / f"{slot_id}.json", base.canonical_json(base.override(slot, task)))
        raw = _render(slot, root).encode("utf-8")
        frozen = root / "frozen-prompts" / f"{slot_id}.prompt.txt"
        write_once(frozen, raw)
        prompts[slot_id] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "crlf_pairs": raw.count(b"\r\n")}
    commands = {str(slot["slot_id"]): frozen_command(slot, root) for slot in slots()}
    private_audit = {"format_version": 1, "study_id": STUDY_ID, "algorithm": audit["algorithm"], "prior_families": sorted({_family(text) for text in _prior_texts()}), "current_families": {row["case_id"]: _family(row["text"]) for row in corpus()}, "status": audit["status"]}
    write_once(root / "motif-template-audit.v1.json", canonical(private_audit))
    receipt = {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "snapshot_files": _snapshot(root), "derivation": "production_renderer_raw_utf8_bytes"}
    write_once(root / "snapshot-receipt.v1.json", canonical(receipt))
    manifest = {"format_version": 1, "study_id": STUDY_ID, "provider_calls": 0, "slots": [str(slot["slot_id"]) for slot in slots()], "prompts": prompts, "commands": commands, "snapshot_receipt_sha256": sha(root / "snapshot-receipt.v1.json"), "motif_audit_sha256": sha(root / "motif-template-audit.v1.json"), "claim": "absent", "live_execution": "unavailable", "promotion": "none"}
    write_once(root / "dry-manifest.v1.json", canonical(manifest))
    return {"provider_calls": 0, "dry_manifest_sha256": sha(root / "dry-manifest.v1.json"), "slots": 12, "motif_audit": audit["status"], "promotion": "none"}


def validate_checkpoint_prompt(slot_id: str, gzip_path: str | Path) -> dict[str, Any]:
    expected = dry_root() / "frozen-prompts" / f"{slot_id}.prompt.txt"
    if not expected.is_file():
        raise ValueError("Frozen prompt is unavailable")
    try:
        observed = gzip.decompress(Path(gzip_path).read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError("Checkpoint prompt gzip is invalid") from exc
    if observed != expected.read_bytes():
        raise ValueError("Checkpoint raw prompt bytes differ from the frozen production render")
    return {"slot_id": slot_id, "bytes": len(observed), "sha256": hashlib.sha256(observed).hexdigest()}


def execution_unavailable() -> None:
    raise ValueError("No claim or provider execution is available in this provider-free successor")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--work-root", type=Path)
    args = parser.parse_args()
    if args.validate:
        result = validate_package()
    else:
        if args.work_root is None:
            raise ValueError("--dry-run requires an explicit external --work-root")
        set_work_root(args.work_root)
        result = dry_freeze()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
