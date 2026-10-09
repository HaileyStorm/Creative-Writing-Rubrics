"""Versioned in-memory extension of the frozen matched-TTCW analyzer.

Call analyze with an already authorized/admitted analysis input. This adapter
opens only its pinned predecessor's code; it cannot establish target access or
native/scientific admission. Historical reader bindings and bytes are preserved.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import FunctionType

from measurement_diagnostics_v1 import leaf_repeat_transitions, scalar_extremes

PREDECESSOR_SHA = "c843cb8bfb54a3cc27955c911c1a8e5aa053d6a2f25a9f4dd3b67479fa22ae19"
POLICY = "matched_ttcw_measurement_extension_v1"


def analyze(base, manifest, targets, ballots, endpoints, hbq, reps=2000):
    """Compose existing scoring/statistics with added descriptive diagnostics."""
    if hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest() != PREDECESSOR_SHA:
        raise ValueError("Frozen analysis predecessor changed")
    hbq_ids = tuple(manifest["runtime"]["question_ids"])
    if len(hbq_ids) != 178 or len(set(hbq_ids)) != 178:
        raise ValueError("Frozen full HBQ inventory differs")

    def distribution(scores, arm):
        result = base.distribution(scores, arm)
        result["scalar_extremes_v1"] = scalar_extremes(scores.values(), base.RANGES[arm])
        return result

    def repeat_summary(arm, profiles, sentinel_ids):
        result = base.repeat_summary(arm, profiles, sentinel_ids)
        if arm in {"hbq", "ttcw14"}:
            ids = hbq_ids if arm == "hbq" else tuple(f"ttcw-{i:02d}" for i in range(1, 15))
            field = "question_id" if arm == "hbq" else "test_id"
            result["four_state_transitions_v1"] = leaf_repeat_transitions(profiles, sentinel_ids, ids, field)
        return result

    # A private globals mapping changes only these two bindings. No mutation of
    # the loaded historical module, scorer, admission path or shared functions.
    namespace = {**base.analyze.__globals__, "distribution": distribution, "repeat_summary": repeat_summary}
    composed = FunctionType(base.analyze.__code__, namespace, base.analyze.__name__, base.analyze.__defaults__, base.analyze.__closure__)
    result = composed(manifest, targets, ballots, endpoints, hbq, reps)
    for endpoint in result.values():
        endpoint["measurement_extension"] = {"policy": POLICY, "predecessor_sha256": PREDECESSOR_SHA,
                                             "descriptive_only": True, "native_admission_established": False,
                                             "target_access_authorized": False, "promotion_established": False}
    return result
