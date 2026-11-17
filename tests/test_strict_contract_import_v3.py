"""The new policy validates contracts without changing historical imports."""
from copy import deepcopy

import pytest

from hbqrs import core, scoring_completion_envelope, scoring_v2


def test_contract_schema_is_versioned_and_checked_before_compilation(modules, bundles, monkeypatch):
    bundle = core.resolve_bundle(bundles, "prose.scene")
    contract = {
        "contract_version": 1, "contract_id": "synthetic", "artifact_id": "synthetic",
        "context": {"artifact_kind": "prose", "declared_scope": "scene", "completion_status": "excerpt",
                    "background": [], "constraints": [], "audience": []},
        "preferences": [], "priorities": [], "binding_requirements": [],
        "weighted_goals": [{"goal_id": "goal", "atomic_question": "Does it satisfy the goal?", "weight": 1,
                            "source": {"kind": "driving_prompt", "reference": "synthetic", "exact_excerpt": "Goal"},
                            "applies_to": ["scene"], "rationale": "Synthetic goal"}],
    }
    valid = scoring_v2.validate_import_admission(modules, bundle, [], artifact_id="synthetic",
                                                 task_contract=contract, admission_policy="strict_import_v3")
    assert valid["policy"] == "strict_import_v3"
    assert len(valid["task_contract_schema_sha256"]) == 64
    for bad_weight in (True, "1"):
        malformed = deepcopy(contract)
        malformed["weighted_goals"][0]["weight"] = bad_weight
        # The older policy is kept for historical direct-import compatibility.
        assert scoring_v2.validate_import_admission(modules, bundle, [], artifact_id="synthetic",
                                                    task_contract=malformed, admission_policy="strict_import_v2")
        with monkeypatch.context() as patch:
            patch.setattr(core, "compile_bundle", lambda *a, **k: pytest.fail("invalid contract reached compilation"))
            for fn in (scoring_v2.score_bundle, scoring_completion_envelope.completion_envelope):
                with pytest.raises(core.HBQError, match=r"weighted_goals\.0\.weight"):
                    fn(modules, bundle, [], artifact_id="synthetic", task_contract=malformed,
                       admission_policy="strict_import_v3")
