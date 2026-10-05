"""Provider-free v6 witnesses; subprocesses are the retained synthetic CLI only."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path.home() / ".codex/tools"
sys.path.insert(0, str(TOOLS))
from model_work_queue import broker as installed_broker
from model_work_queue.adapters import grok_exec as installed_adapter
from model_work_queue import arm_grok_routes as installed_armer
from model_work_queue import test_grok_adapter as synthetic

HERE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-grok-longform-transport-v6"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


d = load("cwr_v6_test_derived", HERE / "derived.py")
entry = load("cwr_v6_test_entry", HERE / "adapters/grok_exec.py")
armer_entry = load("cwr_v6_test_armer", HERE / "arm.py")


class GrokLongformV6Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = synthetic.GrokAdapterTests(methodName="runTest")
        self.fixture.setUp()
        self.b = d.load_broker()
        self.a = d.load_adapter()
        self.fixture.broker = self.b.Broker(self.fixture.root, grok_host_gate_path=self.fixture.grok_host_gate)

    def tearDown(self):
        self.fixture.tearDown()

    def route(self, scenario="completed"):
        route = self.fixture.route(scenario, timeout_seconds=900)
        command = [sys.executable, str(HERE / "adapters/grok_exec.py"), "--tools-root", str(TOOLS)]
        route.update(command=command, command_identity=self.fixture.identity(command),
                     nonvisual_transport_contract=d.CONTRACT_NAME)
        route["capabilities"].append(d.CONTRACT_NAME)
        return route

    def contact(self, prompt="synthetic", scenario="completed"):
        route = self.route(scenario)
        self.fixture.write_route(route)
        return self.fixture.broker.run_grok_native_request(route["name"], {"prompt": prompt})

    def test_private_projections_preserve_canonical_modules_and_files(self):
        raw_before = {k: (TOOLS / "model_work_queue" / k).read_bytes() for k in d.SOURCE_PINS}
        originals = [sys.modules["model_work_queue.broker"], sys.modules["model_work_queue.adapters.grok_exec"],
                     sys.modules["model_work_queue.arm_grok_routes"]]
        profile = d.profile_commitment()
        derived_armer = d.load_armer()
        self.assertEqual(6, self.a.NONVISUAL_V5_ADAPTER_VERSION)
        self.assertEqual(d.CONTRACT, self.a.V5_NONVISUAL_TRANSPORT_CONTRACT)
        self.assertEqual(d.CONTRACT, self.b.GROK_NONVISUAL_TRANSPORT_V5)
        self.assertIs(derived_armer.Broker, self.b.Broker)
        self.assertEqual(str(HERE / "arm.py"), derived_armer.__file__)
        self.assertIs(originals[0], sys.modules["model_work_queue.broker"])
        self.assertIs(originals[1], sys.modules["model_work_queue.adapters.grok_exec"])
        self.assertIs(originals[2], sys.modules["model_work_queue.arm_grok_routes"])
        self.assertEqual(5, installed_adapter.NONVISUAL_V5_ADAPTER_VERSION)
        self.assertEqual("grok_nonvisual_history_v5", installed_broker.GROK_NONVISUAL_TRANSPORT_CONTRACT_NAME)
        self.assertEqual(12, installed_armer.ARMER_VERSION)
        self.assertEqual(raw_before, {k: (TOOLS / "model_work_queue" / k).read_bytes() for k in d.SOURCE_PINS})
        self.assertEqual(profile, d.profile_commitment())

    def test_missing_changed_sources_and_changed_entry_loader_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, "absent"):
                d.pinned_sources(root)
            for name in d.SOURCE_PINS:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((TOOLS / "model_work_queue" / name).read_bytes())
            (root / "broker.py").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "differs"):
                d.pinned_sources(root)
        with patch.object(entry, "LOADER_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "loader pin"):
                entry.implementation(TOOLS)

    def test_independent_serialization_and_first_line_bounds(self):
        contract = d.CONTRACT
        self.assertEqual(b"x" * 400000, self.a._read_bounded_stdin(io.BytesIO(b"x" * 400000), 400000))
        with self.assertRaisesRegex(ValueError, "out of bounds"):
            self.a._read_bounded_stdin(io.BytesIO(b"x" * 400001), 400000)
        session = "00000000-0000-4000-8000-000000000000"
        for prompt, expected in [("x" * 390000, True), ("\U0010ffff" * 90000, False)]:
            self.assertLessEqual(len(prompt.encode()), 400000)
            self.assertEqual(expected, self.b._grok_nonvisual_prompt_history_fits(session, prompt, contract))
            self.assertEqual(expected, self.a._nonvisual_prompt_history_fits(session, prompt, contract))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "updates.jsonl"
            large = b'{"value":"' + b"x" * 390000 + b'"}'
            small = b'{"value":"ok"}'
            path.write_bytes(large + b"\n" + small + b"\n")
            self.assertEqual(2, len(self.a._read_bounded_updates(path, transport_contract=contract)[0]))
            path.write_bytes(small + b"\n" + large + b"\n")
            with self.assertRaisesRegex(ValueError, "line is invalid"):
                self.a._read_bounded_updates(path, transport_contract=contract)

    def test_oversized_prompt_stops_before_contact_callback(self):
        route = self.route()
        self.fixture.write_route(route)
        calls = []
        outcome = self.fixture.broker.run_grok_native_request(route["name"], {"prompt": "x" * 400001},
                                                              before_contact=lambda: calls.append(True))
        self.assertEqual("definitely_not_contacted", outcome["state"])
        self.assertEqual("nonvisual_prompt_too_large", outcome["failure"]["code"])
        self.assertEqual([], calls)

    def test_synthetic_long_prompt_native_completion_and_receipt_bindings(self):
        prompt = "x" * 150000
        outcome = self.contact(prompt)
        self.assertEqual("completed", outcome["state"], outcome)
        result = outcome["result"]
        runtime = result["runtime"]
        self.assertEqual(6, runtime["adapter_version"])
        self.assertEqual(d.CONTRACT, runtime["execution_contract"]["nonvisual_transport_contract"])
        self.assertEqual(d.digest(prompt.encode()), runtime["execution_contract"]["staged_prompt_sha256"])
        self.assertEqual(1, runtime["observed_turns"])
        self.assertEqual("deny_wins_none_attested", runtime["execution_contract"]["tools"])
        route = self.fixture.broker._load_registry_live()["routes"][0]
        raw = self.b._canonical({"control": {"version": 1, "state": "completed"}, "result": result})
        envelope = json.loads(self.fixture.broker.read_grok_native_envelope(result["native_envelope_artifact"]))
        for mutation in ["version", "contract", "prompt"]:
            changed = json.loads(raw)
            if mutation == "version": changed["result"]["runtime"]["adapter_version"] = 5
            elif mutation == "contract": changed["result"]["runtime"]["execution_contract"]["nonvisual_transport_contract"]["prompt_utf8_bytes"] -= 1
            else: changed["result"]["runtime"]["execution_contract"]["staged_prompt_sha256"] = "0" * 64
            parsed = self.fixture.broker._parse_grok_exec_envelope(self.b._canonical(changed), route,
                {"prompt": prompt}, expected_session_id=envelope["sessionId"])
            self.assertEqual("ambiguous", parsed.state)

    def test_tools_wrong_session_and_extra_turns_remain_unadmitted(self):
        for scenario in ["tool_list_dir", "mismatched_session", "turn2", "added_final_lf"]:
            with self.subTest(scenario=scenario):
                self.assertEqual("ambiguous", self.contact(scenario=scenario)["state"])

    def test_entry_requires_one_turn_exact_timeout_and_contract_before_stdin(self):
        for turns, timeout, contract in [(2, 900, d.CONTRACT), (1, 300, d.CONTRACT),
                                         (1, 900, installed_adapter.V5_NONVISUAL_TRANSPORT_CONTRACT)]:
            output = io.StringIO()
            entry.run(["--tools-root", str(TOOLS), "--nonvisual-max-turns", str(turns),
                       "--timeout-seconds", str(timeout), "--nonvisual-transport-contract-json",
                       d.canonical(contract).decode()], stdin=io.BytesIO(b"must-not-be-read"), stdout=output)
            self.assertEqual("definitely_not_contacted", json.loads(output.getvalue())["control"]["state"])

    def test_host_gate_preserves_v5_conflict_and_quiescent_rearm(self):
        old = installed_broker.Broker(self.fixture.root, grok_host_gate_path=self.fixture.grok_host_gate)
        v5 = self.fixture.route(broker=old, timeout_seconds=900)
        v5["capabilities"].append(installed_broker.GROK_NONVISUAL_TRANSPORT_CAPABILITY)
        v5["nonvisual_transport_contract"] = installed_broker.GROK_NONVISUAL_TRANSPORT_CONTRACT_NAME
        old._authorize_grok_host_gate(v5)
        v6 = self.route()
        state, _, token = old._acquire_grok_host_slot(v5, 900)
        self.assertEqual("healthy", state)
        with self.assertRaisesRegex(self.b.QueueError, "calls are active"):
            self.fixture.broker._authorize_grok_host_gate(v6)
        old._release_grok_host_slot(token)
        self.fixture.broker._authorize_grok_host_gate(v6)
        self.assertEqual("reauthorization_required", old._acquire_grok_host_slot(v5, 900)[0])
        state, _, token = self.fixture.broker._acquire_grok_host_slot(v6, 900)
        self.assertEqual("healthy", state)
        self.fixture.broker._release_grok_host_slot(token)

    def test_armer_rejects_old_geometry_without_launching_version_check(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            source.write_text(json.dumps({"schema_version": 3, "allowance_evidence": "standing_owner_authorization"}))
            calls = []
            with self.assertRaisesRegex(ValueError, "historical standing"):
                armer_entry.arm(Path(folder) / "root", subscription_evidence=source,
                    runner=lambda command: calls.append(command))
            self.assertEqual([], calls)

    def test_synthetic_armer_binds_real_entry_and_v6_fixed_geometry(self):
        now = synthetic.dt.datetime.now(synthetic.dt.timezone.utc)
        evidence = {"schema_version": 1, "provider": "xai_grok_build", "account_class": "subscription",
            "allowance_state": "available", "allowance_evidence": "owner_attested_current_subscription_allowance_v1",
            "checked_at": now.isoformat(), "expires_at": (now + synthetic.dt.timedelta(days=1)).isoformat(),
            "saved_session": {"present": True, "location_hash": "9" * 64},
            "catalog": {"cli_version": "grok build fixture 1.0", "mappings": [{"requested": "grok-4.7",
                "reported": "grok-4.7-build", "reasoning_attested": False}]}, "audit": {"source": "fixture", "reference": "fixture"}}
        base = Path(self.fixture.temp.name)
        source = base / "arm-source.json"; source.write_text(json.dumps(evidence))
        executable = base / "fixture.exe"; executable.write_bytes(b"not executable; version runner is mocked")
        root = base / "arm-v6"
        result = armer_entry.arm(root, subscription_evidence=source, grok_executable=executable, env={},
            grok_host_gate_path=base / "isolated-arm-gate.sqlite3",
            runner=lambda _: (0, b"grok build fixture 1.0\n", b""))
        route = next(r for r in self.b.Broker(root)._load_registry_live()["routes"] if r["adapter"] == "grok_exec")
        self.assertEqual(d.CONTRACT_NAME, route["nonvisual_transport_contract"])
        self.assertEqual(1, route["nonvisual_max_turns"])
        self.assertEqual(900, route["timeout_seconds"])
        self.assertEqual(str(HERE / "adapters/grok_exec.py"), route["command"][1])
        self.assertEqual(["--tools-root", str(TOOLS)], route["command"][-2:])
        self.assertTrue(result["nonvisual_history_v6"])
        self.assertNotIn("nonvisual_history_v5", result)
