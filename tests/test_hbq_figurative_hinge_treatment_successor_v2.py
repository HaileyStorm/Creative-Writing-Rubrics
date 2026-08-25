from __future__ import annotations
import importlib.util,sys
from hbqrs.paths import book_root
ROOT=book_root()/"evaluation-results"/"hbq-figurative-hinge-treatment-successor-v2"
def study():
 s=importlib.util.spec_from_file_location("hingev2",ROOT/"study.py");m=importlib.util.module_from_spec(s);assert s and s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m
def test_balanced_hinge_v2_contract():
 m=study();assert m.validate()=={"study_id":m.STUDY_ID,"slots":8,"provider_calls":0,"promotion":"none"};assert len(m.slots())==8;t=m.contract()["treatment"]["exact_text"];assert "compatible and jointly clarify" in t and "Punctuation" in t
def test_no_label_or_punctuation_polarity_leakage():
 m=study();assert all(set(x)=={"case_id","text"} for x in m.corpus());texts={x["case_id"]:x["text"] for x in m.corpus()};assert "and" in texts["f1"] and ":" in texts["g2"] and "and" in texts["h3"] and "but" in texts["j4"]
