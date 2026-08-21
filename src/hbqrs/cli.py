"""Command-line interface for HBQ-RS compile, score, export, and judge rendering."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time
from typing import Any, Sequence

from jsonschema import Draft202012Validator

from . import __version__
from .core import (
    HBQError,
    compile_bundle,
    compiled_questions,
    load_bundles,
    load_data,
    load_modules,
    load_verdicts,
    resolve_bundle,
    validate_registry,
    walk_tree,
    write_data,
)
from .scoring_v2 import score_bundle
from .pack import pack_book
from .paths import book_root, bundles_path, prompts_dir, registry_path, schema_dir
from .runner_v2 import run_judge
from .html_config import render_workflow_configurator
from .html_report import render_html_report, render_html_scorecard
from .html_status import render_workflow_status, summarize_workflow_progress
from .html_weights import render_weight_configurator
from .longform import segment_longform
from .longform_runner_v2 import run_longform_judge
from .weights import make_weight_profile, materialize_weight_profile
from .batch import run_longform_batch


def _load_registry(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return load_modules(args.registry), load_bundles(args.bundles)


def _load_task_contract(path: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = load_data(path)
    if not isinstance(value, dict):
        raise HBQError("Task contract must be a JSON or YAML object")
    errors = sorted(
        Draft202012Validator(load_data(schema_dir() / "hbq_task_contract.schema.json")).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        raise HBQError(f"Task contract violates its strict schema: {errors[0].message}")
    return value


def _load_weight_profile(path: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = load_data(path)
    if not isinstance(value, dict):
        raise HBQError("Weight profile must be a JSON or YAML object")
    return value


def _load_hierarchical_score_profile(path: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = load_data(path)
    if not isinstance(value, dict):
        raise HBQError("Hierarchical score profile must be a JSON or YAML object")
    return _load_hierarchical_score_profile_from_value(value)


def _cmd_init_score_profile(args: argparse.Namespace) -> int:
    source = Path(args.artifact)
    text = source.read_text(encoding="utf-8-sig")
    segmentation = segment_longform(text, artifact_id=source.stem or "artifact")
    eligible_units = [
        unit for unit in segmentation["units"] if unit["local_evaluation"]["eligible"]
    ]
    by_ordinal = {unit["ordinal"]: unit for unit in eligible_units}
    requested_ordinals = list(dict.fromkeys(args.unfinished_unit_ordinal))
    missing = sorted(set(requested_ordinals) - set(by_ordinal))
    if missing:
        available = ", ".join(str(ordinal) for ordinal in sorted(by_ordinal))
        raise HBQError(
            "Unfinished unit ordinals are not eligible source units: "
            + ", ".join(str(ordinal) for ordinal in missing)
            + f"; eligible ordinals are {available}"
        )
    profile: dict[str, Any] = {
        "profile_version": 1,
        "profile_id": args.profile_id,
        "global_weight": args.global_weight,
        "local_weight": args.local_weight,
        "local_reducer": args.local_reducer,
    }
    if requested_ordinals:
        profile["unfinished_unit_ids"] = [by_ordinal[ordinal]["unit_id"] for ordinal in requested_ordinals]
        profile["unfinished_unit_weight"] = args.unfinished_unit_weight
    if args.prologue_epilogue_weight is not None:
        profile["prologue_epilogue_weight"] = args.prologue_epilogue_weight
    _load_hierarchical_score_profile_from_value(profile)
    write_data(args.output, profile, fmt="json")
    return 0


def _load_hierarchical_score_profile_from_value(value: dict[str, Any]) -> dict[str, Any]:
    errors = sorted(
        Draft202012Validator(
            load_data(schema_dir() / "hbq_hierarchical_score_profile.schema.json")
        ).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        raise HBQError(f"Hierarchical score profile violates its strict schema: {errors[0].message}")
    total = float(value["global_weight"]) + float(value["local_weight"])
    if not math.isfinite(total) or total <= 0:
        raise HBQError("global_weight and local_weight must have a positive sum")
    return value


def _cmd_render_report(args: argparse.Namespace) -> int:
    report = load_data(args.report)
    if not isinstance(report, dict):
        raise HBQError("Long-form report must be a JSON or YAML object")
    html = (
        render_html_scorecard(
            report,
            layout=args.card_layout,
        )
        if args.scorecard
        else render_html_report(report, title=args.title)
    )
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return 0


def _cmd_configure(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    catalog = {
        "modules": [
            {
                key: module.get(key)
                for key in (
                    "module_id", "title", "description", "artifact_types", "valid_scopes"
                )
            }
            for module in modules
        ],
        "bundles": [
            {
                key: bundle.get(key)
                for key in (
                    "bundle_id", "title", "description", "artifact_types", "valid_scopes", "module_ids"
                )
            }
            for bundle in bundles
        ],
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_workflow_configurator(catalog, title=args.title), encoding="utf-8")
    return 0


def _cmd_init_weight_profile(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    profile = make_weight_profile(
        modules,
        resolve_bundle(bundles, args.bundle_id),
        profile_id=args.profile_id,
    )
    write_data(args.output, profile, fmt=args.format)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    target = Path(args.output or Path(args.output_dir) / "status.html").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    while True:
        progress = summarize_workflow_progress(args.output_dir)
        rendered = render_workflow_status(
            progress,
            refresh_seconds=args.interval if args.watch else None,
        )
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(target)
        if not args.watch or progress["complete"]:
            print(json.dumps({**progress, "status_html": str(target)}, ensure_ascii=False, indent=2))
            return 0
        time.sleep(args.interval)


def _cmd_configure_weights(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_weight_configurator(
            modules,
            resolve_bundle(bundles, args.bundle_id),
            title=args.title,
        ),
        encoding="utf-8",
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    module_schema = load_data(args.module_schema) if args.module_schema else None
    bundle_schema = load_data(args.bundle_schema) if args.bundle_schema else None
    errors = validate_registry(
        modules,
        bundles,
        module_schema=module_schema,
        bundle_schema=bundle_schema,
    )
    report = {
        "valid": not errors,
        "module_count": len(modules),
        "bundle_count": len(bundles),
        "question_count": sum(1 for module in modules for _ in walk_tree(module.get("tree", []))),
        "errors": errors,
    }
    write_data(args.output, report, fmt=args.format)
    return 0 if not errors else 1


def _cmd_compile(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    modules, bundle, _ = materialize_weight_profile(
        modules,
        resolve_bundle(bundles, args.bundle_id),
        _load_weight_profile(args.weight_profile),
    )
    packet = compile_bundle(
        modules,
        bundle,
        task_contract=_load_task_contract(args.task_contract),
    )
    write_data(args.output, packet, fmt=args.format)
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    modules, bundle, _ = materialize_weight_profile(
        modules,
        resolve_bundle(bundles, args.bundle_id),
        _load_weight_profile(args.weight_profile),
    )
    report = score_bundle(
        modules,
        bundle,
        load_verdicts(args.verdicts),
        artifact_id=args.artifact_id,
        task_contract=_load_task_contract(args.task_contract),
    )
    write_data(args.output, report, fmt=args.format)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    if args.what == "modules":
        output = [
            {
                "module_id": item["module_id"],
                "title": item.get("title"),
                "kind": item.get("kind"),
                "artifact_types": item.get("artifact_types", []),
                "valid_scopes": item.get("valid_scopes", []),
            }
            for item in modules
        ]
    else:
        output = [
            {
                "bundle_id": item["bundle_id"],
                "title": item.get("title"),
                "artifact_types": item.get("artifact_types", []),
                "valid_scopes": item.get("valid_scopes", []),
            }
            for item in bundles
        ]
    write_data(args.output, output, fmt=args.format)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    module_index = {item["module_id"]: item for item in modules}
    if args.identifier in module_index:
        write_data(args.output, module_index[args.identifier], fmt=args.format)
        return 0
    bundle = resolve_bundle(bundles, args.identifier)
    compiled = compile_bundle(modules, bundle)
    output = {
        "bundle": {
            "bundle_id": bundle.get("bundle_id"),
            "title": bundle.get("title"),
            "description": bundle.get("description"),
            "artifact_types": bundle.get("artifact_types", []),
            "valid_scopes": bundle.get("valid_scopes", []),
            "domains": bundle.get("domains", []),
        },
        "module_ids": bundle.get("module_ids", []),
        "compiled_counts": {
            "domain_questions": len(compiled.get("domain_questions", [])),
            "hard_gates": len(compiled.get("hard_gates", [])),
            "penalty_groups": len(compiled.get("penalty_groups", [])),
            "supplemental_questions": len(compiled.get("supplemental_questions", [])),
        },
    }
    write_data(args.output, output, fmt=args.format)
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    if args.bundle_id:
        compiled = compile_bundle(modules, resolve_bundle(bundles, args.bundle_id))
        rows = []
        for item in compiled_questions(compiled):
            question = dict(item["question"])
            rows.append(
                {
                    "bundle_id": args.bundle_id,
                    "module_id": item.get("module_id"),
                    "domain_id": item.get("domain_id"),
                    "role": item.get("role"),
                    "question_id": question.get("id"),
                    "criterion_key": question.get("criterion_key"),
                    "text": question.get("text"),
                    "question_type": question.get("question_type"),
                    "weight": question.get("weight"),
                    "severity": question.get("severity"),
                }
            )
    else:
        rows = []
        for module in modules:
            for leaf, group_ids, _weight in walk_tree(module.get("tree", [])):
                rows.append(
                    {
                        "module_id": module["module_id"],
                        "module_title": module.get("title"),
                        "kind": module.get("kind"),
                        "group_ids": list(group_ids),
                        "question_id": leaf.get("id"),
                        "criterion_key": leaf.get("criterion_key"),
                        "text": leaf.get("text"),
                        "question_type": leaf.get("question_type"),
                        "weight": leaf.get("weight"),
                        "severity": leaf.get("severity"),
                    }
                )
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    else:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
    return 0


def _read_prompt(name: str) -> str:
    path = prompts_dir() / "judge" / name
    return path.read_text(encoding="utf-8").strip()


def _cmd_render_judge(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    compiled = compile_bundle(
        modules,
        resolve_bundle(bundles, args.bundle_id),
        task_contract=_load_task_contract(args.task_contract),
    )
    questions = compiled_questions(compiled)
    if args.question_id:
        questions = [item for item in questions if item["question"].get("id") == args.question_id]
        if not questions:
            raise HBQError(f"Question {args.question_id!r} is not in bundle {args.bundle_id!r}")
    artifact = Path(args.artifact).read_text(encoding="utf-8") if args.artifact else ""
    packet = {
        "bundle_id": args.bundle_id,
        "questions": [
            {
                "role": item.get("role"),
                "module_id": item.get("module_id"),
                "domain_id": item.get("domain_id"),
                "question": item["question"],
            }
            for item in questions
        ],
    }
    sections = [
        _read_prompt("JUDGE_PREFIX.md"),
        "",
        _read_prompt("BINARY_EVALUATION_PROMPT.md"),
        "",
        "## Compiled questions",
        "",
        "```json",
        json.dumps(packet, ensure_ascii=False, indent=2),
        "```",
    ]
    if artifact:
        sections.extend(["", "## Artifact", "", artifact.rstrip(), ""])
    text = "\n".join(sections).rstrip() + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _cmd_pack(args: argparse.Namespace) -> int:
    summary = pack_book(Path(args.root) if args.root else None)
    write_data(args.output, summary, fmt=args.format)
    return 0


def _cmd_judge(args: argparse.Namespace) -> int:
    if args.upgrade_legacy_normalization and not args.resume:
        raise HBQError("--upgrade-legacy-normalization requires --resume")
    summary = run_judge(
        artifact_path=args.artifact,
        bundle_id=args.bundle_id,
        provider=args.provider,
        model=args.model,
        output_dir=args.output_dir,
        registry=args.registry,
        bundles=args.bundles,
        context_paths=args.context,
        task_contract_path=args.task_contract,
        weight_profile=_load_weight_profile(args.weight_profile),
        question_ids=args.question_id,
        batch_size=args.batch_size,
        batch_attempts=args.batch_attempts,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        temperature=args.temperature,
        allow_model_mismatch=args.allow_model_mismatch,
        reasoning=args.reasoning,
        codex_bin=args.codex_bin,
        grok_bin=args.grok_bin,
        allow_remote=args.allow_remote,
        resume=args.resume,
        dry_run=args.dry_run,
        timeout=args.timeout,
        artifact_id=args.artifact_id,
        judge_id=args.judge_id,
        strict_ai=args.strict_ai,
        allow_unattested_reasoning=args.allow_unattested_reasoning,
        upgrade_legacy_normalization=args.upgrade_legacy_normalization,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_longform(args: argparse.Namespace) -> int:
    if args.upgrade_legacy_normalization and not args.resume:
        raise HBQError("--upgrade-legacy-normalization requires --resume")
    driving_prompt = args.driving_prompt
    if args.driving_prompt_file:
        driving_prompt = Path(args.driving_prompt_file).read_text(encoding="utf-8-sig")
    summary = run_longform_judge(
        artifact_path=args.artifact,
        brief_paths=args.brief,
        output_dir=args.output_dir,
        provider=args.provider,
        model=args.model,
        registry=args.registry,
        bundles=args.bundles,
        artifact_kind=args.artifact_kind,
        declared_scope=args.declared_scope,
        completion_status=args.completion_status,
        artifact_id=args.artifact_id,
        driving_prompt=driving_prompt,
        bundle_id=args.bundle_id,
        module_ids=args.module_id,
        task_contract_path=args.task_contract,
        weight_profile=_load_weight_profile(args.weight_profile),
        local_weight_profile=_load_weight_profile(args.local_weight_profile),
        hierarchical_score_profile=_load_hierarchical_score_profile(
            args.hierarchical_score_profile
        ),
        local_bundle_id=args.local_bundle_id,
        route_sample_char_limit=args.route_sample_char_limit,
        local_sample_limit=args.local_sample_limit,
        frozen_sample_ordinals=args.frozen_sample_ordinal,
        binary_workers=args.binary_workers,
        batch_size=args.batch_size,
        batch_attempts=args.batch_attempts,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        temperature=args.temperature,
        allow_model_mismatch=args.allow_model_mismatch,
        openai_structured_outputs=args.openai_structured_outputs,
        structured_reasoning=args.structured_reasoning,
        judge_reasoning=args.judge_reasoning,
        codex_bin=args.codex_bin,
        grok_bin=args.grok_bin,
        allow_remote=args.allow_remote,
        resume=args.resume,
        dry_run=args.dry_run,
        plan_only=args.plan_only,
        timeout=args.timeout,
        strict_ai=args.strict_ai,
        allow_unattested_reasoning=args.allow_unattested_reasoning,
        upgrade_legacy_normalization=args.upgrade_legacy_normalization,
    )
    report_path = Path(args.output_dir) / "report.json"
    if args.html_report and report_path.is_file():
        report = load_data(report_path)
        if not isinstance(report, dict):
            raise HBQError("Completed long-form workflow did not produce an object report")
        (Path(args.output_dir) / "report.html").write_text(
            render_html_report(report), encoding="utf-8"
        )
        (Path(args.output_dir) / "scorecard.html").write_text(
            render_html_scorecard(report), encoding="utf-8"
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    summary = run_longform_batch(
        args.manifest,
        registry=args.registry,
        bundles=args.bundles,
        allow_remote=args.allow_remote,
        resume=args.resume,
        accept_reviewed=args.accept_reviewed,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    root = book_root()
    parser = argparse.ArgumentParser(
        prog="cwr",
        description="HBQ-RS creative-writing rubrics: compile, run, score, export, and render judge prompts.",
    )
    parser.add_argument("--registry", default=str(registry_path()), help="module registry JSON/JSONL/YAML")
    parser.add_argument("--bundles", default=str(bundles_path()), help="bundle collection JSON/JSONL/YAML")
    parser.add_argument("--version", action="version", version=f"creative-writing-rubrics {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate registry and bundles")
    validate.add_argument("--module-schema", default=str(schema_dir() / "hbq_rubric.schema.json"))
    validate.add_argument("--bundle-schema", default=str(schema_dir() / "hbq_bundle.schema.json"))
    validate.add_argument("-o", "--output")
    validate.add_argument("--format", choices=["json", "yaml"], default="json")
    validate.set_defaults(func=_cmd_validate)

    compile_parser = subparsers.add_parser("compile", help="compile one bundle into a flat judge packet")
    compile_parser.add_argument("bundle_id")
    compile_parser.add_argument("--task-contract", help="frozen task-contract JSON/YAML")
    compile_parser.add_argument("--weight-profile", help="strict scoring-weight profile JSON/YAML")
    compile_parser.add_argument("-o", "--output")
    compile_parser.add_argument("--format", choices=["json", "yaml"], default="json")
    compile_parser.set_defaults(func=_cmd_compile)

    score = subparsers.add_parser("score", help="aggregate verdicts under one bundle")
    score.add_argument("bundle_id")
    score.add_argument("verdicts", help="verdict JSON/JSONL/YAML")
    score.add_argument("--artifact-id")
    score.add_argument("--task-contract", help="same frozen task contract used during judging")
    score.add_argument("--weight-profile", help="strict scoring-weight profile JSON/YAML")
    score.add_argument("-o", "--output")
    score.add_argument("--format", choices=["json", "yaml"], default="json")
    score.set_defaults(func=_cmd_score)

    list_parser = subparsers.add_parser("list", help="list available modules or bundles")
    list_parser.add_argument("what", choices=["modules", "bundles"])
    list_parser.add_argument("-o", "--output")
    list_parser.add_argument("--format", choices=["json", "yaml"], default="json")
    list_parser.set_defaults(func=_cmd_list)

    show = subparsers.add_parser("show", help="show one module or bundle")
    show.add_argument("identifier")
    show.add_argument("-o", "--output")
    show.add_argument("--format", choices=["json", "yaml"], default="json")
    show.set_defaults(func=_cmd_show)

    export = subparsers.add_parser("export", help="export flattened questions as JSONL")
    export.add_argument("what", choices=["questions"])
    export.add_argument("--bundle", dest="bundle_id", help="limit export to one compiled bundle")
    export.add_argument("-o", "--output")
    export.set_defaults(func=_cmd_export)

    render = subparsers.add_parser(
        "render-judge",
        help="concatenate the judge prefix, binary-eval prompt, compiled questions, and optional artifact",
    )
    render.add_argument("--bundle", dest="bundle_id", required=True)
    render.add_argument("--artifact", help="path to the draft or other artifact text")
    render.add_argument("--question-id", help="render a single leaf instead of the full bundle")
    render.add_argument("--task-contract", help="frozen task-contract JSON/YAML")
    render.add_argument("-o", "--output")
    render.set_defaults(func=_cmd_render_judge)

    pack = subparsers.add_parser("pack", help="rebuild aggregate JSON/YAML/JSONL from per-file YAML")
    pack.add_argument("--root", default=str(root))
    pack.add_argument("-o", "--output")
    pack.add_argument("--format", choices=["json", "yaml"], default="json")
    pack.set_defaults(func=_cmd_pack)

    configure = subparsers.add_parser(
        "configure",
        help="write an optional self-contained local workflow setup page",
    )
    configure.add_argument("-o", "--output", required=True, help="HTML output path")
    configure.add_argument("--title", default="HBQ-RS long-form workflow setup")
    configure.set_defaults(func=_cmd_configure)

    weight_profile = subparsers.add_parser(
        "init-weight-profile",
        help="write every effective scoring weight for one bundle as editable JSON/YAML",
    )
    weight_profile.add_argument("bundle_id")
    weight_profile.add_argument("-o", "--output", required=True)
    weight_profile.add_argument("--profile-id", default="custom")
    weight_profile.add_argument("--format", choices=["json", "yaml"], default="json")
    weight_profile.set_defaults(func=_cmd_init_weight_profile)

    status = subparsers.add_parser(
        "status",
        help="render an optional local progress page from durable workflow checkpoints",
    )
    status.add_argument("output_dir", help="long-form workflow directory")
    status.add_argument("-o", "--output", help="HTML path; defaults to OUTPUT_DIR/status.html")
    status.add_argument(
        "--watch",
        action="store_true",
        help="keep regenerating the page until report.json is complete",
    )
    status.add_argument("--interval", type=int, choices=range(1, 61), default=3)
    status.set_defaults(func=_cmd_status)

    configure_weights = subparsers.add_parser(
        "configure-weights",
        help="write an optional offline editor for every scoring weight in one bundle",
    )
    configure_weights.add_argument("bundle_id")
    configure_weights.add_argument("-o", "--output", required=True)
    configure_weights.add_argument("--title", default="HBQ-RS scoring weights")
    configure_weights.set_defaults(func=_cmd_configure_weights)

    profile = subparsers.add_parser(
        "init-score-profile",
        help="create a strict, manuscript-bound starter profile for an optional composite score",
    )
    profile.add_argument("artifact", help="UTF-8 long-form text whose unit IDs the profile will bind")
    profile.add_argument("-o", "--output", required=True, help="profile JSON path")
    profile.add_argument("--profile-id", default="balanced-70-30")
    profile.add_argument("--global-weight", type=float, default=7.0)
    profile.add_argument("--local-weight", type=float, default=3.0)
    profile.add_argument(
        "--local-reducer", choices=["weighted_mean", "weakest_unit"], default="weighted_mean"
    )
    profile.add_argument(
        "--unfinished-unit-ordinal",
        action="append",
        type=int,
        default=[],
        help="mark an unfinished source unit; repeatable, with one shared modifier",
    )
    profile.add_argument("--unfinished-unit-weight", type=float, default=0.5)
    profile.add_argument(
        "--prologue-epilogue-weight",
        type=float,
        help="shared modifier for units deterministically headed Prologue or Epilogue",
    )
    profile.set_defaults(func=_cmd_init_score_profile)

    report = subparsers.add_parser(
        "render-report", help="render a strict long-form report as self-contained offline HTML"
    )
    report.add_argument("report", help="long-form report JSON/YAML")
    report.add_argument("-o", "--output", required=True, help="HTML output path")
    report.add_argument("--scorecard", action="store_true", help="render only the embeddable scorecard")
    report.add_argument(
        "--card-layout", choices=["summary", "compact", "minimal"], default="summary"
    )
    report.add_argument("--title", default="HBQ-RS long-form evaluation")
    report.set_defaults(func=_cmd_render_report)

    batch = subparsers.add_parser(
        "batch",
        help="route and grade multiple long-form samples from a strict manifest",
    )
    batch.add_argument("manifest", help="batch manifest JSON/YAML")
    batch.add_argument("--allow-remote", action="store_true")
    batch.add_argument("--resume", action="store_true")
    batch.add_argument(
        "--accept-reviewed",
        action="store_true",
        help="grade review-policy jobs from their persisted, accepted plans",
    )
    batch.set_defaults(func=_cmd_batch)

    judge = subparsers.add_parser(
        "judge",
        help="run a bundle through an OpenAI-compatible endpoint, Codex CLI, Grok Build CLI, or Nous bridge, then score it",
    )
    judge.add_argument("artifact", help="UTF-8 text artifact to evaluate")
    judge.add_argument("--bundle", dest="bundle_id", required=True)
    judge.add_argument("--provider", choices=["openai", "codex", "grok", "nous"], required=True)
    judge.add_argument("--model", required=True)
    judge.add_argument("--output-dir", required=True, help="new run directory, or an existing run with --resume")
    judge.add_argument("--context", action="append", default=[], help="additional UTF-8 brief/canon file; repeatable")
    judge.add_argument("--task-contract", help="frozen task contract with weighted goals and binding requirements")
    judge.add_argument("--weight-profile", help="strict scoring-weight profile JSON/YAML")
    judge.add_argument("--question-id", action="append", default=[], help="limit to a selected leaf; repeatable")
    judge.add_argument("--batch-size", type=int, default=12)
    judge.add_argument(
        "--batch-attempts",
        type=int,
        default=3,
        help="maximum cumulative provider attempts per batch; new-policy retries include validation feedback",
    )
    judge.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    judge.add_argument("--api-key-env", default="OPENAI_API_KEY")
    judge.add_argument("--temperature", type=float)
    judge.add_argument("--allow-model-mismatch", action="store_true")
    judge.add_argument("--reasoning", choices=["low", "medium", "high", "xhigh", "max"], default="medium")
    judge.add_argument("--codex-bin", default="codex")
    judge.add_argument("--grok-bin", default="grok")
    judge.add_argument(
        "--allow-unattested-reasoning",
        action="store_true",
        help="allow provisional Grok/Nous results when the provider does not attest reasoning effort",
    )
    judge.add_argument("--allow-remote", action="store_true")
    judge.add_argument("--resume", action="store_true")
    judge.add_argument(
        "--upgrade-legacy-normalization",
        action="store_true",
        help="on --resume only, upgrade legacy rejected evidence normalization with an immutable audit sidecar",
    )
    judge.add_argument("--dry-run", action="store_true")
    judge.add_argument("--timeout", type=float, default=600.0)
    judge.add_argument("--artifact-id")
    judge.add_argument("--judge-id")
    judge.add_argument("--strict-ai", action="store_true", help="apply the stricter AI-output judge prefix")
    judge.set_defaults(func=_cmd_judge)

    longform = subparsers.add_parser(
        "longform",
        help="route, map, judge, and report on a long-form text with resumable provider calls",
    )
    longform.add_argument("artifact", help="UTF-8 long-form text to evaluate")
    longform.add_argument("--brief", action="append", default=[], help="author brief or notes; repeatable")
    driving_prompt = longform.add_mutually_exclusive_group()
    driving_prompt.add_argument(
        "--driving-prompt", default="", help="prompt that originally drove the artifact"
    )
    driving_prompt.add_argument(
        "--driving-prompt-file",
        help="UTF-8 file containing the human, competition, workshop, or model prompt",
    )
    longform.add_argument("--artifact-kind", default="prose_fiction")
    longform.add_argument("--scope", dest="declared_scope", default="manuscript")
    completion = longform.add_mutually_exclusive_group()
    completion.add_argument(
        "--completion-status",
        choices=["complete", "work_in_progress", "excerpt", "unknown"],
        default="work_in_progress",
        help="declared completion state; defaults to work_in_progress",
    )
    completion.add_argument(
        "--wip",
        dest="completion_status",
        action="store_const",
        const="work_in_progress",
        help="explicit work-in-progress mode; completion-only criteria are not treated as failures",
    )
    longform.add_argument("--artifact-id")
    longform.add_argument(
        "--bundle",
        dest="bundle_id",
        help="freeze one complete bundle instead of automatic bundle/module selection",
    )
    longform.add_argument(
        "--module",
        dest="module_id",
        action="append",
        default=[],
        help="with --bundle, freeze one selected in-bundle module; repeatable",
    )
    longform.add_argument(
        "--task-contract",
        help="freeze a validated task contract instead of using the route model's contract",
    )
    longform.add_argument(
        "--hierarchical-score-profile",
        help="optional JSON/YAML policy for a separate global-plus-local headline score",
    )
    longform.add_argument(
        "--weight-profile",
        help="optional scoring-weight profile for the whole-work bundle",
    )
    longform.add_argument(
        "--local-weight-profile",
        help="optional scoring-weight profile for the local unit bundle",
    )
    longform.add_argument("--local-bundle", dest="local_bundle_id")
    longform.add_argument("--route-sample-chars", dest="route_sample_char_limit", type=int, default=12000)
    longform.add_argument(
        "--local-sample-limit",
        type=int,
        default=None,
        help="explicitly sample at most this many local units; omitted means evaluate every unit",
    )
    longform.add_argument(
        "--frozen-sample-ordinal",
        action="append",
        type=int,
        default=[],
        help="score this unit ordinal locally; repeat to compare the same units across drafts",
    )
    longform.add_argument(
        "--binary-workers",
        type=int,
        default=1,
        help="bounded parallel workers for global and local binary passes; does not reduce coverage",
    )
    longform.add_argument("--provider", choices=["openai", "codex", "grok", "nous"], required=True)
    longform.add_argument("--model", required=True)
    longform.add_argument("--output-dir", required=True, help="new workflow directory, or existing with --resume")
    longform.add_argument("--batch-size", type=int, default=12)
    longform.add_argument(
        "--batch-attempts",
        type=int,
        default=3,
        help="maximum cumulative provider attempts per binary batch; new-policy retries include validation feedback",
    )
    longform.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    longform.add_argument("--api-key-env", default="OPENAI_API_KEY")
    longform.add_argument("--temperature", type=float)
    longform.add_argument("--allow-model-mismatch", action="store_true")
    longform.add_argument(
        "--openai-structured-outputs",
        action="store_true",
        help="request strict JSON Schema output from an endpoint that supports OpenAI Structured Outputs",
    )
    longform.add_argument(
        "--structured-reasoning",
        choices=["low", "medium", "high", "xhigh", "max"],
        default="high",
        help="Codex reasoning for route, map, and synthesis passes",
    )
    longform.add_argument(
        "--judge-reasoning",
        choices=["low", "medium", "high", "xhigh", "max"],
        default="medium",
        help="Codex reasoning for binary rubric batches",
    )
    longform.add_argument("--codex-bin", default="codex")
    longform.add_argument("--grok-bin", default="grok")
    longform.add_argument(
        "--allow-unattested-reasoning",
        action="store_true",
        help="allow provisional Grok/Nous results when the provider does not attest reasoning effort",
    )
    longform.add_argument("--allow-remote", action="store_true")
    longform.add_argument("--resume", action="store_true")
    longform.add_argument(
        "--upgrade-legacy-normalization",
        action="store_true",
        help="on --resume only, upgrade legacy binary evidence normalization with immutable audit sidecars",
    )
    longform.add_argument("--dry-run", action="store_true")
    longform.add_argument(
        "--plan-only",
        action="store_true",
        help="run only automatic route/module planning; inspect plan.json before resuming",
    )
    longform.add_argument("--timeout", type=float, default=600.0)
    longform.add_argument("--strict-ai", action="store_true", help="apply the stricter AI-output judge prefix")
    longform.add_argument(
        "--html-report",
        action="store_true",
        help="on completion, also write self-contained report.html and scorecard.html",
    )
    longform.set_defaults(func=_cmd_longform)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except HBQError as exc:
        parser.error(str(exc))
    return 2
