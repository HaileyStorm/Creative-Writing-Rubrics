"""Exact relaxed kappa bounds from the published four-state aggregate."""
import argparse
from fractions import Fraction
import hashlib
import json
import subprocess
from pathlib import Path

COMMIT = 'e33e2ad50706447c66982db73b1edc3c2411b277'
PATH = 'evaluation-results/hbq-sol-longform-saved-state-contrast-20261029/report.json'
SOURCE = '16202540248a1dfd06f0188cf89c4d4ce4275b8c95d37497469ba867073ae8c7'
STATES = ('YES', 'NO', 'CANNOT_ASSESS', 'NOT_APPLICABLE')


def compositions(n):
    for a in range(n+1):
        for b in range(n-a+1):
            for c in range(n-a-b+1):
                yield (a,b,c,n-a-b-c)


def extrema(left, right, agreed, missing):
    n=sum(left)+missing
    if sum(left)!=sum(right) or n<=0 or missing<0: raise ValueError('invalid margins')
    margins=list(compositions(missing)); low=None; high=None; undefined=0
    for u in margins:
        a=tuple(x+y for x,y in zip(left,u))
        for v in margins:
            b=tuple(x+y for x,y in zip(right,v))
            dot=sum(x*y for x,y in zip(a,b)); den=n*n-dot
            if not den:
                undefined+=1
                continue
            lo=max(0,max(x+y-missing for x,y in zip(u,v)))
            hi=sum(min(x,y) for x,y in zip(u,v))
            numlo=(agreed+lo)*n-dot; numhi=(agreed+hi)*n-dot
            if low is None or numlo*low[1] < low[0]*den: low=(numlo,den)
            if high is None or numhi*high[1] > high[0]*den: high=(numhi,den)
    if low is None or high is None: raise ValueError('no defined kappa')
    return Fraction(*low),Fraction(*high),len(margins)**2,undefined


def analyze(raw):
    if hashlib.sha256(raw).hexdigest()!=SOURCE: raise ValueError('source bytes changed')
    data=json.loads(raw); entries=data['four_state_transitions']
    counts={(r['left'],r['right']):r['count'] for r in entries}
    if len(entries)!=16 or len(counts)!=16 or set(counts)!={(a,b) for a in STATES for b in STATES}: raise ValueError('invalid transition inventory')
    if any(type(x) is not int or x<0 for x in counts.values()): raise ValueError('invalid count')
    left=tuple(sum(counts[a,b] for b in STATES) for a in STATES)
    right=tuple(sum(counts[a,b] for a in STATES) for b in STATES)
    agreed=sum(counts[a,a] for a in STATES)
    missing=data['missing_leaves']
    if (left,right,agreed,missing)!=( (117,8,1,13),(115,8,3,13),132,16): raise ValueError('unexpected scope')
    low,high,work,undefined=extrema(left,right,agreed,missing)
    n=sum(left); dot=sum(a*b for a,b in zip(left,right)); observed=Fraction(agreed*n-dot,n*n-dot)
    return {'schema':'longform_kappa_missingness_v1','source_commit':COMMIT,'source_sha256':SOURCE,
            'observed_pairs':n,'missing_pairs':missing,'planned_pairs':n+missing,
            'observed_kappa':str(observed),'relaxed_minimum_kappa':str(low),'relaxed_maximum_kappa':str(high),
            'margin_pairs_evaluated':work,'undefined_margin_pairs':undefined,
            'assumption':'both labels of every missing pair vary freely; this relaxes known one-sided observations',
            'not':'confidence interval, imputation, human validity, controlled runtime, or new judgments'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--verify',type=Path);args=p.parse_args()
    raw=subprocess.run(['git','-C',str(args.repo),'show',COMMIT+':'+PATH],check=True,stdout=subprocess.PIPE).stdout
    output=(json.dumps(analyze(raw),indent=2,sort_keys=True)+'\n').encode()
    if args.verify:
        if args.verify.read_bytes().replace(b'\r\n',b'\n')!=output: raise ValueError('aggregate differs')
        print('Aggregate reproduced')
    else: print(output.decode(),end='')

if __name__=='__main__': main()
