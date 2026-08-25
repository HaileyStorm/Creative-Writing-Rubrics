from __future__ import annotations
import importlib.util,re,sys
from pathlib import Path
from hbqrs.paths import book_root
BOOK=book_root();ROOT=BOOK/"evaluation-results"/"hbq-figurative-hinge-treatment-successor-v7"
DENY={"verdict","door","appeal","archive","mausoleum","nursery","promise","home","fence","bell","funeral","reveille","town","compass","harbor","hand"}
def study():
 s=importlib.util.spec_from_file_location("hingev7",ROOT/"study.py");m=importlib.util.module_from_spec(s);assert s and s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m
def words(text): return re.findall(r"[a-z]+",text.casefold())
def ngrams(tokens,n): return {tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)}
def test_v7_geometry_and_required_sentence():
 m=study();assert m.validate()=={"study_id":m.STUDY_ID,"slots":6,"provider_calls":0,"promotion":"none"};assert "Sharing a subject, pairing opposite labels" in m.contract()["treatment"]["exact_text"]
def test_semantic_carrier_denylist_and_normalized_overlap_rejection():
 current=' '.join(x['text'] for x in study().corpus());assert not (set(words(current))&DENY)
 prior=[]
 for version in range(1,7):
  path=BOOK/"evaluation-results"/f"hbq-figurative-hinge-treatment-successor-v{version}"/"public-synthetic-corpus.json"
  if path.is_file(): prior.extend(item['text'] for item in __import__('json').loads(path.read_text(encoding='utf-8'))['cases'])
 candidate=words(current);old=words(' '.join(prior))
 for n in range(4,9): assert not (ngrams(candidate,n)&ngrams(old,n)),n
def test_new_opposed_pair_has_external_hinge_only_in_positive():
 rows={x['case_id']:x['text'] for x in study().corpus()};assert 'after rehearsal' in rows['o2'] and 'at dawn' in rows['o2'];assert 'those same dancers' in rows['p3']
