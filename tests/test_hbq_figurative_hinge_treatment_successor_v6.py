from __future__ import annotations
import importlib.util,sys
from hbqrs.paths import book_root
ROOT=book_root()/"evaluation-results"/"hbq-figurative-hinge-treatment-successor-v6"
def study():
 s=importlib.util.spec_from_file_location("hingev6",ROOT/"study.py");m=importlib.util.module_from_spec(s);assert s and s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m
def test_final_small_geometry_and_exact_anti_shortcut():
 m=study();assert m.validate()=={"study_id":m.STUDY_ID,"slots":6,"provider_calls":0,"promotion":"none"};t=m.contract()["treatment"]["exact_text"];assert "Sharing a subject, pairing opposite labels, or restating them with opposite verbs is not an additional hinge; the artifact must supply a relation beyond the coexistence itself." in t
def test_three_cases_are_fresh_and_j4_is_absent():
 m=study();rows={x["case_id"]:x["text"] for x in m.corpus()};assert set(rows)=={"k1","l2","m3"};assert "j4" not in rows;assert "closed the hearing, then carried the case into appeal" in rows["l2"];assert "shut the hearing and opened that same hearing" in rows["m3"]
