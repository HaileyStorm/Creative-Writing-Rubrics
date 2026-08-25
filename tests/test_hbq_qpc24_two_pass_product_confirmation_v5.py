from __future__ import annotations
import importlib.util
import json
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
PUBLIC=REPO/'evaluation-results'/'hbq-qpc24-two-pass-product-confirmation-v5'

def load(path:Path,name:str):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(module);return module

def test_public_contract_reconstructs_full_current_geometry():
 result=load(PUBLIC/'study.py','qpc24_v5_public').validate()
 assert result['provider_calls']==0 and result['inherited_complete_calls']==50
 assert result['planned_new_calls']==10 and result['total_voting_calls']==60 and result['verdict_positions']==1326
 text_files=[path for path in PUBLIC.iterdir() if path.name in {'README.md','study-contract.json','study.py'}]
 assert 'C:\\Users\\' not in '\n'.join(path.read_text(encoding='utf-8') for path in text_files)

def test_public_contract_is_plan_only_and_contains_no_dispatch_surface():
 contract=json.loads((PUBLIC/'study-contract.json').read_text(encoding='utf-8'))
 assert contract['execution']['provider_free_now'] is True
 assert contract['execution']['remote_provider_call_count_now']==0
 assert contract['execution']['dispatch_surface']=='absent'
 assert {path.name for path in PUBLIC.iterdir() if path.suffix!='.pyc' and path.name!='__pycache__'}=={'README.md','study-contract.json','study.py'}
