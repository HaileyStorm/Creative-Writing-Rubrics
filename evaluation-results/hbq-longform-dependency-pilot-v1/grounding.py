"""Named, post-prefix CRLF span descendant; native responses remain immutable."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

POLICY = 'p4_crlf_span_grounding_v1'
DECISION_SHA = '9fc64d6beaffbbd2f3224942db139d70ecb4f6adc205ee128ac18026d5eaf822'
CONTRACT = {
    'policy': POLICY, 'projections': ['exact_identity', 'CRLF_to_LF', 'CRLF_to_one_ASCII_space'],
    'offsets': 'zero_based_half_open_python_characters_and_UTF8_bytes',
    'ambiguity': 'retain_all_locations; differing_recovered_spans_fail_closed',
    'identity_precedence': 'existing_exact_substrings_remain_unchanged',
    'scope': 'committed_available_representation; HBQ_also_declared_task_context',
    'changes': 'evidence_quote_fields_only; unchanged_schema_and_strict_validator',
    'authority': 'post_prefix_task_controller_decision; no_separate_human_approval',
    'provider_calls': 0, 'new_votes': 0,
}


def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
CONTRACT_SHA = digest(canonical(CONTRACT))


def projection(text, mode):
    """Boundaries map each projected character back to its contiguous raw span."""
    if mode not in CONTRACT['projections']: raise ValueError('Unknown CRLF projection')
    output, boundaries, at = [], [0], 0
    while at < len(text):
        if mode != 'exact_identity' and text.startswith('\r\n',at):
            output.append('\n' if mode == 'CRLF_to_LF' else ' '); at += 2
        else: output.append(text[at]); at += 1
        boundaries.append(at)
    return ''.join(output),boundaries


def occurrences(text, quote):
    at = text.find(quote)
    while at >= 0:
        yield at
        at = text.find(quote,at+1)


class SpanSources:
    def __init__(self, sources):
        self.sources = sources; self.cache = {}
        self.byte_offsets = {}
        for key,source in sources.items():
            offsets = [0]
            for character in source['text']: offsets.append(offsets[-1]+len(character.encode('utf-8')))
            self.byte_offsets[key] = offsets

    def matches(self, quote, modes):
        matches = []
        for key,source in self.sources.items():
            text = source['text']; offsets = self.byte_offsets[key]
            for mode in modes:
                if (key,mode) not in self.cache: self.cache[key,mode] = projection(text,mode)
                projected,bounds = self.cache[key,mode]
                for at in occurrences(projected,quote):
                    start,end = bounds[at],bounds[at+len(quote)]; span = text[start:end]
                    if projection(span,mode)[0] != quote: raise ValueError('Inverse span proof failed')
                    location = {'source_id':key,'source_path':source['path'],'source_sha256':digest(text.encode('utf-8')),
                        'projection':mode,'projected_char':[at,at+len(quote)],'source_char':[start,end],
                        'source_utf8_byte':[offsets[start],offsets[end]],'span_sha256':digest(span.encode('utf-8')),
                        'projected_span_sha256':digest(quote.encode('utf-8'))}
                    if source.get('original_coordinates'):
                        original = source['original_coordinates']
                        location['original_source'] = {'path':original['path'],'sha256':original['sha256'],
                            'char':[original['char_start']+start,original['char_start']+end],
                            'utf8_byte':[original['byte_start']+offsets[start],original['byte_start']+offsets[end]]}
                    matches.append((span,location))
        return matches

    def prove(self, quote):
        proof = {'native_quote':quote,'native_quote_sha256':digest(quote.encode('utf-8')),
            'exact_source_quote':None,'locations':[],'ambiguous_locations':False}
        if not quote.strip(): return {**proof,'state':'unsupported_blank_quote'}
        matches = self.matches(quote,['exact_identity'])
        if matches:
            state,span = 'exact_inherited',quote
        else:
            matches = self.matches(quote,['CRLF_to_LF','CRLF_to_one_ASCII_space'])
            spans = {span for span,_ in matches}
            if not spans: return {**proof,'state':'unsupported_transformation_or_unavailable_source'}
            if len(spans)>1:
                return {**proof,'state':'ambiguous_distinct_spans','locations':[loc for _,loc in matches],
                    'ambiguous_locations':True,'candidate_span_sha256s':sorted({digest(s.encode('utf-8')) for s in spans})}
            span = next(iter(spans)); state = 'projected_exact_span'
        return {**proof,'state':state,'exact_source_quote':span,'exact_source_quote_sha256':digest(span.encode('utf-8')),
            'locations':[loc for _,loc in matches],'ambiguous_locations':len(matches)>1}


def quote_fields(value, path=()):
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('quote','exact_quote') and isinstance(item,str): yield path+(key,),item
            else: yield from quote_fields(item,path+(key,))
    elif isinstance(value,list):
        for index,item in enumerate(value): yield from quote_fields(item,path+(index,))


def derive(response, row, sources, context, schema, subset, validator):
    """Caller must first replay the original own native receipt and strict terminal."""
    original_sha = digest(canonical(response)); derived = deepcopy(response)
    certificate = {'policy':POLICY,'contract_sha256':CONTRACT_SHA,'original_response_canonical_sha256':original_sha,
        'quotes':[],'changed_quote_fields':0,'response':None}
    original_admission = validator.semantic_validate(row['arm'],response,row,
        {row['work_id']:sources['available']['text']},subset,context=context,schema=schema)
    certificate['original_admission'] = original_admission
    if not subset.matches_schema(response,schema):
        return {**certificate,'state':'original_schema_rejected','descendant_admission':original_admission}
    allowed = dict(sources)
    if row['arm'] != 'hbq': allowed.pop('task_context',None)
    span_sources = SpanSources(allowed)
    unsupported = False
    for path,quote in quote_fields(response):
        proof = span_sources.prove(quote); certificate['quotes'].append({'field_path':list(path),**proof})
        if proof['exact_source_quote'] is None: unsupported = True; continue
        if proof['exact_source_quote'] != quote and not original_admission['accepted']:
            parent = derived
            for key in path[:-1]: parent = parent[key]
            parent[path[-1]] = proof['exact_source_quote']; certificate['changed_quote_fields'] += 1
    admission = validator.semantic_validate(row['arm'],derived,row,
        {row['work_id']:sources['available']['text']},subset,context=context,schema=schema)
    accepted = original_admission['accepted'] or (not unsupported and admission['accepted'])
    state = 'strict_accepted_inherited' if original_admission['accepted'] else 'projected_accepted' if accepted else 'descendant_rejected'
    return {**certificate,'state':state,'descendant_admission':admission,
        'descendant_response_canonical_sha256':digest(canonical(derived)),
        'response':derived if accepted else None}
