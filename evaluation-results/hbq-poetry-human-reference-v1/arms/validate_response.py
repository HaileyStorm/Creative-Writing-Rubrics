"""Strict presented-text admission; no literary oracle or quote repair."""
from pathlib import Path
import importlib.util

HERE=Path(__file__).resolve().parent


def semantic_validate(arm,response,request,source_texts,subset,context='',schema=None):
    if arm!='poemetric':
        path=HERE/'mfa-admission.py' if HERE.name=='implementation' else HERE.parents[1]/'hbq-matched-mfa-v1/validate_response.py'
        spec=importlib.util.spec_from_file_location('poetry_reference_exact_admission',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.semantic_validate(arm,response,request,source_texts,subset,context=context,schema=schema)
    if schema is None or not subset.matches_schema(response,schema):
        return {'accepted':False,'abstention':False,'errors':['Response violates frozen POEMetric descendant schema']}
    sources=request.get('sources',[])
    if len(sources)!=1 or sources[0]['id'] not in source_texts:
        return {'accepted':False,'abstention':False,'errors':['Committed presented poem unavailable']}
    text=source_texts[sources[0]['id']];errors=[]
    def require(condition,message):
        if not condition:errors.append(message)
    def nonblank(value):return isinstance(value,str) and bool(value.strip())
    def evidence(items,low,high):
        require(low<=len(items)<=high,'POEMetric evidence cardinality differs')
        for item in items:
            require(nonblank(item['quote']) and item['quote'] in text,'POEMetric quote is not an exact presented-poem substring')
            require(nonblank(item['explanation']),'POEMetric evidence explanation is blank')
    abstention=response['status']=='CANNOT_ASSESS'
    if abstention:
        require(response['result'] is None and nonblank(response['abstention_reason']),'Abstention requires null result and reason')
    else:
        result=response['result']
        require(isinstance(result,dict) and response['abstention_reason'] is None,'Scored result requires complete result and null abstention')
        if isinstance(result,dict):
            rows=result['diagnostics'];require(len(rows)==8 and {row['item_id'] for row in rows}==set(range(1,9)),
                'Diagnostics require items1–8 exactly once')
            for row in rows:
                require(nonblank(row['rationale']),'Diagnostic rationale is blank')
                if row['item_id'] in (1,2):
                    require(row['status']=='CANNOT_ASSESS' and row['score'] is None,'Unavailable form/theme instruction fit must be CA/null')
                    evidence(row['evidence'],0,3)
                else:
                    score=row['score'];require(row['status']=='SCORED' and isinstance(score,int), 'Assessed diagnostic requires native integer score')
                    require(score is not None and (score>=1 or row['item_id'] in (7,8)),'Absence zero is permitted only for imagery/devices')
                    evidence(row['evidence'],0 if score==0 else 1,3)
            quality=result['overall_quality'];require(nonblank(quality['rationale']),'Primary quality rationale is blank')
            evidence(quality['evidence'],2,5)
            for field in ('literary_devices_comment','quality_comment'):
                comment=result[field];require(nonblank(comment['comment']),'Separate local comment is blank')
                absent_devices=any(row['item_id']==8 and row['score']==0 for row in rows)
                evidence(comment['evidence'],0 if field=='literary_devices_comment' and absent_devices else 1,3)
    return {'accepted':not errors,'abstention':abstention,'errors':errors}
