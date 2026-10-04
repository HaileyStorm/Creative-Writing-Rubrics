"""Offline semantic admission for the matched study; never invent missing votes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def semantic_validate(arm: str, response: Any, request: dict[str, Any],
                      source_texts: dict[str, str], subset: Any, context: str = "",
                      schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return structural acceptance, explicit abstention, and concrete errors.

    accepted=True with abstention=True is a valid inability-to-assess response,
    never an assessed score/tie. Partial criterion abstentions remain explicit.
    Source texts are keyed by request.sources[*].id; no targets are consulted.
    """
    errors: list[str] = []
    if schema is None:
        if arm == "hbq":
            return {"accepted": False, "abstention": False, "errors": ["HBQ emitted packet schema is required"]}
        schema = json.loads((HERE / "arms" / f"{arm}.schema.json").read_bytes())
    if not subset.matches_schema(response, schema):
        return {"accepted": False, "abstention": False, "errors": ["Response does not match frozen portable schema"]}
    sources = request.get("sources", [])
    if not sources or any(s["id"] not in source_texts for s in sources):
        return {"accepted": False, "abstention": False, "errors": ["Frozen source text unavailable"]}
    story_text = source_texts[sources[0]["id"]]
    abstention = False

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    def nonblank(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def quote(value: Any, text: str = story_text) -> None:
        require(nonblank(value) and value in text, "Evidence quote is not a nonblank contiguous source substring")

    def evidence(items: list[dict[str, Any]], minimum: int, maximum: int) -> None:
        require(minimum <= len(items) <= maximum, "Evidence item count differs")
        for item in items:
            quote(item["quote"])
            require(nonblank(item["explanation"]), "Evidence explanation is blank")

    if arm in {"holistic", "compact", "oregon"}:
        abstention = response["status"] == "CANNOT_ASSESS"
        if abstention:
            require(response["result"] is None and nonblank(response["abstention_reason"]),
                    "Abstention requires null result and nonblank reason")
        else:
            result = response["result"]
            require(isinstance(result, dict) and response["abstention_reason"] is None,
                    "Scored response requires complete result and null abstention reason")
            if isinstance(result, dict):
                if arm == "holistic":
                    evidence(result["evidence"], 2, 5)
                    require(2 <= len(result["strengths"]) <= 4 and len(result["limitations"]) <= 4,
                            "Holistic strengths/limitations count differs")
                    require(nonblank(result["rationale"]) and all(nonblank(s) for s in result["strengths"] + result["limitations"]),
                            "Holistic observation is blank")
                elif arm == "compact":
                    rows = result["dimensions"]
                    expected = set(schema["properties"]["result"]["properties"]["dimensions"]["items"]["properties"]["dimension_id"]["enum"])
                    require(len(rows) == 6 and {r["dimension_id"] for r in rows} == expected,
                            "Compact requires exactly six distinct dimensions")
                    require(nonblank(result["overall_rationale"]), "Compact overall rationale is blank")
                    for row in rows:
                        evidence(row["evidence"], 1, 3)
                        require(nonblank(row["rationale"]), "Compact rationale is blank")
                else:
                    rows = result["traits"]
                    expected = set(schema["properties"]["result"]["properties"]["traits"]["items"]["properties"]["trait_id"]["enum"])
                    require(len(rows) == 6 and {r["trait_id"] for r in rows} == expected, "Oregon requires six distinct traits")
                    require(result["total_score"] == sum(r["score"] for r in rows), "Oregon total is not exact trait sum")
                    require(nonblank(result["overall_note"]), "Oregon overall note is blank")
                    for row in rows:
                        quote(row["exact_quote"])
                        require(nonblank(row["observation"]), "Oregon observation is blank")
    elif arm == "ttcw14":
        rows = response["verdicts"]
        require(len(rows) == 14 and {r["test_id"] for r in rows} == {f"ttcw-{i:02d}" for i in range(1, 15)},
                "TTCW requires exactly fourteen distinct tests")
        abstention = any(r["verdict"] == "CANNOT_ASSESS" for r in rows)
        for row in rows:
            require(nonblank(row["observation"]), "TTCW observation is blank")
            if row["verdict"] == "CANNOT_ASSESS":
                require(nonblank(row["abstention_reason"]), "TTCW abstention reason is blank")
                evidence(row["evidence"], 0, 2)
            else:
                require(row["abstention_reason"] is None, "Assessed TTCW verdict cannot carry abstention reason")
                evidence(row["evidence"], 1, 2)
    elif arm == "pairwise":
        abstention = response["winner"] == "CANNOT_ASSESS"
        require(nonblank(response["tradeoff"]), "Pairwise tradeoff is blank")
        require(len(response["evidence"]) <= 6, "Too many pairwise evidence items")
        if abstention:
            require(nonblank(response["abstention_reason"]), "Pairwise abstention reason is blank")
        else:
            require(response["abstention_reason"] is None, "Assessed pair cannot carry abstention reason")
            require({e["side"] for e in response["evidence"]} == {"A", "B"}, "Assessed pair requires evidence from both stories")
        sides = {s.get("side"): source_texts[s["id"]] for s in sources}
        for item in response["evidence"]:
            quote(item["quote"], sides.get(item["side"], ""))
            require(nonblank(item["explanation"]), "Pairwise evidence explanation is blank")
    elif arm == "hbq":
        rows = response["verdicts"]
        ids = request["question_ids"]
        require(len(rows) == len(ids) and {r["question_id"] for r in rows} == set(ids),
                "HBQ packet requires each selected question exactly once")
        abstention = any(r["verdict"] == "CANNOT_ASSESS" for r in rows)
        for row in rows:
            if row["verdict"] in {"CANNOT_ASSESS", "NOT_APPLICABLE"}:
                require(nonblank(row["note"]), "HBQ abstention/N/A requires a nonblank explanation")
            for item in row["evidence"]:
                require(nonblank(item["reference"]), "HBQ evidence reference is blank")
                if item["kind"] == "exact_quote":
                    require(item["summary"] is None, "HBQ exact quote cannot carry summary")
                    require(nonblank(item["exact_quote"]) and (item["exact_quote"] in story_text or item["exact_quote"] in context),
                            "HBQ exact quote does not match artifact/context")
                else:
                    require(item["exact_quote"] is None and nonblank(item["summary"]), "HBQ summary evidence is malformed")
    else:
        errors.append("Unknown arm")
    return {"accepted": not errors, "abstention": abstention, "errors": errors}
