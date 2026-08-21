"""Thin manifest runner for repeatable long-form HBQ-RS batches."""

from __future__ import annotations

from copy import deepcopy
from html import escape
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from jsonschema import Draft202012Validator

from .core import HBQError, load_bundles, load_data, load_modules, resolve_bundle
from .html_report import render_html_report, render_html_scorecard
from .longform_runner import _derive_bundle, run_longform_judge
from .paths import schema_dir
from .runner import run_judge


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_or_verify_json(path: Path, value: Any) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.is_file():
        if path.read_text(encoding="utf-8") != content:
            raise HBQError(f"Persisted batch artifact changed: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _resolve(base: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def _load_mapping(path: Path | None, label: str) -> dict[str, Any] | None:
    if path is None:
        return None
    value = load_data(path)
    if not isinstance(value, dict):
        raise HBQError(f"{label} must be a JSON or YAML object: {path}")
    return value


def validate_batch_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    errors = sorted(
        Draft202012Validator(load_data(schema_dir() / "hbq_batch.schema.json")).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        path = ".".join(str(part) for part in errors[0].path) or "<root>"
        raise HBQError(f"Batch manifest violates its strict schema at {path}: {errors[0].message}")
    result = deepcopy(dict(value))
    jobs = result["jobs"]
    job_ids = [job["job_id"] for job in jobs]
    if len(job_ids) != len(set(job_ids)):
        raise HBQError("Batch job_id values must be unique")
    if result["routing_policy"] == "shared" and result["shared_route_source_job_id"] not in job_ids:
        raise HBQError("shared_route_source_job_id must name a job in the manifest")
    for job in jobs:
        approved_bundle = job.get("approved_bundle_id")
        approved_modules = job.get("approved_module_ids")
        if (approved_bundle is None) != (approved_modules is None):
            raise HBQError(f"Job {job['job_id']} must provide approved_bundle_id and approved_module_ids together")
        if approved_bundle is not None and result["routing_policy"] != "review":
            raise HBQError("Approved per-job stacks apply only to the review routing policy")
        workflow = job.get("workflow", result["defaults"].get("workflow", "longform"))
        html_report = job.get("html_report", result["defaults"].get("html_report", False))
        if workflow == "single" and html_report:
            raise HBQError(
                f"Job {job['job_id']} requests long-form HTML for a single workflow; "
                "set html_report to false or use workflow: longform"
            )
    return result


def _status_html(state: Mapping[str, Any]) -> str:
    rows = "".join(
        "<tr><th scope=\"row\">{}</th><td>{}</td><td>{}</td></tr>".format(
            escape(str(job["job_id"])), escape(str(job["status"])), escape(str(job.get("detail", "")))
        )
        for job in state["jobs"]
    )
    return f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta http-equiv=\"refresh\" content=\"10\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>HBQ-RS batch status</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:70rem;margin:auto;padding:1rem;color:#172033}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.55rem;border-bottom:1px solid #cad2de;text-align:left}}.note{{color:#546177}}</style></head><body><main><h1>HBQ-RS batch status</h1><p><strong>{escape(str(state['batch_id']))}</strong> · {escape(str(state['routing_policy']))}</p><p class=\"note\">This local page refreshes every 10 seconds. The CLI remains the source of execution and can be stopped or resumed independently.</p><table><thead><tr><th>Job</th><th>Status</th><th>Detail</th></tr></thead><tbody>{rows}</tbody></table></main></body></html>"""


def _write_state(output_root: Path, state: Mapping[str, Any]) -> None:
    _atomic_json(output_root / "batch.json", state)
    (output_root / "batch-status.html").write_text(_status_html(state), encoding="utf-8")


def _job_kwargs(
    *, job: Mapping[str, Any], defaults: Mapping[str, Any], base: Path, output_dir: Path,
    registry: str | Path, bundles: str | Path, allow_remote: bool, resume: bool,
    plan_only: bool, bundle_id: str | None = None, module_ids: Sequence[str] = (),
    task_contract_path: Path | None = None,
    sampling_plan_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    driving_path = _resolve(base, job.get("driving_prompt_file"))
    return {
        "artifact_path": _resolve(base, job["artifact"]),
        "brief_paths": [_resolve(base, path) for path in job.get("brief_paths", [])],
        "output_dir": output_dir,
        "provider": defaults["provider"], "model": defaults["model"],
        "registry": registry, "bundles": bundles,
        "artifact_kind": job.get("artifact_kind", defaults["artifact_kind"]),
        "declared_scope": job.get("declared_scope", defaults["declared_scope"]),
        "completion_status": job.get("completion_status", defaults["completion_status"]),
        "artifact_id": job.get("artifact_id"),
        "driving_prompt": driving_path.read_text(encoding="utf-8-sig") if driving_path else "",
        "bundle_id": bundle_id, "module_ids": list(module_ids),
        "task_contract_path": task_contract_path or _resolve(base, defaults.get("task_contract_path")),
        "weight_profile": _load_mapping(_resolve(base, defaults.get("weight_profile_path")), "Weight profile"),
        "local_weight_profile": _load_mapping(_resolve(base, defaults.get("local_weight_profile_path")), "Local weight profile"),
        "hierarchical_score_profile": _load_mapping(_resolve(base, defaults.get("hierarchical_score_profile_path")), "Hierarchical score profile"),
        "local_bundle_id": defaults.get("local_bundle_id"),
        "route_sample_char_limit": defaults.get("route_sample_char_limit", 12000),
        "local_sample_limit": defaults.get("local_sample_limit"),
        "sampling_plan_override": deepcopy(sampling_plan_override),
        "binary_workers": defaults.get("binary_workers", 1),
        "batch_size": defaults.get("batch_size", 12),
        "batch_attempts": defaults.get("batch_attempts", 3),
        "base_url": defaults.get("base_url", "http://127.0.0.1:8000/v1"),
        "api_key_env": defaults.get("api_key_env", "OPENAI_API_KEY"),
        "temperature": defaults.get("temperature"),
        "allow_model_mismatch": defaults.get("allow_model_mismatch", False),
        "openai_structured_outputs": defaults.get("openai_structured_outputs", False),
        "structured_reasoning": defaults.get("structured_reasoning", "high"),
        "judge_reasoning": defaults.get("judge_reasoning", "medium"),
        "codex_bin": defaults.get("codex_bin", "codex"),
        "grok_bin": defaults.get("grok_bin", "grok"),
        "allow_unattested_reasoning": defaults.get("allow_unattested_reasoning", False),
        "allow_remote": allow_remote, "resume": resume, "plan_only": plan_only,
        "timeout": defaults.get("timeout", 600.0), "strict_ai": defaults.get("strict_ai", False),
    }


def _route_job(
    *, job: Mapping[str, Any], defaults: Mapping[str, Any], base: Path, output_dir: Path,
    registry: str | Path, bundles: str | Path, allow_remote: bool, resume: bool,
    bundle_id: str | None = None, module_ids: Sequence[str] = (),
    task_contract_path: Path | None = None,
    sampling_plan_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return run_longform_judge(
        **_job_kwargs(
            job=job, defaults=defaults, base=base, output_dir=output_dir,
            registry=registry, bundles=bundles, allow_remote=allow_remote,
            resume=resume, plan_only=True, bundle_id=bundle_id, module_ids=module_ids,
            task_contract_path=task_contract_path,
            sampling_plan_override=sampling_plan_override,
        )
    )


def _assert_review_scope_preserved(
    original: Mapping[str, Any], approved: Mapping[str, Any], *, job_id: str
) -> None:
    for field in ("task_contract", "sampling_plan"):
        if approved.get(field) != original.get(field):
            raise HBQError(
                f"Approved stack changed the reviewed {field} for job {job_id}; "
                "create and inspect a new plan instead"
            )


def _run_single_job(
    *, job: Mapping[str, Any], defaults: Mapping[str, Any], base: Path, output_dir: Path,
    support_dir: Path,
    route_plan: Mapping[str, Any], registry: str | Path, bundles: str | Path,
    allow_remote: bool, resume: bool,
) -> dict[str, Any]:
    """Grade one exact artifact once using an LLM-routed, frozen derived bundle."""

    selected_bundle_id = str(route_plan["selected_bundle_id"])
    selected_module_ids = list(route_plan["selected_module_ids"])
    modules = load_modules(registry)
    selected_bundle = resolve_bundle(load_bundles(bundles), selected_bundle_id)
    derived_bundle = _derive_bundle(selected_bundle, selected_module_ids)
    catalog_dir = support_dir / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    registry_path = catalog_dir / "registry.json"
    bundles_path = catalog_dir / "bundles.json"
    contract_path = support_dir / "task-contract.json"
    contract = _load_mapping(
        _resolve(base, defaults.get("task_contract_path")), "Task contract"
    ) or route_plan["task_contract"]
    _write_or_verify_json(registry_path, {"modules": modules})
    _write_or_verify_json(bundles_path, {"bundles": [derived_bundle]})
    _write_or_verify_json(contract_path, contract)
    contexts = [_resolve(base, path) for path in job.get("brief_paths", [])]
    driving_path = _resolve(base, job.get("driving_prompt_file"))
    if driving_path is not None:
        contexts.append(driving_path)
    return run_judge(
        artifact_path=_resolve(base, job["artifact"]),
        bundle_id=selected_bundle_id,
        provider=defaults["provider"], model=defaults["model"], output_dir=output_dir,
        registry=registry_path, bundles=bundles_path, context_paths=contexts,
        task_contract_path=contract_path,
        weight_profile=_load_mapping(_resolve(base, defaults.get("weight_profile_path")), "Weight profile"),
        batch_size=defaults.get("batch_size", 12),
        batch_attempts=defaults.get("batch_attempts", 3),
        base_url=defaults.get("base_url", "http://127.0.0.1:8000/v1"),
        api_key_env=defaults.get("api_key_env", "OPENAI_API_KEY"),
        temperature=defaults.get("temperature"),
        allow_model_mismatch=defaults.get("allow_model_mismatch", False),
        reasoning=defaults.get("judge_reasoning", "medium"),
        codex_bin=defaults.get("codex_bin", "codex"),
        grok_bin=defaults.get("grok_bin", "grok"),
        allow_unattested_reasoning=defaults.get("allow_unattested_reasoning", False),
        allow_remote=allow_remote, resume=resume,
        timeout=defaults.get("timeout", 600.0), artifact_id=job.get("artifact_id"),
        strict_ai=defaults.get("strict_ai", False),
    )


def _render_completed_html(output_dir: Path) -> None:
    report = load_data(output_dir / "report.json")
    if not isinstance(report, dict):
        raise HBQError(f"Completed batch job lacks an object report: {output_dir}")
    (output_dir / "report.html").write_text(render_html_report(report), encoding="utf-8")
    (output_dir / "scorecard.html").write_text(render_html_scorecard(report), encoding="utf-8")


def _load_valid_plan(
    path: Path, *, job: Mapping[str, Any], registry: str | Path, bundles: str | Path
) -> dict[str, Any]:
    if not path.is_file():
        raise HBQError(f"Batch has no persisted plan for job {job['job_id']}: {path}")
    plan = load_data(path)
    if not isinstance(plan, dict):
        raise HBQError(f"Persisted plan is not an object for job {job['job_id']}")
    expected_artifact_id = job.get("artifact_id") or Path(job["artifact"]).stem
    if plan.get("artifact_id") != expected_artifact_id:
        raise HBQError(f"Persisted plan artifact_id changed for job {job['job_id']}")
    bundle_id = plan.get("selected_bundle_id")
    module_ids = plan.get("selected_module_ids")
    if not isinstance(bundle_id, str) or not isinstance(module_ids, list):
        raise HBQError(f"Persisted plan lacks a frozen stack for job {job['job_id']}")
    selected_bundle = resolve_bundle(load_bundles(bundles), bundle_id)
    _derive_bundle(selected_bundle, module_ids)
    contract = plan.get("task_contract")
    if not isinstance(contract, dict) or contract.get("artifact_id") != expected_artifact_id:
        raise HBQError(f"Persisted plan task contract changed for job {job['job_id']}")
    return plan


def run_longform_batch(
    manifest_path: str | Path, *, registry: str | Path, bundles: str | Path,
    allow_remote: bool = False, resume: bool = False, accept_reviewed: bool = False,
) -> dict[str, Any]:
    """Run a strict long-form batch manifest through one of three routing policies.

    ``individual`` lets the configured LLM route and grade each sample without
    confirmation. ``shared`` routes one designated sample, freezes that stack,
    and applies it to all jobs. ``review`` routes every sample ahead of time and
    stops; ``accept_reviewed`` later grades using each accepted or overridden
    frozen stack.
    """

    manifest_file = Path(manifest_path).resolve()
    raw = load_data(manifest_file)
    if not isinstance(raw, dict):
        raise HBQError("Batch manifest must be a JSON or YAML object")
    manifest = validate_batch_manifest(raw)
    base = manifest_file.parent
    defaults = manifest["defaults"]
    output_root = _resolve(base, defaults["output_root"])
    assert output_root is not None
    output_root = output_root.resolve()
    if manifest_file.is_relative_to(output_root):
        raise HBQError(
            "Batch output_root must not contain the manifest; choose a separate output directory"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    jobs = manifest["jobs"]
    if accept_reviewed and manifest["routing_policy"] != "review":
        raise HBQError("--accept-reviewed applies only to a review-policy batch")
    prior_state_path = output_root / "batch.json"
    prior_state = load_data(prior_state_path) if prior_state_path.is_file() else None
    if prior_state is not None and not isinstance(prior_state, dict):
        raise HBQError("Existing batch.json must contain an object")
    if isinstance(prior_state, dict) and (
        prior_state.get("format_version") != 1
        or prior_state.get("batch_id") != manifest["batch_id"]
        or prior_state.get("routing_policy") != manifest["routing_policy"]
    ):
        raise HBQError("Existing batch.json does not belong to this batch manifest")
    if prior_state is not None and not (resume or accept_reviewed):
        raise HBQError(f"Batch output already exists at {output_root}; pass --resume")
    state: dict[str, Any] = {
        "format_version": 1, "batch_id": manifest["batch_id"],
        "routing_policy": manifest["routing_policy"],
        "phase": "review_execution" if accept_reviewed else "running",
        "previous_phase": prior_state.get("phase") if isinstance(prior_state, dict) else None,
        "jobs": [{"job_id": job["job_id"], "status": "PENDING", "detail": ""} for job in jobs],
    }
    _write_state(output_root, state)

    def set_status(job_id: str, status: str, detail: str = "") -> None:
        record = next(item for item in state["jobs"] if item["job_id"] == job_id)
        record.update(status=status, detail=detail)
        _write_state(output_root, state)

    frozen: tuple[str, list[str]] | None = None
    prepared: dict[str, dict[str, Any]] = {}
    policy = manifest["routing_policy"]
    if policy == "shared":
        source = next(job for job in jobs if job["job_id"] == manifest["shared_route_source_job_id"])
        route_dir = output_root / "shared-route"
        route_summary = _route_job(
            job=source, defaults=defaults, base=base, output_dir=route_dir,
            registry=registry, bundles=bundles, allow_remote=allow_remote, resume=resume,
        )
        frozen = (str(route_summary["selected_bundle_id"]), list(route_summary["selected_module_ids"]))

    if policy == "review" and not accept_reviewed:
        for job in jobs:
            set_status(job["job_id"], "ROUTING", "LLM route selection in progress")
            plan_dir = output_root / "plans" / job["job_id"]
            summary = _route_job(
                job=job, defaults=defaults, base=base, output_dir=plan_dir,
                registry=registry, bundles=bundles, allow_remote=allow_remote, resume=resume,
            )
            set_status(job["job_id"], "PLANNED", f"{summary['selected_bundle_id']} ({len(summary['selected_module_ids'])} modules)")
        state["phase"] = "awaiting_review"
        _write_state(output_root, state)
        return state

    if policy == "review":
        # Validate every accepted input/config/checkpoint before any grading starts.
        for job in jobs:
            job_id = job["job_id"]
            original_dir = output_root / "plans" / job_id
            _route_job(
                job=job, defaults=defaults, base=base, output_dir=original_dir,
                registry=registry, bundles=bundles, allow_remote=allow_remote, resume=True,
            )
            original = _load_valid_plan(
                original_dir / "plan.json", job=job, registry=registry, bundles=bundles
            )
            override = "approved_bundle_id" in job
            selected = (
                str(job.get("approved_bundle_id", original["selected_bundle_id"])),
                list(job.get("approved_module_ids", original["selected_module_ids"])),
            )
            plan_dir = original_dir
            plan = original
            route_selection: tuple[str | None, Sequence[str]] = (None, ())
            if override:
                plan_dir = output_root / "approved-plans" / job_id
                support_dir = output_root / ".private" / "approved-plans" / job_id
                contract_path = support_dir / "task-contract.json"
                _write_or_verify_json(contract_path, original["task_contract"])
                _route_job(
                    job=job, defaults=defaults, base=base, output_dir=plan_dir,
                    registry=registry, bundles=bundles, allow_remote=allow_remote,
                    resume=plan_dir.exists(), bundle_id=selected[0], module_ids=selected[1],
                    task_contract_path=contract_path,
                    sampling_plan_override=original["sampling_plan"],
                )
                plan = _load_valid_plan(
                    plan_dir / "plan.json", job=job, registry=registry, bundles=bundles
                )
                _assert_review_scope_preserved(original, plan, job_id=job_id)
                route_selection = selected
            prepared[job_id] = {
                "plan_dir": plan_dir, "plan": plan,
                "route_selection": route_selection,
                "task_contract_path": contract_path if override else None,
                "sampling_plan_override": original["sampling_plan"] if override else None,
            }

    if policy == "shared":
        # Freeze one stack, then finish every artifact-specific plan before grading any job.
        assert frozen is not None
        for job in jobs:
            job_id = job["job_id"]
            plan_dir = output_root / "shared-plans" / job_id
            _route_job(
                job=job, defaults=defaults, base=base, output_dir=plan_dir,
                registry=registry, bundles=bundles, allow_remote=allow_remote,
                resume=resume, bundle_id=frozen[0], module_ids=frozen[1],
            )
            prepared[job_id] = {
                "plan_dir": plan_dir,
                "plan": _load_valid_plan(
                    plan_dir / "plan.json", job=job, registry=registry, bundles=bundles
                ),
                "route_selection": frozen,
            }

    for job in jobs:
        job_id = job["job_id"]
        selection = prepared.get(job_id, {}).get("route_selection")
        set_status(job_id, "RUNNING", "grading")
        try:
            job_output = output_root / "jobs" / job_id
            workflow = job.get("workflow", defaults.get("workflow", "longform"))
            if workflow == "single":
                if policy in {"review", "shared"}:
                    route_plan = prepared[job_id]["plan"]
                else:
                    route_dir = output_root / "routes" / job_id
                    _route_job(
                        job=job, defaults=defaults, base=base, output_dir=route_dir,
                        registry=registry, bundles=bundles, allow_remote=allow_remote, resume=resume,
                    )
                    route_plan = load_data(route_dir / "plan.json")
                if not isinstance(route_plan, dict):
                    raise HBQError(f"Route plan is not an object for job {job_id}")
                summary = _run_single_job(
                    job=job, defaults=defaults, base=base, output_dir=job_output,
                    support_dir=output_root / ".private" / "single" / job_id,
                    route_plan=route_plan, registry=registry, bundles=bundles,
                    allow_remote=allow_remote, resume=resume,
                )
            else:
                output_dir = (
                    prepared[job_id]["plan_dir"] if policy in {"review", "shared"} else job_output
                )
                summary = run_longform_judge(
                    **_job_kwargs(
                        job=job, defaults=defaults, base=base, output_dir=output_dir,
                        registry=registry, bundles=bundles, allow_remote=allow_remote,
                        resume=True if policy in {"review", "shared"} else resume,
                        plan_only=False,
                        bundle_id=selection[0] if selection else None,
                        module_ids=selection[1] if selection else (),
                        task_contract_path=prepared.get(job_id, {}).get("task_contract_path"),
                        sampling_plan_override=prepared.get(job_id, {}).get(
                            "sampling_plan_override"
                        ),
                    )
                )
            if job.get("html_report", defaults.get("html_report", False)) and workflow == "longform":
                if (output_dir / "report.json").is_file():
                    _render_completed_html(output_dir)
            set_status(job_id, str(summary.get("status", "COMPLETE")), "complete")
        except Exception as exc:
            set_status(job_id, "FAILED", str(exc))
            raise
    state["phase"] = "complete"
    _write_state(output_root, state)
    return state
