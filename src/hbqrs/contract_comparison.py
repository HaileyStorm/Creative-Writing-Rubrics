"""Opt-in interval comparison for artifact-bound copies of one task contract.

Report and contract commitments establish local self-consistency, not authentic
provenance. The caller separately attests the shared frozen comparison context.
This API neither rescores inputs nor changes the standard comparator's defaults.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from . import decision_readiness, ladder_uncertainty
from .core import HBQError
from .repeatability import canonical_json_sha256


POLICY = "artifact_bound_contract_comparison_v1"
_CONTEXT_KEYS = frozenset({
    "aggregation_policy", "compiled_bundle_sha256", "task_contract_sha256",
    "scoring_context_sha256",
})


def _validate(
    report: Mapping[str, Any], contract: Mapping[str, Any],
) -> tuple[str, str]:
    if not isinstance(report, Mapping) or not isinstance(contract, Mapping):
        raise HBQError("report and contract must be objects")
    if report.get("scoring_policy") != ladder_uncertainty.POLICY:
        raise HBQError("contract comparison supports uncertainty_preserving_ladder_v1 reports only")
    artifact_id = report.get("artifact_id")
    if (not isinstance(artifact_id, str) or not artifact_id.strip()
            or contract.get("artifact_id") != artifact_id):
        raise HBQError("contract must bind the report artifact identity")
    context = report.get("scoring_context")
    if not isinstance(context, Mapping) or set(context) != _CONTEXT_KEYS:
        raise HBQError("unsupported scoring context")
    if context["aggregation_policy"] != "historical_v1":
        raise HBQError("unsupported aggregation policy")
    compiled = context["compiled_bundle_sha256"]
    if not isinstance(compiled, str) or not re.fullmatch(r"[0-9a-f]{64}", compiled):
        raise HBQError("invalid compiled bundle commitment")
    if context["task_contract_sha256"] != canonical_json_sha256(contract):
        raise HBQError("full task contract does not match the report commitment")
    commitment = {
        "scoring_policy": report["scoring_policy"],
        **{key: context[key] for key in _CONTEXT_KEYS if key != "scoring_context_sha256"},
    }
    if context["scoring_context_sha256"] != canonical_json_sha256(commitment):
        raise HBQError("scoring context commitment does not match its fields")
    semantics = dict(contract)
    del semantics["artifact_id"]
    return canonical_json_sha256(semantics), compiled


def compare(
    left: Mapping[str, Any], right: Mapping[str, Any], *,
    left_contract: Mapping[str, Any], right_contract: Mapping[str, Any],
    comparison_context_sha256: str,
) -> dict[str, Any]:
    """Compare two reports whose full contracts differ only in artifact_id.

    Supports ``uncertainty_preserving_ladder_v1`` with ``historical_v1``
    aggregation. Each full contract must match its own report's commitment;
    compiled bundle commitments and all remaining contract content must match.
    The shared context digest is the caller's attestation, not verified proof
    of common judge, prompts, source versions or report lineage.

    Projection is confined to copies passed to the standard interval comparator.
    Its eligibility, applicability, visible-structure and interval rules remain
    active. Inputs are trusted local reports; this does not recompute scores or
    authenticate evidence. Inconsistent or unsupported commitments raise
    HBQError; non-JSON or nonfinite commitment inputs can raise
    repeatability.RepeatabilityContractError. Both are ValueError subclasses.
    """
    if (not isinstance(comparison_context_sha256, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", comparison_context_sha256)):
        raise HBQError("caller must provide a shared-context SHA-256 attestation")
    left_semantics, left_compiled = _validate(left, left_contract)
    right_semantics, right_compiled = _validate(right, right_contract)
    if left_semantics != right_semantics or left_compiled != right_compiled:
        raise HBQError("contract semantics or compiled bundle commitments differ")
    a, b = deepcopy(left), deepcopy(right)
    for report in (a, b):
        report["scoring_context"] = {
            "comparison_projection_policy": POLICY,
            "semantic_contract_sha256": left_semantics,
            "compiled_bundle_sha256": left_compiled,
        }
    outcome = decision_readiness.interval_comparison(
        a, b, comparison_context_sha256=comparison_context_sha256,
    )
    return {
        "policy": POLICY,
        "comparison": outcome,
        "semantic_contract_sha256": left_semantics,
        "original_report_sha256": [canonical_json_sha256(left), canonical_json_sha256(right)],
        "original_contract_sha256": [canonical_json_sha256(left_contract), canonical_json_sha256(right_contract)],
        "limitations": (
            "Local report and contract commitments are self-consistency checks, not authenticated "
            "provenance. The caller-supplied context digest is not independently verified. "
            "Legacy interval caveats still apply; no universal envelope or human validity is established."
        ),
    }
