from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v11-child20-train-screen-v1"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")


def module():
    spec = importlib.util.spec_from_file_location("v11_train", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def route_provider():
    now = datetime.now(timezone.utc)
    route = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "account_class": "subscription", "identity_evidence": "requested_only", "zero_charge": True, "armed": True, "health": "healthy", "trusted": True, "reasoning_effort": "high", "grok_command": ["fixture"], "grok_command_identity": {"version": 1, "artifacts": []}, "cli_version_identity": {"version": 1, "artifacts": []}, "grok_cli_version": "fixture", "subscription_receipt_hash": "2" * 64, "cost_evidence": {"allowance_state": "available", "checked_at": (now - timedelta(seconds=1)).isoformat(), "evidence_hash": "1" * 64, "expires_at": (now + timedelta(minutes=10)).isoformat(), "kind": "subscription_included", "version": 1}, "allowed_payload_classes": ["public_repo"], "timeout_seconds": 1.0}
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    evidence = {"route_name": route["name"], "route_sha256": hashlib.sha256(canonical(route)).hexdigest(), "cost_evidence_hash": route["cost_evidence"]["evidence_hash"], "subscription_receipt_hash": route["subscription_receipt_hash"], "grok_cli_version": route["grok_cli_version"], "cli_version_identity_sha256": hashlib.sha256(canonical(route["cli_version_identity"])).hexdigest(), "grok_command_identity_sha256": hashlib.sha256(canonical(route["grok_command_identity"])).hexdigest(), "registry_sha256": "3" * 64}
    return lambda _queue: (route, evidence)


def native_runner(value, contacts: list[str], errors: list[str] | None = None):
    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        assert json.loads(schema_path.read_bytes())['required'] == ['scores', 'evidence', 'coverage']
        token = output_dir.name
        score = float(1 + int(token[-1], 16) % 4)
        structured = {
            'scores': {dimension: score for dimension in value.DIMS},
            'evidence': {dimension: f'{dimension} is grounded in the submitted story.' for dimension in value.DIMS},
            'coverage': {dimension: True for dimension in value.DIMS},
        }
        response = json.dumps({
            'modelUsage': {'grok-4.6-build': {'inputTokens': 2, 'outputTokens': 2, 'cacheReadInputTokens': 0, 'cacheCreationInputTokens': 0, 'modelCalls': 1, 'costUSD': 0.0}},
            'num_turns': 1,
            'requestId': f'request-{token}',
            'sessionId': f'session-{token}',
            'stopReason': 'end_turn',
            'structuredOutput': structured,
            'text': json.dumps(structured, sort_keys=True, separators=(',', ':')),
            'thought': 'I evaluated the supplied story against every requested criterion.',
            'total_cost_usd': 0.0,
            'total_cost_usd_ticks': 0,
            'usage': {'input_tokens': 2, 'output_tokens': 2, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0, 'reasoning_tokens': 0, 'total_tokens': 4},
        }, ensure_ascii=False, indent=2).encode()
        responses = output_dir / 'responses'
        responses.mkdir()
        (responses / 'batch-0001.attempt-0001.prompt.txt').write_bytes(prompt)
        try:
            before_contact()
        except ValueError as error:
            if errors is not None:
                errors.append(str(error))
            raise
        contacts.append(token)
        (responses / 'batch-0001.attempt-0001.grok.envelope.json').write_bytes(response)
        return {
            'native_request_bytes': json.dumps({'prompt': prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode(),
            'native_response_bytes': response,
            'identity': {'provider': 'xai', 'requested_model': 'grok-4.6', 'reported_model': 'grok-4.6-build', 'request_id': f'request-{token}', 'session_id': f'session-{token}', 'native_endpoint_contact_cardinality': 'unproven', 'tools_enabled': False},
            'effective_settings': {'route_name': route['name'], 'adapter': 'grok_exec', 'requested_model': 'grok-4.6', 'reported_model': 'grok-4.6-build', 'requested_reasoning_effort': 'high', 'tools_enabled': False, 'web_search_enabled': False, 'subagents_enabled': False, 'tool_free_argv': ['--max-turns', '1', '--no-leader', '--no-subagents', '--disable-web-search', '--no-plan', '--tools', '', '--permission-mode', 'dontAsk', '--sandbox', 'read-only', '--verbatim'], 'system_prompt_override': 'Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.', 'sampler': {'batch_number': 1, 'attempt_number': 1, 'timeout_seconds': 1.0, 'nonvisual_max_turns': 1}, 'runner_prompt_artifact_sha256': value.sha256(prompt), 'reasoning_attested': False},
        }

    return run


def test_exact_train_schedule_has_eight_paired_payloads_and_local_targets_only():
    value = module(); schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    assert len(schedule["cells"]) == 8 and {row["partition"] for row in schedule["cells"]} == {"train"}
    assert {row["candidate_id"] for row in schedule["cells"]} == {value.BASELINE, value.CHILD20}
    assert all(row["endpoint_payload_sha256s"]["grok_primary"] == row["endpoint_payload_sha256s"]["sol_later"] for row in schedule["cells"])
    assert all("target" not in json.loads(base64.b64decode(row["payload_base64"])) for row in schedule["cells"])
    aliases = {row['item_id']: row for row in value.source_items(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)}
    assert value.SOURCE_ALIASES == {
        'item-09006dab15b970e6': {'story_id': '925', 'source_model': 'HINT'},
        'item-f0124faa5a62734e': {'story_id': '403', 'source_model': 'GPT-2 (tag)'},
        'item-b5161cbf50b87beb': {'story_id': '594', 'source_model': 'RoBERTa'},
        'item-8c65749a245496a2': {'story_id': '225', 'source_model': 'CTRL'},
    }
    assert set(aliases) == set(value.SOURCE_ALIASES)


def test_real_lower_lifecycle_prepares_exactly_eight_zero_contact_cells(tmp_path: Path):
    value = module()
    prepared = value.prepare_all(output_root=tmp_path / "output", queue_root=tmp_path / "queue", authorization_acknowledgement_sha256="a" * 64, split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT, route_provider=route_provider())
    assert prepared["logical_cells"] == len(prepared["prepared_cells"]) == 8
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0


def test_execute_eight_uses_the_prepared_lower_lifecycle_once_per_bound_cell(tmp_path: Path):
    value = module()
    common = {'output_root': tmp_path / 'output', 'queue_root': tmp_path / 'queue', 'authorization_acknowledgement_sha256': 'a' * 64, 'split_manifest': SPLIT, 'hanna_csv': CSV, 'successor_contract': CONTRACT, 'route_provider': route_provider()}
    value.prepare_all(**common)
    contacts: list[str] = []
    errors: list[str] = []
    results = value.execute_eight(**common, allow_remote=True, runner=native_runner(value, contacts, errors))
    assert errors == []
    assert len(results) == len(contacts) == 8
    assert all(result.get('process_launches') == 1 and result.get('native_endpoint_contact_cardinality') == 'unproven' for result in results), results
    assert all((common['output_root'] / name / 'native-response.bin').is_file() for name in contacts)
    report = value.report(**{key: common[key] for key in common if key != 'queue_root' and key != 'route_provider'})
    assert report['endpoint'] == 'grok_primary' and report['partition'] == 'train'
    assert len(report['cells']) == report['unique_request_ids'] == report['unique_session_ids'] == 8
    assert all(set(cell['scores']) == set(value.DIMS) and all(isinstance(score, float) for score in cell['scores'].values()) for cell in report['cells'])
    assert report['later_matched_sol8_gate']['promotion'] == 'none'
    assert report['later_matched_sol8_gate']['satisfied'] is report['comparison']['strict_mean_mae_improvement']
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    expected = {row['cell_id']: sum(abs(json.loads((common['output_root'] / row['cell_id'] / 'native-response.bin').read_bytes())['structuredOutput']['scores'][dimension] - row['target'][dimension]) for dimension in value.DIMS) / len(value.DIMS) for row in schedule['cells']}
    assert {cell['cell_id']: cell['mae'] for cell in report['cells']} == expected
    before = {path.relative_to(common['output_root']).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in common['output_root'].rglob('*') if path.is_file()}

    def must_not_run(**_kwargs):
        raise AssertionError('replayed cell invoked its runner')

    with pytest.raises(ValueError, match='no resend'):
        value.execute_one(**common, cell_id=contacts[0], allow_remote=True, runner=must_not_run)
    after = {path.relative_to(common['output_root']).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in common['output_root'].rglob('*') if path.is_file()}
    assert after == before

    original_bound = value.bound

    def reject_collision(field: str):
        @contextmanager
        def collided_bound(**kwargs):
            with original_bound(**kwargs) as (lifecycle, runtime, v9):
                admit = lifecycle.admit

                def duplicate(*args):
                    request, response, identity, settings = admit(*args)
                    altered = dict(identity)
                    altered[field] = 'duplicate-' + field
                    return request, response, altered, settings

                lifecycle.admit = duplicate
                try:
                    yield lifecycle, runtime, v9
                finally:
                    lifecycle.admit = admit

        value.bound = collided_bound
        try:
            with pytest.raises(ValueError, match='duplicate or invalid native identity'):
                value.report(**{key: common[key] for key in common if key != 'queue_root' and key != 'route_provider'})
        finally:
            value.bound = original_bound

    reject_collision('request_id')
    reject_collision('session_id')

    @contextmanager
    def mixed_route_bound(**kwargs):
        with original_bound(**kwargs) as (lifecycle, runtime, v9):
            strict = v9.strict
            prepared = 0

            def mixed(raw, label):
                nonlocal prepared
                value = strict(raw, label)
                if label == 'prepared':
                    prepared += 1
                    if prepared == 2:
                        value = dict(value)
                        route = dict(value['route'])
                        route['name'] = 'mixed-route'
                        value['route'] = route
                return value

            v9.strict = mixed
            try:
                yield lifecycle, runtime, v9
            finally:
                v9.strict = strict

    value.bound = mixed_route_bound
    try:
        with pytest.raises(ValueError, match='mixed receipt route or evidence'):
            value.report(**{key: common[key] for key in common if key != 'queue_root' and key != 'route_provider'})
    finally:
        value.bound = original_bound
    (common['output_root'] / contacts[0] / 'native-response.bin').write_bytes(b'{}\n')
    with pytest.raises(ValueError):
        value.report(**{key: common[key] for key in common if key != 'queue_root' and key != 'route_provider'})


def test_precontact_prepared_mutation_is_rejected_without_contact(tmp_path: Path):
    value = module()
    common = {'output_root': tmp_path / 'output', 'queue_root': tmp_path / 'queue', 'authorization_acknowledgement_sha256': 'a' * 64, 'split_manifest': SPLIT, 'hanna_csv': CSV, 'successor_contract': CONTRACT, 'route_provider': route_provider()}
    cell_id = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)['cells'][0]['cell_id']
    value.prepare_all(**common)
    contacts: list[str] = []
    clean = native_runner(value, contacts)

    def mutate_then_run(**kwargs):
        (kwargs['output_dir'] / 'prepared.json').write_bytes(b'{}\n')
        return clean(**kwargs)

    result = value.execute_one(**common, cell_id=cell_id, allow_remote=True, runner=mutate_then_run)
    assert contacts == [] and result['process_launches'] == 0
    with pytest.raises((ValueError, TypeError), match='ambiguous'):
        value.report(**{key: common[key] for key in common if key != 'queue_root' and key != 'route_provider'})
