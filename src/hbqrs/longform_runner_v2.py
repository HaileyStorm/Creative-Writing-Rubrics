"""Current long-form entry point that adds v2 score descendants without changing v1 workflow evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import core
from .longform_runner import run_longform_judge as run_longform_judge_v1
from .runner_v2 import persist_v2_descendant


def run_longform_judge(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the frozen v1 workflow and persist v2 descendants for completed binary scopes."""

    summary = run_longform_judge_v1(*args, **kwargs)
    destination = Path(kwargs["output_dir"]).resolve()
    private = destination / ".private"
    runtime_bundles = private / "catalog" / "bundles.json"
    registry = kwargs["registry"]
    descendants: list[str] = []
    if runtime_bundles.is_file():
        for parent in sorted((private / "evaluations").glob("*/score.json")):
            scope = parent.parent.name
            contract = private / "generated-inputs" / "contracts" / (
                "work.json" if scope == "global" else f"{scope}.json"
            )
            descendant = persist_v2_descendant(
                output_dir=parent.parent,
                registry=registry,
                bundles=runtime_bundles,
                weight_profile=(
                    kwargs.get("weight_profile")
                    if scope == "global"
                    else kwargs.get("local_weight_profile")
                ),
                task_contract_path=contract if contract.is_file() else None,
            )
            if descendant is not None:
                descendants.append(str(descendant))
    if not descendants:
        return summary
    return {**summary, "score_report_version": 2, "score_v2_descendants": descendants}
