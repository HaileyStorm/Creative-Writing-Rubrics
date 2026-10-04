"""Freeze label-free P1b AI-generation requests without provider contact."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODEL = "gpt-6.1-sol"
EFFORT = "high"
POLICY = "codex_native_rollout_v1"
DESIGN = "semantic-crossform-p1b-v1"
VARIANTS = ("original", "target_defect", "legitimate_style")
SECONDARY_ACCOUNT_SHA256 = "a283be8dc909b7f172c1a348c38883deb00394b66de29023cbe45de4bbc37d3d"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def within(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()) and path != root.resolve(), "Frozen artifact escapes its root")
    return path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "Required local module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def families():
    definitions = [
        ("short_narrative", "self_contained_short_story", "prose.short_story", "craft.narrative.plot_and_causality.causal_chain",
         "A grounded coastal salvage story in spare close third person.",
         "Break one decisive event's causal dependency while preserving its preceding conditions and outcome.",
         "Use a restrained, more elliptical causal presentation whose necessary connection remains recoverable."),
        ("short_narrative", "self_contained_short_story", "prose.short_story", "craft.narrative.point_of_view_and_focalization.access",
         "A domestic negotiation in first person with an explicitly limited narrator.",
         "Give that narrator decisive private information with no observation, communication, inference or declared omniscient access.",
         "Change disclosure timing or use an explicitly uncertain inference without violating the chosen access rules."),
        ("short_narrative", "self_contained_short_story", "prose.short_story", "craft.narrative.plot_and_causality.consequence",
         "A lightly comic repair-shop story with a consequential physical state change.",
         "Reset one important object or bodily state after an explicit irreversible change, without a repair or intervening event.",
         "Tell the same state-preserving events with a deliberate temporal return whose ordering is intelligible."),
        ("short_narrative", "self_contained_short_story", "prose.short_story", "craft.narrative.plot_and_causality.setup",
         "A quiet speculative story whose resolution depends on a modest established world rule.",
         "Remove or contradict the one necessary preparation for the resolution while preserving the resolution and unrelated facts.",
         "Prepare the same resolution indirectly through an apt detail rather than conspicuous explanation."),
        ("novel_work_segment", "bounded_two_scene_work_segment", "prose.chapter", "craft.narrative.foreshadowing_setup_and_payoff.earned",
         "Two connected scenes from an invented social novel, with an explicit supplied setup and later consequential payoff.",
         "Change a necessary planted condition so that the same payoff no longer follows credibly from the supplied evidence.",
         "Use a nonlinear or understated presentation that preserves the setup/payoff relation within the supplied segment."),
        ("novel_work_segment", "bounded_two_scene_work_segment", "prose.chapter", "craft.narrative.temporal_and_spatial_continuity.objects",
         "Two connected scenes from an invented historical novel; track a consequential object through custody and location.",
         "Introduce one incompatible custody/location state for that object without a transfer or declared alternative explanation.",
         "Vary focalization and revelation order while keeping the object's actual custody and chronology consistent."),
        ("poem", "complete_free_verse_poem", "poetry.free_verse", "form.poetry.general_poetry.image_relation",
         "A non-narrative free-verse poem with a connected image system and a contemplative, possibly circular architecture.",
         "Disrupt a specific supplied relation among central images so they become disconnected decorations; do not equate stillness or circularity with failure.",
         "Use juxtaposition, stillness or circular return that preserves a plausible image relation without requiring a linear plot or a change on every line."),
        ("poem", "complete_free_verse_poem", "poetry.free_verse", "form.poetry.free_verse.repetition",
         "A free-verse poem with at least three supplied instances of a refrain whose contexts give it different pressure or meaning.",
         "Flatten the refrain's surrounding relations so the same instances become purposeless restatement without added pressure or meaning.",
         "Keep literal recurrence, chant or a circular return whose changing contexts plausibly justify repetition; recurrence alone is not a defect."),
    ]
    result = []
    for ordinal, (form, scope, bundle, question, brief, defect, legitimate) in enumerate(definitions, 1):
        family_id = f"p1b-f{ordinal:02d}"
        bounds = ({"min_words": 110, "max_words": 190, "min_nonempty_lines": 18, "max_nonempty_lines": 30}
                  if form == "poem" else {"min_words": 900, "max_words": 1200} if form == "novel_work_segment"
                  else {"min_words": 450, "max_words": 650})
        result.append({"ordinal": ordinal, "family_id": family_id, "form": form, "scope": scope,
            "bundle_id": bundle, "target_question_id": question, "brief": brief, "proposed_defect_intent": defect,
            "proposed_legitimate_intent": legitimate, "bounds": bounds, "max_variant_word_delta_fraction": 0.20,
            "variant_ids": {role: f"{family_id}.{role}" for role in VARIANTS},
            "oracle_status": "proposed_requires_independent_blinded_ai_intent_review",
            "scope_limitation": "Supplied work segment only; no whole-novel claim." if form == "novel_work_segment"
                                else "Text only; no performance or universal aesthetic-validity claim."})
    return result


def response_schema(family):
    text = {"type": "string", "minLength": 80, "maxLength": 20000}
    note = {"type": "string", "minLength": 20, "maxLength": 3000}
    variants = {}
    for role in VARIANTS:
        variants[role] = {"type": "object", "additionalProperties": False,
            "required": ["variant_id", "text", "proposed_intent_note"], "properties": {
                "variant_id": {"type": "string", "enum": [family["variant_ids"][role]]},
                "text": text, "proposed_intent_note": note}}
    return {"type": "object", "additionalProperties": False,
        "required": ["schema_version", "family_id", "form", "scope", "work_context", "preservation_anchors", "variants", "proposed_review_notes"],
        "properties": {"schema_version": {"type": "integer", "enum": [1]},
            "family_id": {"type": "string", "enum": [family["family_id"]]},
            "form": {"type": "string", "enum": [family["form"]]}, "scope": {"type": "string", "enum": [family["scope"]]},
            "work_context": {"type": "string", "minLength": 80, "maxLength": 3000}
                            if family["form"] == "novel_work_segment" else {"type": "string", "enum": [""]},
            "preservation_anchors": {"type": "array", "minItems": 3,
                "items": {"type": "string", "minLength": 8, "maxLength": 500}},
            "variants": {"type": "object", "additionalProperties": False, "required": list(VARIANTS), "properties": variants},
            "proposed_review_notes": note}}


def render_prompt(family, semantics):
    return ("Generate an entirely new AI-written creative fixture family. No existing manuscript, human target, rating, or literary ground truth is supplied.\n"
        "Return only the exact schema-conforming JSON. Generate the original first, then two descendants in the same family. All three must preserve genre, voice, characters, setting, and unrelated facts; only the declared target defect may violate its necessary anchor.\n"
        "Each variant must satisfy the declared word bounds. Keep derivative word counts within 20% of the original. For poems preserve line breaks and the stated nonempty-line bounds. Do not add role labels, explanatory headings or intent notes inside the creative text.\n"
        "Novel/work segments must contain two connected scenes and only claim the supplied bounded scope. Provide 50-150 words of shared newly invented work context; make the necessary dependencies assessable in the supplied material. For other forms, work_context must be empty.\n"
        "List 3-8 specific shared preservation anchors. Explain proposed intent outside the texts, including uncertainty and plausible objections. Do not declare any variant an accepted oracle, human label or objectively superior style. A different agent will independently review blinded variants before scoring.\n"
        "The canonical criterion below motivates the intended contrast; it is not a requested judge verdict. Preserve legitimate ellipticism, nonlinearity, refrain, contemplation and circular architecture when plausible. Do not force a change on every poetic line or infer a defect from recurrence alone.\n"
        "FAMILY CONTRACT\n" + canonical(family).decode("utf-8") + "CANONICAL TARGET SEMANTICS\n" + canonical(semantics).decode("utf-8"))


def helper_settings(raw):
    settings = {}
    for node in ast.parse(raw).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in {"CLI", "COLLECTION_HOME"} and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == "Path"
                and len(node.value.args) == 1 and isinstance(node.value.args[0], ast.Constant)
                and isinstance(node.value.args[0].value, str)):
            settings[node.targets[0].id] = Path(node.value.args[0].value).resolve()
    require(set(settings) == {"CLI", "COLLECTION_HOME"}, "Designated helper path constants are unavailable")
    require(settings["COLLECTION_HOME"].name == "cwr-sol-secondary"
            and settings["COLLECTION_HOME"].parent.name == "collection-accounts", "Helper does not select the designated secondary home")
    return settings


def build_plan(secondary_helper, cli, tools_root, timeout=900):
    require(0 < timeout <= 900, "Generation timeout must be positive and at most 900 seconds")
    files = {}
    source_paths = {"inputs/all_modules.yaml": REPO / "registry/all_modules.yaml",
        "inputs/all_bundles.yaml": REPO / "bundles/all_bundles.yaml", "implementation/core.py": REPO / "src/hbqrs/core.py",
        "implementation/runner.py": REPO / "src/hbqrs/runner.py", "implementation/codex_receipts.py": REPO / "src/hbqrs/codex_receipts.py",
        "implementation/schema_subset.py": tools_root / "model_work_queue/adapters/json_schema_subset.py",
        "implementation/secondary-helper.py": secondary_helper, "implementation/prepare.py": HERE / "prepare.py",
        "implementation/collect.py": HERE / "collect.py"}
    for name, path in source_paths.items():
        files[name] = path.read_bytes()
    settings = helper_settings(files["implementation/secondary-helper.py"])
    require(settings["CLI"] == cli.resolve(), "CLI differs from the designated helper")
    subset = load_module("p1b_schema_subset", source_paths["implementation/schema_subset.py"])
    sys.path.insert(0, str(REPO / "src"))
    from hbqrs.core import load_modules, load_bundles, resolve_bundle, compile_bundle, compiled_questions
    modules, bundles = load_modules(source_paths["inputs/all_modules.yaml"]), load_bundles(source_paths["inputs/all_bundles.yaml"])
    panels = {bundle: compiled_questions(compile_bundle(modules, resolve_bundle(bundles, bundle)))
              for bundle in {family["bundle_id"] for family in families()}}
    requests, pairs = [], []
    for family in families():
        selected = [r for r in panels[family["bundle_id"]] if r["question"]["id"] == family["target_question_id"]]
        require(len(selected) == 1, "Canonical target leaf is absent or ambiguous in the declared bundle")
        semantics = {"bundle_id": family["bundle_id"], "module_id": selected[0]["module_id"], "question": selected[0]["question"],
                     "role": selected[0]["role"], "bundle_leaf_count": len(panels[family["bundle_id"]])}
        schema = response_schema(family)
        subset.validate_schema(schema)
        prompt = render_prompt(family, semantics).encode("utf-8")
        stem = f"request-{family['ordinal']:04d}"
        prompt_path, schema_path, semantics_path = f"prompts/{stem}.txt", f"schemas/{stem}.json", f"semantics/{stem}.json"
        files[prompt_path], files[schema_path], files[semantics_path] = prompt, canonical(schema), canonical(semantics)
        row = {"ordinal": family["ordinal"], "family": family, "prompt_path": prompt_path, "schema_path": schema_path,
            "semantics_path": semantics_path, "prompt_sha256": digest(prompt), "schema_sha256": digest(files[schema_path]),
            "semantics_sha256": digest(files[semantics_path]), "prompt_bytes": len(prompt), "schema_bytes": len(files[schema_path])}
        row["logical_sample_id"] = digest(canonical({"design": DESIGN, "family": family, "prompt_sha256": row["prompt_sha256"],
                                                    "schema_sha256": row["schema_sha256"]}))
        requests.append(row)
        for role in VARIANTS[1:]:
            pairs.append({"pair_id": f"{family['family_id']}.original-vs-{role}", "family_id": family["family_id"],
                "left_variant_id": family["variant_ids"]["original"], "right_variant_id": family["variant_ids"][role],
                "comparison_intent": "proposed_target_damage" if role == "target_defect" else "legitimate_style_control",
                "oracle_status": family["oracle_status"]})
    manifest = {"schema_version": 1, "design": DESIGN, "stage": "ai_generation_before_independent_intent_review",
        "provider_calls_by_preparation": 0, "human_labels_supplied": 0, "private_manuscript_inputs": 0,
        "automatic_oracle_acceptance": False, "automatic_judging_or_promotion": False,
        "counts": {"families": 8, "generation_requests": 8, "variants": 24, "declared_pair_comparisons": 16,
                   "forms": dict(Counter(f["form"] for f in families()))}, "requests": requests, "pairs": pairs,
        "runtime": {"model": MODEL, "reasoning": EFFORT, "receipt_policy": POLICY, "timeout_seconds": timeout,
            "workers": 1, "attempts_per_logical_sample": 1, "automatic_retries": 0,
            "destination": "OpenAI ChatGPT subscription via designated secondary native Codex exec",
            "outbound_artifacts": "Frozen fresh family brief/intent/bounds, selected public canonical leaf semantics and response schema; no labels or private manuscripts.",
            "account_identity_sha256": SECONDARY_ACCOUNT_SHA256,
            "codex_home_sha256": digest(str(settings["COLLECTION_HOME"]).encode("utf-8")),
            "sampler": "Native defaults; temperature and sampling seed unsupported by this path.",
            "cost_token_cache_attestation": "Not established by the generation contract or requested settings."},
        "external_pins": {"secondary_helper_path_local_only": str(secondary_helper.resolve()),
            "cli_path_local_only": str(cli.resolve()), "cli_sha256": digest(cli.read_bytes()), "cli_bytes": cli.stat().st_size,
            "collection_home_path_local_only": str(settings["COLLECTION_HOME"]),
            "tools_root_local_only": str(tools_root.resolve()),
            "account_probe_sha256": digest((tools_root / "adaptive_settings/account_probe.py").read_bytes())},
        "artifacts": {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in files.items()}}
    manifest["manifest_content_sha256"] = digest(canonical(manifest))
    validate_manifest(manifest)
    return manifest, files


def validate_manifest(manifest):
    body = {k: v for k, v in manifest.items() if k != "manifest_content_sha256"}
    require(digest(canonical(body)) == manifest["manifest_content_sha256"], "Manifest content commitment differs")
    require(manifest["design"] == DESIGN and manifest["automatic_oracle_acceptance"] is False
            and manifest["automatic_judging_or_promotion"] is False
            and manifest["stage"] == "ai_generation_before_independent_intent_review"
            and manifest["human_labels_supplied"] == manifest["private_manuscript_inputs"] == 0, "Generation authority/scope differs")
    require(manifest["counts"] == {"families": 8, "generation_requests": 8, "variants": 24,
            "declared_pair_comparisons": 16, "forms": dict(Counter(f["form"] for f in families()))}, "Prospective generation counts differ")
    runtime = manifest["runtime"]
    require(runtime["model"] == MODEL and runtime["reasoning"] == EFFORT and runtime["receipt_policy"] == POLICY
            and runtime["workers"] == runtime["attempts_per_logical_sample"] == 1
            and runtime["automatic_retries"] == 0 and runtime["account_identity_sha256"] == SECONDARY_ACCOUNT_SHA256
            and 0 < runtime["timeout_seconds"] <= 900, "Generation runtime contract differs")
    requests = manifest["requests"]
    require([r["ordinal"] for r in requests] == list(range(1, 9))
            and [r["family"] for r in requests] == families()
            and len({r["logical_sample_id"] for r in requests}) == 8, "Prospective family/identity inventory differs")
    require(len(manifest["pairs"]) == 16 and len({p["pair_id"] for p in manifest["pairs"]}) == 16, "Declared pair inventory differs")
    for row in requests:
        family = row["family"]
        require(row["logical_sample_id"] == digest(canonical({"design": DESIGN, "family": family,
            "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"]})), "Logical sample commitment differs")
        for role in VARIANTS[1:]:
            selected = [p for p in manifest["pairs"] if p["pair_id"] == f"{family['family_id']}.original-vs-{role}"]
            require(len(selected) == 1 and selected[0]["family_id"] == family["family_id"]
                    and selected[0]["left_variant_id"] == family["variant_ids"]["original"]
                    and selected[0]["right_variant_id"] == family["variant_ids"][role]
                    and selected[0]["oracle_status"] == family["oracle_status"], "Predeclared pair/variant binding differs")
        for field in ("prompt", "schema", "semantics"):
            require(manifest["artifacts"][row[field + "_path"]]["sha256"] == row[field + "_sha256"], "Request artifact commitment differs")


def read_manifest(path):
    root = path.resolve().parent
    raw = path.read_bytes()
    manifest = json.loads(raw)
    validate_manifest(manifest)
    for relative, metadata in manifest["artifacts"].items():
        artifact = within(root, relative).read_bytes()
        require(len(artifact) == metadata["bytes"] and digest(artifact) == metadata["sha256"], "Frozen input/code artifact differs")
    return manifest, root, digest(raw)


def output_preflight(output, protected=()):
    output = output.resolve()
    require(not output.exists(), "Preparation output must be fresh and nonexistent")
    require(not output.is_relative_to(REPO) and not REPO.is_relative_to(output), "Private generation evidence must be outside repository")
    for path in protected:
        require(not output.is_relative_to(path.resolve()) and not path.resolve().is_relative_to(output), "Output overlaps a retained input")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--secondary-helper", type=Path, required=True)
    parser.add_argument("--codex-cli", type=Path, required=True)
    parser.add_argument("--tools-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        output_preflight(args.output_root, (args.secondary_helper, args.codex_cli, args.tools_root))
        manifest, files = build_plan(args.secondary_helper, args.codex_cli, args.tools_root, args.timeout)
        if not args.dry_run:
            args.output_root.mkdir(parents=True, exist_ok=False)
            for name, raw in files.items():
                write_new(within(args.output_root, name), raw)
            write_new(args.output_root / "manifest.json", canonical(manifest))
        print(json.dumps({"dry_run": args.dry_run, "manifest_sha256": digest(canonical(manifest)),
                          "manifest_content_sha256": manifest["manifest_content_sha256"], "counts": manifest["counts"],
                          "artifact_bytes": sum(len(raw) for raw in files.values()), "provider_calls": 0,
                          "oracle_status": "proposed_requires_independent_blinded_ai_intent_review"}, sort_keys=True))
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"P1b preparation failed: {error}\n")


if __name__ == "__main__":
    main()
