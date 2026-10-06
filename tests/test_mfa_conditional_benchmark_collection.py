from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "evaluation-results/hbq-mfa-conditional-benchmark-v1"
spec = importlib.util.spec_from_file_location("conditional_collector_test", HERE / "collector.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def fixture(tmp_path):
    from hbqrs import runner
    helper = collector.prepare.canary_helpers()
    subset = collector.load_module("conditional_test_subset", Path.home() / ".codex/tools/model_work_queue/adapters/json_schema_subset.py")
    validator = collector.load_module("conditional_test_validator", collector.prepare.CANARY / "validate_response.py")
    task_context = json.dumps({"audience": []}, indent=2).encode()
    scope = b"Visible local scope only."
    text = b"Synthetic candidate passage."
    schema = helper.portable_schema(runner._batch_response_schema(["q-test"]))
    cache = {"prompt.txt": b"rubric-only sentinel\n" + task_context + b"\n" + scope + b"\n" + text,
             "schema.json": collector.canonical(schema), "task-context.txt": task_context,
             "context.txt": scope, "evidence-context.txt": task_context + b"\n" + scope,
             "task.json": collector.canonical({"contract_id": "synthetic"}), "source.txt": text}
    root = tmp_path / "frozen"
    root.mkdir()
    for name, raw in cache.items():
        (root / name).write_bytes(raw)
    manifest = {"artifacts": {name: {"sha256": collector.sha(raw), "bytes": len(raw)} for name, raw in cache.items()}}
    row = {"logical_sample_id": "a" * 64, "endpoint": "sol", "endpoint_ordinal": 1, "arm": "hbq",
           "partition": "confirmation", "bundle_id": "prose.short_form", "task": "quality", "repeat": 0,
           "primary": True, "question_ids": ["q-test"], "batch": 1, "prompt_path": "prompt.txt",
           "prompt_sha256": collector.sha(cache["prompt.txt"]), "prompt_bytes": len(cache["prompt.txt"]),
           "schema_path": "schema.json", "schema_sha256": collector.sha(cache["schema.json"]),
           "schema_bytes": len(cache["schema.json"]), "context_path": "evidence-context.txt",
           "context_sha256": collector.sha(cache["evidence-context.txt"]), "task_context_path": "task-context.txt",
           "task_context_sha256": collector.sha(task_context), "task_contract_path": "task.json",
           "task_contract_sha256": collector.sha(cache["task.json"]),
           "sources": [{"id": "candidate", "input_path": "source.txt", "sha256": collector.sha(text), "bytes": len(text)}]}
    row["request_sha256"] = collector.sha(collector.canonical(row))
    binding = {"endpoint": "sol", "manifest_sha256": "m" * 64,
               "runtime": {"model": "gpt-6.1-sol", "reasoning": "high", "account_identity_sha256": "i" * 64,
                           "secondary_home_sha256": "h" * 64}, "account_probe_sha256": "p" * 64}
    manifest["runtime"] = {"timeout_seconds": 900}
    output = tmp_path / "results"
    output.mkdir()
    collector.record(output / "job.json", binding)
    collector.record(output / "account-binding.json", collector.account_receipt(binding))
    answer = {"verdicts": [{"question_id": "q-test", "verdict": "YES", "confidence": 0.8, "note": "",
                           "evidence": [{"kind": "exact_quote", "reference": "task-context",
                                         "exact_quote": '"audience": []', "summary": None}]}]}

    def call(**args):
        assert args["timeout"] == 900 and args["codex_receipt_policy"] == "codex_native_rollout_v1"
        assert args["model"] == "gpt-6.1-sol" and args["reasoning"] == "high"
        args["before_provider_attempt"]()
        (args["output_dir"] / "final.json").write_bytes(collector.canonical(answer))
        return collector.canonical(answer).decode(), {"state": "completed", "provider_artifacts": {"codex_message": {"path": "final.json"}}}

    def verify(sample, native, **args):
        assert args["prompt"].encode() == cache["prompt.txt"]
        assert args["model"] == "gpt-6.1-sol" and args["reasoning"] == "high"
        assert args["final_raw"] == (sample / "final.json").read_bytes()

    return root, output, cache, manifest, row, binding, subset, validator, answer, call, SimpleNamespace(verify=verify)


def test_exact_declared_context_admission_and_own_response_replay(tmp_path):
    root, output, cache, manifest, row, binding, subset, validator, answer, call, receipts = fixture(tmp_path)
    collector.validate_row(root, manifest, row, {"module": subset, "checked": set()}, cache)
    bad_context = {**cache, "evidence-context.txt": cache["prompt.txt"]}
    with pytest.raises(ValueError, match="Exact declared task/context"):
        collector.validate_row(root, manifest, row, {"module": subset, "checked": set()}, bad_context)
    acceptance = validator.semantic_validate("hbq", answer, row, {"candidate": cache["source.txt"].decode()}, subset,
                                             context=cache["evidence-context.txt"].decode(), schema=json.loads(cache["schema.json"]))
    assert acceptance["accepted"], acceptance["errors"]
    rubric_answer = deepcopy(answer)
    rubric_answer["verdicts"][0]["evidence"][0]["exact_quote"] = "rubric-only sentinel"
    assert not validator.semantic_validate("hbq", rubric_answer, row, {"candidate": cache["source.txt"].decode()}, subset,
        context=cache["evidence-context.txt"].decode(), schema=json.loads(cache["schema.json"]))["accepted"]
    state = collector.collect_one(row, manifest, binding, root, output, subset, validator, receipts, Event(),
                                  SimpleNamespace(CLI="synthetic-cli"), call)
    assert state == "accepted"
    sample = collector.sample_path(output, row)
    terminal, replayed = collector.replay(sample, row, manifest, binding, root, receipts, subset, validator)
    assert terminal["accepted"] and replayed == answer
    rejected_row = {**row, "endpoint_ordinal": 2, "logical_sample_id": "b" * 64}
    answer["verdicts"][0]["evidence"][0]["exact_quote"] = "rubric-only sentinel"
    signal = Event()
    assert collector.collect_one(rejected_row, manifest, binding, root, output, subset, validator, receipts, signal,
                                 SimpleNamespace(CLI="synthetic-cli"), call) == "semantic_rejected"
    assert not signal.is_set()
    rejected, vote = collector.replay(collector.sample_path(output, rejected_row), rejected_row, manifest,
                                      binding, root, receipts, subset, validator)
    assert rejected["accepted"] is False and vote is None and rejected["no_resend"]
    (sample / "response.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="Settled evidence differs"):
        collector.replay(sample, row, manifest, binding, root, receipts, subset, validator)


def test_late_evidence_failure_is_missing_no_resend_and_dispatch_drains_started_tail(tmp_path, monkeypatch):
    root, output, cache, manifest, row, binding, subset, validator, answer, call, receipts = fixture(tmp_path)
    original = Path.read_bytes
    injected = False

    def late_failure(path):
        nonlocal injected
        if not injected and path.name == "acceptance.json" and path.parent == collector.sample_path(output, row):
            injected = True
            raise OSError("synthetic late evidence failure")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", late_failure)
    halt = Event()
    state = collector.collect_one(row, manifest, binding, root, output, subset, validator, receipts, halt,
                                  SimpleNamespace(CLI="synthetic-cli"), call)
    assert injected and state == "unadmitted_no_resend" and halt.is_set()
    terminal, replayed = collector.replay(collector.sample_path(output, row), row, manifest, binding, root, receipts, subset, validator)
    assert terminal["accepted"] is False and terminal["no_resend"] and replayed is None
    with pytest.raises(FileExistsError):
        collector.collect_one(row, manifest, binding, root, output, subset, validator, receipts, Event(),
                              SimpleNamespace(CLI="synthetic-cli"), call)
    incomplete = output / "incomplete"
    incomplete.mkdir()
    with pytest.raises(ValueError, match="Started slot unresolved"):
        collector.replay(incomplete, row, manifest, binding, root, receipts, subset, validator)

    second_started, failure_settled = Event(), Event()
    admitted = []

    def worker(item, signal):
        admitted.append(item["endpoint_ordinal"])
        if item["endpoint_ordinal"] == 1:
            assert second_started.wait(5)
            signal.set()
            failure_settled.set()
            return "unadmitted_no_resend"
        second_started.set()
        assert failure_settled.wait(5)
        return "accepted"

    states, stopped = collector.dispatch([{"endpoint_ordinal": n} for n in (1, 2, 3)], output, 2, worker)
    assert stopped and set(admitted) == {1, 2}
    assert {(v["ordinal"], v["state"]) for v in states} == {(1, "unadmitted_no_resend"), (2, "accepted")}

    def stop_during_last_call(item, signal):
        (output / "STOP").write_text("synthetic stop")
        return "accepted"

    states, stopped = collector.dispatch([{"endpoint_ordinal": 4}], output, 1, stop_during_last_call)
    assert stopped and states == [{"ordinal": 4, "state": "accepted"}]
