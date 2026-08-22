from pathlib import Path
import importlib.util,pytest
P=Path(__file__).resolve().parents[1]/'evaluation-results'/'hbq-multisample-repeatability-v1-remainder-capacity-reset-settler-v5'/'settle.py'
def m():
 s=importlib.util.spec_from_file_location('v5',P);x=importlib.util.module_from_spec(s);s.loader.exec_module(x);return x
def test_freeze_v4_live_exact():
 x=m();f=x.freeze();assert f['batch_count']==6 and f['verdict_count']==179
def test_settle_requires_empty_root(tmp_path):
 x=m();(tmp_path/'x').write_text('x');
 with pytest.raises(ValueError):x.settle(tmp_path)
def test_owner_validator_is_invoked_and_failure_propagates(monkeypatch):
 x=m();called=[]
 monkeypatch.setattr(x,'_owner_validator',lambda:lambda *args:(called.append(args),(_ for _ in ()).throw(ValueError('owner failure')))[1])
 with pytest.raises(ValueError,match='owner failure'):x.freeze()
 assert called
def test_committed_execution_has_exact_lineage_counts():
 x=m();e=x.execution();assert e['lineage_sessions']['source']['unique_count']==146 and e['lineage_sessions']['closed']['unique_count']==183
