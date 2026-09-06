"""Authenticate the preserved v2 terminal residue without admitting contact 28."""

from __future__ import annotations

import gzip
import hashlib
import json
import stat
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
ATTEMPT_SHA256 = "90639b16cd68d0a4b36821acdcc8ed802d510122973a8621cc0bbea6cc4a0be8"
HELPER_SHA256 = "efc3c445137eff401ea2f422eb002d9db20767a2c3b39a674054b047d2c2131b"
RUN = "runs/size-0008/repetition-01/dryad-44cae24e55019e2cbf491660"
REVIEW_SHA256 = "1b11bf1547ff2d2de001ce36549b19c21bcd30810a93548de790a401b9ee5ef9"
REVIEWER_TASK = "019ff75c-e610-7581-bacc-33ee869d521a"
RESIDUE = (
    "responses/attempt-lifecycle/batch-0005/attempt-0001.start.json",
    "responses/attempt-lifecycle/batch-0005/attempt-0001.settled.json",
    "responses/grok-broker/batch-0005-attempt-0001/context-bindings.json",
    "responses/grok-broker/batch-0005-attempt-0001/failure-receipt.json",
    "responses/grok-broker/batch-0005-attempt-0001/outcome.json",
    "responses/grok-broker/batch-0005-attempt-0001/request.json",
    "responses/rejected/batch-0005/attempt-0001.json",
)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _helper() -> tuple[ModuleType, bytes]:
    path = ROOT / "identity_exclusion.py"
    for candidate in (path, *path.parents):
        info = candidate.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Terminal helper path contains a link or reparse point")
    raw = path.read_bytes()
    require(digest(raw) == HELPER_SHA256, "Terminal helper source differs")
    module = ModuleType("_dryad_terminal_residue_helper")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local definitions.
    require(module._plain(path, file=True).read_bytes() == raw, "Terminal helper path differs")
    return module, raw


def validate_terminal_residue(run_root: Path, *, source: dict[str, Any], approved_routes: dict[str, Any], runtime: Any) -> dict[str, Any]:
    """Return only a seven-file residue allowlist for this exact failed snapshot.

    The caller must still replay the four completed batches using all ordinary
    native checks. This result supplies no native identity, score, or authority.
    """
    helper, helper_raw = _helper()
    root = helper._plain(Path(run_root), file=False)
    snapshot = helper._plain(root.parents[3], file=False)
    require(root.relative_to(snapshot).as_posix() == RUN, "Terminal run differs")
    attempt_path = helper._plain(ROOT / "qualification-attempt-2.json", file=True)
    attempt_raw = attempt_path.read_bytes()
    require(digest(attempt_raw) == ATTEMPT_SHA256, "Terminal attempt record differs")
    attempt = helper._object(attempt_raw, "Attempt record")
    before = helper._tree(snapshot)
    require(len(before) == attempt["preserved_snapshot"]["files"] == 372 and digest(canonical(before)) == attempt["preserved_snapshot"]["path_hash_map_sha256"], "Preserved terminal snapshot differs")
    runtime.verify()

    def read(relative: str) -> bytes:
        path = helper._relative(snapshot, relative)
        raw = path.read_bytes()
        require(digest(raw) == before[relative], "Terminal evidence changed during read")
        return raw

    def obj(relative: str) -> dict[str, Any]:
        return helper._object(read(relative), "Terminal evidence")

    manifest = obj(RUN + "/run.json")
    config = manifest["configuration"]
    require(source["opaque_story_id"] == RUN.rsplit("/", 1)[1] == config["artifact_id"] and digest(source["story_text"].encode()) == config["artifact"]["sha256"] and str(Path(source["artifact_path"]).resolve()) == config["artifact"]["path"], "Terminal source binding differs")
    require(manifest["config_sha256"] == digest(runtime.runner._json_bytes(config)), "Terminal configuration hash differs")
    contact_raw = read("contacts/request-0028.json")
    contact = helper._object(contact_raw, "Terminal contact")
    prepared_raw = read("cohorts/0003/prepared.json")
    prepared = helper._object(prepared_raw, "Prepared cohort")
    review_raw = read("cohorts/0003/review.json")
    review = helper._object(review_raw, "Review")
    route = obj("cohorts/0003/route.json")
    route_sha = digest(canonical(route))
    require(digest(contact_raw) == attempt["contact_record_sha256"] and contact["ordinal"] == 28 and contact["cohort_number"] == 3 and contact["plan_sha256"] == attempt["qualification_plan_sha256"], "Terminal contact commitment differs")
    require(contact["prepared_sha256"] == digest(prepared_raw) and prepared["cohort_number"] == 3 and prepared["plan_sha256"] == contact["plan_sha256"] and prepared["request_ordinals"] == list(range(21, 31)) and prepared["execution_source_sha256"] == attempt["execution_source_sha256"] and prepared["previous_settlement_sha256"] == digest(read("cohorts/0002/settlement.json")), "Terminal cohort lineage differs")
    require(digest(review_raw) == REVIEW_SHA256 == contact["review_sha256"] and review["reviewer_task"] == REVIEWER_TASK and review["decision"] == "approved_cohort" and review["prepared_sha256"] == digest(prepared_raw), "Terminal review binding differs")
    require(datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(contact["admitted_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00")), "Terminal contact outside review")
    require(route_sha == contact["route_sha256"] == prepared["route_sha256"] and approved_routes.get(route_sha) == route, "Terminal route binding differs")
    chunk = runtime.questions[32:40]
    schema = runtime.runner._batch_response_schema([item["question"]["id"] for item in chunk])
    schema_raw = runtime.runner._json_bytes(schema)
    schema_path = root / "responses/schemas/batch-0005.json"
    require(read(RUN + "/responses/schemas/batch-0005.json") == schema_raw and digest(schema_raw) == contact["schema_sha256"], "Terminal schema differs")
    binary = (ROOT.parents[1] / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes().decode("utf-8-sig").strip()
    prompt = runtime.runner._render_prompt(binary_prompt=binary, artifact={"name": config["artifact"]["name"], "text": source["story_text"]}, contexts=[], bundle_id="prose.short_story", artifact_id=source["opaque_story_id"], questions=chunk, provider="grok", model="grok-4.6")
    prompt_sha = digest(prompt.encode())
    require(prompt_sha == contact["prompt_sha256"] and gzip.decompress(read(RUN + "/responses/batch-0005.prompt.txt.gz")) == prompt.encode(), "Terminal prompt differs")
    prefix = "responses/grok-broker/batch-0005-attempt-0001/"
    request_raw = read(RUN + "/" + prefix + "request.json")
    context_raw = read(RUN + "/" + prefix + "context-bindings.json")
    outcome_raw = read(RUN + "/" + prefix + "outcome.json")
    failure_raw = read(RUN + "/" + prefix + "failure-receipt.json")
    require(request_raw == canonical({"prompt": prompt}) and digest(request_raw) == attempt["request_sha256"], "Terminal request differs")
    context = runtime.runner._before_provider_attempt_context(destination=root, schema_path=schema_path, run_id=manifest["run_id"], config_sha256=manifest["config_sha256"], provider="grok", model="grok-4.6", reasoning="high", endpoint=None, batch_number=5, question_ids=[item["question"]["id"] for item in chunk], attempt_number=1, batch_attempts=1, base_prompt_sha256=prompt_sha, effective_prompt=prompt, feedback_policy=runtime.runner.VALIDATION_FEEDBACK_POLICY, feedback=None, rejected_chain={})
    context["transport"] = {**config["grok_transport"], "allow_unattested_reasoning": True}
    *_, bindings = runtime.transport._context_bindings(context, route)
    require(context_raw == canonical(bindings), "Terminal context differs")
    require(config["grok_transport"]["declared_sha256"] == runtime.transport_sha256, "Terminal transport differs")
    require(failure_raw == canonical({"schema_version": 1, "source_sha256": runtime.transport_sha256, "route_sha256": route_sha, "request_sha256": digest(request_raw), "context_sha256": digest(context_raw), "outcome_sha256": digest(outcome_raw), "status": "not_completed"}) and digest(failure_raw) == attempt["failure_receipt_sha256"], "Terminal failure receipt differs")
    outcome = helper._object(outcome_raw, "Terminal outcome")
    require(digest(outcome_raw) == attempt["outcome_sha256"] and set(outcome) == {"state", "result", "failure"} and outcome["state"] == "ambiguous" and outcome["result"] is None and isinstance(outcome["failure"], dict), "Terminal outcome differs")
    require(all(outcome["failure"].get(key) == attempt["structured_failure"][key] for key in ("provider", "category", "code", "provider_error_type", "status", "incident_key")) and outcome["failure"].get("revocation") == attempt["structured_failure"]["revocation_recorded"], "Terminal failure classification differs")
    start_path, settled_path, *_, rejected_path = RESIDUE
    start_raw = read(RUN + "/" + start_path)
    start = helper._object(start_raw, "Terminal start")
    require(start == {"format_version": 1, "policy": "terminal_sidecar_v1", "batch": 5, "attempt": 1, "state": "started", "config_sha256": manifest["config_sha256"], "base_prompt_sha256": prompt_sha, "effective_prompt_sha256": prompt_sha, "retry_policy": {"batch_attempts": 1}}, "Terminal start differs")
    rejected_raw = read(RUN + "/" + rejected_path)
    rejected = helper._object(rejected_raw, "Terminal rejection")
    require(digest(rejected_raw) == attempt["rejected_record_sha256"] and rejected["batch"] == 5 and rejected["attempt"] == 1 and rejected["attempt_outcome"] == "provider_nonretryable_failure" and rejected["provider"]["evidence_sha256"] == digest(failure_raw), "Terminal rejected attempt differs")
    settled_raw = read(RUN + "/" + settled_path)
    require(digest(settled_raw) == attempt["terminal_record_sha256"] and helper._object(settled_raw, "Terminal settlement") == {"format_version": 1, "policy": "terminal_sidecar_v1", "batch": 5, "attempt": 1, "state": "settled", "start_sha256": digest(start_raw), "outcome": "provider_nonretryable_failure", "evidence": {"kind": "rejected_attempt", "path": rejected_path, "sha256": digest(rejected_raw)}}, "Terminal settlement differs")
    forbidden = ("responses/batch-0005.json", "responses/batch-0005.accepted-0001.message.txt", prefix + "receipt.json", prefix + "native-envelope.json")
    require(all(RUN + "/" + relative not in before for relative in forbidden), "Terminal contact has completion evidence")
    residue_files = {relative: before[RUN + "/" + relative] for relative in RESIDUE}
    runtime.verify()
    require(helper._tree(snapshot) == before and attempt_path.read_bytes() == attempt_raw and helper._plain(ROOT / "identity_exclusion.py", file=True).read_bytes() == helper_raw, "Terminal evidence changed during verification")
    return {"evidence_class": "authenticated_ambiguous_terminal_residue", "admitted_batches": 4, "terminal_batch": 5, "ordinal": 28, "native_identity_claimed": False, "native_admission": False, "execution_authority": False, "snapshot_sha256": digest(canonical(before)), "attempt_record_sha256": ATTEMPT_SHA256, "authorization_sha256": REVIEW_SHA256, "run_path": RUN, "residue_files": residue_files}
