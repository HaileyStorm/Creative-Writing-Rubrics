"""Zero-call, pinned slot391 descendant under saved_transport_recovery_v1.

The failed native terminal remains evidence. This recipient policy does not
reconstruct its envelope or establish original strict admission/contact counts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOLS = Path(r"C:\Users\Haile\.codex\tools")
HOME = Path(r"C:\Users\Haile\.codex\collection-accounts\cwr-sol-secondary")
POLICY = "ttcw_saved_sol_transport_reconciliation_v1"
SLOT = "0391-570aad3892cf"
TRANSPORT_SHA = "fbedc8e50d08de7dff0547483f26c9fd081a8b4c9e62f0713609ce043e0fb34c"
READER_SHA = "5d1c7af681e881a77201dee7cece4a14fa11cadc86d119714766492e547e1116"
VALIDATOR_SHA = "a41915877b6f7e21a05f0b34d3c31c788f7f23070ab674ecfc514d93391e270e"
PROJECTION_SHA = "0fe4968a729c48a26acf226bc6829b19de864800b1c4fe1228f53fe274c578a1"
PINNED = {
    "manifest": ("d5cc19e50360c5d12e8aa118df5f8e89840174cb308964034be9d6873f500914", 2481729),
    "job": ("bffcfc94a36b028b9ac2ea9651fb16150357a7933f351e3fa21120588ede0676", 1119),
    "condition": ("7aef0428d79fddbb7001548c0a112be86a0bc39935640d83e6ba80514b79682c", 1190),
    "started": ("bfd03eb50de8bf86a3f8fa38500d19a0b19cf3e86de3c8e65d28e142a7255cc2", 121),
    "identity": ("0a5a852594c02ba64dcde29b1e1d67e23e43e96c0cfb5b00938161ee58c3c86b", 116),
    "terminal": ("399b28dd97a9c37a0d16bd8acc1ef226bd94dd7fba291def8a2ce4331d1ec83c", 2029),
    "events": ("be7548c9dfec2afd375ae935d2acce6a4aa6c5c21bdb1fa81b559a3f86e2d59d", 8409),
    "final": ("4e66715c05a3768a3a681cac44525dbb0d8b8d23c7920cfc416f19b04ebfe214", 6619),
    "rollout": ("4860fa1bba24ab8ba92e86d72655c819d7452bc7da0a971848721b294e24a856", 88588),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    previous = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = previous
    return module


def bind_source(manifest, manifest_raw, job, row, identity, started, terminal, schema, artifacts):
    require(row["endpoint"] == "sol" and row["endpoint_ordinal"] == 391
            and f"0391-{row['logical_sample_id'][:12]}" == SLOT, "Only pinned Sol391 is supported; no resend")
    require(row in manifest["requests"] and digest(canonical({k: v for k, v in row.items() if k != "request_sha256"})) == row["request_sha256"],
            "Condition differs from frozen request")
    require(job["manifest_sha256"] == digest(manifest_raw) and job["endpoint"] == "sol"
            and job["model"] == "gpt-6.1-sol" and job["reasoning"] == "high"
            and job["automatic_retries"] == 0 and job["zero_charge_only"] is True
            and job["receipt_reader_sha256"] == READER_SHA and job["validator_sha256"] == VALIDATOR_SHA
            and job["account_identity_sha256"] == "4392760f900d3f082618c27721f07cbc9ffca06b91bb9ac8fa5f20695625d2de"
            and job["helper_sha256"] == "c0a3563dab36105830c9e63be7fdeb551ef7a9805a5b5b44450c9e6501be3b01",
            "Source job/account/runtime differs")
    require(identity == {"logical_sample_id": row["logical_sample_id"], "session_id": None}
            and started["session_id"] is None and started["no_resend"] is True and started["state"] == "before_contact",
            "Own source identity/start differs")
    require(terminal["state"] == "unadmitted_no_resend" and terminal["accepted"] is False
            and terminal["no_resend"] is True and terminal["error_class"] == "_ProviderAttemptFailure"
            and "-3128.9529999999795" in terminal["error"], "Original negative-timeout failure differs")
    retained = terminal["provider_record"]["provider_artifacts"]["codex_events"]
    require(retained == {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": PINNED["events"][1],
                         "sha256": PINNED["events"][0]}, "Original terminal events commitment differs")
    require(schema == artifacts[row["schema_path"]], "Attempt schema differs")
    for kind in ("prompt", "schema"):
        raw = artifacts[row[kind + "_path"]]
        require(digest(raw) == row[kind + "_sha256"] and len(raw) == row[kind + "_bytes"], "Frozen request bytes differ")
    for source in row["sources"]:
        require(digest(artifacts[source["input_path"]]) == source["sha256"], "Frozen source differs")


def reconcile(manifest_path, results, slot, home, rollout, *, snapshot=None, commitments=None):
    require(slot == SLOT, "Only pinned Sol391 is supported; no resend")
    require(home.resolve() == HOME.resolve() and rollout.resolve().is_relative_to(home.resolve() / "sessions"),
            "Selected own account/session root differs")
    transport_path = REPO / "evaluation-results/hbq-native-transport-recovery-v1/reconcile.py"
    require(digest(transport_path.read_bytes()) == TRANSPORT_SHA, "Published transport implementation differs")
    reader_path = REPO / "src/hbqrs/codex_receipts.py"
    require(digest(reader_path.read_bytes()) == READER_SHA, "Published native reader differs")
    transport = load("ttcw_sol391_transport", transport_path)
    class Reads(transport.ReadSet):
        def raw(self, name, path):
            require(self.snapshot is None or name in self.expected, "Snapshot source commitment missing: " + name)
            raw = super().raw(name, path)
            if name in PINNED:
                require((digest(raw), len(raw)) == PINNED[name], "Pinned source differs: " + name)
            return raw
    reads = Reads(snapshot=snapshot, commitments=commitments)
    sample = results / slot
    paths = {"manifest": manifest_path, "job": results / "job.json", "condition": sample / "condition.json",
             "started": sample / "attempt-started.json", "identity": sample / "native-identity.json",
             "terminal": sample / "terminal.json", "attempt_schema": sample / "schema.json"}
    values = {name: json.loads(reads.raw(name, path)) for name, path in paths.items()}
    manifest, job, row = values["manifest"], values["job"], values["condition"]
    require(manifest["implementation"]["semantic_validator_sha256"] == VALIDATOR_SHA, "Frozen validator differs")
    names = {"context.txt", row["prompt_path"], row["schema_path"], *(s["input_path"] for s in row["sources"])}
    artifacts = {}
    for index, name in enumerate(sorted(names)):
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Frozen path escapes manifest")
        raw = reads.raw("frozen_" + str(index), manifest_path.parent / name)
        pin = manifest["artifacts"][name]
        require(digest(raw) == pin["sha256"] and len(raw) == pin["bytes"], "Frozen artifact pin differs")
        artifacts[name] = raw
    bind_source(manifest, reads.raws["manifest"], job, row, values["identity"], values["started"], values["terminal"],
                reads.raws["attempt_schema"], artifacts)
    reads.raw("transport_implementation", transport_path)
    reads.raw("reader_implementation", reader_path)
    validator_path = HERE / "validate_response.py"
    subset_path = TOOLS / "model_work_queue/adapters/json_schema_subset.py"
    require(digest(reads.raw("validator_implementation", validator_path)) == VALIDATOR_SHA, "Validator implementation differs")
    require(digest(reads.raw("schema_implementation", subset_path)) == manifest["implementation"]["schema_subset_sha256"],
            "Frozen schema implementation differs")
    response, native = transport.recover_sol(reads, sample, artifacts[row["prompt_path"]].decode(), home,
                                             values["started"], rollout_path=rollout)
    require(native["filtered_events_sha256"] == PROJECTION_SHA, "Pinned transport projection differs")
    if snapshot is not None:
        projected = reads.raws["events_projection"]
        require(reads.raw("events_projection", Path("derived:validated_dns_transport_projection")) == projected,
                "Snapshot derived events differ")
    require(native["policy"] == "saved_transport_recovery_v1" and native["original_receipt_policy_satisfied"] is False,
            "Named native policy differs")
    subset, validator = load("ttcw_sol391_subset", subset_path), load("ttcw_sol391_validator", validator_path)
    texts = {s["id"]: artifacts[s["input_path"]].decode() for s in row["sources"]}
    acceptance = validator.semantic_validate(row["arm"], response, row, texts, subset,
        context=artifacts["context.txt"].decode(), schema=json.loads(artifacts[row["schema_path"]]))
    response_raw = reads.raws["final"]
    receipt = {"policy": POLICY, "evidence_class": "saved_transport_recovery_v1", "endpoint": "sol", "slot": slot,
        "logical_sample_id": row["logical_sample_id"], "endpoint_ordinal": 391, "request_sha256": row["request_sha256"],
        "state": "completed_semantically_accepted" if acceptance["accepted"] else "completed_semantically_rejected",
        "accepted": acceptance["accepted"], "abstention": acceptance["abstention"], "semantic_errors": acceptance["errors"],
        "original_terminal_preserved": "unadmitted_no_resend", "no_resend": True, "provider_calls_made": 0,
        "new_logical_votes": 0, "full_planned_denominator": 3108, "human_labels_released": False,
        "original_native_envelope_reconstructed": False, "full_runtime_contract_attested": False,
        "native": native, "source_commitments": reads.commitments(), "response_sha256": digest(response_raw),
        "acceptance_sha256": digest(canonical(acceptance)), "implementation_sha256": digest(Path(__file__).read_bytes())}
    return receipt, response_raw, acceptance, reads


def fresh_output(output, roots):
    output = output.resolve()
    require(not output.exists() and all(not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output)
                                       for p in roots), "Output must be fresh and outside source trees/repository")
    return output


def write_new(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "results-root", "own-home", "rollout", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--slot", default=SLOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    output = fresh_output(args.output_root, [REPO, args.manifest.parent, args.results_root, args.own_home, args.rollout.parent])
    receipt, response, acceptance, reads = reconcile(args.manifest.resolve(), args.results_root.resolve(), args.slot,
                                                    args.own_home.resolve(), args.rollout.resolve())
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=False)
        write_new(output / "invocation.json", canonical(vars_for_receipt(args)))
        try:
            (output / "native").mkdir()
            for name, raw in reads.raws.items():
                if name != "events_projection":
                    require(Path(reads.paths[name]).read_bytes() == raw, "Source changed before snapshot")
                write_new(output / "native" / (name + ".bin"), raw)
            write_new(output / "reconcile_sol_transport.py", Path(__file__).read_bytes())
            write_new(output / "response.json", response)
            write_new(output / "acceptance.json", canonical(acceptance))
            write_new(output / "reconciliation.json", canonical(receipt))
            write_new(output / "terminal.json", canonical({"state": receipt["state"], "no_resend": True,
                      "reconciliation_sha256": digest(canonical(receipt))}))
        except (OSError, ValueError):
            if not (output / "terminal.json").exists():
                write_new(output / "terminal.json", canonical({"state": "failed_private_snapshot_pending", "no_resend": True}))
            raise
    print(json.dumps({"dry_run": args.dry_run, "policy": POLICY, "accepted": receipt["accepted"],
        "abstention": receipt["abstention"], "semantic_error_count": len(receipt["semantic_errors"]),
        "verified_input_files": len(reads.raws), "receipt_sha256": digest(canonical(receipt)),
        "response_sha256": receipt["response_sha256"], "provider_calls_made": 0, "new_logical_votes": 0,
        "human_labels_released": False, "full_planned_denominator": 3108}, sort_keys=True))


def vars_for_receipt(args):
    return {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit("Sol reconciliation pending: " + type(error).__name__) from None
