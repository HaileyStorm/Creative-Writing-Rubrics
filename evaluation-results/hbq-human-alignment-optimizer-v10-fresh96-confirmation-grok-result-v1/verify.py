"""Independently recompute the public V10 Grok-only aggregate result."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
RESULT=HERE/'result.json'
COLLECTOR_SHA256='0049b04bdd29560a468be78c8b3c4d9bf979914cf1c77aded839100465b4eeb5'
DIMS=('Relevance','Coherence','Empathy','Surprise','Engagement','Complexity')

def canonical(value:Any)->bytes:return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha256(value:bytes|Any)->str:return hashlib.sha256(value if isinstance(value,bytes) else canonical(value)).hexdigest()
def load_reconciler():
 p=REPO/'evaluation-results'/'hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-reconcile-v1'/'reconcile.py';s=importlib.util.spec_from_file_location('_v10_result_reconcile',p);assert s and s.loader;m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def recompute(*,output_root:Path,freeze_root:Path,collector_path:Path)->dict[str,Any]:
 r=load_reconciler(); replay=r.replay_collector(output_root=output_root,freeze_root=freeze_root,collector_path=collector_path)
 raw=Path(collector_path).read_bytes()
 if sha256(raw)!=COLLECTOR_SHA256:raise ValueError('collector commitment drifted')
 collector=json.loads(raw); schedule=json.loads((Path(freeze_root)/'schedule.json').read_bytes()); index={x['cell_id']:x for x in schedule['cells']}; groups=defaultdict(lambda:defaultdict(list))
 if len(collector['cells'])!=64 or set(index)!={x['cell_id'] for x in collector['cells']}:raise ValueError('cell inventory drifted')
 for cell in collector['cells']:
  row=index[cell['cell_id']]; out=json.loads(base64.b64decode(cell['native_response_base64']))['structuredOutput']['scores'];groups[row['candidate_id']][row['prompt_group_id']].append(sum(abs(float(out[d])-float(row['target'][d])) for d in DIMS)/6)
 metrics=[]
 for candidate in ('candidate-102cc7f06c9a99a7','broader-nextwave-20-missing_evidence_not_no-referent-evidence'):
  gm={g:sum(v)/len(v) for g,v in groups[candidate].items()}
  if len(gm)!=16 or any(len(v)!=2 for v in groups[candidate].values()):raise ValueError('group geometry drifted')
  metrics.append({'candidate_id':candidate,'equal_group_mae':sum(gm.values())/16,'group_mae':gm})
 a,b=metrics; wins=sum(b['group_mae'][g]<a['group_mae'][g] for g in a['group_mae']);ties=sum(b['group_mae'][g]==a['group_mae'][g] for g in a['group_mae'])
 return {'metrics':metrics,'comparison':{'baseline_candidate_id':'candidate-102cc7f06c9a99a7','child20_minus_baseline':b['equal_group_mae']-a['equal_group_mae'],'child_candidate_id':'broader-nextwave-20-missing_evidence_not_no-referent-evidence','relative_reduction':(a['equal_group_mae']-b['equal_group_mae'])/a['equal_group_mae'],'wins_ties_losses':{'child20':wins,'ties':ties,'losses':16-wins-ties}},'replay':replay}
def verify(**kwargs:Any)->dict[str,Any]:
 observed=recompute(**kwargs); published=json.loads(RESULT.read_bytes())
 if observed['metrics'][0]['equal_group_mae']!=published['metrics'][0]['equal_group_mae'] or observed['metrics'][1]['equal_group_mae']!=published['metrics'][1]['equal_group_mae'] or observed['comparison']!=published['comparison']:raise ValueError('published aggregate drifted')
 return observed
