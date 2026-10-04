"""A native ambiguity stops the suffix and cannot be resent on restart."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ttcw_collector_test_subject', HERE/'collector.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
sys.path.insert(0,str(collector.TOOLS))


def fixture_manifest(tmp_path):
    root = tmp_path/'frozen'
    root.mkdir()
    artifacts = {'prompt.txt':b'Synthetic scene.', 'schema.json':b'{"type":"object","properties":{},"required":[],"additionalProperties":false}',
                 'input.txt':b'Synthetic scene.'}
    for name, raw in artifacts.items():
        (root/name).write_bytes(raw)
    requests = []
    for ordinal in range(1,4):
        row = {'endpoint':'grok','endpoint_ordinal':ordinal,'logical_sample_id':str(ordinal)*64,'arm':'pairwise',
            'prompt_path':'prompt.txt','prompt_sha256':collector.digest(artifacts['prompt.txt']),
            'schema_path':'schema.json','schema_sha256':collector.digest(artifacts['schema.json']),
            'sources':[{'id':'synthetic','input_path':'input.txt','sha256':collector.digest(artifacts['input.txt'])}]}
        row['request_sha256']=collector.digest(collector.canonical(row)+b'\n')
        requests.append(row)
    manifest={'artifacts':{name:{'sha256':collector.digest(raw),'bytes':len(raw)} for name,raw in artifacts.items()},'requests':requests}
    from model_work_queue.adapters import json_schema_subset
    manifest['implementation']={'semantic_validator_sha256':collector.digest((HERE/'validate_response.py').read_bytes()),
        'schema_subset_sha256':collector.digest(Path(json_schema_subset.__file__).read_bytes())}
    manifest['manifest_content_sha256']=collector.digest(collector.canonical(manifest)+b'\n')
    (root/'manifest.json').write_bytes(collector.canonical(manifest)+b'\n')
    route_root=tmp_path/'route'
    route_root.mkdir()
    (route_root/'routes.json').write_text(json.dumps({'routes':[{'name':'grok-build-grok-4.7','model':'grok-4.7','destination':'xai_grok_build_subscription'}]}))
    return root/'manifest.json',tmp_path/'results',route_root


def set_args(monkeypatch, manifest, results, route, *extra):
    monkeypatch.setattr(sys,'argv',['collector','--manifest',str(manifest),'--results-dir',str(results),'--endpoint','grok',
        '--route-root',str(route),'--workers','1',*extra])


def test_ambiguity_preserves_prefix_stops_suffix_and_forbids_resend(tmp_path,monkeypatch):
    manifest,results,route=fixture_manifest(tmp_path)
    from model_work_queue import broker
    calls=[]
    class FailedBroker:
        def __init__(self, root):
            pass
        def run_grok_native_request(self,*args,**kwargs):
            kwargs['before_contact']()
            calls.append(args[1]['prompt'])
            return {'state':'ambiguous','result':None,'failure':{'code':'unclassified_after_launch'}}
    monkeypatch.setattr(broker,'Broker',FailedBroker)
    set_args(monkeypatch,manifest,results,route)
    assert collector.main()==3
    assert len(calls)==1
    folders=[p for p in results.iterdir() if p.is_dir()]
    assert len(folders)==1 and (folders[0]/'attempt-started.json').is_file()
    original=(folders[0]/'native-result.json').read_bytes()
    with pytest.raises(ValueError,match='reconciliation; no resend'):
        collector.main()
    assert len(calls)==1 and (folders[0]/'native-result.json').read_bytes()==original


def test_validate_only_never_constructs_broker_or_reserves_output(tmp_path,monkeypatch):
    manifest,results,route=fixture_manifest(tmp_path)
    from model_work_queue import broker
    def forbidden(*args,**kwargs):
        raise AssertionError('Validation must not construct provider control plane')
    monkeypatch.setattr(broker,'Broker',forbidden)
    set_args(monkeypatch,manifest,results,route,'--validate-only')
    assert collector.main()==0 and not results.exists()
