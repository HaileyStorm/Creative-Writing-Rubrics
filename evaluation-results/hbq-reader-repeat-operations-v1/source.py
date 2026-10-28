"""Export the reviewed saved-operations aggregate without private locators."""
import argparse
import hashlib
import json
from pathlib import Path

INPUT_SHA256 = 'd1e42e761274559c406ce3a80f30afc9540334e14d14d1a800cedb0c6e83c637'
INPUT_BYTES = 45498
METRICS = ('input_tokens', 'output_tokens', 'cached_input_tokens',
           'reasoning_output_tokens', 'cache_write_input_tokens',
           'duration_ms', 'time_to_first_token_ms')
SUMMARY_FIELDS = ('observed', 'missing', 'sum', 'minimum', 'median', 'mean',
                  'p90_nearest_rank', 'maximum')
COHORTS = ('dryad_dev30', 'kyoto_qsf12', 'selected_repeats')


def summary(original):
    return {'accepted_requests_in_group': original['accepted_requests_in_group'],
            'metrics': {metric: {field: original['metrics'][metric][field]
                                for field in SUMMARY_FIELDS} for metric in METRICS}}


def export(input_path, output_path):
    raw = Path(input_path).read_bytes()
    if len(raw) != INPUT_BYTES or hashlib.sha256(raw).hexdigest() != INPUT_SHA256:
        raise ValueError('Exact reviewed saved-operations aggregate required')
    original = json.loads(raw)
    cohorts = {}
    for name in COHORTS:
        item = original['cohorts'][name]
        cohort = {key: item[key] for key in (
            'accepted_only', 'accepted_requests', 'membership_sha256',
            'metadata_reference_commitment_sha256')}
        cohort['origin_pointer'] = '/cohorts/' + name
        cohort['source_refs'] = {kind: {key: ref[key] for key in ('sha256', 'bytes')}
                                 for kind, ref in item['source_refs'].items()}
        cohort['binding_dispositions'] = {
            'bound_native_result': item['binding_dispositions']['bound_native_result']}
        cohort['all_accepted'] = summary(item['all_accepted'])
        cohort['by_arm'] = {arm: summary(values) for arm, values in item['by_arm'].items()}
        if 'ladder_candidate' in item:
            cohort['ladder_candidate'] = {key: item['ladder_candidate'][key] for key in (
                'additional_native_judgments', 'additive_to_parent_totals', 'interpretation',
                'operations_attribution', 'parent_accepted_requests')}
        cohorts[name] = cohort
    result = {
        'schema_version': 1,
        'state': 'PUBLIC_SAVED_ACCEPTED_OPERATIONAL_METADATA',
        'provenance': {
            'reviewed_operations': {'sha256': INPUT_SHA256, 'bytes': INPUT_BYTES},
            'producer_source_sha256': 'c1a3ef872b7cd11875dc5d98edafe4ed3a8c3bd68f5fe684b48e7b4b8f7b00b9',
            'producer_source_packet_sha256': original['source_packet_sha256'],
            'pure_extractor_summary_source_sha256': '82389bd26bdb814761ed165eb0ea4280fe7ab4b03dd81b73481ea1f874d37b5d',
            'all_membership_sha256': original['all_membership_sha256'],
            'all_metadata_reference_commitment_sha256': original['all_metadata_reference_commitment_sha256'],
            'reproduction_scope': 'Projection of retained reviewed aggregate; private native counters are not independently reconstructible from this public snapshot.'},
        'cohorts': cohorts,
        'units': {'input_tokens': 'tokens', 'output_tokens': 'tokens',
                  'cached_input_tokens': 'tokens', 'reasoning_output_tokens': 'tokens',
                  'cache_write_input_tokens': 'tokens', 'duration_ms': 'milliseconds',
                  'time_to_first_token_ms': 'milliseconds'},
        'limitations': [
            'Accepted requests only: failures, rejected or unadmitted requests and resource waits are excluded, so these are biased subsets of total collection operations.',
            'Request counts are not complete-story denominators. Selected repeats are a selected reliability population, not human agreement.',
            'Native task duration is not isolated inference latency, collection wall-clock time or throughput. TTFT is only the recorded native field.',
            'Cached input and reasoning output tokens are subset categories; do not add token categories together.',
            'Missing fields remain missing, not zero. Summary means and percentiles use only observed values for that metric.',
            'Ladder shares HBQ parent judgments: zero additional native judgments and no duplicate token attribution. Local scoring cost is not measured.',
            'These aggregates do not establish billing, price, account usage, quality superiority, model identity or backend attestation.',
            'The exporter copies existing summaries; it performs no new analysis, replay, bootstrap, judgment or target read.'],
        'new_statistics': False}
    encoded = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with Path(output_path).open('xb') as stream:
        stream.write(encoded)
    print(json.dumps({'sha256': hashlib.sha256(encoded).hexdigest(), 'bytes': len(encoded)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    export(args.input, args.output)


if __name__ == '__main__':
    main()
