"""Command-line interface for HBQ-RS compile, score, export, and judge rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

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
    score_bundle,
    validate_registry,
    walk_tree,
    write_data,
)
from .pack import pack_book
from .paths import book_root, bundles_path, prompts_dir, registry_path, schema_dir
from .runner import run_judge


def _load_registry(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return load_modules(args.registry), load_bundles(args.bundles)


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
    packet = compile_bundle(modules, resolve_bundle(bundles, args.bundle_id))
    write_data(args.output, packet, fmt=args.format)
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    modules, bundles = _load_registry(args)
    report = score_bundle(
        modules,
        resolve_bundle(bundles, args.bundle_id),
        load_verdicts(args.verdicts),
        artifact_id=args.artifact_id,
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
    compiled = compile_bundle(modules, resolve_bundle(bundles, args.bundle_id))
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
    summary = run_judge(
        artifact_path=args.artifact,
        bundle_id=args.bundle_id,
        provider=args.provider,
        model=args.model,
        output_dir=args.output_dir,
        registry=args.registry,
        bundles=args.bundles,
        context_paths=args.context,
        question_ids=args.question_id,
        batch_size=args.batch_size,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        temperature=args.temperature,
        allow_model_mismatch=args.allow_model_mismatch,
        reasoning=args.reasoning,
        codex_bin=args.codex_bin,
        allow_remote=args.allow_remote,
        resume=args.resume,
        dry_run=args.dry_run,
        timeout=args.timeout,
        artifact_id=args.artifact_id,
        judge_id=args.judge_id,
        strict_ai=args.strict_ai,
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
    compile_parser.add_argument("-o", "--output")
    compile_parser.add_argument("--format", choices=["json", "yaml"], default="json")
    compile_parser.set_defaults(func=_cmd_compile)

    score = subparsers.add_parser("score", help="aggregate verdicts under one bundle")
    score.add_argument("bundle_id")
    score.add_argument("verdicts", help="verdict JSON/JSONL/YAML")
    score.add_argument("--artifact-id")
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
    render.add_argument("-o", "--output")
    render.set_defaults(func=_cmd_render_judge)

    pack = subparsers.add_parser("pack", help="rebuild aggregate JSON/YAML/JSONL from per-file YAML")
    pack.add_argument("--root", default=str(root))
    pack.add_argument("-o", "--output")
    pack.add_argument("--format", choices=["json", "yaml"], default="json")
    pack.set_defaults(func=_cmd_pack)

    judge = subparsers.add_parser(
        "judge",
        help="run a bundle through an OpenAI-compatible endpoint or Codex CLI, then score it",
    )
    judge.add_argument("artifact", help="UTF-8 text artifact to evaluate")
    judge.add_argument("--bundle", dest="bundle_id", required=True)
    judge.add_argument("--provider", choices=["openai", "codex"], required=True)
    judge.add_argument("--model", required=True)
    judge.add_argument("--output-dir", required=True, help="new run directory, or an existing run with --resume")
    judge.add_argument("--context", action="append", default=[], help="additional UTF-8 brief/canon file; repeatable")
    judge.add_argument("--question-id", action="append", default=[], help="limit to a selected leaf; repeatable")
    judge.add_argument("--batch-size", type=int, default=12)
    judge.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    judge.add_argument("--api-key-env", default="OPENAI_API_KEY")
    judge.add_argument("--temperature", type=float)
    judge.add_argument("--allow-model-mismatch", action="store_true")
    judge.add_argument("--reasoning", choices=["low", "medium", "high", "xhigh", "max"], default="medium")
    judge.add_argument("--codex-bin", default="codex")
    judge.add_argument("--allow-remote", action="store_true")
    judge.add_argument("--resume", action="store_true")
    judge.add_argument("--dry-run", action="store_true")
    judge.add_argument("--timeout", type=float, default=600.0)
    judge.add_argument("--artifact-id")
    judge.add_argument("--judge-id")
    judge.add_argument("--strict-ai", action="store_true", help="apply the stricter AI-output judge prefix")
    judge.set_defaults(func=_cmd_judge)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except HBQError as exc:
        parser.error(str(exc))
    return 2
