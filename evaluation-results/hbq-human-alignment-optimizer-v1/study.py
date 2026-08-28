"""Strict, provider-free contracts for the HANNA prompt-profile study."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import stat
import tempfile
import csv
from pathlib import Path
from typing import Any, Mapping

HERE = Path(os.path.abspath(__file__)).parent
CONTRACT_PATH = HERE / "study-contract.json"
OPTIMIZER_CONFIG_PATH = HERE / "optimizer-config.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID = re.compile(r"^candidate-[0-9a-f]{16,64}$")
CALL_ID = re.compile(r"^(?:call|item|run)-[0-9a-f]{16,64}$")
GROUP_ID = re.compile(r"^prompt-[0-9a-f]{16}$")
SPLIT_DESCRIPTOR = (
    "sha256_seeded_rank_bounded_subset_v1|{seed}:hanna_optimizer_split_v1:{prompt_group_id}|"
    "sha256_hex_then_prompt_group_id|lexicographic_include_when_feasible|"
    "train:24:48,development:7:13,confirmation:8:19"
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def checked_path(path: Path, *, must_exist: bool = False) -> Path:
    raw = os.fspath(path)
    if not isinstance(raw, str) or any(part == ".." for part in Path(raw).parts):
        raise ValueError("Optimizer path is not lexical")
    candidate = Path(os.path.abspath(raw))
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError("Optimizer path contains a symlink or reparse point")
    if must_exist and not candidate.exists():
        raise ValueError("Optimizer path does not exist")
    return candidate


def _contains(parent: Path, child: Path) -> bool:
    parent_text, child_text = os.path.normcase(os.fspath(parent)), os.path.normcase(os.fspath(child))
    try:
        return os.path.commonpath((parent_text, child_text)) == parent_text
    except ValueError:
        return False


def require_disjoint_paths(*paths: Path) -> tuple[Path, ...]:
    checked = tuple(checked_path(path) for path in paths)
    for index, first in enumerate(checked):
        if any(_contains(first, second) or _contains(second, first) for second in checked[index + 1:]):
            raise ValueError("Optimizer paths must be disjoint")
    return checked


def checked_package_path(path: Path) -> Path:
    candidate = checked_path(path, must_exist=True)
    if not _contains(checked_path(HERE, must_exist=True), candidate):
        raise ValueError("Optimizer package path escapes its package root")
    return candidate


def checked_output_path(path: Path) -> Path:
    candidate = checked_path(path)
    if _contains(checked_path(HERE, must_exist=True), candidate) or _contains(candidate, checked_path(HERE, must_exist=True)):
        raise ValueError("Optimizer output path overlaps its package root")
    return candidate


def _read_bytes_checked(path: Path) -> bytes:
    candidate = checked_path(path, must_exist=True)
    try:
        raw = candidate.read_bytes()
    except OSError as exc:
        raise ValueError(f"Optimizer path cannot be read: {candidate}") from exc
    checked_path(candidate, must_exist=True)
    return raw


def sha(path: Path) -> str:
    return hashlib.sha256(_read_bytes_checked(path)).hexdigest()


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def _opaque_id(value: Any, prefix: str | None = None) -> bool:
    return isinstance(value, str) and bool(OPAQUE_ID.fullmatch(value)) and (prefix is None or value.startswith(prefix + "-"))


def _exact(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"Optimizer {label} schema is invalid")
    return value


def finite(value: Any, *, low: float, high: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= float(value) <= high:
        raise ValueError(f"Optimizer {label} is invalid")


def read_json(path: Path) -> dict[str, Any]:
    try:
        def reject_constant(value: str) -> None:
            raise ValueError(f"non-finite JSON number: {value}")

        value = json.loads(_read_bytes_checked(path).decode("utf-8"), parse_constant=reject_constant)
    except ValueError as exc:
        if str(exc).startswith("Optimizer path"):
            raise
        raise ValueError(f"Invalid JSON: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _pinned_json(path: Path, expected_sha256: str, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = _read_bytes_checked(path)
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"HANNA optimizer {label} cannot be read") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256 or not isinstance(value, dict):
        raise ValueError(f"HANNA optimizer {label} hash or schema drifted")
    return value, digest


def load_optimizer_config(path: Path = OPTIMIZER_CONFIG_PATH) -> dict[str, Any]:
    value = read_json(checked_package_path(path))
    _exact(value, {"format_version", "study_id", "mode", "candidate_generator"}, "optimizer config")
    generator = _exact(value["candidate_generator"], {"optional_backends", "runtime_dependency", "remote_execution", "train_partition", "selection_partition", "confirmation_partition", "freeze_selected_candidate_before_confirmation", "metric_source"}, "optimizer candidate generator")
    if value["format_version"] != 1 or value["study_id"] != "hbq-human-alignment-optimizer-v1" or value["mode"] != "offline_development_only" or generator != {"optional_backends": ["dspy_miprov2", "optuna"], "runtime_dependency": False, "remote_execution": False, "train_partition": "train", "selection_partition": "development", "confirmation_partition": "confirmation", "freeze_selected_candidate_before_confirmation": True, "metric_source": "manifest_derived_local_metrics_only"}:
        raise ValueError("HANNA optimizer config drifted")
    return value


def _split_descriptor_sha256() -> str:
    return hashlib.sha256(SPLIT_DESCRIPTOR.encode("utf-8")).hexdigest()


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = read_json(checked_package_path(path))
    required = {
        "format_version", "study_id", "kind", "analysis_only", "provider_execution", "parents",
        "dataset", "eligible_universe", "split", "candidate_space", "selection_and_guard",
        "endpoints", "budgets", "optimizer_interfaces", "outputs", "interpretation_limits",
    }
    _exact(contract, required, "contract")
    if contract["format_version"] != 1 or contract["study_id"] != "hbq-human-alignment-optimizer-v1" or contract["kind"] != "development_only_prompt_profile_optimizer" or contract["analysis_only"] is not False or contract["provider_execution"] != "gated_one_cell_train_development_driver_without_promotable_receipts" or contract["outputs"] != ["public-summary.json", "manifest.json"]:
        raise ValueError("HANNA optimizer contract identity drifted")
    parent = _exact(contract["parents"], {"fresh88_primary"}, "parent")["fresh88_primary"]
    parent_keys = {"study_id", "frozen_successor_sha256", "freeze_receipt_sha256", "execution_contract_sha256", "execution_receipt_sha256", "runtime_source_manifest_sha256", "mapping_sets_sha256"}
    _exact(parent, parent_keys, "parent commitment")
    if parent["study_id"] != "hbq-human-alignment-v3-fresh88-analysis-v1" or not all(_is_hash(parent[key]) for key in parent_keys - {"study_id"}):
        raise ValueError("HANNA optimizer parent commitments are invalid")
    dataset = _exact(contract["dataset"], {"repository", "upstream_commit", "csv_name", "license_name", "csv_sha256", "license_sha256", "license"}, "dataset")
    if dataset["repository"] != "https://github.com/dig-team/hanna-benchmark-asg" or dataset["upstream_commit"] != "282f27536a5d05ad4ce14298abcd70c45668fed2" or dataset["csv_name"] != "hanna_stories_annotations.csv" or dataset["license_name"] != "LICENSE" or dataset["license"] != "MIT" or not _is_hash(dataset["csv_sha256"]) or not _is_hash(dataset["license_sha256"]):
        raise ValueError("HANNA optimizer dataset pins are invalid")
    universe = _exact(contract["eligible_universe"], {"source", "item_count", "item_ids", "group_count", "item_ids_sha256", "prompt_sha256s_sha256", "group_ids", "group_ids_sha256", "item_group_map_sha256"}, "eligible universe")
    source = _exact(universe["source"], {"authority_sha256", "authority_receipt_sha256", "frozen_successor_contract_sha256", "hanna_csv_sha256", "selector", "group_derivation"}, "eligible-universe source")
    if not all(_is_hash(source[key]) for key in ("authority_sha256", "authority_receipt_sha256", "frozen_successor_contract_sha256", "hanna_csv_sha256")) or source["authority_sha256"] != parent["frozen_successor_sha256"] or source["hanna_csv_sha256"] != dataset["csv_sha256"] or source["selector"] != "fresh_complement.item_ids where source_model != Human" or source["group_derivation"] != "prompt-{sha256(utf8(Prompt))[:16]}" or universe["item_count"] != 80 or not isinstance(universe["item_ids"], list) or len(universe["item_ids"]) != 80 or any(not isinstance(item, str) or not CALL_ID.fullmatch(item) for item in universe["item_ids"]) or universe["item_ids"] != sorted(set(universe["item_ids"])) or sha256(universe["item_ids"]) != universe["item_ids_sha256"] or universe["group_count"] != 39 or not all(_is_hash(universe[key]) for key in ("item_ids_sha256", "prompt_sha256s_sha256", "group_ids_sha256", "item_group_map_sha256")) or not isinstance(universe["group_ids"], list) or len(universe["group_ids"]) != 39 or any(not isinstance(group, str) or not GROUP_ID.fullmatch(group) for group in universe["group_ids"]) or universe["group_ids"] != sorted(set(universe["group_ids"])) or sha256(universe["group_ids"]) != universe["group_ids_sha256"]:
        raise ValueError("HANNA optimizer eligible universe is invalid")
    split = _exact(contract["split"], {"seed", "algorithm", "algorithm_sha256", "partitions"}, "split")
    if split["seed"] != 628801 or split["algorithm"] != "sha256_seeded_rank_bounded_subset_v1" or split["algorithm_sha256"] != _split_descriptor_sha256() or split["partitions"] != {"train": {"group_count": 24, "item_count": 48}, "development": {"group_count": 7, "item_count": 13}, "confirmation": {"group_count": 8, "item_count": 19}}:
        raise ValueError("HANNA optimizer split commitments are invalid")
    space = _exact(contract["candidate_space"], {"fixed_mapping", "fixed_dimension_weights", "controls", "candidate_count", "fixed_seed", "demonstrations", "baseline_control_profile_sha256"}, "candidate space")
    expected_controls = {
        "construct_framing": ["literary_quality", "human_reference_descriptive", "reader_effects_descriptive"],
        "scope_materiality": ["declared_scope_material", "localized_revision_note"],
        "missing_evidence_not_no": ["explicit", "implicit"],
        "human_reference_variant": ["six_dimension_direct", "overall_with_dimension_checks", "dimension_first_overall_last"],
    }
    if space["fixed_mapping"] != "Fresh88 v3 mapping_sets_sha256" or space["fixed_dimension_weights"] != {"Relevance": 1, "Coherence": 1, "Empathy": 1, "Surprise": 1, "Engagement": 1, "Complexity": 1} or space["controls"] != expected_controls or space["candidate_count"] != {"minimum": 6, "maximum": 8} or not isinstance(space["fixed_seed"], int) or isinstance(space["fixed_seed"], bool) or space["demonstrations"] != 0 or not _is_hash(space["baseline_control_profile_sha256"]):
        raise ValueError("HANNA optimizer candidate space drifted")
    guard = _exact(contract["selection_and_guard"], {"selector", "selector_rule", "grok_role", "forbidden"}, "selection")
    if guard != {"selector": "gpt-5.6-sol", "selector_rule": "Sol selects a candidate solely by the fixed development endpoint, then ordered tie-breakers.", "grok_role": "identical_input_screen_guard_only", "forbidden": ["average_with_sol", "sole_scope_selector", "sole_craft_selector", "sole_penalty_selector"]}:
        raise ValueError("HANNA optimizer model roles drifted")
    endpoints = _exact(contract["endpoints"], {"development", "confirmation"}, "endpoints")
    expected_endpoint = {
        "development": {"primary": "macro_spearman", "direction": "maximize", "tie_breakers": ["mean_absolute_error:ascending", "candidate_id:lexicographic"], "report": "Sol endpoint is selector; Grok is separately reported only."},
        "confirmation": {"primary": "macro_spearman", "direction": "maximize", "comparator": "future selected_candidate versus frozen_control on the eight untouched confirmation groups", "report": "Report Sol and Grok separately; do not pool providers."},
    }
    if endpoints != expected_endpoint:
        raise ValueError("HANNA optimizer endpoints drifted")
    budgets = _exact(contract["budgets"], {"development", "confirmation"}, "budgets")
    if budgets != {"development": {"candidate_count": 6, "train_item_count": 48, "development_item_count": 13, "providers": ["gpt-5.6-sol", "grok-4.6"], "candidate_train_calls": 576, "candidate_development_calls": 156, "maximum_provider_calls": 732}, "confirmation": {"candidate_and_control": 2, "confirmation_item_count": 19, "providers": ["gpt-5.6-sol", "grok-4.6"], "provider_calls": 76, "maximum_provider_calls": 76}}:
        raise ValueError("HANNA optimizer call geometry drifted")
    if contract["optimizer_interfaces"] != {"dspy_miprov2": {"optional": True, "development_only": True, "runtime_dependency": False}, "optuna": {"optional": True, "development_only": True, "runtime_dependency": False}} or contract["interpretation_limits"] != ["The gated executor may make one disclosed train/development provider call only after external acknowledgement, trusted zero-charge proof, and --allow-remote; it claims no alignment improvement.", "HANNA is human-reference context, not literary ground truth.", "A selected development candidate is not a production prompt or a confirmed result.", "The public projection is aggregate-only and must not contain story or prompt prose, per-item rows, raw model responses, session identifiers, local paths, or provider credentials."]:
        raise ValueError("HANNA optimizer policy drifted")
    return contract


CONTRACT = load_contract()
_ELIGIBLE_MAP_CACHE: dict[tuple[str, str], tuple[dict[str, str], ...]] = {}
UNIMPLEMENTED_BLOCKER = "HANNA selection and confirmation are unimplemented until exact per-run/provider manifest recomputation exists"


def derive_eligible_map(frozen_successor_path: Path, hanna_csv_path: Path) -> list[dict[str, str]]:
    """Recompute the opaque 80-item prompt-group map from the two pinned sources."""

    frozen_path = Path(frozen_successor_path)
    csv_path = Path(hanna_csv_path)
    frozen, frozen_sha256 = _pinned_json(
        frozen_path,
        CONTRACT["eligible_universe"]["source"]["frozen_successor_contract_sha256"],
        "frozen successor contract",
    )
    fresh = frozen.get("fresh_complement")
    selection = frozen.get("selection")
    if not isinstance(fresh, Mapping) or not isinstance(selection, Mapping):
        raise ValueError("HANNA optimizer frozen successor is malformed")
    fresh_ids = fresh.get("item_ids")
    if not isinstance(fresh_ids, list) or len(fresh_ids) != 88 or len(set(fresh_ids)) != 88 or any(not isinstance(value, str) for value in fresh_ids):
        raise ValueError("HANNA optimizer fresh-complement selection drifted")
    candidates: dict[str, list[Mapping[str, Any]]] = {}
    for partition in ("development", "confirmatory", "repeatability"):
        rows = selection.get(partition)
        if not isinstance(rows, list):
            raise ValueError("HANNA optimizer frozen selection partition is malformed")
        for row in rows:
            if isinstance(row, Mapping) and isinstance(row.get("item_id"), str):
                candidates.setdefault(row["item_id"], []).append(row)
    selected: list[Mapping[str, Any]] = []
    for item_id in fresh_ids:
        rich = [row for row in candidates.get(item_id, []) if all(isinstance(row.get(key), str) for key in ("item_id", "model", "story_id", "prompt_sha256"))]
        if not rich:
            raise ValueError("HANNA optimizer frozen selection lacks a source-bound item")
        models = {row["model"] for row in rich}
        story_ids = {row["story_id"] for row in rich}
        prompt_hashes = {row["prompt_sha256"] for row in rich}
        if not (len(models) == len(story_ids) == len(prompt_hashes) == 1):
            raise ValueError("HANNA optimizer frozen item source bindings disagree")
        selected.append(rich[0])
    try:
        raw_csv = _read_bytes_checked(csv_path)
        csv_sha256 = hashlib.sha256(raw_csv).hexdigest()
        if csv_sha256 != CONTRACT["eligible_universe"]["source"]["hanna_csv_sha256"]:
            raise ValueError("hash drifted")
        cached = _ELIGIBLE_MAP_CACHE.get((frozen_sha256, csv_sha256))
        if cached is not None:
            return [dict(row) for row in cached]
        rows = list(csv.DictReader(io.StringIO(raw_csv.decode("utf-8-sig"))))
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        raise ValueError("HANNA optimizer CSV cannot be read") from exc
    if not rows or set(rows[0]) != {"Story ID", "Prompt", "Human", "Story", "Model", "Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity", "Worker ID", "Assignment ID", "Work time in seconds", "Name"}:
        raise ValueError("HANNA optimizer CSV schema drifted")
    prompts: dict[str, str] = {}
    for row in rows:
        story_id, prompt = row.get("Story ID"), row.get("Prompt")
        if not isinstance(story_id, str) or not isinstance(prompt, str):
            raise ValueError("HANNA optimizer CSV row is malformed")
        if story_id in prompts and prompts[story_id] != prompt:
            raise ValueError("HANNA optimizer story has inconsistent prompts")
        prompts[story_id] = prompt
    result = []
    for row in selected:
        if row["model"] == "Human":
            continue
        prompt = prompts.get(row["story_id"])
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt is not None else None
        if prompt_sha256 != row["prompt_sha256"]:
            raise ValueError("HANNA optimizer prompt binding drifted")
        source_item_id = row["item_id"]
        result.append({
            "item_id": "item-" + hashlib.sha256(source_item_id.encode("utf-8")).hexdigest()[:16],
            "source_item_id": source_item_id,
            "story_id": row["story_id"],
            "source_model": row["model"],
            "prompt_group_id": "prompt-" + prompt_sha256[:16],
            "prompt_sha256": prompt_sha256,
        })
    result.sort(key=lambda row: row["item_id"])
    if len(result) != 80 or len({row["item_id"] for row in result}) != 80:
        raise ValueError("HANNA optimizer generated universe drifted")
    _ELIGIBLE_MAP_CACHE[(frozen_sha256, csv_sha256)] = tuple(dict(row) for row in result)
    return result


def validate_eligible_map(value: list[Mapping[str, Any]], *, frozen_successor_path: Path, hanna_csv_path: Path) -> None:
    expected = derive_eligible_map(frozen_successor_path, hanna_csv_path)
    if value != expected or sha256(value) != CONTRACT["eligible_universe"]["item_group_map_sha256"]:
        raise ValueError("HANNA optimizer item-to-group mapping drifted")
    universe = CONTRACT["eligible_universe"]
    if [row["item_id"] for row in value] != universe["item_ids"] or sorted({row["prompt_group_id"] for row in value}) != universe["group_ids"] or sha256([row["prompt_sha256"] for row in value]) != universe["prompt_sha256s_sha256"]:
        raise ValueError("HANNA optimizer item/group commitments drifted")


def derive_split_manifest(*, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    split = CONTRACT["split"]
    ranked = sorted(CONTRACT["eligible_universe"]["group_ids"], key=lambda group: (hashlib.sha256(f"{split['seed']}:hanna_optimizer_split_v1:{group}".encode("utf-8")).hexdigest(), group))
    eligible = derive_eligible_map(frozen_successor_path, hanna_csv_path)
    sizes: dict[str, int] = {group: 0 for group in ranked}
    for row in eligible:
        sizes[row["prompt_group_id"]] += 1

    def choose(groups: list[str], group_count: int, item_count: int) -> list[str]:
        cache: dict[tuple[int, int, int], bool] = {}

        def feasible(index: int, groups_needed: int, items_needed: int) -> bool:
            key = (index, groups_needed, items_needed)
            if key not in cache:
                if groups_needed == 0:
                    cache[key] = items_needed == 0
                elif index == len(groups) or groups_needed > len(groups) - index or items_needed < 0:
                    cache[key] = False
                else:
                    cache[key] = feasible(index + 1, groups_needed - 1, items_needed - sizes[groups[index]]) or feasible(index + 1, groups_needed, items_needed)
            return cache[key]

        if not feasible(0, group_count, item_count):
            raise ValueError("HANNA optimizer group-disjoint split is infeasible")
        selected: list[str] = []
        remaining_groups, remaining_items = group_count, item_count
        for index, group in enumerate(groups):
            if remaining_groups and feasible(index + 1, remaining_groups - 1, remaining_items - sizes[group]):
                selected.append(group)
                remaining_groups -= 1
                remaining_items -= sizes[group]
        if remaining_groups or remaining_items:
            raise ValueError("HANNA optimizer split selection drifted")
        return selected

    train = choose(ranked, 24, 48)
    development = choose([group for group in ranked if group not in train], 7, 13)
    confirmation = [group for group in ranked if group not in train and group not in development]
    if len(confirmation) != 8 or sum(sizes[group] for group in confirmation) != 19:
        raise ValueError("HANNA optimizer confirmation split drifted")
    groups: list[dict[str, str]] = []
    for partition, selected_groups in (("train", train), ("development", development), ("confirmation", confirmation)):
        groups.extend({"prompt_group_id": group, "partition": partition} for group in selected_groups)
    partitions = {row["prompt_group_id"]: row["partition"] for row in groups}
    items = [{"item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": partitions[row["prompt_group_id"]]} for row in eligible]
    return {"format_version": 1, "study_id": CONTRACT["study_id"], "eligible_universe_group_ids_sha256": CONTRACT["eligible_universe"]["group_ids_sha256"], "eligible_universe_item_group_map_sha256": CONTRACT["eligible_universe"]["item_group_map_sha256"], "split_algorithm_sha256": split["algorithm_sha256"], "groups": sorted(groups, key=lambda row: row["prompt_group_id"]), "items": items}


def validate_split_manifest(value: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path) -> None:
    _exact(value, {"format_version", "study_id", "eligible_universe_group_ids_sha256", "eligible_universe_item_group_map_sha256", "split_algorithm_sha256", "groups", "items"}, "split manifest")
    if value != derive_split_manifest(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path):
        raise ValueError("Optimizer split manifest is not the frozen derivation")


def derive_selection_artifact(*_args: Any, **_kwargs: Any) -> None:
    raise ValueError(UNIMPLEMENTED_BLOCKER)


def validate_selection_artifact(*_args: Any, **_kwargs: Any) -> None:
    raise ValueError(UNIMPLEMENTED_BLOCKER)


def contract_sha256() -> str:
    return sha(CONTRACT_PATH)


def atomic_output_directory(output: Path, files: Mapping[str, str]) -> None:
    output = checked_output_path(output)
    if output.exists():
        raise ValueError("Refusing to overwrite or merge an existing optimizer output")
    if any(not isinstance(name, str) or Path(name).name != name for name in files):
        raise ValueError("Optimizer output file name is invalid")
    output.parent.mkdir(parents=True, exist_ok=True)
    checked_path(output.parent, must_exist=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for name, text in files.items():
            destination = checked_path(staging / name)
            destination.write_text(text, encoding="utf-8", newline="\n")
            checked_path(destination, must_exist=True)
        checked_path(staging, must_exist=True)
        checked_path(output)
        os.rename(staging, output)
    except BaseException:
        try:
            checked_path(staging, must_exist=True)
            for path in staging.iterdir():
                checked_path(path, must_exist=True)
                path.unlink()
            staging.rmdir()
        except (OSError, ValueError):
            pass
        raise
