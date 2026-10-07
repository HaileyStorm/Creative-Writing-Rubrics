"""Independent optimizer and held-target isolation checks on numeric fixtures."""
from fractions import Fraction as F
import unittest
import source

class Calibration(unittest.TestCase):
    def test_weighted_ties_against_exhaustive_partition_optimum(self):
        points=[(F(0),F(4),F(1,2)),(F(0),F(2),F(1,2)),(F(1),F(1),F(1)),(F(2),F(5),F(2))]
        knots=dict(source.pava(points));xs=sorted({x for x,_,_ in points});objectives=[]
        for mask in range(1<<(len(xs)-1)):
            starts=[0]+[i+1 for i in range(len(xs)-1) if mask&(1<<i)]+[len(xs)]
            fitted={};levels=[]
            for left,right in zip(starts,starts[1:]):
                members=set(xs[left:right]);subset=[(y,w) for x,y,w in points if x in members]
                mean=sum(y*w for y,w in subset)/sum(w for _,w in subset)
                levels.append(mean);fitted.update({x:mean for x in members})
            if all(a<=b for a,b in zip(levels,levels[1:])):
                objectives.append(sum(w*(fitted[x]-y)**2 for x,y,w in points))
        self.assertEqual(sum(w*(knots[x]-y)**2 for x,y,w in points),min(objectives))
        self.assertEqual(knots,{F(0):F(2),F(1):F(2),F(2):F(5)})

    def test_held_prompt_labels_do_not_change_predictions_or_fit(self):
        train=list('abcd');held=list('ef')
        prompts=dict(a='p1',b='p1',c='p2',d='p3',e='p4',f='p4')
        scores=dict(a=F(0),b=F(0),c=F(1),d=F(2),e=F(1,2),f=F(3,2))
        targets=dict(a=F(1),b=F(3),c=F(2),d=F(4),e=F(1),f=F(5))
        first=source.fold_predictions(train,held,scores,targets,prompts,[0,2])
        second=source.fold_predictions(train,held,scores,dict(targets,e=F(5),f=F(1)),prompts,[0,2])
        self.assertEqual(first,second)
        self.assertEqual(first[1]['training_weights']['a'],F(1,2))
        self.assertEqual(first[1]['training_prompts'],3)
        tied=source.curve_bins(train+held,{i:F(3) for i in train+held},targets,prompts)
        self.assertEqual(len(tied),1)
        self.assertEqual(tied[0]['items'],6)
        with self.assertRaisesRegex(ValueError,'Prompt-disjoint'):
            source.fold_predictions(train,held,scores,targets,dict(prompts,e='p1'),[0,2])

if __name__=='__main__':unittest.main()
