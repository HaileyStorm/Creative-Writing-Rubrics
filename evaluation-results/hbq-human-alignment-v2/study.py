"""External-only HANNA data preparation and frozen-study utilities."""
from __future__ import annotations

import csv, hashlib, json, random, statistics, subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.request import urlopen

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.paths import bundles_path, prompts_dir, registry_path, schema_dir

HERE = Path(__file__).resolve().parent
CSV_NAME, LICENSE_NAME = "hanna_stories_annotations.csv", "LICENSE"
RATING_DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PARTITIONS = ("development", "confirmatory")

def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
def sha256_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def sha256_text(value: str) -> str: return sha256_bytes(value.encode())
def sha256_path(path: Path) -> str: return sha256_bytes(path.read_bytes())
def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canonical_json(value))
def load_contract() -> dict[str, Any]: return json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))

@dataclass(frozen=True)
class HannaItem:
    item_id: str; story_id: str; model: str; prompt: str; story: str; ratings: Mapping[str, tuple[int, int, int]]
    @property
    def story_sha256(self) -> str: return sha256_text(self.story)
    @property
    def prompt_sha256(self) -> str: return sha256_text(self.prompt)
    @property
    def human_means(self) -> dict[str, float]: return {key: statistics.fmean(value) for key, value in self.ratings.items()}
    @property
    def human_overall(self) -> float: return statistics.fmean(self.human_means.values())

def fetch_or_verify_dataset(data_dir: Path, *, fetch: bool = False) -> dict[str, Any]:
    contract = load_contract()["dataset"]
    for name, url, expected in ((CSV_NAME, contract["csv_url"], contract["csv_sha256"]), (LICENSE_NAME, contract["license_url"], contract["license_sha256"])):
        path = data_dir / name
        if not path.is_file():
            if not fetch: raise ValueError(f"Missing external dataset file: {path}")
            with urlopen(url, timeout=60) as response:  # nosec B310: contract-frozen https URL
                content = response.read()
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
        if sha256_path(path) != expected: raise ValueError(f"HANNA {name} SHA-256 does not match frozen direct source")
    if "MIT License" not in (data_dir / LICENSE_NAME).read_text(encoding="utf-8"): raise ValueError("HANNA LICENSE is not MIT")
    return {name: {"sha256": sha256_path(data_dir / name), "bytes": (data_dir / name).stat().st_size} for name in (CSV_NAME, LICENSE_NAME)}

def load_hanna_items(data_dir: Path) -> list[HannaItem]:
    with (data_dir / CSV_NAME).open(encoding="utf-8", newline="") as handle: rows = list(csv.DictReader(handle))
    required = {"Story ID", "Prompt", "Story", "Model", "Worker ID", "Assignment ID", *RATING_DIMENSIONS}
    if not rows or not required <= set(rows[0]): raise ValueError("HANNA CSV headers differ from frozen contract")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if not row.get("Story ID", "").strip(): raise ValueError("HANNA row lacks Story ID")
        grouped[row["Story ID"]].append(row)
    result = []
    for story_id, records in sorted(grouped.items(), key=lambda pair: int(pair[0])):
        if len(records) != 3: raise ValueError(f"HANNA Story ID {story_id} has {len(records)}, not exactly three ratings")
        if any(len({row[field] for row in records}) != 1 or not records[0][field].strip() for field in ("Prompt", "Story", "Model")): raise ValueError(f"HANNA Story ID {story_id} has inconsistent text/model")
        ratings: dict[str, tuple[int, int, int]] = {}
        for dimension in RATING_DIMENSIONS:
            try: values = tuple(int(row[dimension]) for row in records)
            except (TypeError, ValueError) as exc: raise ValueError(f"HANNA Story ID {story_id} has invalid {dimension}") from exc
            if any(value not in range(1, 6) for value in values): raise ValueError(f"HANNA Story ID {story_id} has out-of-range {dimension}")
            ratings[dimension] = values
        result.append(HannaItem(f"hanna-{story_id}", story_id, records[0]["Model"], records[0]["Prompt"], records[0]["Story"], ratings))
    return result

def privacy_forbidden_strings(data_dir: Path) -> list[str]:
    """Actual identifiers are audit inputs only; never persist them in study results."""
    with (data_dir / CSV_NAME).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return sorted({value for row in rows for field in ("Worker ID", "Assignment ID") if len(value := str(row.get(field, "")).strip()) >= 8})

def select_partitions(items: Sequence[HannaItem], *, seed: int) -> dict[str, list[dict[str, Any]]]:
    """Split prompt clusters first; ratings only determine within-partition strata."""
    contract = load_contract()["selection"]
    prompts = {item.prompt_sha256: item.prompt for item in items}
    if len(prompts) != contract["prompt_groups"]:
        raise ValueError(f"Expected {contract['prompt_groups']} distinct HANNA prompts, found {len(prompts)}")
    groups = sorted(prompts)
    random.Random(f"{seed}:prompt-groups").shuffle(groups)
    groups_by_partition = {
        "development": set(groups[:contract["prompt_groups_per_partition"]]),
        "confirmatory": set(groups[contract["prompt_groups_per_partition"]:]),
    }
    if groups_by_partition["development"] & groups_by_partition["confirmatory"]:
        raise ValueError("Prompt groups overlap across partitions")
    selected = {name: [] for name in PARTITIONS}
    for partition in PARTITIONS:
        by_model: dict[str, list[HannaItem]] = defaultdict(list)
        for item in items:
            if item.prompt_sha256 in groups_by_partition[partition]: by_model[item.model].append(item)
        if len(by_model) != contract["models"]:
            raise ValueError(f"{partition} does not cover every Model")
        for model in sorted(by_model):
            ordered = sorted(by_model[model], key=lambda item: (item.human_overall, int(item.story_id)))
            quartiles: dict[int, list[HannaItem]] = {number: [] for number in range(1, 5)}
            for index, item in enumerate(ordered): quartiles[min(4, 4 * index // len(ordered) + 1)].append(item)
            for quartile, stratum in quartiles.items():
                if len(stratum) < contract["items_per_model_quartile_partition"]: raise ValueError(f"{partition}/{model}/{quartile} lacks enough prompt-disjoint items")
                shuffled = sorted(stratum, key=lambda item: int(item.story_id)); random.Random(f"{seed}:{partition}:{model}:{quartile}").shuffle(shuffled)
                for rank, item in enumerate(shuffled[:contract["items_per_model_quartile_partition"]], 1):
                    selected[partition].append({"item_id": item.item_id, "story_id": item.story_id, "model": model, "quartile": quartile, "selected_rank": rank, "story_sha256": item.story_sha256, "prompt_sha256": item.prompt_sha256, "prompt_group_id": f"prompt-{item.prompt_sha256[:16]}"})
    for values in selected.values(): values.sort(key=lambda row: (row["model"], row["quartile"], row["selected_rank"]))
    if len(selected["development"]) != 88 or len(selected["confirmatory"]) != 88 or len({row["item_id"] for rows in selected.values() for row in rows}) != 176: raise ValueError("Selection must be 88 disjoint items per partition")
    if {row["prompt_sha256"] for row in selected["development"]} & {row["prompt_sha256"] for row in selected["confirmatory"]}: raise ValueError("Selected prompt overlap across partitions")
    return selected

def mapping_sets() -> dict[str, list[str]]:
    return {
      "Relevance": ["task.contract.hanna.prompt_response", "core.task_and_brief_fidelity.operation", "core.audience_and_purpose_fit.use_context"],
      "Coherence": ["form.prose.short_story.unity", "form.prose.short_story.structure", "craft.narrative.plot_and_causality.causal_chain", "craft.narrative.plot_and_causality.consequence", "craft.narrative.scene_construction.progression"],
      "Empathy": ["craft.narrative.characterization.dimensionality", "craft.narrative.characterization.motives", "core.emotional_and_intellectual_effect.earned_emotion", "core.emotional_and_intellectual_effect.aftermath", "craft.narrative.narrative_momentum.investment"],
      "Surprise": ["core.freshness_and_non_genericness.no_cliche", "core.freshness_and_non_genericness.no_stock_beats", "core.freshness_and_non_genericness.unpredictable_specificity", "core.freshness_and_non_genericness.no_default_metaphors", "craft.narrative.theme_and_subtext.open_questions"],
      "Engagement": ["craft.narrative.narrative_momentum.curiosity", "craft.narrative.narrative_momentum.investment", "craft.narrative.narrative_momentum.commitment", "craft.narrative.scene_construction.pressure", "core.language_craft.cadence"],
      "Complexity": ["core.audience_and_purpose_fit.complexity", "craft.narrative.theme_and_subtext.emergence", "craft.narrative.theme_and_subtext.development", "craft.narrative.theme_and_subtext.counterpoint", "craft.narrative.characterization.contradiction"],
    }

def make_task_contract(item: HannaItem) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": "hanna", "artifact_id": item.item_id, "context": {"artifact_kind": "short prose fiction", "declared_scope": "complete short story", "completion_status": "complete", "background": ["The supplied context is the originating HANNA writing prompt."], "constraints": ["Evaluate the story as a response to that supplied prompt."], "audience": ["general fiction reader"]}, "preferences": [], "priorities": [], "weighted_goals": [{"goal_id": "prompt_response", "atomic_question": "Does the story meaningfully respond to the supplied HANNA writing prompt?", "weight": 2.0, "source": {"kind": "driving_prompt", "reference": "HANNA Prompt", "exact_excerpt": item.prompt}, "applies_to": ["whole artifact"], "rationale": "Non-gating prompt-specific relevance signal."}], "binding_requirements": []}

def compiled_question_ids() -> list[str]:
    sample = HannaItem("hanna-sample", "0", "sample", "prompt", "story", {key: (3, 3, 3) for key in RATING_DIMENSIONS})
    bundle = resolve_bundle(load_bundles(bundles_path()), "prose.short_story")
    return [str(row["question"]["id"]) for row in compiled_questions(compile_bundle(load_modules(registry_path()), bundle, task_contract=make_task_contract(sample)))]
def assert_mapping_valid(question_ids: Iterable[str] | None = None) -> None:
    missing = {item for values in mapping_sets().values() for item in values} - set(question_ids or compiled_question_ids())
    if missing: raise ValueError("Pre-registered mapping IDs absent from compiled bundle: " + ", ".join(sorted(missing)))
def fingerprint(path: Path) -> dict[str, Any]: return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_path(path)}
def assert_frozen_package_files(expected: Mapping[str, Any], paths: Sequence[Path]) -> None:
    for path in paths:
        actual = fingerprint(path)
        if expected.get(path.name) != actual: raise ValueError(f"Frozen package file drifted: {path.name}")
def package_paths() -> list[Path]:
    root = HERE.parent.parent
    return [
        registry_path(), bundles_path(), prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md",
        prompts_dir() / "judge" / "JUDGE_PREFIX.md", schema_dir() / "hbq_judge_response.schema.json",
        schema_dir() / "hbq_verdict.schema.json", schema_dir() / "hbq_task_contract.schema.json",
        schema_dir() / "hbq_score_report.schema.json", root / "src" / "hbqrs" / "core.py",
        root / "src" / "hbqrs" / "runner.py", root / "src" / "hbqrs" / "weights.py",
        root / "src" / "hbqrs" / "paths.py", root / "src" / "hbqrs" / "__init__.py", HERE / "study.py", HERE / "prepare_hanna.py",
        HERE / "run_study.py", HERE / "analyze_study.py", HERE / "confirmation_gate.py", HERE / "study-contract.json",
    ]

def freeze_external_work(data_dir: Path, work_dir: Path, *, fetch: bool = False) -> dict[str, Any]:
    dataset_files = fetch_or_verify_dataset(data_dir, fetch=fetch); contract = load_contract(); items = load_hanna_items(data_dir); selections = select_partitions(items, seed=contract["selection"]["seed"]); assert_mapping_valid()
    if (work_dir / "frozen-run-contract.json").exists(): raise ValueError("Refusing to overwrite existing frozen external contract")
    by_id = {item.item_id: item for item in items}
    for partition, rows in selections.items():
        for row in rows:
            item = by_id[row["item_id"]]; folder = work_dir / "inputs" / partition / item.item_id; folder.mkdir(parents=True, exist_ok=False)
            (folder / "source.md").write_text(item.story, encoding="utf-8", newline="\n"); (folder / "prompt.md").write_text(item.prompt, encoding="utf-8", newline="\n"); write_json(folder / "task-contract.json", make_task_contract(item))
            row["external_input"] = {name: fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
    repeat = []
    for model in sorted({row["model"] for row in selections["development"]}):
        candidates = [row for row in selections["development"] if row["model"] == model]
        choice = min(candidates, key=lambda row: sha256_text(f"{contract['repeatability']['seed']}:{model}:{row['item_id']}")); repeat.append({"item_id": choice["item_id"], "model": model, "partition": "development"})
    try: commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE.parent.parent, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError): commit = "UNAVAILABLE"
    clean = subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE.parent.parent, text=True, timeout=10).strip() == ""
    frozen = {"format_version": 2, "study_id": contract["study_id"], "frozen_before_execution": True, "dataset": {**contract["dataset"], "verified_files": dataset_files}, "selection": contract["selection"], "partitions": selections, "repeatability": {**contract["repeatability"], "items": repeat}, "provider": contract["provider"], "runner": contract["runner"], "mapping_sets": mapping_sets(), "mapping_sets_sha256": sha256_bytes(canonical_json(mapping_sets())), "package_commit": commit, "working_tree_clean": clean, "snapshot_mode": "explicit_file_fingerprints; clean tree is recorded but not relied upon", "package_files": {path.name: fingerprint(path) for path in package_paths()}, "question_ids": compiled_question_ids()}
    write_json(work_dir / "frozen-run-contract.json", frozen); return frozen

def validate_external_inputs(work_dir: Path, frozen: Mapping[str, Any]) -> None:
    for partition, rows in frozen["partitions"].items():
        for row in rows:
            folder = work_dir / "inputs" / partition / row["item_id"]
            expected = row["external_input"]
            for name in ("source.md", "prompt.md", "task-contract.json"):
                if expected.get(name) != fingerprint(folder / name): raise ValueError(f"External input drifted: {partition}/{row['item_id']}/{name}")

def validate_frozen_contract(work_dir: Path) -> dict[str, Any]:
    frozen = json.loads((work_dir / "frozen-run-contract.json").read_text(encoding="utf-8"))
    if not frozen.get("frozen_before_execution"): raise ValueError("Run contract was not frozen before execution")
    if frozen.get("question_ids") != compiled_question_ids(): raise ValueError("Compiled question sequence drifted")
    if frozen.get("mapping_sets") != mapping_sets() or frozen.get("mapping_sets_sha256") != sha256_bytes(canonical_json(mapping_sets())): raise ValueError("Frozen mapping set drifted")
    try: current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE.parent.parent, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as exc: raise ValueError("Cannot verify frozen package commit") from exc
    if frozen.get("package_commit") != current: raise ValueError("Frozen package commit drifted")
    assert_frozen_package_files(frozen.get("package_files", {}), package_paths()); validate_external_inputs(work_dir, frozen); assert_mapping_valid(frozen["question_ids"]); return frozen

def rank(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1]); result = [0.0] * len(values); start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]: end += 1
        for index, _ in ordered[start:end]: result[index] = (start + 1 + end) / 2
        start = end
    return result
def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2: return None
    a, b = statistics.fmean(left), statistics.fmean(right); top = sum((x-a)*(y-b) for x,y in zip(left,right)); bottom = sum((x-a)**2 for x in left) * sum((y-b)**2 for y in right)
    return None if not bottom else top / bottom**.5
def spearman(left: Sequence[float], right: Sequence[float]) -> float | None: return pearson(rank(left), rank(right))
def bootstrap_correlation(left: Sequence[float], right: Sequence[float], *, seed: int, draws: int = 1000) -> dict[str, Any]:
    point = spearman(left, right); generator = random.Random(seed); samples = []
    if point is not None:
        for _ in range(draws):
            indices = [generator.randrange(len(left)) for _ in left]; value = spearman([left[i] for i in indices], [right[i] for i in indices])
            if value is not None: samples.append(value)
    samples.sort(); return {"estimate": point, "draws": draws, "ci_95_low": samples[round(.025*(len(samples)-1))] if samples else None, "ci_95_high": samples[round(.975*(len(samples)-1))] if samples else None}
def alpha_nominal(rows: Iterable[Sequence[str]]) -> float | None:
    pooled: Counter[str] = Counter(); pairs = disagreements = 0
    for row in rows:
        pooled.update(row)
        for left, right in __import__('itertools').combinations(row, 2): pairs += 1; disagreements += left != right
    if not pairs: return None
    total = sum(pooled.values()); expected = sum(count*(total-count) for count in pooled.values()) / (total*(total-1)); observed = disagreements / pairs
    return 1.0 if not expected and not observed else (None if not expected else 1-observed/expected)
