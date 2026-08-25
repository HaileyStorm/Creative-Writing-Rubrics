"""Regression contract for the three approved HBQ-RS wording promotions."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from hbqrs import core
from hbqrs.paths import book_root


BOOK = book_root()
S1_INSTRUCTION_BLOCK = (
    "Answer NOT_APPLICABLE when no recurrence is supplied or indicated, and CANNOT_ASSESS "
    "when recurrence is indicated but too few instances are supplied to judge its effect. "
    "Presence of recurrence alone does not satisfy this criterion. Answer YES only when "
    "sufficient supplied instances show that recurring words, phrases, or structures change "
    "pressure or meaning; when sufficient supplied instances recur without doing so, answer NO."
)
S1_ORIGINAL_QUESTION = "When words, phrases, or structures recur, does recurrence alter pressure or meaning?"
S1_TEXT = S1_INSTRUCTION_BLOCK + " " + S1_ORIGINAL_QUESTION
S1_CANDIDATE_SHA256 = "aca280986e71062b92f87e4c508856741a4b3e7ed69fc009061983091dd41a0a"
S2_TEXT = (
    "For a passage explicitly declared to be an excerpt or fragment, does the supplied evaluation "
    "avoid penalizing it for not being a complete work?"
)
FIGURATIVE_TEXT = (
    "Inspect linked material metaphors or images in the declared scope. Return YES when their implications are "
    "compatible and jointly clarify the supplied passage. If linked images carry opposing implications, return YES "
    "only when the artifact supplies an additional concrete semantic hinge that relates, reconciles, or distinguishes "
    "those implications, such as a demonstrated causal, temporal, role, perspective, or double-meaning relation. "
    "Punctuation, an explicit connective, or a bare assertion that images coexist is not itself that hinge. Sharing "
    "a subject, pairing opposite labels, or restating them with opposite verbs is not an additional hinge; the artifact "
    "must supply a relation beyond the coexistence itself. Return NO when opposing implications merely occur together "
    "without an additional artifact-grounded hinge. Do not judge familiarity/defaultness or figurative density; cite "
    "the linked spans and the compatibility or hinge, or the absence of one. Do metaphors and images cooperate rather "
    "than stack, mix, or compete?"
)


def _find_leaf(node: Any, leaf_id: str) -> dict[str, Any] | None:
    if isinstance(node, dict):
        if node.get("id") == leaf_id:
            return node
        for value in node.values():
            found = _find_leaf(value, leaf_id)
            if found is not None:
                return found
    if isinstance(node, list):
        for value in node:
            found = _find_leaf(value, leaf_id)
            if found is not None:
                return found
    return None


def _leaf(node: Any, leaf_id: str) -> dict[str, Any]:
    found = _find_leaf(node, leaf_id)
    assert found is not None, f"Missing leaf: {leaf_id}"
    return found


def _module(name: str) -> dict[str, Any]:
    value = core.load_data(BOOK / "registry" / "modules" / name)
    assert isinstance(value, dict)
    return value


def _assert_preserved_contract(module: dict[str, Any], leaf: dict[str, Any], *, module_id: str, leaf_id: str, version: int, text: str, weight: float, question_type: str) -> None:
    assert module["standard"] == {"id": "HBQ-RS", "version": "1.2.1"}
    assert module["module_id"] == module_id and module["version"] == version
    assert leaf["id"] == leaf_id and leaf["criterion_key"] == leaf_id and leaf["text"] == text
    assert leaf["pass_answer"] == "YES" and leaf["weight"] == weight
    assert leaf["question_type"] == question_type and leaf["severity"] == "material"
    assert leaf["applies_when"] == "The criterion is relevant to the requested artifact, scope, and operation."
    assert leaf["evidence_policy"] == {
        "required": True,
        "minimum_references": 1,
        "reference_style": "artifact span, unit ID, timestamp, or source ID",
    }
    assert leaf["tags"] == []


def test_approved_wording_promotions_preserve_leaf_identity_and_influence_contracts():
    s1 = _module("form.poetry.free_verse.yaml")
    s1_leaf = _leaf(s1, "form.poetry.free_verse.repetition")
    _assert_preserved_contract(s1, s1_leaf, module_id="form.poetry.free_verse", leaf_id="form.poetry.free_verse.repetition", version=3, text=S1_TEXT, weight=1.5, question_type="scored")
    assert s1_leaf["text"] == S1_INSTRUCTION_BLOCK + " " + S1_ORIGINAL_QUESTION
    assert s1_leaf["text"].count("?") == 1
    canonical_candidate = {
        "id": s1_leaf["id"],
        "module_id": s1["module_id"],
        "criterion_key": s1_leaf["criterion_key"],
        "text": s1_leaf["text"],
        "pass_answer": s1_leaf["pass_answer"],
        "weight": s1_leaf["weight"],
        "question_type": s1_leaf["question_type"],
        "severity": s1_leaf["severity"],
        "applies_when": s1_leaf["applies_when"],
        "evidence_policy": s1_leaf["evidence_policy"],
    }
    assert hashlib.sha256(json.dumps(canonical_candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() == S1_CANDIDATE_SHA256
    assert s1["owner_domains"] == ["form.free_verse"] and s1["artifact_types"] == ["poetry"]

    s2 = _module("scope.passage.yaml")
    _assert_preserved_contract(s2, _leaf(s2, "scope.passage.status"), module_id="scope.passage", leaf_id="scope.passage.status", version=2, text=S2_TEXT, weight=2.0, question_type="diagnostic")
    assert s2["modifier_actions"] == [{"action": "minimum_neighboring_units", "value": 1}]

    figurative = _module("penalty.purple_prose.yaml")
    _assert_preserved_contract(figurative, _leaf(figurative, "penalty.purple_prose.metaphor"), module_id="penalty.purple_prose", leaf_id="penalty.purple_prose.metaphor", version=2, text=FIGURATIVE_TEXT, weight=1.5, question_type="scored")
    assert figurative["owner_domains"] == ["penalty.purple_prose"]
    assert figurative["profile_overrides"]["caps"] == {"short_prose": 5, "long_prose": 5, "poetry": 4, "script": 4}


def test_rendered_rubric_book_carries_the_same_three_approved_texts_once_each():
    rendered = (BOOK / "docs" / "RUBRIC_BOOK.md").read_text(encoding="utf-8")
    for text in (S1_TEXT, S2_TEXT, FIGURATIVE_TEXT):
        assert rendered.count(text) == 1
