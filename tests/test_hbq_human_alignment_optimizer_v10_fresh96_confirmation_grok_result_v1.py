from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1];PACKAGE=ROOT/'evaluation-results'/'hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-result-v1'
def module():
 s=importlib.util.spec_from_file_location('v10_result',PACKAGE/'verify.py');assert s and s.loader;m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_public_result_is_grok_only_and_aggregate_only():
 v=json.loads((PACKAGE/'result.json').read_bytes());assert v['geometry']=={'cells':64,'dimensions':6,'groups':16,'items':32};assert v['endpoint']=='grok_primary';assert v['native_endpoint_contact_cardinality']=='unproven';assert v['authority']=={'confirmation':'measurement_only','endpoint_pooling':'forbidden','generalization':'none','promotion':'none','runtime':'none','selection':'none','sol':'not_implemented'};assert 'prompt-' not in (PACKAGE/'result.json').read_text()
def test_external_replay_is_opt_in():
 r=os.getenv('CWR_V10_R1_ROOT');f=os.getenv('CWR_V10_FREEZE_ROOT');c=os.getenv('CWR_V10_COLLECTOR')
 if not all((r,f,c)):pytest.skip('external immutable V10 evidence not supplied')
 o=module().verify(output_root=Path(r),freeze_root=Path(f),collector_path=Path(c));assert o['comparison']['wins_ties_losses']=={'child20':15,'ties':1,'losses':0}
