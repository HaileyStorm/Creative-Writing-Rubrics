"""Finite historical schedule-ID/directory-name join; no output contents opened."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,stat
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
COMMON=HERE.parent/'hbq-census-wpb-metadata-v1/census.py'
COMMON_SHA='e4bec7354352abc24665951875c7b71331151b42c68b1d206b77bc9c9a9ea0f6'
SELECTOR={'study_id':True,'schedule_sha256':True,'cells':[{key:True for key in ('cell_id','candidate_id','item_id','prompt_group_id')}]}
def require(condition,message):
    if not condition:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
def plain(path):
    require(path.is_absolute(),'Absolute input root required')
    for current in (path,*path.parents):
        metadata=current.lstat()
        require(not stat.S_ISLNK(metadata.st_mode) and not (getattr(metadata,'st_file_attributes',0)&0x400),'Reparse/symlink input rejected')
def checked(path,pin):
    plain(path)
    raw=path.read_bytes()
    require(len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],'Frozen source bytes differ')
    return raw
def projector():
    require(sha(COMMON.read_bytes())==COMMON_SHA,'Pinned projection adapter differs')
    spec=importlib.util.spec_from_file_location('fresh96_pinned_projection_adapter',COMMON)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.common().project
def directory_id(cell):return 'v10-sol-'+sha(canonical({'source':cell}))[:16]
def directory_names(outputs):
    plain(outputs)
    names=[]
    for child in outputs.iterdir():
        metadata=child.lstat()
        require(not (getattr(metadata,'st_file_attributes',0)&0x400) and stat.S_ISDIR(metadata.st_mode),'Output child is not a plain directory')
        names.append(child.name)
    return sorted(names)
def join(schedule,names,expected):
    cells=schedule['cells'];require(len(cells)==expected['cells'],'Frozen cell count differs')
    keys=set(SELECTOR['cells'][0]);require(all(set(cell)==keys and all(isinstance(v,str) and bool(v) for v in cell.values()) for cell in cells),'Cell identity schema differs')
    require(len({cell['cell_id'] for cell in cells})==len(cells),'Duplicate schedule cell')
    candidates={cell['candidate_id'] for cell in cells};items={cell['item_id'] for cell in cells};groups={cell['prompt_group_id'] for cell in cells}
    require((len(candidates),len(items),len(groups))==(expected['candidates'],expected['items'],expected['prompt_groups']),'Frozen membership counts differ')
    require(len({(cell['candidate_id'],cell['item_id']) for cell in cells})==len(cells),'Duplicate candidate/item cell')
    require(all({cell['item_id'] for cell in cells if cell['candidate_id']==candidate}==items for candidate in candidates),'Unbalanced candidate/item membership')
    require(all(len({cell['prompt_group_id'] for cell in cells if cell['item_id']==item})==1 for item in items),'Item/group mapping differs')
    rows=[dict(cell,directory_id=directory_id(cell['cell_id'])) for cell in cells]
    require(len({row['directory_id'] for row in rows})==len(rows),'Directory transform collision')
    require(len(names)==len(set(names))==expected['cells'] and set(names)=={row['directory_id'] for row in rows},'Directory/schedule membership differs')
    return sorted(rows,key=lambda row:row['cell_id'])
def run(freeze,outputs,recipe):
    plain(freeze);plain(outputs)
    require(recipe['schema_version']==1 and recipe['policy']=='historical_fresh96_schedule_directory_membership_v1','Wrong census policy')
    roots=recipe['source_roots']
    require(roots['root_id']=='documents' and freeze.name==roots['freeze'] and outputs.name==roots['outputs'] and freeze.parent==outputs.parent,'Frozen source root locators differ')
    for pin in recipe['source_implementations'].values():require(sha((REPO/pin['locator']).read_bytes())==pin['sha256'],'Source implementation differs')
    manifest_raw=checked(freeze/'manifest.json',recipe['manifest']);schedule_raw=checked(freeze/'schedule.json',recipe['schedule'])
    manifest=json.loads(manifest_raw)
    require(manifest=={'study_id':recipe['study_id'],'schedule_sha256':recipe['declared_logical_schedule_sha256'],'candidate_sha256s':recipe['candidate_sha256s'],'analysis_rule_sha256':recipe['analysis_rule_sha256']},'Four-field freeze manifest differs')
    schedule=projector()(schedule_raw,SELECTOR)
    require(schedule['study_id']==recipe['study_id'] and schedule['schedule_sha256']==manifest['schedule_sha256'],'Projected schedule declaration differs')
    names=directory_names(outputs)
    rows=join(schedule,names,recipe['expected'])
    ledger={'membership':rows,'source_roots':roots,'raw_manifest_sha256':sha(manifest_raw),'raw_schedule_sha256':sha(schedule_raw)}
    report={'schema_version':1,'policy':recipe['policy'],'study_id':recipe['study_id'],'observed':recipe['expected'],
            'exact_directory_membership':True,'directory_set_sha256':sha(canonical(sorted(names))),
            'cell_directory_membership_sha256':sha(canonical(rows)),'private_ledger_sha256':sha(canonical(ledger)),
            'manifest_sha256':sha(manifest_raw),'raw_schedule_sha256':sha(schedule_raw),
            'declared_logical_schedule_sha256':manifest['schedule_sha256'],'logical_schedule_hash_recomputed':False,
            'source_roots':roots,'source_implementations':recipe['source_implementations'],'projection_adapter_sha256':COMMON_SHA,
            'selector':SELECTOR,'disposition':recipe['disposition'],'collector_locator':None,'missing_collector_sha256':recipe['missing_collector_sha256'],
            'registry_v6_modified':False,'provider_calls':0,'new_provider_votes':0,'native_output_contents_opened':0,
            'whole_schedule_utf8_decoded_for_lexing':True,'request_payloads_or_human_targets_materialized':False,
            'native_admission_replayed':False,'scoring_replayed':False,
            'physical_contact_cardinality':None,'qualified_measurements_added':0,'unused_confirmation':False}
    return report,ledger
def create(path,raw):
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Output readback differs')
def main():
    parser=argparse.ArgumentParser()
    for flag in ('freeze-root','outputs-root','output'):parser.add_argument('--'+flag,required=True,type=Path)
    args=parser.parse_args();plain(args.output.absolute().parent);output=args.output.resolve()
    require(not output.exists() and all(not output.is_relative_to(root.resolve()) and not root.resolve().is_relative_to(output) for root in (REPO,args.freeze_root,args.outputs_root)),'Fresh private output outside repository and retained input roots required')
    plain(output.parent)
    recipe_raw=(HERE/'recipe.json').read_bytes();source_raw=Path(__file__).read_bytes();recipe=json.loads(recipe_raw)
    report,ledger=run(args.freeze_root.absolute(),args.outputs_root.absolute(),recipe)
    require((HERE/'recipe.json').read_bytes()==recipe_raw and Path(__file__).read_bytes()==source_raw,'Implementation changed during read')
    require(sha(checked(args.freeze_root.absolute()/'manifest.json',recipe['manifest']))==report['manifest_sha256'] and
            sha(checked(args.freeze_root.absolute()/'schedule.json',recipe['schedule']))==report['raw_schedule_sha256'] and
            sha(canonical(directory_names(args.outputs_root.absolute())))==report['directory_set_sha256'],'Sources changed before output')
    report.update(recipe_sha256=sha(recipe_raw),implementation_sha256=sha(source_raw))
    output.mkdir()
    for name,raw in [('report.json',canonical(report)),('private-ledger.json',canonical(ledger)),('recipe.json',recipe_raw),('census.py',source_raw)]:create(output/name,raw)
    terminal={'state':'completed','report_sha256':sha(canonical(report)),'private_ledger_sha256':sha(canonical(ledger)),
              'recipe_sha256':sha(recipe_raw),'implementation_sha256':sha(source_raw),'provider_calls':0,'new_provider_votes':0}
    create(output/'terminal.json',canonical(terminal));print(json.dumps(terminal,sort_keys=True))
if __name__=='__main__':main()
