"""One behavioral guard: strict flips, ties and exact decimal distinctions."""
from fractions import Fraction as F
import source
def test():
    cases=[([-1,0,1,-1,1],'strict_reversal'),([1,0,1,0,1],'tie_changing_no_reversal'),([1]*5,'stable_strict'),([0]*5,'always_tied')]
    assert [source.category(s) for s,_ in cases]==[expected for _,expected in cases]
    summary=source.summarize([{'signs':cases[0][0]}])
    assert summary['sign_cross_tab']==[[1,1,3],[1,0,2],[1,0,1]]
    assert summary['strict_flip_comparisons']==4 and summary['tie_change_comparisons']==4 and summary['same_sign_comparisons']==2
    assert summary['strict_flip_rate_when_both_strict']==F(2,3)
    swapped=source.summarize([{'signs':[-s for s in cases[0][0]]}])
    assert swapped['pair_category_counts']==summary['pair_category_counts'] and swapped['strict_flip_comparisons']==4
    assert source.sign(F(1,10**30))==1 and source.sign(-F(1,10**30))==-1 and source.sign(F(0))==0
    tied=source.summarize([{'signs':[0]*5}]);empty=source.summarize([])
    assert tied['strict_flip_rate_all_comparisons']==0 and tied['strict_flip_rate_when_both_strict'] is None
    assert empty['pair_strict_reversal_rate'] is None and empty['repeat_index_pair_comparisons']==0
test();print('PASS 1 behavioral guard')
