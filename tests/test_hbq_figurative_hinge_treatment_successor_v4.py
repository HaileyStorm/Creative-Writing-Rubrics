from __future__ import annotations
import importlib.util,json,sys
from hbqrs.paths import book_root
ROOT=book_root()/"evaluation-results"/"hbq-figurative-hinge-treatment-successor-v4"
def study():
 s=importlib.util.spec_from_file_location("hingev4",ROOT/"study.py");m=importlib.util.module_from_spec(s);assert s and s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m
def labels(): return {"f1":"YES","g2":"YES","h3":"NO","j4":"NO"}
def test_v4_contract_and_lineage():
 m=study();assert m.validate()=={"study_id":m.STUDY_ID,"slots":8,"provider_calls":0,"promotion":"none"};assert m.contract()["source_anchor"]["predecessor"]=="hbq-figurative-hinge-treatment-successor-v3-zero-call"
def test_punctuation_connective_features_are_not_perfectly_correlated_with_label():
 m=study();rows={x["case_id"]:x["text"] for x in m.corpus()};y=[rows[k] for k,v in labels().items() if v=="YES"];n=[rows[k] for k,v in labels().items() if v=="NO"]
 features={"colon":lambda text:":" in text,"connective":lambda text:any(token in text.casefold() for token in (" and "," but "," also "))}
 for feature,has in features.items():
  assert any(has(text) for text in y) and any(not has(text) for text in y),feature
  assert any(has(text) for text in n) and any(not has(text) for text in n),feature
def test_v4_exact_cases_change_both_sides_of_colon_confound():
 m=study();rows={x["case_id"]:x["text"] for x in m.corpus()};assert ":" not in rows["f1"] and "so" in rows["f1"];assert ":" in rows["j4"] and "born there" in rows["j4"]
