"""Synthetic provider-free checks for Dryad's native composite admission."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "baseline_composite_admission_v5.py"
SCHEDULE_SOURCE = PACKAGE / "baseline_selected_schedule.py"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load():
    spec = importlib.util.spec_from_file_location("dryad_composite_admission_v5_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_schedule(path: Path):
    spec = importlib.util.spec_from_file_location("dryad_selected_schedule_composite_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def descriptor(root: Path, name: str, value: object) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def identity(number: int) -> dict[str, str]:
    return {"request_id_hash": f"{number:064x}", "session_id_hash": f"{number + 500_000:064x}"}


def old_identity(number: int) -> dict[str, int | str]:
    return {**identity(number), "observed_turns": 1}


def verdicts(case):
    return [{"question_id": question_id, "verdict": "YES"} for question_id in case.question_ids]


def default_old(case):
    def admit(*, pass_record):
        index = case.passes.index(pass_record)
        return {
            "evidence_class": "native_record_replay_only", "verdicts": verdicts(case),
            "native_identities": [old_identity(index * 23 + item + 1) for item in range(23)],
            "score": 50.0, "coverage": 1.0,
            "run_manifest_sha256": digest(f"run-{index}".encode()),
            "checkpoint_head_sha256": digest(f"checkpoint-{index}".encode()),
        }
    return admit


def default_suffix(case):
    prefix = [identity(number) for number in range(1, 80)]

    def admit(*, pass_id):
        index = next(number for number, item in enumerate(case.passes, start=1) if item["pass_id"] == pass_id)
        mixed = index == 4
        fresh_count = 12 if mixed else 23
        fresh_start = 10_000 + (index - 4) * 23
        return {
            "pass_id": pass_id,
            "evidence_class": "mixed_v4_native_recovered70_and_v5_native_replay" if mixed else "v5_native_full_pass_replay",
            "provider_calls_made": 0, "old_prefix_native_records": 79,
            "old_v4_native_records": 10 if mixed else 0, "old_recovered70_records": 1 if mixed else 0,
            "new_v5_native_records": fresh_count,
            "native_identities": prefix + [identity(fresh_start + item) for item in range(fresh_count)],
            "verdicts": verdicts(case), "score": 50.0, "coverage": 1.0,
        }
    return admit


def build_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = load()
    plan_root, suffix_root, evidence_root = tmp_path / "plan", tmp_path / "suffix", tmp_path / "evidence"
    for path in (plan_root, suffix_root, evidence_root):
        path.mkdir(parents=True)
    source = plan_root / "inputs" / "story.txt"
    source.parent.mkdir()
    source.write_text("Synthetic Dryad source.", encoding="utf-8")
    source_raw = source.read_bytes()
    question_ids = [f"criterion-{index:03d}" for index in range(178)]
    passes, requests = [], []
    for number in range(1, 237):
        partition = "TRAIN" if number <= 176 else "DEV"
        pass_id = f"baseline8-v1/{partition.lower()}/{number:04d}/synthetic-{number:03d}"
        passes.append({
            "pass_id": pass_id, "partition": partition, "logical_sample_id": f"logical-{number:03d}",
            "opaque_story_id": f"opaque-{number:03d}",
            "input_path": "inputs/story.txt", "source_sha256": digest(source_raw), "source_bytes": len(source_raw),
        })
        for batch in range(1, 24):
            start = (batch - 1) * 8
            requests.append({
                "ordinal": (number - 1) * 23 + batch, "pass_id": pass_id, "batch_number": batch,
                "question_ids": question_ids[start:start + (8 if batch < 23 else 2)],
            })
    plan_path = plan_root / "plan.json"
    plan_path.write_bytes(canonical({
        "dispatch_batch_size": 8, "empirical_batch_cap": None, "passes": passes, "requests": requests,
        "runtime": {"question_ids": question_ids},
    }))
    schedule_source = evidence_root / "selected-schedule-source.py"
    schedule_source.write_bytes(SCHEDULE_SOURCE.read_bytes())
    schedule = load_schedule(schedule_source).build_selected_schedule(
        plan_root=plan_root, expected_plan_sha256=digest(plan_path.read_bytes()),
        selected_train_ids=[record["pass_id"] for record in passes[:70]],
        selected_dev_ids=[record["pass_id"] for record in passes[176:206]],
    )
    schedule_path = evidence_root / "selected-schedule.json"
    schedule_path.write_bytes(canonical(schedule))
    schedule_descriptor = {
        "path": str(schedule_path), "sha256": digest(schedule_path.read_bytes()), "bytes": len(schedule_path.read_bytes()),
    }
    schedule_source_descriptor = {"path": str(schedule_source), "sha256": digest(schedule_source.read_bytes())}
    public = evidence_root / "public-inputs.json"
    public.write_bytes(canonical({"synthetic": "public-inputs"}))
    old_root = evidence_root / "old-execution"
    old_root.mkdir()
    old_runtime_sha = digest(b"old runtime manifest")
    initialization = descriptor(old_root, "initialization.json", {
        "schema_version": 1, "evidence_class": "provider_free_baseline_initialization",
        "plan_sha256": digest(plan_path.read_bytes()), "plan_inventory_sha256": digest(b"plan inventory"),
        "plan_files": 11094, "runtime_manifest_sha256": old_runtime_sha,
        "route_sha256": digest(b"old route"), "execution_source_sha256": digest(b"old execution"),
        "public_inputs_sha256": digest(public.read_bytes()),
    })
    cohort_settlement = descriptor(old_root, "cohorts/0008/settlement.json", {
        "schema_version": 3, "cohort_number": 8, "plan_sha256": digest(plan_path.read_bytes()),
        "prepared_sha256": digest(b"prepared"), "review_sha256": digest(b"review"),
        "route_sha256": digest(b"old route"), "previous_settlement_sha256": digest(b"previous settlement"),
        "settled_at": "2026-09-09T00:00:00Z", "contacts": [], "authorization_chain": [],
    })
    historical = {
        "schema_version": 2, "evidence_class": "preserved_predecessor_native_identity_exclusion",
        "completed_identity_records": 33,
        "records": [{"request_id_hash": identity(900_000 + index)["request_id_hash"],
                     "session_id_hash": identity(900_000 + index)["session_id_hash"]} for index in range(33)],
    }
    predecessor = {
        "schema_version": 1,
        "initialization": initialization,
        "ledger_head": cohort_settlement,
        "recovery_manifest": descriptor(evidence_root, "recovery.json", {"kind": "recovery"}),
        "identity_exclusion": descriptor(evidence_root, "historical-identities.json", historical),
    }
    predecessor_path = evidence_root / "predecessor.json"
    predecessor_path.write_bytes(canonical(predecessor))
    old_passes = []
    for number in range(3):
        root = evidence_root / "old-runs" / str(number + 1)
        root.mkdir(parents=True)
        old_passes.append({"pass_id": passes[number]["pass_id"], "run_root": str(root)})
    prefix_manifest = descriptor(evidence_root, "prefix.json", {"kind": "prefix"})
    suffix_source_sha = digest(b"synthetic suffix source")
    context = SimpleNamespace(
        epoch={
            "executor_source": {"path": str(evidence_root / "suffix.py"), "sha256": suffix_source_sha},
            "plan_sha256": digest(plan_path.read_bytes()), "old_prefix_manifest": prefix_manifest,
            "recovered_study_manifest": descriptor(evidence_root, "recovered-study.json", {"kind": "recovered"}),
            "recovery_adoption_sha256": digest(b"adoption"), "recovery_amendment_sha256": digest(b"amendment"),
            "runtime_manifest": descriptor(evidence_root, "runtime.json", {"kind": "runtime"}),
            "runtime_package": {"root": str(evidence_root), "manifest_sha256": digest(b"package")},
            "old_runtime_manifest": {"path": str(evidence_root / "old-runtime.json"), "sha256": old_runtime_sha},
            "selected_schedule": schedule_descriptor,
            "selected_schedule_source": schedule_source_descriptor,
            "selected_request_ordinals": schedule["selected_request_ordinals"],
            "remaining_request_ordinals": schedule["grok_remaining_request_ordinals"],
            "old_execution_inventory": {
                "initialization.json": initialization["sha256"], "cohorts/0008/settlement.json": cohort_settlement["sha256"],
            },
        },
        old_root=old_root, old_passes=old_passes, prefix_manifest=prefix_manifest,
        prefix_anchors={
            "grok51_manifest_sha256": predecessor["recovery_manifest"]["sha256"],
            "initialization_sha256": initialization["sha256"],
            "final_settlement_sha256": cohort_settlement["sha256"],
        },
    )
    case = SimpleNamespace(
        subject=subject, plan_root=plan_root, suffix_root=suffix_root, public=public, predecessor=predecessor_path,
        predecessor_value=predecessor, passes=passes, question_ids=question_ids, context=context,
        suffix_source_sha=suffix_source_sha, schedule=schedule, schedule_path=schedule_path,
        schedule_source=schedule_source,
    )
    case.old_admit, case.suffix_admit = default_old(case), default_suffix(case)
    terminals = [{"ordinal": ordinal, "attempt_start_sha256": digest(f"start-{ordinal}".encode()),
                  "terminal_sha256": digest(f"terminal-{ordinal}".encode()), "review_sha256": digest(b"review")}
                 for ordinal in schedule["grok_remaining_request_ordinals"]]

    def terminal_commitments(*_args, **kwargs):
        assert kwargs["ordinals"] == schedule["grok_remaining_request_ordinals"]
        return terminals, digest(canonical(terminals)), [{"path": "review", "sha256": digest(b"review"), "bytes": 6}]

    monkeypatch.setattr(subject, "_actual_replay_context", lambda **_kwargs: context)
    monkeypatch.setattr(subject, "_actual_old_admit",
                        lambda _context, **kwargs: case.old_admit(pass_record=kwargs["pass_record"]))
    monkeypatch.setattr(subject, "_actual_suffix_admit",
                        lambda _context, **kwargs: case.suffix_admit(pass_id=kwargs["pass_id"]))
    monkeypatch.setattr(subject, "_terminal_commitments", terminal_commitments)
    return case


def compose(
    case, *, expected_public_inputs_sha256: str | None = None, expected_predecessor_sha256: str | None = None,
    expected_selected_schedule_sha256: str | None = None, expected_selected_schedule_source_sha256: str | None = None,
):
    return case.subject.admit_composite_baseline(
        plan_root=case.plan_root, public_inputs_path=case.public, predecessor_path=case.predecessor,
        suffix_root=case.suffix_root, expected_plan_sha256=digest((case.plan_root / "plan.json").read_bytes()),
        expected_public_inputs_sha256=expected_public_inputs_sha256 or digest(case.public.read_bytes()),
        expected_predecessor_sha256=expected_predecessor_sha256 or digest(case.predecessor.read_bytes()),
        expected_suffix_epoch_sha256=digest(b"synthetic epoch"), expected_suffix_source_sha256=case.suffix_source_sha,
        expected_selected_schedule_sha256=expected_selected_schedule_sha256 or digest(case.schedule_path.read_bytes()),
        expected_selected_schedule_source_sha256=(
            expected_selected_schedule_source_sha256 or digest(case.schedule_source.read_bytes())
        ),
        expected_composer_sha256=digest(SOURCE.read_bytes()), approved_v4_routes={"v4": {}}, approved_v5_routes={"v5": {}},
    )


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return build_case(tmp_path, monkeypatch)


def test_composes_actual_opaque_rows_from_private_pinned_replay_seams(case) -> None:
    result = compose(case)
    record = result["composite_admission"]
    assert result["provider_calls_made"] == 0 and result["execution_authority"] is False
    assert result["composite_admission_sha256"] == digest(canonical(record))
    assert "composite_admission_sha256" not in record
    assert record["schema_version"] == 2
    assert record["evidence_class"] == "composite_v4_recovered70_v5_selected_baseline_admission"
    assert record["counts"] == {"passes": 100, "logical": 2300, "native": 2299, "recovered": 1}
    assert record["recovered_ordinals"] == [70]
    selected = [*case.passes[:70], *case.passes[176:206]]
    assert len(record["endpoint_grok_rows"]) == len(record["per_pass_replay_commitments"]) == 100
    assert [item["opaque_story_id"] for item in record["endpoint_grok_rows"]] == [
        item["opaque_story_id"] for item in selected
    ]
    assert all(row["opaque_story_id"] != selected[index]["logical_sample_id"]
               for index, row in enumerate(record["endpoint_grok_rows"]))
    assert len(record["suffix"]["ordered_terminals"]) == 2220
    assert record["suffix"]["ordered_terminals"][0]["ordinal"] == 81
    assert record["suffix"]["ordered_terminals"][-1]["ordinal"] == 4738
    assert record["suffix"]["covered_ordinals"] == case.schedule["grok_remaining_request_ordinals"]
    assert record["suffix"]["covered_ordinals"][record["suffix"]["covered_ordinals"].index(1610) + 1] == 4049
    assert record["selection"] == {
        "schedule": {**case.context.epoch["selected_schedule"], "bytes": len(case.schedule_path.read_bytes())},
        "source": {**case.context.epoch["selected_schedule_source"], "bytes": len(case.schedule_source.read_bytes())},
        "train_pass_ids": case.schedule["selected_train_ids"], "dev_pass_ids": case.schedule["selected_dev_ids"],
        "request_ordinals": case.schedule["selected_request_ordinals"],
    }
    assert record["predecessor"]["prefix_manifest"] == case.context.prefix_manifest
    assert set(record["predecessor"]["original_initialization"]) == {"execution_source_sha256", "route_sha256"}
    assert record["predecessor"]["ledger_head"]["cohort_number"] == 8
    assert record["predecessor"]["ledger_head"]["settlement_sha256"] == case.predecessor_value["ledger_head"]["sha256"]
    assert Path(case.predecessor_value["ledger_head"]["path"]).name == "settlement.json"


def test_preserves_original_full_plan_geometry_while_admitting_selected_schedule(case) -> None:
    _plan, _raw, passes, _by_id, questions = case.subject._plan(
        case.plan_root, digest((case.plan_root / "plan.json").read_bytes()),
    )
    assert len(passes) == 236 and len(_plan["requests"]) == 5428 and len(questions) == 178
    assert compose(case)["composite_admission"]["counts"]["passes"] == 100


def test_replays_only_schedule_selected_passes(case) -> None:
    observed: list[str] = []
    original = case.suffix_admit

    def tracked(*, pass_id):
        observed.append(pass_id)
        return original(pass_id=pass_id)

    case.suffix_admit = tracked
    compose(case)
    selected = [item["pass_id"] for item in [*case.passes[:70], *case.passes[176:206]]]
    assert observed == selected[3:]
    assert case.passes[70]["pass_id"] not in observed
    assert case.passes[206]["pass_id"] not in observed


def test_public_admission_does_not_accept_replay_callbacks(case) -> None:
    parameters = inspect.signature(case.subject.admit_composite_baseline).parameters
    assert "old_admit_pass" not in parameters
    assert "suffix_admit_pass" not in parameters
    assert "expected_selected_schedule_sha256" in parameters
    assert "expected_selected_schedule_source_sha256" in parameters


def _replace_schedule(case, value: object) -> str:
    case.schedule_path.write_bytes(canonical(value))
    schedule_sha = digest(case.schedule_path.read_bytes())
    case.context.epoch["selected_schedule"] = {
        "path": str(case.schedule_path), "sha256": schedule_sha, "bytes": len(case.schedule_path.read_bytes()),
    }
    return schedule_sha


@pytest.mark.parametrize("kind", ["expected_schedule", "expected_source", "schedule_drift", "source_drift", "missing"])
def test_rejects_selected_schedule_descriptor_and_source_binding_drift(case, kind: str) -> None:
    if kind == "expected_schedule":
        with pytest.raises(ValueError, match="Selected schedule epoch binding"):
            compose(case, expected_selected_schedule_sha256="0" * 64)
    elif kind == "expected_source":
        with pytest.raises(ValueError, match="Selected schedule epoch binding"):
            compose(case, expected_selected_schedule_source_sha256="0" * 64)
    elif kind == "schedule_drift":
        case.schedule_path.write_bytes(case.schedule_path.read_bytes() + b" ")
        with pytest.raises(ValueError, match="Selected schedule drift"):
            compose(case)
    elif kind == "source_drift":
        case.schedule_source.write_bytes(case.schedule_source.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="Selected schedule source drift"):
            compose(case)
    else:
        del case.context.epoch["selected_schedule"]
        with pytest.raises(ValueError, match="Selected schedule descriptor differs"):
            compose(case)


def test_rejects_selected_schedule_descriptor_byte_drift(case) -> None:
    case.context.epoch["selected_schedule"]["bytes"] += 1
    with pytest.raises(ValueError, match="Selected schedule bytes differ"):
        compose(case)


@pytest.mark.parametrize("fault", ["duplicate", "order"])
def test_rejects_duplicate_or_reordered_selected_schedule_ordinals(case, fault: str) -> None:
    value = json.loads(case.schedule_path.read_bytes())
    ordinals = value["selected_request_ordinals"]
    if fault == "duplicate":
        ordinals[100] = ordinals[99]
    else:
        ordinals[100], ordinals[101] = ordinals[101], ordinals[100]
    schedule_sha = _replace_schedule(case, value)
    with pytest.raises(ValueError, match="Selected schedule descriptor differs"):
        compose(case, expected_selected_schedule_sha256=schedule_sha)


def test_actual_old_wrapper_forwards_exact_native_result_and_logical_source(case) -> None:
    subject = load()
    expected = default_old(case)(pass_record=case.passes[0])
    observed = {}

    class Native:
        def admit_pass(self, run_root, **kwargs):
            observed["run_root"] = run_root
            observed.update(kwargs)
            return expected

    result = subject._actual_old_admit(
        SimpleNamespace(native=Native(), old_runtime=object()),
        plan_root=case.plan_root, pass_record=case.passes[0], run_root=Path(case.context.old_passes[0]["run_root"]),
        approved_v4_routes={"v4": {}},
    )
    assert result is expected
    assert observed["source"]["opaque_story_id"] == case.passes[0]["logical_sample_id"]
    assert observed["source"]["source_opaque_story_id"] == case.passes[0]["opaque_story_id"]
    assert observed["batch_size"] == 8
    subject._qualified(
        result, case.question_ids, expected_native=23, evidence_class="native_record_replay_only",
    )


@pytest.mark.parametrize("terminals", [[], [{"ordinal": 81}] * 2220])
def test_rejects_missing_or_duplicate_suffix_terminal_commitments(case, monkeypatch, terminals) -> None:
    monkeypatch.setattr(
        case.subject,
        "_terminal_commitments",
        lambda *_args, **_kwargs: (terminals, digest(canonical(terminals)), [{"path": "review", "sha256": digest(b"review")}]),
    )
    with pytest.raises(ValueError, match="Composite endpoint"):
        compose(case)


def test_rejects_selected_train_dev_terminal_boundary_gap(case, monkeypatch) -> None:
    terminals = [
        {"ordinal": ordinal, "attempt_start_sha256": digest(f"start-{ordinal}".encode()),
         "terminal_sha256": digest(f"terminal-{ordinal}".encode()), "review_sha256": digest(b"review")}
        for ordinal in case.schedule["grok_remaining_request_ordinals"] if ordinal != 4049
    ]
    monkeypatch.setattr(
        case.subject,
        "_terminal_commitments",
        lambda *_args, **_kwargs: (terminals, digest(canonical(terminals)), [{"path": "review", "sha256": digest(b"review")}]),
    )
    with pytest.raises(ValueError, match="Composite endpoint"):
        compose(case)


@pytest.mark.parametrize("fault", ["missing", "order", "prefix", "collision", "provisional", "coverage", "recovery"])
def test_rejects_incomplete_ordered_or_unqualified_suffix_replay(case, fault: str) -> None:
    base = default_suffix(case)

    def broken(*, pass_id):
        value = base(pass_id=pass_id)
        if fault == "missing" and pass_id == case.passes[4]["pass_id"]:
            value["verdicts"] = value["verdicts"][:-1]
        elif fault == "order" and pass_id == case.passes[4]["pass_id"]:
            value["verdicts"] = list(reversed(value["verdicts"]))
        elif fault == "prefix" and pass_id == case.passes[5]["pass_id"]:
            value["native_identities"] = [{**item, "request_id_hash": "f" * 64} for item in value["native_identities"]]
        elif fault == "collision" and pass_id == case.passes[5]["pass_id"]:
            value["native_identities"][-1] = value["native_identities"][0]
        elif fault == "provisional" and pass_id == case.passes[4]["pass_id"]:
            value["provisional"] = True
        elif fault == "coverage" and pass_id == case.passes[4]["pass_id"]:
            value["coverage"] = 0.5
        elif fault == "recovery" and pass_id == case.passes[3]["pass_id"]:
            value["old_recovered70_records"] = 0
        return value

    case.suffix_admit = broken
    with pytest.raises(ValueError):
        compose(case)


def test_rejects_old_v5_cross_category_and_historical_identity_collisions(case) -> None:
    base = default_suffix(case)

    def cross_category(*, pass_id):
        value = base(pass_id=pass_id)
        if pass_id == case.passes[4]["pass_id"]:
            value["native_identities"][-1] = {
                "request_id_hash": identity(1)["session_id_hash"], "session_id_hash": identity(20_000)["session_id_hash"],
            }
        return value

    case.suffix_admit = cross_category
    with pytest.raises(ValueError, match="identity"):
        compose(case)

    def historical(*, pass_id):
        value = base(pass_id=pass_id)
        if pass_id == case.passes[4]["pass_id"]:
            value["native_identities"][-1] = identity(900_000)
        return value

    case.suffix_admit = historical
    with pytest.raises(ValueError, match="identity"):
        compose(case)


def test_rejects_plan_public_predecessor_and_source_drift(case) -> None:
    public_sha = digest(case.public.read_bytes())
    case.public.write_bytes(case.public.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Public inputs"):
        compose(case, expected_public_inputs_sha256=public_sha)

    case = build_case(case.plan_root.parent / "source-drift", pytest.MonkeyPatch())
    (case.plan_root / "inputs" / "story.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen source"):
        compose(case)

    case = build_case(case.plan_root.parent / "predecessor-drift", pytest.MonkeyPatch())
    predecessor_sha = digest(case.predecessor.read_bytes())
    case.predecessor.write_bytes(case.predecessor.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Composite predecessor"):
        compose(case, expected_predecessor_sha256=predecessor_sha)


def test_rejects_predecessor_records_outside_actual_old_inventory(case) -> None:
    value = json.loads(case.predecessor.read_bytes())
    value["initialization"] = descriptor(case.public.parent, "foreign-init.json", {
        "schema_version": 1, "evidence_class": "provider_free_baseline_initialization",
    })
    case.predecessor.write_bytes(canonical(value))
    with pytest.raises(ValueError, match="outside the actual old execution root"):
        compose(case)


def test_composition_does_not_hide_old_or_v5_identity_duplicates(case) -> None:
    original = case.old_admit

    def duplicated_old(*, pass_record):
        value = original(pass_record=pass_record)
        if pass_record["pass_id"] == case.passes[2]["pass_id"]:
            value["native_identities"][0] = old_identity(1)
        return value

    case.old_admit = duplicated_old
    with pytest.raises(ValueError, match="old-prefix"):
        compose(case)
