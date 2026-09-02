from __future__ import annotations

import base64
import importlib.util
import inspect
import json
import os
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1];PACKAGE=ROOT/'evaluation-results'/'hbq-human-alignment-optimizer-v10-fresh96-confirmation-sol-exec-v1'
V9_NATIVE_ROOT=Path('C:/Users/Haile/Documents/cwr-desc18-broad-sol-veto-926f8f1-20260901a')
def module():
 s=importlib.util.spec_from_file_location('v10sol',PACKAGE/'executor.py');assert s and s.loader;m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def _answer(mod, *, score=3, covered=True, evidence='The final agent message cites the writing.'):
 return {'scores':{name:score for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')},'evidence':{name:evidence for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')},'coverage':{name:covered for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')}}

def _native_route(mod, lifecycle, runtime):
 try: proof_path=next(V9_NATIVE_ROOT.rglob('zero-charge-route-proof.json'))
 except StopIteration: pytest.skip('V9 native lifecycle fixture not supplied')
 proof=json.loads(proof_path.read_text(encoding='utf-8'))
 return lifecycle.sol_v4()._frozen_route(proof['route'],proof['route_evidence'],runtime._load_v3(),require_unexpired=False)

def _write_prepared_cell(mod, runtime, row, root, route, evidence, acknowledgement):
 root.mkdir(); payload=base64.b64decode(row['payload_base64'],validate=True); schema=mod.canonical(json.loads(payload.decode('utf-8'))['response_schema'])
 for name,raw in runtime._prepared(row,payload,schema,row['target'],route,evidence,acknowledgement).items(): (root/name).write_bytes(raw)

def _write_terminal_cell(mod, runtime, row, output, queue, route, evidence, acknowledgement, index):
 root=output/row['cell_id']; _write_prepared_cell(mod,runtime,row,root,route,evidence,acknowledgement)
 v3=runtime._load_v3(); original_route=runtime._route; interim=mod.canonical(_answer(mod,score=0,covered=False,evidence='interim')).decode('utf-8').strip(); final=mod.canonical(_answer(mod,evidence=f'The final agent message cites writing cell {index}.')).decode('utf-8').strip(); thread=f'fixture-thread-{index}'
 def invoke(**kwargs):
  responses=kwargs['output_dir']/'responses'; responses.mkdir(); kwargs['before_provider_attempt'](); events='\n'.join(json.dumps(value,separators=(',',':')) for value in ({'type':'thread.started','thread_id':thread},{'type':'turn.started'},{'type':'item.started','item':{'id':'m1','type':'agent_message','text':''}},{'type':'item.completed','item':{'id':'m1','type':'agent_message','text':interim}},{'type':'item.completed','item':{'id':'m2','type':'agent_message','text':final}},{'type':'turn.completed','usage':{}}))+'\n'; raw=events.encode('utf-8'); (responses/'batch-0001.attempt-0001.events.jsonl').write_bytes(raw); (responses/'batch-0001.attempt-0001.message.json').write_bytes(final.encode('utf-8')); (kwargs['output_dir']/'raw-codex-stderr.bin').write_bytes(b''); return final,{'command':v3._expected_codex_command(kwargs['executable'],kwargs['output_dir']),'reported':v3._strict_stderr_labels(b''),'provider_artifacts':{'codex_events':{'path':'responses/batch-0001.attempt-0001.events.jsonl','bytes':len(raw),'sha256':mod.sha256(raw)},'codex_stderr':{'path':'raw-codex-stderr.bin','bytes':0,'sha256':mod.sha256(b'')}}}
 runtime._route=lambda *_args,**_kwargs:(route,evidence,v3)
 try: result=runtime.execute_one(output_root=output,cell_id=row['cell_id'],queue_root=queue,authorization_acknowledgement_sha256=acknowledgement,allow_remote=True,call_codex=invoke)
 finally: runtime._route=original_route
 assert result=={'cell_id':row['cell_id'],'state':'reconcile_required_after_process_launch','process_launches':1,'provider_calls_made':None}

def _write_normal_cell(mod, runtime, row, output, queue, route, evidence, acknowledgement, index, *, thread=None):
 v3=runtime._load_v3(); original_route=runtime._route; final=mod.canonical(_answer(mod,evidence=f'Normal receipt evidence cites writing cell {index}.')).decode('utf-8').strip(); thread=thread or f'normal-thread-{index}'
 def invoke(**kwargs):
  root=kwargs['output_dir']; responses=root/'responses'; responses.mkdir(); kwargs['before_provider_attempt'](); events='\n'.join(json.dumps(value,separators=(',',':')) for value in ({'type':'thread.started','thread_id':thread},{'type':'turn.started'},{'type':'item.started','item':{'id':'m1','type':'agent_message','text':''}},{'type':'item.completed','item':{'id':'m1','type':'agent_message','text':final}},{'type':'turn.completed','usage':{}}))+'\n'; raw=events.encode('utf-8'); (responses/'batch-0001.attempt-0001.events.jsonl').write_bytes(raw); (responses/'batch-0001.attempt-0001.message.json').write_bytes(final.encode('utf-8')); (root/'raw-codex-stderr.bin').write_bytes(b''); return final,{'command':v3._expected_codex_command(kwargs['executable'],root),'reported':v3._strict_stderr_labels(b''),'provider_artifacts':{'codex_events':{'path':'responses/batch-0001.attempt-0001.events.jsonl','bytes':len(raw),'sha256':mod.sha256(raw)},'codex_stderr':{'path':'raw-codex-stderr.bin','bytes':0,'sha256':mod.sha256(b'')}}}
 runtime._route=lambda *_args,**_kwargs:(route,evidence,v3)
 try: runtime.execute_one(output_root=output,cell_id=row['cell_id'],queue_root=queue,authorization_acknowledgement_sha256=acknowledgement,allow_remote=True,call_codex=invoke)
 finally: runtime._route=original_route

def _terminal_output(mod, tmp_path):
 freeze=os.getenv('CWR_V10_FREEZE_ROOT')
 if not freeze: pytest.skip('external frozen root not supplied')
 resolution=mod._resolution(Path(freeze)); lifecycle,runtime=mod._runtime(resolution); route,evidence=_native_route(mod,lifecycle,runtime); output=tmp_path/'terminal-output'; output.mkdir(parents=True); queue=tmp_path/'queue'; queue.mkdir(); acknowledgement='a'*64
 for index,row in enumerate(resolution['rows']): _write_terminal_cell(mod,runtime,row,output,queue,route,evidence,acknowledgement,index)
 return Path(freeze),resolution,output,acknowledgement

def _mixed_output(mod, tmp_path, *, normal_cells, duplicate_cross_class=False):
 freeze=os.getenv('CWR_V10_FREEZE_ROOT')
 if not freeze: pytest.skip('external frozen root not supplied')
 resolution=mod._resolution(Path(freeze)); lifecycle,runtime=mod._runtime(resolution); route,evidence=_native_route(mod,lifecycle,runtime); output=tmp_path/'mixed-output'; output.mkdir(parents=True); queue=tmp_path/'queue'; queue.mkdir(); acknowledgement='a'*64
 for index,row in enumerate(resolution['rows']):
  root=output/row['cell_id']
  if index < normal_cells: _write_prepared_cell(mod,runtime,row,root,route,evidence,acknowledgement)
  else: _write_terminal_cell(mod,runtime,row,output,queue,route,evidence,acknowledgement,index)
 for index,row in enumerate(resolution['rows'][:normal_cells]): _write_normal_cell(mod,runtime,row,output,queue,route,evidence,acknowledgement,index,thread='fixture-thread-1' if duplicate_cross_class and index==0 else None)
 return Path(freeze),resolution,output,queue,acknowledgement
def test_contract_is_measurement_only():
 value=module().validate_package()
 assert value['authority']['confirmation']=='measurement_only' and value['authority']['endpoint_pooling']=='forbidden'
 assert value['pins']['hanna_csv_sha256']=='ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b'
 source=(PACKAGE/'executor.py').read_text().lower()
 assert 'import dspy' not in source and 'import optuna' not in source
def test_external_frozen_rows_are_exact_and_tool_free():
 root=os.getenv('CWR_V10_FREEZE_ROOT')
 if not root:pytest.skip('external frozen root not supplied')
 rows=module()._rows(Path(root));assert len(rows)==64 and {x['candidate_id'] for x in rows}=={'candidate-102cc7f06c9a99a7','broader-nextwave-20-missing_evidence_not_no-referent-evidence'}
 assert len({(x['candidate_id'],x['item_id']) for x in rows})==64 and all(x['payload_parity']=='frozen_fresh96_schedule_exact_payload_bytes' for x in rows)

def test_response_quality_does_not_reject_ordinary_placeholder_wording():
 value={'scores':{name:3 for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')},'evidence':{name:'Placeholders are a story device here.' for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')},'coverage':{name:True for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')}}
 assert module().validate_response_quality(value)==value

def test_wave_is_explicit_and_terminal_safe_without_resend():
 mod=module();parameters=inspect.signature(mod.execute_wave).parameters
 assert set(parameters)=={'output_root','freeze_root','queue_root','authorization_acknowledgement_sha256','allow_remote','broker_factory','call_codex'}
 source=(PACKAGE/'executor.py').read_text()
 assert 'def _pending_rows' in source and 'terminal_names' in source and 'pool.map(run, pending)' in source

def test_collector_and_prepared_metadata_are_v10_measurement_only():
 source=(PACKAGE/'executor.py').read_text()
 assert 'Path(collector_output), HERE, REPO, Path(output_root), Path(queue_root)' in source
 assert 'sol_role": "measurement_only_after_grok_qualification"' in source
 assert '"independently_replayed_grok_result_internal_sha256"' in source
 assert 'def reconcile_existing_output' in source and 'def _terminal_projection' in source

def test_reconcile_rejects_minimal_fabricated_terminal_jsonl(tmp_path):
 root=os.getenv('CWR_V10_FREEZE_ROOT')
 if not root: pytest.skip('external frozen root not supplied')
 mod=module();rows=mod._rows(Path(root));output=tmp_path/'terminal-output';output.mkdir()
 final={'scores':{name:3 for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')},'evidence':{name:'The final agent message cites the writing.' for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')},'coverage':{name:True for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')}}
 for row in rows:
  cell=output/row['cell_id'];cell.mkdir();(cell/'result.json').write_bytes(mod.canonical({'format_version':1,'study_id':mod.STUDY_ID,'kind':'reconcile_required_after_process_launch','cell_id':row['cell_id'],'process_launches':1,'provider_calls_made':None,'error_type':'ValueError'}))
  events='\n'.join((json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'{"interim":true}'}}),json.dumps({'type':'item.completed','item':{'type':'agent_message','text':mod.canonical(final).decode().strip()}})))+'\n'
  (cell/'responses').mkdir(); (cell/'responses'/'batch-0001.attempt-0001.events.jsonl').write_text(events,encoding='utf-8')
 with pytest.raises(ValueError,match='prepared|inventory'):
  mod.reconcile_existing_output(output_root=output,freeze_root=Path(root),authorization_acknowledgement_sha256='a'*64)

def test_reconcile_replays_complete_v10_terminal_lifecycle_without_resend(tmp_path):
 mod=module(); freeze,_resolution,output,acknowledgement=_terminal_output(mod,tmp_path); queue=tmp_path/'queue'; collector=tmp_path/'collector.json'
 value=mod.reconcile_existing_output(output_root=output,freeze_root=freeze,authorization_acknowledgement_sha256=acknowledgement)
 assert len(value['cells'])==64 and value['provider_calls_made']==0 and value['process_launches']==0
 replay=mod.write_reconciled_collector(output_root=output,freeze_root=freeze,queue_root=queue,collector_output=collector,authorization_acknowledgement_sha256=acknowledgement)
 assert replay['cells']==64 and replay['historical_process_launches']==64

def test_finalize_collector_accepts_63_normal_receipts_and_one_terminal_reconciliation(tmp_path):
 mod=module(); freeze,resolution,output,queue,acknowledgement=_mixed_output(mod,tmp_path,normal_cells=63); collector=tmp_path/'mixed-collector.json'
 value=mod.finalize_collector(output_root=output,freeze_root=freeze,queue_root=queue,collector_output=collector,authorization_acknowledgement_sha256=acknowledgement)
 assert value['normal_receipt_cells']==63 and value['reconciled_terminal_cells']==1 and value['historical_process_launches']==64 and value['no_resend'] is True
 replay=mod.replay_collector(output_root=output,freeze_root=freeze,collector_path=collector,authorization_acknowledgement_sha256=acknowledgement)
 assert replay['normal_receipt_cells']==63 and replay['reconciled_terminal_cells']==1
 normal=output/resolution['rows'][0]['cell_id']/'responses'/'batch-0001.attempt-0001.message.json'; terminal=output/resolution['rows'][-1]['cell_id']/'responses'/'batch-0001.attempt-0001.message.json'; normal.write_bytes(terminal.read_bytes())
 with pytest.raises(ValueError,match='final|response|binding'):
  mod.replay_collector(output_root=output,freeze_root=freeze,collector_path=collector,authorization_acknowledgement_sha256=acknowledgement)

def test_finalize_collector_rejects_cross_class_duplicate_identity(tmp_path):
 mod=module(); freeze,_resolution,output,queue,acknowledgement=_mixed_output(mod,tmp_path,normal_cells=1,duplicate_cross_class=True)
 with pytest.raises(ValueError,match='duplicate Sol lifecycle identity across normal and reconciled cells'):
  mod.finalize_collector(output_root=output,freeze_root=freeze,queue_root=queue,collector_output=tmp_path/'collector.json',authorization_acknowledgement_sha256=acknowledgement)

def test_reconcile_rejects_each_missing_terminal_lifecycle_artifact(tmp_path):
 mod=module(); freeze,resolution,output,acknowledgement=_terminal_output(mod,tmp_path); cell=output/resolution['rows'][0]['cell_id']
 for artifact in ('launch-intent.json','zero-charge-route-proof.json','prepared.json'):
  raw=(cell/artifact).read_bytes(); (cell/artifact).unlink()
  with pytest.raises(ValueError,match='inventory|incomplete'):
   mod.reconcile_existing_output(output_root=output,freeze_root=freeze,authorization_acknowledgement_sha256=acknowledgement)
  (cell/artifact).write_bytes(raw)

def test_reconcile_rejects_bad_event_order_duplicate_identity_and_swapped_output(tmp_path):
 mod=module(); freeze,resolution,output,acknowledgement=_terminal_output(mod,tmp_path); first,second=(output/resolution['rows'][index]['cell_id'] for index in range(2))
 first_events=(first/'responses'/'batch-0001.attempt-0001.events.jsonl').read_bytes(); second_events=(second/'responses'/'batch-0001.attempt-0001.events.jsonl').read_bytes(); events=first_events.decode('utf-8').splitlines(); events[1],events[2]=events[2],events[1]; broken=('\n'.join(events)+'\n').encode('utf-8'); (first/'responses'/'batch-0001.attempt-0001.events.jsonl').write_bytes(broken)
 with pytest.raises(ValueError,match='sequence|nonterminal'):
  mod.reconcile_existing_output(output_root=output,freeze_root=freeze,authorization_acknowledgement_sha256=acknowledgement)
 (first/'responses'/'batch-0001.attempt-0001.events.jsonl').write_bytes(first_events); duplicate=second_events.decode('utf-8').replace('fixture-thread-1','fixture-thread-0').encode('utf-8'); (second/'responses'/'batch-0001.attempt-0001.events.jsonl').write_bytes(duplicate)
 with pytest.raises(ValueError,match='duplicate terminal lifecycle identity'):
  mod.reconcile_existing_output(output_root=output,freeze_root=freeze,authorization_acknowledgement_sha256=acknowledgement)
 (second/'responses'/'batch-0001.attempt-0001.events.jsonl').write_bytes(second_events); first_message=first/'responses'/'batch-0001.attempt-0001.message.json'; second_message=second/'responses'/'batch-0001.attempt-0001.message.json'; first_message.write_bytes(second_message.read_bytes())
 with pytest.raises(ValueError,match='event/message binding'):
  mod.reconcile_existing_output(output_root=output,freeze_root=freeze,authorization_acknowledgement_sha256=acknowledgement)

def test_terminal_projection_accepts_only_final_completed_agent_message():
 mod=module();final={'scores':{name:3 for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')},'evidence':{name:'Final evidence cites the writing.' for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')},'coverage':{name:True for name in ('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')}}
 interim={'scores':{name:0 for name in final['scores']},'evidence':{name:'interim' for name in final['scores']},'coverage':{name:False for name in final['scores']}}
 events=[{'type':'thread.started','thread_id':'thread-1'},{'type':'turn.started'},{'type':'item.completed','item':{'type':'agent_message','text':mod.canonical(interim).decode().strip()}},{'type':'item.completed','item':{'type':'agent_message','text':mod.canonical(final).decode().strip()}},{'type':'turn.completed','usage':{}}]
 projection=mod._terminal_projection(('\n'.join(json.dumps(item) for item in events)+'\n').encode())
 assert projection['completed_agent_message_text']==mod.canonical(final).decode().strip()
 events[-1],events[-2]=events[-2],events[-1]
 with pytest.raises(ValueError,match='sequence|last output'):
  mod._terminal_projection(('\n'.join(json.dumps(item) for item in events)+'\n').encode())
