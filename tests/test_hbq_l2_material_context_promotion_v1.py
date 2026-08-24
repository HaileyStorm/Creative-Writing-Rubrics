from __future__ import annotations

import json

import yaml

from hbqrs.paths import book_root


LEAF_ID = "form.poetry.free_verse.line_breaks"
TEXT = (
    "Does each supplied line break materially strengthen its immediate poetic context through rhythm, syntax, "
    "emphasis, image, ambiguity, or pace, beyond merely creating a detectable pause, syntactic interruption, or "
    "repeated pattern?"
)


def test_material_context_promotion_preserves_leaf_contract_and_packed_parity():
    root = book_root()
    source = yaml.safe_load(
        (root / "registry" / "modules" / "form.poetry.free_verse.yaml").read_text(encoding="utf-8")
    )
    packed = json.loads((root / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    aggregate = next(module for module in packed if module["module_id"] == source["module_id"])
    leaf = next(
        child
        for group in source["tree"]
        for child in group["children"]
        if child["id"] == LEAF_ID
    )
    ownership = json.loads((root / "registry" / "criterion_ownership.json").read_text(encoding="utf-8"))

    assert source["standard"] == {"id": "HBQ-RS", "version": "1.2.0"}
    assert source["version"] == 2
    assert aggregate == source
    assert leaf == {
        "id": LEAF_ID,
        "type": "question",
        "criterion_key": LEAF_ID,
        "text": TEXT,
        "pass_answer": "YES",
        "weight": 2.0,
        "question_type": "scored",
        "severity": "material",
        "applies_when": "The criterion is relevant to the requested artifact, scope, and operation.",
        "evidence_policy": {
            "required": True,
            "minimum_references": 1,
            "reference_style": "artifact span, unit ID, timestamp, or source ID",
        },
        "tags": [],
    }
    assert ownership[LEAF_ID] == {
        "module_id": "form.poetry.free_verse",
        "question_id": LEAF_ID,
    }
