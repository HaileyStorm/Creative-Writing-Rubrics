"""Offline admission for the named MFA excerpt-quality arms."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def semantic_validate(arm, response, request, source_texts, subset, context="", schema=None):
    errors = []
    if schema is None:
        if arm == "hbq":
            return {"accepted": False, "abstention": False, "errors": ["Frozen HBQ packet schema required"]}
        schema = json.loads((HERE / "arms" / f"{arm}.schema.json").read_bytes())
    if not subset.matches_schema(response, schema):
        return {"accepted": False, "abstention": False, "errors": ["Response violates frozen schema"]}
    sources = request.get("sources", [])
    if not sources or any(s["id"] not in source_texts for s in sources):
        return {"accepted": False, "abstention": False, "errors": ["Committed excerpt unavailable"]}
    text = source_texts[sources[0]["id"]]
    abstention = False

    def require(condition, message):
        if not condition:
            errors.append(message)

    def nonblank(value):
        return isinstance(value, str) and bool(value.strip())

    def evidence(items, low, high, source=text):
        require(low <= len(items) <= high, "Evidence cardinality differs")
        for item in items:
            require(nonblank(item["quote"]) and item["quote"] in source, "Evidence quotation is not an exact excerpt substring")
            require(nonblank(item["explanation"]), "Evidence explanation is blank")

    if arm == "pairwise":
        require(len(sources) == 2 and {s.get("side") for s in sources} == {"A", "B"}, "Pairwise sources require both orientations")
        sides = {s.get("side"): source_texts[s["id"]] for s in sources}
        abstention = response["winner"] == "CANNOT_ASSESS"
        require(nonblank(response["tradeoff"]), "Tradeoff is blank")
        if abstention:
            require(nonblank(response["abstention_reason"]), "Abstention reason required")
            require(len(response["evidence"]) <= 6, "Too many evidence items")
        else:
            require(response["abstention_reason"] is None, "Assessed pair cannot carry abstention reason")
            require({e["side"] for e in response["evidence"]} == {"A", "B"}, "Assessed pair requires evidence from both excerpts")
            for side in ("A", "B"):
                require(1 <= sum(e["side"] == side for e in response["evidence"]) <= 3, "Pair evidence cardinality differs")
        for item in response["evidence"]:
            require(nonblank(item["quote"]) and item["quote"] in sides.get(item["side"], ""), "Pair quote is not on the declared side")
            require(nonblank(item["explanation"]), "Pair explanation is blank")
    elif arm in ("holistic", "compact"):
        abstention = response["status"] == "CANNOT_ASSESS"
        if abstention:
            require(response["result"] is None and nonblank(response["abstention_reason"]), "Abstention requires null result and reason")
        else:
            result = response["result"]
            require(isinstance(result, dict) and response["abstention_reason"] is None, "Scored result must be complete with null abstention reason")
            if isinstance(result, dict) and arm == "holistic":
                evidence(result["evidence"], 2, 5)
                require(2 <= len(result["strengths"]) <= 4 and len(result["limitations"]) <= 4, "Holistic observation counts differ")
                require(nonblank(result["rationale"]) and all(nonblank(v) for v in result["strengths"] + result["limitations"]), "Holistic observation is blank")
            elif isinstance(result, dict):
                dimensions = result["dimensions"]
                expected = schema["properties"]["result"]["properties"]["dimensions"]["items"]["properties"]["dimension_id"]["enum"]
                require(len(dimensions) == 6 and {d["dimension_id"] for d in dimensions} == set(expected), "Compact dimensions must occur exactly once")
                require(nonblank(result["overall_rationale"]), "Overall rationale is blank")
                for dimension in dimensions:
                    require(nonblank(dimension["rationale"]), "Dimension rationale is blank")
                    evidence(dimension["evidence"], 1, 3)
    elif arm == "hbq":
        verdicts = response["verdicts"]
        ids = request["question_ids"]
        require(len(verdicts) == len(ids) and {v["question_id"] for v in verdicts} == set(ids), "HBQ packet must contain every committed question once")
        abstention = any(v["verdict"] == "CANNOT_ASSESS" for v in verdicts)
        for verdict in verdicts:
            if verdict["verdict"] in ("NOT_APPLICABLE", "CANNOT_ASSESS"):
                require(nonblank(verdict["note"]), "N/A and abstention require explanation")
            for item in verdict["evidence"]:
                require(nonblank(item["reference"]), "HBQ evidence reference is blank")
                if item["kind"] == "exact_quote":
                    require(item["summary"] is None and nonblank(item["exact_quote"])
                            and (item["exact_quote"] in text or item["exact_quote"] in context), "HBQ quotation is not an exact artifact/context substring")
                else:
                    require(item["exact_quote"] is None and nonblank(item["summary"]), "HBQ summary evidence is malformed")
    else:
        errors.append("Unknown MFA quality arm")
    return {"accepted": not errors, "abstention": abstention, "errors": errors}
